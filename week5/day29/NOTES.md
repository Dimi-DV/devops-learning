# Day 29 — Observability: SLOs, CloudWatch Alarms, and Dashboards

**The day in one sentence.** Defined SLOs for the healthy-app service, then built the CloudWatch alarms and dashboard in Terraform that make those SLOs enforceable — deployed, generated traffic, watched the dashboard populate, destroyed.

---

## SLOs first, alarms second

The prompt said "add monitoring, then define SLOs." Did it in reverse order deliberately. Alarms without SLOs are guesswork — you end up with thresholds like "CPU > 80%" with no articulation of *why* 80% and not 70% or 90%. The SLO document (`SLOs.md`) defines three targets:

1. **Availability ≥ 99.9%** over a rolling 28 days (~40 minutes of error budget)
2. **Latency p95 < 500ms** at the ALB
3. **Error rate < 1%** in any 5-minute window (fast-burn tactical alert)

Every alarm threshold and dashboard widget traces back to one of these. If a metric isn't tied to an SLO or needed for context during an incident, it doesn't belong on the dashboard.

---

## Three pillars of observability

**Metrics** — numeric time-series data. "CPU was 42% at 14:03." Cheap to store, fast to query, good for alerting. CloudWatch metrics, Prometheus counters/gauges/histograms.

**Logs** — discrete events with context. "At 14:03, request abc123 to /visit failed with ConnectionRefused to postgres:5432." Expensive to store, slow to query at scale, essential for debugging after metrics tell you *something* is wrong.

**Traces** — the path of a single request across services. "Request abc123 hit ALB → task A → postgres, total 340ms, 280ms was DB." Not relevant for a single-service stack, critical once you have microservices where latency hides in inter-service calls.

**Monitoring vs observability.** Monitoring answers "is the system healthy?" — predefined checks for anticipated failure modes. Observability answers "why is the system unhealthy?" — the ability to ask arbitrary questions of a system you didn't anticipate needing to debug. Alarms are monitoring. Logs + traces + ad-hoc metric queries are observability. You need both.

---

## What was built in monitoring.tf

### Alarms

**Unhealthy host count** (existed, cleaned up)
- Metric: `UnHealthyHostCount` in `AWS/ApplicationELB`, dimensioned by TargetGroup + LoadBalancer
- Fires when `Maximum > 0` for 2 consecutive 60s periods
- Uses `Maximum` not `Average` — if any single data point in the period shows an unhealthy host, we want to know. Average would mask a host that flaps between healthy and unhealthy within a period.
- Added `ok_actions` pointing to the same SNS topic — without this, you get paged when it breaks but never notified when it heals. In production, the recovery notification is what tells on-call "the incident is over" and lets PagerDuty auto-resolve.

**CPU high** (new)
- Metric: `CPUUtilization` in `AWS/EC2`, dimensioned by `AutoScalingGroupName`
- Fires when `Average > 70%` for 5 consecutive 60s periods
- Dimensioned by ASG name, not per-instance. This gives the aggregate view — if the group as a whole is hot, something is wrong. One hot instance is normal (uneven load balancing, garbage collection); all instances hot for 5 minutes is not.
- 5 evaluation periods (vs 2 for the others) because CPU spikes are normal during deploys, healthcheck bursts, and cron jobs. Short spikes should not page anyone.

**ALB 5xx error rate** (new) — the interesting one
- Uses `metric_query` blocks instead of a single `metric_name`. Why: raw 5xx count is meaningless without knowing total request volume. 10 errors out of 10 million requests is noise; 10 errors out of 100 is a fire.
- Three metric queries: `errors` (HTTPCode_Target_5XX_Count, Sum), `requests` (RequestCount, Sum), and `error_rate` ((errors / requests) * 100). Only `error_rate` has `return_data = true` — the other two feed the expression but aren't evaluated as alarm conditions.
- Threshold is 1%, matching SLO 3. 2 evaluation periods at 60s = fires after 2 minutes of sustained errors.
- Only counts `HTTPCode_Target_5XX_Count` (errors from instances), not `HTTPCode_ELB_5XX_Count` (errors from the ALB itself like 502/503 when no targets are healthy). ELB-generated 5xx would already fire the unhealthy host alarm, so you'd get paged either way — just by a different alarm. In a more complete setup, you'd sum both to match the SLO formula exactly.

### Dashboard

Six widgets in a 2-column grid (CloudWatch uses a 24-unit grid, each widget 12 units wide = half):

| Left | Right |
|---|---|
| Request Count — traffic volume baseline | HTTP 5xx vs 2xx — red/green error view |
| Target Response Time (p95 + avg) with SLO line at 500ms | Healthy vs Unhealthy Hosts — green/red |
| ASG CPU (avg + max) with alarm threshold line at 70% | Alarm Status — red/green/grey summary panel |

