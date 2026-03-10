# Day 12 — Load Balancers, Auto Scaling, RDS, DynamoDB + Architecture Patterns

## Route 53 — AWS DNS Service

- AWS's **authoritative DNS service** — runs on port 53 (hence the name)
- Used to register domains and create DNS records pointing to AWS resources
- **Alias records**: AWS-specific, like a CNAME but works at zone apex and is free for AWS resources
- Route 53 health checks are separate from ALB health checks — used for **cross-region** failover

### Routing Policies

| Policy | Use Case |
|--------|----------|
| **Simple** | One record, one destination (single ALB) |
| **Weighted** | Split traffic by percentage (blue/green: 90% v1, 10% v2) |
| **Latency-based** | Route to nearest region (ALBs in us-east-1 AND eu-west-1) |
| **Failover** | Active/passive — DNS switches to standby if primary health check fails |
| **Geolocation** | Route based on user's country/continent (regulatory/content reasons) |

---

## Elastic Load Balancing (ELB)

### ALB (Application Load Balancer) — Layer 7

- Understands HTTP/HTTPS — can read headers, paths, query strings
- Makes routing decisions based on request **content**

**Key Components:**

- **Listeners**: Process checking for connections on a specific port/protocol (80 or 443). Has rules for routing.
  - Path-based: `/api/*` → API target group
  - Host-based: `api.myapp.com` → API servers
- **Target Groups**: Logical grouping of targets (EC2, IPs, Lambda) that receive traffic from ALB
  - Protocol + port config tells ALB **how to talk to** instances (not a filter)
  - When ASG attached, instances auto-register/deregister
