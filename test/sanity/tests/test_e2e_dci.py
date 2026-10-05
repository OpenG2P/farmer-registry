import json

import pytest

from sanity import fixtures
from sanity import dci as _dci
from sanity.dci import build_search_envelope

# End-to-end DCI search through the full PEP path:
#   partner signs the DCI envelope + an embedded consent JWS with its PM key ->
#   registry verifies the envelope (PM key) -> registry calls Consent Manager
#   /validate for the consent JWS -> registry filters each internal record to
#   the consented data scopes' fields -> registry renders it through the
#   register's outgoing DCI template.
#
# The record searched for is the sanity farmer injected by the data-seed Job, so
# these assertions never depend on `dbSeed.loadSampleData` being on.
#
# Farmer field-specific test (Set 2). The assertions look for the seeded values
# anywhere in the rendered record, so they hold whatever the farmer DCI
# template's layout (openg2p_farmer_to_dci nests demographics under
# farmer_personal_details.demographic_info). The scopes come from the chart's
# sanity.dataScopes / sanity.deniedScopes (Farmer Registry scope catalogue).

SEARCH_PATH = "/dci/registry/sync/search"


def _post_search(partner_client, envelope):
    """POST a DCI search. DCI answers HTTP 200 even for a rejection.

    Prefers the harness helper, which retries ONLY a transient dependency 5xx
    (e.g. Consent Manager handing out a stale pooled DB connection); a genuine
    policy denial is returned immediately and still fails the assertion.

    A variant image is built FROM a PINNED base image, so this overlay can be
    newer than the harness it lands on. Falling back to a plain POST keeps the
    suite runnable on a base image that predates the helper, instead of dying at
    collection with ImportError.
    """
    post = getattr(_dci, "post_search", None)
    if post is not None:
        return post(partner_client, SEARCH_PATH, envelope)
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
def test_dci_search_returns_the_consented_record(partner_client, cfg, priv, seeded, record_seeded, step):
    """The happy path: the partner actually gets the data it consented to."""
    step(f"building signed DCI search envelope (reg_type={cfg.reg_type}, search_text={cfg.search_text!r})")
    step(f"attaching consent object for scopes={cfg.data_scopes} (signed as a JWS with the PM partner key)")
    envelope = build_search_envelope(cfg, priv, with_consent=True)
    step(f"sending DCI search to partner-api {SEARCH_PATH} — registry will verify the envelope (PM key), "
         "call Consent Manager /validate, filter each record to the consented data scopes, and render it "
         "through the DCI template")
    resp = _require_succ(_post_search(partner_client, envelope))
    step("received DCI response with status='succ'")

    records = _records(resp)
    step(f"response carried {len(records)} record(s)")
    assert records, (
        f"no records returned for search_text '{cfg.search_text}'. The sanity record "
        f"{fixtures.RECORD_FUNCTIONAL_ID} should match. If the register is otherwise "
        f"healthy, check that dbSeed.loadTemplates=true — without the DCI template in "
        f"MinIO every record fails to render and the error surfaces as an empty 200."
    )

    # Consent asked for the demographic details scope (a section scope covering
    # first/last name and birth date), so the seeded values must come back —
    # wherever this register's template puts them.
    record = records[0]
    rendered = json.dumps(record, default=str)
    step(f"asserting the consented scopes {cfg.data_scopes} carried the seeded demographics")
    for field in ("first_name", "last_name", "birth_date"):
        assert str(fixtures.RECORD[field]) in rendered, (
            f"consented field {field}={fixtures.RECORD[field]!r} missing from record: {rendered[:500]}"
        )
    step("consented record returned the correct given_name / surname / birth_date ✓")


@pytest.mark.e2e
def test_dci_search_clamps_to_consented_scopes(partner_client, cfg, priv, seeded, record_seeded):
    """Fields outside the consented scopes must not come back.

    The registry filters the record to the consented scopes' fields before the
    template renders it. The catalogue (GET /partner/data_scopes) says which
    fields each scope covers: the seeded values of the denied scopes' fields
    (that no consented scope also covers) must appear nowhere in the record.
    """
    resp = _require_succ(
        _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True))
    )
    if _meta(resp).get("consent_enforcement") != "enabled":
        pytest.skip("consent enforcement disabled — nothing is filtered")

    records = _records(resp)
    assert records, "no records to assert filtering on"

    catalogue = partner_client.get("/partner/data_scopes")
    assert catalogue.status_code == 200, catalogue.text
    scopes = {s["scope_id"]: s for s in (catalogue.json().get("data_scopes") or [])}

    def fields_of(scope_ids):
        fields = set()
        for scope_id in scope_ids:
            scope = scopes.get(scope_id) or {}
            versions = scope.get("versions") or []
            if versions:
                fields.update(versions[-1].get("resolved_fields") or [])
        return fields

    consented = fields_of(cfg.data_scopes)
    seeded = {**fixtures.RECORD, "foundational_id": fixtures.RECORD_FOUNDATIONAL_ID}
    denied = {
        ref.split(".", 1)[1] for ref in fields_of(cfg.denied_scopes)
        if ref.startswith(f"{cfg.reg_type}.") and ref not in consented and f"{cfg.reg_type}.*" not in consented
    }
    checked = sorted(field for field in denied if seeded.get(field))
    assert checked, (
        f"none of the denied scopes {cfg.denied_scopes} covers a seeded field of {cfg.reg_type}; "
        "pick a denied scope with seeded fields (sanity.deniedScopes)"
    )
    for record in records:
        rendered = json.dumps(record, default=str)
        for field in checked:
            assert str(seeded[field]) not in rendered, (
                f"unconsented field {field} ({seeded[field]!r}) was returned"
            )
