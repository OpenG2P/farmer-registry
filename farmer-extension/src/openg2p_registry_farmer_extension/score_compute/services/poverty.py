import logging
from typing import Any

from openg2p_registry_core.interfaces.g2p_score_compute_interface import (
    G2PScoreComputeInterface,
)

_logger = logging.getLogger(__name__)


class G2PScoreComputeServicePoverty(G2PScoreComputeInterface):
    """
    Weighted poverty score for Household records.

    Weights and optional value lookups come from
    g2p_register_score_contributing_attributes. A higher score means a more
    vulnerable household.
    """

    @staticmethod
    def _to_number(value: Any) -> float:
        if value is None:
            return 0.0
        if hasattr(value, "value"):
            value = value.value
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _lookup_key(value: Any) -> str | None:
        if value is None:
            return None
        if hasattr(value, "value"):
            value = value.value
        return str(value)

    def _weighted_value(self, raw: Any, attribute_config: dict[str, Any]) -> float:
        if attribute_config.get("attribute_computation_required"):
            lookup = attribute_config.get("attribute_computation_value") or {}
            key = self._lookup_key(raw)
            if not isinstance(lookup, dict) or key is None or key not in lookup:
                return 0.0
            raw = lookup[key]
        return self._to_number(raw)

    async def compute_score(
        self,
        link_internal_record_id: str,
        contributing_attribute_config: list[dict[str, Any]],
        contributing_attribute_values: dict[str, Any],
    ) -> float:
        """
        Sum each present contributing attribute times its configured weight.

        When attribute_computation_required is set, the stored value is mapped
        through attribute_computation_value before weighting.
        """
        values = contributing_attribute_values or {}
        _logger.info(
            "Computing poverty score for record %s with %s attributes",
            link_internal_record_id,
            len(values),
        )

        score = 0.0
        for attribute_config in contributing_attribute_config or []:
            attribute_name = attribute_config.get("attribute_name")
            if not attribute_name or attribute_name not in values:
                continue
            try:
                weight = float(attribute_config.get("attribute_weightage") or 0.0)
            except (TypeError, ValueError):
                continue
            score += self._weighted_value(values.get(attribute_name), attribute_config) * weight

        computed = round(score, 4)
        _logger.info(
            "Computed poverty score: %s for record %s",
            computed,
            link_internal_record_id,
        )
        return computed
