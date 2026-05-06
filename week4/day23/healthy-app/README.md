# Flask + Postgres Multi-Container App

A two-service application demonstrating Docker Compose, container networking, and persistent state management. Flask serves a small HTTP API that records visits to a PostgreSQL database, with both services orchestrated as containers on a private Docker network.

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Host (Ubuntu VM)                                        │
│                                                          │
│  ┌───────────────────────────────────────────────────┐   │
│  │  compose-app_default (bridge network)             │   │
│  │                                                   │   │
│  │   ┌──────────────┐         ┌──────────────────┐   │   │
│  │   │  web         │         │  db              │   │   │
│  │   │  Flask 3.0   │ ──────▶ │  Postgres 16     │   │   │
│  │   │  port 5000   │  5432   │  alpine          │   │   │
│  │   │  appuser     │         │  port 5432       │   │   │
│  │   └──────┬───────┘         └────────┬─────────┘   │   │
│  │          │                          │             │   │
│  └──────────┼──────────────────────────┼─────────────┘   │
│             │                          │                 │
│        host:5000 ─┐               named volume           │
│                   │              "dbdata"                │
└───────────────────┼──────────────────────────────────────┘
                    │
              curl localhost:5000
```

Two services on a private bridge network. Compose's embedded DNS lets the Flask container reach Postgres at hostname `db` — no IP configuration needed. Only the web service publishes to the host (port 5000); the database is reachable only from within the network. Database state lives in a named Docker volume that persists across container recreations.

## Prerequisites

- Docker Engine 20.10+ (tested on 29.4.2)
- Docker Compose V2 (built into modern Docker installations)
- Available host port: 5000

## Deploy

```bash
docker compose up -d
```

First run pulls the Postgres image from Docker Hub and builds the Flask image from the Dockerfile (~30 seconds). Subsequent runs reuse the cached layers and start in a few seconds. The `db` service waits for its healthcheck (`pg_isready`) to pass before `web` is allowed to start, ensuring Flask doesn't fail to connect on boot.

## Use

```bash
# Sanity check — Flask responding
curl http://localhost:5000/

# One-time: create the visits table
curl http://localhost:5000/init

# Record visits (each call inserts a row, returns id + timestamp)
curl http://localhost:5000/visit
curl http://localhost:5000/visit

# List the 10 most recent visits
curl http://localhost:5000/visits
```

## Verify state persistence

The whole point of named volumes is that container data survives container destruction. To prove it:

```bash
# Record some visits
curl http://localhost:5000/init
curl http://localhost:5000/visit
curl http://localhost:5000/visit

# Tear everything down (containers gone, volume kept)
docker compose down

# Bring it back — same data is still there
docker compose up -d
curl http://localhost:5000/visits
```

The Postgres container that wrote those rows is destroyed and recreated. The data persists because it lives in the `dbdata` named volume, not on the container's writable layer.

To fully reset (nuke the volume too):

```bash
docker compose down -v
```

## Destroy

```bash
docker compose down -v          # remove containers, network, AND volume
docker rmi compose-app-web      # remove the locally built Flask image
```

## Design decisions

**Service-name DNS over hardcoded IPs.** The Flask container reaches Postgres via the hostname `db`. Compose creates a private network where every service is resolvable by name through Docker's embedded DNS. This works regardless of the container's actual IP, which changes on every restart.

**Named volume for database storage.** The Postgres data directory (`/var/lib/postgresql/data`) is backed by a Docker-managed volume rather than a bind mount. Decouples database state from any specific host filesystem path and survives `docker compose down` (without `-v`).

**Healthcheck-gated startup.** `depends_on: condition: service_healthy` ensures Flask doesn't start until Postgres is actually ready to accept connections — not just until its container has launched. The default `depends_on` behavior only waits for the container to start, which usually loses the race.

**Multi-stage Dockerfile for the web service.** Build dependencies (pip, build wheels) live in a `builder` stage that gets discarded. Only the installed Python packages are copied into the runtime stage. Smaller image, smaller attack surface. See the Dockerfile for the pattern.

**Non-root user inside the web container.** The Flask process runs as `appuser` (uid 1000), not root. Defense-in-depth: if the application is compromised, the attacker can't escalate within the container.

**Postgres on Alpine.** `postgres:16-alpine` is roughly 80MB vs ~400MB for the default Debian-based image. For a development database the alpine variant is fine; some production deployments stick with the Debian variant for glibc compatibility with extensions.

## Cost estimate

Zero. Runs entirely on local Docker. No AWS charges incurred.

## Known limitations and production improvements

This project is a local development pattern, not a production deployment. The following would change for a real environment:

- **Secrets are inline.** `POSTGRES_PASSWORD` is hardcoded in `docker-compose.yml`. For local dev the next step is a gitignored `.env` file referenced via `${DB_PASSWORD}` substitution. For production, secrets come from AWS Secrets Manager or SSM Parameter Store, injected into the container at runtime by the orchestrator (ECS task definition, Kubernetes secret).
- **Single-instance database.** Production would not run Postgres in a container at all — managed RDS provides automated backups, multi-AZ failover, and point-in-time recovery for free relative to the operational burden of self-managing.
- **No replicas, no load balancer.** The Flask service runs as a single container. Production would put it behind an ALB with multiple instances behind an Auto Scaling Group, or run it on ECS Fargate with `desired_count > 1`.
- **No TLS.** Plain HTTP on port 5000. Production terminates TLS at the load balancer with an ACM certificate.
- **No structured logging or metrics.** Logs go to stdout (which Docker captures), but there's no log shipping or metric collection. Production would push CloudWatch Logs and emit application metrics.
- **No image scanning or supply-chain controls.** Production CI would scan the built image for CVEs (e.g., `docker scout`, Trivy, ECR scan-on-push) before promoting it.
- **No resource limits.** Either container can consume all host CPU and memory. Compose supports `deploy.resources.limits` to bound this; ECS/Kubernetes enforce it natively via task definition / pod spec.

## File layout

```
compose-app/
├── Dockerfile              # multi-stage build for the Flask image
├── .dockerignore           # excludes junk from build context
├── app.py                  # Flask application
├── requirements.txt        # Python dependencies
├── docker-compose.yml      # service definitions, network, volume
└── README.md               # this file
```

