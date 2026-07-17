"""Assert audit events landed in Audit Manager.

Audit Manager has **no query API** — its surface is ingest (`POST
/v1/auditmanager/events`) plus health/version/config. So the only way to assert
an event was recorded is to read its `audit_events` table (RANGE-partitioned
monthly by `occurred_at`).

The write path is asynchronous end-to-end: the registry middleware fires the
event with `asyncio.create_task` (fire-and-forget), Audit Manager returns 202
before enqueueing, and a consumer batch-writes from Kafka to Postgres. A
read-after-write would race, so callers must poll — `wait_for` below does.
"""

import time

from . import db

_RECENT = """
SELECT type, action, outcome, resource_type, resource_id, actor_type, actor_id, occurred_at
  FROM "public"."audit_events"
 WHERE occurred_at >= %s
   AND resource_id = %s
 ORDER BY occurred_at DESC
 LIMIT 50;
"""


def wait_for(cfg, resource_id, since, timeout=None, interval=3):
    """Poll audit_events for any event about `resource_id`.

    Returns the list of matching rows, or [] if none arrived within the timeout.
    """
    deadline = time.time() + (timeout if timeout is not None else cfg.audit_timeout)
    rows = []
    while time.time() < deadline:
        try:
            rows = db.query(cfg.audit_dsn, _RECENT, (since, str(resource_id)))
        except Exception:  # noqa: BLE001 — table may not exist yet on a fresh install
            rows = []
        if rows:
            return rows
        time.sleep(interval)
    return rows
