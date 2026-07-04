"""Partner-side signing for the Farmer Registry sanity suite.

The sanity acts as a partner: it signs TWO things with the same PM-registered key,
both as JWS verified by openg2p-fastapi-common's ``CryptoHelper``:

  * the **consent object** — a self-contained compact JWS (payload = claims),
    verified by the Consent Manager;
  * the **DCI envelope** — a detached JWS over ``{header, message}``, verified by
    the registry partner-api.

The envelope is DETACHED, so its canonicalisation must byte-match the verifier's:
fastapi-common uses ``orjson.dumps(..., OPT_SORT_KEYS)``. We use the same here.
"""

import orjson
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from jwt.api_jws import PyJWS


def load_private_key_pem(pem: str):
    return serialization.load_pem_private_key(pem.encode("utf-8"), password=None)


def alg_for_key(priv) -> str:
    if isinstance(priv, ed25519.Ed25519PrivateKey):
        return "EdDSA"
    if isinstance(priv, ec.EllipticCurvePrivateKey):
        return "ES256"
    if isinstance(priv, rsa.RSAPrivateKey):
        return "RS256"
    raise ValueError("unsupported private key type for sanity signing")


def _canonical(payload: dict) -> bytes:
    # MUST match openg2p_fastapi_common.utils.crypto.PyJWTCryptoHelper._canonical
    return orjson.dumps(payload, option=orjson.OPT_SORT_KEYS)


def sign_consent_jws(claims: dict, priv, kid: str, alg: str = "EdDSA") -> str:
    """Self-contained compact JWS (header.payload.signature) over the claims."""
    return PyJWS().encode(_canonical(claims), priv, algorithm=alg, headers={"kid": kid})


def sign_dci_envelope(header: dict, message: dict, priv, kid: str, alg: str = "EdDSA") -> str:
    """Detached JWS (``header..signature``) over ``{header, message}`` — the DCI
    envelope signature the registry verifies against the partner's PM key."""
    full = PyJWS().encode(
        _canonical({"header": header, "message": message}),
        priv,
        algorithm=alg,
        headers={"kid": kid},
    )
    part1, _payload, part3 = full.split(".")
    return f"{part1}..{part3}"
