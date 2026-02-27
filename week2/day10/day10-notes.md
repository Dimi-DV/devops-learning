# Day 10 — EC2 Deep Dive + S3

## EC2 Concepts

### Instance Types
Instance families follow the pattern: **family + generation + size** (e.g. `t3.micro`)

| Family | Optimized for | Use case |
|--------|--------------|----------|
| t3/t4g | Burstable general purpose | Dev, test, learning labs |
| m6i/m7i | Balanced CPU+RAM | Production web/app servers |
| c6i/c7i | Compute | High CPU workloads, encoding |
| r6i/r7i | Memory | Databases, Redis, in-memory analytics |
| i3/i4i | Storage (NVMe) | High I/O databases |
| p3/p4/g4 | GPU | ML training, inference |

**Decision framework:** identify your bottleneck first. CPU-bound → C family. Memory-bound → R family. General → M family. Cost-sensitive + spiky → T family.

**T-family gotcha:** CPU credits earned at idle, spent at burst. Sustained high CPU exhausts credits and throttles. Use `t3.unlimited` or switch to M-family for production.

---

### AMIs (Amazon Machine Images)
- Template for launching EC2: root volume snapshot + launch permissions + block device mappings
- **Golden image pattern:** bake software/config into AMI so instances launch fully ready (no bootstrap time)
- AMIs are **regional** — copy to use in another region
- Creating an AMI reboots the instance by default (ensures filesystem consistency)
- AMIs only capture the **root volume** by default — extra attached volumes don't come along

**Workflow:** launch base AMI → SSH in → install/configure → Actions → Create Image → launch new instances from it

---

### User Data Scripts
- Runs **once** on first boot, as root
- Essential for Auto Scaling Groups — bootstrap without touching the instance
- Logs go to `/var/log/cloud-init-output.log` for debugging
- Must start with `#!/bin/bash`
- 16KB size limit

```bash
#!/bin/bash
yum update -y
yum install -y nginx
systemctl start nginx
systemctl enable nginx
```

---

### Instance Metadata (169.254.169.254)
- Link-local address — only accessible from within the instance itself
- No credentials required — instances use this to discover information about themselves
- **IMDSv2** (current default) requires a session token — prevents SSRF attacks

```bash
# Get token first (IMDSv2)
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600")

# Query with token
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/meta-data/instance-id

# Other useful endpoints
# /latest/meta-data/placement/availability-zone
# /latest/meta-data/instance-type
# /latest/meta-data/public-ipv4
# /latest/meta-data/iam/security-credentials/
```

**Why IMDSv2 matters:** IMDSv1 allowed SSRF attacks to steal IAM credentials via the metadata endpoint. IMDSv2's token requirement blocks this.

---

### EBS Volumes

| Type | Name | Use case |
|------|------|----------|
| gp3 | General Purpose SSD | Default — boot volumes, most workloads |
| gp2 | Old general purpose | Legacy, prefer gp3 |
| io2 | Provisioned IOPS SSD | Databases needing consistent low latency |
| st1 | Throughput HDD | Big sequential reads, data warehouses |
| sc1 | Cold HDD | Infrequently accessed archival |

**gp3 vs gp2:** gp3 is better and cheaper. IOPS and throughput configured independently — no need to over-provision storage to get more IOPS.

**EBS is AZ-scoped** — a volume in us-east-1a can only attach to an instance in us-east-1a. To move across AZs: snapshot → create volume in new AZ.

**Snapshots:** incremental, stored in S3 (AWS-managed). First snapshot is full, subsequent ones only store changed blocks.

---

### Instance Store vs EBS

| | EBS | Instance Store |
|--|-----|----------------|
| Persistence | Survives stop/terminate (configurable) | **Destroyed on stop/terminate** |
| Location | Network-attached | Physically on the host machine |
| Speed | Fast, slight network overhead | Extremely fast (direct NVMe) |
| Snapshots | Yes | No |
| Use case | Root volumes, databases, durable data | Temp files, caches, buffer storage |

---

### Spot Instances
- Up to 90% cheaper — uses unused AWS capacity
- AWS can reclaim with **2 minutes warning**
- Use for: stateless/fault-tolerant workloads, batch jobs, CI workers, ML training
- Never use for: databases, stateful workloads, anything requiring guaranteed availability

**Pricing tiers:**
- **On-Demand:** full price, no commitment
- **Reserved (1-3yr):** up to 72% off, stable baseline workloads
- **Spot:** up to 90% off, interruptible
- **Savings Plans:** flexible spend commitment, more flexible than Reserved

---

## What We Built (EC2)

1. Launched `day10-web` EC2 (t3.micro, Amazon Linux 2023) in prod-vpc public subnet with user data script auto-installing nginx
2. Verified nginx served via public IP in browser (no SSH required)
3. Queried instance metadata via IMDSv2 — retrieved instance-id, AZ, instance-type, public-ipv4
4. Created and attached a second 8GB gp3 EBS volume, formatted (ext4) and mounted at `/data`
5. Wrote a test file to `/data`, created a manual snapshot of the data volume
6. Created custom AMI `day10-nginx-ami` from the running instance
7. Launched `day10-from-ami` — a new instance with **no user data** — nginx was already present from the AMI
8. Cleaned up: terminated both instances, deleted snapshot, deregistered AMI, deleted extra EBS volume

