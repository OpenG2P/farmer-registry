"""A fixed TEST-ONLY Ed25519 private key for the Farmer Registry sanity e2e.

This is the SAME shared sanity identity the Consent Manager uses
(``PARTNER_CM_SANITY`` / kid ``cm-sanity-1``), so a single test partner exists in
Partner Management and both suites verify against it. The key is NOT secret and
MUST NEVER be used by a real partner — the sanity partner is bound to a dedicated
test controller/audience and is inert for real data sharing.

Only the private key is stored: the public half (which PM stores) is derived from
it at seed time, so there is a single source of truth for the pair.

Override with SANITY_PM_PRIVATE_KEY_PEM (+ a matching PM-seeded key) to manage
your own test key.
"""

# Ed25519 PKCS#8 private key — TEST ONLY. Same key as the Consent Manager sanity.
TEST_PRIVATE_KEY_PEM = """-----BEGIN PRIVATE KEY-----
MC4CAQAwBQYDK2VwBCIEIEzzrTrPbzYjc2k3BCPMcK6vaULPtmvxVo2EdKjSTW3a
-----END PRIVATE KEY-----
"""

# Stable identifiers for the shared persistent sanity partner in PM.
DEFAULT_PARTNER_ID = "PARTNER_CM_SANITY"
DEFAULT_KID = "cm-sanity-1"
