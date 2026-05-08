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
        internal_record_id: str,
        contributing_attribute_values: dict,
        score_config: dict,
    ) -> float:
        """
        Compute poverty score based on configured household attributes.
        
        Args:
            internal_record_id: UUID of the register record
            contributing_attribute_values: Dictionary containing attribute values
                that feed into this score computation
            score_config: Configuration dictionary containing weights and parameters
                
        Returns:
            float: Computed poverty score (higher indicates more vulnerable)
        """
        _logger.info(
            f"Computing poverty score for record {internal_record_id} "
            f"with {len(contributing_attribute_values)} attributes"
        )

        # The worker passes values for the score definition's configured
        # contributing_attributes, and score_config contains matching weights.
        weights = score_config.get(
            "weights",
            {
                "size_of_group": 0.4,
                "number_of_children": 0.6,
            },
        )
        score = 0.0

        if "size_of_group" in contributing_attribute_values:
            score += (
                self._to_number(contributing_attribute_values.get("size_of_group"))
                * weights.get("size_of_group", 0.0)
            )

        if "number_of_children" in contributing_attribute_values:
            score += (
                self._to_number(contributing_attribute_values.get("number_of_children"))
                * weights.get("number_of_children", 0.0)
            )

        _logger.info(
            f"Computed poverty score: {round(score, 4)} for record {internal_record_id}"
        )

        return round(score, 4)
