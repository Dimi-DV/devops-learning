# Day 22 — Docker Fundamentals

**Date:** Friday, May 1, 2026
**Hours covered:** 1–4 of 6–7 (volume mounts in depth + Docker Compose moved to Day 23)
**Branch:** `week4/day22`

---

## Conceptual foundation

### What a container actually is
A container is a **process** running on the host that *thinks* it has its own filesystem, network, and process tree, but is actually using the host's kernel. It is not a VM. No second OS boots. Isolation comes from kernel features (namespaces for PIDs/network/mounts, cgroups for CPU/memory limits, capabilities for permissions).

The shipping container metaphor: package an app + its libs + its config into one standardized format, and any host running Docker can run it identically. Kills "works on my machine."

### VMs vs containers — the real difference
Both partition one machine into isolated workloads. The difference is **where** the isolation happens:

| | Hypervisor (VM) | Docker (container) |
|---|---|---|
| Sits between | Hardware ↔ guest OS | One running kernel ↔ processes |
| Per-app overhead | Full guest OS (GBs, seconds to boot) | Just the app's libs (MBs, milliseconds to start) |
| Isolation strength | Strong (kernel exploit stays in VM) | Weaker (shared kernel) |
| Can run | Any OS (Linux on Windows, etc.) | Only what works on host kernel |
| Density | ~10 VMs per host | ~100 containers per host |

When to reach for which:
- Untrusted multi-tenant workloads → VMs (or microVMs)
- Internal apps your team controls → containers (density + speed wins)
- Modern cloud answer → microVMs running containers (Fargate, Lambda container mode, Cloud Run) — best of both

### Lambda is not a Docker container
Lambda runs every invocation inside a **Firecracker microVM** — AWS's lightweight hypervisor for serverless. Each execution gets its own kernel. Since 2020, Lambda accepts Docker images as a *packaging format* (up to 10GB), but AWS unpacks them into Firecracker at runtime. Same for Fargate (ECS or EKS) — looks like Docker from your side, but each task runs in a microVM. Only ECS-on-EC2 actually uses the Docker daemon as the runtime.

Interview framing: "What's the difference between Lambda, Fargate, and ECS-on-EC2?" → who manages the isolation layer. AWS gives you progressively more control (and more responsibility) moving from Lambda → Fargate → ECS-on-EC2.

### Docker Hub as brew/pip equivalent
Same registry concept, but "installed package" doesn't apply — images are sandboxed artifacts, not modifications to the host system. Docker Hub = central public registry. ECR = private registry (own pip index / private brew tap).

### Docker architecture — three pieces to keep separate
1. **Docker client** (`docker` CLI) — translates commands into API calls. Doesn't do work itself.
2. **Docker daemon** (`dockerd`) — long-running background process, manages images/containers/networks/volumes. On Linux runs natively; on Mac runs inside a hidden Linux VM that Docker Desktop manages (which is why containers always need a Linux kernel somewhere).
3. **Registry** — where images live before reaching your machine (Docker Hub, ECR, GHCR).

Two concepts that confuse people:
- **Image** = read-only template (frozen filesystem snapshot). Pulled from registries.
- **Container** = running instance of an image. Same relationship as class:object, AMI:EC2 instance.

### What `docker run nginx` actually does
1. Client sends "run nginx" to daemon
2. Daemon checks if `nginx` image is local; if not, pulls from Hub
3. Daemon creates a thin writable layer on top of the read-only image
4. Daemon starts a process inside that filesystem with isolated namespaces
5. Returns container ID to client

### Image layers (the part that matters for Dockerfiles)
Images are stacks of read-only layers. Each Dockerfile instruction creates one layer. Two consequences:

1. **Pull is incremental** — pulling a 200MB image often only transfers 20MB because earlier layers (Ubuntu base, Python interpreter) are already on disk from previous pulls.
2. **Build is cached** — when rebuilding after a code change, only layers from the change downward rebuild. Earlier layers come from cache.

**The layer cache is daemon-wide, not directory-tied.** Layers live in `/var/lib/docker/`. A new project in a different directory will hit cache for any layer whose inputs are byte-identical to an existing one. Identical `requirements.txt` files across projects = shared `pip install` layer = free dependency-install cache hits across builds.

Cache key = instruction + its inputs (file content hashes for COPY). Once any layer misses, every layer after it misses too — there's no jumping back to cache further down the chain.

---

## The install problem (what happened, what fixed it)

