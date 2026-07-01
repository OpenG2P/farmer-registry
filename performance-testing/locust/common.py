"""Shared config + auth helpers for the Farmer Registry load tests.

Auth model: acquire an OIDC access token ONCE per simulated user via the
Keycloak password grant against the release's `staff` realm client, cache it,
and refresh only when it is close to expiry. This avoids benchmarking Keycloak's
token endpoint instead of the registry (a common load-test mistake).

All connection details come from environment variables so the same script runs
against any environment without edits.
"""

import os
import time
import requests

# ---------------------------------------------------------------------------
# Configuration (override via environment variables)
# ---------------------------------------------------------------------------
# Target API base URLs. For in-cluster runs use the ClusterIP service DNS, e.g.
#   http://<release>-staff-portal-api  /  http://<release>-partner-api
# For end-to-end runs use the public hostnames behind Istio/RP.
STAFF_API_BASE = os.environ.get("STAFF_API_BASE", "http://localhost:8000")
PARTNER_API_BASE = os.environ.get("PARTNER_API_BASE", "http://localhost:8001")

# Keycloak / OIDC
KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "https://keycloak.example.openg2p.org")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "staff")
# Per-release client id — equals the chart's global.authClientId, e.g. "fr-staff-portal".
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "fr-staff-portal")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")  # if confidential client
OIDC_USERNAME = os.environ.get("OIDC_USERNAME", "admin")
OIDC_PASSWORD = os.environ.get("OIDC_PASSWORD", "")

# Path to the seed manifest (sample of valid ids / search terms across the full
# key space, produced by the bulk seeder — see scripts/seed_bulk.md).
SEED_MANIFEST = os.environ.get("SEED_MANIFEST", "seed_manifest.json")

# Register mnemonics under test
REGISTER_FARMER = "Farmer"
REGISTER_HOUSEHOLD = "Household"


class TokenCache:
    """Per-user cached OIDC token with lazy refresh."""

    def __init__(self):
        self._token = None
        self._exp = 0.0

    def token(self) -> str:
        now = time.time()
        if self._token and now < self._exp - 30:  # refresh 30s before expiry
            return self._token
        self._fetch()
        return self._token

    def _fetch(self):
        url = f"{KEYCLOAK_BASE}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/token"
        data = {
            "grant_type": "password",
            "client_id": OIDC_CLIENT_ID,
            "username": OIDC_USERNAME,
            "password": OIDC_PASSWORD,
        }
        if OIDC_CLIENT_SECRET:
            data["client_secret"] = OIDC_CLIENT_SECRET
        resp = requests.post(url, data=data, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        self._token = body["access_token"]
        self._exp = time.time() + int(body.get("expires_in", 300))

    def auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}
