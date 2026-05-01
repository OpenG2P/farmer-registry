from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import LivestockSystemEnum


class G2PSchemaLivestock:

    livestock_type: Optional[str] = None
    breed: Optional[str] = None
    head_count: Optional[int] = None
    livestock_system: Optional[LivestockSystemEnum] = None


class G2PRegisterSchemaLivestock(G2PRegisterBaseSchema, G2PSchemaLivestock):
    """
    Schema for Livestock register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaLivestock are specific to the Livestock domain.
    """


class G2PRegisterHistorySchemaLivestock(G2PRegisterHistorySchema):
    """
    Schema for Livestock history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaLivestock(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaLivestock):
    """
    Schema for Livestock intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaLivestock are specific to the Livestock domain and are included in the intake form schema for data collection.
    """
