# Postmortem: NAT Gateway Single-Point-of-Failure Causes Checkout Outage

**Incident date:** May 3, 2026
**Authored:** May 4, 2026
**Author:** Dimitrije V. (on-call)
**Reviewers:** Infrastructure team, Platform team
**Status:** Final
**Severity:** SEV-2

---

## Summary

On May 3, 2026, an AWS NAT gateway degradation in `us-east-1a` caused our production ECS checkout service to fail for 45 minutes. Both private subnets routed egress through a single NAT gateway in the affected AZ, so the second-AZ task fleet failed alongside the first. Approximately 1,400 checkout attempts returned 5xx errors before manual mitigation — creating a second NAT gateway in `us-east-1b` and rerouting the second subnet through it — restored service for half the fleet. The remaining tasks recovered when AWS resolved the upstream issue. The root cause is structural: a documented "known limitation" (single NAT gateway, accepted for cost) was never revisited as the workload's criticality changed.

---

## Impact

| Dimension | Detail |
|---|---|
| Duration | 45 minutes (14:22–15:07 UTC) |
| Severity | SEV-2 |
| Failed checkouts | ~1,400 (estimated from ALB 5xx count, 14:22–15:07 UTC) |
| Revenue impact | Finance to confirm — estimate pending, based on gross checkout value × abandonment-after-error rate |
| Error rate at peak | 71% of checkout requests returning 5xx |
| SLO impact | Availability SLO (99.9% monthly): consumed ~22% of monthly error budget in a single event |
| Customer-visible | Yes — checkouts failed with generic 5xx response |
| Data integrity | No data loss. Failed transactions never reached the payment API; no half-completed state to reconcile |

---

## Timeline

All times UTC.

| Time | Event |
|---|---|
| 14:22 | AWS NAT gateway in `us-east-1a` begins service degradation (per AWS Service Health Dashboard, retroactively confirmed). |
| 14:25 | CloudWatch alarm `prod-alb-5xx-rate` fires; threshold >5% sustained 2 minutes. SNS pages on-call. |
| 14:27 | On-call acknowledges page. Posts in `#incidents` declaring SEV-2 investigation in progress. |
| 14:28 | On-call reviews recent deploys. Most recent deploy was 36 hours prior — ruled out as proximate cause. |
| 14:30 | On-call inspects ECS task logs. Observes high volume of `ConnectionTimeoutError` to the payment API endpoint. |
| 14:32 | Initial hypothesis: third-party payment API outage. On-call checks payment provider's status page; provider reports all systems green. |
| 14:34 | On-call pivots hypothesis: if the payment API is up and tasks can't reach it, the network path is suspect. |
| 14:35 | On-call identifies NAT gateway in `us-east-1a` as showing `ErrorPortAllocation` and `PacketsDropCount` spikes in CloudWatch. |
| 14:37 | AWS Service Health Dashboard updated to acknowledge NAT gateway service event in `us-east-1a`. |
| 14:38 | On-call proposes mitigation in `#incidents`: provision a second NAT gateway in `us-east-1b`, update `private-1b` route table to use it. Half-fleet recovery is acceptable while AWS resolves the underlying issue. |
| 14:42 | Second NAT gateway created manually via AWS Console in `us-east-1b`. Route table for `private-1b` updated to point `0.0.0.0/0` at the new NAT. |
| 14:48 | ECS tasks in `us-east-1b` recover. ALB 5xx rate drops to ~35% (half the fleet now healthy). |
| 14:50 | On-call considers provisioning a second NAT in `us-east-1a` as well to bypass the degraded one. AWS Service Health Dashboard updates that recovery is in progress; on-call holds. |
| 14:55 | AWS reports NAT gateway in `us-east-1a` fully recovered. |
| 15:02 | Tasks in `us-east-1a` recover as the original NAT resumes normal operation. |
| 15:07 | ALB 5xx rate returns to baseline (<0.5%). On-call declares incident resolved. |
| 15:15 | On-call posts initial summary in `#incidents` and schedules the postmortem review. |

---

