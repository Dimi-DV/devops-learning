# Supply Chain Exposure Audit: Mini Shai-Hulud Campaign

| | |
| --- | --- |
| **Report ID** | SEC-2026-05-12-001 |
| **Date** | 2026-05-12 |
| **Author** | Dimitrije Davidovic Vedda |
| **Environment** | `labvm` — Ubuntu 24.04, UTM on Apple M2 host |
| **Repository in scope** | `github.com/Dimi-DV/devops-learning` |
| **Incident reference** | Mini Shai-Hulud / TeamPCP, May 11–12, 2026 |
| **Related identifiers** | CVE-2026-45321, GHSA-g7cv-rxg3-hmpx |
| **Status** | Closed — no exposure identified |
| **Severity (this environment)** | None (informational) |
| **Time to complete audit** | ~25 minutes |

---

## 1. Summary

Between May 11 and May 12, 2026, an active supply chain campaign known as Mini Shai-Hulud, attributed to threat group TeamPCP, compromised 172 unique packages across 403 malicious versions on the npm and PyPI registries. The payload is a credential-stealing worm that targets AWS, GCP, Azure, GitHub, npm, Vault, and Kubernetes credentials, with specific tradecraft for extracting GitHub Actions OIDC tokens from runner memory.

A targeted audit of the `devops-learning` development environment was performed on May 12, 2026, focused on three exposure surfaces: declared dependencies, recently executed package installs, and GitHub Actions workflow configuration. **No indicators of compromise were identified, and no compromised packages are present in any project dependency tree.** No remediation actions were taken; hardening recommendations are listed in Section 7.

---

## 2. Background

The Mini Shai-Hulud campaign is the fourth documented wave of the broader Shai-Hulud worm toolchain and the third confirmed operation by TeamPCP, following the Aqua Security Trivy scanner compromise (March 2026) and the Bitwarden CLI npm package compromise (April 2026).

### 2.1 Initial access vector

The campaign's index case was a malicious pull request against the public `TanStack/router` GitHub repository on May 11 at 10:49 UTC. The attacker exploited a `pull_request_target` workflow misconfiguration ("Pwn Request" pattern), poisoned the GitHub Actions cache across the fork-to-base trust boundary, and extracted the publishing OIDC token from runner memory mid-workflow. Packages were then published using the legitimate maintainer's identity, producing artifacts that carried valid SLSA provenance — the first such case publicly documented.

### 2.2 Payload behavior

On installation or import, the payload downloads the Bun JavaScript runtime, executes an obfuscated 2.3 MB credential stealer, and harvests credentials from the host environment. Targeted credential surfaces include:

- AWS access keys, session tokens, and EC2 IMDS metadata (`169.254.169.254`)
- GCP and Azure cloud credentials
- GitHub tokens (`ghp_`, `gho_`, `ghs_` prefixes)
- npm publish tokens
- GitHub Actions OIDC tokens (extracted from runner process memory)
- HashiCorp Vault tokens
- Kubernetes service account tokens and `~/.kube/config`
- SSH private keys and environment variables

The payload includes a destructive wipe routine triggered by npm token revocation, which has implications for the order of incident response steps (image first, then revoke).

### 2.3 Self-propagation

After credential exfiltration, the worm enumerates additional packages owned by compromised maintainer identities and publishes infected versions of each. This is the mechanism by which the campaign expanded from the TanStack ecosystem to UiPath, Mistral AI, OpenSearch, Guardrails AI, and Intercom packages within hours of initial publication.

---

## 3. Scope

The audit covered the following environment surfaces:

| Surface | Rationale |
| --- | --- |
| Python `requirements.txt` files across all project directories | Direct dependency declarations on the affected PyPI ecosystem |
| `package.json` / `package-lock.json` files | Direct dependency declarations on the affected npm ecosystem |
| `pyproject.toml` files | Modern Python dependency declarations |
| Active Python virtual environments | Confirmed resolved transitive dependencies |
| GitHub Actions workflow files | `pull_request_target` trigger usage (initial access vector) |
| Shell history for the audit window (May 11–12) | Recent `pip install` / `npm install` execution against unpinned specs |

Out of scope for this audit: production AWS resources (no recent infrastructure deployments occurred in the attack window), Terraform state (no module installs in the window), and Docker base images (separate audit scope).

---

## 4. Methodology

Five command sequences were executed against the working tree at `~/devops-learning`. Each is documented in Appendix A. The methodology was designed to fail closed — if any check returned an ambiguous result, the next step was full credential rotation rather than further investigation.

The five checks, in execution order:

