from __future__ import annotations

import random
import time

from locust import tag, task

from shared.base_user import LocustUser
from shared.config import (
    CR_SEARCH_PAGE_SIZE,
    REGISTER_FARMER,
    SEARCH_PAGE_SIZE,
    SEARCH_TERMS,
    STAFF_API_BASE,
    TAB_ITERATION_MAX_WAIT_SECONDS,
    TAB_ITERATION_MIN_WAIT_SECONDS,
)
from shared.response_utils import safe_json
from shared.slo_shape import SLOStepRampShape
from register_read_helpers import (
    RegisterBrowseState,
    change_request_items,
    choose_internal_record_id,
    extract_awe_request_id,
    extract_ordered_tab_ids,
    extract_version_dates,
    total_pages,
)


class RegisterReadRampShape(SLOStepRampShape):
    """Step 1 ramp-to-failure for register_read -- see shared/slo_shape.py
    and documentation/staff-api/test-scenarios.md §4/§5. Locust auto-detects
    this and takes over concurrency once you click "Start swarming"; -u/-r
    are ignored (see SLOStepRampShape's docstring)."""


class RegisterUser(LocustUser):
    """Staff-portal register browsing: search once, then view one record's detail."""

    host = STAFF_API_BASE

    # Shared across all RegisterUser greenlets in this process: how many
    # currently-live users are sticky on each term, so on_start can join
    # whichever term is least contended right now instead of picking blind.
    # This is read-only, so many concurrent users piling on one hot term
    # doesn't cause a race the way it does in the *_read_and_approve flows
    # (nothing here writes or claims a resource another user could collide
    # on) -- it's purely to keep search load spread out the way real staff
    # traffic would be, rather than an artifact of everyone randomly
    # clustering on the same few terms. True exclusivity isn't achievable
    # here anyway once concurrent users outnumber len(SEARCH_TERMS), which a
    # ramp-to-failure run is designed to do.
    _term_usage_counts: dict[str, int] = {}

    def on_start(self):
        super().on_start()
        self.total_pages = None
        # Sticky per user for its whole session: spreads search load across
        # the full search_text index space across users, while each user's
        # own searches stay on one term (mirrors a staff user repeatedly
        # searching similar things in one sitting). See
        # performance-testing/seeding/README.md "Search-text anchors".
        self.search_text = self._claim_least_used_term()
        print(f"\nDEBUG SEARCH_TERM anchored -> {self.search_text}\n")

    def on_stop(self):
        if self.search_text:
            self._term_usage_counts[self.search_text] = max(
                0, self._term_usage_counts.get(self.search_text, 0) - 1
            )

    def _claim_least_used_term(self) -> str:
        if not SEARCH_TERMS:
            return ""
        min_count = min(self._term_usage_counts.get(term, 0) for term in SEARCH_TERMS)
        least_used = [term for term in SEARCH_TERMS if self._term_usage_counts.get(term, 0) == min_count]
        term = random.choice(least_used)
        self._term_usage_counts[term] = self._term_usage_counts.get(term, 0) + 1
        return term

    @tag("search", "register", "read")
    @task
    def browse_registers_and_view_detailed_record(self):
        self._get_register_summary_data()

        search_response = self._search_in_a_register()
        register_state = self.construct_register_state(search_response)
        
        if not register_state.has_record():
            return

        self._get_subject_record(register_state)

        tabs_response = self._get_all_tabs(register_state)
        print(f"\nDEBUG tabs_response -> {safe_json(tabs_response)}\n")
        tab_ids = extract_ordered_tab_ids(safe_json(tabs_response))

        print(f"\nDEBUG tab_ids -> {tab_ids}\n")
        for index, tab_id in enumerate(tab_ids):
            if index > 0:
                time.sleep(random.uniform(TAB_ITERATION_MIN_WAIT_SECONDS, TAB_ITERATION_MAX_WAIT_SECONDS))
            print(f"\nDEBUG browsing tab_id -> {tab_id}\n")
            register_state.tab_id = tab_id
            self._browse_tab(register_state)

    def _browse_tab(self, register_state: RegisterBrowseState):
        self._get_tab_sections(register_state)
        self._get_tab_records(register_state)
        self._get_number_of_pending_change_requests(register_state)

        for change_request in self._iterate_change_requests(register_state):
            self._process_change_request(register_state, change_request)

        self._get_number_of_versions(register_state)

        version_dates_response = self._get_version_dates(register_state)
        version_dates = extract_version_dates(safe_json(version_dates_response))
        print(f"\nDEBUG version_dates -> {version_dates}\n")
        for version_date in version_dates:
            self._get_versions_for_a_date(register_state, version_date)

    def _iterate_change_requests(self, register_state: RegisterBrowseState):
        current_page = 1
        pages_total = 1
        while current_page <= pages_total:
            response_json = safe_json(self._get_change_requests(register_state, current_page))
            pages_total = total_pages(response_json)
            yield from change_request_items(response_json)
            current_page += 1

    def _process_change_request(self, register_state: RegisterBrowseState, change_request: dict):
        change_request_id = change_request.get("change_request_id")
        if not change_request_id:
            return
        section_id = change_request.get("section_id")

        self._get_change_request_documents(change_request_id)
        if section_id:
            self._get_section_ui_schema(register_state, section_id)
        change_request_response = self._get_change_request(change_request_id)
        # self._check_change_request_sequence(change_request_id)

        awe_request_id = extract_awe_request_id(safe_json(change_request_response))
        if awe_request_id:
            self._list_tasks_for_request(awe_request_id)

        self._get_deduplication_change_request_results(change_request_id)
        self._get_deduplication_register_results(change_request_id)

    # ------------------------------------------------------------------
    # 1 — get_register_summary_data
    # ------------------------------------------------------------------
    def _get_register_summary_data(self):
        payload = self.build_request(request_payload={"register_id": REGISTER_FARMER})
        return self._post(
            STAFF_API_BASE,
            "/register-data/get_register_summary_data",
            payload,
            name="get_register_summary_data",
            debug=True,
        )

    # ------------------------------------------------------------------
    # 2 — search_in_a_register
    # ------------------------------------------------------------------
    def _search_in_a_register(self):
        current_page = random.randint(1, self.total_pages) if self.total_pages else 1
        print(f"\nDEBUG PAGE_NUMBER -> {current_page}\n")
        payload = self.build_request(
            request_payload={"register_id": REGISTER_FARMER},
            pagination_request={
                "current_page": current_page,
                "page_size": SEARCH_PAGE_SIZE,
                "search_text": self.search_text,
            },
        )
        response = self._post(
            STAFF_API_BASE,
            "/register-data/search_in_a_register",
            payload,
            name="search_in_a_register",
            debug=True,
        )
        pagination_response = safe_json(response).get("response_body", {}).get("pagination_response") or {}
        total_pages = pagination_response.get("number_of_pages")
        if total_pages:
            self.total_pages = total_pages
        return response

    def construct_register_state(self, search_response) -> RegisterBrowseState:
        internal_record_id = choose_internal_record_id(safe_json(search_response))
        return RegisterBrowseState(register_id=REGISTER_FARMER, internal_record_id=internal_record_id)

    # ------------------------------------------------------------------
    # 3 — get_subject_record
    # ------------------------------------------------------------------
    def _get_subject_record(self, register_state: RegisterBrowseState):
        payload = self.build_request(
            request_payload={
                "subject_register_id": register_state.register_id,
                "subject_record_id": register_state.internal_record_id,
            },
        )
        return self._post(STAFF_API_BASE, "/register-data/get_subject_record", payload, name="get_subject_record")

    # ------------------------------------------------------------------
    # 4 — get_all_tabs (g2p_register_tab_metadata_controller)
    # ------------------------------------------------------------------
    def _get_all_tabs(self, register_state: RegisterBrowseState):
        payload = self.build_request(request_payload={"register_id": register_state.register_id})
        return self._post(
            STAFF_API_BASE, "/register-tab-metadata/get_all_tabs", payload, name="get_all_tabs", debug=True
        )

    # ------------------------------------------------------------------
    # 4a — get_sections, tab-scoped (g2p_register_tab_metadata_controller)
    # ------------------------------------------------------------------
    def _get_tab_sections(self, register_state: RegisterBrowseState):
        payload = self.build_request(request_payload={"tab_id": register_state.tab_id})
        return self._post(
            STAFF_API_BASE, "/register-tab-metadata/get_sections", payload, name="get_tab_sections", debug=True
        )

    # ------------------------------------------------------------------
    # 4b — get_tab_records
    # ------------------------------------------------------------------
    def _get_tab_records(self, register_state: RegisterBrowseState):
        payload = self.build_request(
            request_payload={
                "subject_register_id": register_state.register_id,
                "subject_record_id": register_state.internal_record_id,
                "tab_id": register_state.tab_id,
            },
        )
        return self._post(STAFF_API_BASE, "/register-data/get_tab_records", payload, name="get_tab_records")

    # ------------------------------------------------------------------
    # 4c — get_number_of_pending_change_requests (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _get_number_of_pending_change_requests(self, register_state: RegisterBrowseState):
        payload = self.build_request(request_payload=self._subject_tab_scope(register_state))
        return self._post(
            STAFF_API_BASE,
            "/change-requests/get_number_of_pending_change_requests",
            payload,
            name="get_number_of_pending_change_requests",
        )

    # ------------------------------------------------------------------
    # 4d — get_change_requests (g2p_register_change_request_controller), paginated
    # ------------------------------------------------------------------
    def _get_change_requests(self, register_state: RegisterBrowseState, current_page: int):
        payload = self.build_request(
            request_payload=self._subject_tab_scope(register_state),
            pagination_request={"current_page": current_page, "page_size": CR_SEARCH_PAGE_SIZE},
        )
        return self._post(
            STAFF_API_BASE, "/change-requests/get_change_requests", payload, name="get_change_requests"
        )

    # ------------------------------------------------------------------
    # 4da — get_change_request_documents (g2p_document_controller)
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
    # 4db — get_section_ui_schema (g2p_register_section_metadata_controller)
    # ------------------------------------------------------------------
    def _get_section_ui_schema(self, register_state: RegisterBrowseState, section_id: str):
        payload = self.build_request(
            request_payload={"section_id": section_id, "register_id": register_state.register_id},
        )
        return self._post(
            STAFF_API_BASE, "/register-section-metadata/get_section_ui_schema", payload, name="get_section_ui_schema"
        )

    # ------------------------------------------------------------------
    # 4dc — get_change_request (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    def _get_change_request(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(STAFF_API_BASE, "/change-requests/get_change_request", payload, name="get_change_request")

    # ------------------------------------------------------------------
    # 4dd — check_change_request_sequence (g2p_register_change_request_controller)
    # ------------------------------------------------------------------
    # def _check_change_request_sequence(self, change_request_id: str):
    #     payload = self.build_request(request_payload={"change_request_id": change_request_id})
    #     return self._post(
    #         STAFF_API_BASE,
    #         "/change-requests/check_change_request_sequence",
    #         payload,
    #         name="check_change_request_sequence",
    #     )

    # ------------------------------------------------------------------
    # 4de — list_tasks_for_request (g2p_awe_proxy_controller)
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
    # 4df — get_deduplication_change_request_results (g2p_register_data_controller)
    # ------------------------------------------------------------------
    def _get_deduplication_change_request_results(self, change_request_id: str):
        payload = self.build_request(request_payload={"change_request_id": change_request_id})
        return self._post(
            STAFF_API_BASE,
            "/register-data/get_deduplication_change_request_results",
            payload,
            name="get_deduplication_change_request_results",
        )

    # ------------------------------------------------------------------
    # 4dg — get_deduplication_register_results (g2p_register_data_controller)
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
    # 4f — get_number_of_versions
    # ------------------------------------------------------------------
    def _get_number_of_versions(self, register_state: RegisterBrowseState):
        payload = self.build_request(request_payload=self._record_tab_scope(register_state))
        return self._post(
            STAFF_API_BASE, "/register-data/get_number_of_versions", payload, name="get_number_of_versions"
        )

    # ------------------------------------------------------------------
    # 4g — get_version_dates
    # ------------------------------------------------------------------
    def _get_version_dates(self, register_state: RegisterBrowseState):
        payload = self.build_request(request_payload=self._record_tab_scope(register_state))
        return self._post(
            STAFF_API_BASE, "/register-data/get_version_dates", payload, name="get_version_dates", debug=True
        )

    # ------------------------------------------------------------------
    # 4ga — get_versions_for_a_date
    # ------------------------------------------------------------------
    def _get_versions_for_a_date(self, register_state: RegisterBrowseState, version_date: str):
        payload = self.build_request(
            request_payload={**self._record_tab_scope(register_state), "truncated_created_date": version_date},
        )
        return self._post(
            STAFF_API_BASE, "/register-data/get_versions_for_a_date", payload, name="get_versions_for_a_date"
        )

    @staticmethod
    def _record_tab_scope(register_state: RegisterBrowseState) -> dict:
        return {
            "register_id": register_state.register_id,
            "internal_record_id": register_state.internal_record_id,
            "tab_id": register_state.tab_id,
        }

    @staticmethod
    def _subject_tab_scope(register_state: RegisterBrowseState) -> dict:
        # Same (register, record, tab) scope as _record_tab_scope, but the
        # change-requests controller's payload schemas use subject_register_id
        # / subject_record_id rather than register_id / internal_record_id
        # (see registry-platform's schemas/change_request.py).
        return {
            "subject_register_id": register_state.register_id,
            "subject_record_id": register_state.internal_record_id,
            "tab_id": register_state.tab_id,
        }
