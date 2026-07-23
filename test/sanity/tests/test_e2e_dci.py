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
#
# Farmer field-specific test (Set 2): the farmer DCI template
# (openg2p_farmer_to_dci) nests the demographics under
# <scope>.demographic_info, so the assertion below reaches one level deeper than
# the reference registry's individual_to_dci template does.

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
def test_dci_search_returns_the_consented_record(partner_client, cfg, priv, seeded, farmer_seeded, step):
    """The happy path: the partner actually gets the data it consented to."""
    step(f"building signed DCI search envelope (reg_type={cfg.reg_type}, search_text={cfg.search_text!r})")
    step(f"attaching consent object for scopes={cfg.data_scopes} (signed as a JWS with the PM partner key)")
    envelope = build_search_envelope(cfg, priv, with_consent=True)
    step(f"sending DCI search to partner-api {SEARCH_PATH} — registry will verify the envelope (PM key), "
         "call Consent Manager /validate, render each record through the DCI template, and clamp to consented scopes")
    resp = _require_succ(_post_search(partner_client, envelope))
    step("received DCI response with status='succ'")

    records = _records(resp)
    step(f"response carried {len(records)} record(s)")
    assert records, (
        f"no records returned for search_text '{cfg.search_text}'. The sanity farmer "
        f"{fixtures.FARMER_FUNCTIONAL_ID} should match. If the register is otherwise "
        f"healthy, check that dbSeed.loadTemplates=true — without the DCI template in "
        f"MinIO every record fails to render and the error surfaces as an empty 200."
    )

    # Consent asked for the farmer_personal_details scope, so it must be present
    # AND carry the values the data-seed Job injected. The farmer DCI template
    # nests name/birth_date under a `demographic_info` block inside the scope.
    scope = cfg.data_scopes[0]
    record = records[0]
    assert scope in record, f"consented scope '{scope}' missing from record: {sorted(record)}"

    step(f"asserting consented scope '{scope}' is present and carries the seeded demographics")
    demographic = (record.get(scope) or {}).get("demographic_info") or {}
    name = demographic.get("name") or {}
    assert name.get("given_name") == fixtures.FARMER["first_name"]
    assert name.get("surname") == fixtures.FARMER["last_name"]
    assert demographic.get("birth_date") == fixtures.FARMER["birth_date"]
    step("consented record returned the correct given_name / surname / birth_date ✓")


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
