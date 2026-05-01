import logging

from openg2p_registry_core.schemas import ChangeRequestRequestPayload
from openg2p_registry_core.services import G2PRegisterDomainService

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceLivestock(G2PRegisterDomainService):
    async def validate_domain_attributes(
        self, change_request_request_payload: ChangeRequestRequestPayload
    ):
        _logger.info("Validating livestock domain attributes")
        return

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for livestock")

        keys = [
            "livestock_type",
            "breed",
            "head_count",
            "livestock_system",
        ]
        search_text = []
        if extra:
            search_text.extend(
                str(value).strip() for value in extra if str(value).strip()
            )
        search_text.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(search_text).strip()

    def construct_record_name(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing record name for livestock")

        keys = ["livestock_type", "breed"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