`curl get.docker.com | sudo sh` succeeded but daemon wouldn't start. Error from journal:
```
failed to load listeners: no sockets found via socket activation:
make sure the service was started by systemd
```

**Conceptual cause:** Docker uses **socket activation** — two systemd units coordinate:
- `docker.socket` — creates `/run/docker.sock` listening socket
- `docker.service` — the daemon, which inherits the socket from the socket unit

When the install script upgraded from 28.2.2 to 29.4.2, it stopped both units and tried to restart the service, but the socket unit didn't come back up first. So `dockerd` started, looked for its inherited socket, found nothing, and bailed. systemd then retried fast enough to hit the rate limiter ("Start request repeated too quickly") and gave up.

**Fix:**
```bash
sudo systemctl daemon-reload
sudo systemctl reset-failed docker.service docker.socket
sudo systemctl start docker.socket          # socket FIRST
sudo systemctl start docker.service         # then service
sudo systemctl status docker
```

`reset-failed` clears the rate-limiter state. Start the socket first so the service has something to inherit when it comes up.

To use `docker` without `sudo`:
```bash
sudo usermod -aG docker $USER
newgrp docker        # or close + reopen SSH session
```

---

## Hands-on: running containers

### First containers
```bash
docker run hello-world                         # output narrates the architecture
docker run -d -p 8080:80 --name web nginx      # detached, port-mapped, named
docker ps                                      # running containers (-a includes stopped)
curl http://localhost:8080                     # nginx welcome HTML (NOT https — TLS not configured)
```

### Inspecting a running container
```bash
docker exec -it web bash                       # shell inside the container
ls /etc/nginx/                                 # nginx config
cat /etc/nginx/nginx.conf
# ps aux                                       # FAILS — not installed in the slim image
exit
docker top web                                 # process list from outside, uses host's tools
docker logs web                                # stdout/stderr from the container
```

**Key insight from `ps not found`:** an image holds **what your one app needs to run, nothing else**. The `nginx` image is ~70MB instead of 800MB precisely because `ps`, `top`, `vim`, `curl`, `ping`, compilers — all stripped out. Production images push this further (distroless = no shell at all).

**`docker top` lesson:** PIDs shown are the *host's* numbering (e.g., 6457). Inside the container that same nginx master is PID 1. Same processes, different lens — that's the PID namespace doing its job. Containers aren't magic; they're regular processes wearing a costume.

### Cleanup matters
Stopping a container does NOT delete it. The writable layer + config + logs persist until `rm`.
```bash
docker stop web
docker rm web
docker ps -a                                   # confirm gone
docker container prune                         # nuke all stopped containers
```

Two flags worth knowing:
- `docker run --rm ...` — auto-deletes container on exit. Standard for one-shot jobs.
- `docker run -d --restart=unless-stopped ...` — auto-restarts on crash or host reboot. Standard for long-running services.

---

## Volume mounts: bridging host filesystem into the container

### The capability
```bash
docker run -d -p 8080:80 --name web \
  -v ~/labs/week4/day22/site:/usr/share/nginx/html:ro \
  nginx
```

`-v host_path:container_path:mode` — host directory appears inside the container at that path. Same inode, no copy. Edit a file on the host, the running container sees it instantly. No image rebuild, no container restart.

### VMs vs containers on host filesystem access
VMs *can* mount host directories (UTM/VirtualBox/VMware shared folders) — the capability isn't unique to containers. The difference is **friction**:
- VM shared folder → emulated filesystem protocol (9p, virtio-fs) because the VM has its own kernel. Translation layer exists.
- Container bind mount → no translation. Container process is just a host process with a namespaced filesystem view.

Zero overhead = trivial enough to become daily workflow. The live-edit dev loop (edit on host, container reflects instantly) is the canonical pattern for the entire industry.

### Two volume types
- **Bind mount** (`-v /host/path:/container/path`) — mount a specific host path. Tight coupling to host layout. Used heavily in dev.
- **Named volume** (`-v mydata:/var/lib/postgres`) — Docker manages storage under `/var/lib/docker/volumes/`. Decouples data from any specific host path. Used in production for stateful workloads.

### Cloud-native pattern
**Separate compute from state.** Containers are ephemeral and stateless; persistent data lives in managed services (S3 for blobs, RDS for relational, DynamoDB for KV). Fargate doesn't even give you persistent host disk to bind-mount.

