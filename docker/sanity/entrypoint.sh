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

# --- wait for the registry APIs to be reachable before running ---
# As a post-install Helm hook this Job can fire before the registry pods are
# Ready, so we wait for BOTH the partner-api (DCI) and, for the e2e, the
# staff-portal-api (change requests). Reachability is necessary but not
# sufficient — the staff-portal-api permission path warms up a little after it
# starts answering, so the change-request test additionally retries on 403.
python - <<'PY'
import os, sys, time
import httpx

verify = (os.environ.get("SANITY_VERIFY_TLS", "true").lower() not in ("false", "0", "no"))
deadline = time.time() + int(os.environ.get("SANITY_READINESS_TIMEOUT", "180"))
run_e2e = (os.environ.get("SANITY_RUN_E2E", "false").lower() in ("1", "true", "yes", "on"))

# (label, url, "ready" predicate). staff-portal-api has no unauthenticated 200
# endpoint, so any HTTP response (even 401/404) means it is up.
targets = []
partner = (os.environ.get("SANITY_PARTNER_BASE_URL") or "").rstrip("/")
if partner:
    targets.append(("partner-api", partner + "/ping", lambda r: r.status_code == 200))
staff = (os.environ.get("SANITY_STAFF_BASE_URL") or "").rstrip("/")
if run_e2e and staff:
    targets.append(("staff-portal-api", staff + "/docs", lambda r: r.status_code < 500))

for label, url, ready in targets:
    while time.time() < deadline:
        try:
            if ready(httpx.get(url, timeout=10, verify=verify)):
                print(f"[sanity] {label} ready at {url}")
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        print(f"[sanity] {label} not ready after wait ({url}); running anyway")
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
