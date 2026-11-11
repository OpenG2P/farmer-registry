from typing import Optional

from openg2p_registry_core.schemas import (
    G2PIntakeFormSchemaBase,
    G2PRegisterBaseSchema,
    G2PRegisterHistorySchema,
)
from ..models.enums import DisabilitySeverityEnum, DisabilityTypeEnum


class G2PSchemaFarmerDisability:

    disability_domains: Optional[DisabilityTypeEnum] = None
    disability_severity: Optional[DisabilitySeverityEnum] = None


class G2PRegisterSchemaFarmerDisability(G2PRegisterBaseSchema, G2PSchemaFarmerDisability):
    """Schema for a farmer disability row. A farmer can have one row per domain."""


class G2PRegisterHistorySchemaFarmerDisability(G2PRegisterHistorySchema):
    disability_domains: Optional[DisabilityTypeEnum] = None
    disability_severity: Optional[DisabilitySeverityEnum] = None


class G2PIntakeFormSchemaFarmerDisability(
    G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaFarmerDisability
):
    """Intake schema for a farmer disability row."""
