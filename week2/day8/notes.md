# Day 8 — AWS IAM Deep Dive

## Core Concepts

### Identity Types
- **Root user** — unrestricted, can't be locked down. Enable MFA, never use it. Only for initial setup and billing edge cases.
- **IAM Users** — permanent identity with password and/or access keys. For humans needing long-term access.
- **Groups** — collections of users sharing policies. Not identities themselves — can't log in as a group or reference in policies.
- **Roles** — temporary identity assumed by services, instances, or cross-account principals. Issues short-lived credentials via STS. Preferred over users for anything non-human.

### Policy Types
- **AWS Managed** — maintained by AWS, often too broad for production
- **Customer Managed** — you write them, reusable across identities, version-controlled
- **Inline** — embedded in a single identity, deleted with it. Hard to audit, use sparingly.
- **Resource-based** — attached to the resource itself (S3 bucket policy, KMS key policy)

---

## Policy JSON Structure

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "HumanReadableLabel",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::my-bucket",
        "arn:aws:s3:::my-bucket/*"
      ],
      "Condition": {
        "Bool": {
          "aws:MultiFactorAuthPresent": "true"
        }
      }
    }
  ]
}
```

**Key fields:**
- `Effect` — `Allow` or `Deny`. Default for everything is implicit deny.
- `Principal` — only in resource-based policies and trust policies. Never in identity-based policies.
- `Action` — AWS API calls, format `service:Action`. Use `NotAction` for inverse (everything except).
- `Resource` — ARN of the target. S3 needs two ARNs: bucket + `bucket/*` for object operations.
- `Condition` — operators: `StringEquals`, `StringNotEquals`, `Bool`, `IpAddress`, `DateLessThan`

**Evaluation order:** Explicit Deny > Explicit Allow > Implicit Deny. Explicit Deny can never be overridden.

---

## Policy Exercises Completed

### Scenario 1 — S3 Read (finance-reports bucket)
Key lesson: S3 splits at two levels. `ListAllMyBuckets` needs `Resource: *`. `ListBucket` needs the bucket ARN. `GetObject` needs `bucket/*`. Three separate statements.

### Scenario 2 — Full EC2, us-east-1 only
Key lesson: Condition on Allow creates implicit deny elsewhere, but explicit Deny with `StringNotEquals` is production-grade — can't be overridden by other policies.

```json
"Condition": { "StringEquals": { "aws:RequestedRegion": "us-east-1" } }
```

### Scenario 3 — Lambda execution role (DynamoDB + CloudWatch Logs)
Key lesson: CloudWatch Logs always needs two resource ARNs:
```
arn:aws:logs:...:log-group:/aws/lambda/*        ← the group
arn:aws:logs:...:log-group:/aws/lambda/*:*      ← streams inside it
```
Always include all three actions: `CreateLogGroup`, `CreateLogStream`, `PutLogEvents`.

### Scenario 4 — MFA enforcement guardrail
Key lesson: `NotAction` is the inverse of `Action` — deny everything except these. Combined with `Effect: Deny` and `aws:MultiFactorAuthPresent: false`, this blocks all access until MFA is used. Bool condition values are strings in IAM JSON (`"false"` not `false`).

```json
{
  "Effect": "Deny",
  "NotAction": ["iam:GetUser", "iam:CreateVirtualMFADevice", "iam:EnableMFADevice", ...],
  "Resource": "*",
  "Condition": { "Bool": { "aws:MultiFactorAuthPresent": "false" } }
}
```

### Scenario 5 — EC2 instance role (ECR + CloudWatch Logs)
Key lesson: IAM controls AWS API calls, not OS commands. `docker pull` is the client command — `ecr:BatchGetImage` is the underlying API call IAM actually sees. Never put shell commands in `Action`.

ECR requires two statements:
- `ecr:GetAuthorizationToken` on `Resource: *` (account-level call)
- `ecr:BatchCheckLayerAvailability`, `ecr:BatchGetImage`, `ecr:GetDownloadUrlForLayer` on `arn:aws:ecr:...:repository/*`

---

## Instance Profiles
Container that holds an IAM role for EC2. The EC2 metadata service (`169.254.169.254`) provides auto-rotating temporary credentials to the instance. AWS SDK uses these automatically — never put access keys on an instance.

```
EC2 Instance → Instance Profile → IAM Role → Permissions
```

---

## Cross-Account Access (Conceptual)
Two documents required:

**Trust policy** (on the role in Account B) — who can assume it:
```json
{
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::ACCOUNT-A-ID:root" },
  "Action": "sts:AssumeRole"
}
```

**Permissions policy** (on the role in Account B) — what it can do.

Both the trust policy AND the caller's permission to call `sts:AssumeRole` must be in place.

---

## AWS CLI — IAM Commands

```bash
# Identity check — run this first when debugging
aws sts get-caller-identity

# Users
aws iam list-users
aws iam create-user --user-name cli-test-user
aws iam create-access-key --user-name cli-test-user
aws iam delete-user --user-name cli-test-user

# Groups
aws iam create-group --group-name developers
aws iam add-user-to-group --group-name developers --user-name cli-test-user
aws iam attach-group-policy --group-name developers --policy-arn arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
aws iam list-attached-group-policies --group-name developers

# Custom policies from file
aws iam create-policy --policy-name MyPolicy --policy-document file://policy.json
aws iam list-policies --scope Local

# Attach to user
aws iam attach-user-policy --user-name cli-test-user --policy-arn arn:aws:iam::123456789012:policy/MyPolicy
aws iam list-attached-user-policies --user-name cli-test-user
```

---

## Profiles — ~/.aws/credentials and ~/.aws/config

```ini
# ~/.aws/credentials
[default]
aws_access_key_id = AKIA...
aws_secret_access_key = ...

[readonly]
aws_access_key_id = AKIA...
aws_secret_access_key = ...
```

```ini
# ~/.aws/config
[default]
region = us-east-1
output = json

[profile readonly]       ← note: "profile" prefix required here, not in credentials
region = us-east-1
output = json
```

**Switching profiles:**
```bash
# Per command
aws s3 ls --profile readonly

# Whole session
export AWS_PROFILE=readonly
aws sts get-caller-identity   # verify
unset AWS_PROFILE             # back to default

# Single command inline
AWS_PROFILE=readonly aws s3 ls
```

---

## CLI Exercise — TODO (complete tomorrow)
- [ ] `aws sts get-caller-identity` — verify admin-user
- [ ] `aws iam list-users`
- [ ] Create cli-test-user, create access keys
- [ ] Attach S3ReadOnly managed policy
- [ ] `aws configure --profile cli-test`
- [ ] Test: `AWS_PROFILE=cli-test aws s3 ls` (should work) vs EC2 (should fail)
- [ ] Clean up: detach policy, delete access key, delete user

---

## Key Principles to Remember
- `Principal` only appears in resource-based policies and trust policies — never identity-based
- S3 always needs two resource ARNs for most operations (bucket + bucket/*)
- CloudWatch Logs always needs two resource ARNs (log group + log group:*)
- Explicit Deny beats everything — use it when you need a guarantee, not just implicit deny
- `NotAction` = deny everything except this list
- Bool condition values are strings: `"true"` / `"false"`
- IAM sees API calls, not shell commands
- `aws sts get-caller-identity` is your first debugging move, always
