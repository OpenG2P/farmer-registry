"""Connection handling, batched COPY writer, and the defer-indexes /
ANALYZE steps described in README.md "Load mechanics"."""

import io
import json
import os
import time
from csv import writer as csv_writer
from datetime import date, datetime, timezone
from urllib.parse import urlparse

import psycopg2

import config
from config import BATCH_SIZE

# Session-scoped advisory lock so parallel pods drop/rebuild indexes once.
_SEED_LOCK = 87421033
_WRITERS_TABLE = "_seed_active_writers"
_INDEX_BACKUP_TABLE = "_seed_deferred_indexes"


def log(msg: str) -> None:
    """UTC timestamp + pid, flushed so kubectl logs show lines immediately."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(f"{ts} [pid={os.getpid()}] {msg}", flush=True)


def _redact_dsn(dsn: str) -> str:
    try:
        parsed = urlparse(dsn)
        if parsed.password:
            user = parsed.username or ""
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            return f"{parsed.scheme}://{user}:***@{host}{port}{parsed.path}"
    except Exception:
        pass
    return dsn


def _build_dsn_from_env():
    """Build DSN from individual environment variables (Kubernetes pattern)."""
    pg_host = os.environ.get("PGHOST", "localhost")
    pg_port = os.environ.get("PGPORT", "5432")
    pg_database = os.environ.get("PGDATABASE", "g2p_registry")
    pg_user = os.environ.get("PGUSER", "postgres")
    pg_password = os.environ.get("PGPASSWORD", "postgres")

    return f"postgresql://{pg_user}:{pg_password}@{pg_host}:{pg_port}/{pg_database}"


def connect():
    # Build DSN from environment variables if they are set (Kubernetes pattern)
    # Environment variables take precedence over config.DB_DSN
    if any(key in os.environ for key in ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"]):
        config.DB_DSN = _build_dsn_from_env()
        log("[db] using PGHOST/PGPORT/PGDATABASE/PGUSER env for DSN")
    else:
        log("[db] no PG* env; using config.DB_DSN")

    log(f"[db] connecting { _redact_dsn(config.DB_DSN) }")

    # references config.DB_DSN (not a bound import) so run.py's --dsn
    # override, applied by mutating config.DB_DSN before connect() is
    # called, takes effect.
    conn = psycopg2.connect(config.DB_DSN)
    conn.autocommit = False
    return conn


def configure_bulk_session(conn):
    """Cheap commits + larger sort memory for COPY / index rebuild."""
    with conn.cursor() as cur:
        cur.execute("SET synchronous_commit TO off")
        cur.execute("SET work_mem TO '256MB'")
        cur.execute("SET maintenance_work_mem TO '1GB'")
    conn.commit()
    log("[db] session: synchronous_commit=off work_mem=256MB maintenance_work_mem=1GB")


def target_tables() -> list[str]:
    tables: list[str] = []
    for live_table, history_table, _ in config.TABLE_NAMES.values():
        tables.append(live_table)
        tables.append(history_table)
    return tables


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "t" if value else "f"
    if isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


class BatchWriter:
    """Buffers row dicts for one table and flushes via COPY ... FROM STDIN.

    An empty, unquoted CSV field is read back by Postgres as NULL (the
    default for FORMAT csv), which is why _to_text() maps None -> "" rather
    than needing an explicit NULL marker.
    """

    def __init__(self, conn, table: str, columns: list[str], batch_size: int = BATCH_SIZE):
        self.conn = conn
        self.table = table
        self.columns = columns
        self.batch_size = batch_size
        self.buffer: list[dict] = []
        self.total_written = 0
        self._flush_count = 0

    def add(self, row: dict):
        self.buffer.append(row)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        out = io.StringIO()
        writer = csv_writer(out)
        for row in self.buffer:
            writer.writerow(_to_text(row.get(col)) for col in self.columns)
        out.seek(0)

        cols_sql = ", ".join(self.columns)
        started = time.monotonic()
        with self.conn.cursor() as cur:
            cur.copy_expert(f"COPY {self.table} ({cols_sql}) FROM STDIN WITH (FORMAT csv)", out)
        elapsed = time.monotonic() - started
        n = len(self.buffer)
        self.total_written += n
        self.buffer.clear()
        self._flush_count += 1
        log(
            f"[copy] {self.table} +{n} rows in {elapsed:.1f}s "
            f"({n / elapsed if elapsed else 0:.0f}/s) total={self.total_written}"
        )
        # Commit every other COPY so WAL stays bounded without fsync-per-batch.
        if self._flush_count % 2 == 0:
            self.conn.commit()


def capture_and_drop_indexes(cursor, table: str) -> list[str]:
    """Captures CREATE INDEX statements for table's non-PK indexes, drops
    them, and returns the statements so recreate_indexes() can rebuild
    identically after the load. Leaves the primary key index in place
    (needed for FK-style lookups during generation)."""
    cursor.execute(
        """
        SELECT indexname, indexdef FROM pg_indexes
         WHERE tablename = %s AND indexname NOT LIKE '%%_pkey'
        """,
        (table,),
    )
    rows = cursor.fetchall()
    log(f"[index] {table}: dropping {len(rows)} non-PK index(es)")
    for indexname, _ in rows:
        cursor.execute(f"DROP INDEX IF EXISTS {indexname}")
        log(f"[index] dropped {indexname}")
    return [indexdef for _, indexdef in rows]


def recreate_indexes(cursor, index_defs: list[str]):
    total = len(index_defs)
    for i, indexdef in enumerate(index_defs, start=1):
        if not indexdef:
            continue
        name = indexdef.split()[2] if len(indexdef.split()) > 2 else indexdef[:80]
        log(f"[index] rebuild {i}/{total} {name}")
        started = time.monotonic()
        cursor.execute("SAVEPOINT idx_rebuild")
        try:
            cursor.execute(indexdef)
            cursor.execute("RELEASE SAVEPOINT idx_rebuild")
            log(f"[index] rebuilt {name} in {time.monotonic() - started:.0f}s")
        except psycopg2.errors.DuplicateTable:
            cursor.execute("ROLLBACK TO SAVEPOINT idx_rebuild")
            log(f"[index] skip {name} (already exists)")


def analyze(cursor, table: str):
    log(f"[analyze] {table}")
    started = time.monotonic()
    cursor.execute(f"ANALYZE {table}")
    log(f"[analyze] {table} done in {time.monotonic() - started:.0f}s")


def begin_deferred_indexes(conn, writer_id: str) -> None:
    """Drop non-PK indexes once; register this pod as an active writer."""
    tables = target_tables()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (_SEED_LOCK,))
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_INDEX_BACKUP_TABLE} (
                tablename text NOT NULL,
                indexdef text NOT NULL
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_WRITERS_TABLE} (
                writer_id text PRIMARY KEY
            )
            """
        )
        cur.execute(
            f"INSERT INTO {_WRITERS_TABLE} (writer_id) VALUES (%s) ON CONFLICT DO NOTHING",
            (writer_id,),
        )
        cur.execute(f"SELECT count(*) FROM {_INDEX_BACKUP_TABLE}")
        already_captured = cur.fetchone()[0] > 0
        if not already_captured:
            log("[db] dropping non-PK indexes on live + history tables")
            for table in tables:
                for indexdef in capture_and_drop_indexes(cur, table):
                    cur.execute(
                        f"INSERT INTO {_INDEX_BACKUP_TABLE} (tablename, indexdef) VALUES (%s, %s)",
                        (table, indexdef),
                    )
        else:
            log("[db] indexes already deferred by another pod")
            for table in tables:
                capture_and_drop_indexes(cur, table)
        conn.commit()
        cur.execute("SELECT pg_advisory_unlock(%s)", (_SEED_LOCK,))


