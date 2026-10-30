"""Detached DCI JWS. Canonical bytes match PyJWTCryptoHelper._canonical."""

from __future__ import annotations

import os
from pathlib import Path

import orjson
from cryptography.hazmat.primitives import serialization
from jwt.api_jws import PyJWS

_DEFAULT_KEY = (
    Path(__file__).resolve().parents[6]
    / "registry-platform"
    / "test"
    / "sanity"
    / "sanity"
    / "testkey.py"
)


def _pem_from_testkey(path: Path) -> str:
    text = path.read_text()
    start = text.index("-----BEGIN PRIVATE KEY-----")
    end = text.index("-----END PRIVATE KEY-----") + len("-----END PRIVATE KEY-----")
    return text[start:end]


def load_private_key():
    pem = os.environ.get("PARTNER_PRIVATE_KEY_PEM", "").strip()
    if not pem:
        key_file = os.environ.get("PARTNER_PRIVATE_KEY_FILE", "")
        path = Path(key_file) if key_file else _DEFAULT_KEY
        pem = _pem_from_testkey(path)
    return serialization.load_pem_private_key(pem.encode(), password=None)


def sign_envelope(header: dict, message: dict, private_key, kid: str) -> str:
    payload = orjson.dumps({"header": header, "message": message}, option=orjson.OPT_SORT_KEYS)
    full = PyJWS().encode(payload, private_key, algorithm="EdDSA", headers={"kid": kid})
    part1, _body, part3 = full.split(".")
    return f"{part1}..{part3}"
