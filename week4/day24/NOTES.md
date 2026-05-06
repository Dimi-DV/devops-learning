# Day 24 — CI/CD with GitHub Actions + ECR

## What this day built

Automated the manual Docker build/push flow from Day 23 into a GitHub Actions pipeline. End state: `git push` triggers lint → test → build → push to ECR, with no static AWS credentials anywhere in the system.

The Flask app (`week4/day23/healthy-app/`) is the target. Everything in this day's work either lives in the app directory, in `.github/workflows/ci.yml`, or in this `week4/day24/` directory.

---

## Pipeline shape

```
git push (week4/day24 or main, paths under healthy-app/**)
        ↓
GitHub schedules workflow
        ↓
Job: Lint (flake8)        ← fresh runner, ~13s
        ↓ needs:
Job: Test (pytest)        ← fresh runner, ~10s
        ↓ needs:
Job: Build and push       ← fresh runner, ~20s
        ↓
ECR: healthy-app:<sha> + healthy-app:latest
```

Three jobs, three ephemeral runners. `needs:` orders them; nothing else shares state between them. Each job re-runs `actions/checkout` and `pip install` because its runner starts empty.

---

## Files added or modified

- `.github/workflows/hello.yml` — minimal workflow used to verify the trigger mechanism. Kept as a debug aid.
- `.github/workflows/ci.yml` — the real pipeline.
- `week4/day23/healthy-app/.flake8` — flake8 config (max line length 120).
- `week4/day23/healthy-app/tests/__init__.py` — makes tests/ a package for pytest discovery.
- `week4/day23/healthy-app/tests/test_app.py` — 3 pytest tests against routes that don't require a database.
- `week4/day23/healthy-app/requirements.txt` — added pytest 8.3.4, flake8 7.1.1.
- `week4/day23/healthy-app/app.py` — fixed PEP 8 violations surfaced by flake8 (mostly E302 — missing blank lines between top-level defs).
- `week4/day24/github-actions-ecr-policy.json` — IAM permissions policy scoped to ECR push on healthy-app repository only.
- `week4/day24/github-actions-trust-policy.json` — IAM trust policy for OIDC role, restricting assumption to this repo + specific branches.
- `.gitignore` — added Python ignores (`.venv/`, `venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`).

---

## Core mental model: GitHub Actions runners

**Each job runs on its own fresh, ephemeral, isolated VM that gets destroyed when the job ends.** This is the single most important concept.

- A workflow contains jobs. Jobs run in parallel by default; `needs:` chains them.
- A job runs on one fresh runner (Ubuntu VM) provisioned at job start.
- A job contains steps. Steps run sequentially on the same runner and share state.
- A step is either `run:` (shell command) or `uses:` (a marketplace action).
- When the job ends, the runner is destroyed. Nothing persists between jobs.

Implications:
- Every job re-runs `actions/checkout@v4` because its runner has no code yet.
- Every job re-installs dependencies because its runner has no packages.
- `needs: lint` is *scheduling order only* — it does NOT share state with the dependent job.
- This is why credentials/state must come from external sources (secrets, OIDC, artifacts).

---

## Triggers and path filtering

```yaml
on:
  push:
    branches: [week4/day24, main]
    paths:
      - 'week4/day23/healthy-app/**'
      - '.github/workflows/ci.yml'
  pull_request:
    branches: [main]
    paths:
      - 'week4/day23/healthy-app/**'
      - '.github/workflows/ci.yml'
```

- `paths:` scopes runs to commits that actually changed app code. Doc-only commits don't burn runner minutes.
- Including `.github/workflows/ci.yml` in the path filter ensures workflow edits trigger their own validation run — easy to forget, frustrating to debug.
- `pull_request` trigger enables "require CI to pass before merge" branch protection later.

---

## Quality gates (the CI part)

