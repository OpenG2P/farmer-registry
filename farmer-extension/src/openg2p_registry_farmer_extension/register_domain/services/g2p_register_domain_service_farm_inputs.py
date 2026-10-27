import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .land_link_validation import validate_land_link

from .domain_validation_utils import duplicate_key, fallback_record_name, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceFarmInputs(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        self._validate_no_duplicate_farm_inputs(records)
        await validate_land_link(records, "Farm input")

    def _validate_no_duplicate_farm_inputs(self, records: list[dict]) -> None:
        seen: set[tuple] = set()
        fields = (
            "link_internal_record_id",
            "fertilizer_use",
            "pesticide_use",
            "insecticide_use",
            "improved_seed_use",
            "water_source",
            "access_to_machinery",
            "access_to_finance",
        )
        for record in records:
            normalized = duplicate_key(record, fields)
            if normalized is None:
                continue
            if normalized in seen:
                validation_error(
                    "Duplicate farm input entries are not allowed for the same parent, fertilizer, pesticide, insecticide, improved seed use, water source, machinery, and finance"
                )
            seen.add(normalized)

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
