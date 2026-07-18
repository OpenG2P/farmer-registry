"""Idempotent injection of the sanity test farmer into the registry database.

Why SQL and not an API:
  * every staff-portal-api register write is a **change request** — using it to
    build a fixture would mean creating and approving a CR before the DCI test
    could run, entangling two tests;
  * the record must exist in a known, ACTIVE, already-approved state so the DCI
    search is deterministic.

Why the test data is injected at all rather than reusing seeded sample data:
the sample farmers are only present when `dbSeed.loadSampleData=true`, which a
production install turns off — the e2e must not depend on them.

**`search_text` is written explicitly.** On the ORM it is auto-populated by
SQLAlchemy event listeners, which do NOT fire for raw SQL. db-seed's
load_sample_data.py has the same constraint and does the same thing. The DCI
search is `search_text ILIKE '%<text>%'`, so this column is what makes the
injected record findable.
"""

from . import fixtures

_COLUMNS = [
    "internal_record_id", "functional_record_id",
    "record_name", "created_by", "created_at",
    "last_approved_at", "last_approved_by",
    "search_text", "record_status",
    "foundational_id", "first_name", "last_name", "given_name",
    "gender", "birth_date", "marital_status", "education_level",
    "language_code", "registration_date", "middle_name",
]

# Re-runnable: a second install/upgrade updates the row rather than colliding on
# the primary key, and resets the change-request field (middle_name) and
# search_text so every run starts from a known state.
_UPSERT = f"""
INSERT INTO "public"."g2p_register_farmers" ({", ".join(f'"{c}"' for c in _COLUMNS)})
VALUES ({", ".join(["%s"] * len(_COLUMNS))})
ON CONFLICT ("internal_record_id") DO UPDATE SET
    "search_text"   = EXCLUDED."search_text",
    "record_status" = EXCLUDED."record_status",
    "middle_name"   = EXCLUDED."middle_name",
    "first_name"    = EXCLUDED."first_name",
    "last_name"     = EXCLUDED."last_name",
    "birth_date"    = EXCLUDED."birth_date",
    "gender"        = EXCLUDED."gender";
"""

_CREATED_AT = "2026-01-01 00:00:00"


def _row():
    f = fixtures.FARMER
    full_name = f"{f['first_name']} {f['last_name']}"
    # The marker must be inside search_text — that is the only column the DCI
    # search matches on.
    search_text = " ".join([
        fixtures.SEARCH_MARKER,
        fixtures.FARMER_FUNCTIONAL_ID,
        full_name,
        f["gender"],
        f["birth_date"],
    ])
    return (
        fixtures.FARMER_INTERNAL_ID, fixtures.FARMER_FUNCTIONAL_ID,
        full_name, fixtures.CREATED_BY, _CREATED_AT,
        _CREATED_AT, fixtures.CREATED_BY,
        search_text, "ACTIVE",
        fixtures.FARMER_FOUNDATIONAL_ID, f["first_name"],
        f["last_name"], full_name,
        f["gender"], f["birth_date"], f["marital_status"], f["education_level"],
        f["language_code"], _CREATED_AT, fixtures.CR_VALUE_INITIAL,
    )


def ensure_seeded(cfg) -> str:
    """Insert (or reset) the sanity farmer. Returns "seeded"."""
    from . import db

    db.execute(cfg.registry_dsn, _UPSERT, _row())
    return "seeded"


def main() -> int:
    """CLI entrypoint (`python -m sanity.data_seed`) for the deploy-time Job.
    Idempotent; exits 0 on success or benign skip, non-zero on unexpected error."""
    from .config import Config

    cfg = Config.from_env()
    if not cfg.registry_dsn:
        print("[data-seed] registry DB not configured — nothing to seed; skipping")
        return 0
    try:
        status = ensure_seeded(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"[data-seed] FAILED to seed farmer '{fixtures.FARMER_FUNCTIONAL_ID}': {exc}")
        return 1
    print(f"[data-seed] farmer '{fixtures.FARMER_FUNCTIONAL_ID}': {status}")
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
