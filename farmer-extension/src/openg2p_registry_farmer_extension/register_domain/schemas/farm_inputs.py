from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase


class G2PSchemaFarmInputs:

    fertilizer_use: Optional[bool] = None
    pesticide_use: Optional[bool] = None
    insecticide_use: Optional[bool] = None
    improved_seed_use: Optional[bool] = None
    water_source: Optional[str] = None
    access_to_machinery: Optional[bool] = None
    access_to_finance: Optional[bool] = None


class G2PRegisterSchemaFarmInputs(G2PRegisterBaseSchema, G2PSchemaFarmInputs):
    """
    Schema for Farm Inputs register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaFarmInputs are specific to the Farm Inputs domain.
    """


class G2PRegisterHistorySchemaFarmInputs(G2PRegisterHistorySchema):
    """
    Schema for Farm Inputs history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaFarmInputs(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaFarmInputs):
    """
    Schema for Farm Inputs intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaFarmInputs are specific to the Farm Inputs domain and are included in the intake form schema for data collection.
    """
