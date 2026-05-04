# Day 23 — Healthchecks, ECR, and Fargate prep

**Date:** Monday, May 4, 2026
**Hours covered:** 1–5 (ECS Fargate deployment in progress, paused mid-task)
**Branch:** `week4/day23`

---

## Healthchecks — the layered model

The most important conceptual win from today. There are three places a healthcheck "lives" and they have very different importance:

### 1. `app.py /health` route — the source of truth
The only place where actual health logic exists. Opens a database connection, runs `SELECT 1`, returns 200 with `{"status": "healthy"}` on success or 503 with `{"status": "unhealthy", "error": ...}` on failure. No other layer can do this — Compose can't reach into Python and ask Postgres a question, Docker can't either. **The check has to live where the dependencies live.**

```python
@app.route('/health')
def health():
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT 1')
        cur.close()
        conn.close()
        return jsonify({"status": "healthy"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 503
```

**Shallow vs deep healthchecks:**
- Shallow: just returns 200. Proves process is alive. Used for liveness probes (decide whether to *restart*).
- Deep: checks downstream dependencies. Proves service can do its job. Used for readiness probes (decide whether to *route traffic*).

Production usually has both: `/health/live` (shallow, restart trigger) and `/health/ready` (deep, traffic routing trigger).

### 2. Dockerfile `HEALTHCHECK` — the portable bridge
Bakes the probe command into the image so any orchestrator can use it. Travels with the image as a contract: "here's how you check if I'm healthy."

```dockerfile
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:5000/health || exit 1
```

Flags:
- `--interval=10s` — run every 10 seconds
- `--timeout=3s` — fail if check takes >3s
- `--start-period=10s` — grace period before failures count
- `--retries=3` — must fail 3 times consecutively to mark unhealthy

This is what makes the image self-describing. Without it, every consumer (Compose, ECS, K8s) has to re-specify probe behavior, possibly inconsistently.

### 3. docker-compose.yml `healthcheck:` — local dev override
The most replaceable layer. Useful when you don't control the image (added one for `db` because the official postgres image doesn't ship with one). **Disappears entirely in production** — ECS task definitions and K8s pod specs don't read docker-compose.yml.

### Importance hierarchy (counterintuitive but correct)
```
app.py route        ← most important, defines what "healthy" means
Dockerfile HEALTHCHECK  ← portable, ships with the image
Compose healthcheck    ← local-only, replaceable
```

The further down the stack you delete, the bigger the blast radius. Compose healthcheck "feels" most important because it does something *visible* (gates startup via `depends_on: condition: service_healthy`), but that's just the most local consumer. The signal itself is what matters.

### Healthcheck without a consumer = documentation
**A healthcheck without a consumer is documentation. A healthcheck with a consumer is policy enforcement.**

In healthy-app today, web's healthcheck has no consumer (nothing in compose.yml acts on it). Demonstrated: stop db, web flips to unhealthy, but `curl /visit` still returns 500 — Compose did nothing to drain traffic. That's because Compose isn't a production orchestrator.

In production, consumers read the same signal:
- **ECS Fargate** replaces unhealthy tasks automatically
- **ALB target groups** drain unhealthy targets from rotation
- **Kubernetes** uses livenessProbe (restart) + readinessProbe (drain)

Same signal you defined, different consumers picking up the phone.

### Why /health needs to be defined twice (sort of)
The Flask route exists in app.py. The HEALTHCHECK in Dockerfile tells Docker to *invoke* curl-to-Flask. Routes are for Flask, commands are for Docker — they communicate via HTTP requests and exit codes, never by reading each other's source. Inside the process Flask owns request handling; outside the process Docker runs commands and interprets exit codes.

---

## ECR — the artifact handoff point

ECR (Elastic Container Registry) = AWS's private Docker registry. Three properties matter:
1. **Private by default** — only authenticated callers in your AWS account
2. **IAM-integrated auth** — ECS tasks pull using their IAM role, no credentials to rotate
3. **Inside AWS network** — fast, free intra-AWS pulls (no NAT gateway charges)

This is the *artifact handoff point* between application development and infrastructure deployment. Before push, image is local-only. After push, it's AWS-deployable infrastructure.

