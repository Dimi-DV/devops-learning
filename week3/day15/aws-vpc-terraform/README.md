# Production VPC on AWS — Terraform Module

A production-pattern AWS VPC built as a reusable Terraform module with separate dev and prod environment callers. The module provisions a VPC with public and private subnets across two availability zones, an internet gateway, an optional NAT gateway, route tables, and baseline security groups with proper instance-to-instance referencing.

This project went through two passes: an initial flat-structure build (Days 15-16, kept under `_initial-pass/` for reference), then a refactor into a reusable module with multi-environment callers using `for_each`, `cidrsubnet()`, and conditional resources. The current deployable configuration is the module plus the environment callers.

---

## Architecture

```
                            Internet
                               │
                               ▼
                  ┌──────────────────────────┐
                  │   Internet Gateway       │
                  └─────────────┬────────────┘
                                │
                ┌───────────────┴───────────────┐
                │  VPC: 10.0.0.0/16             │
                │                               │
                │  ┌─────────────┐ ┌─────────────┐ │
                │  │ Public 1a   │ │ Public 1b   │ │
                │  │ 10.0.0.0/24 │ │ 10.0.1.0/24 │ │
                │  │ us-east-1a  │ │ us-east-1b  │ │
                │  └──────┬──────┘ └─────────────┘ │
                │         │                        │
                │         ▼  (NAT optional)        │
                │   ┌─────────────┐                │
                │   │ NAT Gateway │                │
                │   │ + Elastic IP│                │
                │   └──────┬──────┘                │
                │          │                       │
                │  ┌───────▼─────┐ ┌─────────────┐ │
                │  │ Private 1a  │ │ Private 1b  │ │
                │  │ 10.0.10.0/24│ │ 10.0.11.0/24│ │
                │  │ us-east-1a  │ │ us-east-1b  │ │
                │  └─────────────┘ └─────────────┘ │
                └───────────────────────────────────┘

Security groups:
  web-sg      — ingress 80/443 from 0.0.0.0/0, 22 from configured CIDRs
  private-sg  — ingress: all traffic from web-sg ONLY (SG-to-SG reference)
```

Subnet CIDRs are computed at runtime via `cidrsubnet(var.vpc_cidr, 8, idx)` for public and `cidrsubnet(var.vpc_cidr, 8, idx + 10)` for private, so changing `var.vpc_cidr` or adding AZs reslices the address space automatically.

---

## Repository structure

```
aws-vpc-terraform/
├── modules/
│   └── vpc/                     # the reusable module — current canonical version
│       ├── main.tf              # VPC, subnets, IGW, NAT, route tables, security groups
│       ├── variables.tf
│       └── outputs.tf
├── environments/
│   ├── dev/                     # dev environment caller
│   └── prod/                    # prod environment caller
├── _initial-pass/               # original Day 15-16 flat structure, kept for reference
└── README.md
```

---

## Prerequisites

- AWS account with credentials configured (`aws configure` or environment variables)
- Terraform 1.14+
- IAM principal with permissions to create VPC, subnet, route table, internet gateway, NAT gateway, EIP, and security group resources
- Remote state backend — this project uses an S3 bucket and a DynamoDB lock table. Replace the backend block in `environments/<env>/main.tf` with your own bucket and table before deploying.

---

## Deploy

```bash
cd environments/dev/
terraform init
terraform plan
terraform apply
```

The `prod` environment uses identical structure with a separate state file and (in real use) different CIDRs / availability zones.

---

## Verify

The module provisions networking only — no compute by default. To test end-to-end, launch two EC2 instances using the outputs and confirm the bastion pattern works:

```bash
# From environments/dev/ after apply
PUBLIC_SUBNET=$(terraform output -raw public_subnet_ids | jq -r '.[0]')
PRIVATE_SUBNET=$(terraform output -raw private_subnet_ids | jq -r '.[0]')

# Launch instances, SSH into the public one, then SSH-hop into the private,
# then `ping google.com` from the private to confirm NAT egress.
```

---

## Destroy

```bash
cd environments/dev/
terraform destroy
```

The NAT Gateway is the most expensive component (~$0.045/hr plus data processing). The module exposes `create_nat` (default `true`) so you can deploy without NAT for cheap testing where private subnet egress isn't needed.

---

## Cost estimate

| Resource | Cost (per environment) |
|---|---|
| VPC, subnets, route tables, IGW, security groups | $0 (free) |
| NAT Gateway | ~$33/month + $0.045/GB processed |
| Elastic IP (attached to NAT) | $0 |

**Without NAT (`create_nat = false`):** essentially $0/month. The networking primitives cost nothing to leave running.

