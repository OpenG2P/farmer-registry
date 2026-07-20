"""Create the sanity e2e's own Keycloak user, via the Keycloak Admin API.

Why this exists — the two obvious shortcuts don't work:

  * **The demo users can't be used.** keycloak-init documents its user password
    as "(required) Initial password (temporary)", so Keycloak attaches an
    `UPDATE_PASSWORD` required action and any password grant fails with
    `invalid_grant: Account is not fully set up`. The schema exposes no
    `temporary` / `requiredActions` field, so this cannot be declared away in
    the chart's `realms` block.
  * **The registry's client has no service account.** It is declared as a
    browser OIDC client (redirectUris + clientRoles), and keycloak-init's
    schema has no `serviceAccountsEnabled` field — so `client_credentials` is
    rejected too.

So the suite provisions its own identity with the admin API, which is also what
was asked for: a TEST user, tagged and removable, that does not disturb the
shipped demo users' security posture (they keep their forced password change).

What it does, all idempotent:
  1. ensure the user exists in the staff realm;
  2. set its password with `temporary=False` and clear `requiredActions`, so the
     password grant works;
  3. grant it the client roles it needs to raise and approve change requests;
  4. ensure `directAccessGrantsEnabled` on the registry client — the password
     grant needs it, and keycloak-init cannot declare it.

Removal (not automatic — fixtures are left for inspection):
    DELETE the user `sanity-e2e` from the staff realm.
"""

import httpx

from . import fixtures


def _admin_token(cfg) -> str:
    r = httpx.post(
        f"{cfg.keycloak_base_url}/realms/master/protocol/openid-connect/token",
        data={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": cfg.keycloak_admin_user,
            "password": cfg.keycloak_admin_password,
        },
        verify=cfg.verify_tls,
        timeout=20,
    )
    if r.status_code != 200:
        raise RuntimeError(f"keycloak admin login failed ({r.status_code}): {r.text[:200]}")
    return r.json()["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _realm(cfg):
    return f"{cfg.keycloak_base_url}/admin/realms/{cfg.keycloak_realm}"


def _find_user(cfg, h, username):
    r = httpx.get(f"{_realm(cfg)}/users", params={"username": username, "exact": "true"},
                  headers=h, verify=cfg.verify_tls, timeout=20)
    r.raise_for_status()
    users = r.json()
    return users[0]["id"] if users else None


def _find_client(cfg, h, client_id):
    r = httpx.get(f"{_realm(cfg)}/clients", params={"clientId": client_id},
                  headers=h, verify=cfg.verify_tls, timeout=20)
    r.raise_for_status()
    clients = r.json()
    return clients[0] if clients else None


def _ensure_direct_access_grants(cfg, h, client):
    """The password grant needs directAccessGrantsEnabled; keycloak-init cannot
    declare it, so guarantee it here rather than depending on a Keycloak default."""
    if client.get("directAccessGrantsEnabled"):
        return "already-on"
    httpx.put(
        f"{_realm(cfg)}/clients/{client['id']}",
        headers=h,
        json={**client, "directAccessGrantsEnabled": True},
        verify=cfg.verify_tls,
        timeout=20,
    ).raise_for_status()
    return "enabled"


def _ensure_user(cfg, h, username):
    user_id = _find_user(cfg, h, username)
    if user_id:
        return user_id
    r = httpx.post(
        f"{_realm(cfg)}/users",
        headers=h,
        json={
            "username": username,
            "enabled": True,
            "emailVerified": True,
            "firstName": "Sanity",
            "lastName": "E2E",
            "email": f"{username}@sanity.invalid",
            # No required actions — this identity must be able to log in
            # non-interactively. This is a TEST user; the shipped demo users
            # keep their forced password change.
            "requiredActions": [],
        },
        verify=cfg.verify_tls,
        timeout=20,
    )
    if r.status_code not in (201, 409):
        raise RuntimeError(f"could not create user '{username}' ({r.status_code}): {r.text[:200]}")
    user_id = _find_user(cfg, h, username)
    if not user_id:
        raise RuntimeError(f"user '{username}' still not found after create")
    return user_id


def _set_password(cfg, h, user_id, password):
    httpx.put(
        f"{_realm(cfg)}/users/{user_id}/reset-password",
        headers=h,
        # temporary=False is the whole point: it is what stops Keycloak adding
        # UPDATE_PASSWORD and breaking the password grant.
        json={"type": "password", "value": password, "temporary": False},
        verify=cfg.verify_tls,
        timeout=20,
    ).raise_for_status()
    # Belt and braces: clear any required action inherited from realm defaults.
    httpx.put(
        f"{_realm(cfg)}/users/{user_id}",
        headers=h,
        json={"requiredActions": []},
        verify=cfg.verify_tls,
        timeout=20,
    ).raise_for_status()


def _grant_client_roles(cfg, h, user_id, client, role_names):
    r = httpx.get(f"{_realm(cfg)}/clients/{client['id']}/roles",
                  headers=h, verify=cfg.verify_tls, timeout=20)
    r.raise_for_status()
    available = {role["name"]: role for role in r.json()}
    missing = [n for n in role_names if n not in available]
    if missing:
        raise RuntimeError(
            f"client '{client['clientId']}' has no roles {missing} — "
            f"available: {sorted(available)}"
        )
    httpx.post(
        f"{_realm(cfg)}/users/{user_id}/role-mappings/clients/{client['id']}",
        headers=h,
        json=[available[n] for n in role_names],
        verify=cfg.verify_tls,
        timeout=20,
    ).raise_for_status()


def _grant_awe_admin(cfg, h, user_id) -> str:
    """Grant the AWE admin role (a role on the awe-admin-portal client) so the
    sanity user can approve every task on the change request, regardless of
    assignee. Non-fatal if the AWE admin client isn't present — the change-request
    approval test will then fail with a clear message rather than the seed dying.
    """
    awe_client = _find_client(cfg, h, cfg.awe_admin_client_id)
    if not awe_client:
        return f"skipped (client '{cfg.awe_admin_client_id}' not found)"
    _grant_client_roles(cfg, h, user_id, awe_client, [cfg.awe_admin_role])
    return f"{cfg.awe_admin_role}@{cfg.awe_admin_client_id}"


def ensure_user(cfg) -> str:
    """Provision the sanity user + client so the password grant works."""
    token = _admin_token(cfg)
    h = _headers(token)

    client = _find_client(cfg, h, cfg.staff_client_id)
    if not client:
        raise RuntimeError(f"keycloak client '{cfg.staff_client_id}' not found in realm '{cfg.keycloak_realm}'")
    dag = _ensure_direct_access_grants(cfg, h, client)

    user_id = _ensure_user(cfg, h, cfg.staff_username)
    _set_password(cfg, h, user_id, cfg.staff_password)
    _grant_client_roles(cfg, h, user_id, client, cfg.staff_roles)
    awe = _grant_awe_admin(cfg, h, user_id)
    return f"user={cfg.staff_username} roles={cfg.staff_roles} awe_admin={awe} directAccessGrants={dag}"


def main() -> int:
    """CLI entrypoint (`python -m sanity.keycloak_seed`) for the deploy-time Job."""
    from .config import Config

    cfg = Config.from_env()
    if not (cfg.keycloak_base_url and cfg.keycloak_admin_password):
        print("[kc-seed] Keycloak admin not configured — nothing to seed; skipping")
        return 0
    try:
        status = ensure_user(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[kc-seed] FAILED to provision '{fixtures.STAFF_USERNAME}': {exc}")
        return 1
    print(f"[kc-seed] {status}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