### Workflow that landed today
```bash
# 1. Create repository (one-time per app)
aws ecr create-repository \
  --repository-name healthy-app \
  --region us-east-1 \
  --image-scanning-configuration scanOnPush=true

# 2. Save the URI
export ECR_URI=$(aws ecr describe-repositories \
  --repository-names healthy-app \
  --query 'repositories[0].repositoryUri' --output text)
# Format: <account>.dkr.ecr.<region>.amazonaws.com/<name>

# 3. Authenticate Docker (12hr token)
aws ecr get-login-password --region us-east-1 | \
  docker login --username AWS --password-stdin $ECR_URI

# 4. Tag local image with ECR URI
docker tag healthy-app-web:latest $ECR_URI:1.0
docker tag healthy-app-web:latest $ECR_URI:latest

# 5. Push
docker push $ECR_URI:1.0
docker push $ECR_URI:latest

# 6. Verify
aws ecr list-images --repository-name healthy-app
```

### Round-trip proof
Deleted local copies, pulled fresh from ECR. Same digest, came from AWS storage this time. Proves any AWS service with permission can pull this exact artifact.

### `docker rmi` failure pattern (worth remembering)
"unable to remove repository reference (must force) - container X is using its referenced image" = a container still references this image. Even stopped containers count. Fix: `docker compose down` first, then `docker rmi`. Don't use `-f` in scripts — it leaves orphaned `<missing>` references.

### Image scan results
After push, ~30-60s for scan to complete:
```bash
aws ecr describe-image-scan-findings \
  --repository-name healthy-app \
  --image-id imageTag=1.0 \
  --query 'imageScanFindings.findingSeverityCounts'
```
MEDIUM/LOW findings come from python:3.11-slim base. Production discipline: alert on CRITICAL/HIGH, monthly base image refresh cadence.

---

## Multi-stage Dockerfile insight (from today's confusion)

`apt install` cleanup must happen in the *same RUN*, not a separate one. Layers are immutable — a separate RUN that deletes adds a tombstone but the bytes stay in the previous layer.

```dockerfile
# RIGHT — single layer, no metadata in final image
RUN apt-get update && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

# WRONG — metadata layer + tombstone layer, both ship
RUN apt-get update && apt-get install -y curl
RUN rm -rf /var/lib/apt/lists/*
```

Same pattern for pip (`--no-cache-dir`), npm (`--production`), etc. Build tools cache aggressively; cache is dead weight at runtime.

### Curl in runtime stage, not builder
Multi-stage = "stuff you only need at build time" vs "stuff you need when running."
- Builder: pip, build wheels, gcc → discarded
- Runtime: Python interpreter, your code, **curl for healthcheck** ← needed at runtime by HEALTHCHECK command

If a tool is *used inside the running container at runtime*, it goes in runtime. Multi-stage doesn't strip things; whatever's in the runtime stage filesystem is what ships.

---

## File-by-file mental model (resolves the "syntax jumble")

When confused about what a file does, ask: **who reads this, when, and what do they produce?**

| File | Read by | When | Produces |
|------|---------|------|----------|
| `app.py` | Python interpreter | At runtime | API responses |
| `requirements.txt` | pip | At build time | Installed packages |
| `Dockerfile` | docker build | At build time (one-time) | An image |
| `.dockerignore` | docker build | At build time | Filtered build context |
| `docker-compose.yml` | docker compose | At deploy time | Running services |

**Only one file contains application logic: app.py.** Everything else is plumbing.

Configuration is layered, not duplicated:
- `app.py` reads `os.environ['DB_PASSWORD']`
- `docker-compose.yml` sets `DB_PASSWORD: secretpass` (passed in via environment)
- Production puts the same value in Secrets Manager

Each layer doesn't redefine — it passes the value down. Same value, different transports.

---

## Compose milestone vocabulary (deciphered today's confusion)

```
✔ Image healthy-app-web       Built     1.7s
✔ Network healthy-app_default Created   0.0s
✔ Volume healthy-app_dbdata   Created   0.0s
✔ Container healthy-app-db-1  Healthy   5.6s
✔ Container healthy-app-web-1 Started   5.7s
```

Different verbs because resource types have different lifecycles:
- **Image** — built or pulled
- **Network** — exists or doesn't (Created)
- **Volume** — exists or doesn't (Created)
- **Container** — created → started → running → healthy → unhealthy → exited

Why db shows "Healthy" but web shows "Started":
- db has a healthcheck **and** something downstream (`web`) waits for it via `condition: service_healthy`. Compose waited for the healthcheck to pass before declaring success.
- web has a healthcheck but nothing downstream waits for it. Compose just started it and moved on.

Compose is reporting **milestones, not states**. "Healthy" is a transition (starting → healthy), not a current state. The current state is in `docker ps`.

