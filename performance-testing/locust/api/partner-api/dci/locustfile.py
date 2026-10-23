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
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from locust import HttpUser, constant, tag, task
from shared.slo_shape import SLOStepRampShape

_log = logging.getLogger("locust")

from signing import load_private_key, sign_envelope


class PartnerSearchRampShape(SLOStepRampShape):
    """4 users, then +4 every 30s, up to 100. Keep adding users while CPU
    and p99 are inside the gates. Freeze at 1.85 cores or p99 over 5000ms
    for two windows. Then hold that user count for 5 minutes and stop."""

    warmup_users = 4
    step_users = 4
    freeze_when_rps_flat = False
    sustain_seconds = 5 * 60

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
FIDS = Path(os.environ.get("DCI_FID_POOL", _SEED / "partner_btree_fids.txt"))
TERMS = Path(os.environ.get("DCI_SEARCH_TERMS", _SEED / "register_search_terms.txt"))
FID_POOL_SIZE = 100_000

PATHS = {
    "sync": "/dci/sync/search",
    "async": "/dci/async/search",
}
PAGE_SIZE = 10
MAX_PAGES = 10


def _load_pool() -> list[dict]:
    if not POOL.is_file():
        raise SystemExit(f"search pool not found: {POOL}. Run prepare_dci.sh first.")
    with POOL.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise SystemExit(f"search pool is empty: {POOL}")
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


class DciSearchUser(HttpUser):
    host = HOST
    wait_time = constant(0)

    def on_start(self):
        if MODE not in PATHS:
            raise SystemExit("DCI_MODE must be sync or async")
        self.pool = _load_pool()
        self.fids = None
        self.terms = _load_terms()
        self.private_key = load_private_key()
        self._active_pool = None
        self.anchor = None
        self._probe = True
        self.pending_pages = []
        self._last_index = None

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

    def _fresh_row(self):
        """One new farmer, page 1. Used when paging the same row repeats one result set."""
        self._active_pool = self.pool
        return self._new_term(), 1, PAGE_SIZE

    @staticmethod
    def _birth_window(row) -> tuple[str, str]:
        """Seven days from this farmer's birth date, so one page holds more than one day."""
        start = datetime.fromisoformat(row["birth_date"]).date()
        return start.isoformat(), (start + timedelta(days=6)).isoformat()

    def _expression(self, query_body: dict, page: int, size: int) -> dict:
        return self._criteria(
            "expression",
            {"type": "expression", "value": {"expression": {"query": query_body}}},
            page,
            size,
        )

    def _post(self, name: str, criteria: dict) -> None:
        message_id = uuid.uuid4().hex
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
            "transaction_id": message_id,
            "search_request": [
                {"reference_id": message_id[:32], "search_criteria": criteria}
            ],
        }
        body = {
            "signature": sign_envelope(header, message, self.private_key, KID),
            "header": header,
            "message": message,
        }
        path = PATHS[MODE]
        with self.client.post(
            path,
            json=body,
            name=f"{MODE}:{name}",
            catch_response=True,
        ) as response:
            _log.info("%s %s %s", f"{MODE}:{name}", response.status_code, response.text)
            self._check(response)

    def _check(self, response) -> None:
        if response.status_code != 200:
            response.failure(f"HTTP {response.status_code}")
            return
        try:
            payload = response.json()
        except ValueError:
            response.failure("response is not JSON")
            return
        if payload.get("errors"):
            response.failure(str(payload["errors"]))
            return
        if MODE == "sync":
            status = (payload.get("header") or {}).get("status")
            if status != "succ":
                header = payload.get("header") or {}
                response.failure(
                    f"status={status} {header.get('status_reason_code')} {header.get('status_reason_message')}"
                )
                return
            self._plan_pages(payload)
            return
        ack = (payload.get("message") or {}).get("ack_status")
        if ack != "ACK":
            error = (payload.get("message") or {}).get("error")
            response.failure(f"ack_status={ack} {error}")
            return
        self._plan_pages(payload)

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
        row, page, size = self._ready(self.pool)
        day = row["birth_date"]
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
        row, page, size = self._fresh_row()
        start, end = self._birth_window(row)
        self._post(
            "expression",
            self._expression(
                {"$and": [{"birth_date": {"$gte": start}}, {"birth_date": {"$lte": end}}]},
                page,
                size,
            ),
        )

    @tag("predicate")
    @task
    def query_predicate(self):
        row, page, size = self._fresh_row()
        start, end = self._birth_window(row)
        self._post(
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
        )

    @tag("graphql")
    @task
    def query_graphql(self):
        row, page, size = self._fresh_row()
        start, end = self._birth_window(row)
        document = (
            "query { farmer(birth_date: "
            f'{{ gte: "{start}", lte: "{end}" }}) '
            "{ functional_record_id } }"
        )
        self._post(
            "graphql",
            self._criteria(
                "graphql",
                {"type": "graphql", "value": {"expression": document}},
                page,
                size,
            ),
        )

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
