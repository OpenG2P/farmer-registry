#!/usr/bin/env python3
"""Build ix_g2p_register_farmers_birth_date and leave every row unchanged.

The birth-date spread stopped after 34,850,000 updates. _farmer_birth_map
still holds the other 15,233,664 planned dates. This job does not read or
drop that map and does not update g2p_register_farmers.
"""

from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

import psycopg2

INDEX = "ix_g2p_register_farmers_birth_date"


def log(msg: str) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [birth-index] {msg}", flush=True)


def dsn() -> str:
    host = os.environ.get("PGHOST", "localhost")
    port = os.environ.get("PGPORT", "5432")
    db = os.environ.get("PGDATABASE", "farmer_registry")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def redact(url: str) -> str:
    parsed = urlparse(url)
    if parsed.password:
        return url.replace(parsed.password, "***")
    return url


def main() -> int:
    url = dsn()
    log(f"connecting {redact(url)}")
    conn = psycopg2.connect(
        url,
        keepalives=1,
        keepalives_idle=30,
        keepalives_interval=10,
        keepalives_count=5,
    )
    conn.autocommit = True
    cur = conn.cursor()
    wall = time.monotonic()
    try:
        for stmt in (
            "SET maintenance_work_mem TO '2GB'",
            "SET statement_timeout TO 0",
        ):
            cur.execute(stmt)
            log(f"session {stmt}")
        log(f"CREATE INDEX {INDEX}")
        started = time.monotonic()
        cur.execute(
            f"CREATE INDEX IF NOT EXISTS {INDEX} ON g2p_register_farmers (birth_date)"
        )
        log(f"index ready in {time.monotonic() - started:.0f}s")
        started = time.monotonic()
        cur.execute("ANALYZE g2p_register_farmers")
        log(f"ANALYZE g2p_register_farmers in {time.monotonic() - started:.0f}s")
        log(f"done wall={time.monotonic() - wall:.0f}s")
    except Exception as exc:
        log(f"failed: {exc}")
        raise
    finally:
        cur.close()
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
