# Week 5 — Day 31

**Date:** May 15, 2026
**Type:** Reading day. No infrastructure code. No deploys.
**Hours invested:** ~4.5 hours active reading + back-and-forth conceptual work.

## Context

Day 31 is the first day of the Triage capstone sprint (Days 31–36), per the v3 decision doc in `~/triage/triage-decision-doc-v3.md`. The sprint builds an AIOps incident-response agent on Amazon Bedrock AgentCore with a custom MCP server, four-namespace tool partition (ECS / logs / metrics / runbooks), Cedar policy guardrails, AWS FIS-injected outage corpus, and AgentCore Evaluations with MAST failure-mode classification.

Per the decision doc, Day 31 is browser-only: read the source material, build the mental model, do not start coding. Claude Code installation and the first infrastructure commits are Day 32 morning.

## What I read

Consolidated study guide synthesizing the following sources into one continuous narrative:

- **Molumuri, Fine, Alioto, Qureshi** — "Leverage Agentic AI for Autonomous Incident Response with AWS DevOps Agent" (AWS DevOps Blog, March 31, 2026). The canonical architecture being mirrored.
- **AgentCore developer guide** — Runtime, Memory, Gateway, Identity primitives (October 2025 GA, re:Invent 2025 additions including Episodic Memory).
- **AgentCore Evaluations announcement** — "Amazon Bedrock AgentCore adds quality evaluations and policy controls for deploying trusted AI agents" (March 31, 2026). 13 built-in evaluators, LLM-as-judge custom evaluators, code-based evaluators, ground-truth modes.
- **Sebin, Arora, Jha** — "IBM and UC Berkeley Diagnose Why Enterprise Agents Fail Using IT-Bench and MAST" (Hugging Face blog, February 18, 2026). 14-mode failure taxonomy across FC1 system design, FC2 inter-agent misalignment, FC3 task verification.
- **Arora, Oruganty** — "Build multi-agent site reliability engineering assistants with Amazon Bedrock AgentCore" (AWS ML Blog). Source of the four-namespace MCP convention.
- **aws-samples/sample-fully-autonomous-incident-response** — three-agent A2A reference implementation (Strands + OpenAI Agents SDK + Google ADK).
- **MCP protocol docs** — modelcontextprotocol.io spec, 2026 roadmap by David Soria Parra, OAuth 2.1 + RFC 8707 Resource Indicators for production auth.
- **AWS FIS docs** — experiment templates (targets + actions + stop conditions), scenarios library, AZ slowdown / EC2 stop / EBS pause-IO / network blackhole as the four corpus scenarios.
- **Operational gap-fill** — SSM Session Manager, CloudTrail, AWS Config, GuardDuty, IAM Access Analyzer.

## Concepts that crystallized (with the Q&A threads that did the work)

These weren't passive reading. Each one required multiple rounds of pushback before the model in my head matched what the docs actually say.

### 1. AgentCore vs. AWS DevOps Agent — separating the layers

Started confused about whether they were the same product. Resolved by working through a three-layer stack: **Bedrock** (model inference) → **AgentCore** (general-purpose agent primitives, what I'm building on) → **DevOps Agent** (a specific product AWS built on AgentCore, what I'm mirroring but not using). DevOps Agent's "Agent Spaces" feature is a product-layer abstraction; my Triage build does the same job by hand via IAM scoping and explicit AgentCore configuration. Cost, control, and portfolio differentiation are why I'm building rather than configuring DevOps Agent.

### 2. Why my capstone evaluations aren't reproducible from DevOps Agent

I pushed Claude on whether AgentCore Evaluations could be wedged onto DevOps Agent traces. First answer was overconfident: "DevOps Agent traces are opaque." After I asked for verification, Claude searched the docs and corrected itself — DevOps Agent does ship vended logs to CloudWatch and AgentCore Evaluations does read from CloudWatch log groups, so the integration is theoretically possible. The honest interview framing isn't "impossible" but "not productized as a workflow, and you can't act on the findings because DevOps Agent doesn't expose the agent design surface."

**Lesson for me:** push back when the model sounds too confident on recent-GA territory. Trust-but-verify is how I avoid putting hallucinated claims into interview answers.

### 3. AgentCore Identity — STS-shaped credential broker, not a permission grantor

Initial intuition: "Identity assigns permissions to agents." Wrong. Identity is closer to Secrets Manager + a smart proxy. The agent's AWS permissions live in plain IAM (same IAM roles I've been writing since Week 2). Identity holds the *credentials* (Cognito JWTs for ingress, OAuth tokens / API keys for egress) and brokers the issuance of resource credentials. For AWS resources specifically, Identity coordinates with the agent's IAM execution role via STS; for third parties, Identity returns tokens from its vault.

### 4. The two-token delegation pattern

Worked through the actual flow with Claude: user authenticates to IdP → user token → AgentCore Identity exchanges it for a **workload access token** (proves agent-plus-user identity) → workload token is presented to Identity's resource credential provider → provider issues the actual AWS/OAuth/API-key credential → agent uses that credential against the real service.

The critical insight: the workload access token is an **identity proof**, not a capability bundle. A stolen workload token can't be used as an AWS credential directly. The two-token separation is the security boundary.

### 5. IAM scoping in a four-namespace Gateway architecture

