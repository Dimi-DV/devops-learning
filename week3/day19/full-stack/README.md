# Production-Pattern Web Stack on AWS — Terraform

A fully-deployed, highly-available web application infrastructure built end-to-end with Terraform. The stack provisions a VPC (via a reusable module), an Application Load Balancer fronting an Auto Scaling Group of EC2 instances across two availability zones, with IAM roles, S3 access logging, and CloudWatch monitoring wired throughout.

This project demonstrates the canonical "production web app" pattern that underpins most AWS-hosted web services: high availability via multi-AZ deployment, self-healing via Auto Scaling, defense-in-depth via security group chaining, and operational visibility via centralized logs and alerts.

---

## Architecture

```
                            Internet
                               │
                               ▼
                    ┌──────────────────────┐
                    │  ALB (public-facing) │
                    │  alb-sg: :80 from    │
                    │  0.0.0.0/0           │
                    └──────────┬───────────┘
                               │ Forward to target group
                               ▼
        ┌──────────────────────────────────────────┐
        │         Target Group (HTTP :80)          │
        │   Health check: GET /, expects 200       │
        └──────────────────────────────────────────┘
                               │
                ┌──────────────┴──────────────┐
                ▼                             ▼
         ┌─────────────┐              ┌─────────────┐
         │   EC2       │              │   EC2       │
         │  (us-east-  │              │  (us-east-  │
         │   1a)       │              │   1b)       │
         │             │              │             │
         │ instance-sg │              │ instance-sg │
         │ :80 from    │              │ :80 from    │
         │ alb-sg ONLY │              │ alb-sg ONLY │
         └──────┬──────┘              └──────┬──────┘
                │ IAM role (CloudWatch Logs write)
                │ User data: nginx + instance ID page
                ▼                             ▼
                ASG (min: 2, max: 4, desired: 2)
                Health check: ELB
                ▼
        Replaces failed instances automatically

Side channels:
        ALB → S3 bucket (access logs, versioned, encrypted)
        CloudWatch alarm (UnHealthyHostCount > 0) → SNS → email
```

### Traffic flow

1. Client requests reach the ALB on port 80 from the public internet.
2. The ALB forwards to the target group, which load-balances across registered ASG instances.
3. Each instance has the instance security group attached, which only allows port 80 traffic from sources tagged with the ALB security group. Direct internet access to the instances is blocked.
4. nginx on each instance serves a page identifying the instance ID and AZ.
5. ALB writes an access log entry for every request to the S3 logs bucket.
6. CloudWatch monitors `UnHealthyHostCount`. If any host is unhealthy for two consecutive minute-long evaluation periods, SNS fires an email to the configured address.

---

## Component breakdown

### Networking — VPC module

Reuses the VPC module at `../../day15/aws-vpc-terraform/modules/vpc/`. The Day 19 root config calls the module with `create_nat = false` because instances run in public subnets for direct internet access during the lab.

The module creates:
- VPC with CIDR `10.10.0.0/16`
- Two public subnets (`10.10.0.0/24`, `10.10.1.0/24`) in `us-east-1a`/`us-east-1b`
- Two private subnets (`10.10.10.0/24`, `10.10.11.0/24`) — created but unused in this lab
- Internet Gateway with public route table
- Two security groups (`web` and `private`) — also created but not used by the Day 19 stack, which defines its own purpose-built SGs

### Load balancing — ALB

- `aws_lb.main` — Application Load Balancer in both public subnets, `internal = false`
- `aws_lb_target_group.app` — HTTP/80, health checks every 30 seconds against `/`
- `aws_lb_listener.http` — port 80 listener, forwards to the target group as default action
- Access logging enabled, writing to the dedicated S3 bucket

### Compute — Launch template + ASG

- `aws_launch_template.app` — Amazon Linux 2023 (looked up via `data.aws_ami` with `most_recent = true`), `t3.micro`, instance security group + IAM instance profile attached, user data installs nginx and writes a page showing the EC2 instance ID and AZ
- `aws_autoscaling_group.app` — min 2, max 4, desired 2; ELB health check type so application-level failures (not just OS) trigger replacement; 60-second grace period to allow nginx to install before health-checking
- `lifecycle { create_before_destroy = true }` on the launch template so changes don't strand the ASG with a deleted template reference

### Security groups

Two purpose-built SGs replace the more general-purpose SGs the VPC module provides:

- `aws_security_group.alb` — accepts port 80 from `0.0.0.0/0`. The only public-facing entry point.
- `aws_security_group.instance` — accepts port 80 **only from instances with the ALB SG attached** (via `security_groups = [aws_security_group.alb.id]`, not a CIDR). Also allows SSH from configured CIDRs for debugging.

This SG-to-SG reference pattern is the cleanest way to express "only the load balancer can reach my instances" — IP-based CIDRs would break if the ALB's IPs changed.