def end_deferred_indexes(conn, writer_id: str) -> bool:
    """Unregister this pod. If it was the last writer, rebuild indexes.

    Returns True when this caller rebuilt indexes.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_lock(%s)", (_SEED_LOCK,))
        cur.execute(f"DELETE FROM {_WRITERS_TABLE} WHERE writer_id = %s", (writer_id,))
        cur.execute(f"SELECT count(*) FROM {_WRITERS_TABLE}")
        remaining = cur.fetchone()[0]
        if remaining > 0:
            conn.commit()
            cur.execute("SELECT pg_advisory_unlock(%s)", (_SEED_LOCK,))
            log(f"[db] {remaining} writer(s) still running; skipping index rebuild")
            return False

        log("[db] last writer: rebuilding deferred indexes")
        cur.execute(f"SELECT indexdef FROM {_INDEX_BACKUP_TABLE}")
        defs = [row[0] for row in cur.fetchall()]
        conn.commit()
        recreate_indexes(cur, defs)
        cur.execute(f"DROP TABLE IF EXISTS {_INDEX_BACKUP_TABLE}")
        cur.execute(f"DROP TABLE IF EXISTS {_WRITERS_TABLE}")
        conn.commit()
        cur.execute("SELECT pg_advisory_unlock(%s)", (_SEED_LOCK,))
        return True
