from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase


class G2PSchemaPovertyScore:

    poverty_score: Optional[str] = None
    poverty_score_type: Optional[str] = None


class G2PRegisterSchemaPovertyScore(G2PRegisterBaseSchema, G2PSchemaPovertyScore):
    """
    Schema for Poverty Score register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaPovertyScore are specific to the Poverty Score domain.
    """


class G2PRegisterHistorySchemaPovertyScore(G2PRegisterHistorySchema):
    """
    Schema for Poverty Score history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaPovertyScore(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaPovertyScore):
    """
    Schema for Poverty Score intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaPovertyScore are specific to the Poverty Score domain and are included in the intake form schema for data collection.
    """