1. Enumerate all dependency manifest files in the repository
2. Search all files for compromised package names from the published IOC list
3. Cross-check installed packages inside the active Python venv against the same list
4. Inspect GitHub Actions workflow files for the `pull_request_target` trigger
5. Inspect timestamped shell history for `pip install` or `npm install` invocations during the attack window

---

## 5. Findings

### 5.1 Dependency manifests (PASS)

Three Python `requirements.txt` files exist in the repository. No `package.json`, `package-lock.json`, or `pyproject.toml` files were found.

| Path | Contents |
| --- | --- |
| `week4/day23/healthy-app/requirements.txt` | `flask==3.0.0`, `psycopg2-binary==2.9.9`, `pytest==8.3.4` |
| `week4/day22/compose-app/requirements.txt` | `flask==3.0.0`, `psycopg2-binary==2.9.9` |
| `week4/day22/flask-app/requirements.txt` | *(empty file)* |

All declared dependencies use exact version pins (`==`). None of the declared package names appear on the IOC list. The empty `flask-app/requirements.txt` is a hygiene observation, not a security finding; see Section 7.

### 5.2 IOC name search across repository tree (PASS)

A recursive grep for compromised package names returned no matches in source files. Four superficial matches were investigated and dismissed as false positives:

| Match location | Determination |
| --- | --- |
| `.venv/lib/python3.12/site-packages/pip/_vendor/rich/_emoji_codes.py` (two matches) | String literals `"cloud_with_lightning"` and `"cloud_with_lightning_and_rain"` — Unicode weather emoji names in pip's vendored `rich` library. Not a package reference. |
| `.venv/lib/python3.12/site-packages/pip/_vendor/rich/__pycache__/_emoji_codes.cpython-312.pyc` | Compiled bytecode of the file above. Same content. |
| `.venv/lib/python3.12/site-packages/pycodestyle-2.12.1.dist-info/METADATA` | Documentation reference to a "lightning talk at PyCon 2016." Not a package reference. |

### 5.3 Installed package set in active venv (PASS)

The active virtual environment at `week4/day23/healthy-app/.venv/` was activated and inspected directly. Total installed package count: 19, consistent with the expected transitive closure of Flask, pytest, and psycopg2-binary. Targeted grep against compromised names returned no matches.

### 5.4 GitHub Actions workflow configuration (PASS)

No `pull_request_target` triggers are configured in any workflow file under `.github/workflows/`. The initial access vector for this campaign is not present in this environment.

### 5.5 Recent package installation activity (PASS)

A single `pip install` was executed during the audit-relevant window:

| Timestamp | Command | Target |
| --- | --- | --- |
| 2026-05-12 12:15:57 UTC | `pip install -r requirements.txt` | `week4/day23/healthy-app/` venv |

The install was executed against a fully pinned `requirements.txt` (Section 5.1), and the resulting venv contents have been verified against the IOC list (Section 5.3). No `npm install` invocations occurred in the audit window.

---

## 6. Risk Assessment

Residual risk to this environment is assessed as **negligible**. The reasoning:

The compromised packages span three ecosystems — JavaScript frontend (TanStack), AI/ML SDKs (Mistral, Guardrails, Lightning), and enterprise RPA (UiPath) — none of which intersect with the dependency surface of a minimal Flask web application. The repository's only Python dependencies are Flask 3.0.0, psycopg2-binary 2.9.9, and pytest 8.3.4, all of which have well-characterized dependency trees that do not transitively pull from the affected packages. The repository contains no JavaScript or TypeScript code and no npm-managed dependencies.

The single `pip install` that occurred during the campaign window was executed against an exact-version manifest, which would have rejected any attacker-published "latest" version regardless of registry state. The active venv has been verified.

The initial access vector (`pull_request_target` with checkout of fork-controlled code) is not present in any workflow file in this repository.

Conclusion: no credentials require rotation, no images require rebuilding, no infrastructure requires redeployment.

---

## 7. Recommendations

The following hardening measures are recommended for ongoing development practice, ordered by leverage. None are required for this incident; all are preventive against future campaigns of this class.

**7.1 Adopt transitive dependency locking.** Top-level pins (`flask==3.0.0`) constrain only the directly declared package. Transitive dependencies (`werkzeug`, `jinja2`, `markupsafe`, etc.) resolve to whatever satisfies the top-level package's own version ranges at install time. A compromise of a transitive dependency would not be caught by the current setup. Migrate to `pip-tools` (`pip-compile` → `requirements.lock`) or `uv` (`uv.lock`) for full-tree pinning. Estimated effort: 15 minutes per project.

