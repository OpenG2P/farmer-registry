"""Indexed DCI search cases for sync and async.

DCI_MODE=sync  posts /dci/sync/search and requires header.status=succ.
DCI_MODE=async posts /dci/async/search and requires message.ack_status=ACK.

Run one tag at a time. See SCENARIOS.md.
"""

from __future__ import annotations

import csv
import logging
import math
import os
import random
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import gevent
from gevent.lock import Semaphore
from locust import HttpUser, constant, constant_pacing, events, tag, task
from shared.slo_shape import SLOStepRampShape

_log = logging.getLogger("locust")

from signing import load_private_key, sign_envelope


class PartnerSearchRampShape(SLOStepRampShape):
    """4 users, then +4 every 30s, up to 100. Keep adding users while CPU
    and p99 are inside the gates. Freeze at 1.85 cores or p99 over 5000ms
    for two windows. Then hold that user count for 5 minutes and stop.

    Range cases set DCI_FIXED_USERS to 8 per pod (8, 16, or 24). Those
    runs stay at that count. Sync stops 10 minutes after Start. Async
    sets DCI_RECORD_BUDGET and stops once that many records have been
    requested. Each user sends one request, waits for the response, then
    sends the next. It does not add users.
    """

    _fixed_users = os.environ.get("DCI_FIXED_USERS", "").strip()
    warmup_users = int(_fixed_users) if _fixed_users.isdigit() else 4
    step_users = int(_fixed_users) if _fixed_users.isdigit() else 4
    freeze_when_rps_flat = False
    sustain_seconds = 5 * 60
    _range_seconds = os.environ.get("DCI_RANGE_RUN_SECONDS", "").strip()
    range_run_seconds = int(_range_seconds) if _range_seconds.isdigit() else 10 * 60
    record_budget = os.environ.get("DCI_RECORD_BUDGET", "").strip()

    def tick(self):
        if not self._fixed_users:
            return super().tick()
        if self.record_budget:
            return (self.warmup_users, self.step_users)
        run_time = self.get_run_time()
        if run_time >= self.range_run_seconds:
            if not getattr(self, "_range_stopped", False):
                self._range_stopped = True
                print(
                    f"[shape] range run complete: {self.range_run_seconds}s "
                    f"at {self.warmup_users} users"
                )
            return None
        return (self.warmup_users, self.step_users)

HOST = os.environ.get(
    "PARTNER_API_BASE",
    "https://partner-farmer-registry.perftest.openg2p.org",
)
MODE = os.environ.get("DCI_MODE", "sync").strip().lower()
SENDER_ID = os.environ.get("DCI_SENDER_ID", "Staff Portal")
RECEIVER_ID = os.environ.get("DCI_RECEIVER_ID", "farmer-registry")
KID = os.environ.get("PARTNER_KEY_KID", "perftest-staff-portal")
_SEED = Path(__file__).resolve().parents[6] / "perf-seed"
POOL = Path(os.environ.get("DCI_SEARCH_POOL", _SEED / "partner_search_pool.csv"))
WEEKS = Path(os.environ.get("DCI_BIRTH_WEEKS", _SEED / "partner_birth_weeks.csv"))
FIDS = Path(os.environ.get("DCI_FID_POOL", _SEED / "partner_btree_fids.txt"))
TERMS = Path(os.environ.get("DCI_SEARCH_TERMS", _SEED / "register_search_terms.txt"))
FID_POOL_SIZE = 100_000

PATHS = {
    "sync": "/dci/sync/search",
    "async": "/dci/async/search",
}
PAGE_SIZE = int(os.environ.get("DCI_PAGE_SIZE", "10"))
MAX_PAGES = 10
RECORDS_LOG = os.environ.get("DCI_RECORDS_LOG", "").strip()
KAFKA_START = os.environ.get("DCI_KAFKA_RECORDS_START", "").strip()
KAFKA_STOP = os.environ.get("DCI_KAFKA_RECORDS_STOP", "").strip()
RUN_ID = os.environ.get("DCI_RUN_ID", "").strip()


