# Day 23 (continued) — ECS Fargate Deployment

**Date:** Tuesday, May 5, 2026
**Hours covered:** 6–8 (continuation of Day 23 — picked up after Day 22-23 healthcheck/ECR work, finished with successful ECS deployment + teardown)
**Branch:** `week4/day23-fargate`

This file extends the original `NOTES.md` (healthchecks + ECR). That file covers the application + image work; this one covers everything from "image is in ECR" to "image is running on AWS infrastructure behind a public URL."

---

## What was actually built

A complete containerized AWS deployment, end to end:

- **Cluster** (logical grouping)
- **Execution role** (IAM role Fargate uses to pull from ECR + write logs to CloudWatch)
- **CloudWatch log group** with 7-day retention
- **Two security groups** — one for ALB (port 80 from internet), one for tasks (port 5000 from ALB SG only)
- **Task definition** (revision 1 originally, revision 2 after fix)
- **Target group** with deep `/health` healthcheck
- **Internet-facing ALB** with HTTP listener forwarding to target group
- **Service** maintaining 2 healthy tasks across 2 AZs

End state: hitting the ALB DNS returned `Hello from container ip-10-0-X-X.ec2.internal`, alternating between two tasks across `us-east-1a` and `us-east-1b`. Round-robin load balancing across multiple AZs working as intended.

---

## ECS vocabulary, locked in

Five terms, in dependency order:

1. **Cluster** — logical grouping of tasks/services. Free, near-instant to create.
2. **Task definition** — the *spec* for "how to run one container." Versioned via revisions (`healthy-app:1`, `healthy-app:2`). Template, not running.
3. **Task** — one running instance of a task definition. Ephemeral; replaced if it dies.
4. **Service** — controller that maintains N healthy tasks. Replaces failures, handles rolling deployments. **Where reliability lives.**
5. **Target group** — bridge between ALB and ECS service. Service registers task IPs into target group on port 5000. ALB has its own healthcheck independent of container's.

Chain: `cluster → service → tasks (from task definition)`. Traffic: `internet → ALB → target group → tasks`.

---

## Three healthchecks at three layers (now confirmed in production)

The layered healthcheck model from yesterday played out exactly as predicted:

1. **Container healthcheck** (Dockerfile `HEALTHCHECK` + task definition `healthCheck`) — runs *inside* container. Drives task replacement decisions.
2. **Target group healthcheck** (ALB) — runs from ALB *over the network*. Drives traffic-routing decisions.
3. **Application logic** (`/health` route in `app.py`) — the actual code. Both consumers above hit this same endpoint.

Same code, two consumers, different decisions. The signal is published once; multiple systems independently subscribe and act.

In production this manifested as: deployed without the database the app expects → `/health` correctly returned 503 → both consumers (container check + ALB check) saw failures → grace period (`healthCheckGracePeriodSeconds: 90`) kept tasks alive long enough for traffic to flow despite the unhealthy state. Once grace expired, system started thrashing (task replaced → grace period restarts → new task fails → loop). Real production "outage shape" — partially functional but never settling.

---

## Three tier vs two tier — why ALB lives in public, tasks in private

ALB in public subnets (must — internet-facing requires this).
Tasks in private subnets (defense in depth — tasks have private IPs only, never directly addressable from the internet).
Traffic flow: `Internet → ALB → (private network) → tasks`.

Tasks reach ECR/CloudWatch through the NAT gateway in the public subnet. Standard 3-tier pattern.

---

## Production gotchas hit today (the actually valuable lessons)

### 1. Stale routes go to /dev/null silently

**Symptom:** `ResourceInitializationError: unable to pull secrets or registry auth ... dial tcp i/o timeout`

**Diagnosis chain:**
- `aws ecs describe-services ... events` showed the error
- `aws ec2 describe-route-tables` showed the private route table had a `0.0.0.0/0` route in state `blackhole`
- The route still pointed at a NAT gateway that no longer existed (deleted with prior Terraform destroys)

**Fix:**
```bash
# Allocate EIP, create new NAT, replace stale route
EIP_ALLOC=$(aws ec2 allocate-address --domain vpc --query 'AllocationId' --output text)
NAT_GW=$(aws ec2 create-nat-gateway --subnet-id $PUBLIC_SUBNET_1 \
  --allocation-id $EIP_ALLOC --query 'NatGateway.NatGatewayId' --output text)
aws ec2 wait nat-gateway-available --nat-gateway-ids $NAT_GW

# create-route would FAIL here with RouteAlreadyExists — must use replace-route
aws ec2 replace-route --route-table-id $PRIVATE_RT \
  --destination-cidr-block 0.0.0.0/0 --nat-gateway-id $NAT_GW
```

**Lesson:** AWS routes can point at deleted resources. State is `blackhole`, packets disappear, no error returned. Use `replace-route` not `create-route` when working with existing route tables. In real production, `terraform destroy` and similar tools handle this; manual cleanup is fragile.

### 2. Architecture mismatch — the Mac M-series ECS gotcha

**Symptom (from CloudWatch logs):** `exec /usr/local/bin/python: exec format error`

