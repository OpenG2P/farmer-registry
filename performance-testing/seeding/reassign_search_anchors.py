#!/usr/bin/env python3
"""Reassign 10k search anchors on existing g2p_register_farmers rows.

Does not reseed. Updates first_name, record_name, and search_text only.
Drops the farmer search_text GIN index for the UPDATE, then recreates it.

Idempotent: a lowercase 4-char prefix that is in the new pool is stripped
and replaced; otherwise the new term is prepended (original Faker names
start with a capital, so they are not stripped on the first run).

Usage (same DSN as rebuild_indexes.py):

    python reassign_search_anchors.py
"""

from __future__ import annotations

import os
import random
import string
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import execute_values

SEARCH_ANCHOR_COUNT = 10_000
SEARCH_ANCHOR_LENGTH = 4
RANDOM_SEED = 42
BATCH_SIZE = int(os.environ.get("SEED_BATCH_SIZE", "50000"))
GIN_NAME = "idx_g2p_register_farmers_search_text_trigram"
GIN_SQL = (
    f"CREATE INDEX IF NOT EXISTS {GIN_NAME} "
    "ON g2p_register_farmers USING gin (search_text gin_trgm_ops)"
)


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [reanchor] {msg}", flush=True)


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
        p = urlparse(url)
        if p.password:
            return url.replace(p.password, "***")
    except Exception:
        pass
    return url


def generate_anchors(count: int = SEARCH_ANCHOR_COUNT, length: int = SEARCH_ANCHOR_LENGTH) -> list[str]:
    random.seed(RANDOM_SEED)
    anchors: set[str] = set()
    while len(anchors) < count:
        anchors.add("".join(random.choices(string.ascii_lowercase, k=length)))
    return sorted(anchors)


def main() -> int:
    url = dsn()
    anchors = generate_anchors()
    log(f"connecting {redact(url)}")
    log(f"anchors={len(anchors)} batch={BATCH_SIZE}")
    conn = psycopg2.connect(url)
    conn.autocommit = True
    cur = conn.cursor()
    wall = time.monotonic()
    try:
        for stmt in (
            "SET maintenance_work_mem TO '2GB'",
            "SET work_mem TO '256MB'",
            "SET synchronous_commit TO off",
            "CREATE EXTENSION IF NOT EXISTS pg_trgm",
        ):
            cur.execute(stmt)
            log(f"session {stmt}")

        cur.execute("SELECT count(*) FROM g2p_register_farmers")
        n_farmers = cur.fetchone()[0]
        log(f"farmers={n_farmers}")

        cur.execute("DROP TABLE IF EXISTS _seed_search_anchors")
        cur.execute("CREATE UNLOGGED TABLE _seed_search_anchors (idx smallint PRIMARY KEY, term text NOT NULL UNIQUE)")
        execute_values(
            cur,
            "INSERT INTO _seed_search_anchors (idx, term) VALUES %s",
            [(i, term) for i, term in enumerate(anchors)],
            page_size=1000,
        )
        log("loaded _seed_search_anchors")

        log(f"DROP INDEX {GIN_NAME}")
        started = time.monotonic()
        cur.execute(f"DROP INDEX IF EXISTS {GIN_NAME}")
        log(f"dropped GIN in {time.monotonic() - started:.0f}s")

        cur.execute("DROP TABLE IF EXISTS _farmer_anchor_map")
        log("building _farmer_anchor_map")
        started = time.monotonic()
        # Inline the divisor: psycopg2 treats SQL `%` as a placeholder, so
        # `n % %s` becomes IndexError rather than modulo.
        cur.execute(
            f"""
            CREATE UNLOGGED TABLE _farmer_anchor_map AS
            SELECT ctid AS rid,
                   ((row_number() OVER (ORDER BY ctid) - 1) % {int(SEARCH_ANCHOR_COUNT)})::smallint AS idx
              FROM g2p_register_farmers
            """
        )
        cur.execute("CREATE INDEX ON _farmer_anchor_map (rid)")
        log(f"map ready in {time.monotonic() - started:.0f}s")

        updated = 0
        batch_no = 0
        while True:
            batch_no += 1
            started = time.monotonic()
            cur.execute(
                """
                WITH batch AS (
                    SELECT rid, idx
                      FROM _farmer_anchor_map
                     ORDER BY rid
                     LIMIT %s
                ),
                upd AS (
                    UPDATE g2p_register_farmers AS f
                       SET first_name = v.new_first,
                           record_name = concat_ws(' ', v.new_first, f.last_name),
                           search_text = concat_ws(
                               ' ',
                               f.functional_record_id,
                               v.new_first,
                               f.last_name,
                               f.middle_name,
                               f.foundational_id,
                               f.birth_date::text,
                               f.address_line_1,
                               f.address_line_2
                           )
                    FROM (
                        SELECT f2.ctid AS rid,
                               a.term || CASE
                                   WHEN substring(f2.first_name FROM 1 FOR 4) ~ '^[a-z]{4}$'
                                   THEN substring(f2.first_name FROM 5)
                                   ELSE f2.first_name
                               END AS new_first
                          FROM g2p_register_farmers f2
                          JOIN batch b ON b.rid = f2.ctid
                          JOIN _seed_search_anchors a ON a.idx = b.idx
                    ) v
                    WHERE f.ctid = v.rid
                    RETURNING f.ctid
                ),
                discarded AS (
                    DELETE FROM _farmer_anchor_map m
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

        log(f"CREATE INDEX {GIN_NAME}")
        started = time.monotonic()
        cur.execute(GIN_SQL)
        log(f"GIN rebuilt in {time.monotonic() - started:.0f}s")

        started = time.monotonic()
        cur.execute("ANALYZE g2p_register_farmers")
        log(f"ANALYZE g2p_register_farmers in {time.monotonic() - started:.0f}s")

        cur.execute("DROP TABLE IF EXISTS _farmer_anchor_map")
        cur.execute("DROP TABLE IF EXISTS _seed_search_anchors")
        log("dropped helper tables")
    finally:
        for stmt in (
            "RESET maintenance_work_mem",
            "RESET work_mem",
            "RESET synchronous_commit",
        ):
            try:
                cur.execute(stmt)
            except Exception as exc:
                log(f"RESET failed: {exc}")
        cur.close()
        conn.close()

    log(f"done wall={time.monotonic() - wall:.0f}s updated={updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
