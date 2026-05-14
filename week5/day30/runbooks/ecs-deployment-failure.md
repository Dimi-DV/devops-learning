# Runbook: ECS Service Failing to Start New Tasks

## Alarm / Trigger

Any of the following:

- CloudWatch alarm: `ecs-service-deployment-stuck` — `RunningTaskCount` < `DesiredTaskCount` for > 10 minutes
- CloudWatch alarm: `ecs-task-stop-rate-high` — task stop count > 5 in 5 minutes
- Manual report: deployment in ECS console stuck in `IN_PROGRESS` state
- Failed CI/CD pipeline reporting "ECS deployment did not stabilize"

## Severity

**Default: SEV-2** if the service has running tasks (degraded capacity, not full outage).
**Escalate to SEV-1** if `RunningTaskCount == 0` (full service outage).

## Prerequisites

- AWS Console access OR AWS CLI configured with the `prod-readonly` profile
- IAM permissions: `ecs:Describe*`, `ecs:List*`, `logs:GetLogEvents`, `ec2:Describe*`
- Open in browser:
  - ECS console for the affected cluster
  - CloudWatch Logs for the service's log group
  - The relevant deployment's task definition in the ECS console
- Slack `#incidents` channel open for status updates

## Diagnostic Steps

**Step 1 — Confirm the symptom and scope.**

```bash
aws ecs describe-services \
  --cluster <cluster-name> \
  --services <service-name> \
  --query 'services[0].{desired:desiredCount,running:runningCount,pending:pendingCount,deployments:deployments[*].{status:status,taskDef:taskDefinition,desired:desiredCount,running:runningCount,failed:failedTasks}}'
```

Note the `failedTasks` count on the primary deployment. If it's incrementing on each check, ECS is repeatedly trying to start tasks that are failing.

**Step 2 — Find a stopped task to inspect.**

```bash
aws ecs list-tasks --cluster <cluster-name> --service-name <service-name> --desired-status STOPPED --max-results 10
```

Pick the most recent task ARN.

**Step 3 — Get the stop reason.**

```bash
aws ecs describe-tasks --cluster <cluster-name> --tasks <task-arn> \
  --query 'tasks[0].{stopCode:stopCode,stoppedReason:stoppedReason,containers:containers[*].{name:name,exitCode:exitCode,reason:reason}}'
```

The `stoppedReason` field is the primary signal. Use the table below to branch.

| `stoppedReason` contains | Likely cause | Go to |
|---|---|---|
| `CannotPullContainerError` | ECR image missing, untagged, or task lacks pull permissions | Step 4 |
| `ResourceInitializationError` | Secrets Manager / SSM Parameter Store access failed | Step 5 |
| `Essential container in task exited` | Application crash on startup | Step 6 |
| `Task failed ELB health checks` | App started but isn't healthy from ALB's perspective | Step 7 |
| `Task failed container health checks` | App started but the container `HEALTHCHECK` is failing | Step 7 |
| `Host EC2 ... terminated` | Underlying EC2 capacity issue (only if launch type is EC2, not Fargate) | Step 8 |
| Empty or unhelpful | Inspect CloudWatch Logs for the task | Step 6 |

**Step 4 — Image pull failure (`CannotPullContainerError`).**

Check the task definition's image reference:

```bash
aws ecs describe-task-definition --task-definition <task-def-arn> \
  --query 'taskDefinition.containerDefinitions[*].image'
```

Then verify the image exists in ECR:

```bash
aws ecr describe-images --repository-name <repo-name> --image-ids imageTag=<tag>
```

- If image does not exist → an upstream CI/CD step failed to push, or the image was deleted. Go to **Resolution: Rollback to previous task definition**.
- If image exists but pull is failing → check the task execution IAM role has `AmazonECSTaskExecutionRolePolicy` attached.

**Step 5 — Secrets / parameter resolution failure (`ResourceInitializationError`).**

The `stoppedReason` will name the specific secret or parameter. Verify:
- The resource exists in Secrets Manager or Parameter Store
- The task execution role has `secretsmanager:GetSecretValue` or `ssm:GetParameters` for the resource ARN

