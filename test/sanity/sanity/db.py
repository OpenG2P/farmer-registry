"""Direct Postgres access for the sanity e2e.

Three databases are reachable, each for one reason the HTTP APIs cannot serve:

  * **registry** — inject the test farmer. There is no unauthenticated write API
    we are willing to depend on, and every staff-portal-api write is a change
    request (which is the *subject* of one test, not a fixture mechanism).
  * **awe** — register the sanity approver against the shipped policy's stages.
  * **audit** — assert audit events. Audit Manager exposes ingest + health only;
    it has no query endpoint, so the table is the only assertion surface.

All are optional: a missing DSN makes the dependent test skip, never fail.
"""

import contextlib

import psycopg2
import psycopg2.extras


def _dsn(host, port, dbname, user, password):
    if not (host and dbname and user):
        return None
    return {
        "host": host,
        "port": int(port or 5432),
        "dbname": dbname,
        "user": user,
        "password": password or "",
        "connect_timeout": 10,
    }


@contextlib.contextmanager
def connect(dsn):
    """Yield a cursor, committing on success. Raises if dsn is None."""
    if not dsn:
        raise RuntimeError("database not configured")
    conn = psycopg2.connect(**dsn)
    try:
        with conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
    finally:
        conn.close()


def query(dsn, sql, params=None):
    with connect(dsn) as cur:
        cur.execute(sql, params or ())
        return cur.fetchall()


def execute(dsn, sql, params=None):
    with connect(dsn) as cur:
        cur.execute(sql, params or ())
        return cur.rowcount
