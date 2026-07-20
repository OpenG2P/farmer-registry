#!/usr/bin/env bash
# Run the sanity suite from your laptop against a live cluster.
#
# The suite is plain pytest configured entirely through SANITY_* environment
# variables — nothing ties it to the in-cluster Job. The only obstacle is that
# every endpoint it talks to is a ClusterIP Service, so this script:
#   1. port-forwards each of them (and Postgres),
#   2. reads the credentials out of the same Secrets the chart wires in,
#   3. exports the SANITY_* env, and
#   4. runs pytest locally.
#
# Usage:
#   ./run-local.sh                       # smoke only
#   ./run-local.sh --e2e                 # smoke + full e2e (seeds fixtures)
#   ./run-local.sh --e2e -k clamp -x     # extra args go to pytest
#
#   NS=trial RELEASE=fr ./run-local.sh --e2e
#
# Requires: kubectl (context already pointing at the cluster), python3, and the
# suite's deps:  pip install -e .   (from this directory)
#
# NOTE ON KEYCLOAK: tokens are fetched over the PUBLIC Keycloak URL, not a
# port-forward. Keycloak stamps the `iss` claim from the hostname it is reached
# on, and staff-portal-api rejects a token whose `iss` does not match a
# LoginProvider row (which holds the public issuer). A port-forwarded token
# would carry iss=http://localhost:... and be rejected. Override with
# KEYCLOAK_URL if your public hostname differs.

set -euo pipefail

NS="${NS:-trial}"
RELEASE="${RELEASE:-fr}"
COMMONS="${COMMONS:-commons}"
COMMONS_SVC="${COMMONS_SVC:-commons-services}"
REALM="${REALM:-staff}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://keycloak.${NS}.openg2p.org}"

# Local ports. Change if any clash.
P_PARTNER=18081
P_STAFF=18082
P_PM_PARTNER=18083
P_PM_ADMIN=18084
P_CM_STAFF=18085
P_PG=15432

RUN_E2E=false
if [ "${1:-}" = "--e2e" ]; then RUN_E2E=true; shift; fi

PIDS=()
cleanup() {
  echo "[run-local] stopping port-forwards…"
  for pid in "${PIDS[@]:-}"; do kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

pf() {  # pf <svc> <local-port> <remote-port>
  kubectl -n "$NS" port-forward "svc/$1" "$2:$3" >/dev/null 2>&1 &
  PIDS+=($!)
}

secret() {  # secret <name> <key>  -> decoded value ("" if absent)
  kubectl -n "$NS" get secret "$1" -o "jsonpath={.data.$2}" 2>/dev/null | base64 -d 2>/dev/null || true
}

echo "[run-local] namespace=$NS release=$RELEASE e2e=$RUN_E2E"
echo "[run-local] port-forwarding…"
pf "${RELEASE}-partner-api"                 "$P_PARTNER"    80
pf "${RELEASE}-staff-portal-api"            "$P_STAFF"      80
pf "${COMMONS_SVC}-pm-partner-api"          "$P_PM_PARTNER" 80
pf "${COMMONS_SVC}-pm-staff-portal-api"     "$P_PM_ADMIN"   80
pf "${COMMONS_SVC}-cm-api"                  "$P_CM_STAFF"   80
# All three databases (registry, awe, audit) live on this one host.
pf "${COMMONS}-postgresql"                  "$P_PG"         5432
sleep 4

# ── endpoints ────────────────────────────────────────────────────────────────
export SANITY_PARTNER_BASE_URL="http://localhost:${P_PARTNER}"
export SANITY_STAFF_BASE_URL="http://localhost:${P_STAFF}"
export SANITY_PM_PARTNER_API_URL="http://localhost:${P_PM_PARTNER}"
export SANITY_PM_ADMIN_URL="http://localhost:${P_PM_ADMIN}"
export SANITY_CM_STAFF_URL="http://localhost:${P_CM_STAFF}"
export SANITY_KEYCLOAK_BASE_URL="${KEYCLOAK_URL}"
export SANITY_KEYCLOAK_REALM="${REALM}"

TOKEN_URL="${KEYCLOAK_URL}/realms/${REALM}/protocol/openid-connect/token"
export SANITY_STAFF_TOKEN_URL="$TOKEN_URL"
export SANITY_CM_TOKEN_URL="$TOKEN_URL"
export SANITY_PM_ADMIN_TOKEN_URL="$TOKEN_URL"

# The registry echoes this back as the DCI envelope receiver.
export SANITY_DCI_RECEIVER_ID="${RELEASE}"
export SANITY_RUN_E2E="$RUN_E2E"
export SANITY_VERIFY_TLS=false
export SANITY_FAIL_ON_ERROR=true   # local runs should fail loudly

# ── credentials (same Secrets the chart wires into the Job) ──────────────────
export SANITY_KEYCLOAK_ADMIN_USER=admin
export SANITY_KEYCLOAK_ADMIN_PASSWORD="$(secret "${COMMONS}-keycloak" admin-password)"
export SANITY_STAFF_CLIENT_ID="${RELEASE}-staff-portal"
export SANITY_STAFF_CLIENT_SECRET="$(secret "${RELEASE}-staff-portal" client_secret)"
export SANITY_CM_CLIENT_ID=consent-manager
export SANITY_CM_CLIENT_SECRET="$(secret consent-manager client_secret)"
export SANITY_PM_ADMIN_CLIENT_ID="${COMMONS_SVC}-staff-portal"
export SANITY_PM_ADMIN_CLIENT_SECRET="$(secret "${COMMONS_SVC}-staff-portal" client_secret)"

# ── databases (one forwarded host, three database names) ─────────────────────
REG_DB="$(printf '%s' "$RELEASE" | tr '-' '_')"
export SANITY_REGISTRY_PGHOST=localhost SANITY_REGISTRY_PGPORT="$P_PG"
export SANITY_REGISTRY_PGDATABASE="$REG_DB"
export SANITY_REGISTRY_PGUSER="${REG_DB}_user"
export SANITY_REGISTRY_PGPASSWORD="$(secret "${RELEASE}" "${RELEASE}-db-user")"

export SANITY_AWE_PGHOST=localhost SANITY_AWE_PGPORT="$P_PG"
export SANITY_AWE_PGDATABASE=awe SANITY_AWE_PGUSER=awe_user
export SANITY_AWE_PGPASSWORD="$(secret awe-db-user awe-db-user-password)"

export SANITY_AUDIT_PGHOST=localhost SANITY_AUDIT_PGPORT="$P_PG"
export SANITY_AUDIT_PGDATABASE=audit_manager SANITY_AUDIT_PGUSER=audit_manager_user
export SANITY_AUDIT_PGPASSWORD="$(secret audit-manager-db-user audit-manager-db-user-password)"

# ── report what resolved, so a skip is diagnosable ───────────────────────────
echo "[run-local] resolved:"
for v in SANITY_KEYCLOAK_ADMIN_PASSWORD SANITY_STAFF_CLIENT_SECRET \
         SANITY_CM_CLIENT_SECRET SANITY_REGISTRY_PGPASSWORD \
         SANITY_AWE_PGPASSWORD SANITY_AUDIT_PGPASSWORD; do
  if [ -n "${!v:-}" ]; then echo "    $v = <set>"; else echo "    $v = MISSING (dependent tests will skip)"; fi
done

echo "[run-local] running pytest…"
if [ "$RUN_E2E" = "true" ]; then
  python3 -m pytest "$@"
else
  python3 -m pytest -m smoke "$@"
fi