class _RecordsServed:
    """Records returned in response bodies, one row per minute."""

    def __init__(self):
        self._lock = Semaphore()
        self.started = 0.0
        self.total = 0
        self._open_minute = 0
        self._open_count = 0
        self._minutes: list[int] = []
        self._written = 0
        self._loop = None

    def start(self):
        with self._lock:
            self.started = time.monotonic()
            self.total = 0
            self._open_minute = 0
            self._open_count = 0
            self._minutes = []
            self._written = 0
        if self._loop is None:
            self._loop = gevent.spawn(self._watch)

    def add(self, count: int):
        if count <= 0 or self.started <= 0:
            return
        with self._lock:
            self._roll()
            self._open_count += count
            self.total += count

    def _roll(self):
        minute = int((time.monotonic() - self.started) // 60)
        while self._open_minute < minute:
            self._minutes.append(self._open_count)
            self._open_minute += 1
            self._open_count = 0

    def _write(self, rows: list[int], include_log: bool):
        running = 0
        lines = ["minute,processed_records,records_total"]
        for minute, count in enumerate(rows, start=1):
            running += count
            lines.append(f"{minute},{count},{running}")
            if include_log and minute > self._written:
                print(f"[served] minute {minute}: processed {count}, total {running}")
        if RECORDS_LOG:
            Path(RECORDS_LOG).write_text("\n".join(lines) + "\n")
        self._written = len(rows)

    def _watch(self):
        while True:
            gevent.sleep(5)
            if self.started <= 0:
                continue
            with self._lock:
                self._roll()
                if len(self._minutes) <= self._written:
                    continue
                self._write(list(self._minutes), include_log=True)

    def finish(self):
        if self.started <= 0:
            return
        with self._lock:
            self._roll()
            rows = list(self._minutes)
            if self._open_count or not rows:
                rows.append(self._open_count)
            elapsed = time.monotonic() - self.started
            total = self.total
            self._write(rows, include_log=True)
        print(f"[served] {elapsed / 60:.1f} min: processed {total} records")
        if RECORDS_LOG:
            print(f"[served] wrote {RECORDS_LOG}")


_served = _RecordsServed()


class _RecordBudget:
    """Stop once this many farmer rows have been requested.

    Async has no total_count on the ACK, so the cap is the sync run's
    records_total. The last request uses a smaller page size when the
    remainder is below the page size.
    """

    def __init__(self):
        raw = os.environ.get("DCI_RECORD_BUDGET", "").strip()
        self.limit = int(raw) if raw.isdigit() else 0
        self.sent = 0
        self._lock = Semaphore()
        self._quit_sent = False
        self.runner = None

    def take(self, page_size: int) -> int | None:
        if self.limit <= 0:
            return page_size
        with self._lock:
            left = self.limit - self.sent
            if left <= 0:
                return None
            size = page_size if page_size < left else left
            self.sent += size
            return size

    def quit_if_spent(self):
        if self.limit <= 0 or self.sent < self.limit or self._quit_sent:
            return
        self._quit_sent = True
        print(
            f"[served] requested {self.sent} records "
            f"(budget {self.limit}); stopping"
        )
        if self.runner is not None:
            self.runner.quit()


_budget = _RecordBudget()


class _KafkaDone:
    """Ids whose on-search publish has been read from Kafka."""

    def __init__(self):
        self.path = os.environ.get("DCI_KAFKA_DONE_FILE", "").strip()
        self.ids: set[str] = set()
        self._lock = Semaphore()
        self._offset = 0
        self._loop = None

    def start(self):
        if not self.path or self._loop is not None:
            return
        self._loop = gevent.spawn(self._watch)

    def _watch(self):
        while True:
            self._read()
            gevent.sleep(0.2)

    def _read(self):
        path = Path(self.path)
        if not path.is_file():
            return
        with path.open() as handle:
            handle.seek(self._offset)
            chunk = handle.read()
            self._offset = handle.tell()
        if not chunk:
            return
        with self._lock:
            for line in chunk.splitlines():
                tid = line.strip()
                if tid:
                    self.ids.add(tid)

    def wait(self, transaction_id: str, timeout: float = 45.0) -> bool:
        if not self.path:
            return True
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _budget._quit_sent:
                return False
            self._read()
            with self._lock:
                if transaction_id in self.ids:
                    return True
            gevent.sleep(0.2)
        _log.warning("kafka publish not seen within %.0fs: %s", timeout, transaction_id)
        return False


_kafka_done = _KafkaDone()


class _InFlight:
    """Cap searches the pod has accepted but not finished.

    Each worker's pool is 30 connections. The cap stays under that, scaled
    by pods and workers, so a search is not left waiting until the pool
    throws it away. The slot is released when Kafka sees the publish.
    """

    def __init__(self):
        raw = os.environ.get("DCI_ASYNC_INFLIGHT", "").strip()
        self.limit = int(raw) if raw.isdigit() else 0
        self._sem = Semaphore(self.limit) if self.limit else None

    def acquire(self) -> bool:
        if self._sem is None:
            return True
        while not _budget._quit_sent:
            if self._sem.acquire(timeout=0.5):
                return True
        return False

    def release(self):
        if self._sem is not None:
            self._sem.release()

    def release_when_published(self, transaction_id: str):
        try:
            _kafka_done.wait(transaction_id, timeout=40.0)
        finally:
            self.release()


_inflight = _InFlight()


@events.test_start.add_listener
def _served_start(environment, **kwargs):
    _budget.runner = environment.runner
    _kafka_done.start()
    if RECORDS_LOG:
        _served.start()
    if KAFKA_START:
        # Wall-clock origin for the Kafka minute buckets. Minute 1 is the
        # next 60 seconds from this instant.
        Path(KAFKA_START).write_text(f"{time.time():.6f}\n")


@events.test_stop.add_listener
def _served_stop(environment, **kwargs):
    if RECORDS_LOG:
        _served.finish()
    if KAFKA_STOP:
        Path(KAFKA_STOP).write_text("stop\n")


def _load_pool() -> list[dict]:
    if not POOL.is_file():
        raise SystemExit(f"search pool not found: {POOL}. Run prepare_dci.sh first.")
    with POOL.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"search pool is empty: {POOL}")
    return rows