**With NAT (default):** ~$35/month per environment if left running 24/7. Deploy → test → destroy keeps actual spend at pennies per session.

---

## Design decisions

### Module + environment structure over a single flat configuration

The flat structure works fine for one VPC in one account. The moment you need a second environment, or a second app in the same account, the flat structure forces copy-paste duplication of every resource block. The module pattern lets each environment caller be ten lines — CIDR, AZs, project name, NAT toggle — and the module handles the rest. This is how teams organize Terraform once they're past the prototype stage.

### `cidrsubnet()` over hard-coded subnet CIDRs

The initial flat configuration hard-coded `10.0.1.0/24`, `10.0.2.0/24`, and so on as variable defaults. The module derives subnet CIDRs from the VPC CIDR via `cidrsubnet(var.vpc_cidr, 8, each.value)`. Two consequences: subnets always nest correctly inside the VPC even when the VPC CIDR changes, and adding a third AZ requires only appending the AZ name to the list — the new subnet CIDR computes automatically. No more "what's the next available /24" arithmetic.

### `for_each` over numbered resource blocks

The flat structure declared `aws_subnet.public_1a` and `aws_subnet.public_1b` as separate resources. The module uses `for_each` over the AZ list, producing `aws_subnet.public["us-east-1a"]` and `aws_subnet.public["us-east-1b"]` from a single block. Adding a third AZ is a one-line variable change. Removing one is also a one-line change, and Terraform plans the removal cleanly because the resource keys are based on AZ names, not list positions (which would cause cascading shifts).

### Conditional NAT via `count`

The NAT Gateway, its Elastic IP, and the private route's NAT target are all gated on `var.create_nat ? 1 : 0`. NAT is the expensive part of a VPC, and most testing doesn't need outbound internet from private subnets. Making it optional keeps the module deployable cheaply while keeping the production path one variable away.

### Private security group references web-sg by ID, not by CIDR

`private_sg` allows ingress from `security_groups = [aws_security_group.web.id]` rather than from the public subnet CIDR. This is the better pattern because the rule expresses the actual security intent ("only public-tier instances can reach private-tier instances") and remains correct even if the underlying CIDRs change. SG-to-SG references are the AWS-recommended pattern for any tiered architecture.

### Single NAT Gateway rather than one per AZ

The current module places one NAT Gateway in the first public subnet. Production deployments would create one NAT per AZ so an AZ outage doesn't cut off the other AZ's private subnets from the internet. The single-NAT version is a deliberate cost choice for this learning project; the production gap is listed below.

---

## Known limitations and production improvements

- **Single NAT Gateway.** Production should provision one NAT per AZ. Currently if `us-east-1a` has an outage, private instances in `us-east-1b` lose internet access because their NAT route points at the NAT in `us-east-1a`.
- **No VPC endpoints.** Production VPCs typically have S3 and DynamoDB gateway endpoints (free) and interface endpoints for STS, ECR, CloudWatch Logs, Secrets Manager, and so on — for both cost savings (no NAT data charges for AWS API calls) and security (traffic stays inside the AWS network).
- **No flow logs.** Production VPCs enable VPC Flow Logs to CloudWatch or S3 for network forensics and intrusion detection.
- **`web-sg` allows SSH from configured CIDRs.** Production should use Session Manager (no SSH ports open at all) with the SSM agent and an IAM role granting `AmazonSSMManagedInstanceCore`.
- **Default route table not managed.** The module creates explicit public and private route tables. The VPC's default route table is left unused. A locked-down production posture would explicitly empty the default route table (or use `aws_default_route_table` to manage it) so no resource accidentally inherits unintended routing.
- **No NACLs.** The module relies on security groups (stateful) for traffic control. Production may add NACLs (stateless, subnet-level) as a second defense layer.

---

## What this project demonstrates

For a junior cloud / DevOps role, this project shows fluency with:

- **VPC architecture from primitives** — VPC, subnets, route tables, IGW, NAT, EIP, route table associations, security groups
- **Terraform module design** — separating reusable infrastructure (the module) from environment-specific configuration (the callers)
- **Multi-environment patterns** — `environments/dev/` and `environments/prod/` with separate state and parameterized inputs
- **Advanced HCL features** — `for_each` over collections, `count` for conditional resources, `cidrsubnet()` for derived CIDRs, data sources, locals, output composition
- **Security group composition** — SG-to-SG references instead of CIDR references, descriptions on every rule
- **Cost-conscious infrastructure design** — making NAT optional, documenting per-resource costs, building toward production posture without paying production rates during development
