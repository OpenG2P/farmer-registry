from __future__ import annotations

from locust import HttpUser, between

from shared.token_cache import TokenCache
from shared.config import STAFF_API_BASE
from shared.request_builder import build_g2p_request
from shared.response_utils import is_expected_business_error, safe_json


class LocustUser(HttpUser):
    """Shared base class for Farmer Registry Locust workloads."""

    abstract = True
    wait_time = between(0.5, 2.0)
    host = STAFF_API_BASE

    def on_start(self):
        self.tokens = TokenCache()

    def build_request(self, request_payload: dict, pagination_request: dict | None = None) -> dict:
        return build_g2p_request(
            request_payload=request_payload,
            pagination_request=pagination_request,
            sender_app_url=self.host,
        )

    def _post(self, base, path, payload, name, debug=False):
        with self.client.post(
            f"{base}{path}",
            json=payload,
            headers=self.tokens.auth_header(),
            name=name,
            catch_response=True,
        ) as response:
            return self._finalize_response(response, path, debug)

    def _post_multipart(self, base, path, files, data, name, debug=False):
        """For endpoints taking raw multipart/form-data (File/Form params),
        not the usual JSON G2PRequest envelope -- e.g. /documents/upload_documents."""
        with self.client.post(
            f"{base}{path}",
            files=files,
            data=data,
            headers=self.tokens.auth_header(),
            name=name,
            catch_response=True,
        ) as response:
            return self._finalize_response(response, path, debug)

    @staticmethod
    def _finalize_response(response, path, debug):
        if debug:
            try:
                body = response.json()
            except ValueError:
                body = response.text
            print(f"\nDEBUG {path} -> {response.status_code}: {body}\n")

        if response.status_code >= 400:
            response.failure(f"{response.status_code}")
        else:
            header = safe_json(response).get("response_header", {})
            if header.get("response_status") == "ERROR":
                if is_expected_business_error(header):
                    # Sequence-check / already-decided task: HTTP 200, domain
                    # rejection. Latency is a valid sample; do not mark fail.
                    response.success()
                else:
                    response.failure(
                        f"{header.get('response_error_code')}: {header.get('response_error_message')}"
                    )
            else:
                response.success()

        return response
