# Farmer Registry — sanity tests (field-specific, Set 2)

The Farmer Registry does **not** carry its own copy of the sanity suite. The
registry-platform publishes the whole suite as an image,
`openg2p/openg2p-registry-sanity-tests`, containing:

- the **harness** — signing, DCI envelope building, PM/CM/Keycloak/AWE seeding,
  DB helpers, step logging, and the `conftest.py` banners/fixtures;
- **Set 1 (extension-independent tests)** — `test_smoke.py` and
  `test_e2e_negative.py`: liveness, wiring, and the fail-closed cases (search
  without consent / bad signature / wrong audience is rejected). These are
  identical for every registry and run unchanged.

This directory holds only **Set 2 — the Farmer Registry's field-specific parts**,
which `docker/sanity-tests/Dockerfile` layers onto that base image (overwriting
the reference registry's versions at the same paths):

| File | What is farmer-specific |
|---|---|
| `sanity/fixtures.py`  | the seeded record + the `g2p_register_farmers` tables |
| `sanity/data_seed.py` | idempotent injection into `g2p_register_farmers` |
| `tests/test_e2e_dci.py` | the farmer DCI template nests demographics under `<scope>.demographic_info` |
| `tests/test_e2e_change_request.py` | the register/history rows are verified in the farmer tables |

Everything else (register id, DCI reg-type, search text, consent scopes, CR
tab/section) is **configuration**, supplied as env by the Helm chart's `sanity.*`
values — not baked here.

## Extending for another registry

A new registry repeats this pattern: build `FROM openg2p-registry-sanity-tests`,
overlay its own `fixtures.py` / `data_seed.py` and any test whose assertions are
template- or table-shaped, and set its `sanity.*` values. Set 1 and the harness
are inherited, so the platform-level guarantees (auth, consent enforcement,
approval-workflow integrity, audit) are re-verified for free.
