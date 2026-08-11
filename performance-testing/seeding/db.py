"""Connection handling, batched COPY writer, and the defer-indexes /
ANALYZE steps described in README.md "Load mechanics"."""

import io
import json
from csv import writer as csv_writer
from datetime import date, datetime

import psycopg2

import config
from config import BATCH_SIZE


def connect():
    # references config.DB_DSN (not a bound import) so run.py's --dsn
    # override, applied by mutating config.DB_DSN before connect() is
    # called, takes effect.
    conn = psycopg2.connect(config.DB_DSN)
    conn.autocommit = False
    return conn


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
        with self.conn.cursor() as cur:
            cur.copy_expert(f"COPY {self.table} ({cols_sql}) FROM STDIN WITH (FORMAT csv)", out)
        self.conn.commit()
        self.total_written += len(self.buffer)
        self.buffer.clear()


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
    for indexname, _ in rows:
        cursor.execute(f"DROP INDEX IF EXISTS {indexname}")
    return [indexdef for _, indexdef in rows]


def recreate_indexes(cursor, index_defs: list[str]):
    for indexdef in index_defs:
        cursor.execute(indexdef)


def analyze(cursor, table: str):
    cursor.execute(f"ANALYZE {table}")