## Root cause analysis

Applying the 5 Whys:

1. **Why did checkouts fail?**
   ECS tasks could not reach the third-party payment API. Checkout requests timed out and returned 5xx to clients.

2. **Why couldn't the tasks reach the payment API?**
   Both private subnets — `private-1a` and `private-1b` — lost internet egress.

3. **Why did both subnets lose egress?**
   Both private subnets routed `0.0.0.0/0` through a single NAT gateway located in `us-east-1a`. When that NAT degraded, both subnets lost their internet path simultaneously.

4. **Why was there only one NAT gateway?**
   The original VPC design chose a single NAT gateway as a cost optimization, saving roughly $32/month versus a per-AZ NAT configuration. The Terraform VPC module README explicitly noted this as a "known limitation" and listed multi-AZ NAT as a "production improvement."

5. **Why was that known limitation never revisited?**
   No review cadence existed for "known limitations" documented in infrastructure READMEs. The flag was raised at design time and then never resurfaced. The organization had no mechanism for periodically reconsidering deliberately accepted risks as the workload's criticality changed.

**The fifth Why is where the structural action item lives.** The proximate fix ("add more NAT gateways") would prevent the second occurrence of this specific outage. The structural fix ("establish a quarterly review of known infrastructure limitations") prevents the entire category of outages where a deliberately accepted risk silently becomes unacceptable.

### Contributing factors

- **Runbook gap.** The runbook for high 5xx error rate did not include NAT gateway as a candidate cause, biasing initial investigation toward the application layer.
- **Recent-context anchoring.** A deploy-related incident the prior week had produced similar symptoms. This anchored the on-call's early hypothesis on the application rather than the network.
- **Alarm threshold miscalibration.** CloudWatch alarms on NAT gateway `ErrorPortAllocation` existed but had been tuned to thresholds that did not fire during this event. Properly tuned alarms would have caught the issue approximately 5 minutes earlier.
- **NAT metrics not on the primary dashboard.** The on-call had to navigate to the VPC console to find NAT-level metrics rather than seeing them in the on-call dashboard.

---

## What went well

- **Alerting fired quickly.** The ALB 5xx alarm caught the issue 3 minutes after onset.
- **Page-to-ack time was strong.** 2 minutes from page to acknowledgement, well within the SEV-2 target of 5 minutes.
- **Communication discipline.** The `#incidents` channel had a clear running narrative from 14:27 forward. Stakeholders did not need to ask "what's happening?"
- **Mitigation worked under pressure.** Provisioning a new NAT gateway and rerouting a subnet during an active incident restored half the fleet without breaking anything else.
- **No data loss.** Failed checkouts failed cleanly. No half-completed transactions, no payment-side reconciliation required.
- **AWS Service Health correlation.** Once the network path was suspected, AWS's own status dashboard corroborated the hypothesis within 2 minutes, accelerating the response.

---

## What went poorly

- **A known SPOF was never revisited.** The single-NAT cost optimization made sense when the system was small. As checkout volume grew, the risk profile changed but the decision did not.
- **Initial diagnosis chased the wrong layer.** Eight minutes were spent investigating the application before the network path was considered. The runbook did not list NAT gateway among the candidate causes for ALB 5xx errors.
- **Mitigation introduced infrastructure drift.** The new NAT gateway and route table change were made manually in the console, not via Terraform. The state and the live infrastructure are now out of sync until reconciled.
- **NAT metrics were not where the on-call was looking.** Critical signals lived in the VPC console rather than the primary on-call dashboard.
- **Alarm thresholds were miscalibrated.** Existing alarms on NAT-level metrics existed but were tuned too loosely to fire during this event.

---

## Action items

