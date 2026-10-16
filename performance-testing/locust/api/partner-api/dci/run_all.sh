#!/usr/bin/env bash
# Run the three search cases for one mode, one after another.
#   ./run_all.sh sync
#   ./run_all.sh async
set -euo pipefail

MODE="${1:?sync or async}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASES=(
  btree_fid
  gin_text
  composite
)

for case in "${CASES[@]}"; do
  echo "=== ${MODE} ${case} ==="
  HEADLESS=1 "${HERE}/run_case.sh" "${MODE}" "${case}"
done
