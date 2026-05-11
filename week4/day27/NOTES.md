# Day 27 — Portfolio Polish + Pipeline Debugging

**Plan vs reality.** Day 27 was meant to be the lighter review-and-summary day per the battle plan. Reality: spent the session overhauling the GitHub portfolio surface area, then three cascading pipeline failures from the restructure ate another 40 minutes. Ended with the Terraform VPC pipeline running green end-to-end for the first time — first complete PR → automated plan → human review → merge → apply flow.

---

## CI/CD conceptual review (skipped the test format)

Did this as back-and-forth Q&A instead of the 30-question assessment. The reframes that actually stuck:

**CI is not "the gate before merge."** CI is the system that gives every commit fast automated feedback. The pre-merge gate is a *consequence* of that system, not the system itself. Without continuous feedback, bugs accumulate silently between commits.

**Continuous Delivery ≠ Continuous Deployment.**
- Delivery: automated to "ready to ship," human clicks deploy. Most teams use this for prod.
- Deployment: no human in the loop. Most teams use this for non-prod.

**The human approval in CD isn't pure overhead.** CI already verified correctness. The human verifies *timing* — is now a good moment for change? Black Friday, stacked deploys, ongoing incidents. Different question, different surface. CI can't answer it. Mature teams handle 2am emergencies with a "break glass" fast-track path that bypasses approval but logs everything.

**Image tagging: `:latest` is a trap.** Three problems — no rollback (what does "previous" mean?), no traceability, cache poisoning across machines. Always tag with commit SHA. Task definitions reference specific SHAs so rollback = "deploy previous task definition revision" without ambiguity.

**ECS doesn't watch ECR.** Pushing an image to ECR is not a deploy. Something has to call `UpdateService` to tell ECS to look again. Two paths:
- Register new task definition revision with new image tag, then `UpdateService` → this is the right way
- `UpdateService --force-new-deployment` → works for `:latest` references, but fragile

**Container images are immutable.** Once `:abc123` is pushed, it can't be mutated. If a deploy fails, the bytes you pushed are exactly what's running — the bug is in the code or config inside the image, not in any "pointer."

---

## The four layers of an ECS deploy failure

When tasks fail health checks and ECS rolls back, the failure is in exactly *one* of these layers:

1. **Task can't start at all** — bad image reference, can't pull from ECR (task execution role missing perms), invalid task definition (CPU/memory combo not valid for Fargate), networking can't reach ECR (no NAT, no VPC endpoint)
2. **Container starts but crashes immediately** — missing env var, DB unreachable, command in Dockerfile wrong
3. **Container runs but fails health check** — wrong path, app slow to warm (grace period too short), dependency down
4. **Container healthy but ALB can't route** — security group blocking ALB→task port, target group health check path wrong, target group on wrong port

**30-second on-call debug order:**