**Key commands:**
```bash
# Format and mount EBS
sudo mkfs -t ext4 /dev/nvme1n1
sudo mkdir /data
sudo mount /dev/nvme1n1 /data
df -h /data
lsblk
```

---

## S3 Concepts

### Core Model
- **Bucket:** globally unique container for objects
- **Object:** the file + metadata
- **Key:** the full name of the object — `public/images/photo.jpg` is one flat string, not a folder path. S3 is a flat key-value store; "folders" are an illusion rendered by the console

### Bucket Policies
- ACLs are deprecated — use bucket policies
- JSON with Effect, Principal, Action, Resource, Condition
- **Block Public Access** overrides all bucket policies — must explicitly disable it to allow public access
- `Principal: "*"` = anyone on the internet

### Versioning
- Keeps every version of every object with unique version IDs
- Delete creates a **delete marker** — object still exists, just hidden
- To permanently delete: must delete the specific version ID
- Bucket cannot be deleted while versions exist — must delete all versions first

### Storage Classes
Standard → Standard-IA → One Zone-IA → Glacier Instant → Glacier Flexible → Glacier Deep Archive

Pattern: cheaper storage = slower/more expensive retrieval

**Intelligent-Tiering:** auto-moves objects between tiers based on access patterns — use when access patterns are unknown.

### Lifecycle Rules
Automate moving objects between storage classes or deleting them based on age. Example: logs move to IA after 30 days, Glacier after 90 days, deleted after 365 days.

### Static Website Hosting
- S3 can serve HTML/CSS/JS directly — no server needed
- HTTP only (no HTTPS) on the S3 website endpoint
- Production setup: S3 (private) + CloudFront in front (adds HTTPS, custom domain, caching, DDoS protection)
- URL format: `bucket-name.s3-website-us-east-1.amazonaws.com`

### Presigned URLs
Temporary time-limited URL with embedded credentials for accessing a private object.

```bash
aws s3 presign s3://bucket/file.txt --expires-in 300
```

Use case: user clicks "Download invoice" → backend generates presigned URL → user gets temporary access → file stays private.

### Encryption
- **SSE-S3:** AWS manages keys, default on new buckets, no visibility into key usage
- **SSE-KMS:** you control keys via KMS, every usage logged in CloudTrail, auditable, required for compliance
- **SSE-C:** you provide key per request, AWS never stores it
- **Client-side:** you encrypt before uploading

---

## What We Built (S3)

1. Created bucket `dimi-day10-2026` via CloudShell
2. Uploaded `test.txt`, enabled versioning, uploaded v2 of same file — listed both versions with unique version IDs
3. Wrote bucket policy allowing public read on `public/*` prefix only, uploaded file to `public/` and verified public access, confirmed `test.txt` at root was blocked (403)
4. Updated policy to `/*`, enabled static website hosting, uploaded `index.html`, accessed live website via S3 website endpoint
5. Generated presigned URL for `test.txt` with 300 second expiry — confirmed access via browser
6. Deleted bucket (required deleting all versions + delete markers first due to versioning)

**Key commands:**
```bash
# Bucket operations
aws s3 mb s3://bucket-name
aws s3 cp file.txt s3://bucket-name/
aws s3 ls s3://bucket-name/
aws s3 presign s3://bucket-name/file.txt --expires-in 300

# Versioning
aws s3api put-bucket-versioning --bucket bucket-name \
  --versioning-configuration Status=Enabled
aws s3api list-object-versions --bucket bucket-name --prefix file.txt

# Cleanup versioned bucket
aws s3 rm s3://bucket-name --recursive   # removes current versions
aws s3api delete-objects --bucket bucket-name \
  --delete "$(aws s3api list-object-versions \
  --bucket bucket-name \
  --query '{Objects: Versions[].{Key:Key,VersionId:VersionId}}' \
  --output json)"
aws s3api delete-objects --bucket bucket-name \
  --delete "$(aws s3api list-object-versions \
  --bucket bucket-name \
  --query '{Objects: DeleteMarkers[].{Key:Key,VersionId:VersionId}}' \
  --output json)"
aws s3 rb s3://bucket-name
```

---

## Key Concepts to Remember

- **User data** runs once at first boot as root — check `/var/log/cloud-init-output.log` if it doesn't work
- **AMIs capture root volume only** — extra EBS volumes don't come along
- **IMDSv2 requires a token** — plain curl to 169.254.169.254 returns nothing on new instances
- **Instance store is ephemeral** — gone when instance stops. EBS persists.
- **S3 keys are flat strings** — no real folders, slashes are just characters
- **Block Public Access overrides bucket policies** — must disable it before any public access works
- **Versioned buckets** can't be deleted until all versions AND delete markers are removed
- **Presigned URLs expire** — the credentials are embedded in the URL itself

## Interview Questions to Know

- What's the difference between instance store and EBS?
- How does versioning work when you delete an S3 object?
- What's IMDSv2 and why does it matter?
- When would you use a spot instance?
- What EBS type for a high-traffic database?
- What happens to your root EBS volume when you terminate an instance?
- What's a presigned URL and when would you use it?
- Difference between SSE-S3 and SSE-KMS?
- S3 object is private but bucket policy says public — why can't anyone access it?
