# Service Level Objectives — healthy-app

**Service:** Flask application on ECS Fargate + ALB
**Owner:** Dimitrije Davidovic Vedda
**Last updated:** 2026-05-12
**Status:** Active

---

## Background

This document defines the Service Level Indicators (SLIs), Service Level Objectives (SLOs), and error budgets for the `healthy-app` service. It is the authoritative reference for what "the service is healthy" means, and for every CloudWatch alarm and dashboard widget in `monitoring.tf`.

The distinction between monitoring and observability is important here. Alarms catch the failures we anticipated; the SLOs are what tell us how much failure we are willing to accept before those alarms should fire. Thresholds that are not derived from an explicit target are guesswork.

---

## SLO 1 — Availability

| | |
|---|---|
| **SLI** | Proportion of requests received at the ALB that return a non-5xx status code |
| **Target** | ≥ 99.9% over a rolling 28-day window |
| **Error budget** | 0.1% of requests — approximately 40 minutes of full outage equivalent per 28 days |

### Measurement

```
availability = 1 - (
  (HTTPCode_Target_5XX_Count + HTTPCode_ELB_5XX_Count)
  /
  RequestCount
)
```

All metrics from the `AWS/ApplicationELB` namespace, dimensioned by `LoadBalancer`.

The formula includes both `HTTPCode_Target_5XX_Count` and `HTTPCode_ELB_5XX_Count` deliberately. Target 5xx means the container returned a server error; ELB 5xx means the load balancer could not obtain a valid response at all — for example, no healthy targets, connection timeout, or a task that stopped mid-request. Both represent failure from the user's perspective and both consume error budget.

4xx status codes are excluded. A 404 or 400 reflects a client-side error, not a service failure. Including 4xx would cause the SLO to degrade in proportion to invalid traffic, which is not a signal the team can act on.

### Rationale

99.9% is the standard starting point for an internal-facing or early-stage service. At 2 tasks and no persistent state to lose, the primary availability risk is ECS task replacement lag and misrouted health checks. 99.9% gives a realistic budget for planned deployments while requiring that unplanned outages are short and infrequent.

---

## SLO 2 — Latency

| | |
|---|---|
| **SLI** | p95 of `TargetResponseTime` measured at the ALB |
| **Target** | p95 < 500ms over a rolling 28-day window |
| **Error budget** | 5% of requests may exceed 500ms |

### Measurement

```
metric: TargetResponseTime
namespace: AWS/ApplicationELB
statistic: p95 (extended statistic)
dimension: LoadBalancer
```

`TargetResponseTime` is the interval between the ALB forwarding a request to a registered target and receiving the first byte of the response. It excludes connection overhead between the client and the ALB, and excludes transmission time from the ALB back to the client. It reflects the latency the application is responsible for.

p95 is the appropriate statistic rather than average or p50. Average latency is insensitive to tail behavior — a small fraction of slow requests is invisible in the average but directly experienced by the users who receive them. p95 means 1 in 20 users may wait longer than the threshold; if that number rises, something is degrading under load or a specific code path is regressing.

### Rationale

500ms is a reasonable ceiling for a simple API with in-process logic and no database calls. For requests that involve external I/O, this target would need revisiting. If a downstream dependency is added, this SLO should be renegotiated with the new latency baseline in mind.

---

## SLO 3 — Error Rate (Fast Burn)

| | |
|---|---|
| **SLI** | Proportion of requests returning a 5xx status code in any 5-minute window |
| **Target** | < 1% over any 5-minute window |
| **Error budget** | N/A — this is an alerting SLO, not a 28-day aggregate |

### Measurement

```
error_rate = (
  (HTTPCode_Target_5XX_Count + HTTPCode_ELB_5XX_Count)
  /
  RequestCount
) * 100
```

Same underlying metrics as SLO 1, evaluated over a 5-minute period rather than a rolling 28-day window.

### Relationship to SLO 1

SLO 1 and SLO 3 are not redundant. SLO 1 is the **strategic measure** — it tracks the cumulative health of the service over a long window and determines whether reliability investment is needed. SLO 3 is the **tactical alert** — it fires quickly when a spike occurs, before the 28-day aggregate has moved materially.

An error rate spike that lasts 4 minutes and resolves may barely register in SLO 1 but will fire SLO 3. That is intentional. Short spikes are still user-visible failures and warrant investigation even if they do not consume significant error budget.

---

## Error Budget Policy

| Budget remaining | Response |
|---|---|
| > 50% | Normal feature velocity. Deployments proceed on schedule. |
| 25%–50% | Elevated caution. Risky changes require review. No experiments in production. |
| < 25% | Reliability focus. Feature work deprioritized. Root cause analysis required for any further budget consumption. |
| Exhausted | Freeze on changes that could affect reliability. Post-incident review before resuming normal operations. |

---

## What is not monitored here, and why

**Memory utilization** is not an SLO metric and does not have an alarm. On Fargate, memory utilization often runs high and stable — the Python interpreter and gunicorn workers hold memory; that is normal behavior. Memory pressure manifests not as a gradual metric rise but as abrupt task termination with reason `OutOfMemoryError`, which is better detected via stopped task events or a Logs Insights query against ECS agent logs than via a utilization threshold.

**Request count** does not have an alarm. High request volume is not a problem; it is the service doing its job. The consequences of high volume that matter — latency degradation and error rate increase — are covered by SLO 2 and SLO 3 respectively.

**4xx rate** is tracked on the dashboard for context but is not an SLO metric. A rising 4xx rate may indicate a client integration problem or a routing misconfiguration and is worth investigating, but it does not represent a service failure and should not trigger an on-call response.

---

## Revision history

| Date | Change | Author |
|---|---|---|
| 2026-05-12 | Initial SLO definition | Dimitrije Davidovic Vedda |
