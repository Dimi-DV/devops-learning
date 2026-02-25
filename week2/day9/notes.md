# VPC Architecture Documentation — Day 9

## Overview

Production-style VPC built manually in the AWS Console (us-east-1). This architecture provides public-facing web tier and isolated private tier across two Availability Zones for high availability. This will be recreated in Terraform on Day 16.

## Architecture Diagram

```
                         INTERNET
                            |
                      ┌─────┴─────┐
                      │  prod-igw │
                      └─────┬─────┘
                            |
        ┌───────────────────┴───────────────────────┐
        │              prod-vpc                      │
        │            10.0.0.0/16                     │
        │                                            │
        │   ┌─── us-east-1a ───┐  ┌─ us-east-1b ──┐ │
        │   │                  │  │                │ │
        │   │   public-1a      │  │   public-1b    │ │
        │   │   10.0.1.0/24    │  │   10.0.2.0/24  │ │
        │   │   [web-sg]       │  │   [web-sg]     │ │
        │   │   ┌──────────┐   │  │                │ │
        │   │   │ NAT GW   │   │  │                │ │
        │   │   │(prod-nat)│   │  │                │ │
        │   │   │ EIP      │   │  │                │ │
        │   │   └──────────┘   │  │                │ │
        │   │                  │  │                │ │
        │   ├──────────────────┤  ├────────────────┤ │
        │   │                  │  │                │ │
        │   │   private-1a     │  │   private-1b   │ │
        │   │   10.0.10.0/24   │  │   10.0.11.0/24 │ │
        │   │   [private-sg]   │  │   [private-sg] │ │
        │   │                  │  │                │ │
        │   └──────────────────┘  └────────────────┘ │
        └────────────────────────────────────────────┘
```

## Components

| Component | Name | Details |
|-----------|------|---------|
| VPC | prod-vpc | 10.0.0.0/16 (65,534 usable IPs) |
| Public Subnet 1a | public-1a | 10.0.1.0/24 in us-east-1a (254 usable IPs) |
| Public Subnet 1b | public-1b | 10.0.2.0/24 in us-east-1b (254 usable IPs) |
| Private Subnet 1a | private-1a | 10.0.10.0/24 in us-east-1a (254 usable IPs) |
| Private Subnet 1b | private-1b | 10.0.11.0/24 in us-east-1b (254 usable IPs) |
| Internet Gateway | prod-igw | Attached to prod-vpc, 1:1 relationship |
| NAT Gateway | prod-nat | Located in public-1a, has Elastic IP |
| Elastic IP | prod-nat-eip | Static public IP for NAT Gateway |
| Public Route Table | public-rt | 0.0.0.0/0 → IGW, associated with public subnets |
| Private Route Table | private-rt | 0.0.0.0/0 → NAT GW, associated with private subnets |
| Web Security Group | web-sg | HTTP (80), HTTPS (443) from anywhere; SSH (22) from my IP |
| Private Security Group | private-sg | All traffic from web-sg (SG reference, not IP-based) |

## Route Tables

### public-rt
| Destination | Target | Purpose |
|-------------|--------|---------|
| 10.0.0.0/16 | local | VPC internal traffic |
| 0.0.0.0/0 | prod-igw | Internet access via IGW |

### private-rt
| Destination | Target | Purpose |
|-------------|--------|---------|
| 10.0.0.0/16 | local | VPC internal traffic |
| 0.0.0.0/0 | prod-nat | Outbound internet via NAT GW |

## Security Groups

### web-sg (for public-facing instances)
| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 80 | 0.0.0.0/0 | HTTP web traffic |
| Inbound | TCP | 443 | 0.0.0.0/0 | HTTPS web traffic |
| Inbound | TCP | 22 | My IP/32 | SSH admin access |
| Outbound | All | All | 0.0.0.0/0 | All outbound (default) |

### private-sg (for private instances)
| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | All | All | web-sg (SG ID) | Allow traffic from web tier only |
| Outbound | All | All | 0.0.0.0/0 | All outbound (default) |

## Traffic Flow Scenarios

### 1. Internet → Public Instance (e.g., user visits web server)
```
User's browser
  → Internet
    → Internet Gateway (prod-igw)
      → public-rt routes to subnet
        → web-sg checks: is port 80/443 from anywhere? YES
          → Traffic reaches EC2 in public subnet
```

### 2. Public Instance → Internet (e.g., server downloads updates)
```
EC2 in public subnet
  → public-rt: destination 0.0.0.0/0 matches → send to IGW
    → Internet Gateway
      → Internet
        → Response returns same path (security groups are stateful)
```

### 3. Private Instance → Internet (e.g., apt update)
```
EC2 in private subnet
  → private-rt: destination 0.0.0.0/0 matches → send to NAT GW
    → NAT Gateway (in public-1a) translates private IP to EIP
      → Internet Gateway
        → Internet
          → Response returns via NAT GW → private instance
```

### 4. Internet → Private Instance (BLOCKED)
```
External request → Internet Gateway → ???
  No route exists from IGW to private subnets.
  NAT Gateway does NOT accept inbound connections.
  RESULT: Connection impossible. Private instances are unreachable from internet.
```

### 5. Public Instance → Private Instance (Bastion Pattern)
```
SSH into public EC2 (bastion/jump box)
  → From bastion, SSH to private EC2's private IP
    → private-sg checks: source is web-sg? YES
      → Traffic reaches private EC2
```

## What Makes a Subnet "Public" vs "Private"?

A subnet is NOT inherently public or private. What makes it public is its route table having a route to an Internet Gateway. Remove that route, and the subnet becomes private. The naming is just a convention — the route table is what matters.

## Key Concepts Learned

- **Security group referencing**: private-sg allows traffic from web-sg by SG ID, not by IP. This means any instance with web-sg attached can reach any instance with private-sg, regardless of IP changes.
- **Stateful security groups**: If an outbound request is allowed, the response is automatically allowed back in. No need for explicit inbound rules for return traffic.
- **NAT Gateway is outbound-only**: It allows private instances to initiate connections to the internet, but the internet cannot initiate connections to private instances through it.
- **Bastion pattern**: The only way to access private instances is through a public instance that acts as a jump box.

## Testing Results

| Test | Expected | Actual |
|------|----------|--------|
| SSH to public instance | Success | ✅ Success |
| Ping google.com from public | Success | ✅ Success (via IGW) |
| SSH directly to private instance | Fail/timeout | ✅ Timed out (no route) |
| SSH bastion hop (public → private) | Success | ✅ Success (agent forwarding) |
| Ping google.com from private | Success | ✅ Success (via NAT GW) |

## Cost Notes

- **NAT Gateway**: ~$0.045/hr (~$32/month). Delete when not in use. This is the only significant cost.
- **Elastic IP**: Free when attached to running NAT GW. ~$0.005/hr if NAT GW deleted but EIP not released.
- **VPC, subnets, route tables, IGW, security groups**: Always free.
- **EC2 t2.micro**: Free tier (750 hrs/month for first 12 months).

## Production Improvements

- Add NAT Gateway in public-1b for redundancy (single NAT GW is a single point of failure)
- Enable VPC Flow Logs for network traffic monitoring
- Add NACLs as an additional layer of defense (defense in depth)
- Use more restrictive private-sg rules (specific ports instead of all traffic)
- Add VPC endpoints for AWS services (S3, DynamoDB) to avoid NAT GW costs for AWS traffic

## Cleanup Checklist

- [x] Terminate both EC2 test instances
- [x] Delete NAT Gateway (prod-nat)
- [x] Release Elastic IP
- [ ] VPC, subnets, route tables, IGW, security groups can stay (free)
