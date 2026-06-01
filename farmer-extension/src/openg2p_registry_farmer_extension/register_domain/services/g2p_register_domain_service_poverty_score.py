import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import as_float, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServicePovertyScore(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_poverty_score(record)

    def _validate_poverty_score(self, record: dict) -> None:
        score = as_float(record.get("poverty_score"))
        if score is not None and (score < 0 or score > 100):
            validation_error("poverty_score must be between 0 and 100 when provided")

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for poverty score")

        keys = [
            "poverty_score",
            "poverty_score_type",
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
        _logger.info("Constructing record name for poverty score")

        keys = ["poverty_score_type", "poverty_score"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
