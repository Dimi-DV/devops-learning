# Runbook: High CPU Alarm on ASG Instances

## Alarm / Trigger

- CloudWatch alarm: `asg-cpu-high` — `CPUUtilization` > 80% sustained for > 10 minutes across ASG average
- CloudWatch alarm: `asg-cpu-critical` — `CPUUtilization` > 95% sustained for > 5 minutes
- Secondary symptom: increased ALB target response times, customer reports of slowness

## Severity

**Default: SEV-3** — degraded performance, no outage.
**Escalate to SEV-2** if `CPUUtilization` > 95% sustained, OR if customer-facing latency exceeds SLO.
**Escalate to SEV-1** if instances are becoming unresponsive and ALB is removing them from rotation faster than ASG can replace them.

## Prerequisites

- AWS Console access OR AWS CLI with `prod-readonly`
- IAM permissions: `cloudwatch:GetMetricData`, `ec2:Describe*`, `autoscaling:Describe*`, `ssm:StartSession`
- Session Manager configured on the instances (no SSH required for production access)
- Open in browser:
  - CloudWatch dashboard for the ASG
  - The ASG's scaling activity tab
  - Recent deployment history (look for changes in the last 24 hours)

## Diagnostic Steps

The goal of diagnosis is to distinguish three categories of CPU pressure, because the response for each is different:

- **A — Legitimate load increase** (traffic genuinely up) → scale out
- **B — Inefficient code** (recent deploy made a workload more CPU-heavy) → rollback
- **C — Runaway process** (one bad process consuming CPU) → kill the process and investigate

**Step 1 — Confirm the scope of the alarm.**

Is the high CPU on:
- All instances in the ASG? → likely Category A or B
- One or two specific instances? → likely Category C
- A specific time pattern (every hour, every night)? → likely a cron job or scheduled task

Check the CloudWatch metric broken out per-instance dimension to answer this.

**Step 2 — Check recent deployments.**

```bash
aws ecs describe-services --cluster <cluster> --services <service> \
  --query 'services[0].deployments[*].{status:status,createdAt:createdAt,taskDef:taskDefinition}'
```

Was there a deployment in the last 6 hours? If yes, this is the leading hypothesis (Category B). Note the task definition revision.

**Step 3 — Check traffic levels.**

CloudWatch metrics to compare against the same time last week:
- `AWS/ApplicationELB`: `RequestCount` per minute
- `AWS/ApplicationELB`: `ActiveConnectionCount`

If request volume is significantly elevated vs. baseline → Category A.

**Step 4 — Inspect a single high-CPU instance.**

Use Session Manager to get a shell on an affected instance:

```bash
aws ssm start-session --target <instance-id>
```

Once on the instance:

```bash
# Top CPU consumers right now
top -b -n 1 -o %CPU | head -20

# Per-process CPU averaged over time
ps -eo pid,ppid,user,%cpu,%mem,cmd --sort=-%cpu | head -20

# Load average (1 min, 5 min, 15 min)
uptime
```

- If a single process is dominating CPU (>50% by itself) → Category C
- If many processes share elevated CPU evenly → Category A or B (load distribution)
- If load average is much higher than CPU count → the system is queueing work, not just busy

**Step 5 — Inspect application-level signals.**

Check the application's own logs and metrics:

```bash
aws logs tail /aws/ecs/<service-name> --since 10m | grep -iE 'slow|timeout|gc|memory'
```

Look for:
- GC pressure (Java/Go services): repeated long GC pauses suggest memory pressure causing CPU thrashing
- Slow query warnings: database queries hitting timeouts can pile up requests
- Lock contention: many threads waiting on the same resource

## Resolution Steps

**Resolution A — Scale out (Category A, legitimate load).**

Increase the ASG desired count:

```bash
aws autoscaling set-desired-capacity \
  --auto-scaling-group-name <asg-name> \
  --desired-capacity <new-count> \
  --honor-cooldown
```

Watch the CloudWatch dashboard. New instances should join the ALB target group within 3–5 minutes and begin absorbing traffic.

**Verification:** average CPU should drop below the alarm threshold within 10 minutes of new instances becoming healthy.

**Resolution B — Rollback recent deployment (Category B, inefficient code).**

For ECS:

```bash
aws ecs update-service \
  --cluster <cluster> \
  --service <service> \
  --task-definition <family>:<previous-revision>
```

See `runbooks/ecs-deployment-failure.md` for full rollback procedure.

**Verification:** CPU should return to baseline within 5 minutes of the rollback completing.

**Resolution C — Kill the runaway process (Category C, single misbehaving process).**

This is the most situational resolution and the easiest to do wrong. Before killing anything:

1. Capture diagnostic information for postmortem:
   ```bash
   ps -eo pid,ppid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head -20 > /tmp/ps-snapshot-$(date +%s).txt
   # For Java processes, capture thread dump:
   # jstack <pid> > /tmp/jstack-<pid>-$(date +%s).txt
   ```
2. Kill the process:
   ```bash
   sudo kill <pid>      # Try SIGTERM first
   # Wait 10 seconds, check if process is still there
   sudo kill -9 <pid>   # SIGKILL if necessary
   ```
3. Verify the supervising service (systemd, ECS, etc.) restarts it cleanly.
4. Watch CPU and application logs for 5 minutes to confirm the new process does not exhibit the same behavior.

If the same process becomes runaway again on the new instance → this is not Category C alone, it's likely Category B (deployed code has a bug that produces a runaway process). Move to Resolution B.

## Rollback

- **Resolution A (scale out):** if the new instances cause unrelated issues (e.g., exhaust database connection pool), scale back down with the same command using the original desired count.
- **Resolution B (deployment rollback):** revert to the failing task definition with the same `update-service` call. You're back to the starting state; escalate.
- **Resolution C (kill process):** there's no "rollback" — the process is gone. If killing it caused secondary problems (data loss, partial state), this becomes a SEV-2 in itself and needs immediate investigation.

## Escalation

Escalate if:

- CPU does not return to baseline within **30 minutes** of starting the chosen resolution
- Customer-facing latency stays above SLO threshold for **15 minutes**
- Resolution C is needed more than once in the same incident (suggests a deeper bug, not a one-off runaway)
- You cannot determine which category applies after diagnostic Steps 1–5

Escalation path:

1. Senior on-call via PagerDuty `compute-platform-escalation`
2. Notify Application team if Category B (their code is implicated)
3. SEV-2+ → open `#incident-{date}` Slack channel and post link in `#incidents`

## Related

- Runbook: `runbooks/ecs-deployment-failure.md` — for the rollback procedure details
- Runbook: `runbooks/rds-connection-errors.md` — if high CPU is downstream of database slowness
- Architecture: `docs/asg-scaling-policies.md`
- Reference: capacity planning baseline — `docs/capacity-baselines.md`