### IAM

- `aws_iam_role.app_role` — trust policy allows EC2 to assume it
- `aws_iam_policy.cloudwatch_write` — allows `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents`
- `aws_iam_role_policy_attachment.app_cloudwatch` — glues policy to role
- `aws_iam_instance_profile.app` — wraps the role for EC2 attachment via the launch template

All policy documents are written using the `aws_iam_policy_document` data source for type-checked HCL syntax rather than embedded JSON.

### S3 — ALB access logs

- `aws_s3_bucket.alb_logs` — globally unique bucket name with `force_destroy = true` for clean lab teardown
- `aws_s3_bucket_versioning` — versioning enabled (separate resource per AWS provider v4+ convention)
- `aws_s3_bucket_server_side_encryption_configuration` — SSE-S3 (AES-256)
- `aws_s3_bucket_policy.alb_logs` — grants the regional ELB service account permission to write objects, looked up dynamically via `data.aws_elb_service_account.main` so the policy is portable across regions

### Monitoring — CloudWatch + SNS

- `aws_cloudwatch_metric_alarm.unhealthy_host` — watches `UnHealthyHostCount` on the target group, fires when `Maximum > 0` for two consecutive 60-second periods
- `aws_sns_topic.alerts` — alert channel
- `aws_sns_topic_subscription.alerts_email` — pipes alerts to the configured email address

The alarm uses `Maximum` rather than `Average` so even a single unhealthy host across the period registers as a breach.

---

## Project structure

```
full-stack/
├── providers.tf          # AWS provider, S3 backend, default tags
├── variables.tf          # all input variables with defaults
├── terraform.tfvars      # alert_email value (gitignored)
├── main.tf               # VPC module call
├── security_groups.tf    # ALB SG + instance SG (chained)
├── iam.tf                # role, policies, instance profile
├── s3.tf                 # ALB logs bucket + configs + bucket policy
├── compute.tf            # AMI lookup, launch template, ASG
├── alb.tf                # ALB, target group, listener
├── monitoring.tf         # SNS topic, subscription, CloudWatch alarm
├── outputs.tf            # ALB DNS, role ARN, etc.
├── user_data.sh          # nginx install + dynamic index page
└── README.md
```

---

## Prerequisites

- AWS account with CLI credentials configured (`aws configure`)
- Terraform >= 1.5
- An S3 bucket named `dimitrije-tf-state-2026` and a DynamoDB table named `terraform-locks` for remote state (configured in `providers.tf`)
- The Day 15 VPC module present at `../../day15/aws-vpc-terraform/modules/vpc/`
- A real email address for SNS alerts

---

## Deployment

### 1. Configure variables

Create `terraform.tfvars`:

```hcl
alert_email = "you@example.com"
```

All other variables have sensible defaults in `variables.tf`. Override there or in `terraform.tfvars` as needed.

### 2. Initialize and apply

```bash
terraform init      # downloads AWS provider, links VPC module
terraform validate
terraform plan      # should show ~33 resources to add
terraform apply     # ~5 minutes to fully deploy
```

### 3. Confirm SNS subscription

After apply, AWS sends a confirmation email to the configured address. Click the link to activate alert delivery. Without confirmation, alerts will not fire.

### 4. Test the deployment

```bash
# Hit the ALB URL — see different instance IDs across requests
for i in {1..10}; do
  curl -s "$(terraform output -raw alb_url)" | grep "Hello from"
done

# Confirm health and instance count
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names day19-stack-app-asg \
  --query "AutoScalingGroups[0].Instances[*].[InstanceId,HealthStatus]" \
  --output table

# Test self-healing — terminate an instance, watch ASG replace it
aws ec2 terminate-instances --instance-ids <instance-id>
sleep 90
# Re-run the describe command; you'll see a new instance launching
```

---

## Teardown

```bash
terraform destroy
```

If the SNS subscription is still in `PendingConfirmation` (email never confirmed), destroy will fail on that resource. Workaround:

```bash
terraform state rm aws_sns_topic_subscription.alerts_email
terraform destroy
```

The pending subscription auto-expires in AWS after three days.

---

## Cost estimate

Running this stack 24/7 in `us-east-1` costs roughly:

| Resource | Cost |
|---|---|
| ALB | ~$16.20/month (fixed) + $0.008/LCU-hour |
| 2× t3.micro EC2 | $0 (free tier) or ~$15/month |
| EBS volumes (2× 8GB gp3) | ~$1.30/month |
| S3 storage (logs) | <$0.10/month for typical lab traffic |
| CloudWatch alarm | $0.10/month |
| SNS | Effectively free for email at this volume |
| Data transfer | <$1/month for testing |

**Total: ~$20-35/month if running continuously.** For learning and demos, deploy → test → destroy keeps costs well under $1 per session.

