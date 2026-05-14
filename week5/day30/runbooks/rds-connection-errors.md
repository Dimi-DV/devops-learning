# Runbook: Application Database Connection Errors to RDS

## Alarm / Trigger

- CloudWatch alarm: `app-db-connection-error-rate` — application logs contain `connection refused` / `connection timeout` / `too many connections` errors at rate > 1% of requests
- CloudWatch alarm: `rds-cpu-high` — RDS instance CPU > 80% sustained for > 10 minutes
- CloudWatch alarm: `rds-connections-near-max` — `DatabaseConnections` > 80% of `max_connections`
- Manual report: application returning 5xx with database-related error messages

## Severity

**Default: SEV-2** — database issues almost always have customer impact.
**Escalate to SEV-1** if the database is unreachable entirely (no connections succeeding).

## Prerequisites

- AWS Console access OR AWS CLI with `prod-readonly`
- IAM permissions: `rds:Describe*`, `cloudwatch:GetMetricData`, `ec2:Describe*`, `logs:GetLogEvents`
- Database read-only credentials in Secrets Manager (for diagnostic queries; do not use write creds in a runbook)
- Open in browser:
  - RDS console for the affected database
  - CloudWatch dashboard for `RDSMetrics`
  - Application logs in CloudWatch Logs Insights
  - Performance Insights (if enabled on the instance)

## Diagnostic Steps

The five failure modes worth distinguishing, each with a different fix:

- **A — Network path broken** (security group, NAT, route table) → fix network
- **B — Database is up but at connection limit** → scale connections or restart pool
- **C — Database is up but CPU-saturated** → identify expensive queries
- **D — Database failover in progress** (Multi-AZ) → wait and verify
- **E — Database is hard down** (instance failure) → restore or fail over

**Step 1 — Can anything reach the database at all?**

From an application instance (via Session Manager):

```bash
# Test TCP connectivity to the RDS endpoint
nc -zv <rds-endpoint> 5432   # or 3306 for MySQL
```

- Connection refused immediately → Category A or E (network or instance down)
- Connection times out (hangs then fails) → Category A (security group / route)
- Connection succeeds → database is reachable; go to Step 2

**Step 2 — Check the RDS instance status.**

```bash
aws rds describe-db-instances --db-instance-identifier <db-id> \
  --query 'DBInstances[0].{status:DBInstanceStatus,az:AvailabilityZone,multiAZ:MultiAZ,endpoint:Endpoint.Address}'
```

Possible statuses:
- `available` → database is healthy from AWS perspective; go to Step 3
- `failing-over` → Category D, wait and verify
- `rebooting` / `modifying` → maintenance in progress; check AWS Health Dashboard
- `incompatible-parameters` / `storage-full` → escalate immediately

**Step 3 — Check connection count vs. limit.**

```bash
aws cloudwatch get-metric-statistics \
  --namespace AWS/RDS \
  --metric-name DatabaseConnections \
  --dimensions Name=DBInstanceIdentifier,Value=<db-id> \
  --statistics Maximum \
  --start-time $(date -u -d '15 minutes ago' +%Y-%m-%dT%H:%M:%SZ) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%SZ) \
  --period 60
```

Compare against `max_connections` parameter (in the parameter group, typically formula-based on instance size).

If `DatabaseConnections` is near or at the maximum → Category B.

**Step 4 — Check database CPU and slow queries.**

CloudWatch metrics for the RDS instance:
- `CPUUtilization`
- `ReadIOPS` / `WriteIOPS`
- `DiskQueueDepth`

If CPU is sustained > 80% → Category C. Use Performance Insights to identify expensive queries:

```bash
aws pi describe-dimension-keys \
  --service-type RDS \
  --identifier <rds-resource-id> \
  --metric db.load.avg \
  --group-by Group=db.sql_tokenized,Limit=10 \
  --start-time $(date -u -d '30 minutes ago' +%s) \
  --end-time $(date -u +%s)
```

The top SQL by load is the suspect. Often a missing index, a recently deployed query, or a runaway analytical query.

**Step 5 — Check the network path (if Step 1 indicated network issues).**

Verify the application security group can reach the database security group:

```bash
aws ec2 describe-security-groups --group-ids <db-security-group-id> \
  --query 'SecurityGroups[0].IpPermissions'
```

The DB security group should allow inbound from the application security group on the database port. If recently changed (check CloudTrail) → Category A.

Also verify:
- Route tables for the application's subnets point to the right targets
- No recent VPC changes (NAT gateway, peering connections)
- AWS Service Health Dashboard for RDS in your region

## Resolution Steps

**Resolution A — Fix network path.**

Specific fix depends on what's broken:

