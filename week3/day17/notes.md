# Day 17 — Terraform Modules + Advanced Patterns

## What I built

Refactored the single-directory VPC project from Day 15–16 into a reusable module
with per-environment callers. Same infrastructure shape, but the code can now
produce dev and prod (and staging, eventually) from one module.

### Directory structure

week3/day15/aws-vpc-terraform/
├── modules/vpc/          # the reusable module
│   ├── main.tf           # resources (VPC, subnets, IGW, NAT, route tables, SGs)
│   ├── variables.tf      # inputs the caller must provide
│   └── outputs.tf        # values the caller can reference
└── environments/
├── dev/              # calls module with 10.0.0.0/16, no NAT
│   ├── main.tf
│   └── outputs.tf
└── prod/             # calls module with 10.1.0.0/16, NAT enabled
├── main.tf
└── outputs.tf

## Concepts learned

### Modules (Hour 1–3)
- A module is just a folder of .tf files that takes inputs (variables), produces
  outputs, and can be called from somewhere else. Like a function.
- The `module "name" { source = "..." }` block is the "function call."
  Arguments passed in must match variables declared in the module.
- Outputs are how a module exposes values to its caller. Without `output "x"`,
  the caller cannot access resources inside the module.
- Backend config and provider config live at the CALLER, not inside the module.
  Modules inherit providers. Each caller has its own state file.
- Per-environment state isolation: different `key` in the same S3 bucket
  (e.g., `envs/dev/terraform.tfstate` vs `envs/prod/terraform.tfstate`).
  This is what keeps dev and prod from stepping on each other.

### Overlap & collision layers
Terraform does NOT make overlap physically impossible. Discipline required:
1. State file isolation — different backend keys per env
2. Resource naming — compose from `${var.project_name}-${var.environment}-*`,
   never hardcode inside a module
3. AWS uniqueness — S3 buckets, IAM roles, etc. must prefix with env_name
4. CIDR non-overlap — convention (dev=10.0/16, prod=10.1/16) prevents future
   peering problems
5. Backend state key collision — wrong key = "apply wants to destroy 40 resources"
   is how people delete prod

### Functions, loops, conditionals (Hour 4)
- `cidrsubnet(prefix, newbits, netnum)` — slices a parent CIDR into subnets.
  Caller passes `vpc_cidr = "10.0.0.0/16"` once; module derives all subnet ranges.
- `for_each = { for idx, az in var.availability_zones : az => idx }` —
  converts a list into a map keyed by AZ name, valued by index. Iterating over
  this map creates one resource per AZ.
- `each.key` = the map key for this iteration; `each.value` = the value.
  Resource addresses become `aws_subnet.public["us-east-1a"]` — the bracketed
  key in state.
- `count = var.create_nat ? 1 : 0` — the conditional resource pattern. When
  count=0, resource doesn't exist. When count=1, address becomes `aws_eip.nat[0]`.
- `for_each` vs `count`: `for_each` uses stable keys (removing one doesn't shift
  the others); `count` uses numeric indices (removing middle item shifts
  everything after it, causing destroy-recreate).
- List comprehension: `[for s in aws_subnet.public : s.id]` — extracts IDs
  from a `for_each`-created map as a flat list for outputs.

### Design principles internalized
- Required inputs have NO defaults in reusable modules — forces explicit
  decision per caller, prevents silent CIDR overlap.
- Modules should absorb complexity; callers should stay simple.
  AZ-driven design (derive subnets from AZs) beats subnet-driven design
  (hand-list every subnet) for standard VPCs.
- Make invalid configurations unrepresentable. A module that can't express
  an asymmetric network is a feature, not a limitation.

## Bugs hit and how they resolved
- **Name vs name**: global find-replace of `Name = "${var.project_name}-"` also
  matched the top-level `name` attribute on `aws_security_group`. Lowercase `name`
  is the AWS API field; capital `Name` is only valid inside `tags {}`. Fix: one
  lowercase replacement in each SG block.
- **Empty outputs.tf**: `cp` appeared to run but left a 0-byte file. Plan failed
  with "module.vpc does not have attribute vpc_id" because the module literally
  declared no outputs. Lesson: outputs are how modules expose internals. No
  output, no access.
- **Missing [0] index after adding count**: when adding `count` to a resource,
  every other reference to it breaks until updated to bracket-index. Terraform
  surfaces these one error at a time — fix each and re-plan.
- **Two simultaneous `terraform init` processes**: caused a deadlock, not a
  download hang. Always use `ps aux` to check before assuming network issues.

## Verification workflow (the real-world pattern)
1. Write module code
2. Write caller in `environments/dev/main.tf`
3. `terraform init` in the environment dir (not the module dir)
4. `terraform plan` — read output carefully, verify resource count, tags, CIDRs
5. Only `apply` when the plan is what you expect
6. `destroy` when done to stop NAT Gateway charges

Prod was never applied today — plan output alone proves the module is reusable.

## State at end of day
- `week3/day17` branch with all changes
- Module in `modules/vpc/` with 5 required variables + 1 optional (`create_nat`)
- `environments/dev/` configured (applied once earlier, then destroyed)
- `environments/prod/` configured but NEVER applied (plan-only proof)
- No AWS resources currently running from this work

## Open items for Day 18+
- `terraform state mv` — the CLI command for refactoring resource addresses
  without destroy/recreate. Interview-relevant. Mentioned today, not practiced.
- `templatefile()` for user_data — listed in Hour 4 plan, not needed since we
  didn't touch EC2 today. Covered when we add EC2 resources later.
- Terraform Associate quiz — deferred from Hour 6–7, do during Day 20 review.