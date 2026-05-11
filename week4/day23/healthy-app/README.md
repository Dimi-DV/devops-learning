# Containerized Flask App on ECS Fargate — CI/CD Pipeline

A containerized Python Flask application deployed to AWS ECS Fargate, with the full CI/CD pipeline that builds, tests, and pushes images to ECR using OIDC-authenticated GitHub Actions. The project began as a local Docker Compose two-service app (Flask + Postgres) and evolved to a cloud-deployed service running on Fargate behind a multi-AZ Application Load Balancer.

This is the canonical "ship a container" journey end-to-end: write the Dockerfile, run it locally with Compose, push to a registry, deploy to managed container orchestration with health checks and logging, and automate the whole build-and-push loop on every commit.

---

## Architecture

### Local development (Docker Compose)

```
┌────────────────────────────────────────────────────────┐
│  Host (Ubuntu VM)                                      │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Docker bridge network                           │  │
│  │                                                  │  │
│  │   ┌──────────────┐         ┌──────────────────┐  │  │
│  │   │  web         │ ──────▶ │  db              │  │  │
│  │   │  Flask 3.0   │   :5432 │  Postgres 16     │  │  │
│  │   │  port 5000   │         │  alpine          │  │  │
│  │   └──────┬───────┘         └────────┬─────────┘  │  │
│  │          │                          │            │  │
│  └──────────┼──────────────────────────┼────────────┘  │
│             │                          │               │
│        host:5000 ─┐               named volume         │
│                   │              "dbdata"              │
└───────────────────┼────────────────────────────────────┘
                    │
              curl localhost:5000
```

### Cloud deployment (ECS Fargate)

```
                          Internet
                              │
                              ▼
                ┌──────────────────────────┐
                │  Application Load        │
                │  Balancer (multi-AZ)     │
                └─────────────┬────────────┘
                              │ HTTP :5000
                ┌─────────────┴─────────────┐
                ▼                           ▼
         ┌────────────┐             ┌────────────┐
         │ Fargate    │             │ Fargate    │
         │ Task       │             │ Task       │
         │ healthy-app│             │ healthy-app│
         │ us-east-1a │             │ us-east-1b │
         │ 256 / 512  │             │ 256 / 512  │
         └─────┬──────┘             └─────┬──────┘
               │                          │
               └──────────┬───────────────┘
                          ▼
                   CloudWatch Logs
                   /ecs/healthy-app

Image lifecycle:
  Code commit → GitHub Actions → ECR → ECS task definition revision → Service update
```

---

## Repository contents

```
healthy-app/
├── app.py                       # Flask application
├── requirements.txt
├── tests/
│   └── test_app.py              # pytest suite
├── Dockerfile                   # multi-stage build, non-root user, healthcheck
├── .dockerignore
├── .flake8                      # lint config used by CI
├── docker-compose.yml           # local two-service stack (web + Postgres)
└── aws/
    ├── task-definition.json     # ECS task definition (Fargate, awsvpc, 256/512)
    └── service-definition.json  # ECS service configuration
```

The CI/CD pipeline lives at the repository root under `.github/workflows/`: `ci.yml` orchestrates lint → test matrix → build, calling `docker-build-push.yml` as a reusable workflow for the ECR push.

---

## Prerequisites

- Docker Engine 20.10+ and Docker Compose V2 (for local development)
- AWS account with an ECR repository named `healthy-app` and an ECS cluster ready to register the included task definition against
- IAM role `github-actions-ecr-push` with an OIDC trust policy permitting this repository to assume it, plus ECR push permissions
- No repository secrets are required — credentials are obtained via OIDC at workflow runtime

---

## Local development

```bash
docker compose up -d

# Sanity check
curl http://localhost:5000/

# Initialize the visits table (one-time)
curl http://localhost:5000/init

# Record visits and read them back
curl http://localhost:5000/visit
curl http://localhost:5000/visits

# Health check (exercised by the container HEALTHCHECK and by ECS)
curl http://localhost:5000/health
```

The Compose stack uses healthcheck-gated startup (`depends_on: condition: service_healthy`) so the Flask container does not try to connect before Postgres is actually ready. Database state lives in a named volume; `docker compose down` keeps the data, `docker compose down -v` wipes it.

---

## Deploy to ECS Fargate

The current ECS deployment runs the web container only — the Postgres database is local-only for now. A full production deployment would replace the Compose-managed Postgres with managed RDS and inject DB credentials via SSM Parameter Store or Secrets Manager. This section covers the path that is actually wired up: pushing the web container to ECR and getting Fargate to run it.

```bash
# Register the task definition (creates a new revision pointing at the latest image)
aws ecs register-task-definition --cli-input-json file://aws/task-definition.json

# Update the service to use the new revision
aws ecs update-service \
  --cluster <your-cluster> \
  --service healthy-app \
  --task-definition healthy-app \
  --force-new-deployment

# Watch the deployment roll out
aws ecs describe-services --cluster <your-cluster> --services healthy-app \
  --query "services[0].deployments"
```

The current pipeline stops at "image is in ECR" — promotion to ECS is a manual step. Production CD would add `amazon-ecs-render-task-definition` and `amazon-ecs-deploy-task-definition` to automate the deploy after each successful ECR push.

---

## CI/CD pipeline

Three workflows compose the full pipeline.

### `ci.yml` — lint, test, build, push

Triggers:
- Push to `main` or `week*/**` branches that touches `healthy-app/` or the workflow files
- Pull request to `main` matching the same path filters

Path-based triggers mean unrelated commits don't run the pipeline.

Jobs run in sequence with explicit `needs`:

