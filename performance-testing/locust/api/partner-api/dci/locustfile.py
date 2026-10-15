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
from datetime import datetime, timezone
from pathlib import Path

from locust import HttpUser, constant, tag, task
from shared.slo_shape import SLOStepRampShape

_log = logging.getLogger("locust")

from signing import load_private_key, sign_envelope


class PartnerSearchRampShape(SLOStepRampShape):
    """4 users, then +4 every 30s. Stop adding users when a step's successful
    RPS does not rise. Also freeze at 1.85 cores or p99 over 1000ms for two
    windows. Then soak at the last user count that still raised RPS."""

    warmup_users = 4
    freeze_when_rps_flat = True

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
TERMS = Path(os.environ.get("DCI_SEARCH_TERMS", _SEED / "register_search_terms.txt"))

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

    def _criteria(self, query_type: str, query: dict, page: int, size: int) -> dict:
        return {
            "version": "1.0.0",
            "reg_type": "Farmer",
            "reg_record_type": "farmer",
            "query_type": query_type,
            "query": query,
            "pagination": {"page_size": size, "page_number": page},
        }

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
        row, page, size = self._ready(self.pool)
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
