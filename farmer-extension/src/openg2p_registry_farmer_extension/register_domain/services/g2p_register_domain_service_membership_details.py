import logging

from openg2p_registry_core.services import G2PRegisterDomainService

from .domain_validation_utils import as_bool, is_blank, validation_error

_logger = logging.getLogger("g2p-register-domain-service")


class G2PRegisterDomainServiceMembershipDetails(G2PRegisterDomainService):
    async def validate_domain_attributes(self, records: list[dict]):
        for record in records:
            self._validate_cooperative_membership(record)
            self._validate_union_membership(record)
            self._validate_cluster_membership(record)

    def _validate_cooperative_membership(self, record: dict) -> None:
        is_member = as_bool(record.get("is_primary_cooperative_member"))
        if is_member is False and not is_blank(record.get("primary_cooperative_name")):
            validation_error(
                "primary_cooperative_name must be empty when is_primary_cooperative_member is false"
            )

    def _validate_union_membership(self, record: dict) -> None:
        is_member = as_bool(record.get("is_cooperative_union_member"))
        if is_member is False and not is_blank(record.get("cooperative_union_name")):
            validation_error(
                "cooperative_union_name must be empty when is_cooperative_union_member is false"
            )

    def _validate_cluster_membership(self, record: dict) -> None:
        is_member = as_bool(record.get("is_farmer_cluster_member"))
        if is_member is False and not is_blank(record.get("farmer_cluster_role")):
            validation_error(
                "farmer_cluster_role must be empty when is_farmer_cluster_member is false"
            )

    def construct_search_text(self, payload: dict, extra: list[str] = None) -> str:
        _logger.info("Constructing search text for membership details")

        keys = [
            "primary_cooperative_name",
            "cooperative_union_name",
            "farmer_cluster_role",
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
        _logger.info("Constructing record name for membership details")

        keys = ["primary_cooperative_name", "cooperative_union_name"]
        record_name = []
        if extra:
            record_name.extend(str(item).strip() for item in extra if str(item).strip())
        record_name.extend(
            str(payload.get(key) or "").strip()
            for key in keys
            if str(payload.get(key) or "").strip()
        )

        return " ".join(record_name).strip()