def _load_weeks() -> list[dict]:
    """One-week windows on birth dates the spread job already committed."""
    if not WEEKS.is_file():
        raise SystemExit(f"birth week file not found: {WEEKS}")
    with WEEKS.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) < 1000:
        raise SystemExit(f"birth week file has {len(rows)} rows: {WEEKS}")
    return rows


def _load_fids() -> list[dict]:
    if not FIDS.is_file():
        raise SystemExit(f"functional id pool not found: {FIDS}. Run prepare_fids.sh first.")
    rows = []
    seen = set()
    for raw in FIDS.read_text().splitlines():
        fid = raw.strip()
        if not fid or fid.startswith("#") or fid in seen:
            continue
        seen.add(fid)
        rows.append({"functional_record_id": fid})
    if len(rows) < FID_POOL_SIZE:
        raise SystemExit(
            f"functional id pool has {len(rows)} ids; need {FID_POOL_SIZE}: {FIDS}"
        )
    return rows


def _load_terms() -> list[str]:
    if not TERMS.is_file():
        raise SystemExit(f"search terms not found: {TERMS}")
    terms = []
    for raw in TERMS.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#"):
            terms.append(line)
    if len(terms) < 10000:
        raise SystemExit(f"search terms has {len(terms)} rows; need at least 10000: {TERMS}")
    return terms


_pace = os.environ.get("DCI_ASYNC_PACE_SECONDS", "").strip()


