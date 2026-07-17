"""Build the DCI search request the sanity partner sends to the registry.

The consent object (a compact JWS) is embedded at
``search_criteria.authorize.consent_jws``; the whole ``{header, message}`` is then
signed as a detached JWS (the envelope signature). Both are verified by the
registry / Consent Manager against the partner's Partner-Management key.
"""

import uuid
from datetime import datetime, timedelta, timezone

from . import fixtures
from .signing import sign_consent_jws, sign_dci_envelope


def make_consent_claims(cfg) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "@context": "https://openg2p.org/contexts/consent_object.jsonld",
        "@type": "ConsentObject",
        "jti": uuid.uuid4().hex,
        # The injected sanity farmer. NOTE: the registry never passes subject_id
        # to the Consent Manager and never filters rows by it — consent clamps
        # which FIELDS are returned, not which ROWS. This value is therefore
        # descriptive today, not enforced.
        "subject_id": {"type": "national_id", "value": fixtures.FARMER_FOUNDATIONAL_ID},
        "data_controller": cfg.controller_id,
        "aud": cfg.cm_audience,
        "purpose": {"code": "share_farm_profile", "text": "FR sanity"},
        "data_scopes": list(cfg.data_scopes),
        "fetch_type": "oneshot",
        "validity": {
            "valid_from": now.isoformat(),
            "valid_until": (now + timedelta(days=30)).isoformat(),
        },
        "issued_at": now.isoformat(),
    }


def _header(cfg) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "version": "1.0.0",
        "message_id": uuid.uuid4().hex,
        "message_ts": now.isoformat(),
        "action": "search",
        "sender_id": cfg.dci_sender_id,
        "receiver_id": cfg.dci_receiver_id,
    }


def _message(cfg, consent_jws) -> dict:
    now = datetime.now(timezone.utc)
    search_criteria = {
        "version": "1.0.0",
        "reg_type": cfg.reg_type,
        "reg_record_type": cfg.reg_record_type,
        "query_type": "expression",
        "query": {
            "type": "expression",
            "value": {"expression": {"query": {"search_text": {"$eq": cfg.search_text}}}},
        },
    }
    if consent_jws is not None:
        # Partners embed the consent JWS in the DCI-standard authorize block.
        search_criteria["authorize"] = {"consent_jws": consent_jws}

    return {
        "transaction_id": uuid.uuid4().hex,
        "search_request": [
            {
                "reference_id": uuid.uuid4().hex[:16],
                "timestamp": now.isoformat(),
                "search_criteria": search_criteria,
                "locale": "eng",
            }
        ],
    }


def build_search_envelope(cfg, priv, *, with_consent: bool = True) -> dict:
    """Return a fully-signed DCI search envelope ready to POST.

    When ``with_consent`` is False the consent JWS is omitted — used to exercise
    the fail-closed deny path when consent enforcement is on.
    """
    from .signing import alg_for_key

    alg = alg_for_key(priv)
    consent_jws = None
    if with_consent:
        consent_jws = sign_consent_jws(make_consent_claims(cfg), priv, cfg.pm_kid, alg=alg)

    header = _header(cfg)
    message = _message(cfg, consent_jws)
    signature = sign_dci_envelope(header, message, priv, cfg.pm_kid, alg=alg)
    return {"signature": signature, "header": header, "message": message}
