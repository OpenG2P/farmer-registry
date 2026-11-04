#!/usr/bin/env bash
# Eligible PENDING rows for every beat-driven worker task.
# Beat and workers should stay at 0 while you read this.

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cat "$ROOT/sql/case_defs.sql" "$ROOT/sql/count_body.sql" | "$ROOT/psql.sh" celery-counts