- **Security group change reverted:** restore the previous rule via Terraform or as an emergency manual change. Document the manual change for reconciliation.
- **NAT gateway issue:** see the NAT-related runbook (or postmortem `postmortem-2026-05-03-nat-gateway-checkout-outage.md`).
- **VPC peering / route table:** escalate to Infrastructure team; do not modify routing tables alone during an incident.

**Verification:** TCP connectivity test from Step 1 succeeds; application connection error rate returns to baseline.

**Resolution B — Connection limit exhaustion.**

Two-phase response:

**Phase 1 (immediate, stop the bleeding):**

Restart the application service to flush stale connections. For ECS:

```bash
aws ecs update-service --cluster <cluster> --service <service> --force-new-deployment
```

This causes ECS to start new tasks and drain old ones, releasing their connections.

**Phase 2 (root cause):**

The application is leaking connections or has a misconfigured pool. After the immediate fix:
- Check connection pool configuration (max pool size × number of app instances must be < `max_connections` with headroom)
- Look for code paths that open connections without releasing them
- Consider RDS Proxy as a longer-term solution

**Verification:** `DatabaseConnections` drops as old tasks drain; new connections succeed.

**Resolution C — CPU-saturated database.**

**Phase 1 (immediate):**

If a specific query is dominating load and is identifiable (from Step 4), and it's safe to kill:

```sql
-- PostgreSQL example
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = <pid>;
```

**Use extreme caution.** Killing the wrong query can corrupt data or break dependent services. Only kill queries you can confidently identify as runaway analytical work, not transactional traffic.

**Phase 2 (root cause):**

- If recent deploy: rollback (see `runbooks/ecs-deployment-failure.md`)
- If missing index: add the index (off-hours preferred; concurrent index creation in PostgreSQL avoids locking)
- If volume genuinely up: scale the RDS instance (requires downtime unless using Aurora)

**Resolution D — Failover in progress.**

Wait. Multi-AZ failovers typically complete in 60–120 seconds. The application's connection pool will need to reconnect; restart the application service (Resolution B Phase 1) if connections do not recover within 3 minutes after the failover completes.

**Verification:** RDS status returns to `available`; application reconnects.

**Resolution E — Database hard down.**

This is the worst case. Steps depend on configuration:

- **Multi-AZ:** AWS should automatically fail over to the standby. If it has not within 5 minutes, manually trigger via `aws rds reboot-db-instance --force-failover`.
- **Single-AZ with read replica:** promote the read replica to primary. **This is a data-loss operation** for any writes that did not replicate before the primary failed. Coordinate with engineering leadership before promoting.
- **Single-AZ with no replica:** restore from the latest automated snapshot. Significant downtime; data loss back to the snapshot time.

**Verification:** New endpoint accessible; application reconfigured to point at the new primary; data integrity confirmed before declaring resolved.

## Rollback

- **Resolution A:** if the network change had a reason (intentional security tightening that revealed a missing rule), reverting opens that gap again. Document the trade-off in the incident channel before reverting.
- **Resolution B:** force-deploying a service is generally safe to do twice — but if the new tasks fail to start, see `runbooks/ecs-deployment-failure.md`.
- **Resolution C (Phase 1):** killed queries cannot be un-killed. If the query was important, the calling service will retry or fail; investigate the impact.
- **Resolution D:** failovers cannot be cleanly rolled back. Once the standby is primary, it is primary.
- **Resolution E:** any data restoration is irreversible at incident time. The state at the point of restoration is the new ground truth.

## Escalation

Escalate immediately if any of:

- Database status is anything other than `available` or `failing-over`
- Resolution E is required (you are not making this call alone)
- Data integrity is in question (replication lag during incident, mismatched writes, etc.)
- The application uses this database AND it's a system of record for financial / customer / regulated data

Time-based escalation:

- **5 minutes** without identifying a category → page senior on-call
- **15 minutes** without resolution → SEV-1, war room
- **Any** data-integrity question → page engineering leadership

Escalation path:

1. Senior on-call via PagerDuty `database-platform-escalation`
2. For data integrity questions: engineering leadership + legal/compliance
3. Open AWS Support case at Critical severity if AWS-side issue suspected

## Related

- Runbook: `runbooks/ecs-deployment-failure.md` — for application rollback details
- Runbook: `runbooks/high-cpu-alarm.md` — if app CPU is downstream of DB slowness
- Postmortem: `postmortems/postmortem-2026-05-03-nat-gateway-checkout-outage.md` — example of network path failure
- Architecture: `docs/rds-topology.md`
- AWS documentation: RDS troubleshooting — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_Troubleshooting.html
- AWS documentation: Performance Insights — https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/USER_PerfInsights.html
