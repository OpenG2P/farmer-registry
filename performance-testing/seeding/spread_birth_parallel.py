#!/usr/bin/env python3
"""Finish the birth-date spread with one pod.

The five slice tables already assign each farmer one birth_date, at most
142 rows on any day. This process drains those tables in ctid order and
sets only g2p_register_farmers.birth_date. The last step builds
ix_g2p_register_farmers_birth_date.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone

import psycopg2
from psycopg2 import errors

BATCH_SIZE = int(os.environ.get("SEED_BATCH_SIZE", "50000"))
SLICES = [f"_birth_slice_{n}" for n in range(5)]
BIRTH_INDEX = "ix_g2p_register_farmers_birth_date"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [birth] {msg}", flush=True)


def connect():
    conn = psycopg2.connect(
        host=os.environ["PGHOST"],
        port=os.environ.get("PGPORT", "5432"),
        dbname=os.environ["PGDATABASE"],
        user=os.environ["PGUSER"],
        password=os.environ["PGPASSWORD"],
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = True
    return conn


def main() -> int:
    conn = connect()
    cur = conn.cursor()
    for stmt in (
        "SET statement_timeout TO 0",
        "SET synchronous_commit TO off",
        "SET work_mem TO '256MB'",
    ):
        cur.execute(stmt)

    present = []
    for name in SLICES:
        cur.execute("SELECT to_regclass(%s)", (name,))
        if cur.fetchone()[0] is None:
            continue
        cur.execute(f"SELECT count(*) FROM {name}")
        count = cur.fetchone()[0]
        log(f"{name} rows={count}")
        if count:
            present.append((name, count))
    if not present:
        log("no slice rows left")
    else:
        for name, count in present:
            updated = 0
            batch_no = 0
            log(f"draining {name} in ctid order")
            while True:
                batch_no += 1
                started = time.monotonic()
                try:
                    cur.execute(
                        f"""
                        WITH batch AS (
                            SELECT rid, birth_date
                              FROM {name}
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
                            DELETE FROM {name} AS s
                             USING batch b
                             WHERE s.rid = b.rid
                        )
                        SELECT count(*) FROM upd
                        """,
                        (BATCH_SIZE,),
                    )
                except errors.DeadlockDetected:
                    log(f"{name} batch {batch_no} deadlock, retry")
                    continue
                n = cur.fetchone()[0]
                if not n:
                    break
                updated += n
                log(
                    f"{name} batch {batch_no} updated={n} "
                    f"total={updated}/{count} in {time.monotonic() - started:.1f}s"
                )
            cur.execute(f"DROP TABLE IF EXISTS {name}")
            log(f"{name} done updated={updated}")

    cur.execute("SET maintenance_work_mem TO '2GB'")
    log(f"CREATE INDEX {BIRTH_INDEX}")
    started = time.monotonic()
    cur.execute(
        f"CREATE INDEX IF NOT EXISTS {BIRTH_INDEX} ON g2p_register_farmers (birth_date)"
    )
    log(f"btree ready in {time.monotonic() - started:.0f}s")
    cur.execute("DROP TABLE IF EXISTS _birth_worker_done")
    cur.close()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
