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

# Keycloak / OIDC — the only config TokenCache itself needs. Every other
# env-var constant that used to live here (STAFF_API_BASE, REGISTER_FARMER,
# SEED_MANIFEST, ...) duplicated shared/config.py, which is the actual
# source every locustfile imports from; only TokenCache is ever imported
# from this module.
KEYCLOAK_BASE = os.environ.get("KEYCLOAK_BASE", "https://keycloak.perftest.openg2p.org")
KEYCLOAK_REALM = os.environ.get("KEYCLOAK_REALM", "staff")
OIDC_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID", "farmer-registry-staff-portal")
OIDC_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET", "")  # if confidential client
OIDC_USERNAME = os.environ.get("OIDC_USERNAME", "admin")
OIDC_PASSWORD = os.environ.get("OIDC_PASSWORD", "")


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
        time.sleep(0.5)  # give the API a moment before the token's first use (clock-skew / not-yet-valid mitigation)
        body = resp.json()
        self._token = body["access_token"]
        self._exp = time.time() + int(body.get("expires_in", 300))

    def auth_header(self) -> dict:
        return {"Authorization": f"Bearer {self.token()}"}
