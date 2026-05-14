# Day 30 — Incident Response, Postmortems, and Runbooks

**Date:** May 14, 2026
**Week:** 5 — Monitoring, Observability, SRE Concepts
**Status:** Complete

## What this day was about

Day 30 introduces the operational maturity layer that sits on top of monitoring. Monitoring tells you *that* something is wrong; incident response is the discipline of what happens *next* — how the team detects, responds to, mitigates, resolves, and learns from operational failures.

The day produces three artifact types:

1. **Notes on the incident response framework** (this file)
2. **One postmortem** — a backward-looking document about a specific incident
3. **Three runbooks** — forward-looking procedural guides for paging-conditions

These aren't just academic exercises. They are the artifacts mature engineering organizations actually produce, and they are reviewed in interviews because they reveal how a candidate thinks about reliability.

## Key concepts

### Incident response framework

An incident is a deviation from expected service behavior with customer or business impact. The deviation may be measurable (latency, error rate, availability) or qualitative (third-party outage breaking a user flow). What matters is customer impact, not the technical specifics of what's happening internally.

The five-phase lifecycle:

1. **Detect** — alarm fires, customer reports, monitoring anomaly. MTTR clock starts here.
2. **Respond** — on-call acknowledges page, opens incident channel, communicates. *Establish command before investigating.*
3. **Mitigate** — stop the bleeding. Often not the root-cause fix (rollback is mitigation; understanding why v2.4 broke is resolution).
4. **Resolve** — root cause identified and properly fixed. System back to healthy steady state.
5. **Follow-up** — postmortem, action items, lessons learned.

The critical distinction is **mitigate vs. resolve**. Senior on-calls will say "I rolled back the deploy, customers are unblocked, we'll investigate tomorrow." That's healthy: mitigation fast, root-cause analysis careful.

### Terminology

- **MTTR** = Mean Time To Resolution (sometimes Recovery, Repair, or Restore — industry is sloppy). The headline metric for incident response. Lower is better.
- **SEV levels** = severity classification.
  - SEV-1: site down, major revenue impact, customer data at risk. All hands, page everyone, war room.
  - SEV-2: significant degradation, partial service. Page on-call.
  - SEV-3: minor issue, no customer-visible impact. Business hours.
- **On-call rotation** = schedule where engineers take turns being the first responder. Tools like PagerDuty manage scheduling and paging.
- **Incident Commander** = the engineer responsible for coordinating an incident's response, not just fixing it.

### Postmortems vs. runbooks

| Dimension | Postmortem | Runbook |
|---|---|---|
| Direction | Backward-looking (one specific incident) | Forward-looking (a class of incidents) |
| Audience | Engineering org, future readers | Future responder (possibly groggy, possibly an agent) |
| Voice | Narrative ("the on-call investigated") | Imperative ("check the logs") |
| Structure | Flexible — spirit over letter | Rigid — consistent across the collection |
| Goal | Learning and system improvement | Fast, repeatable action |

A useful frame: **postmortems are literature, runbooks are code.** Both have rules, but the rules are stricter for code.

### What goes in a postmortem

Five questions every postmortem answers, regardless of formatting:

1. What happened, and when?
2. Who was affected, and how badly?
3. Why did it happen — at the deepest honest level?
4. What did we learn?
5. What are we going to do about it, specifically, and who's doing it?

The standard nine sections that answer those questions:

1. Metadata (date, severity, authors)
2. Summary (3 sentences for an executive)
3. Impact (quantified — duration, users, revenue, SLO)
4. Timeline (UTC, minute-by-minute, including wrong hypotheses)
5. Root cause analysis (5 Whys — push until you hit something systemic)
6. What went well
7. What went poorly
8. Action items (concrete, owned, dated)
9. Lessons learned (the durable wisdom)

Two principles that separate good postmortems from mediocre ones:

- **Blameless framing.** Focus on systems and processes, not individuals. "The team's mental model defaulted to application-layer causes" — not "Dimitrije was slow to identify the issue."
- **5 Whys for root cause.** Stop at the third Why and you get a shallow action item ("add more NAT gateways"). Push to the fifth Why and you get a structural one ("establish a quarterly review of known limitations"). Both belong; only the second is the real wisdom.

### What goes in a runbook

The structure used in the three runbooks produced today:

1. **Alarm / Trigger** — what fires this runbook
2. **Severity** — default SEV plus escalation conditions
3. **Prerequisites** — access, tools, dashboards needed before step 1
4. **Diagnostic Steps** — numbered, branching, leading to a resolution path
5. **Resolution Steps** — the actual fix actions, with commands
6. **Rollback** — how to reverse every state-changing action
7. **Escalation** — when to stop trying, who to page
8. **Related** — postmortems, related runbooks, architecture docs