But volumes still matter in production:
- **Configuration injection** — secrets/config mounted at startup (ECS task definitions pull from SSM Parameter Store / Secrets Manager into mount points)
- **Hot caches** — local SSD caches that survive container restarts but not region failures
- **Self-managed stateful workloads** — Postgres in a container with EBS-backed volume when you don't want managed RDS pricing

**Containers should be cattle, not pets.** Destroy and recreate at will; state lives in volumes or external services.

---

## Building images with Dockerfiles

### Anatomy
- `FROM` — base image (almost always a language runtime or OS). Layer 1.
- `WORKDIR` — sets current directory inside image. Persistent.
- `COPY src dst` — copies files from build context into image.
- `RUN cmd` — executes at build time, bakes result into a new layer.
- `ENV key=value` — env vars that persist into running containers.
- `EXPOSE port` — documents listening port. Doesn't actually publish (that's `-p` at run time).
- `USER name` — switches to non-root user for everything that follows.
- `CMD ["..."]` — default command when container starts.

### Build context (the part that confuses people)
`docker build .` — the `.` is the **build context**, not where the Dockerfile is. Every file in that directory is uploaded to the daemon. `COPY` can only see files from the context. `COPY ../somefile .` doesn't work.

**`.dockerignore`** — excludes files from context upload. Same syntax as `.gitignore`. Makes builds faster and prevents leaking secrets into images.

### The Flask app build
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py .
ENV APP_VERSION=1.0.0
EXPOSE 5000
CMD ["python", "app.py"]
```

Build:
```bash
docker build -t flask-hello:1.0 .
```

`-t name:tag` tags the image. Without a tag you get a hash and have to reference by hash.

### Critical Flask gotcha
`app.run(host='0.0.0.0', port=5000)` — Flask's default is `127.0.0.1` (localhost-only). Inside a container that means "this container only" and port forwarding from the host won't reach it. **Listening on `0.0.0.0` is required for any containerized web app.** Single biggest reason new containerized apps appear broken.

### Layer order rule (interview-critical)
**Order Dockerfile instructions from least-likely-to-change to most-likely-to-change.** Base image → OS packages → language deps → your code.

Why: when you change `app.py` (50 times a day), Docker rebuilds only that layer + downstream. `pip install` stays cached → 1-2 second builds.

If you wrote `COPY . .` before `RUN pip install`, every code change invalidates the COPY layer, which invalidates pip install, which means every code edit triggers a fresh dependency install (30+ seconds each time).

### Why no Flask install on host was needed
The pip install runs **inside the image being built**, using the Python from the base image. The host VM doesn't need Python 3.11, doesn't need pip, doesn't need Flask. The Dockerfile says "start from a clean Python environment, install these deps, copy this code in." Docker provides everything inside the image.

This is the ergonomic win: the entire runtime environment ships with the app as one artifact. Laptop, CI runner, production server can be radically different — they just need Docker.

---

## Versioning conventions

Tags are **manual, mutable pointers** to immutable image digests. Docker doesn't auto-increment anything. Three valid conventions:

- **Semantic versioning** (`1.4.2`) — major.minor.patch. For releases.
- **Git SHA tags** (`abc1234`) — total reproducibility. CI builds use this.
- **Environment tags** (`:staging`, `:prod`) — moving pointers, applied alongside immutable version tags.

Typical CI build tags one image multiple ways:
```bash
docker build -t flask-hello:1.4.2 -t flask-hello:abc1234 -t flask-hello:latest .
```

**`latest` is not a version** — it's the default tag Docker uses when none is specified. Production deploys should NEVER pin `:latest`. Reproducibility = pinning a specific semver or SHA tag.

---

## Production-readiness upgrades (Hour 4)

### Three problems with the naive image
1. No `.dockerignore` (junk in build context)
2. Container runs as root (security issue)
3. Bloated with build toolchain (size + attack surface)

### Fix 1: `.dockerignore`
```
__pycache__
*.pyc
.git
.gitignore
.env
.venv
venv
.DS_Store
README.md
Dockerfile
.dockerignore
```
Excluding `.git` matters most — in a real repo it can be hundreds of MB.

### Fix 2: non-root user
```dockerfile
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser
```

Order matters — `useradd` is **after** `pip install` because pip needs root to write to system site-packages. Once deps are installed, never need root again.

Verify it worked:
```bash
docker exec -it flask whoami      # appuser
docker exec -it flask id          # uid=1000(appuser) gid=1000(appuser)
docker exec -it flask bash
apt update                         # FAILS — permission denied (the point)
```

Container root isn't host root (namespace isolation) but it's still way more privilege than the app needs. Defense in depth — costs nothing, matters every time something goes wrong.

### Fix 3: multi-stage build
Define multiple `FROM` stages. Heavy lifting in early stage, copy only needed artifacts into clean final stage. Final image = last stage; everything else discarded.

```dockerfile
# ---- Stage 1: builder ----
FROM python:3.11-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# ---- Stage 2: runtime ----
FROM python:3.11-slim AS runtime
WORKDIR /app
COPY --from=builder /app/deps /app/deps
COPY app.py .
ENV PYTHONPATH=/app/deps
RUN useradd --create-home --shell /bin/bash appuser \
 && chown -R appuser:appuser /app