- **Health Checks**: ALB periodically sends HTTP requests to each target
  - Protocol: HTTP, Path: `/`, Port: 80
  - Healthy threshold: 3, Unhealthy threshold: 2
  - Timeout: 5s, Interval: 30s, Success codes: 200
  - If instance fails → ALB stops sending traffic (but doesn't terminate — that's ASG's job)

**TLS Termination**: ALB decrypts HTTPS, forwards plain HTTP to backends. Certs managed in ACM.

**Cross-zone load balancing**: Enabled by default. Traffic distributed evenly across ALL instances regardless of AZ distribution.

### NLB (Network Load Balancer) — Layer 4

- Works with TCP/UDP directly — doesn't inspect HTTP content
- **When to use NLB over ALB:**
  - Ultra-low latency (microseconds vs milliseconds)
  - Static IP addresses needed (NLB gives one per AZ; ALB only has DNS name)
  - Non-HTTP protocols (gaming UDP, IoT, database proxies)
  - TLS passthrough (backend terminates TLS, not the LB)

### ALB vs NLB Comparison

| | ALB | NLB |
|---|---|---|
| Layer | 7 (HTTP/HTTPS) | 4 (TCP/UDP/TLS) |
| Routing | Path, host, header, query string | Port number only |
| Static IP | No (DNS name only) | Yes (one per AZ) |
| Latency | ~ms | ~μs |
| TLS | Terminates at LB | Can pass through |
| Use case | Web apps, APIs, microservices | Gaming, IoT, financial, TCP |

**Classic Load Balancer (CLB)** = legacy, never use for new deployments.

### ALB Architecture — One ALB, Multiple AZ Nodes

- One ALB is a **single resource** spanning multiple AZs
- AWS places an ALB **node** in each selected subnet automatically
- Single DNS name resolves to all node IPs
- Each node can route to instances in ANY AZ (cross-zone)
- ALB is fully managed — AWS handles redundancy, scaling, patching
- Not technically impossible to fail, but extremely unlikely with multi-AZ

### Security Group Pattern

```
ALB SG (alb-sg):
  Inbound: 80/443 from 0.0.0.0/0     ← Internet reaches ALB
  
Instance SG (web-sg):
  Inbound: 80 from alb-sg              ← ONLY ALB reaches instances
  Inbound: 22 from MY-IP               ← SSH for admin only
```

Key: instances reference ALB's SG ID as source — same SG-chaining pattern as private-sg referencing web-sg.

---

## Auto Scaling Groups (ASG)

Solves three problems: **availability** (replace dead instances), **elasticity** (scale with demand), **cost** (don't over-provision).

### Launch Templates

Blueprint for EC2 instances — captures everything needed to launch:
- AMI, instance type, key pair, security group, IAM profile, user data, tags
- Supports **versioning** — update AMI in v2, ASG launches new instances on v2
- **AMI vs Launch Template**: AMI = disk snapshot (OS + installed software). Launch Template = launch parameters (which AMI, which instance type, which SG). Template *references* an AMI. They work together, not as alternatives.

### ASG Configuration

- Launch template + version
- VPC + subnets (which AZs to use)
- Capacity: minimum, maximum, desired
- Load balancer integration: attach to target group
- Health check type + grace period

### Health Check Types — Critical Distinction

- **EC2 health checks**: Only checks if VM is running at hypervisor level. Nginx crashes but OS is fine = "healthy." ❌
- **ELB health checks**: Uses ALB's HTTP health check. Nginx crashes = unhealthy → ASG terminates and replaces. ✅
- **Always use ELB health checks** when ASG is attached to a load balancer.

**Health check grace period**: Wait time after launch before checking health. Prevents death loop where instances get terminated before user data finishes. 300s is safe default.

### Scaling Policies

**1. Target Tracking (recommended starting point)**
- Set a target metric value, AWS manages the rest
- "Keep average CPU at 50%" — like a thermostat
- AWS auto-creates and manages CloudWatch alarms
- Available metrics: CPU utilization, request count per target, network in/out

**How it actually works:**
1. You tell ASG: "keep CPU at 50%"
2. ASG creates two CloudWatch alarms automatically (scale out + scale in)
3. CloudWatch evaluates alarms against aggregated metrics
4. When alarm triggers → CloudWatch notifies ASG → ASG adjusts capacity
- Flow: CloudWatch watches → CloudWatch alarms trigger → ASG acts

**2. Step Scaling**
- Granular: CPU 50-70% → +1, CPU 70-90% → +2, CPU >90% → +3
- You create CloudWatch alarms manually

**3. Simple Scaling**
- One alarm, one action. Oldest type. Target tracking almost always better.

**Scheduled Scaling**: Time-based — "weekdays 8AM set desired=4, 8PM set desired=2"

---

## Full Request Flow Through Architecture

```
1. User → Route 53 resolves domain → ALB DNS name
2. Client → ALB (alb-sg allows port 80) → Listener matches rule → Target group
3. ALB picks healthy target (round-robin, cross-zone) → Instance
4. Instance (web-sg allows port 80 from alb-sg) → nginx responds
5. Background: ALB health checks every 30s, ASG monitors capacity, CloudWatch collects metrics
```

### Failure Scenarios

**Instance crashes:**
- ALB health check fails (2 failures × 30s) → stops routing traffic
- ASG sees ELB health check failure → terminates instance
- ASG detects current < desired → launches replacement from Launch Template
- After grace period, new instance passes health checks → receives traffic
- **Zero downtime** (other instance handles all traffic during replacement)

**AZ goes down:**
- ALB routes all traffic to remaining AZ
- ASG launches replacements in healthy AZ only
- Production tip: set min:2 per AZ (min:4 total) for true HA

**Traffic spike:**
- Target tracking sees metric above target → ASG increases desired
- New instance launches, boots, passes health checks → receives traffic
- Traffic drops → policy scales in (respects minimum capacity)

**Observed behavior when terminating an instance:**
- First few seconds: 502 errors alternating with working responses (ALB hasn't detected failure yet)
- Next: ALB detects failure, all traffic goes to healthy instance (slightly slower)
- ~Minutes later: ASG launches replacement, goes healthy, traffic balanced again
- The brief 502s are why production uses **connection draining** (deregistration delay)

---

## Hands-On Lab — What I Built

### ALB + ASG Build

1. **Launch Template** (`web-lt`): Amazon Linux 2023, t3.micro, prod-key, web-sg, IMDSv2 user data installing nginx with instance ID page
2. **Target Group** (`web-tg`): HTTP:80, health check on `/`, didn't register targets manually (ASG handles it)
3. **ALB SG** (`alb-sg`): inbound 80 from 0.0.0.0/0
4. **Modified web-sg**: added inbound 80 from alb-sg
5. **ALB** (`web-alb`): internet-facing, public-1a + public-1b, listener port 80 → web-tg
6. **ASG** (`web-asg`): web-lt, public-1a + public-1b, attached to web-tg, ELB health checks, 300s grace period, min:2 max:4 desired:2, target tracking CPU 50%

**Debugging issue encountered:** Instances launched without public IPs → couldn't reach internet → user data couldn't `yum install nginx` → health checks failed.
**Fix:** Enabled auto-assign public IPv4 on both public subnets, terminated old instances, ASG launched new ones with public IPs.

**Tested:** Hit ALB DNS, refreshed multiple times — saw different instance IDs alternating. Terminated one instance, watched ASG self-heal and replace it.

### RDS Build

1. **DB Subnet Group** (`prod-db-subnet-group`): private-1a + private-1b
2. **RDS SG** (`rds-sg`): inbound MySQL 3306 from web-sg only
3. **RDS Instance** (`database-1`): MySQL 8.4, db.t4g.micro, free tier, prod-vpc, private subnets, no public access
4. **Connected via bastion pattern**: Mac → SSH → EC2 in public subnet (web-sg) → MySQL on port 3306 → RDS (rds-sg allows web-sg)
5. **Database operations**: Created `testdb`, created `users` table, inserted 3 rows, queried with SELECT
6. **Took manual snapshot** for backup

**Key learning:** Easy Create doesn't let you pick VPC (defaults to default VPC, not editable after creation). Must use Full Configuration to specify prod-vpc, subnet group, and security group.

### DynamoDB Build

1. **Created table** `Users`: partition key `userId` (String), on-demand capacity
2. **Added items** with different attributes per item (user-001 has `age`, user-002 has `favoriteColor`) — demonstrates NoSQL schema flexibility
3. **Queried by partition key**: `user-001` → returned only that item

**DynamoDB data types**: `S` = String, `N` = Number, `B` = Binary, `BOOL` = Boolean, `L` = List, `M` = Map

---

## RDS — Relational Database Service

- **Managed** relational database: AWS handles patching, backups, failover
- Engines: MySQL, PostgreSQL, MariaDB, Oracle, SQL Server, Aurora
- You connect and run queries — no SSH into the server

### Multi-AZ Deployments

- Standby replica in different AZ with **synchronous replication**
- If primary fails → RDS flips DNS endpoint to standby (60-120s)
- App doesn't change connection strings (connects to DNS endpoint)
- **Cannot read from standby** — exists purely for failover (common exam misconception)

### Read Replicas

- Solve **performance** (not availability) — handle read-heavy workloads
- Up to 15 read replicas
- **Asynchronous** replication — slight lag, possibly stale data
- Accessible for read queries (unlike Multi-AZ standby)
- Can be cross-region
- Can be promoted to standalone database (DR strategy)
- Can combine Multi-AZ (failover) + Read Replicas (performance)

### Aurora

- AWS proprietary, MySQL/PostgreSQL compatible
- Storage: distributed, 6 copies across 3 AZs, auto-grows to 128 TB
- Replicas share same storage → <10ms replication lag
- Failover: ~30s (vs 60-120s for standard RDS)
- **Aurora Serverless**: auto-scales compute, pay per second
- SAA signal: "high performance" + "high availability" + "MySQL/PostgreSQL" + "minimal overhead" → Aurora

### RDS Backups

- **Automated**: daily snapshots + transaction logs, 1-35 day retention, point-in-time recovery
- **Manual snapshots**: persist until deleted, use before major changes
- Both create a **new** RDS instance on restore (don't overwrite original)

---

## DynamoDB — Serverless NoSQL

- No instance, no storage provisioning, no patching — fully serverless
- Key-value and document store
- Single-digit millisecond latency at any scale

### Data Model

**Partition key only (simple):** Single attribute uniquely identifies each item. DynamoDB hashes it to determine physical partition.

**Partition key + sort key (composite):** Two attributes together = unique. Same partition key items stored together, sorted by sort key.

Good partition key = even data distribution. Bad key = hot partition bottleneck.

### Capacity Modes

- **On-demand**: Pay per request, no planning, great for unpredictable workloads
- **Provisioned**: Specify read/write capacity units, cheaper if traffic predictable, can auto-scale

### Key Features for SAA

- **DAX**: In-memory cache → microsecond responses. "Improve DynamoDB read performance" → DAX
- **Global Tables**: Multi-region, multi-active (read AND write in every region)
- **DynamoDB Streams**: Ordered stream of changes → trigger Lambda functions

---

## SQL vs NoSQL Decision Framework

| Criteria | SQL (RDS) | NoSQL (DynamoDB) |
|----------|-----------|-----------------|
| **Data relationships** | Complex joins across tables | No joins — query per table, stitch in app code |
| **Query patterns** | Ad-hoc queries, complex filtering, GROUP BY, reporting | Known access patterns, simple lookups by key |
| **Scale** | Vertical (bigger instance) + read replicas, hits ceiling | Horizontal, essentially unlimited |
| **Latency** | Good, but varies | Consistent single-digit ms at any scale |

**Quick SAA reference:**
- E-commerce catalog with complex queries → RDS
- User session storage → DynamoDB
- Traditional business app (ERP, CRM) → RDS
- Gaming leaderboards → DynamoDB
- Financial reporting with joins → RDS
- IoT sensor data at massive scale → DynamoDB

---

## 3-Tier Web Architecture

```
TIER 1 — Presentation (Public Subnets)
  Route 53 → ALB (alb-sg: 80/443 from 0.0.0.0/0)
  Optional: CloudFront CDN in front of ALB

TIER 2 — Application (Private Subnets ideally)
  EC2/ASG (web-sg: 80 from alb-sg)
  Or: ECS/Fargate containers, Lambda functions

TIER 3 — Data (Private Subnets)
  RDS (rds-sg: 3306 from web-sg)
  DynamoDB, ElastiCache, S3
```

Each tier only talks to the tier directly adjacent. Defense in depth — same least privilege principle from IAM.

## Serverless Architecture

```
Client → API Gateway → Lambda → DynamoDB / S3 / SNS / SQS
```

- API Gateway replaces ALB + EC2 (fully managed HTTP endpoint)
- Lambda replaces EC2 app tier (pay per invocation, no idle instances)
- DynamoDB already serverless

**Serverless when:** "minimize operational overhead," "pay only for what you use," variable/bursty traffic
**Traditional when:** long-running processes (Lambda 15-min timeout), consistent low latency needed, predictable high traffic

## Well-Architected Framework — 6 Pillars

1. **Operational Excellence** — Automate everything, monitor proactively, improve iteratively (CloudWatch alarms/dashboards)
2. **Security** — Least privilege access, protect data, detect threats (SG chaining, IAM policies)
3. **Reliability** — Recover from failures, scale to meet demand (ALB + ASG + Multi-AZ)
4. **Performance Efficiency** — Right resource types/sizes, monitor and adapt (t3.micro vs c5.xlarge, DynamoDB vs RDS)
5. **Cost Optimization** — Eliminate waste, right pricing models (delete unused resources, scale down off-hours)
6. **Sustainability** — Minimize environmental impact (right-sizing, managed services, scale down when idle)

**Interview tip:** Structure architecture answers around these pillars — "For reliability, I'd use Multi-AZ with auto scaling. For security, private subnets with SG chaining. For cost, target tracking to scale in off-hours."

---

## Cost Awareness

| Resource | Cost |
|----------|------|
| ALB | ~$0.0225/hr (~$16/mo) + LCU charges |
| EC2 t3.micro | Free tier (750 hrs/mo) — 2 instances burns faster |
| Route 53 | $0.50/mo per hosted zone + $0.40/million queries |
| Cross-AZ data transfer | ~$0.01/GB |
| RDS db.t4g.micro | ~$0.019/hr, free tier eligible |
| DynamoDB on-demand | Pay per request |

**Always delete ALB, ASG, and RDS when done with exercises.**

---

## Key Interview Questions

1. "What happens if an instance behind an ALB fails?" → Health check fail → deregister → ASG replaces
2. "ALB vs NLB?" → Layer 7 vs Layer 4 decision tree
3. "How handle traffic spike?" → Target tracking, scale out, health check grace period
4. "ELB vs EC2 health checks?" → ELB checks application health, EC2 only checks instance status
5. "Zero-downtime deployments?" → New Launch Template version, instance refresh, connection draining
6. "When RDS vs DynamoDB?" → Relationships/complex queries → RDS; Key-value lookups at scale → DynamoDB
7. "What's Multi-AZ vs Read Replicas?" → Multi-AZ = failover (standby, can't read). Read Replicas = performance (readable, async)
