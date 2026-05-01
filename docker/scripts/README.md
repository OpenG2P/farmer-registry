# docker/scripts/ — Local build scripts for the Farmer Registry Docker images

## Overview

The `docker/scripts/` folder provides a fully local, command-line equivalent
of the `.github/workflows/docker-build-*.yml` GitHub Actions workflows.
Running `build.sh` does exactly what the workflow does:

1. Reads a **service spec file** (e.g. `staff-portal-api/develop.txt`, path
   relative to `docker/`)
2. Parses the Docker image tag, git dependencies, and Dockerfile path
3. Copies any **local-path deps** (e.g. `./farmer-extension`) into
   `docker/local_deps/` so they are inside the Docker build context
4. Generates `docker/adapters.requirements.txt` (consumed by the Dockerfiles)
5. Runs `docker build` with `docker/` as the context, plus OCI labels
   and `--build-arg` values
6. Optionally pushes to Docker Hub

---

## Layout

```
docker/
├── staff-portal-api/
├── partner-api/
├── staff-portal-ui/
├── celery/
├── db-seed/
├── local_deps/          ← Staging for local-path deps (git-tracked via .gitignore)
└── scripts/
    ├── build.sh         ← Main entry point
    ├── parse_service.py ← Spec-file parser
    ├── .env.example     ← Template for Docker Hub credentials
    └── README.md        ← This file
```

---

## Quick Start

### 1. Set up credentials

```bash
cp docker/scripts/.env.example docker/scripts/.env
# Edit docker/scripts/.env and fill in DOCKER_HUB_USERNAME and DOCKER_HUB_TOKEN
```

> `docker/scripts/.env` is gitignored — never commit it.

### 2. Make the script executable (first time only)

```bash
chmod +x docker/scripts/build.sh
```

### 3. Build all default services (no push)

```bash
cd /path/to/farmer-registry
./docker/scripts/build.sh
```

### 4. Build a single service

```bash
./docker/scripts/build.sh staff-portal-api/develop.txt
./docker/scripts/build.sh celery/develop.txt
./docker/scripts/build.sh partner-api/develop.txt
./docker/scripts/build.sh staff-portal-ui/develop.txt
```

> Paths are relative to `docker/`. Do **not** prefix with `docker/`.

### 5. Build and push to Docker Hub

```bash
./docker/scripts/build.sh --push staff-portal-api/develop.txt
# or set env var:
PUSH=1 ./docker/scripts/build.sh
```

### 6. Multi-arch build (amd64 + arm64) and push

```bash
./docker/scripts/build.sh --platform linux/amd64,linux/arm64 --push staff-portal-api/develop.txt
# or:
BUILD_PLATFORM=linux/amd64,linux/arm64 PUSH=1 ./docker/scripts/build.sh
```

> Multi-arch builds require Docker Buildx (installed by default in Docker Desktop).

### 6a. Building `amd64` on an Apple Silicon (arm64) Mac

Default is native arch, so on an M-series Mac you'll get arm64 by default.
To cross-build amd64 (emulated via QEMU built into Docker Desktop):

```bash
BUILD_PLATFORM=linux/amd64 ./docker/scripts/build.sh staff-portal-api/develop.txt
# or:
./docker/scripts/build.sh --platform linux/amd64 staff-portal-api/develop.txt
```

Verify:

```bash
docker inspect --format '{{.Architecture}}' openg2p/openg2p-farmer-registry-staff-portal-api:develop
# → amd64
```

> First-time setup: Docker Desktop ≥ 4.x has QEMU enabled by default. If
> you see `exec format error` during the build, run once:
> `docker run --privileged --rm tonistiigi/binfmt --install amd64`
>
> **Speed note:** emulated amd64 builds are ~2–5× slower than native arm64.
> For day-to-day iteration, stick with the native-arm64 default; switch to
> amd64 only when you need to verify amd64 behaviour, or let CI handle it
> (GitHub Actions runners are amd64 natively).

### 7. Build without cache

```bash
./docker/scripts/build.sh --no-cache staff-portal-api/develop.txt
# or:
NO_CACHE=1 ./docker/scripts/build.sh
```

### 8. Override Dockerfile path

```bash
./docker/scripts/build.sh --dockerfile celery/Dockerfile celery/develop.txt
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCKER_HUB_USERNAME` | — | Docker Hub username (required for push) |
| `DOCKER_HUB_TOKEN` | — | Docker Hub access token (required for push) |
| `PUSH` | `0` | Set to `1` to push after build |
| `NO_CACHE` | `0` | Set to `1` to disable Docker layer cache |
| `BUILD_PLATFORM` | *host native arch* | Platform(s) to build for. Auto-detected: `linux/amd64` on Intel, `linux/arm64` on Apple Silicon. Override explicitly to cross-build. |

---

## Service Spec File Format

The service files (e.g. `docker/staff-portal-api/develop.txt`) follow this format:

```
#!docker-org/image-name:tag          ← required: Docker image to produce
# optional comments

./farmer-extension                                            ← local-path dep (relative to project root)
git://BRANCH_OR_TAG//GITHUB_URL#subdirectory=pkg              ← git pip dep
git://v1.2.3//https://github.com/org/repo#subdirectory=subpkg
regular-pypi-package==1.0.0                                   ← plain pip dep
```

For **local-path** entries (e.g. `./farmer-extension`), `parse_service.py`
resolves the path relative to the **project root** (passed via
`--source-root`) and copies the directory into
`docker/local_deps/<dir_name>/` so it lives inside the Docker build context.
The requirement line is rewritten to `./local_deps/<dir_name>` which pip
installs from the local source tree.

For **git** entries, the script converts each `git://BRANCH//URL` line into
a pip-installable URL of the form `git+URL@BRANCH#subdirectory=pkg`.

All entries are written to `docker/adapters.requirements.txt` which the
Dockerfiles `COPY` and `pip install` during the build.

The **Dockerfile** is resolved in this order:
1. `--dockerfile` CLI argument
2. `Dockerfile` in the same directory as the spec file
3. A second `#!` line in the spec file (legacy format)

---

## Default Service Matrix

When called with no arguments, `build.sh` builds all four services:

| Service | Spec File (relative to `docker/`) | Produces |
|---------|-----------|----------|
| staff-portal-api | `staff-portal-api/develop.txt` | `openg2p/openg2p-farmer-registry-staff-portal-api:develop` |
| celery | `celery/develop.txt` | `openg2p/openg2p-farmer-registry-celery:develop` |
| partner-api | `partner-api/develop.txt` | `openg2p/openg2p-farmer-registry-partner-api:develop` |
| staff-portal-ui | `staff-portal-ui/develop.txt` | `openg2p/openg2p-farmer-registry-staff-portal-ui:develop` |

---

## Building for a different branch

Each branch has its own `develop.txt`-style spec file (the name is
conventional, not special). To build for a new branch:

1. Create a new spec file under `docker/`, e.g. `docker/staff-portal-api/release-1.0.txt`
2. Update the `#!...` image tag line (e.g. `:release-1.0`)
3. Update any git-branch references if pinning to a specific farmer-extension tag
4. Run: `./docker/scripts/build.sh staff-portal-api/release-1.0.txt`

---

## Requirements

- **Docker** ≥ 20 with Buildx (for multi-arch; standard builds work without it)
- **Python** ≥ 3.10 (for `parse_service.py`)
- **git** in PATH
- A valid Docker Hub account with push access to the target image names
