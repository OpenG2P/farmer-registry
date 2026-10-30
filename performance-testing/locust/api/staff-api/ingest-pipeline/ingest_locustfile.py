from locust import tag, task

from shared.base_user import LocustUser
from shared.config import STAFF_API_BASE


class IngestUser(LocustUser):
    host = STAFF_API_BASE

    @tag("ingest", "write")
    @task
    def ingest_pipeline_placeholder(self):
        payload = self.build_request(
            request_payload={"placeholder": True},
        )
        self._post(STAFF_API_BASE, "/ingest/pipeline", payload, name="ingest_pipeline_placeholder")
