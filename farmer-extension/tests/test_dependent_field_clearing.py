import unittest

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer_disability import (
    G2PRegisterDomainServiceFarmerDisability,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_household_member import (
    G2PRegisterDomainServiceHouseholdMember,
)
from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_membership_details import (
    G2PRegisterDomainServiceMembershipDetails,
)


class DependentFieldClearingTests(unittest.IsolatedAsyncioTestCase):
    async def test_duplicate_disability_domain_rejected(self):
        service = G2PRegisterDomainServiceFarmerDisability()
        records = [
            {"disability_domains": "MOBILITY", "disability_severity": "SOME_DIFFICULTY"},
            {"disability_domains": "MOBILITY", "disability_severity": "A_LOT_OF_DIFFICULTY"},
        ]
        with self.assertRaises(G2PRegistryException):
            await service.validate_domain_attributes(records)

    async def test_different_disability_domains_allowed(self):
        service = G2PRegisterDomainServiceFarmerDisability()
        records = [
            {"disability_domains": "MOBILITY", "disability_severity": "SOME_DIFFICULTY"},
            {"disability_domains": "VISION", "disability_severity": "NO_DIFFICULTY"},
            {"edit_action": "DELETE", "disability_domains": "VISION", "disability_severity": "SOME_DIFFICULTY"},
        ]
        await service.validate_domain_attributes(records)

    async def test_invalid_disability_domain_rejected(self):
        service = G2PRegisterDomainServiceFarmerDisability()
        with self.assertRaises(G2PRegistryException):
            await service.validate_domain_attributes(
                [{"disability_domains": "NOT_A_DOMAIN", "disability_severity": "SOME_DIFFICULTY"}]
            )

    async def test_cooperative_names_removed_independently(self):
        service = G2PRegisterDomainServiceMembershipDetails()
        record = {
            "is_primary_cooperative_member": False,
            "primary_cooperative_name": "Village Coop",
            "is_cooperative_union_member": "yes",
            "cooperative_union_name": "District Union",
        }
        await service.validate_domain_attributes([record])
        self.assertIsNone(record["primary_cooperative_name"])
        self.assertEqual(record["cooperative_union_name"], "District Union")

        record["is_cooperative_union_member"] = "no"
        await service.validate_domain_attributes([record])
        self.assertIsNone(record["cooperative_union_name"])

    async def test_head_relationship_removed_when_is_head_selected_after(self):
        service = G2PRegisterDomainServiceHouseholdMember()
        record = {"is_head": True, "relationship_to_the_head": "CHILD", "first_name": "Abebe"}
        await service.validate_domain_attributes([record])
        self.assertIsNone(record["relationship_to_the_head"])

    async def test_non_head_keeps_relationship(self):
        service = G2PRegisterDomainServiceHouseholdMember()
        record = {"is_head": False, "relationship_to_the_head": "SPOUSE", "first_name": "Abebe"}
        await service.validate_domain_attributes([record])
        self.assertEqual(record["relationship_to_the_head"], "SPOUSE")

    async def test_non_head_still_requires_relationship(self):
        service = G2PRegisterDomainServiceHouseholdMember()
        record = {"is_head": False, "relationship_to_the_head": None, "first_name": "Abebe"}
        with self.assertRaises(G2PRegistryException):
            await service.validate_domain_attributes([record])

    async def test_unrelated_member_edit_does_not_clear_relationship(self):
        service = G2PRegisterDomainServiceHouseholdMember()
        record = {"first_name": "Abebe", "relationship_to_the_head": "CHILD"}
        await service.validate_domain_attributes([record])
        self.assertEqual(record["relationship_to_the_head"], "CHILD")


if __name__ == "__main__":
    unittest.main()
