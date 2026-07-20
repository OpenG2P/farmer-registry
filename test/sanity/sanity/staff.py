"""Client for the registry staff-portal-api.

Unlike the partner-api (signature-based, no Keycloak), staff-portal-api runs the
full chain: Audit -> CSRF -> ValidateAndRefresh -> ResolvePermission -> DataPolicy.

**Authenticates as the suite's OWN seeded user, via the password grant.**
Neither shortcut works on a stock install: the registry's Keycloak client is a
browser OIDC client with no service account (so `client_credentials` is
rejected), and keycloak-init's demo users are created with a *temporary*
password, so Keycloak forces UPDATE_PASSWORD and their password grant fails with
"Account is not fully set up". So `sanity.keycloak_seed` provisions a dedicated
test user with a non-temporary password and the roles it needs, and this logs in
as that. See keycloak_seed.py.

Two things make this work headlessly, without a browser:

  * **A bearer token is a first-class input.** The refresh-session check returns
    early when there is no `X-Session-Id` cookie, and the only provider claim
    required is `sub` — so an `Authorization: Bearer` header alone is enough.
  * **CSRF is a double-submit compare.** It only checks that the `X-CSRF-Token`
    cookie equals the `X-CSRF-Token` header — it is not bound to the session or
    the token — so sending a matching pair passes.

The password grant needs `directAccessGrantsEnabled` on the client, which
keycloak-init cannot declare — `sanity.keycloak_seed` turns it on via the admin
API, so it is guaranteed rather than assumed.
"""

import base64
import json
import uuid
from datetime import datetime, timezone

import httpx


def _jwt_sub(token: str) -> str:
    """The `sub` claim of a JWT, without verifying it (identity only)."""
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return json.loads(base64.urlsafe_b64decode(payload)).get("sub", "")


def fetch_token(cfg, username: str, password: str) -> str:
    """Password-grant token for `username` on the registry's Keycloak client."""
    data = {
        "grant_type": "password",
        "client_id": cfg.staff_client_id,
        "username": username,
        "password": password,
        "scope": "openid",
    }
    # The registry client is confidential (keycloak-init mints a client_secret
    # Secret named after the clientId), so the secret rides along with the
    # user's credentials.
    if cfg.staff_client_secret:
        data["client_secret"] = cfg.staff_client_secret
    r = httpx.post(cfg.staff_token_url, data=data, verify=cfg.verify_tls, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(
            f"password grant failed for '{username}' ({r.status_code}): {r.text[:300]}. "
            f"If this says the account is not fully set up, the user has a required "
            f"action pending — sanity.keycloak_seed should have cleared it."
        )
    return r.json()["access_token"]


def envelope(payload: dict) -> dict:
    """Wrap a request payload in the G2P request envelope the APIs expect."""
    return {
        "request_header": {
            "sender_app_mnemonic": "sanity-e2e",
            "sender_app_url": "http://sanity",
            "request_id": uuid.uuid4().hex,
            "request_timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "request_body": {"request_payload": payload},
    }


class StaffClient:
    """Thin authenticated wrapper for one user. All staff-portal-api calls are POST."""

    def __init__(self, cfg, token: str, username: str = ""):
        self.cfg = cfg
        self.username = username
        # The subject (Keycloak user id) that audit events are attributed to.
        self.subject = _jwt_sub(token)
        csrf = uuid.uuid4().hex
        self._client = httpx.Client(
            base_url=cfg.staff_base_url,
            verify=cfg.verify_tls,
            timeout=60,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                # Double-submit pair — see the module docstring.
                "X-CSRF-Token": csrf,
            },
            cookies={"X-CSRF-Token": csrf},
        )

    @classmethod
    def login(cls, cfg, username: str, password: str) -> "StaffClient":
        return cls(cfg, fetch_token(cfg, username, password), username)

    def relogin(self):
        """Refresh the token in place — used to pick up role mappings that were
        granted moments earlier, when the permission path is still warming up
        just after install."""
        token = fetch_token(self.cfg, self.username, self.cfg.staff_password)
        self.subject = _jwt_sub(token)
        old = self._client
        csrf = uuid.uuid4().hex
        self._client = httpx.Client(
            base_url=self.cfg.staff_base_url,
            verify=self.cfg.verify_tls,
            timeout=60,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "X-CSRF-Token": csrf,
            },
            cookies={"X-CSRF-Token": csrf},
        )
        old.close()

    def close(self):
        self._client.close()

    def post(self, path: str, payload: dict) -> dict:
        r = self._client.post(path, json=envelope(payload))
        assert r.status_code == 200, (
            f"{path} as '{self.username}' -> {r.status_code}: {r.text[:400]}"
        )
        return r.json()

    # ── change requests ──────────────────────────────────────────────────────

    def create_change_request(self, payload: dict) -> dict:
        return self.post("/change-requests/create_change_request", payload)

    def get_change_requests(self, payload: dict) -> dict:
        return self.post("/change-requests/get_change_requests", payload)

    # ── AWE proxy (the ONLY approval path that honours the policy) ────────────
    #
    # `/change-requests/approve_change_request` exists and would also flip the
    # CR to approved — but it never inspects the AWE workflow state, so
    # approving through it would bypass the policy entirely and the test would
    # prove nothing. Always approve through the proxy.

    def list_my_tasks(self, payload: dict) -> dict:
        return self.post("/awe/list_my_tasks", payload)

    def submit_task_decision(self, payload: dict) -> dict:
        return self.post("/awe/submit_task_decision", payload)

    # ── register data + history ──────────────────────────────────────────────

    def get_record_history(self, payload: dict) -> dict:
        return self.post("/register-data/get_record_history", payload)

    def get_number_of_versions(self, payload: dict) -> dict:
        return self.post("/register-data/get_number_of_versions", payload)
