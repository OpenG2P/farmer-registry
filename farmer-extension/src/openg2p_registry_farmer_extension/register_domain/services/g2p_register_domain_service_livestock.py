import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceLivestock(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        self._validate_no_duplicate_livestock_type(records)

    def _validate_no_duplicate_livestock_type(self, records: list[dict]) -> None:
        seen: set[str] = set()
        for record in records:
            value = record.get("livestock_type")
            if value is None or str(value).strip() == "":
                continue
            normalized = str(value).strip()
            if normalized in seen:
                validation_error("Duplicate livestock_type entries are not allowed")
            seen.add(normalized)

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
