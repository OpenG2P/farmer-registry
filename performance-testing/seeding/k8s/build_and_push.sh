#!/bin/bash
# Build and push the seeding Docker image

set -e

# Configuration
IMAGE_NAME="${IMAGE_NAME:-vin0dkhichar/farmer-registry-seeding}"
IMAGE_TAG="${IMAGE_TAG:-v3}"
FULL_IMAGE="${IMAGE_NAME}:${IMAGE_TAG}"

# Get the script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEEDING_DIR="$(dirname "$SCRIPT_DIR")"
PERF_SEED_DIR="$(cd "${SEEDING_DIR}/../../.." && pwd)/perf-seed"
TERMS_FILE="${PERF_SEED_DIR}/register_search_terms.txt"

if [[ ! -f "${TERMS_FILE}" ]]; then
  echo "Missing search terms file: ${TERMS_FILE}" >&2
  exit 1
fi

echo "Building Docker image: ${FULL_IMAGE}"
echo "Seeding directory: ${SEEDING_DIR}"
echo "Search terms: ${TERMS_FILE}"

# Terms live in openg2p/perf-seed (not in the seeding tree). Bake them in via
# an extra BuildKit context so the image still has /perf-seed/register_search_terms.txt
docker build \
  -t "${FULL_IMAGE}" \
  -f "${SCRIPT_DIR}/Dockerfile" \
  --build-context "perfseed=${PERF_SEED_DIR}" \
  "${SEEDING_DIR}"

echo "Pushing Docker image: ${FULL_IMAGE}"
docker push "${FULL_IMAGE}"

echo "Image built and pushed successfully: ${FULL_IMAGE}"