**Diagnosis:** Image was built on M2 Mac VM (linux/arm64). Default Fargate compute is x86_64. x86 hardware cannot execute ARM machine code — `exec format error` is the kernel's translation of "wrong instruction set."

**Fix (cross-compilation requires QEMU):**
```bash
# Install QEMU emulators via binfmt
docker run --privileged --rm tonistiigi/binfmt --install all

# Build for x86 explicitly, push directly to ECR
docker buildx build --platform linux/amd64 -t $ECR_URI:1.1 --push .
```

Then register a new task definition revision pointing at `:1.1`, and update the service:
```bash
sed "s|:1.0|:1.1|" task-definition.json > task-definition-v2.json
aws ecs register-task-definition --cli-input-json file://task-definition-v2.json  # → revision 2
aws ecs update-service --cluster ... --task-definition healthy-app:2 --force-new-deployment
```

**Lesson:** This is THE most common ECS gotcha for Mac developers. Symptom is cryptic — `exec format error` doesn't say "wrong arch" anywhere. Production CI fix is multi-arch builds: `docker buildx build --platform linux/amd64,linux/arm64 ...`. ECR stores both as one logical tag, ECS picks the right one for its host. Day 24 will set this up properly in GitHub Actions.

**Interview gold:** "Tell me about a time you debugged a deployment failure" → walk through the two-layer diagnostic (events → logs), the cryptic symptom, the architecture realization, and the multi-arch CI fix.

### 3. Fargate cold starts need long grace periods

Default health checks evaluate too aggressively for Fargate's startup time (image pull + microVM allocation + container start can be 60-90s). Settings that worked:

- Task definition `healthCheck.startPeriod: 60` — Docker grace before failures count
- Service `healthCheckGracePeriodSeconds: 90` — ECS grace for ALB target health
- Target group: `healthy-threshold-count: 2`, `interval: 15` — needs 2 consecutive passes (~30s) to be marked healthy

If `startPeriod` is too short, tasks get killed mid-startup and the service enters a relaunch loop. Symptom: tasks oscillate between "running" and "stopped" states for several minutes before the service circuit-breaker pauses retries.

### 4. AWS resource deletion is eventually consistent

`delete-load-balancer` returns success when deletion is *queued*, not complete. The underlying ENIs that reference security groups can take 1-3 minutes to release. So:

```bash
aws ec2 delete-security-group --group-id $TASK_SG_ID
# DependencyViolation: resource has a dependent object
```

The "dependent object" is an ENI from the ALB or Fargate task that hasn't been fully torn down yet. **Wait, then retry** — or better, write teardown scripts with explicit `sleep` commands or `aws ... wait` calls between dependent operations. Terraform handles this via dependency graphs; manual CLI teardown is fragile.

---

## The teardown order that actually works

Reverse order of creation, with waits where async deletion matters:

```bash
# 1. Service: scale to 0, then force delete
aws ecs update-service --cluster $CLUSTER_NAME --service healthy-app-service --desired-count 0
sleep 30
aws ecs delete-service --cluster $CLUSTER_NAME --service healthy-app-service --force

# 2. ALB listener + ALB itself
LISTENER_ARN=$(aws elbv2 describe-listeners --load-balancer-arn $ALB_ARN --query 'Listeners[0].ListenerArn' --output text)
aws elbv2 delete-listener --listener-arn $LISTENER_ARN
aws elbv2 delete-load-balancer --load-balancer-arn $ALB_ARN
sleep 30  # async — target group delete fails if ALB still references it

# 3. Target group
aws elbv2 delete-target-group --target-group-arn $TG_ARN

# 4. Cluster
aws ecs delete-cluster --cluster $CLUSTER_NAME

# 5. Security groups (may need 60s wait for ENI cleanup)
aws ec2 delete-security-group --group-id $TASK_SG_ID
aws ec2 delete-security-group --group-id $ALB_SG_ID

# 6. NAT gateway + EIP — most expensive, kill ASAP
aws ec2 delete-nat-gateway --nat-gateway-id $NAT_GW
aws ec2 wait nat-gateway-deleted --nat-gateway-ids $NAT_GW
aws ec2 release-address --allocation-id $EIP_ALLOC

# 7. Log group
aws logs delete-log-group --log-group-name /ecs/healthy-app

# 8. Task definitions can't be deleted, only deregistered
aws ecs deregister-task-definition --task-definition healthy-app:1
aws ecs deregister-task-definition --task-definition healthy-app:2
```

**Verification:** all describes empty:
```bash
aws ecs list-clusters
aws elbv2 describe-load-balancers --query 'LoadBalancers[*].LoadBalancerName' --output text
aws ec2 describe-nat-gateways --filter "Name=state,Values=available,pending" --query 'NatGateways[*].NatGatewayId' --output text
aws ec2 describe-addresses --query 'Addresses[*].[AllocationId,AssociationId,InstanceId]' --output table
```

What stays (zero ongoing cost):
- IAM execution role `ecsTaskExecutionRole` — account-wide, reusable
- ECR repo `healthy-app` — under 500MB free tier
- Task definition revisions (deregistered, not deleted — AWS retains for audit)

