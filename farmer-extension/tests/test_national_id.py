import unittest

from openg2p_registry_farmer_extension.register_domain.services.g2p_register_domain_service_farmer import (
    G2PRegisterDomainServiceFarmer,
)


_NATIONAL_ID = "123456789012"
_RID = "1" * 29


class NationalIdTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = G2PRegisterDomainServiceFarmer()

    async def test_national_id_clears_rid(self):
        record = {
            "has_national_id": True,
            "foundational_id": _NATIONAL_ID,
            "rid": _RID,
            "rid_status": "PENDING",
        }
        await self.service.validate_domain_attributes([record])
        self.assertEqual(record["foundational_id"], _NATIONAL_ID)
        self.assertIsNone(record["rid"])
        self.assertIsNone(record["rid_status"])

    async def test_rid_clears_national_id_and_marks_pending(self):
        record = {
            "has_national_id": False,
            "foundational_id": _NATIONAL_ID,
            "rid": _RID,
        }
        await self.service.validate_domain_attributes([record])
        self.assertIsNone(record["foundational_id"])
        self.assertEqual(record["rid"], _RID)
        self.assertEqual(record["rid_status"], "PENDING")

    async def test_other_sections_do_not_require_an_identifier(self):
        record = {"first_name": "Abebe", "foundational_id": "NID-1"}
        await self.service.validate_domain_attributes([record])
        self.assertEqual(record["foundational_id"], "NID-1")

    async def test_delete_skips_identifier_rules(self):
        record = {"edit_action": "DELETE", "has_national_id": True}
        await self.service.validate_domain_attributes([record])

    def test_search_text_includes_national_id_and_rid(self):
        text = self.service.construct_search_text(
            {"foundational_id": _NATIONAL_ID, "rid": _RID, "first_name": "Abebe"}
        )
        self.assertIn(_NATIONAL_ID, text)
        self.assertIn(_RID, text)