1. **Lint** — flake8 against `app.py` and `tests/`
2. **Test** — pytest across Python 3.10, 3.11, and 3.12 in a matrix. Each version runs in parallel; the job only succeeds if all three pass.
3. **Build and push** — only runs on push to `main`. Calls the reusable `docker-build-push.yml` workflow.

### `docker-build-push.yml` — reusable workflow

Authenticates to AWS via OIDC, logs into ECR, builds with Buildx, and pushes the image tagged with both the commit SHA and `latest`. Inputs (`image-name`, `build-context`, `aws-region`, `role-arn`) make the workflow consumable from any other repo workflow that needs the same Docker → ECR pattern.

### Auth: OIDC over stored access keys

The pipeline does not use AWS access keys stored as GitHub secrets. Instead:

1. GitHub Actions exchanges its own OIDC token with AWS STS
2. AWS STS issues short-lived credentials for the `github-actions-ecr-push` role
3. The role's trust policy restricts assumption: only OIDC tokens from this repository are accepted

This is the modern AWS-recommended pattern. No long-lived credentials sit in the repo. Compromised secrets aren't a thing because there are no secrets — the trust policy controls assumption, not the secrets store.

---

## Cost estimate

| Component | Cost (running 24/7) |
|---|---|
| ECR storage (1-2 GB of images) | <$0.20/month |
| ECS Fargate tasks (2 × 256 CPU / 512 MB) | ~$15/month |
| ALB | ~$16/month + LCU charges |
| CloudWatch Logs (low volume) | <$1/month |
| GitHub Actions (public repo) | Free |

**Total at idle: ~$32-35/month.** For learning use, keep the ECS service at desired count 0 between sessions and scale to 2 only when actively demoing — costs drop to single-digit dollars per month with that pattern.

---

## Design decisions

### Multi-stage Dockerfile

The build stage installs Python dependencies into `/app/deps`. The runtime stage starts from a fresh `python:3.11-slim`, copies in only the installed packages, and discards the builder. The final image excludes pip caches, build wheels, and apt indexes. Result: smaller image, smaller attack surface, faster pulls during Fargate task startup.

### Non-root user inside the container

The Flask process runs as `appuser` (uid 1000), not root. If the application is compromised, the attacker cannot escalate within the container or escape to the host. The Dockerfile creates the user before switching to it and `chown -R appuser:appuser /app` ensures the process can read its own files.

### Container-level HEALTHCHECK

The Dockerfile declares `HEALTHCHECK CMD curl -fsS http://localhost:5000/health || exit 1`. This is independent of the ECS task health check and provides defense in depth — Docker can mark a container unhealthy locally even if external health checking is unconfigured. ECS reads this status and replaces unhealthy tasks.

### OIDC over stored access keys

Covered in the CI/CD section. The shift from "AWS access keys in GitHub Secrets" to OIDC role assumption is one of the most important security upgrades in modern CI/CD; mentioned explicitly because it's a recognizable interview signal.

### Image tagging with commit SHA

Every image is tagged with `${{ github.sha }}`. The `:latest` tag is also applied but should not be relied on for deployment — task definitions reference specific SHAs so that rollback means "deploy the previous revision" without ambiguity about what was actually running.

### Reusable workflow for the build-push step

Splitting the ECR push into `docker-build-push.yml` means any other pipeline in this repo that needs Docker → ECR can call it with inputs rather than reimplementing the steps. Future projects in this repo can use it directly.

### Path-based workflow triggers

The CI workflow only runs when `healthy-app/` files change. Commits that only touch Terraform projects or Week 1 notes don't burn CI minutes or clutter the actions history. Good hygiene to establish early and important at scale.

---

## Known limitations and production improvements

- **No automated ECS deployment.** The pipeline pushes images to ECR but does not update the ECS service automatically. Production CD would call `amazon-ecs-render-task-definition` and `amazon-ecs-deploy-task-definition` after each successful push.
- **Database isn't in the cloud deployment.** The Compose stack has Postgres; the ECS deployment doesn't. Production would provision an RDS Postgres instance in the VPC's private subnets, with the Flask container's DB env vars injected from Secrets Manager via the task definition.
- **No image scanning gate.** Production CI should scan the built image for CVEs (ECR scan-on-push, `docker scout`, or Trivy) before promoting it to production environments.
- **`:latest` tag is still pushed.** Useful for local pulls and debugging, but production-strict environments disable this to prevent accidental "deploy latest" outside of controlled paths.
- **No deployment circuit breaker.** ECS supports automatic rollback if a deployment doesn't reach steady state. Production should enable this on the service definition.
- **No structured logging.** The app logs to stdout (which Fargate ships to CloudWatch Logs), but it's unstructured text. Production would emit JSON logs with request IDs for correlation.
- **No replica count autoscaling.** The service runs a fixed `desired_count`. Production would attach `aws_appautoscaling_target` and `aws_appautoscaling_policy` to scale on CPU or request count.
- **No HTTPS at the ALB.** The current listener is HTTP:80. Production terminates TLS at the ALB with an ACM certificate.

---

## What this project demonstrates

- **Container fundamentals** — multi-stage Dockerfile, non-root user, container-level healthcheck, `.dockerignore`, layer-caching-aware instruction order
- **Local-to-cloud container journey** — Docker Compose for development, ECS task definitions and services for managed orchestration
- **ECS Fargate operational model** — task definitions, services, awsvpc networking mode, CloudWatch logging integration via the `awslogs` driver
- **CI/CD pipeline construction** — multi-stage workflows with `needs`, matrix testing across Python versions, path-based triggers, reusable workflows
- **AWS authentication via OIDC** — modern auth pattern with no long-lived credentials in CI
- **Image and deployment lifecycle** — SHA-based image tagging, ECS task definition revisions, the rationale behind tagging strategy