---

## Cost check

Approximate hourly rates while running:
- ALB: ~$0.022/hr
- NAT Gateway: ~$0.045/hr (the most expensive piece)
- 2× Fargate tasks (0.25 vCPU, 0.5GB): ~$0.024/hr
- ECR: free tier
- CloudWatch Logs: pennies

Total session cost (~3 hours running): ~$0.30. NAT gateway is the surprising one — if you forget it overnight that's $1/day until torn down. **Always tear down NAT gateways immediately when done.**

---

## File artifacts (committable)

- `aws/task-definition.json` — Fargate task spec template with placeholders
- `aws/service-definition.json` — Service spec template with placeholders

Both use `__VARIABLE__` placeholders that are substituted via `sed` before `aws ecs register-task-definition`. The actual deployed JSON contains the real ARNs/IDs.

---

## ECS task definition fields worth understanding

```json
{
  "family": "healthy-app",                    // logical name; revisions are versioned within this
  "networkMode": "awsvpc",                    // required for Fargate; each task gets own ENI
  "requiresCompatibilities": ["FARGATE"],     // platform constraint
  "cpu": "256",                               // 0.25 vCPU; smallest valid Fargate config
  "memory": "512",                            // 512 MB; CPU/memory must be from allowed pairs
  "executionRoleArn": "...",                  // role for Fargate infrastructure (ECR + logs)
  "containerDefinitions": [{
    "name": "web",
    "image": "<ECR_URI>:1.0",
    "essential": true,                        // task fails if this container exits
    "portMappings": [{...}],
    "environment": [{...}],
    "healthCheck": {...},                     // ECS-level container check
    "logConfiguration": {                     // streams stdout/stderr to CloudWatch
      "logDriver": "awslogs",
      "options": {...}
    }
  }]
}
```

**Two roles, not one:**
- **Execution role** (used today) — Fargate infrastructure layer. Pulls from ECR, writes logs.
- **Task role** (NOT used today) — Application layer. Used by app code calling AWS APIs (boto3 → S3, DynamoDB, etc.).

If your app needs to call AWS services, attach a task role. If it just runs containers, execution role alone is enough.

---

## Mental model that ties Day 22 + Day 23 together

```
app.py                          ← Application layer (Python code)
  ↓ packaged into
Docker image                    ← Build artifact (Dockerfile output)
  ↓ pushed to
ECR                             ← Storage layer (versioned, scanned)
  ↓ referenced by
Task definition                 ← Spec layer (how to run the image)
  ↓ instantiated by
Service                         ← Reliability layer (maintains N healthy)
  ↓ runs on
Fargate (microVM)              ← Compute layer (managed by AWS)
  ↓ traffic via
Target group                    ← Routing layer (registers task IPs)
  ↓ accessed via
ALB                             ← Public entry layer (DNS + load balancing)
```

Each layer is replaceable. ECR could be Docker Hub. Fargate could be ECS-on-EC2 or EKS. ALB could be NLB or API Gateway. The key insight is the *boundary contracts*: image follows OCI spec, task definition is JSON, service uses target group, target group accepts IPs. Swap any layer for an equivalent and the rest still works.

This is what "cloud-native architecture" actually means — not "uses AWS" but "every layer has clean interfaces, every component is replaceable, state lives in managed services not in compute."

---

## Open questions answered today
- "Why does my Fargate task time out trying to reach ECR?" → Routing. Either no NAT gateway, no route to it, or stale route to a deleted NAT.
- "Why does `exec format error` mean?" → Architecture mismatch. ARM image on x86 host (or vice versa).
- "Why is the target group unhealthy but my app still answers curl?" → `healthCheckGracePeriodSeconds` keeps targets in rotation despite failed checks during startup window. Once grace expires, ALB drains them.
- "Why do I need both a container healthcheck AND a target group healthcheck?" → They drive different decisions. Container check → restart task. Target group check → drain traffic. Both consume the same `/health` endpoint.
- "Why can't I delete the security group right after the ALB?" → Async ENI cleanup. ALB delete is queued; underlying network interfaces hold SG references for 1-3 minutes. Wait then retry.
- "Why use `replace-route` not `create-route` when fixing the NAT?" → If a route to that destination already exists (even if blackholed), `create-route` fails with `RouteAlreadyExists`. `replace-route` updates the target.

---

## Project state at end of session

**AWS resources clean:**
- All ECS resources torn down
- ALB, target group, NAT gateway, EIP all deleted
- VPC + subnets remain (from Week 3 Terraform — keep these)
- IAM execution role retained (free, reusable)
- ECR repo retained with image tags 1.0 (ARM, broken on Fargate) and 1.1 (x86, working)

**Local repo:**
- `~/devops-learning/week4/day23/healthy-app/aws/task-definition.json`
- `~/devops-learning/week4/day23/healthy-app/aws/service-definition.json`
- This NOTES file

**Lessons that transfer to Day 24 (CI/CD):**
- Multi-arch builds belong in CI from the start (one less debugging cycle)
- `--force-new-deployment` is how you trigger a rolling deploy on a service
- Task definition revisions are immutable — every deploy is a new revision