Critical principle: **the unit of a runbook is "what does the responder see when they're paged?" — not "what went wrong upstream."** A single alarm has one runbook; the runbook's diagnostic section fans out to all possible causes for that symptom. This is why "ECS service failing to start tasks" gets one runbook even though the underlying cause could be a missing ECR image, an IAM gap, an app crash, or a health-check misconfiguration. All four cases produce the same page, so one runbook handles the diagnostic fan-out.

Another critical principle: **diagnosis before resolution.** Junior runbooks jump to "restart the service." Senior runbooks say "first determine *why* the service is failing — here are the diagnostic branches and how to distinguish them." Diagnosis-first prevents confident wrong actions.

### Connection to observability

A subtle but important realization: tests, linters, CI checks, alarms, health checks, structured logs are all the same kind of investment — **converting silent failures into loud, locatable failures**.

The pattern is universal:

| Without instrumentation | With instrumentation |
|---|---|
| App crashes silently; users notice via support tickets | Health check fails → alarm fires → page within 2 minutes |
| Bad code merges to main, breaks on next deploy | CI lint + tests catch on the PR; never reaches main |
| Database queries slowly degrade over weeks | Slow query alarm catches at week 1 |

This is what "observability as a first-class engineering investment" means. Mature teams treat instrumentation as part of the feature, not as something added afterward. "If it isn't observable, it isn't done."

Each alarm a system has → needs a runbook. New alarm → new runbook (Definition of Done). This is how SRE orgs scale operationally as systems grow.

### Connection to the Triage project

The runbooks produced today become **skill tier 2** (user-defined skills) when wired into the Triage agent via `runbooks-api/*` MCP namespace on Day 36. The structure consistency enforced today is what makes the parser feasible later.

The mental model: in Triage, the agent **is** the responder. The agent receives the CloudWatch alarm, queries `runbooks-api/lookup` to retrieve the runbook for that alarm type, then follows the diagnostic steps. The runbook is data the agent reads; it's a passive lookup service, not an event subscriber.

The eval table on Day 35 will implicitly audit whether the runbooks themselves are fit for purpose. If the agent fails because the runbook gave it bad guidance, that's a runbook problem. The eval audits the *entire response system*, not just the agent's reasoning.

## Artifacts produced today

### Postmortem

`postmortems/postmortem-2026-05-03-nat-gateway-checkout-outage.md`

A full postmortem for a scenario where the production ECS checkout service failed for 45 minutes due to a single-AZ NAT gateway degradation. Both private subnets routed egress through one NAT gateway in `us-east-1a`; when that NAT degraded, both subnets lost egress simultaneously. The fifth Why surfaces the structural cause: no review cadence existed for "known limitations" documented at design time. Eight action items spanning prevention, detection, and process improvement. Includes one action item (FIS scenario for NAT failure) that foreshadows the Day 35 outage corpus design.

### Runbooks

Three runbooks, each demonstrating a different archetype:

1. `runbooks/ecs-deployment-failure.md` — **"Stuck workflow" archetype.** Something should be happening but isn't. Diagnostic branching on the `stoppedReason` field from `describe-tasks`, with eight branches mapping to specific resolution paths.

2. `runbooks/high-cpu-alarm.md` — **"Metric threshold" archetype.** Something is too much. Diagnostic branching distinguishes legitimate load (scale out), inefficient code (rollback), and runaway process (kill with care). Demonstrates the importance of distinguishing categories before acting.

3. `runbooks/rds-connection-errors.md` — **"Downstream dependency" archetype.** Something can't reach what it needs. Five failure modes (network, connection limit, CPU saturation, failover, hard down), each with phased resolution (immediate mitigation + root cause). Demonstrates extreme caution around irreversible actions (failover, replica promotion, query kills).

These three archetypes cover most of the alarm patterns Triage will need to handle.

## What I want to remember from today

- **The unit of a runbook is the page, not the cause.** One symptom, one runbook, internal branching.
- **Mitigate before you resolve.** Stop the bleeding first; understand later.
- **The fifth Why is where the real action item lives.** Push past proximate causes to systemic ones.
- **Diagnosis before resolution.** Don't restart the service before knowing why it's failing.
- **Every state-changing action needs a documented rollback.** If you can't reverse it, the runbook has a bug.
- **Blameless framing is not politeness — it's accuracy.** Systems fail; individuals do their best with the information they had.
- **Observability is an engineering investment that pays in MTTR.** Tests, linters, alarms, health checks — same family.
- **Runbooks are code, postmortems are literature.** Different rules for different shapes.

## Cross-references

- Postmortem: `postmortems/postmortem-2026-05-03-nat-gateway-checkout-outage.md`
- Runbooks: `runbooks/ecs-deployment-failure.md`, `runbooks/high-cpu-alarm.md`, `runbooks/rds-connection-errors.md`
- Triage decision doc Section 3.6: skill tier 2 (user-defined skills) — the runbooks here are the prototype
- Triage decision doc Section 3.5: AgentCore Evaluations + MAST — the eval system that audits whether these runbooks are actually working
- Battle plan Day 36: `/add-runbook` Claude Code skill — the scaffolding tool that enforces this structure on future runbooks