class DciSearchUser(HttpUser):
    host = HOST
    # Async range runs set a gap so the next search starts only after the
    # previous one has had time to finish its database work. The ACK itself
    # returns in tens of milliseconds and must not be the pace.
    wait_time = constant_pacing(float(_pace)) if _pace else constant(0)

    def on_start(self):
        if MODE not in PATHS:
            raise SystemExit("DCI_MODE must be sync or async")
        self.pool = _load_pool()
        self.weeks = _load_weeks()
        _log.info("birth weeks %s rows from %s", len(self.weeks), WEEKS)
        self.fids = None
        self.terms = _load_terms()
        self.private_key = load_private_key()
        self._active_pool = None
        self.anchor = None
        self._probe = True
        self.pending_pages = []
        self._last_index = None
        self.range_start = None
        self.range_end = None
        self.range_page = 1
        self.range_pages = None

    def _new_term(self):
        pool = self._active_pool
        indexes = list(range(len(pool)))
        if self._last_index is not None and len(indexes) > 1:
            indexes.remove(self._last_index)
        self._last_index = random.choice(indexes)
        self.anchor = pool[self._last_index]
        self._probe = True
        self.pending_pages = []
        return self.anchor

    def _ready(self, pool):
        """Stay on one anchor from `pool`. Page 1 learns the page count.
        Later requests open up to 10 pages in random order, then a new anchor.
        """
        if self._active_pool is not pool:
            self._active_pool = pool
            self.anchor = None
            self._probe = True
            self.pending_pages = []
            self._last_index = None
        if self.anchor is None:
            self._new_term()
        if self._probe:
            return self.anchor, 1, PAGE_SIZE
        if not self.pending_pages:
            self._new_term()
            return self.anchor, 1, PAGE_SIZE
        return self.anchor, self.pending_pages.pop(), PAGE_SIZE

    def _plan_pages(self, payload: dict) -> None:
        if not self._probe:
            return
        self._probe = False
        total = _total_count(payload)
        if total is None:
            chosen = list(range(2, MAX_PAGES + 1))
        else:
            page_count = max(1, math.ceil(total / PAGE_SIZE))
            if page_count <= 1:
                chosen = []
            elif page_count <= MAX_PAGES:
                chosen = list(range(2, page_count + 1))
            else:
                chosen = random.sample(range(2, page_count + 1), MAX_PAGES - 1)
        random.shuffle(chosen)
        self.pending_pages = chosen

    def _criteria(self, query_type: str, query: dict | list, page: int, size: int) -> dict:
        return {
            "version": "1.0.0",
            "reg_type": "Farmer",
            "reg_record_type": "farmer",
            "query_type": query_type,
            "query": query,
            "pagination": {"page_size": size, "page_number": page},
        }

    def _pick_week(self) -> tuple[str, str]:
        """One start/end pair from perf-seed/partner_birth_weeks.csv."""
        row = random.choice(self.weeks)
        start, end = row.get("start_date", ""), row.get("end_date", "")
        if not start or not end:
            raise SystemExit(f"birth week row has no start_date/end_date: {row}")
        return start, end

    def _range_page(self) -> tuple[str, str, int, int]:
        """Stay on one week until every page of that week has been requested."""
        if self.range_start is None:
            self.range_start, self.range_end = self._pick_week()
            self.range_page = 1
            self.range_pages = None
            _log.info(
                "%s range %s..%s page 1",
                MODE,
                self.range_start,
                self.range_end,
            )
        return self.range_start, self.range_end, self.range_page, PAGE_SIZE

    def _capped_range(self) -> tuple[str, str, int, int] | None:
        size = _budget.take(PAGE_SIZE)
        if size is None:
            _budget.quit_if_spent()
            return None
        start, end, page, _full = self._range_page()
        return start, end, page, size

    def _finish_range_page(self, payload: dict) -> None:
        _served.add(_page_record_count(payload))
        if self.range_pages is None:
            total = _total_count(payload)
            if isinstance(total, int):
                self.range_pages = max(1, math.ceil(total / PAGE_SIZE))
            else:
                self.range_pages = self.range_page
        if self.range_page >= self.range_pages:
            _log.info(
                "%s range %s..%s done pages=%s",
                MODE,
                self.range_start,
                self.range_end,
                self.range_pages,
            )
            self.range_start = None
            return
        self.range_page += 1

    def _expression(self, query_body: dict, page: int, size: int) -> dict:
        return self._criteria(
            "expression",
            {"type": "expression", "value": {"expression": {"query": query_body}}},
            page,
            size,
        )

    def _post(self, name: str, criteria: dict, track_pages: bool = True) -> dict | None:
        message_id = uuid.uuid4().hex
        # Async results come back on a shared topic. The run id is echoed
        # on message.transaction_id so the Kafka counter can ignore every
        # other publish.
        if RUN_ID:
            transaction_id = f"{RUN_ID}-{message_id}"
            if len(transaction_id) > 99:
                transaction_id = transaction_id[:99]
        else:
            transaction_id = message_id
        header = {
            "version": "1.0.0",
            "message_id": message_id,
            "message_ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "action": "search",
            "sender_id": SENDER_ID,
            "receiver_id": RECEIVER_ID,
            "is_msg_encrypted": False,
        }
        message = {
            "transaction_id": transaction_id,
            "search_request": [
                {"reference_id": message_id[:32], "search_criteria": criteria}
            ],
        }
        body = {
            "signature": sign_envelope(header, message, self.private_key, KID),
            "header": header,
            "message": message,
        }
        if not _inflight.acquire():
            return None
        path = PATHS[MODE]
        try:
            # The ACK returns in tens of milliseconds and Locust would reuse
            # that TCP connection. Gunicorn then keeps every follow-up search
            # on the one worker that accepted it, and the other worker stays
            # idle. Closing the connection lets both workers accept.
            post_headers = {"Connection": "close"} if MODE == "async" else None
            with self.client.post(
                path,
                json=body,
                headers=post_headers,
                name=f"{MODE}:{name}",
                catch_response=True,
            ) as response:
                payload = self._check(response, track_pages=track_pages)
        except Exception:
            _inflight.release()
            raise
        if payload is not None and _inflight.limit:
            gevent.spawn(_inflight.release_when_published, transaction_id)
        else:
            _inflight.release()
        return payload

    def _check(self, response, track_pages: bool = True) -> dict | None:
        if response.status_code != 200:
            response.failure(f"HTTP {response.status_code}")
            return None
        try:
            payload = response.json()
        except ValueError:
            response.failure("response is not JSON")
            return None
        if payload.get("errors"):
            response.failure(str(payload["errors"]))
            return None
        if MODE == "sync":
            status = (payload.get("header") or {}).get("status")
            if status != "succ":
                header = payload.get("header") or {}
                response.failure(
                    f"status={status} {header.get('status_reason_code')} {header.get('status_reason_message')}"
                )
                return None
            if track_pages:
                self._plan_pages(payload)
            return payload
        ack = (payload.get("message") or {}).get("ack_status")
        if ack != "ACK":
            error = (payload.get("message") or {}).get("error")
            response.failure(f"ack_status={ack} {error}")
            return None
        if track_pages:
            self._plan_pages(payload)
        return payload

    @tag("btree_fid")
    @task
    def btree_functional_id(self):
        if self.fids is None:
            self.fids = _load_fids()
        row, page, size = self._ready(self.fids)
        self._post(
            "btree_fid",
            self._expression({"functional_record_id": {"$eq": row["functional_record_id"]}}, page, size),
        )

    @tag("btree_uin")
    @task
    def btree_foundational_id(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "btree_uin",
            self._expression({"foundational_id": {"$eq": row["foundational_id"]}}, page, size),
        )

    @tag("btree_birth")
    @task
    def btree_birth_date(self):
        row, page, size = self._ready(self.weeks)
        day = row["start_date"]
        self._post(
            "btree_birth",
            self._expression(
                {
                    "$and": [
                        {"birth_date": {"$gte": day}},
                        {"birth_date": {"$lte": day}},
                    ]
                },
                page,
                size,
            ),
        )

    @tag("gin_first")
    @task
    def gin_first_name(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "gin_first",
            self._expression({"first_name": {"$startsWith": row["first_name"][:3]}}, page, size),
        )

    @tag("gin_last")
    @task
    def gin_last_name(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "gin_last",
            self._expression({"last_name": {"$startsWith": row["last_name"][:3]}}, page, size),
        )

    @tag("gin_text")
    @task
    def gin_search_text(self):
        term, page, size = self._ready(self.terms)
        self._post(
            "gin_text",
            self._expression({"search_text": {"$contains": term}}, page, size),
        )

    @tag("composite")
    @task
    def composite_name_and_birth(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "composite",
            self._expression(
                {
                    "$and": [
                        {"last_name": {"$startsWith": row["last_name"][:3]}},
                        {"first_name": {"$startsWith": row["first_name"][:3]}},
                        {"birth_date": {"$eq": row["birth_date"]}},
                    ]
                },
                page,
                size,
            ),
        )

    @tag("expression")
    @task
    def query_expression(self):
        capped = self._capped_range()
        if capped is None:
            return
        start, end, page, size = capped
        payload = self._post(
            "expression",
            self._expression(
                {"$and": [{"birth_date": {"$gte": start}}, {"birth_date": {"$lte": end}}]},
                page,
                size,
            ),
            track_pages=False,
        )
        if payload is not None:
            self._finish_range_page(payload)
        _budget.quit_if_spent()

    @tag("predicate")
    @task
    def query_predicate(self):
        capped = self._capped_range()
        if capped is None:
            return
        start, end, page, size = capped
        payload = self._post(
            "predicate",
            self._criteria(
                "predicate",
                [
                    {
                        "seq_num": 1,
                        "expression1": {
                            "attribute_name": "birth_date",
                            "operator": "ge",
                            "attribute_value": start,
                        },
                    },
                    {
                        "seq_num": 2,
                        "expression1": {
                            "attribute_name": "birth_date",
                            "operator": "le",
                            "attribute_value": end,
                        },
                    },
                ],
                page,
                size,
            ),
            track_pages=False,
        )
        if payload is not None:
            self._finish_range_page(payload)
        _budget.quit_if_spent()

    @tag("graphql")
    @task
    def query_graphql(self):
        capped = self._capped_range()
        if capped is None:
            return
        start, end, page, size = capped
        document = (
            "query { farmer(birth_date: "
            f'{{ gte: "{start}", lte: "{end}" }}) '
            "{ functional_record_id } }"
        )
        payload = self._post(
            "graphql",
            self._criteria(
                "graphql",
                {"type": "graphql", "value": {"expression": document}},
                page,
                size,
            ),
            track_pages=False,
        )
        if payload is not None:
            self._finish_range_page(payload)
        _budget.quit_if_spent()

    @tag("idtype_value")
    @task
    def query_idtype_value(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "idtype_value",
            self._criteria(
                "idtype-value",
                {"type": "FID", "value": row["functional_record_id"]},
                page,
                size,
            ),
        )

    @tag("id_fid")
    @task
    def idtype_fid(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "id_fid",
            self._criteria(
                "idtype-value",
                {"type": "FID", "value": row["functional_record_id"]},
                page,
                size,
            ),
        )

    @tag("id_uin")
    @task
    def idtype_uin(self):
        row, page, size = self._ready(self.pool)
        self._post(
            "id_uin",
            self._criteria(
                "idtype-value",
                {"type": "UIN", "value": row["foundational_id"]},
                page,
                size,
            ),
        )


def _page_record_count(payload: dict) -> int:
    message = payload.get("message") or {}
    count = 0
    for item in message.get("search_response") or []:
        records = ((item or {}).get("data") or {}).get("reg_records") or []
        if isinstance(records, list):
            count += len(records)
    return count


def _total_count(payload: dict) -> int | None:
    message = payload.get("message") or {}
    items = message.get("search_response") or []
    if items:
        pagination = (items[0] or {}).get("pagination") or {}
        total = pagination.get("total_count")
        if isinstance(total, int):
            return total
    total = message.get("total_count")
    if isinstance(total, int):
        return total
    return None
