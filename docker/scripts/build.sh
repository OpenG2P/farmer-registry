#!/usr/bin/env bash
# =============================================================================
# build.sh — Local CLI equivalent of the docker-build-*.yml GitHub Actions
# workflows for the Farmer Registry repo.
#
# SERVICE_FILE paths are relative to the docker/ directory (e.g.
# "staff-portal-api/develop.txt", NOT "docker/staff-portal-api/develop.txt").
#
# Usage:
#   ./docker/scripts/build.sh [OPTIONS] [SERVICE_FILE]
#
# Examples:
#   ./docker/scripts/build.sh                                # Build all default services (no push)
#   ./docker/scripts/build.sh staff-portal-api/develop.txt   # Build a single service
#   ./docker/scripts/build.sh --push staff-portal-api/develop.txt
#   ./docker/scripts/build.sh --dockerfile staff-portal-api/Dockerfile staff-portal-api/develop.txt
#   ./docker/scripts/build.sh --platform linux/amd64 --push all
#
# Required env vars (set in docker/scripts/.env or export before running):
#   DOCKER_HUB_USERNAME   — Docker Hub username
#   DOCKER_HUB_TOKEN      — Docker Hub access token / password
#
# Optional env vars:
#   BUILD_PLATFORM        — Docker platform(s). Default: host native arch
#                           (linux/amd64 on Intel, linux/arm64 on Apple Silicon).
#                           - Set to a single platform like linux/amd64 to
#                             cross-build (emulated via QEMU on Docker Desktop —
#                             slower but produces a genuine amd64 image on arm64).
#                           - Set to "linux/amd64,linux/arm64" for multi-arch
#                             (uses buildx; push-only unless --load is added).
#   NO_CACHE              — Set to "1" to disable Docker build cache
#   PUSH                  — Set to "1" to push after build (overrides --push flag)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# docker/scripts → docker/ → repo root
DOCKER_CTX="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${DOCKER_CTX}/.." && pwd)"
# Alias retained for readability below. The Docker build context is docker/,
# which is also where local_deps/ and adapters.requirements.txt live.
REPO_ROOT="${DOCKER_CTX}"

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------
PUSH="${PUSH:-0}"
NO_CACHE="${NO_CACHE:-0}"
OVERRIDE_DOCKERFILE=""

# Default BUILD_PLATFORM = host's native architecture (native-speed build).
# To cross-build for a different arch — e.g. producing amd64 images on an
# Apple Silicon Mac — set BUILD_PLATFORM explicitly or pass --platform.
_detect_native_platform() {
  case "$(uname -m)" in
    x86_64|amd64)    echo "linux/amd64" ;;
    arm64|aarch64)   echo "linux/arm64" ;;
    *)               echo "linux/amd64" ;;   # safe fallback
  esac
}
BUILD_PLATFORM="${BUILD_PLATFORM:-$(_detect_native_platform)}"

# Default service matrix (mirrors the workflow's fallback list)
DEFAULT_SERVICES=(
  "staff-portal-api/develop.txt"
  "celery/develop.txt"
  "partner-api/develop.txt"
  "staff-portal-ui/develop.txt"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
log()  { echo "[build.sh] $*"; }
err()  { echo "[build.sh] ERROR: $*" >&2; }
die()  { err "$*"; exit 1; }

usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,2\}//'
  exit 0
}

cleanup() {
  rm -f "${SCRIPT_DIR}/_service_env.sh"
  rm -f "${REPO_ROOT}/adapters.requirements.txt"
  # Remove package subdirs staged by this build. Skip dotfiles so .gitignore
  # inside local_deps/ is never touched, keeping the directory git-tracked.
  find "${REPO_ROOT}/local_deps" -mindepth 1 -maxdepth 1 \
    -not -name ".*" -exec rm -rf {} +
}

# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------
POSITIONAL=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)        usage ;;
    --push)           PUSH=1; shift ;;
    --no-cache)       NO_CACHE=1; shift ;;
    --platform)       BUILD_PLATFORM="$2"; shift 2 ;;
    --dockerfile)     OVERRIDE_DOCKERFILE="$2"; shift 2 ;;
    *)                POSITIONAL+=("$1"); shift ;;
  esac
done

# Determine which service files to build
SERVICE_FILES=()
if [[ ${#POSITIONAL[@]} -eq 0 || "${POSITIONAL[0]:-}" == "all" ]]; then
  SERVICE_FILES=("${DEFAULT_SERVICES[@]}")
else
  SERVICE_FILES=("${POSITIONAL[@]}")
fi

# ---------------------------------------------------------------------------
# Credential check
# ---------------------------------------------------------------------------
if [[ "${PUSH}" == "1" ]]; then
  ENV_FILE="${SCRIPT_DIR}/.env"
  if [[ -f "${ENV_FILE}" ]]; then
    log "Loading credentials from ${ENV_FILE}"
    # shellcheck disable=SC1090
    set -a; source "${ENV_FILE}"; set +a
  fi
  [[ -n "${DOCKER_HUB_USERNAME:-}" ]] || die "DOCKER_HUB_USERNAME is not set. Set it in docker/scripts/.env or export it."
  [[ -n "${DOCKER_HUB_TOKEN:-}"    ]] || die "DOCKER_HUB_TOKEN is not set. Set it in docker/scripts/.env or export it."

  log "Logging in to Docker Hub as ${DOCKER_HUB_USERNAME}..."
  echo "${DOCKER_HUB_TOKEN}" | docker login --username "${DOCKER_HUB_USERNAME}" --password-stdin
fi

# ---------------------------------------------------------------------------
# Multi-arch buildx setup (only if needed)
# ---------------------------------------------------------------------------
if [[ "${BUILD_PLATFORM}" == *","* ]]; then
  log "Multi-arch build requested (${BUILD_PLATFORM}). Setting up buildx builder..."
  if ! docker buildx inspect openg2p-farmer-registry-builder &>/dev/null; then
    docker buildx create --name openg2p-farmer-registry-builder --use
  else
    docker buildx use openg2p-farmer-registry-builder
  fi
  docker buildx inspect --bootstrap
  BUILDX=1
else
  BUILDX=0
fi

# ---------------------------------------------------------------------------
# Process each service file
# ---------------------------------------------------------------------------
FAILURES=()

for SERVICE_FILE in "${SERVICE_FILES[@]}"; do
  # Resolve relative to repo root
  if [[ ! "${SERVICE_FILE}" = /* ]]; then
    SERVICE_FILE="${REPO_ROOT}/${SERVICE_FILE}"
  fi

  log "============================================================"
  log "Processing service file: ${SERVICE_FILE}"
  log "============================================================"

  # Ensure local_deps/ exists (it is git-tracked via its .gitignore, but may
  # have been absent if this is a fresh clone with no prior build run).
  mkdir -p "${REPO_ROOT}/local_deps"

  # Parse the service file. For local-path deps this also copies source trees
  # into <repo_root>/local_deps/ so they are inside the Docker build context.
  # --source-root is the project root — it's where ./nsr-extension and other
  # relative paths in the spec files are resolved from. The build context
  # itself (--repo-root) is docker/, so the copied trees land in
  # docker/local_deps/<pkg>/ and adapters.requirements.txt lands in docker/.
  python3 "${SCRIPT_DIR}/parse_service.py" \
    --service-file "${SERVICE_FILE}" \
    --repo-root    "${REPO_ROOT}" \
    --source-root  "${PROJECT_ROOT}" \
    ${OVERRIDE_DOCKERFILE:+--dockerfile "${OVERRIDE_DOCKERFILE}"} \
    --output-env   "${SCRIPT_DIR}/_service_env.sh"

  # shellcheck disable=SC1091
  source "${SCRIPT_DIR}/_service_env.sh"

  log "Image      : ${SVC_IMAGE}"
  log "Dockerfile : ${SVC_DOCKERFILE}"
  log "Context    : ${SVC_CONTEXT}"
  log "REPO_URL   : ${SVC_REPO_URL}"
  log "GIT_BRANCH : ${SVC_GIT_BRANCH}"

  # List staged local packages (exclude dotfiles like .gitignore)
  LOCAL_PKGS=$(find "${REPO_ROOT}/local_deps" -mindepth 1 -maxdepth 1 -not -name ".*" -type d 2>/dev/null || true)
  if [[ -n "${LOCAL_PKGS}" ]]; then
    log "Local deps staged into build context:"
    echo "${LOCAL_PKGS}" | xargs -I{} basename {} | sed 's/^/    /'
  fi

  log "Generated adapters.requirements.txt:"
  cat "${REPO_ROOT}/adapters.requirements.txt"
  echo ""

  # Build args
  BUILD_ARGS=(
    -f "${SVC_DOCKERFILE}"
    -t "${SVC_IMAGE}"
    --build-arg "REPO_URL=${SVC_REPO_URL}"
    --build-arg "GIT_BRANCH=${SVC_GIT_BRANCH}"
    --label "org.opencontainers.image.created=${SVC_CREATED}"
    --label "org.opencontainers.image.revision=${SVC_COMMIT}"
    --label "org.opencontainers.image.vendor=${SVC_VENDOR}"
    --label "org.opencontainers.image.title=${SVC_TITLE}"
    --label "org.opencontainers.image.version=${SVC_VERSION}"
    --label "org.opencontainers.image.description=OpenG2P Farmer Registry service image"
  )

  [[ "${NO_CACHE}" == "1" ]] && BUILD_ARGS+=(--no-cache)

  if [[ "${BUILDX}" == "1" ]]; then
    PUSH_FLAG="--load"
    [[ "${PUSH}" == "1" ]] && PUSH_FLAG="--push"
    log "Running: docker buildx build --platform ${BUILD_PLATFORM} ${PUSH_FLAG} ..."
    if docker buildx build \
        --platform "${BUILD_PLATFORM}" \
        "${BUILD_ARGS[@]}" \
        ${PUSH_FLAG} \
        "${SVC_CONTEXT}"; then
      log "✅ Build succeeded: ${SVC_IMAGE}"
    else
      err "❌ Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  else
    # Single-platform build. We always pass --platform so the image is
    # produced for the requested architecture even when host arch differs
    # (e.g. BUILD_PLATFORM=linux/amd64 on an Apple Silicon Mac — QEMU
    # emulation is triggered automatically by Docker Desktop).
    log "Running: docker build --platform ${BUILD_PLATFORM} ..."
    if docker build --platform "${BUILD_PLATFORM}" "${BUILD_ARGS[@]}" "${SVC_CONTEXT}"; then
      log "✅ Build succeeded: ${SVC_IMAGE}"
      if [[ "${PUSH}" == "1" ]]; then
        log "Pushing ${SVC_IMAGE}..."
        docker push "${SVC_IMAGE}"
      fi
    else
      err "❌ Build failed: ${SVC_IMAGE}"
      FAILURES+=("${SVC_IMAGE}")
    fi
  fi

  # Clean up per-build temp files. local_deps/ itself and its dotfiles are
  # preserved so subsequent builds can still COPY it cleanly.
  cleanup
done

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
log "============================================================"
log "Build Summary"
log "============================================================"
TOTAL=${#SERVICE_FILES[@]}
FAILED=${#FAILURES[@]}
PASSED=$(( TOTAL - FAILED ))
log "Total: ${TOTAL}  Passed: ${PASSED}  Failed: ${FAILED}"

if [[ ${FAILED} -gt 0 ]]; then
  err "The following builds failed:"
  for f in "${FAILURES[@]}"; do
    err "  - ${f}"
  done
  exit 1
fi

log "All builds completed successfully."
