from __future__ import annotations

import random

from locust import tag, task

from shared.base_user import LocustUser
from shared.config import INTAKE_SEARCH_PAGE_SIZE, REGISTER_FARMER, SEARCH_TERMS, STAFF_API_BASE
from shared.response_utils import safe_json
from shared.slo_shape import SLOStepRampShape
from intake_read_and_approve_helpers import pending_submission_ids, total_pages


class IntakeReadAndApproveRampShape(SLOStepRampShape):
    """Step 1 ramp-to-failure for intake_read_and_approve -- see
    shared/slo_shape.py and documentation/staff-api/test-scenarios.md §4/§5."""


class IntakeReadAndApproveUser(LocustUser):
    """Pages through every intake submission for the Farmer register and approves each one still PENDING.

    search_in_intake_form_submissions has no server-side way to filter by
    approval_status (see intake_read_and_approve_helpers.pending_submission_ids),
    so every page is fetched and PENDING submissions are picked out
    client-side. For each one: get_intake_form_submission, add_verification,
    then approve_intake_form_submission — approve_submission requires
    number_of_verifications_done >= number_of_verifications_required (1 for
    the farmer intake form), so it fails without the verification step.
    Continues, page by page, until the search is exhausted.
    """

    host = STAFF_API_BASE

    def on_start(self):
        super().on_start()
        # Sticky per user for its whole session -- see
        # staff-api/register_read/register_read_locustfile.py /
        # documentation/seeding-design.md "Search-text anchors". Finds real
        # matches once intake_create has run (it embeds an anchor into every
        # generated farmer's first_name).
        self.search_text = random.choice(SEARCH_TERMS)
        print(f"\nDEBUG SEARCH_TERM anchored -> {self.search_text}\n")

    @tag("intake", "write")
    @task
    def read_and_approve_pending_intakes(self):
        self._get_intake_form_submissions_summary()

        current_page = 1
        pages_total = 1
        while current_page <= pages_total:
            search_response = self._search_in_intake_form_submissions(current_page)
            search_response_json = safe_json(search_response)
            pages_total = total_pages(search_response_json)

            for submission_id in pending_submission_ids(search_response_json):
                self._process_submission(submission_id)

            current_page += 1

    def _process_submission(self, submission_id: str):
        self._get_intake_form_submission(submission_id)
        self._get_verifications(submission_id)
        self._add_verification(submission_id)
        self._get_intake_form_documents(submission_id)
        self._get_deduplication_intake_form_register_results(submission_id)
        self._get_deduplication_intake_form_intake_form_results(submission_id)
        self._approve_intake_form_submission(submission_id)

    # ------------------------------------------------------------------
    # get_intake_form_submissions_summary (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _get_intake_form_submissions_summary(self):
        payload = self.build_request(request_payload={})
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/get_intake_form_submissions_summary",
            payload,
            name="get_intake_form_submissions_summary",
        )

    # ------------------------------------------------------------------
    # search_in_intake_form_submissions (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _search_in_intake_form_submissions(self, current_page: int):
        payload = self.build_request(
            request_payload={"register_id": REGISTER_FARMER},
            pagination_request={
                "current_page": current_page,
                "page_size": INTAKE_SEARCH_PAGE_SIZE,
                "search_text": self.search_text,
            },
        )
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/search_in_intake_form_submissions",
            payload,
            name="search_in_intake_form_submissions",
        )

    # ------------------------------------------------------------------
    # get_intake_form_submission (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _get_intake_form_submission(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/get_intake_form_submission",
            payload,
            name="get_intake_form_submission",
        )

    # ------------------------------------------------------------------
    # get_verifications (g2p_verification_controller)
    # ------------------------------------------------------------------
    def _get_verifications(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/verifications/get_verifications",
            payload,
            name="get_verifications",
        )

    # ------------------------------------------------------------------
    # add_verification (g2p_verification_controller)
    # ------------------------------------------------------------------
    def _add_verification(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id, "is_approved": True})
        return self._post(
            STAFF_API_BASE,
            "/verifications/add_verification",
            payload,
            name="add_verification",
        )

    # ------------------------------------------------------------------
    # get_intake_form_documents (g2p_document_controller)
    # ------------------------------------------------------------------
    def _get_intake_form_documents(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/documents/get_intake_form_documents",
            payload,
            name="get_intake_form_documents",
        )

    # ------------------------------------------------------------------
    # get_deduplication_intake_form_register_results (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _get_deduplication_intake_form_register_results(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/get_deduplication_intake_form_register_results",
            payload,
            name="get_deduplication_intake_form_register_results",
        )

    # ------------------------------------------------------------------
    # get_deduplication_intake_form_intake_form_results (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _get_deduplication_intake_form_intake_form_results(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/get_deduplication_intake_form_intake_form_results",
            payload,
            name="get_deduplication_intake_form_intake_form_results",
        )

    # ------------------------------------------------------------------
    # approve_intake_form_submission (g2p_intake_form_data_controller)
    # ------------------------------------------------------------------
    def _approve_intake_form_submission(self, submission_id: str):
        payload = self.build_request(request_payload={"submission_id": submission_id})
        return self._post(
            STAFF_API_BASE,
            "/intake-form-data/approve_intake_form_submission",
            payload,
            name="approve_intake_form_submission",
        )