---

## Design decisions

### Why a VPC module instead of inline networking?

The Day 15 module encapsulates the standard VPC pattern (multi-AZ subnets, IGW, route tables, optional NAT). Reusing it across projects exercises the modules-as-functions concept and keeps Day 19's root config focused on the application-specific layer (ALB, ASG, IAM, monitoring).

### Why instances in public subnets, not private?

The lab runs `create_nat = false` to avoid NAT Gateway charges (~$0.045/hour). Without NAT, instances in private subnets can't reach the internet to install packages. Putting them in public subnets with `map_public_ip_on_launch = true` lets the user data fetch nginx directly from the package repos.

In production this would be inverted: instances would run in private subnets behind the ALB, with NAT Gateways in public subnets handling outbound traffic. The cost trade-off is justified by the security benefit of not having public IPs on application instances.

### Why `health_check_type = "ELB"` on the ASG?

The default (`EC2`) only checks whether the instance is running. If nginx crashed but the EC2 stayed up, the ASG would consider the instance healthy while the ALB marked it as a failing target. With `ELB`, the ASG defers to the load balancer's health check, so application-level failures trigger instance replacement. This is the right default for any ALB-fronted ASG.

### Why two purpose-built SGs instead of reusing the module's `web_sg`?

The module's `web_sg` accepts traffic from `0.0.0.0/0` on ports 80, 443, and 22 — appropriate for a general "web server" but too permissive for the ALB pattern. The Day 19 SGs enforce that only the ALB can reach the instances on port 80, which is the cleaner production posture. The module focuses on networking primitives; application-specific SGs belong to the consumer.

### Why a separate S3 bucket for ALB logs instead of reusing one?

Bucket policies are attached to a single bucket and grant access to a single principal (the ELB service account). Mixing ALB logs with other content in the same bucket would require either broader policies (more access than needed) or partition-based separation that's harder to reason about. One bucket per logging concern is the cleanest default.

### Why `lifecycle { create_before_destroy = true }` on the launch template?

When the launch template needs replacement (new AMI, modified user data, etc.), Terraform's default order is destroy-then-create. During the gap, the ASG references a non-existent launch template and fails any scaling actions. Reversing the order ensures the ASG always has a valid template attached.

### Tagging strategy

Common tags (`Project`, `ManagedBy`) are set via `default_tags` on the AWS provider so every resource is tagged consistently without per-resource boilerplate. Resources only declare their own specific tags (like `Name`). This is the recommended pattern for tag governance — it's how cost allocation and operational ownership are typically driven in production.

---

## Known limitations and production improvements

- **Single NAT Gateway / no NAT in this config.** A production deployment would use one NAT Gateway per AZ for high availability of outbound traffic from private subnets.
- **No HTTPS.** The ALB listener is HTTP/80 only. Production would terminate TLS at the ALB using an ACM certificate, with HTTP→HTTPS redirect.
- **No WAF.** Public-facing ALBs in production should have AWS WAF in front for common attack mitigation.
- **No auto-scaling policies.** The ASG has fixed sizing; production would add `aws_autoscaling_policy` resources to scale on CPU, request count, or custom metrics.
- **Instance SG allows SSH from the configured CIDRs.** For production, SSH access would go through Session Manager (no SSH ports open at all) using the SSM agent and an IAM role with `AmazonSSMManagedInstanceCore`.
- **No log retention policies.** ALB logs accumulate in S3 indefinitely. A lifecycle rule would transition logs to Glacier after 30 days and delete after a year.
- **No deletion protection.** The ALB and S3 bucket should have deletion protection in production via `enable_deletion_protection = true` on the ALB and `lifecycle { prevent_destroy = true }` on critical resources.
- **Bucket policy uses the legacy ELB service account principal.** Newer AWS regions use the AWS Logs Delivery service principal (`logdelivery.elasticloadbalancing.amazonaws.com`); this template would need adjusting for those regions.

---

## What this project demonstrates

For a junior cloud/DevOps role, this project shows fluency with:

- **AWS networking primitives** — VPC, subnets, route tables, IGW, security groups
- **Compute and load balancing** — EC2, launch templates, ASGs, ALBs, target groups
- **IAM at the right grain** — role + policy + attachment + instance profile, with policies built from `aws_iam_policy_document` data sources
- **Storage with proper configuration** — versioning, encryption, lifecycle (split-resource pattern in AWS provider v4+)
- **Monitoring and incident response** — CloudWatch metrics, alarms, SNS topics, alert delivery
- **Terraform module reuse** — calling a module across environments with environment-specific inputs
- **Terraform best practices** — `default_tags` for governance, `lifecycle` rules for safe replacements, `name_prefix` over `name` where required, remote state with locking, sensible variable defaults