Go to **Resolution: Fix IAM or recreate missing secret**, then redeploy.

**Step 6 — Application crash (`Essential container exited`).**

Pull the container logs for the stopped task:

```bash
aws logs tail /ecs/<service-name> --since 15m --filter-pattern '<task-id-short>'
```

Look for stack traces, missing environment variables, failed database connections, or panics. The fix lives in the application code or configuration — typically a rollback while the engineer who pushed the change investigates.

**Step 7 — Health check failures.**

For ELB health checks:

```bash
aws elbv2 describe-target-health --target-group-arn <target-group-arn>
```

Note the `Reason` field. Common cases:

- `Target.Timeout` — app is slow to start. Increase the target group's deregistration delay or the ECS service's `healthCheckGracePeriodSeconds`.
- `Target.FailedHealthChecks` — app returns non-200 on the health check path. Verify the app's `/health` endpoint works by hitting a running task directly.
- `Target.ResponseCodeMismatch` — app is up but returning wrong status code. Check the target group's expected response codes.

For container `HEALTHCHECK`: inspect the task definition's healthcheck command and run it manually inside a working task if one exists.

**Step 8 — Capacity issue (EC2 launch type only).**

Check the ECS cluster's capacity:

```bash
aws ecs describe-clusters --clusters <cluster-name> --include STATISTICS
```

If `registeredContainerInstancesCount` is low or capacity is exhausted, the Auto Scaling Group backing the cluster needs to scale out or the instance type lacks resources for the task's CPU/memory requirements. Escalate to Infrastructure if not obvious.

## Resolution Steps

**Resolution A — Rollback to previous task definition** (most common, fastest mitigation).

```bash
# Find the previous task definition revision
aws ecs list-task-definitions --family-prefix <family-name> --sort DESC --max-results 5

# Update the service to use the previous revision
aws ecs update-service \
  --cluster <cluster-name> \
  --service <service-name> \
  --task-definition <family-name>:<previous-revision>
```

Wait for the new deployment to stabilize:

```bash
aws ecs wait services-stable --cluster <cluster-name> --services <service-name>
```

**Resolution B — Fix the root cause and redeploy** (only after stop-the-bleeding rollback if customer impact is active).

Apply the fix identified in diagnostic steps 4–8, push a new image (if applicable), and let CI/CD deploy. Do not skip the rollback while the fix is being prepared if customers are impacted.

**Resolution C — Scale out cluster capacity** (EC2 launch type, capacity case).

Increase the ASG's desired capacity. Wait for new instances to register with ECS before retrying the deployment.

## Rollback

If the resolution made things worse:

- **From Resolution A:** revert to the original (failing) task definition with the same `update-service` command. You're back to the starting state; escalate to bring in another engineer.
- **From Resolution B:** the fix push goes through normal CI/CD, which means normal rollback procedure (push a revert commit, let the pipeline redeploy).
- **From Resolution C:** scale the ASG back down once tasks have placed successfully.

Note any manual changes made during the incident. They must be reconciled with Terraform after resolution (see "Manual mitigations introduce drift" in the postmortem template).

## Escalation

Escalate if any of the following:

- `RunningTaskCount` hits zero and rollback does not restore tasks within **10 minutes**
- The `stoppedReason` is unfamiliar or does not match any branch in Step 3
- Multiple unrelated services are showing the same symptom (suggests cluster-wide or AWS-side issue — check AWS Service Health Dashboard)
- More than **30 minutes** have passed without resolution

Escalation path:

1. Page senior on-call via PagerDuty escalation policy `ecs-platform-escalation`
2. If platform issue suspected, open AWS Support case at Business or higher severity
3. For SEV-1, open the war-room Zoom and post the link in `#incidents`

## Related

- Postmortem: `postmortems/postmortem-2026-05-03-nat-gateway-checkout-outage.md` (different root cause, same alarm shape)
- Runbook: `runbooks/high-cpu-alarm.md` (if the deployment looks healthy but performance is degraded)
- Architecture: `docs/ecs-deployment-topology.md`
- AWS documentation: ECS stopped task error reference — https://docs.aws.amazon.com/AmazonECS/latest/developerguide/stopped-task-error-codes.html