USER appuser
ENV APP_VERSION=1.0.0
EXPOSE 5000
CMD ["python", "app.py"]
```

Key line: `COPY --from=builder /app/deps /app/deps` — copies the dependency directory across stages. Pip itself, apt cache, builder-only artifacts → all left behind.

`--target=/app/deps` flag makes pip install to a specific dir we can copy out cleanly. `ENV PYTHONPATH=/app/deps` tells Python where to find imports.

For Flask the size difference is small. For real workloads with build deps (C extensions, ML libraries, gcc toolchain), multi-stage routinely cuts images from 2GB → 300MB.

**Interview framing:** multi-stage separates the build environment from the runtime environment. Compilers, package managers, source maps, test files, dev deps — all needed at build time, all dangerous bloat at runtime. Each MB shipped is an MB attackers can search for vulns + an MB ECR transfers to every Fargate task at startup.

**Distroless** = the most aggressive version. `gcr.io/distroless/python3-debian12` — no shell, no package manager, no coreutils. Can't even `docker exec` in. Standard for serious production / regulated environments.

---

## Commands reference

### Image management
```bash
docker pull <image>                 # fetch from registry
docker images                       # list local images
docker images <name>                # filter
docker rmi <image>                  # remove image
docker history <image>              # show layers + sizes
docker tag <src> <dst>              # add a tag (no rebuild)
```

### Container lifecycle
```bash
docker run -d -p HOST:CONT --name N IMAGE     # start detached
docker ps                                      # running
docker ps -a                                   # include stopped
docker stop <name|id>                          # SIGTERM, SIGKILL after 10s
docker rm <name|id>                            # delete stopped container
docker container prune                         # delete all stopped
docker logs <name|id>                          # stdout/stderr
docker exec -it <name|id> bash                 # shell inside running container
docker top <name|id>                           # processes from outside
```

### Build
```bash
docker build -t name:tag .                     # `.` is build context
docker build -t name:tag -f Dockerfile.prod .  # custom Dockerfile path
```

### Disk usage
```bash
docker system df                               # space breakdown
docker system prune -a                         # nuke unused stuff
```

### Useful run flags
- `-d` detached
- `-p HOST:CONT` port forward
- `-v HOST:CONT[:ro]` volume mount
- `-e KEY=VALUE` env var (overrides Dockerfile ENV)
- `--name N` readable name
- `--rm` auto-delete on exit
- `--restart=unless-stopped` auto-restart on crash/reboot
- `-it` interactive + TTY (for shells)

---

## What's next (Day 23)

- Hour 5–6 Day 22 carry-over: Docker Compose with Flask + Postgres (multi-container app, networking by service name)
- Day 23 main topics:
  - Health checks in Dockerfiles
  - Resource limits (`--memory`, `--cpus`)
  - Image scanning for vulnerabilities (`docker scout cves`)
  - AWS ECR (push image to registry)
  - ECS Fargate first deployment

---

## Open conceptual questions answered today
- Docker Hub vs brew/pip → same registry concept, but images are sandboxed artifacts not host installs
- Are Lambdas Docker? → No, they run in Firecracker microVMs; can use Docker as packaging format only
- Docker vs hypervisor goal → both isolate, but at different layers (kernel vs hardware) — cascades into every difference
- VMs accessing host files vs containers → VMs can do it via shared folders, containers do it with zero translation overhead, which is why it became the default dev workflow
- Layer cache scope → daemon-wide, not project-tied; cache hits cross projects when inputs are byte-identical
- Versioning auto-increment → no, all manual; conventions are semver, git SHA, environment pointers
