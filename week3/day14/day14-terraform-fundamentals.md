# Day 15 — Terraform Fundamentals

## What is Infrastructure as Code (IaC)?

Writing code that describes your infrastructure instead of clicking through the AWS Console. Benefits: reproducible, version-controlled, reviewable, and automatable. Terraform is the most popular IaC tool (by HashiCorp), used across AWS, Azure, GCP, and hundreds of other providers.

**Terraform vs Console**: Console is imperative and manual. Terraform is declarative — you describe *what* you want, it figures out *how*.

**Terraform vs CloudFormation**: CloudFormation is AWS-only, uses JSON/YAML. Terraform is multi-cloud, uses HCL (HashiCorp Configuration Language).

## HCL Syntax — Block Types

Every `.tf` file is built from blocks:

```
block_type "label1" "label2" {
  argument = value
}
```

| Block Type | Purpose | Reference Pattern |
|---|---|---|
| `resource` | Creates infrastructure | `aws_s3_bucket.my_bucket.arn` |
| `provider` | Configures which cloud to talk to | N/A |
| `variable` | Input parameters (from outside) | `var.environment` |
| `output` | Values printed after apply | N/A |
| `data` | Reads existing info (doesn't create) | `data.aws_caller_identity.current.account_id` |
| `locals` | Computed internal values | `local.bucket_name` (singular!) |
| `terraform` | Settings: provider versions, backend | N/A |

## Key Concept: Terraform Merges All .tf Files

Terraform reads **every `.tf` file in the current directory** as one configuration. No imports, no includes, no file ordering. `main.tf`, `variables.tf`, `outputs.tf` are just naming conventions for humans.

This is fundamentally different from Python where each file is a separate module requiring explicit imports.

## The Data Flow

```
variables (user-provided inputs)
    ↓
data sources (queried from AWS)
    ↓
locals (computed from variables + data sources)
    ↓
resources (create infrastructure using all of the above)
    ↓
outputs (expose resource attributes after apply)
```

### Variables — Inputs from outside your code

```hcl
variable "environment" {
  type        = string
  default     = "dev"
  description = "Environment name"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}
```

**Who controls the value**: the person running Terraform, not the code.

**Input precedence** (lowest to highest): default in variable block → `terraform.tfvars` file → `-var` CLI flag.

If no default and no value provided, Terraform prompts interactively. Variables are resolved before anything else happens.

### Data Sources — Read existing info from AWS

```hcl
data "aws_caller_identity" "current" {}
# Use: data.aws_caller_identity.current.account_id
```

Doesn't create anything. Just queries. Like running `aws sts get-caller-identity` but making the result available in your config.

### Locals — Computed internal values

```hcl
locals {
  bucket_name = "dimitrije-${var.project_name}-2026"
  common_tags = {
    Environment = var.environment
    ManagedBy   = "terraform"
    AccountId   = data.aws_caller_identity.current.account_id
  }
}
```

**Who controls the value**: the code itself. Nobody outside can set a local.

Use locals to avoid repeating yourself — define a tag map once, reference `local.common_tags` everywhere. String interpolation `${}` works like Python f-strings.

### Resources — Create infrastructure

```hcl
resource "aws_s3_bucket" "first_bucket" {
  bucket = local.bucket_name
  tags   = local.common_tags
}
```

References like `aws_s3_bucket.first_bucket.id` create implicit dependencies — Terraform builds the dependency graph automatically.

### Outputs — Expose values after apply

```hcl
output "bucket_arn" {
  value       = aws_s3_bucket.first_bucket.arn
  description = "ARN of the S3 bucket"
}
```

Printed to terminal after every apply. Also how modules share data (covered in Day 17).

## The Core Workflow

1. **`terraform init`** — Downloads provider plugins. Run once per project or when backend/providers change. Like `pip install`.
2. **`terraform plan`** — Preview changes. Compares code vs state vs reality. **Read every line.**
3. **`terraform apply`** — Execute the plan. Makes real AWS API calls. Type `yes` to confirm.
4. **`terraform destroy`** — Tear everything down. Reverses all creates.

### Reading Plans — Symbols

| Symbol | Meaning |
|---|---|
| `+` | Create |
| `~` | Update in-place |
| `-/+` | Destroy and recreate (replacement) |
| `-` | Destroy |

**`# forces replacement`** — appears when a change requires destroying and recreating (e.g., renaming an S3 bucket). This is a critical flag to watch for in production.

**`(known after apply)`** — value that AWS assigns at creation time (ARN, ID, etc.). Can't be predicted.

## State — Terraform's Memory

`terraform.tfstate` is a JSON file mapping your code to real AWS resources. It records what Terraform built, so it knows what changed, what to update, and what to destroy.

**Critical rules:**
- Losing state = Terraform forgets your infrastructure (resources still exist in AWS, just unmanaged)
- State can contain secrets — **never commit to Git**
- Two people with different local state = chaos

## Remote State — S3 + DynamoDB

Solves the local state problems by storing state in a shared, locked location.

**S3** stores the state file. **DynamoDB** provides locking so only one person can modify at a time.

### Setup (chicken-and-egg: create these manually first)

```bash
# Create state bucket
aws s3api create-bucket --bucket dimitrije-tf-state-2026 --region us-east-1

# Create lock table
aws dynamodb create-table \
  --table-name terraform-locks \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region us-east-1
```

### Backend configuration in Terraform

```hcl
terraform {
  backend "s3" {
    bucket         = "dimitrije-tf-state-2026"
    key            = "terraform-basics/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

Each project uses a unique `key` path. After adding backend, run `terraform init` to migrate.

## .gitignore for Terraform

```
*.tfstate
*.tfstate.backup
.terraform/
*.tfvars
crash.log
```

**DO commit**: `.tf` files, `.terraform.lock.hcl` (locks provider versions)
**DON'T commit**: state files, `.terraform/` directory, tfvars (may contain secrets)

## File Organization Convention

```
project/
├── main.tf          # Provider, resources, data sources, locals
├── variables.tf     # All variable declarations
├── outputs.tf       # All output declarations
├── terraform.tfvars # Variable values (don't commit if sensitive)
└── .terraform.lock.hcl  # Provider version lock (commit this)
```

## Commands Reference

```bash
terraform init                    # Initialize, download providers
terraform plan                    # Preview changes
terraform apply                   # Apply changes
terraform destroy                 # Destroy all resources
terraform plan -var="key=value"   # Override a variable
terraform fmt                     # Auto-format .tf files
terraform validate                # Check syntax without calling AWS
```

## Environment Details

- **Terraform**: v1.14.7 installed on Linux VM (Ubuntu/UTM)
- **AWS Provider**: hashicorp/aws v5.100.0
- **Remote State Bucket**: `dimitrije-tf-state-2026`
- **Lock Table**: `terraform-locks` (DynamoDB, PAY_PER_REQUEST)
- **Region**: us-east-1