Asked Claude how IAM scoping works in my single-agent setup with four namespaces. Initial answer focused on the agent execution role only. After I asked for doc verification, the picture got cleaner:

- **Agent execution role**: minimal — call Gateway, call Identity, write to Observability.
- **Gateway service role**: can invoke the four target Lambdas.
- **Per-namespace backend Lambda roles** (4): each scoped to exactly what that namespace needs (ECS describes, CloudWatch Logs, CloudWatch metrics, runbook backend).

Six IAM roles total. Defense in depth: the agent code never holds powerful AWS credentials directly. Prompt injection attempts to make the agent call AWS directly fail because the agent doesn't have AWS credentials to misuse.

### 6. OpenAPI → MCP tool translation timing

The agent doesn't get tool definitions on-demand from OpenAPI specs. Translation happens **once at Gateway target creation**, persisted as part of the target. The agent fetches the full pre-translated MCP catalog at session start via `tools/list`. If I change a spec, I have to call `UpdateGatewayTarget` / `SynchronizeGatewayTargets` to propagate. Semantic search via `x_amz_bedrock_agentcore_search` exists for large tool catalogs but I won't need it at my scale.

### 7. Single-agent with four namespaces is not "one namespace at a time"

Worked through the question of whether the agent "takes up" one namespace per session. It doesn't. The agent has the full MCP catalog from all four namespaces in context throughout the session. The four-namespace partition is for **tool selection clarity** (the prefix gives the LLM domain context), not for runtime separation. The "planner" in my single-agent setup is the agent's own reasoning loop — no supervisor agent needed because the LLM can plan across four well-organized tool domains without help.

### 8. MAST failure taxonomy — what I'm grading against

14 failure modes across 3 categories. The four most-cited in the ITBench analysis and the four I should design my system prompt to defend against:

- **FM-3.3 Incorrect Verification** — agent declares victory without checking ground truth (strongest predictor of failure across frontier models)
- **FM-2.6 Reasoning-Action Mismatch** — plan says X, action does Y
- **FM-1.5 Unaware of Termination** — agent loops or wanders
- **FM-1.4 Loss of Conversation History** — agent forgets mid-session

The eval table — rows for scenarios, columns for AgentCore Evaluations scores + MAST failure code for the failures — is my headline interview artifact. Built-in evaluators I'll enable: GoalSuccessRate, ToolSelectionAccuracy, ToolParameterAccuracy, Correctness, plus one custom LLM-as-judge for mitigation specificity. Judge model must be a different family from the agent model (don't grade your own homework).

## The architecture I can now draw from memory

Seven boxes top-to-bottom:

1. FIS injects one of four outage scenarios (AZ slowdown, EC2 stop, EBS pause-IO, network blackhole)
2. CloudWatch alarm fires on the resulting symptoms
3. SNS → Lambda invokes the agent
4. AgentCore Runtime (session-isolated microVM) runs the agent loop, with Memory (runbooks, topology) and Identity (JWT validation, credential vault) wrapping the auth on both sides
5. Agent calls tools through AgentCore Gateway (OAuth 2.1 + Cedar policy gate)
6. Gateway routes to four MCP namespaces (ecs-api, logs-api, metrics-api, runbooks-api), each backed by a Lambda with its own IAM scope
7. Tools hit the production AWS stack (ECS Fargate, ALB, Multi-AZ RDS, VPC with NAT, WAF, ACM)

Agent posts diagnosis to Slack. AgentCore Evaluations scores the trace; MAST classifies any failures. AgentCore Observability captures OpenTelemetry traces from every box, flowing to CloudWatch.

## What's deferred to Day 32

- Install the PreCommit secrets-scan hook and the PreToolUse `terraform apply` gate
- Mid-morning browser: AgentCore Runtime, Memory, Gateway, Identity developer guides (~2 hours)
- Afternoon (Claude Code primary): Terraform infrastructure hardening — second NAT gateway, second RDS replica, ACM certificate request, Route 53 records

Per the v3 decision doc, the pacing target is ~4 hours for infrastructure hardening instead of the v2-planned 8–10, with the freed time reallocated to Days 34 (agent design) and 35 (eval rigor).

## Optional: SSM Session Manager lab

Decision doc lists this as Day 31 hands-on. Pushing to Day 32 morning before the AgentCore docs read, since today's reading filled the time. Lab is: EC2 in private subnet, no inbound SSH, IAM role with `AmazonSSMManagedInstanceCore`, `aws ssm start-session --target i-xxx` for shell access.

## Reflection

Calibrated check at end of day: can I draw the architecture without looking? Yes. Can I name the four MCP namespaces and explain what each does? Yes. Can I explain the two-layer write gate (Cedar at Gateway + Slack approval) and why both? Yes. Can I name the four MAST failure codes and explain the eval table that's my interview artifact? Yes. Can I walk the aws-samples repo structure from memory? Yes — I read the structure today but didn't clone it yet (deferred to Day 32 since I have it in project memory).

Heavy day cognitively. Reading volume was substantial; the conceptual model-building was harder than the reading itself. The Q&A back-and-forth was where the actual learning happened — passive reading would have left me with a much shallower understanding of how Runtime, Identity, IAM, and Gateway compose. Confident going into Day 32.
