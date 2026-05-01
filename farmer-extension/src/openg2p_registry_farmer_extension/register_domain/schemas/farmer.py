from typing import Optional

from openg2p_registry_core.schemas import (
    G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema,
    G2PRegisterHistorySchema, G2PPersonHistorySchema, G2PGeoHistorySchema,
    G2PIntakeFormSchemaBase
)
from ..models.enums import (
    DisabilityTypeEnum,
    DisabilitySeverityEnum,
    EducationalLevelEnum,
    SourceOfIncomeEnum,
)

class G2PSchemaFarmer:
    
    estimated_age: Optional[int] = None
    has_personal_phone: Optional[bool] = None
    disabled: Optional[bool] = None
    disability_type: Optional[DisabilityTypeEnum] = None
    disability_severity: Optional[DisabilitySeverityEnum] = None
    source_of_income: Optional[SourceOfIncomeEnum] = None
    source_of_income_other: Optional[str] = None
    language_spoken: Optional[str] = None
    education_level: Optional[EducationalLevelEnum] = None
    national_id_masked: Optional[str] = None

class G2PRegisterSchemaFarmer(G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaFarmer):
    """
    Schema for Farmer register.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain.
    """


class G2PRegisterHistorySchemaFarmer(G2PRegisterHistorySchema, G2PPersonHistorySchema, G2PGeoHistorySchema):
    """
    Schema for Farmer history.
    Inherits fields from G2PRegisterHistorySchema, G2PPersonHistorySchema, and G2PGeoHistorySchema.
    Attributes specific to the Farmer domain are not included in the history schema as they are not expected to change over time.
    """

class G2PIntakeFormSchemaFarmer(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PPersonSchema, G2PGeoSchema, G2PSchemaFarmer):
    """
    Schema for Farmer intake form.
    Inherits fields from G2PRegisterBaseSchema, G2PPersonSchema, and G2PGeoSchema.
    Attributes inherited from G2PSchemaFarmer are specific to the Farmer domain and are included in the intake form schema for data collection.
    """
