# Day 26: Kubernetes Introduction

**Date:** May 8, 2026
**Week 4, Day 26 of 42-day battle plan**
**Status:** Complete — all Hour 1-6 objectives met after disk-resize detour

---

## Objectives (from battle plan)

- Understand K8s architecture and core objects
- Spin up local cluster (Kind)
- Deploy app via Deployment + Service
- Practice scaling, rolling updates, rollbacks
- Use ConfigMap and Secret for configuration injection

All achieved. Plus an unplanned but valuable lesson on disk-full as a sneaky K8s failure mode.

---

## Conceptual core

### The mental model

Kubernetes is **what ECS would be if AWS had open-sourced it and everyone agreed on it as the standard.** Same problem ECS solves (run containers, restart them, scale them, load-balance them, do rolling updates), but portable across clouds and on-prem. More complex than ECS, more powerful, the de facto standard.

### Architecture: control plane vs worker nodes

**Control plane** (the brain):
- **API server** — front door. Every kubectl command, every controller, every component talks to it. Only thing that writes to etcd.
- **etcd** — the database. Stores desired state.
- **Scheduler** — decides which worker node a new pod lands on.
- **Controller manager** — hosts all the reconciliation loops (Deployment controller, ReplicaSet controller, Endpoints controller, etc.). Each loop watches its resource type and reconciles desired state to actual state.

**Worker nodes** (the muscle):
- **kubelet** — agent that runs containers on the node, talks to the API server.
- **kube-proxy** — programs networking on the node so Service traffic reaches the right pods.
- **Container runtime** — Docker, containerd, etc. Actually runs containers.

### Core objects

- **Pod** — smallest scheduled unit. One or more containers sharing network/storage. You almost never create directly.
- **Deployment** — manages pods via a ReplicaSet. Declares desired replica count, pod template, update strategy.
- **ReplicaSet** — intermediate layer between Deployment and pods. Maintains the count. Two layers exist specifically to enable rolling updates and rollbacks.
- **Service** — stable DNS/IP that load-balances to a dynamic set of pods matching a label selector. ECS analogy: ALB + Target Group.
- **Namespace** — logical boundary. Default is `default`.
- **ConfigMap** — non-sensitive key-value config injected into pods.
- **Secret** — base64-encoded (NOT encrypted) key-value config for credentials.

### The reconciliation principle

K8s is a **state-reconciliation system, not a command system.** Every component just watches state and writes state back through the API server. Nobody "deploys a pod." The ReplicaSet controller observes a gap between desired and actual count, and writes a new Pod object to etcd. The scheduler observes an unscheduled pod and writes a node assignment. The kubelet observes an assigned pod and starts the container.

This is why you `apply` YAML files instead of running commands — same instinct as Terraform.

### Label triangulation (the #1 K8s gotcha)

Three labels must agree for traffic to flow:

```
Deployment.spec.selector.matchLabels    ← what the Deployment claims as its pods
        ↕  must match
Deployment.spec.template.metadata.labels  ← what gets stamped on each pod
        ↕  must match
Service.spec.selector                    ← what the Service routes to
```

