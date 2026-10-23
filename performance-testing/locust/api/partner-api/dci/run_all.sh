#!/usr/bin/env bash
# Run the three search cases for one mode and one pod count, one after another.
#   ./run_all.sh sync 1
#   ./run_all.sh async 3
set -euo pipefail

MODE="${1:?sync or async}"
POD_SCALE="${2:?pass 1, 2, or 3}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CASES=(
  btree_fid
  gin_text
  composite
)

for case in "${CASES[@]}"; do
  echo "=== ${MODE} ${case} pod-${POD_SCALE} ==="
  HEADLESS=1 "${HERE}/run_case.sh" "${MODE}" "${case}" "${POD_SCALE}"
done
