import logging
from typing import Any

from openg2p_registry_core.interfaces.g2p_score_compute_interface import (
    G2PScoreComputeInterface,
)

_logger = logging.getLogger(__name__)


class G2PScoreComputeServicePoverty(G2PScoreComputeInterface):
    """
    Poverty score computation for Household records.

    Higher scores indicate higher household vulnerability.
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

    async def compute_score(
        self,
        link_internal_record_id: str,
        contributing_attribute_config: list[dict[str, Any]],
        contributing_attribute_values: dict,
    ) -> float:
        """
        Compute poverty score from the contributing-attribute rows the worker loads.

        Args:
            link_internal_record_id: UUID of the subject register record
            contributing_attribute_config: Rows with attribute_name and attribute_weightage
            contributing_attribute_values: Attribute values for this queue item

        Returns:
            float: Computed poverty score (higher indicates more vulnerable)
        """
        _logger.info(
            f"Computing poverty score for record {link_internal_record_id} "
            f"with {len(contributing_attribute_values)} attributes"
        )

        score = 0.0
        for item in contributing_attribute_config or []:
            name = item.get("attribute_name")
            if not name or name not in contributing_attribute_values:
                continue
            try:
                weight = float(item.get("attribute_weightage") or 0.0)
            except (TypeError, ValueError):
                weight = 0.0
            raw_value = contributing_attribute_values.get(name)
            lookup = item.get("attribute_computation_value") or {}
            if isinstance(lookup, dict) and raw_value in lookup:
                raw_value = lookup[raw_value]
            score += self._to_number(raw_value) * weight

        _logger.info(
            f"Computed poverty score: {round(score, 4)} for record {link_internal_record_id}"
        )

        return round(score, 4)
