"""Fail-closed cases: the search must be REJECTED when authorisation is absent.

Every rejection surfaces as **HTTP 200 with `header.status == "rjct"`** — the
controller funnels every failure through one broad handler and returns a signed
error envelope. So these assert on the body, never on the HTTP status.

Both gates are independently switchable and BOTH DEFAULT OFF in the chart. When
a gate is off the corresponding test is vacuous, so each one probes the
enforcement posture stamped into `header.meta` and skips rather than passing
for the wrong reason.
"""

import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519

from sanity.dci import build_search_envelope

SEARCH_PATH = "/dci/registry/sync/search"


def _post_search(partner_client, envelope):
    r = partner_client.post(SEARCH_PATH, json=envelope)
    assert r.status_code == 200, r.text
    return r.json()


def _status(resp):
    return (resp.get("header") or {}).get("status")


def _meta(resp):
    return (resp.get("header") or {}).get("meta") or {}


def _posture(partner_client, cfg, priv):
    """Learn which gates are actually on, from a normal consented call."""
    return _meta(_post_search(partner_client, build_search_envelope(cfg, priv, with_consent=True)))


@pytest.mark.e2e
def test_search_without_consent_is_rejected(partner_client, cfg, priv, seeded, farmer_seeded):
    if _posture(partner_client, cfg, priv).get("consent_enforcement") != "enabled":
        pytest.skip("consent enforcement disabled — a no-consent request is not rejected")

    resp = _post_search(partner_client, build_search_envelope(cfg, priv, with_consent=False))
    assert _status(resp) == "rjct", (
        f"expected 'rjct' when consent is missing and enforcement is on, got: {resp.get('header')}"
    )


@pytest.mark.e2e
def test_search_with_unverifiable_signature_is_rejected(
    partner_client, cfg, priv, seeded, farmer_seeded
):
    """Sign with a key that Partner Management does not hold for this partner.

    The envelope is well-formed and the consent is valid — only the signing key
    is wrong, so this isolates signature verification. Note that when
    `signature_validation` is disabled the signature is not inspected at all and
    any string passes, which is exactly why this skips instead of failing.
    """
    if _posture(partner_client, cfg, priv).get("signature_validation") != "enabled":
        pytest.skip("signature validation disabled — an unverifiable signature is not rejected")

    impostor = ed25519.Ed25519PrivateKey.generate()
    resp = _post_search(partner_client, build_search_envelope(cfg, impostor, with_consent=True))
    assert _status(resp) == "rjct", (
        f"expected 'rjct' for a signature made with an unregistered key, got: {resp.get('header')}"
    )


@pytest.mark.e2e
def test_search_with_wrong_consent_audience_is_rejected(
    partner_client, cfg, priv, seeded, farmer_seeded
):
    """A consent object whose `aud` matches no CM binding must be denied.

    `aud` is how the Consent Manager finds the partner binding that carries the
    policy; pointing it at a non-existent audience must not fall through to a
    permit.
    """
    if _posture(partner_client, cfg, priv).get("consent_enforcement") != "enabled":
        pytest.skip("consent enforcement disabled — consent contents are not inspected")

    import dataclasses

    bogus = dataclasses.replace(cfg, cm_audience="FR_SANITY_NO_SUCH_AUDIENCE")
    resp = _post_search(partner_client, build_search_envelope(bogus, priv, with_consent=True))
    assert _status(resp) == "rjct", (
        f"expected 'rjct' for a consent bound to an unknown audience, got: {resp.get('header')}"
    )
