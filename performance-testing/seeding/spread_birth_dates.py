#!/usr/bin/env python3
"""Spread g2p_register_farmers.birth_date so any 7 days hold at most 1000 rows.

Does not reseed. Each calendar day receives at most 1000 // 7 rows (142), so
any seven consecutive dates hold at most 994. Dates start at 1200-01-01 and
run for ceil(n / 142) days. search_text is left unchanged.

Drops only ix_g2p_register_farmers_birth_date for the UPDATE, then recreates
it. If a previous run removed the search_text indexes, this job creates them
again and does not drop them. Idempotent: a second run spreads again.

Usage (same DSN as reassign_search_anchors.py):

    python spread_birth_dates.py
"""

from __future__ import annotations

import math
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

import psycopg2

MAX_PER_WEEK = int(os.environ.get("BIRTH_MAX_PER_WEEK", "1000"))
PER_DAY = max(1, MAX_PER_WEEK // 7)
BASE = date(1200, 1, 1)
BATCH_SIZE = int(os.environ.get("SEED_BATCH_SIZE", "50000"))

BIRTH_INDEX = (
    "ix_g2p_register_farmers_birth_date",
    "CREATE INDEX IF NOT EXISTS ix_g2p_register_farmers_birth_date "
    "ON g2p_register_farmers (birth_date)",
)
# Restored if missing. Never dropped by this job.
SEARCH_INDEXES = (
    (
        "idx_g2p_register_farmers_search_text_trigram",
        "CREATE INDEX IF NOT EXISTS idx_g2p_register_farmers_search_text_trigram "
        "ON g2p_register_farmers USING gin (search_text gin_trgm_ops)",
    ),
    (
        "idx_g2p_register_farmers_search_text_fts",
        "CREATE INDEX IF NOT EXISTS idx_g2p_register_farmers_search_text_fts "
        "ON g2p_register_farmers USING gin (to_tsvector('simple', coalesce(search_text, '')))",
    ),
)


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [birth] {msg}", flush=True)


def dsn() -> str:
    if any(k in os.environ for k in ("PGHOST", "PGDATABASE", "PGUSER", "PGPASSWORD")):
        host = os.environ.get("PGHOST", "localhost")
        port = os.environ.get("PGPORT", "5432")
        db = os.environ.get("PGDATABASE", "farmer_registry")
        user = os.environ.get("PGUSER", "postgres")
        password = os.environ.get("PGPASSWORD", "")
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"
    return os.environ.get(
        "SEED_DB_DSN",
        "postgresql://postgres:postgres@localhost:5432/farmer_registry",
    )


def redact(url: str) -> str:
    try:
        parsed = urlparse(url)
        if parsed.password:
            return url.replace(parsed.password, "***")
    except Exception:
        pass
    return url


def main() -> int:
    url = dsn()
    log(f"connecting {redact(url)}")
    log(f"max_per_week={MAX_PER_WEEK} per_day={PER_DAY} batch={BATCH_SIZE}")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    wall = time.monotonic()
    pending_indexes: list[tuple[str, str]] = []
    try:
        for stmt in (
            "SET maintenance_work_mem TO '2GB'",
            "SET work_mem TO '256MB'",
            "SET synchronous_commit TO off",
            "SET statement_timeout TO 0",
        ):
            cur.execute(stmt)
            log(f"session {stmt}")

        cur.execute("SELECT count(*) FROM g2p_register_farmers")
        n_farmers = cur.fetchone()[0]
        span_days = max(1, math.ceil(n_farmers / PER_DAY))
        last = BASE + timedelta(days=span_days - 1)
        log(
            f"farmers={n_farmers} span_days={span_days} "
            f"{BASE.isoformat()}..{last.isoformat()}"
        )
        if n_farmers == 0:
            log("no farmers")
            return 0

        for name, sql in SEARCH_INDEXES:
            log(f"ensure {name}")
            started = time.monotonic()
            cur.execute(sql)
            log(f"{name} ready in {time.monotonic() - started:.0f}s")

        name, sql = BIRTH_INDEX
        log(f"DROP INDEX {name}")
        started = time.monotonic()
        cur.execute(f"DROP INDEX IF EXISTS {name}")
        pending_indexes.append(BIRTH_INDEX)
        log(f"dropped {name} in {time.monotonic() - started:.0f}s")

        cur.execute("DROP TABLE IF EXISTS _farmer_birth_map")
        log("building _farmer_birth_map")
        started = time.monotonic()
        # MOD() avoids the % operator, which psycopg2 treats as a placeholder.
        # Cast to int: date + bigint is not an operator.
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE _farmer_birth_map AS
            SELECT ctid AS rid,
                   (DATE '{BASE.isoformat()}'
                     + MOD((row_number() OVER (ORDER BY ctid) - 1), {int(span_days)})::int)::date
                     AS birth_date
              FROM g2p_register_farmers
            """
        )
        cur.execute("CREATE INDEX ON _farmer_birth_map (rid)")
        log(f"map ready in {time.monotonic() - started:.0f}s")

        updated = 0
        batch_no = 0
        while True:
            batch_no += 1
            started = time.monotonic()
            cur.execute(
                """
                WITH batch AS (
                    SELECT rid, birth_date
                      FROM _farmer_birth_map
                     ORDER BY rid
                     LIMIT %s
                ),
                upd AS (
                    UPDATE g2p_register_farmers AS f
                       SET birth_date = b.birth_date
                      FROM batch b
                     WHERE f.ctid = b.rid
                    RETURNING f.ctid
                ),
                discarded AS (
                    DELETE FROM _farmer_birth_map m
                     USING batch b
                     WHERE m.rid = b.rid
                )
                SELECT count(*) FROM upd
                """,
                (BATCH_SIZE,),
            )
            n = cur.fetchone()[0]
            if not n:
                break
            updated += n
            log(
                f"batch {batch_no} updated={n} total={updated}/{n_farmers} "
                f"in {time.monotonic() - started:.1f}s"
            )

        log(f"CREATE INDEX {BIRTH_INDEX[0]}")
        started = time.monotonic()
        cur.execute(BIRTH_INDEX[1])
        pending_indexes.clear()
        log(f"btree rebuilt in {time.monotonic() - started:.0f}s")

        week_end = BASE + timedelta(days=6)
        cur.execute(
            """
            SELECT count(*)
              FROM g2p_register_farmers
             WHERE birth_date >= %s
               AND birth_date <= %s
            """,
            (BASE, week_end),
        )
        week_count = cur.fetchone()[0]
        log(f"week {BASE.isoformat()}..{week_end.isoformat()} rows={week_count}")
        if week_count > MAX_PER_WEEK:
            log(f"week has {week_count} rows, cap is {MAX_PER_WEEK}")
            return 1

        started = time.monotonic()
        cur.execute("ANALYZE g2p_register_farmers")
        log(f"ANALYZE g2p_register_farmers in {time.monotonic() - started:.0f}s")

        cur.execute("DROP TABLE IF EXISTS _farmer_birth_map")
        log(f"done wall={time.monotonic() - wall:.0f}s updated={updated}")
    except Exception as exc:
        log(f"failed: {exc}")
        raise
    finally:
        for name, sql in pending_indexes:
            try:
                log(f"restoring {name}")
                cur.execute(sql)
            except Exception as exc:
                log(f"restore {name} failed: {exc}")
        try:
            cur.execute("DROP TABLE IF EXISTS _farmer_birth_map")
        except Exception as exc:
            log(f"drop map failed: {exc}")
        for stmt in (
            "RESET maintenance_work_mem",
            "RESET work_mem",
            "RESET synchronous_commit",
            "RESET statement_timeout",
        ):
            try:
                cur.execute(stmt)
            except Exception as exc:
                log(f"RESET failed: {exc}")
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
