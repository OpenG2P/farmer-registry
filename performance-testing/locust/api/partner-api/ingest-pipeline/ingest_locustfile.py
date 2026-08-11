from locust import tag, task

from shared.base_user import LocustUser
from shared.config import PARTNER_API_BASE


class PartnerIngestUser(LocustUser):
    host = PARTNER_API_BASE

    @tag("partner", "write")
    @task
    def ingest_placeholder(self):
        payload = self.build_request(
            request_payload={"placeholder": True},
        )
        self._post(PARTNER_API_BASE, "/ingest", payload, name="partner_ingest_placeholder")
