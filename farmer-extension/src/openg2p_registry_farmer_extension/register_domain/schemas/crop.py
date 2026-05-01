from datetime import date
from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import CropEndUseEnum


class G2PSchemaCrop:

    commodity: Optional[str] = None
    planted_date: Optional[date] = None
    season: Optional[str] = None
    end_use: Optional[CropEndUseEnum] = None


class G2PRegisterSchemaCrop(G2PRegisterBaseSchema, G2PSchemaCrop):
    """
    Schema for Crop register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaCrop are specific to the Crop domain.
    """


class G2PRegisterHistorySchemaCrop(G2PRegisterHistorySchema):
    """
    Schema for Crop history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaCrop(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaCrop):
    """
    Schema for Crop intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaCrop are specific to the Crop domain and are included in the intake form schema for data collection.
    """
