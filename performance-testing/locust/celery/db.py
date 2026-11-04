"""Postgres connection for the celery backlog observer.

Uses DATABASE_URL when set, otherwise PGHOST / PGPORT / PGUSER / PGPASSWORD /
PGDATABASE. Does not embed credentials.
"""

from __future__ import annotations

import os

import psycopg2


def connect():
    url = os.environ.get("DATABASE_URL")
    if url:
        return psycopg2.connect(url)
    return psycopg2.connect(
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
        dbname=os.environ.get("PGDATABASE", "farmer_registry"),
    )


def fetch_one_int(conn, sql: str) -> int:
    with conn.cursor() as cur:
        cur.execute(sql)
        row = cur.fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def fetch_status_counts(conn, sql: str) -> dict[str, int]:
    with conn.cursor() as cur:
        cur.execute(sql)
        return {str(status): int(n) for status, n in cur.fetchall()}