1. ECS service → **Events tab** (plain-English narrative, resolves ~60% of cases — "Task failed ELB health checks", "CannotPullContainerError", "reached steady state")
2. Click into a **stopped task** → read **stop reason + exit code** (137 = OOM kill, 139 = segfault, 1 = generic app error, 0 = clean shutdown)
3. **CloudWatch Logs** for the task — application's own output (tracebacks, "DB refused", missing env)
4. **Target group** → Targets tab → health reason (502 = app returning error; "Connection timed out" = ALB can't reach the task at all)
5. **Task definition JSON** to verify what actually got registered (did the image tag substitute correctly in CI?)

Words that signal you've actually done this in an interview: events tab, stop reason, exit code, task execution role, target group health check, deployment circuit breaker.

**Task execution role vs task role** — two different IAM roles, easy to confuse. Execution role: what ECS itself uses to pull the image and write logs. Task role: what the application code inside the container uses to call AWS APIs. Image won't pull → execution role. App gets `AccessDenied` calling S3 → task role.

---

## Portfolio overhaul

### Profile-level fixes

The profile page at github.com/Dimi-DV was actively harmful — empty repos (`LLM_project`, `cloud-foundations-week1`) were surfacing as "Popular repositories" before recruiters saw any real work. Fixes:

- Pinned `devops-learning` and `Product-Review-Scraping-and-Analysis`
- Deleted empty repos
- Set bio: *"Cloud infrastructure engineer focused on AWS and AI-augmented operations. Building production-style infra with Terraform, containers, and CI/CD."*
- Set location
- Created profile README at `Dimi-DV/Dimi-DV` repo (GitHub auto-renders its README on the profile page)

### Repo-level fixes for `devops-learning`

- Replaced top-level README. Old framing ("DevOps Learning Journey — 42-day intensive bootcamp") was undoing the signal from the deeper project READMEs. New framing presents the repo as a project showcase with a Featured projects section linking to the strongest work.
- Cleaned `.gitignore` — had duplicated entries and a stray `EOF` line from a botched heredoc.
- Added README to `week3/day15/aws-vpc-terraform/` (none existed before, despite the code being one of the strongest artifacts).
- Rewrote `week4/day23/healthy-app/README.md` (was a copy of compose-app's, didn't reflect the ECS Fargate + CI/CD evolution).

### VPC project restructure

Top level had both a flat single-environment config (vpc.tf, routing.tf, nat.tf, security_groups.tf at root) AND the refactored module + environment callers. Confusing for a reader. Moved the flat files into `_initial-pass/`:

```bash
cd week3/day15/aws-vpc-terraform/
mkdir -p _initial-pass
mv vpc.tf routing.tf nat.tf security_groups.tf providers.tf variables.tf outputs.tf _initial-pass/
mv .terraform.lock.hcl _initial-pass/
```

Verified before running: day19's full-stack project sources `../../day15/aws-vpc-terraform/modules/vpc` — the module subdirectory, NOT the flat root files. So the restructure was safe for downstream consumers. `environments/dev/` and `environments/prod/` both reference `../../modules/vpc` too. Module path unchanged → no consumer broke.

### Workflow / secrets cleanup

- Moved AWS account ID to a repo Variable (`AWS_ACCOUNT_ID = 042729137214` under Settings → Secrets and variables → Actions → Variables tab — NOT Secrets, account IDs aren't credentials). Referenced as `${{ vars.AWS_ACCOUNT_ID }}` in both workflow files.
- Pruned stale remote branches:
  ```bash
  git fetch --prune  # refresh local view of what's actually on origin
  git push origin --delete <branchname> ...  # delete any that are still there
  ```
- TODO: enable "Automatically delete head branches" in repo settings so future PR merges clean up their branches without manual intervention.

---

## The cascade — three failures from one restructure

This was the painful part. Each fix revealed the next failure.

### Failure 1: "No configuration files" on `terraform apply`

Root cause: `terraform-vpc.yml` had `working-directory: week3/day15/aws-vpc-terraform` — which became empty of .tf files after moving them to `_initial-pass/`. The workflow was running `terraform init/plan/apply` in a directory with no Terraform config.

Fix:
- Pointed working-directory at `environments/dev/`
- Added a separate format-check step that overrides working-directory back to project root and runs `terraform fmt -check -recursive` so module formatting is still validated
- Tightened path filters to only fire on `modules/vpc/**`, `environments/dev/**`, or the workflow file itself

### Failure 2: 403 Forbidden on `terraform init`

Init successfully configured the S3 backend, then failed refreshing state with 403 on `HeadObject envs/dev/terraform.tfstate`.

Root cause: the IAM policy on `github-actions-terraform-vpc` granted S3 access to `dimitrije-tf-state-2026/vpc/*` only — scoped tight to the OLD flat config's state path. The new working directory uses backend key `envs/dev/terraform.tfstate`. Policy was doing exactly what least-privilege says it should, but didn't follow the restructure.

Fix — updated the inline policy:
```json
"Resource": [
  "arn:aws:s3:::dimitrije-tf-state-2026/envs/*"
]
```
Also split `ListBucket` (bucket-level action) into its own statement, separate from object-level `Get/Put/DeleteObject` — was technically mixed in the original and silently working but sloppy.

Applied via:
```bash
aws iam put-role-policy \
  --role-name github-actions-terraform-vpc \
  --policy-name terraform-vpc-permissions \
  --policy-document file://week4/day25/terraform-vpc-permissions-policy.json
```

(Run from repo root, or use absolute `$HOME/...` path. `file://` is just "read these bytes from disk" — AWS never sees the filename.)

Verified with:
```bash
aws iam get-role-policy \
  --role-name github-actions-terraform-vpc \
  --policy-name terraform-vpc-permissions \
  --query 'PolicyDocument.Statement[*].Resource'
```

### Failure 3: The pipeline didn't fire at all

Pushed a commit. No action ran. First reaction: panic. Actual cause: pushed `week4/day25/terraform-vpc-permissions-policy.json` (the docs copy of the policy). Path filter on the workflow correctly excluded this file — it's documentation, not infrastructure code, doesn't change what Terraform would do. Path filter doing its job, not broken.

Distinguish *workflow didn't run* from *workflow ran and failed* before assuming a problem.

Fix: committed an actual change to a watched path (added a header comment to `environments/dev/main.tf` documenting what the environment is for — useful change in its own right). PR triggered. Plan ran. Plan commented on PR. Status: green.

---

## What this cascade actually was

An apparently-simple reorganization touched three coupled surfaces — workflow path, IAM scope, trigger semantics — and each surfaced one at a time. This is the exact failure mode that hits production teams when they reorganize S3 layouts, rename IAM roles, or move state files. The 40 minutes spent debugging *is* the work that cloud support engineers do daily. Not a bug, the job.

---

## Deferred to Day 36

- **Branch protection on main** — Settings → Branches → require PR + status checks (Format and Validate, Plan (PR only), healthy-app CI jobs). The fact that direct pushes to main work right now is a hygiene issue; the experience of "pushed and nothing happened" makes it vivid why this rule exists.
- **Tier 4 extraction** — separate repos for `aws-vpc-terraform`, `aws-full-stack-terraform`, `flask-ecs-cicd`. Deferred because (a) capstone hasn't been built and final 6-pin strategy depends on it, and (b) extracting means redoing the GHA workflows we just spent the session fixing.
- **Capstone repo created from day one as its own repo**, not inside `devops-learning`. Decision locked.

---

## Lessons on the wall

1. **IAM policies are coupled to the structure of what they grant access to.** Restructuring underlying organization (state paths, S3 prefixes, role names) means policy follows. This is why least-privilege "feels brittle" — because it is, and that's the point. The policy is doing its job.
2. **Path filters do their job correctly.** "Action didn't fire" sometimes means "correctly ignored non-infrastructure commit." Distinguish *didn't run* from *ran and failed* before debugging.
3. **Production restructures cascade.** One change breaks N coupled systems and only surfaces them one at a time. Mature posture isn't "avoid cascades" (impossible) but "expect cascades, fix one at a time, document dependencies as found."
4. **Filename ≠ semantic name in AWS CLI.** `file://` arguments are just byte-stream reads from disk; AWS never sees the path. The policy *name* (`--policy-name`) is the semantic identifier in AWS.
5. **`git branch -r` is a local cache.** Branches deleted on origin don't disappear from local view until `git fetch --prune`. Auto-fix: enable "Automatically delete head branches" in repo settings.
6. **The good READMEs were doing real work.** The full-stack and compose-app READMEs were holding up the entire portfolio's signal density; the top-level README was undoing it. Framing at the entry point matters more than depth at the leaves.

---

## Final state

- Top-level README, profile README, profile metadata: all professional
- VPC project: own README, clean structure (`_initial-pass/`, `modules/vpc/`, `environments/dev/`, `environments/prod/`)
- healthy-app README: tells the full container journey (Compose → ECS Fargate → CI/CD)
- Terraform VPC pipeline: green end-to-end on first real run
- Empty/stub repos: removed from profile
- AWS account ID: in repo Variables, not hardcoded in workflows
- Stale branches: pruned

5 portfolio-quality READMEs, 1 cleaned `.gitignore`, 1 fixed workflow, 1 fixed IAM policy, 1 first end-to-end pipeline run. Day 28 is rest. Day 29 starts monitoring + SRE concepts.
