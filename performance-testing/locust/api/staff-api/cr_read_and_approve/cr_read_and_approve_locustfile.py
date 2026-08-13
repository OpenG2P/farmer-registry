from __future__ import annotations

import random

from locust import tag, task

from shared.base_user import LocustUser
from shared.config import CR_SEARCH_PAGE_SIZE, REGISTER_FARMER, SEARCH_TERMS, STAFF_API_BASE
from shared.response_utils import safe_json
from shared.slo_shape import SLOStepRampShape
from cr_read_and_approve_helpers import (
    actionable_task,
    approval_blocked,
    extract_awe_request_id,
    pending_change_requests,
    response_error_code,
    response_payload,
    response_status,
    total_pages,
)

CR_ARTIFACT_TYPE = "registry.change_request"


class CrReadAndApproveRampShape(SLOStepRampShape):
    """Step 1 ramp-to-failure for cr_read_and_approve -- see
    shared/slo_shape.py and documentation/staff-api/test-scenarios.md §4/§5."""


class CrReadAndApproveUser(LocustUser):
    """Pages through every change request still PENDING approval and runs each one
    through the full read-and-approve sequence: get_change_request,
    check_change_request_sequence, get_deduplication_register_results,
    get_deduplication_change_request_results, list_tasks_for_request,
    submit_task_decision. Continues, page by page, until the search is
    exhausted.
    """

    host = STAFF_API_BASE

    def on_start(self):
        super().on_start()
        # Sticky per user for its whole session -- see
        # staff-api/register_read/register_read_locustfile.py /
        # documentation/seeding-design.md "Search-text anchors". Finds real
        # matches once cr_create has run (it edits bulk-seeded farmers, which
        # do have anchors embedded).
        self.search_text = random.choice(SEARCH_TERMS)
        print(f"\nDEBUG SEARCH_TERM anchored -> {self.search_text}\n")

    @tag("change_request", "write")
    @task
    def read_and_approve_change_requests(self):
        self._get_register_change_request_summary_data()

        current_page = 1
        pages_total = 1
        while current_page <= pages_total:
            search_response_json = safe_json(self._search_in_change_request(current_page))
            print(f"\nDEBUG search_in_change_request response_payload -> {response_payload(search_response_json)}\n")
            pages_total = total_pages(search_response_json)

            for change_request in pending_change_requests(search_response_json):
                self._process_change_request(change_request)

            current_page += 1

    def _process_change_request(self, change_request: dict):
        change_request_id = change_request["change_request_id"]
        section_id = change_request.get("section_id")

        self._get_change_request_documents(change_request_id)
        if section_id:
            self._get_section_ui_schema(section_id)
        change_request_response_json = safe_json(self._get_change_request(change_request_id))
        sequence_response_json = safe_json(self._check_change_request_sequence(change_request_id))
        if approval_blocked(sequence_response_json):
            print(f"\nDEBUG {change_request_id} -> approval blocked by an earlier pending change request, skipping\n")
            return

        self._get_deduplication_change_request_results(change_request_id)
        self._get_deduplication_register_results(change_request_id)

        awe_request_id = extract_awe_request_id(change_request_response_json)
        if not awe_request_id:
            return

        tasks_response_json = safe_json(self._list_tasks_for_request(awe_request_id))
        task = actionable_task(tasks_response_json)
        if not task:
            return

        decision_response_json = safe_json(
            self._submit_task_decision(
                task_id=task["id"],
                artifact_id=change_request_id,
                current_stage=task.get("stage_order") or 1,
            )
        )
        print(
            f"\nDEBUG DECISION RESULT for {change_request_id} -> "
            f"{response_status(decision_response_json)} {response_error_code(decision_response_json) or ''}\n"
        )

    # ------------------------------------------------------------------
    # get_register_change_request_summary_data (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _get_register_change_request_summary_data(self):
        payload = self.build_request(request_payload={})
        return self._post(
            STAFF_API_BASE,
            "/change-requests/get_register_change_request_summary_data",
            payload,
            name="get_register_change_request_summary_data",
        )

    # ------------------------------------------------------------------
    # search_in_change_request (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _search_in_change_request(self, current_page: int):
        payload = self.build_request(
            request_payload={},
            pagination_request={
                "current_page": current_page,
                "page_size": CR_SEARCH_PAGE_SIZE,
                "search_text": self.search_text,
            },
        )
        return self._post(
            STAFF_API_BASE, "/change-requests/search_in_change_request", payload, name="search_in_change_request"
        )

    # ------------------------------------------------------------------
    # get_change_request_documents (g2p_document_controller)
    # ------------------------------------------------------------------
    def _get_change_request_documents(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(
            STAFF_API_BASE,
            "/documents/get_change_request_documents",
            payload,
            name="get_change_request_documents",
        )

    # ------------------------------------------------------------------
    # get_section_ui_schema (g2p_register_section_metadata_controller)
    # ------------------------------------------------------------------
    def _get_section_ui_schema(self, section_id: str):
        payload = self.build_request(request_payload={"section_id": section_id, "register_id": REGISTER_FARMER})
        return self._post(
            STAFF_API_BASE, "/register-section-metadata/get_section_ui_schema", payload, name="get_section_ui_schema"
        )

    # ------------------------------------------------------------------
    # get_change_request (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _get_change_request(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(STAFF_API_BASE, "/change-requests/get_change_request", payload, name="get_change_request")

    # ------------------------------------------------------------------
    # check_change_request_sequence (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _check_change_request_sequence(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(
            STAFF_API_BASE,
            "/change-requests/check_change_request_sequence",
            payload,
            name="check_change_request_sequence",
        )

    # ------------------------------------------------------------------
    # list_tasks_for_request (g2p_awe_proxy_controller)
    # ------------------------------------------------------------------
    def _list_tasks_for_request(self, awe_request_id: str):
        payload = self.build_request(request_payload={"request_id": awe_request_id})
        return self._post(
            STAFF_API_BASE,
            "/awe/list_tasks_for_request",
            payload,
            name="list_tasks_for_request",
        )

    # ------------------------------------------------------------------
    # submit_task_decision (g2p_awe_proxy_controller)
    # ------------------------------------------------------------------
    def _submit_task_decision(self, task_id: str, artifact_id: str, current_stage: int):
        payload = self.build_request(
            request_payload={
                "task_id": task_id,
                "action": "approve",
                "artifact_id": artifact_id,
                "artifact_type": CR_ARTIFACT_TYPE,
                "current_stage": current_stage,
            },
        )
        return self._post(
            STAFF_API_BASE,
            "/awe/submit_task_decision",
            payload,
            name="submit_task_decision",
        )

    # ------------------------------------------------------------------
    # get_deduplication_register_results (g2p_register_data_controller)
    # ------------------------------------------------------------------
    def _get_deduplication_register_results(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(
            STAFF_API_BASE,
            "/register-data/get_deduplication_register_results",
            payload,
            name="get_deduplication_register_results",
        )

    # ------------------------------------------------------------------
    # get_deduplication_change_request_results (g2p_register_data_controller)
    # ------------------------------------------------------------------
    def _get_deduplication_change_request_results(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(
            STAFF_API_BASE,
            "/register-data/get_deduplication_change_request_results",
            payload,
            name="get_deduplication_change_request_results",
        )