### Lint: flake8
- Wraps three tools: pycodestyle (PEP 8), pyflakes (likely bugs), mccabe (complexity).
- Exit code 0 = clean, 1 = violations found.
- Config in `.flake8` sets `max-line-length = 120` (industry default beats PEP 8's 79).
- Common errors fixed in app.py: E302 (need 2 blank lines before top-level defs), E305 (need 2 blank lines after function block), W391 (trailing blank line), W292 (missing newline at EOF).

### Test: pytest
- Tests in `tests/test_app.py` use Flask's `test_client()` fixture — exercises routes in-process, no real network or DB.
- Only the `/` route is tested because all other routes require a Postgres connection.
- Day 25 will add a Postgres service container to test DB-dependent routes properly.
- 3 tests pass in ~0.05s. Unit tests should be fast.

### Build: Docker
- Uses `docker/build-push-action@v5` instead of raw `docker build` shell commands.
- `platforms: linux/amd64` is critical: GitHub runners are x86_64; without explicit pinning a multi-arch builder might produce arm64 images that fail on ECS Fargate with `exec format error`.
- Two tags pushed per image:
  - `${{ github.sha }}` — immutable, permanently linked to the commit
  - `latest` — mutable convenience tag (never deploy `latest` to production)

---

## AWS authentication: two paths implemented

### Path A: Long-lived access keys (implemented and then removed)

1. Created dedicated IAM user `github-actions-ci`.
2. Wrote scoped IAM policy `GitHubActionsECRPushHealthyApp`:
   - `ecr:GetAuthorizationToken` on `*` (required — this action is account-level, can't be resource-scoped)
   - 7 specific ECR push/pull actions on `arn:aws:ecr:us-east-1:042729137214:repository/healthy-app` only
3. Generated access key, stored in GitHub Secrets as `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`.
4. Workflow used:
   ```yaml
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
       aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
       aws-region: us-east-1
   ```

**Downside:** keys live until manually rotated. Leaks (accidental commit, compromised laptop, malicious action) give persistent AWS access.

### Path B: OIDC federation (current state)

1. Created OIDC identity provider in AWS account, pointing at `token.actions.githubusercontent.com`. One-time, account-wide setup.
2. Created IAM role `github-actions-ecr-push` with trust policy that:
   - Allows assumption only by the federated GitHub OIDC provider
   - Validates the token's `aud` claim is `sts.amazonaws.com`
   - Validates the token's `sub` claim matches `repo:Dimi-DV/devops-learning:ref:refs/heads/{main,week4/day24}` only
3. Attached the same `GitHubActionsECRPushHealthyApp` policy to the role.
4. Workflow updated to:
   ```yaml
   permissions:
     id-token: write   # required for OIDC token request
     contents: read    # required for actions/checkout
   ...
   - uses: aws-actions/configure-aws-credentials@v4
     with:
       role-to-assume: arn:aws:iam::042729137214:role/github-actions-ecr-push
       aws-region: us-east-1
   ```
5. Deleted access key, detached policy from user, deleted user, deleted GitHub Secrets.

**Auth flow at runtime:**
```
GitHub Actions runner
    ↓ requests OIDC token from GitHub (id-token: write permission required)
GitHub mints short-lived JWT with claims (repo, ref, sha, etc.)
    ↓ runner calls sts:AssumeRoleWithWebIdentity with JWT
AWS validates JWT signature against GitHub's published keys
AWS evaluates trust policy: aud match? sub match?
    ↓ if all pass
AWS issues temporary credentials (~1 hour validity)
    ↓ runner uses them for ECR auth and push
```

No long-lived AWS credentials exist anywhere. Token expires when the run ends.

---

## IAM concepts solidified today

- **Users vs roles:** Users have long-lived credentials and are persistent identities. Roles have no credentials of their own — they're permission sets that other identities (federated OIDC, EC2 instance profiles, etc.) temporarily assume. Roles are how AWS does temporary, scoped, federated access.
- **The same permissions policy can be attached to multiple principals.** `GitHubActionsECRPushHealthyApp` was attached to a user and a role simultaneously during the Path A → Path B migration. Detachment doesn't delete the policy.
- **Trust policy vs permissions policy:** The trust policy answers "who can assume this role?" The permissions policy answers "what can the assumer do?" Both required for a usable role.
- **`StringLike` vs `StringEquals` in trust conditions:** `StringLike` supports wildcards in the `sub` claim (e.g., `refs/heads/release/*`). Conventional choice even when wildcards aren't used today.

---

## What we built vs what we deliberately didn't

**Built:** Continuous Integration + Continuous Delivery
- Every push validated (lint, test, build)
- Successful builds produce a deployable artifact in ECR

**Did NOT build:** Continuous Deployment
- ECS service is not auto-updated when new images land
- Adding deploy = one CLI command (`aws ecs update-service --force-new-deployment`) or one workflow step
- Deliberately deferred: production teams typically gate deploys with manual approval (environment protection rules, change windows). Continuous *delivery* is the responsible default; continuous *deployment* is a riskier choice that requires extra safeguards.

---

## Verification commands

Confirm OIDC role exists and is configured correctly:
```bash
aws iam get-role --role-name github-actions-ecr-push
aws iam list-attached-role-policies --role-name github-actions-ecr-push
```

Confirm old access-key user is gone:
```bash
aws iam get-user --user-name github-actions-ci   # expects NoSuchEntity error
```

List images in ECR:
```bash
aws ecr list-images --repository-name healthy-app \
  --query 'imageIds[?imageTag!=null].[imageTag,imageDigest]' \
  --output table | cat
```

Validate workflow YAML locally before pushing:
```bash
python3 -c "
import yaml
data = yaml.safe_load(open('.github/workflows/ci.yml'))
print('Top-level keys:', list(data.keys()))
print('Jobs:', list(data['jobs'].keys()))
"
```

---

## Lessons learned (failure modes encountered)

1. **YAML indentation matters more than expected.** A single misindented job key produces `Unexpected value 'build-and-push'` errors. Two-space indents, no tabs, validate locally before pushing.
2. **VS Code save discipline.** Editing a file without saving it before running `git status` produces "nothing to commit" confusion. Enable auto-save or watch the dot indicator on the tab.
3. **Linters surface real bugs disguised as style.** flake8's E302 "missing blank lines" caught structural issues in app.py that would've shipped otherwise. Treat lint failures as blocking, not advisory.
4. **`pip install --break-system-packages` is not the right answer.** Ubuntu's `python3.12-venv` package is required; the venv is the right discipline regardless of how isolated the environment seems.
5. **Two distinct CI failure modes to recognize:**
   - YAML/structural errors: workflow never schedules a runner. Surfaces as a banner on the run page.
   - Runtime errors: runner spins up, step fails with non-zero exit. Surfaces in step logs. Subsequent steps are skipped.
6. **Mac M2 → ECS Fargate gotcha:** local `docker build` defaults to arm64; Fargate runs amd64. Always pin `platforms: linux/amd64` in CI for ECS targets, or use multi-arch builds.

---

## Interview talking points this day produces

- "My CI/CD pipeline authenticates to AWS via OIDC federation — no static credentials stored in GitHub."
- "Trust policy restricts role assumption to my specific repo and only `main` plus the working branch, so feature branches can't deploy."
- "Permissions policy is least-privilege, scoped to ECR push on a single repository."
- "Pipeline runs lint, tests, and a platform-pinned Docker build, then pushes with both an immutable per-commit tag and a latest tag."
- "I deliberately stopped at delivery, not full continuous deployment, because production deploys should have a controlled promotion step."
- "Build action handles caching automatically; I didn't hand-roll Docker commands because that loses caching, retries, and structured logging."

---

## What comes next (Day 25)

- Advanced GitHub Actions: matrix testing across Python versions, branch protection rules, status badges, reusable workflows.
- Terraform in CI/CD: `terraform fmt -check` + `terraform validate` + `terraform plan` on PRs, `terraform apply` on merge to main. Same pattern as today (runner authenticates to AWS via OIDC), different artifact (infrastructure changes instead of container images).
- Likely revisit: pip caching via `actions/setup-python`'s built-in cache, splitting requirements into runtime vs dev dependencies.

---

## Cost summary

- GitHub Actions: free tier covers all of today's runs (2,000 minutes/month for public repos, free for this repo's tier).
- ECR storage: ~free tier (under 500MB total in the repo).
- AWS API calls (IAM, STS, ECR auth): negligible.
- Total day cost: ~$0.

No persistent infrastructure created beyond IAM resources (free) and the ECR repository (~free). The pipeline can run unbounded times without ongoing cost.
