import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .land_link_validation import validate_land_link

from .domain_validation_utils import fallback_record_name

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceFarmInputs(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        await validate_land_link(records, "Farm input")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for farm inputs")

        keys = [
            "water_source",
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
        _logger.info("Constructing record name for farm inputs")

        keys = ["water_source"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip() or fallback_record_name(payload, "Farm inputs")
