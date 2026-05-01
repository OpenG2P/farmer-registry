from typing import Optional

from openg2p_registry_core.schemas import G2PRegisterBaseSchema, G2PRegisterHistorySchema, G2PIntakeFormSchemaBase
from ..models.enums import FarmerClusterRoleEnum


class G2PSchemaMembershipDetails:

    is_primary_cooperative_member: Optional[bool] = None
    primary_cooperative_name: Optional[str] = None
    is_cooperative_union_member: Optional[bool] = None
    cooperative_union_name: Optional[str] = None
    is_farmer_cluster_member: Optional[bool] = None
    farmer_cluster_role: Optional[FarmerClusterRoleEnum] = None


class G2PRegisterSchemaMembershipDetails(G2PRegisterBaseSchema, G2PSchemaMembershipDetails):
    """
    Schema for Membership Details register.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaMembershipDetails are specific to the Membership Details domain.
    """


class G2PRegisterHistorySchemaMembershipDetails(G2PRegisterHistorySchema):
    """
    Schema for Membership Details history.
    Inherits fields from G2PRegisterHistorySchema.
    """


class G2PIntakeFormSchemaMembershipDetails(G2PIntakeFormSchemaBase, G2PRegisterBaseSchema, G2PSchemaMembershipDetails):
    """
    Schema for Membership Details intake form.
    Inherits fields from G2PRegisterBaseSchema.
    Attributes inherited from G2PSchemaMembershipDetails are specific to the Membership Details domain and are included in the intake form schema for data collection.
    """