| ID | Action | Owner | Priority | Due |
|---|---|---|---|---|
| AI-1 | Provision a NAT gateway per AZ permanently via Terraform. Reconcile the manually created NAT in `us-east-1b` into IaC. Remove drift. | Infrastructure | P0 | May 10, 2026 |
| AI-2 | Update VPC Terraform module so `single_nat_gateway` defaults to `false` for any environment tagged `production`. Require explicit override with documented justification. | Infrastructure | P0 | May 10, 2026 |
| AI-3 | Add NAT gateway health metrics (`ErrorPortAllocation`, `PacketsDropCount`, `IdleTimeoutCount`) to the primary on-call CloudWatch dashboard. | Platform | P1 | May 17, 2026 |
| AI-4 | Tighten CloudWatch alarm thresholds on NAT gateway error metrics. Page on-call when sustained anomaly exceeds 2 minutes. | Platform | P1 | May 17, 2026 |
| AI-5 | Update the "high 5xx error rate" runbook to include a "network egress path" diagnostic section: NAT health, route tables, security groups, AWS Service Health Dashboard check. | SRE | P1 | May 17, 2026 |
| AI-6 | Establish a quarterly "known limitations review" — a recurring meeting that surfaces every README-documented limitation, reviews whether it still represents an acceptable risk, and converts accepted risks into either action items or formal exceptions. | Engineering leadership | P1 | First review: June 30, 2026 |
| AI-7 | Add an FIS (Fault Injection Service) scenario simulating NAT gateway failure in one AZ. Include in the quarterly chaos engineering exercise. | SRE | P2 | June 30, 2026 |
| AI-8 | Postmortem process improvement: add a "did the runbook help?" question to the postmortem template to systematically capture runbook gaps. | SRE | P2 | May 31, 2026 |

---

## Lessons learned

**Cost optimizations are decisions, not facts.** The single-NAT choice was deliberate, documented, and correct for the system as it existed when the choice was made. The mistake was not the choice — it was the absence of a mechanism to revisit the choice as the system grew. Every "known limitation" in a README is an IOU. Without a review cadence, IOUs accumulate quietly until one of them comes due during an incident.

**Anchoring on recent context is a real cost during triage.** The on-call's hypothesis space was shaped by the prior week's deploy incident. The same engineer, facing the same symptoms on a different day with no prior anchor, would likely have considered network causes earlier. This is not a personal failure — it is how human cognition works under pressure. Mitigations are environmental: better runbooks that force consideration of multiple layers, better dashboards that surface the right signals, and structured triage checklists that resist the pull of the most recent priors.

**Manual mitigations are useful and dangerous in the same breath.** Creating a NAT gateway in the console under pressure saved roughly 20 minutes versus writing and applying Terraform. It also created drift that has to be reconciled. The lesson is not "don't do this" — under pressure, do whatever stops the bleeding. The lesson is "schedule the reconciliation as a P0 follow-up before closing the incident." Drift accepted intentionally and tracked is fine; drift accepted and forgotten is how next year's outage starts.

**Defense in depth applies to availability, not just to security.** A single NAT gateway is a single point of failure in exactly the same way a single AZ is. The cost of redundancy (~$32/month) was trivially smaller than the cost of this outage. Future infrastructure design reviews should explicitly cost-justify removed redundancy, not just removed dollars.

**The fifth Why is worth the discomfort.** Stopping at the third Why ("we only had one NAT") yields a shallow action item ("add more NATs") that prevents the next instance of *this* outage. Pushing to the fifth Why ("we never revisited known limitations") yields a structural action ("establish a quarterly review") that prevents the next *category* of outage. Both action items belong in this document. Only the second one is the real wisdom.

---

## References

- Terraform VPC module README — `single_nat_gateway` limitation documented; multi-AZ NAT listed as "production improvement"
- AWS Service Health Dashboard archive, May 3, 2026 — `us-east-1` NAT gateway service event
- AWS NAT gateway CloudWatch metrics reference — https://docs.aws.amazon.com/vpc/latest/userguide/vpc-nat-gateway-cloudwatch.html
- Pre-incident runbook: `runbooks/high-5xx-error-rate.md`
- Slack `#incidents` thread, May 3, 2026 14:27 UTC onward

---

*This postmortem is blameless. Its purpose is to improve the system, not to assign individual fault. Where actions or omissions are described, the question is "what about the system made this likely?", not "who is at fault?"*
