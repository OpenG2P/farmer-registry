import logging
from typing import Any

from openg2p_registry_core.interfaces.g2p_score_compute_interface import (
    G2PScoreComputeInterface,
)

_logger = logging.getLogger(__name__)


class G2PScoreComputeServicePmtScore(G2PScoreComputeInterface):
    """
    PMT (Poverty Means Test) Score computation implementation.
    
    This is a sample implementation that computes a poverty score based on
    various socioeconomic indicators. The actual formula can be customized
    based on specific program requirements.
    """

    async def compute_score(
        self,
        internal_record_id: str,
        contributing_attribute_values: dict,
        score_config: dict,
    ) -> float:
        """
        Compute PMT score based on household characteristics.
        
        Args:
            internal_record_id: UUID of the register record
            contributing_attribute_values: Dictionary containing attribute values
                that feed into this score computation
            score_config: Configuration dictionary containing weights and parameters
                
        Returns:
            float: Computed PMT score (typically 0-100, lower indicates more vulnerable)
        """
        _logger.info(
            f"Computing PMT score for record {internal_record_id} "
            f"with {len(contributing_attribute_values)} attributes"
        )

        # Extract configuration parameters with defaults
        weights = score_config.get("weights", {})
        score = 0.0

        # Use actual farmer table fields for PMT computation
        income_level  = contributing_attribute_values.get("income_level") or 0
        education_level = contributing_attribute_values.get("education_level") or "ILLITERATE"
        estimated_age = contributing_attribute_values.get("estimated_age") or 0
        marital_status = contributing_attribute_values.get("marital_status") or "SINGLE"
        occupation    = contributing_attribute_values.get("occupation") or 0

        # Apply weights based on socioeconomic factors
        score += float(income_level or 0)  * weights.get("income_level", 0.3)
        score += float(estimated_age or 0)  * weights.get("estimated_age", 0.1)
        score += float(occupation or 0)    * weights.get("occupation", 0.05)
        
        # Handle categorical selection fields
        # Education level using EducationalLevelEnum values
        education_score = 0
        if education_level == "ILLITERATE":
            education_score = 0.0
        elif education_level == "CAN_READ_AND_WRITE":
            education_score = 0.5
        elif education_level == "BASIC":
            education_score = 1.0
        elif education_level == "INTERMEDIARY":
            education_score = 1.5
        elif education_level == "HIGHER_EDUCATION":
            education_score = 2.0
        score += education_score * weights.get("education_level", 0.2)
        
        # Marital status: Different weights for different marital statuses
        # Note: marital_status comes from G2PPerson base class, using typical values
        marital_score = 0
        if marital_status == "SINGLE":
            marital_score = 0.1
        elif marital_status == "MARRIED":
            marital_score = 0.05
        elif marital_status == "DIVORCED":
            marital_score = 0.15
        elif marital_status == "WIDOWED":
            marital_score = 0.2
        score += marital_score * weights.get("marital_status", 0.05)

        _logger.info(f"Computed PMT score: {round(score, 4)} for record {internal_record_id}")
        
        return round(score, 4)