Mismatch between Deployment selector and pod template labels → runaway (Deployment keeps creating pods it doesn't recognize).
Mismatch between Service selector and pod labels → Service has no endpoints, traffic goes nowhere.

### Pod replacement walkthrough

When you `kubectl delete pod X` where X is managed by a Deployment with replicas=2:

1. **API server** marks the pod deleted in etcd, tells kubelet to stop the container.
2. **ReplicaSet controller** (NOT Deployment controller — that one only handles ReplicaSet changes) notices count dropped to 1, creates a new Pod object in etcd.
3. **Scheduler** assigns the new pod a node.
4. **kubelet** on that node pulls the image and starts the container.
5. **Endpoints controller** sees the new pod matches the Service selector, adds its IP to the Endpoints object.

Total time: usually <5 seconds. Service stays up throughout.

### Why two layers (Deployment → ReplicaSet → Pods)?

Rolling updates and rollbacks. When you change the image:
- Deployment controller creates a NEW ReplicaSet with the new pod template
- New ReplicaSet scales up to N replicas
- Old ReplicaSet scales down to 0 (but stays around)
- For rollback: old ReplicaSet scales back up, new one scales down

Verified live: after `kubectl set image`, `kubectl get replicaset` showed two ReplicaSets — old one at 0 replicas, new one at 2.

---

## Operational reps completed

### Cluster lifecycle
- Installed kubectl + Kind for arm64 (M2 VM)
- `kind create cluster --name flask-lab` → single-node cluster (control plane node is a Docker container)
- Verified `kubectl get nodes` showed Ready
- `kubectl get pods --all-namespaces` showed kube-system: kube-apiserver, etcd, kube-scheduler, kube-controller-manager, coredns, kindnet, kube-proxy

### Deployment + Service
- Wrote `deployment.yaml` (2 replicas of nginx:alpine) and `service.yaml` (NodePort, port 80 → targetPort 80, nodePort 30080)
- `kubectl apply` for both
- Verified pods Running, Service created, Endpoints showing both pod IPs (10.244.0.5:80, 10.244.0.6:80)

### Reconciliation
- `kubectl delete pod <name>` while watching `kubectl get pods -w`
- Saw pod transition to Terminating, replacement Pending → ContainerCreating → Running within ~1 second
- Service kept routing throughout

### Scaling
- `kubectl scale --replicas=4` → 2 new pods spawned
- `kubectl scale --replicas=2` → 2 pods terminated
- Note: this is **imperative** and creates drift from the YAML file

### Rolling update
- `kubectl set image deployment/nginx-app nginx=nginx:1.25-alpine`
- `kubectl rollout status` showed 1 of 2 new replicas updated, then old replicas terminated
- `kubectl get replicaset` confirmed two ReplicaSets coexisted (old at 0, new at 2)

### Rollback
- `kubectl rollout undo deployment/nginx-app`
- Old ReplicaSet scaled back up, new one scaled to 0
- Warning about `kubectl.kubernetes.io/last-applied-configuration` — K8s warning that mixing imperative + declarative creates drift

### Drift detection
- `kubectl diff -f deployment.yaml` returns empty when file and cluster agree
- Created drift on purpose with `kubectl scale`, ran diff, saw the replicas line in red/green diff format
- Reconciled with `kubectl apply -f deployment.yaml`

### ConfigMap + Secret
- `kubectl create configmap nginx-config --from-literal=ENVIRONMENT=production --from-literal=LOG_LEVEL=info`
- `kubectl create secret generic nginx-secret --from-literal=DB_PASSWORD=...`
- Edited `deployment.yaml` to add `env` block referencing both via `configMapKeyRef` / `secretKeyRef`
- Apply triggered another rolling update (new pod template = new ReplicaSet)
- `kubectl exec -it <pod> -- env | grep -E "ENVIRONMENT|LOG_LEVEL|DB_PASSWORD"` showed all three values injected

---

## Key learnings

### Imperative vs declarative — the drift problem

K8s supports two paradigms:

- **Imperative** (`kubectl scale`, `kubectl set image`, `kubectl edit`) — fast, console-like, no source of truth
- **Declarative** (`kubectl apply -f file.yaml`) — source of truth is git, cluster reconciles to match

Mixing them creates **drift**: live state diverges from what's in your YAML files. Same pattern as clicking around in AWS console while having Terraform.

Production rule: **only declarative.** Imperative commands are emergency break-glass tools. Real changes go: edit YAML → commit → PR → CI/CD applies.

### K8s Secrets aren't actually secret

Secrets are **base64-encoded, not encrypted**. Anyone with `kubectl get secret` permissions can decode them in 2 seconds:

```bash
kubectl get secret nginx-secret -o jsonpath='{.data.DB_PASSWORD}' | base64 -d
```

Production approaches: encryption at rest for etcd (KMS), external secret managers (AWS Secrets Manager, Vault), IRSA on EKS, Sealed Secrets for git-stored secrets, tight RBAC on `get secret`.

Relevant for the capstone: agent credentials should use IAM roles via IRSA or AgentCore Identity, not K8s Secrets.

### Disk-full as a sneaky K8s failure mode

Kind cluster init failed with "control plane unhealthy after 4-minute timeout." The kubeadm output blamed kubelet/networking. The real cause: VM root filesystem at 100%. K8s couldn't write etcd, kubelet state, or container logs.

**Diagnostic order for confusing K8s failures:** `df -h` → `docker system df` → only then dig into K8s/kubelet logs.

This is the classic pattern: weird symptoms across multiple components → mundane root cause (disk, memory, network).

### LVM disk expansion (4 layers)

When growing storage on Linux:

```
Layer 0: Disk (vda)              ← grew via UTM in macOS
Layer 1: Partition (vda3)        ← grew via `growpart /dev/vda 3`
Layer 2: LVM Physical Volume     ← grew via `pvresize /dev/vda3`
Layer 3: LVM Logical Volume      ← grew via `lvextend -l +100%FREE`
Layer 4: Filesystem (ext4)       ← grew via `resize2fs` (online, while mounted)
```

Each layer must be told independently. ext4 supports online resize — no unmount, no reboot.

This same principle applies to AWS: EBS volume expansion + partition + filesystem. Cloud-init handles some of it on standard AMIs, but you'll see "I expanded EBS but the OS doesn't see it" tickets in cloud support roles.

---

## Mappings to ECS / AWS

| K8s | AWS / ECS equivalent |
|---|---|
| Container in Pod | Container in ECS Task |
| Pod | ECS Task |
| Pod template (in Deployment) | ECS Task Definition |
| Deployment + Service | ECS Service + ALB |
| Service type LoadBalancer | ALB / NLB |
| Service type ClusterIP | Internal-only routing (no AWS analog needed) |
| HorizontalPodAutoscaler | ASG with scaling policies |
| ConfigMap | SSM Parameter Store / env vars |
| Secret (with encryption) | AWS Secrets Manager |
| NetworkPolicy | Security Group |
| Namespace | Tag scope / loose account boundary |

---

## Files in this directory

- `deployment.yaml` — 2-replica nginx Deployment with env vars sourced from ConfigMap + Secret
- `service.yaml` — NodePort Service exposing port 30080 → pod port 80
- `NOTES.md` — this file

ConfigMap and Secret were created imperatively (`kubectl create configmap ... --from-literal`) — they're not in YAML files. In production these would be declarative too, with Secrets handled via Sealed Secrets or external secret manager.

---

## What's next

**Day 27 (review day):** comprehensive Week 4 assessment + portfolio polish + third SAA practice exam.

**Capstone (Days 31-36):** AgentCore + MCP server + production AWS stack. K8s won't be central — the stack is ECS Fargate-based per the capstone decision doc — but the K8s literacy from today means I can talk fluently about container orchestration trade-offs in interviews.

**Skills demonstrated for resume / interviews:**
- Deploy and operate workloads on Kubernetes (Deployments, Services, ConfigMaps, Secrets)
- Reason about reconciliation loops and the controller pattern
- Diagnose drift between desired and actual state
- Understand security limitations of stock K8s Secrets
- Storage troubleshooting on Linux (LVM stack)

---

## Time accounting (honest)

Plan budget: 6-7 hours.
Actual: ~5 hours active work + ~1.5 hours on infrastructure issues (disk full, VM resize).

Hours 1-2 (concepts) — done in full, with extra depth on controller manager vs ReplicaSet controller distinction.
Hours 3-4 (cluster + first deploy) — done after disk-full detour.
Hours 5-6 (scale, rollout, rollback, ConfigMap, Secret) — done.

The disk-full incident wasn't wasted time — it produced a real ops lesson and a runbook entry. Day 30's postmortem exercise will reuse this pattern.
