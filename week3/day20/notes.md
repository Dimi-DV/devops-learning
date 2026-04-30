# Day 20 — Week 3 Consolidation: State Manipulation Deep Dive

## Summary

Day 20 was the Week 3 consolidation day. Started with a 30-question Terraform assessment that exposed a major gap around state manipulation commands — these had not been covered in depth during Days 15–19. Pivoted the rest of the day into a hands-on lab covering every state operation that matters in production, from `terraform import` through `apply -replace`.

Conceptual breakthroughs around the three-way relationship between config, state, and AWS reality made every subsequent command click. The phrase that landed: **"state is a middleman between config and reality — config never talks to AWS directly."**

---

## Week 3 Assessment Results

Score: 16.25 / 30 (54%)

The raw score underrepresented conceptual understanding. Strong on architecture, lifecycle, providers, dynamic blocks, and `for_each` concepts. Weak on:

- State manipulation commands (Q6, Q9, Q10 — the major gap)
- `for_each` syntax cold without docs (Q17)
- Conditional resource pattern with ternary (Q20)
- Variable precedence order (Q24)
- `cidrsubnet()` semantics (Q18)

Decision: skip moving to Week 4 prep and use the rest of the day to close the most important gap — state manipulation — through hands-on lab work.

---

## The Mental Model (The Most Important Takeaway)

Every Terraform operation moves information between three things:

1. **Config** (`.tf` files) — what I want
2. **State** (`.tfstate` in S3 backend) — what Terraform thinks it manages
3. **Reality** (AWS) — what actually exists

The provider plugin (downloaded by `terraform init`) is the only thing that talks to AWS. **Config never communicates with AWS directly.** State is the ledger that records what was built and its attributes — it doesn't translate, execute, or transform anything. It's just JSON.

### What `terraform plan` actually does

