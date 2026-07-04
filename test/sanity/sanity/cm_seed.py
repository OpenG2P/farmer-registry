"""Idempotent seeding of the sanity partner's binding + policy into the Consent
Manager (CM).

The registry's consent enforcement calls CM ``/validate`` for the embedded consent
object; that only permits if CM has an **active partner binding** (keyed by the
consent object's ``aud``) with a **policy** allowing the requested scopes. This
module ensures such a binding + policy exist for the shared sanity partner —
created once via CM's staff API and then left in place (persistent test fixture).

All operations are idempotent: if the binding/policy already exist they are
reused (the policy is re-PUT, which is a no-op when unchanged).
"""

import httpx


def _admin_token(cfg):
    """Client-credentials token for CM's staff API (needs CONSENT_MANAGER_ADMIN).

    Returns None when CM auth is disabled or no credentials are configured.
    """
    if not cfg.cm_auth_enabled:
        return None
    if not cfg.cm_token_url or not cfg.cm_client_secret:
        return None
    r = httpx.post(
        cfg.cm_token_url,
        data={
            "grant_type": "client_credentials",
            "client_id": cfg.cm_client_id,
            "client_secret": cfg.cm_client_secret,
        },
        verify=cfg.verify_tls,
        timeout=20,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _headers(token):
    h = {"Content-Type": "application/json"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    return h


def _find_partner_id(cfg, headers):
    """Return the CM binding id whose audience == cfg.cm_audience, or None."""
    r = httpx.get(
        f"{cfg.cm_staff_url}/consent/v1/partners",
        headers=headers,
        verify=cfg.verify_tls,
        timeout=20,
    )
    r.raise_for_status()
    for partner in r.json():
        if partner.get("audience") == cfg.cm_audience:
            return partner.get("id")
    return None


def _put_policy(cfg, headers, partner_id) -> dict:
    r = httpx.put(
        f"{cfg.cm_staff_url}/consent/v1/partners/{partner_id}/policy",
        headers=headers,
        json={
            "allowed_data_scopes": cfg.data_scopes,
            "allowed_purposes": ["share_farm_profile"],
            "allowed_subject_id_types": ["national_id"],
            "allowed_signing_algs": ["EdDSA", "ES256", "RS256"],
            "max_validity_duration": "P1Y",
            "fetch_type": "oneshot",
        },
        verify=cfg.verify_tls,
        timeout=30,
    )
    r.raise_for_status()
    return r.json() if r.content else {}


def ensure_binding(cfg) -> str:
    """Ensure the CM binding + policy exist for the sanity partner.

    Returns "exists" | "created". Raises RuntimeError if CM is not configured or
    the staff API rejects the calls.
    """
    if not cfg.can_reach_cm:
        raise RuntimeError("SANITY_CM_STAFF_URL not set — cannot seed the CM binding")

    token = _admin_token(cfg)
    headers = _headers(token)

    partner_id = _find_partner_id(cfg, headers)
    if partner_id:
        _put_policy(cfg, headers, partner_id)
        return "exists"

    r = httpx.post(
        f"{cfg.cm_staff_url}/consent/v1/partners",
        headers=headers,
        json={
            "name": "FR Sanity Partner",
            "audience": cfg.cm_audience,
            "controller_id": cfg.controller_id,
            "partner_mgmt_id": cfg.pm_partner_id,
        },
        verify=cfg.verify_tls,
        timeout=30,
    )
    if r.status_code in (401, 403):
        raise RuntimeError(
            f"CM staff API rejected the binding create ({r.status_code}). The seed "
            f"needs a Keycloak client with the CONSENT_MANAGER_ADMIN role "
            f"(token_sent={token is not None})."
        )
    # Tolerate a race/duplicate: re-resolve and continue.
    if r.status_code in (400, 409):
        partner_id = _find_partner_id(cfg, headers)
        if not partner_id:
            r.raise_for_status()
    else:
        r.raise_for_status()
        partner_id = r.json()["id"]

    _put_policy(cfg, headers, partner_id)
    return "created"


def main() -> int:
    """CLI entrypoint (`python -m sanity.cm_seed`) for the deploy-time seed Job.
    Idempotent; exits 0 on success or benign skip, non-zero on unexpected error."""
    from sanity.config import Config

    cfg = Config.from_env()
    if not cfg.can_reach_cm:
        print("[cm-seed] SANITY_CM_STAFF_URL not set — nothing to seed; skipping")
        return 0
    try:
        status = ensure_binding(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[cm-seed] FAILED to seed CM binding for '{cfg.cm_audience}': {exc}")
        return 1
    print(f"[cm-seed] CM binding '{cfg.cm_audience}' (partner_mgmt_id={cfg.pm_partner_id}): {status}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
