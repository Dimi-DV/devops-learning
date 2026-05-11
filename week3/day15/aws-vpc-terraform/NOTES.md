# Day 16 — Terraform VPC: Production Infrastructure as Code (Portfolio Project #1)

## What I Built Today
- Wrote 7 Terraform files from scratch to deploy a complete production-style VPC
- Deployed 18 AWS resources entirely through code
- Validated connectivity with EC2 test instances in public and private subnets
- Committed Portfolio Project #1 to GitHub

## Architecture Deployed

```
VPC: 10.0.0.0/16
├── public-1a:  10.0.1.0/24  (us-east-1a)  ──┐
├── public-1b:  10.0.2.0/24  (us-east-1b)  ──┤── Route table → IGW
├── private-1a: 10.0.10.0/24 (us-east-1a)  ──┐
├── private-1b: 10.0.11.0/24 (us-east-1b)  ──┤── Route table → NAT GW
├── Internet Gateway (attached to VPC)
├── NAT Gateway + Elastic IP (in public-1a)
├── web-sg: 80/443 from anywhere, 22 from my IP
└── private-sg: all traffic from web-sg only
```

## Project File Structure

```
aws-vpc-terraform/
├── providers.tf          # AWS provider + S3 backend config
├── variables.tf          # All input variables (region, CIDRs, AZs, naming)
├── vpc.tf                # VPC, 4 subnets, internet gateway
├── routing.tf            # Route tables, routes, subnet associations
├── nat.tf                # Elastic IP + NAT gateway
├── security_groups.tf    # web-sg + private-sg
├── outputs.tf            # VPC ID, subnet IDs, SG IDs, NAT ID
```

## Key Terraform Concepts Learned

### What You Define vs What's Predefined
- **Predefined by Terraform/provider**: keywords (`resource`, `variable`), resource types (`aws_vpc`, `aws_subnet`), argument names (`vpc_id`, `cidr_block`), exported attributes (`.id`, `.arn`)
- **Defined by you**: resource names (the second quoted string), variable names, actual values

### Resource References & Dependency Graph
- Resources reference each other with `type.name.attribute` pattern
  - Example: `aws_vpc.main.id` = "get the id from the resource of type aws_vpc named main"
- Terraform reads ALL .tf files, builds a dependency graph from references, and determines creation order automatically
- Order in the file doesn't matter — Terraform figures it out from references
- A reference can only POINT TO a resource definition — it cannot create one
- Every `type.name.attribute` reference must have a matching `resource "type" "name"` block somewhere

### How Terraform Files Work
- All `.tf` files in the same directory are merged as one flat configuration
- Filenames are for YOUR organization — Terraform doesn't care about them
- Variables defined in `variables.tf` are accessible in any other `.tf` file — no imports needed
- Terraform does NOT recurse into subdirectories (that's for modules, Day 17)

### Resource Types vs Resource Names
- `resource "aws_subnet" "public_1a"` — `aws_subnet` is the type (predefined, must be exact), `public_1a` is the name (you choose)
- Same name on different types = no conflict: `aws_subnet.public_1a` and `aws_route_table_association.public_1a` are completely different resources

### State & IDs
- CIDR block (e.g. `10.0.1.0/24`) = what YOU choose
- Subnet ID (e.g. `subnet-0abc123...`) = what AWS assigns at creation
- Terraform stores AWS-assigned IDs in the state file
- `(known after apply)` in plan output = will be assigned when resource is created
- S3 keys look like paths (`vpc/terraform.tfstate`) but S3 is flat — no real folders

### Specific Resource Notes
- `aws_route` does NOT support tags (tags go on the route table)
- `aws_route_table_association` links a subnet to a route table — it doesn't create anything new
- `aws_eip`: `domain = "vpc"` is required (tells AWS the EIP is for VPC use)
- `aws_nat_gateway`: `allocation_id` and `subnet_id` are both required arguments
- Security groups: `gateway_id` for IGW, `nat_gateway_id` for NAT — different argument names
- Security groups: `protocol = "-1"` means all protocols; when used, `from_port = 0` and `to_port = 0` are placeholders
- Private subnets don't set `map_public_ip_on_launch` (defaults to false)
- `Name` tag must be capital N to display in AWS Console

## Validation Results
- ✅ Public instance (10.0.1.x) — internet access via IGW confirmed with ping
- ✅ Private instance (10.0.10.x) — internet access via NAT confirmed with ping
- ✅ SSH hop from public to private — security group reference working
- ✅ Route tables correctly directing traffic

## Commands Used

```bash
terraform init                    # Initialize provider + S3 backend
terraform plan                    # Preview all 18 resources
terraform apply                   # Deploy everything
terraform destroy                 # Tear down to avoid charges

# Validate connectivity
ssh -i ~/.ssh/prod-key.pem ec2-user@<public-ip>
ping -c 3 google.com
ssh -i ~/prod-key.pem ec2-user@<private-ip>   # hop from public instance

# Check key pairs
aws ec2 describe-key-pairs --region us-east-1
# Check security group rules
aws ec2 describe-security-groups --group-ids <sg-id> --region us-east-1
```

## Cost Notes
- NAT Gateway: ~$0.045/hr (~$1.08/day) — destroy when not in use
- EC2 t4g.micro: minimal cost, used only for testing then destroyed
- EIP: free when attached to running instance, $0.005/hr when idle

## Troubleshooting Encountered
- Empty .tf files: VS Code tabs showed code but files weren't saved — always verify with `ls -la *.tf` and check file sizes
- SSH timeout: Used VM local IP (192.168.64.2) instead of public IP in security group — must use public IP from `curl ifconfig.me`
- Cafe WiFi may block port 22 outbound — temporarily opened SSH to 0.0.0.0/0 to diagnose

---
Date: 2026-04-10
Status: ✅ Portfolio Project #1 complete and committed
