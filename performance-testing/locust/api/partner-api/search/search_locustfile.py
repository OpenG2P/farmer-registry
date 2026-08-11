from locust import tag, task

from shared.base_user import LocustUser
from shared.config import PARTNER_API_BASE


class PartnerSearchUser(LocustUser):
    host = PARTNER_API_BASE

    @tag("partner", "read")
    @task
    def search_placeholder(self):
        payload = self.build_request(
            request_payload={"query": {"text": ""}},
        )
        self._post(PARTNER_API_BASE, "/sync/search", payload, name="partner_search_placeholder")