Three steps in order:
1. Load config
2. Read state (from S3 backend)
3. Refresh state against AWS (in memory only — disk state isn't modified during plan)
4. Compare refreshed state ↔ config and produce the diff

Two comparisons happen on every plan: AWS ↔ state (refresh) → state ↔ config (the visible plan output).

### What `terraform apply` actually does

1. Acquire DynamoDB lock
2. Re-run plan internally
3. Provider makes AWS API calls (create/update/delete)
4. After each successful API call, write new attributes to state
5. Write final state back to S3
6. Release lock

Apply is the only command that writes to the on-disk state file in normal usage (with the explicit exceptions of state subcommands and `apply -refresh-only`).

---

## Commands Covered (Organized by What They Touch)

### Reading state — no mutations

| Command | Purpose |
|---|---|
| `terraform state list` | Show all tracked resource addresses |
| `terraform state show <addr>` | Show one resource's full attributes from state |
| `terraform plan -refresh-only` | Show drift between state and reality, change nothing |
| `terraform state pull` | Dump raw state JSON for backup or inspection |

### Mutating state only — no AWS API calls

| Command | Purpose | Real-world use case |
|---|---|---|
| `terraform import <addr> <id>` | Add ledger entry for existing AWS resource | Joining a team with manual infra |
| `import {}` block | Declarative version of import | PR-driven imports, CI/CD compatible |
| `terraform state rm <addr>` | Remove ledger entry, AWS untouched | Cross-repo transfer, stop managing |
| `terraform state mv <src> <dst>` | Rename ledger entry | Refactoring within a codebase |
| `moved {}` block | Declarative version of state mv | Reviewable refactors via PR |
| `terraform apply -refresh-only` | Pull drift from reality into state | Audit/accept manual changes |

### Mutating reality — real AWS API calls

| Command | Purpose |
|---|---|
| `terraform apply` | Normal config-driven changes |
| `terraform apply -replace=<addr>` | Force destroy + recreate of one resource |
| `terraform destroy` | Destroy everything in state |

---

## The Five-Step Import Workflow

This is the answer to "how do you bring existing AWS infrastructure under Terraform management":

1. Write a stub resource block (just enough so Terraform has an address to bind)
2. Run `terraform import <addr> <id>` to write the ledger entry
3. Run `terraform plan` to read drift between empty config and reality
4. Fill in config to match what import discovered
5. Run `terraform plan` again — confirm "no changes" before any apply

Same loop for any resource type. S3 was the lab example because S3 IDs equal bucket names, but for most resources the address (Terraform name) and AWS ID look completely different (e.g., `aws_instance.web` ↔ `i-0abc123def456`).

---

## `state rm` — Stop Managing Without Destroying

The most counterintuitive command and the one most commonly misunderstood. **It does NOT delete the AWS resource.** It only removes the entry from state.

Use cases:
- Splitting a monorepo into team-owned repos
- Transferring resource ownership to another codebase
- Resource type migration (deprecated → new resource type)
- Spinning a resource out before `terraform destroy`

Verified hands-on: `state rm`'d the imported bucket, ran `aws s3 ls` — bucket still existed in AWS. Subsequent `terraform plan` showed "+ create" because state forgot the bucket exists, even though reality still has it.

---

## `state mv` and `moved` Blocks — Refactoring Without Downtime

The command that prevents production data loss during refactors.

### The disaster scenario

Renaming `aws_s3_bucket.managed` to `aws_s3_bucket.primary` in code without state operations produces:

```
Plan: 1 to add, 0 to change, 1 to destroy.
```

For an S3 bucket with data or an RDS database with 500 GB of customer data, this is catastrophic.

### CLI fix

```bash
terraform state mv aws_s3_bucket.managed aws_s3_bucket.primary
```

Zero AWS API calls. Plan immediately shows "No changes." Bucket creation timestamp in AWS unchanged.

### Modern declarative fix (`moved` block, Terraform 1.1+)

```hcl
moved {
  from = aws_s3_bucket.primary
  to   = aws_s3_bucket.managed
}
```

Add to config, commit through PR, run apply. Plan output shows the rename:
```
# aws_s3_bucket.primary has moved to aws_s3_bucket.managed
Plan: 0 to add, 0 to change, 0 to destroy.
```

Why `moved` blocks beat CLI `state mv` for team work:
- Visible in plan output, reviewable in PRs
- Works in CI/CD without coordination
- No state mutation outside of normal apply
- Audit trail in git history

---

## `create_before_destroy` vs `state mv` — Critical Distinction

These solve fundamentally different problems:

| | `create_before_destroy` | `state mv` |
|---|---|---|
| AWS API calls? | Yes — real replacement | No — ledger only |
| Resource ID in AWS | Changes (new resource) | Stays the same |
| Data preservation | Lost (or requires migration) | Preserved (same physical resource) |
| Use case | Legitimate replacement, smoother rollover | Avoid replacement entirely |

`create_before_destroy` is for when something IS being replaced and you want to minimize the gap. `state mv` is for when something only LOOKS like a replacement (just a code rename) and shouldn't actually be replaced.

For refactoring a database into a module: `state mv` only. `create_before_destroy` would create a new empty database and destroy the original with all data. For S3 buckets, `create_before_destroy` doesn't even work — globally unique bucket names cause `BucketAlreadyOwnedByYou` errors.

---

## `apply -refresh-only` — Audit and Drift Acceptance

`terraform plan -refresh-only` is the audit tool — shows drift, changes nothing.

`terraform apply -refresh-only` writes the drift into state. Does NOT update config. So after running it, regular plan still wants to revert the drift unless config is also updated.

Honest assessment after pushback: for simple cases where you know what drifted, just edit config and run regular apply. Refresh-only is for niche cases:
- Resource was deleted in AWS and you want state to reflect that
- Schema migration mid-flight
- Pipeline-driven scheduled drift reconciliation
- Auditing what changed without committing anything (use `plan -refresh-only`)

`terraform refresh` (without `apply -`) is fully deprecated — it mutated state silently without showing a diff.

---

## `apply -replace` — Forced Recreation

The modern replacement for `terraform taint` (deprecated in 0.15.2).

Syntax:
```bash
terraform apply -replace=aws_s3_bucket.managed
```

Plan output annotation: `will be replaced, as requested` — Terraform telling you the replacement is from the flag, not from drift or config change.

Real-world use cases:
- Stuck EC2 instance that won't respond
- Container in ECS task is wedged
- Bad user data deployment, want to force re-bootstrap
- Cert/secret rotation when content changes don't trigger replacement
- Test recovery procedures

Verified hands-on: bucket creation timestamp in AWS updated from 15:31:44 to 17:47:28 — proof it was actually destroyed and recreated, not just relabeled.

Safety habits:
1. Always run `plan -replace=...` first
2. One resource at a time
3. Think twice for stateful resources (databases, EBS, buckets with data)
4. In CI/CD, gate behind manual approval

---

## Timestamp Diagnostic Pattern

AWS resource creation timestamps reveal which category of operation touched a resource:

| Category | Examples | AWS timestamp behavior |
|---|---|---|
| Pure state ops | `state rm`, `state mv`, `import`, `apply -refresh-only` | Unchanged — no AWS API calls |
| Real config changes | `apply` (when config differs) | Updated only when replacement required |
| Forced replacement | `apply -replace`, lifecycle replacement | Always updated — full destroy + create |

Useful debugging skill — read AWS timestamps to verify what category of operation actually happened.

---

## CLI vs Declarative — Where Things Are Heading

Terraform has been moving from imperative CLI commands to declarative blocks for state operations:

| Operation | Old way (CLI) | Modern way (declarative) |
|---|---|---|
| Bring existing resource under management | `terraform import` | `import {}` block (1.5+) |
| Rename or relocate a resource | `terraform state mv` | `moved {}` block (1.1+) |
| Stop managing a resource | `terraform state rm` | No declarative equivalent — still CLI |
| Force recreation | `terraform taint` (deprecated) | `terraform apply -replace=...` |

Declarative versions win for team work because they're reviewable, CI/CD-compatible, and visible in plan output.

For interviews: "I use the CLI for one-off exploration, but for any state operation that goes through code review I use declarative blocks — they're auditable and play nicely with pipelines."

---

## Common Interview Questions This Lab Prepares For

1. **"How do you bring existing AWS infrastructure under Terraform management?"** → Five-step import workflow.
2. **"What's the difference between `terraform state rm` and `terraform destroy`?"** → State rm only removes the ledger entry; destroy deletes the actual AWS resource.
3. **"How would you refactor a resource into a module without destroying it?"** → `terraform state mv` or `moved {}` block.
4. **"When would you use `create_before_destroy` vs `state mv`?"** → Replacement vs avoiding replacement.
5. **"You discovered drift in production. Walk me through your options."** → plan-refresh-only to audit, then either revert (regular apply), accept into state (refresh-only + config update), or accept into config (just edit and apply).
6. **"An EC2 instance is stuck. How do you force Terraform to recreate it?"** → `apply -replace=<addr>`.
7. **"What's in a Terraform state file?"** → Resource address-to-AWS-ID mapping, current attribute values, dependencies. JSON file. Stored remotely in S3 with DynamoDB locking.

---

## Lab Environment Used

- VS Code SSH to Ubuntu VM on Mac M2
- Working directory: `~/devops-learning/week3/day20/state-lab/`
- Backend: S3 bucket `dimitrije-tf-state-2026`, key `state-lab/terraform.tfstate`
- DynamoDB lock table: `terraform-locks`
- Region: us-east-1
- Lab bucket names:
  - `dimitrije-state-lab-managed-2026` (managed by Terraform)
  - `dimitrije-state-lab-imported-2026` (created via CLI, imported, then state rm'd)

---

## Cleanup

- `terraform destroy` removed the `managed` bucket
- `aws s3 rb s3://dimitrije-state-lab-imported-2026` removed the imported bucket manually (Terraform wasn't tracking it)
- State file at `s3://dimitrije-tf-state-2026/state-lab/terraform.tfstate` left in place as record of the lab

---

## Gaps Still Open from Week 3 Assessment

State manipulation gap: closed.

Remaining gaps to revisit:
- `for_each` syntax cold without docs (Q17) — practice by rewriting Day 17 VPC module subnet block from blank
- Conditional resource pattern: `count = bool ? 1 : 0` (Q20)
- Variable precedence order: CLI flag > auto.tfvars > tfvars > env var > default (Q24)
- `cidrsubnet()` semantics: third arg is network number, returns `10.0.<n>.0/24` for /16 + 8 (Q18)
- NAT Gateway placement (lives in public subnet, allows outbound only)

---

## What's Next

- Day 21: rest day
- Day 22: Docker fundamentals (Week 4 starts)
- Postponed from Day 20: SAA practice exam #2, Week 3 summary, portfolio polish — pick these up before Day 22