---

## ECS Fargate deployment (in progress — pick up tomorrow)

Got through the conceptual setup but didn't finish. State at end of session:

### What was completed
- Confirmed VPC ID and subnets from prod-vpc still exist
- Mental model of ECS vocabulary loaded

### ECS vocabulary (5 terms in dependency order)
1. **Cluster** — logical grouping (organizational boundary, one per env)
2. **Task definition** — spec for "how to run one container" (image URI, CPU/mem, ports, env vars, IAM role, healthcheck). Template, not running.
3. **Task** — one running instance of a task definition. Ephemeral.
4. **Service** — controller that maintains N healthy tasks. Replaces failed tasks, handles rolling deployments. **Where reliability lives.**
5. **ALB target group** — bridge between ALB and ECS service. Service registers task IPs into target group. ALB has its OWN healthcheck independent of container's HEALTHCHECK.

Chain: cluster contains service contains tasks created from task definition. Traffic: ALB → target group → tasks.

### What's left (tomorrow)
1. Create ECS cluster
2. Create IAM execution role (for ECR pulls + CloudWatch logs)
3. Register task definition (JSON spec referencing `$ECR_URI:1.0`)
4. Create target group + ALB + listener (port 80 → target group)
5. Create ECS service (connects task definition + ALB target group)
6. Watch task come up, hit ALB DNS, see Flask respond
7. Tear everything down (cost: ~$0.05/hr if left running)

### Conceptual shift to internalize
Fargate = "ECS without the EC2." With ECS-on-EC2 you'd manage a fleet of EC2 instances each running Docker. With Fargate, AWS provisions ephemeral microVMs per task and bills per-second. No instances to patch, no AMIs, no SSH, no ASG for hosts. Pure container-as-a-service.

### Resources to have ready tomorrow
- `$ECR_URI` from today's session: 042729137214.dkr.ecr.us-east-1.amazonaws.com/healthy-app
- prod-vpc still standing with public + private subnets
- Image `$ECR_URI:1.0` already in ECR

---

## Open conceptual questions answered today
- "Does docker-compose act on the web healthcheck?" → No. Compose only acts on healthchecks that have a `condition: service_healthy` consumer. Web's healthcheck published a signal nobody was listening to.
- "Why is the Compose healthcheck most important?" → It isn't. It's the most *visible* but the most *replaceable*. The Python route is the source of truth.
- "Why do we need to define HEALTHCHECK in the Dockerfile when Flask already has the route?" → Because Docker doesn't speak HTTP into your app — it runs shell commands periodically. Routes are Flask's domain; commands are Docker's. The HEALTHCHECK tells Docker how to invoke the route.
- "Does multi-stage strip dependencies?" → No. Multi-stage means each stage is its own complete image, and only the *last stage* ships. Things in earlier stages don't get copied unless you explicitly `COPY --from=`.
- "Layer cache scope?" → Daemon-wide, hashes content. If `app.py` shows CACHED when you expected a rebuild, the file genuinely didn't change on disk (editor wasn't saved, etc.).

---

## Commands reference

### ECR
```bash
aws ecr create-repository --repository-name NAME [--image-scanning-configuration scanOnPush=true]
aws ecr describe-repositories --repository-names NAME --query 'repositories[0].repositoryUri'
aws ecr get-login-password --region REGION | docker login --username AWS --password-stdin URI
aws ecr list-images --repository-name NAME
aws ecr describe-image-scan-findings --repository-name NAME --image-id imageTag=TAG
```

### Healthcheck observation
```bash
docker ps                                  # shows (healthy)/(unhealthy) status
docker inspect --format='{{.State.Health.Status}}' CONTAINER
docker inspect --format='{{json .State.Health}}' CONTAINER | jq
```

### Compose with watching
```bash
docker compose up           # foreground, see logs in real time (no -d)
docker compose up -d        # detached, normal mode
docker compose down         # stop + remove containers + network (keep volumes)
docker compose down -v      # also remove volumes
```

---

## Project state at end of day
- `~/devops-learning/week4/day23/healthy-app/` — complete healthcheck-enabled Flask + Postgres app
- ECR repo `healthy-app` exists in us-east-1 with `:1.0` and `:latest` tags
- Branch `week4/day23` ready to push
- VPC + subnets from Week 3 still standing
- ECS deployment NOT YET CREATED (no clusters, no task definitions, no ALBs)

Nothing is incurring AWS charges right now beyond ECR storage (under free tier).
