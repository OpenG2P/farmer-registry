"""Farmer Registry — Locust load test (STARTER).

Implements the blended workload from ../03-workload-model.md:
    reads 70% (search / record-read / dedup) · writes 20% · DCI search 10%

Task weights below approximate that mix. Run a single task class in isolation
for per-endpoint capacity (Phase 1), or the whole set for the blended runs.

IMPORTANT — request bodies are marked `TODO`. The exact JSON shapes
(SearchRegisterRequest, intake submission, change request, etc.) must be filled
from the registry-platform API schema / OpenAPI before a real run. The auth
flow, task structure, weights, and id parameterisation are production-shaped and
ready; only the payloads need finalising. Validate each request returns 2xx
once before driving load.

Usage:
    pip install locust requests
    export STAFF_API_BASE=http://<release>-staff-portal-api
    export KEYCLOAK_BASE=https://keycloak.<ns>.openg2p.org
    export OIDC_CLIENT_ID=fr-staff-portal OIDC_USERNAME=... OIDC_PASSWORD=...
    export SEED_MANIFEST=seed_manifest.json
    # headless, single endpoint (Phase 1), ramp to 200 users:
    locust -f locustfile.py --headless -u 200 -r 10 -t 10m \
           --host $STAFF_API_BASE --tags search --csv results/phase1_search
"""

import json
import os
import random

from locust import HttpUser, task, tag, between
from common import (
    TokenCache, STAFF_API_BASE, PARTNER_API_BASE, SEED_MANIFEST,
    REGISTER_FARMER,
)


def _load_manifest():
    """Sample of valid record ids / search terms across the full key space.
    Falls back to trivial defaults if the manifest isn't present yet."""
    if os.path.isfile(SEED_MANIFEST):
        with open(SEED_MANIFEST) as f:
            return json.load(f)
    return {"record_ids": ["FARMER-0000001"], "search_terms": ["a", "ma", "jo"]}


MANIFEST = _load_manifest()


class RegistryUser(HttpUser):
    # Closed-model think time. For an open-model (constant arrival) capacity run,
    # use a ConstantThroughput / pacing strategy instead and document it.
    wait_time = between(0.5, 2.0)
    host = STAFF_API_BASE

    def on_start(self):
        self.tokens = TokenCache()

    # ----- helpers -------------------------------------------------------
    def _post(self, base, path, payload, name):
        return self.client.post(
            f"{base}{path}",
            json=payload,
            headers=self.tokens.auth_header(),
            name=name,  # group stats by logical endpoint, not by URL with ids
        )

    def _rand_id(self):
        return random.choice(MANIFEST["record_ids"])

    def _rand_term(self):
        return random.choice(MANIFEST["search_terms"])

    # ----- READS (target ~70%) ------------------------------------------
    @tag("search", "read")
    @task(38)
    def search_in_a_register(self):
        # TODO: real SearchRegisterRequest body (register, filters, page, size)
        payload = {"register_mnemonic": REGISTER_FARMER,
                   "search_text": self._rand_term(), "page": 1, "page_size": 20}
        self._post(STAFF_API_BASE, "/register-data/search_in_a_register",
                   payload, name="search_in_a_register")

    @tag("record_read", "read")
    @task(21)
    def get_subject_record(self):
        # TODO: real get_subject_record body
        payload = {"register_mnemonic": REGISTER_FARMER, "record_id": self._rand_id()}
        self._post(STAFF_API_BASE, "/register-data/get_subject_record",
                   payload, name="get_subject_record")

    @tag("dedup", "read")
    @task(11)
    def deduplication(self):
        # TODO: real dedup request body (pg_trgm fuzzy — heaviest read)
        payload = {"register_mnemonic": REGISTER_FARMER, "record_id": self._rand_id()}
        self._post(STAFF_API_BASE, "/register-data/get_deduplication_register_results",
                   payload, name="get_deduplication_register_results")

    # ----- WRITES (target ~20%) -----------------------------------------
    @tag("write", "intake")
    @task(10)
    def intake_save(self):
        # TODO: real save_intake_form_submission body (a full farmer record)
        payload = {"register_mnemonic": REGISTER_FARMER, "data": {}}
        self._post(STAFF_API_BASE, "/intake-form-data/save_intake_form_submission",
                   payload, name="save_intake_form_submission")

    @tag("write", "change_request")
    @task(7)
    def change_request_create(self):
        # TODO: real create_change_request body
        payload = {"register_mnemonic": REGISTER_FARMER, "record_id": self._rand_id(), "changes": {}}
        self._post(STAFF_API_BASE, "/change-requests/create_change_request",
                   payload, name="create_change_request")

    @tag("write", "verification")
    @task(3)
    def add_verification(self):
        # TODO: real add_verification body
        payload = {"register_mnemonic": REGISTER_FARMER, "record_id": self._rand_id()}
        self._post(STAFF_API_BASE, "/verifications/add_verification",
                   payload, name="add_verification")

    # ----- DCI / partner search (target ~10%) ---------------------------
    @tag("dci", "read")
    @task(10)
    def dci_search(self):
        # TODO: real DCI sync/search body
        payload = {"query": {"text": self._rand_term()}}
        self._post(PARTNER_API_BASE, "/sync/search", payload, name="dci_sync_search")