**7.2 Add automated dependency scanning to CI.** Run `pip-audit` (Python) and `npm audit` (Node, when applicable) as a required job in the GitHub Actions pipeline. Fail the build on high-severity findings. This catches known-vulnerable versions before they reach a running environment.

**7.3 Add a `SECURITY.md` to portfolio repositories.** A brief disclosure policy, supply chain hygiene statement, and IOC monitoring approach is a low-effort artifact that signals security awareness to recruiters reviewing the GitHub profile.

**7.4 Remove or populate the empty `week4/day22/flask-app/requirements.txt`.** An empty manifest is ambiguous — it may indicate "no dependencies" or "forgotten to populate." Either remove the file or add an explicit comment stating its intent.

**7.5 Scope GitHub Actions IAM roles to minimum required permissions.** The current OIDC-assumed role for ECR pushes should be reviewed to confirm it grants only ECR push permissions, with no broader IAM, S3, or EC2 access. If the runner is ever compromised, the blast radius is limited to what the assumed role can do.

**7.6 Maintain the existing OIDC-based authentication pattern.** The current CI/CD pipeline uses GitHub Actions OIDC to assume an AWS role rather than long-lived access keys stored as repository secrets. This is the correct posture and should not be regressed. Note: the OIDC token itself was the target of this campaign — short-lived tokens limit but do not eliminate exposure when the runner is compromised.

---

## Appendix A — Audit commands executed

```bash
# Working directory
cd ~/devops-learning

# Check 1: enumerate dependency manifests
find . -name 'requirements.txt' \
    -o -name 'package.json' \
    -o -name 'package-lock.json' \
    -o -name 'pyproject.toml'

# Check 2: IOC name search across repo tree
grep -rE '@tanstack|@uipath|@mistralai|@opensearch-project|mistralai|guardrails-ai|lightning|pytorch-lightning|intercom-client|bitwarden/cli|trivy-action|setup-trivy' .

# Check 3: inspect active venv contents
source week4/day23/healthy-app/.venv/bin/activate
pip list | wc -l
pip list | grep -iE 'mistralai|guardrails|lightning|intercom|tanstack|uipath|opensearch'
deactivate

# Check 4: scan workflows for the initial access trigger
grep -rn 'pull_request_target' .github/workflows/

# Check 5: review pip/npm install activity during attack window
HISTTIMEFORMAT='%F %T ' history | grep -E 'npm install|pip install' | tail -50

# Inspect manifest contents
cat week4/day23/healthy-app/requirements.txt
cat week4/day22/flask-app/requirements.txt
cat week4/day22/compose-app/requirements.txt
```

---

## Appendix B — Indicators of Compromise (selected, public)

Compromised package scopes published during the May 11–12 window:

- npm: `@tanstack/*` (42 packages), `@uipath/*` (65 packages), `@mistralai/*`, `@opensearch-project/opensearch`, `@draftlab/*`, `@squawk/*`
- PyPI: `mistralai==2.4.6`, `guardrails-ai==0.10.1`, `lightning==2.6.2`, `lightning==2.6.3` (this last from the immediately preceding wave)

Earlier waves attributed to the same group (TeamPCP):
- `@bitwarden/cli` (April 2026)
- `trivy-action`, `setup-trivy` (March 2026, CVE-2026-33634)
- SAP CAP framework npm packages (late April 2026)

Behavioral indicators (informational; not used in this audit):
- Outbound traffic to `83.142.209.194` (PyPI second-stage payload host)
- Bun runtime download from `github.com/oven-sh/bun/releases/`
- Anomalous User-Agent: `mozilla/4.0 (compatible; msie 8.0; windows nt 5.1; trident/4.0)` (IE 8 / Windows XP fingerprint, reliable detection signal in 2026)
- Unauthorized files named `router_init.js`, `setup.mjs`, or `codeql_analysis.yml` in unexpected locations

---

## Appendix C — References

- Mend.io, *Mini Shai-Hulud Is Back: 172 npm and PyPI Packages Compromised in Latest Wave* (May 12, 2026)
- Snyk, *TanStack npm Packages Hit by Mini Shai-Hulud* (May 12, 2026)
- StepSecurity, *Mini Shai-Hulud Self-Spreading Supply Chain Attack* (May 12, 2026)
- SafeDep, *Mass Supply Chain Attack Hits TanStack, Mistral AI npm and PyPI Packages* (May 12, 2026)
- Socket, *lightning PyPI Package Compromised in Supply Chain Attack* (April 30, 2026)
- The Register, *Ongoing supply chain attacks worm into SAP npm packages* (April 30, 2026)
- GitHub Security Advisory GHSA-g7cv-rxg3-hmpx
- CVE-2026-45321

---

*End of report.*