Design choices:
- **Horizontal annotations** on the latency and CPU widgets draw the SLO/alarm thresholds directly on the graph. During an incident, you can see at a glance how close a metric is to its threshold without remembering what the number is.
- **p95 and Average on the same latency graph.** If average is fine but p95 is bad, you have a tail latency problem — a slow code path or one bad instance. If both are bad, the whole service is degrading.
- **CPU avg and max on the same graph.** Max shows the hottest instance. If max is high but avg is normal, load balancing is uneven. If both are high, the ASG isn't scaling out (or has hit max capacity).
- **Alarm status widget** is the "glanceable" panel — green means go look at something else. Three colors: green (OK), red (ALARM), grey (INSUFFICIENT_DATA, meaning no traffic is flowing so the metric can't be evaluated).

### Output

`dashboard_url` output gives a clickable console link after `terraform apply`. Avoids digging through the CloudWatch console to find the right dashboard.

---

## SLI / SLO / SLA — the distinction that matters in interviews

**SLI (Service Level Indicator)** — the measurement itself. "What percentage of requests returned non-5xx?" It's a number you can compute from metrics.

**SLO (Service Level Objective)** — the target for the SLI. "That percentage should be ≥ 99.9% over 28 days." It's an internal commitment the team sets. Violating it triggers reliability-focused work, not lawsuits.

**SLA (Service Level Agreement)** — a contractual commitment to a customer, with consequences for violation (refunds, credits). SLAs are always looser than SLOs — if your SLO is 99.9%, your SLA might be 99.5%, giving you a buffer before you owe money. Engineering teams target SLOs; business teams negotiate SLAs.

**Error budget** — the inverse of the SLO. If availability target is 99.9%, you have 0.1% error budget = ~40 minutes of total outage per 28 days. The error budget is what makes SLOs actionable: it turns "be reliable" into "you have 40 minutes to spend." Deployments, experiments, and migrations all consume error budget. When the budget is exhausted, the team freezes risky changes until it regenerates.

---

## What is NOT monitored, and why

**Memory utilization** — on EC2 (like on Fargate), memory often runs high and stable. The failure mode isn't gradual rise but abrupt OOM kill, better caught via instance termination events than a utilization threshold. Also, CloudWatch doesn't get memory metrics from EC2 by default — you'd need the CloudWatch agent installed, which is a separate infrastructure concern.

**Request count** — high traffic isn't a problem; it's the service doing its job. The *consequences* of high traffic (latency degradation, error rate increase) are already covered by the latency and 5xx alarms.

**4xx rate** — tracked on the dashboard for context but not alarmed. A rising 4xx rate may signal a client integration problem, but it's not a service failure and shouldn't wake someone up at 2am.

---

## terraform.tfvars vs variable defaults — precedence lesson

Hit an `InvalidParameter: Endpoint` error on the SNS subscription because `terraform.tfvars` had `alert_email = ""` (blanked before a previous commit to avoid pushing a real email to GitHub). Added a `default` in `variables.tf` thinking that would fix it — it didn't. Terraform's variable precedence:

1. Environment variables (`TF_VAR_name`)
2. `terraform.tfvars` (auto-loaded)
3. `*.auto.tfvars` (auto-loaded, alphabetical)
4. `-var` and `-var-file` flags
5. Variable `default` in the definition (lowest priority)

`terraform.tfvars` beats `default` every time. The fix was putting the real value in `terraform.tfvars` and removing the unnecessary default. Lesson: if you blank a value in tfvars for commit hygiene, you can't override it with a default — tfvars wins.

---

## Supply chain incident audit — Mini Shai-Hulud

An active supply chain campaign hit npm and PyPI on May 11–12. The Mini Shai-Hulud campaign (TeamPCP) compromised 172 packages across 403 versions — TanStack, Mistral AI, UiPath, OpenSearch, Guardrails AI, and others. Payload is a credential-stealing worm that targets AWS keys, GitHub tokens, OIDC tokens extracted from runner memory, Kubernetes configs, SSH keys, and Vault tokens. It self-propagates by using stolen npm tokens to publish infected versions of the compromised maintainer's other packages.

**Initial access vector:** a malicious PR against `TanStack/router` exploiting a `pull_request_target` workflow misconfiguration (the "Pwn Request" pattern). The attacker poisoned the GitHub Actions cache, extracted the publishing OIDC token from runner memory mid-workflow, and published packages with valid SLSA provenance — first documented case of provenance-carrying malicious artifacts.

**Relevance to this environment:** performed a 25-minute audit across five surfaces:
1. Dependency manifests (`requirements.txt` files) — all pinned, no overlap with IOC list
2. Recursive IOC name search across repo tree — no matches (4 false positives investigated and dismissed)
3. Active Python venv package list — 19 packages, all expected, no IOC matches
4. GitHub Actions workflows — no `pull_request_target` triggers present
5. Shell history during attack window — one `pip install` against a fully-pinned manifest

**Result: no exposure.** No credentials require rotation, no images need rebuilding, no infrastructure needs redeployment.

**Why this matters for observability day.** Supply chain attacks are an incident type that monitoring alone cannot catch. No CloudWatch alarm fires when a compromised package is installed. This is the gap between monitoring (predefined checks for anticipated failures) and security observability (the ability to investigate unanticipated threats). The audit methodology — enumerate surfaces, search for IOCs, verify installed state, check workflow configuration — is the manual equivalent of what tools like `pip-audit`, `npm audit`, and Dependabot automate.

**Hardening takeaways from the audit:**
- Adopt transitive dependency locking (`pip-compile` or `uv.lock`) — top-level pins don't constrain transitive deps
- Add `pip-audit` as a required CI job
- Current OIDC auth pattern is correct posture — no long-lived keys to steal. But the OIDC token *itself* was the target here, so short-lived doesn't mean invulnerable
- `pull_request_target` is dangerous because it runs with write permissions in the context of the base repo, even for PRs from forks. None of our workflows use it.

Full report: `incidents/2026-05-12-mini-shai-hulud-audit.md`

---

## Day 29 checklist

- [x] Understand three pillars of observability (metrics, logs, traces)
- [x] Can define SLIs/SLOs/SLAs with examples
- [x] CloudWatch monitoring added to Terraform project (3 alarms + dashboard)
- [ ] Prometheus/Grafana concepts (deferred — interview prep prompt still TODO)
- [x] SLO document written (`SLOs.md`)
- [x] Deployed, generated traffic, verified dashboard, destroyed
