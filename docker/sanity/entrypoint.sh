#!/usr/bin/env bash
# Run the Farmer Registry partner-api sanity suite in-cluster (post-install/
# post-upgrade hook, or on demand).
#
#   SANITY_RUN_E2E=false (default) -> smoke only (creates NO data, needs no PM/CM).
#                       true       -> also the signed DCI search round-trip, which
#                                     seeds a persistent PM partner + CM binding.
#   SANITY_FAIL_ON_ERROR=false (default) -> always exit 0, so a failing run never
#                       fails the install/upgrade; read the logs for results.
#                       true       -> propagate pytest's exit code (CD gating).
#   SANITY_READINESS_TIMEOUT (default 180) -> wait for partner-api /ping first.
set -o pipefail
cd /app

# --- wait for the partner-api to answer /ping before running ---
python - <<'PY'
import os, sys, time
import httpx

base = (os.environ.get("SANITY_PARTNER_BASE_URL") or "").rstrip("/")
if not base:
    sys.exit(0)
verify = (os.environ.get("SANITY_VERIFY_TLS", "true").lower() not in ("false", "0", "no"))
deadline = time.time() + int(os.environ.get("SANITY_READINESS_TIMEOUT", "180"))
url = base + "/ping"
while time.time() < deadline:
    try:
        if httpx.get(url, timeout=10, verify=verify).status_code == 200:
            print(f"[sanity] Farmer Registry partner-api ready at {url}")
            sys.exit(0)
    except Exception:
        pass
    time.sleep(5)
print(f"[sanity] not ready after wait ({url}); running anyway")
PY

if [ "${SANITY_RUN_E2E}" = "true" ]; then
  echo "[sanity] running FULL suite (smoke + e2e)"
  pytest "$@"
else
  echo "[sanity] running smoke only (SANITY_RUN_E2E=false)"
  pytest -m "smoke" "$@"
fi
rc=$?

if [ "${SANITY_FAIL_ON_ERROR}" = "true" ]; then
  exit $rc
fi
echo "[sanity] SANITY_FAIL_ON_ERROR=false -> exiting 0 (deploy not affected). pytest rc=${rc}"
exit 0
