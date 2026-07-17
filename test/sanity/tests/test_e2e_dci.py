import pytest

from sanity import fixtures
from sanity.dci import build_search_envelope

# End-to-end DCI search through the full PEP path:
#   partner signs the DCI envelope + an embedded consent JWS with its PM key ->
#   registry verifies the envelope (PM key) -> registry calls Consent Manager
#   /validate for the consent JWS -> registry renders each record through the
#   register's outgoing DCI template -> registry clamps the rendered record to
#   the consented scopes.
#
# The record searched for is the sanity farmer injected by the data-seed Job, so
# these assertions never depend on `dbSeed.loadSampleData` being on.

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


def _require_succ(resp):
    header = resp.get("header") or {}
    status = header.get("status")
    reason = header.get("status_reason_message") or ""
    if status == "rjct" and "pending" in reason.lower():
        pytest.skip(f"consent policy pending approval (AWE enabled): {reason}")
    assert status == "succ", f"expected 'succ', got '{status}': {reason}"
    return resp


@pytest.mark.e2e
def test_dci_search_returns_the_consented_record(partner_client, cfg, priv, seeded, farmer_seeded):
    """The happy path: the partner actually gets the data it consented to."""
    resp = _require_succ(
        _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True))
    )

    records = _records(resp)
    assert records, (
        f"no records returned for search_text '{cfg.search_text}'. The sanity farmer "
        f"{fixtures.FARMER_FUNCTIONAL_ID} should match. If the register is otherwise "
        f"healthy, check that dbSeed.loadTemplates=true — without the DCI template in "
        f"MinIO every record fails to render and the error surfaces as an empty 200."
    )

    # Consent asked for farmer_personal_details, so it must be present AND carry
    # the values the data-seed Job injected.
    scope = cfg.data_scopes[0]
    record = records[0]
    assert scope in record, f"consented scope '{scope}' missing from record: {sorted(record)}"

    demographic = (record[scope] or {}).get("demographic_info") or {}
    name = demographic.get("name") or {}
    assert name.get("given_name") == fixtures.FARMER["first_name"]
    assert name.get("surname") == fixtures.FARMER["last_name"]
    assert demographic.get("birth_date") == fixtures.FARMER["birth_date"]


@pytest.mark.e2e
def test_dci_search_clamps_to_consented_scopes(partner_client, cfg, priv, seeded, farmer_seeded):
    """Fields outside the consented scopes must not come back.

    Clamping is a strict allow-list over the rendered record's TOP-LEVEL keys,
    so this asserts both directions: the consented scope survives, and every
    scope we did not consent to is absent.
    """
    resp = _require_succ(
        _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True))
    )
    if _meta(resp).get("consent_enforcement") != "enabled":
        pytest.skip("consent enforcement disabled — nothing is clamped")

    records = _records(resp)
    assert records, "no records to assert clamping on"

    allowed = set(cfg.data_scopes)
    for record in records:
        leaked = set(record.keys()) - allowed
        assert not leaked, f"record leaked fields outside consented scopes: {sorted(leaked)}"
        for denied in cfg.denied_scopes:
            assert denied not in record, f"unconsented scope '{denied}' was returned"
