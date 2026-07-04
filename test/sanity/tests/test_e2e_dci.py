import pytest

from sanity.dci import build_search_envelope

# End-to-end DCI search through the full PEP path:
#   partner signs the DCI envelope + an embedded consent JWS with its PM key ->
#   registry verifies the envelope (PM key) -> registry calls Consent Manager
#   /validate for the consent JWS -> registry clamps returned fields to the
#   consented scopes. Seeds the shared sanity partner into PM (key) and CM
#   (binding + policy) first. Gated by SANITY_RUN_E2E + reachable PM/CM.

SEARCH_PATH = "/dci/registry/sync/search"


def _post_search(partner_client, envelope):
    # DCI returns HTTP 200 even for a rejected result (status lives in the body).
    r = partner_client.post(SEARCH_PATH, json=envelope)
    assert r.status_code == 200, r.text
    return r.json()


def _meta(resp):
    return (resp.get("header") or {}).get("meta") or {}


def _records(resp):
    search_response = (resp.get("message") or {}).get("search_response") or []
    if not search_response:
        return []
    return (search_response[0].get("data") or {}).get("reg_records") or []


@pytest.mark.e2e
def test_dci_search_with_consent_permits(partner_client, cfg, priv, seeded):
    resp = _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True))
    header = resp.get("header") or {}
    status = header.get("status")
    reason = header.get("status_reason_message") or ""

    if status == "rjct" and "pending" in reason.lower():
        pytest.skip(f"consent policy pending approval (AWE enabled): {reason}")
    assert status == "succ", f"expected 'succ', got '{status}': {reason}"

    # With consent enforcement on, every returned record must be clamped to the
    # consented scopes — a strict allow-list, never more than was consented to.
    if _meta(resp).get("consent_enforcement") == "enabled":
        allowed = set(cfg.data_scopes)
        for record in _records(resp):
            leaked = set(record.keys()) - allowed
            assert not leaked, f"record leaked fields outside consented scopes: {leaked}"


@pytest.mark.e2e
def test_dci_search_without_consent_denied(partner_client, cfg, priv, seeded):
    # Learn the enforcement posture from a normal consented call first.
    probe = _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True))
    if _meta(probe).get("consent_enforcement") != "enabled":
        pytest.skip("consent enforcement disabled — a no-consent request is not rejected")

    resp = _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=False))
    assert (resp.get("header") or {}).get("status") == "rjct", (
        f"expected 'rjct' when consent is missing and enforcement is on, got: {resp.get('header')}"
    )
