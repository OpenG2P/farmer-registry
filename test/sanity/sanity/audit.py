"""Assert audit events landed in Audit Manager.

Audit Manager has **no query API** — its surface is ingest (`POST
/v1/auditmanager/events`) plus health/version/config. So the only way to assert
an event was recorded is to read its `audit_events` table (RANGE-partitioned
monthly by `occurred_at`).

The write path is asynchronous end-to-end: the registry middleware fires the
event with `asyncio.create_task` (fire-and-forget), Audit Manager returns 202
before enqueueing, and a consumer batch-writes from Kafka to Postgres. A
read-after-write would race, so callers must poll — `wait_for` below does.

**Events are keyed by actor, not resource.** The staff-portal-api audit
middleware emits one event per HTTP request with `actor_id = <the user's sub>`
and `source = /openg2p/registry-staff-portal-api`, but it does NOT populate
`resource_id`/`action` (the controllers don't set `request.state.audit_*`). So
the audit trail for the change-request flow is found by the sanity user's
subject, not by the change-request id.
"""

import time

from . import db

_BY_ACTOR = """
SELECT source, type, outcome, occurred_at
  FROM "public"."audit_events"
 WHERE occurred_at >= %s
   AND actor_id = %s
   AND source LIKE %s
 ORDER BY occurred_at DESC
 LIMIT 50;
"""


def wait_for(cfg, actor_id, since, source_like="%registry%", timeout=None, interval=3):
    """Poll audit_events for any event attributed to `actor_id`.

    Returns the list of matching rows, or [] if none arrived within the timeout.
    """
    deadline = time.time() + (timeout if timeout is not None else cfg.audit_timeout)
    rows = []
    while time.time() < deadline:
        try:
            rows = db.query(cfg.audit_dsn, _BY_ACTOR, (since, str(actor_id), source_like))
        except Exception:  # noqa: BLE001 — table may not exist yet on a fresh install
            rows = []
        if rows:
            return rows
        time.sleep(interval)
    return rows
