import unittest

from openg2p_registry_farmer_extension.register_domain.services.disability_status_sync import (
    disabled_from_rows,
    parent_ids_for_disability_change,
    rows_for_farmer,
)


class DisabilityStatusFromTableTests(unittest.TestCase):
    def test_no_rows_is_not_disabled(self):
        self.assertFalse(disabled_from_rows([]))
        self.assertFalse(disabled_from_rows(None))

    def test_one_or_more_rows_is_disabled(self):
        self.assertTrue(disabled_from_rows([{"disability_domains": "VISION"}]))
        self.assertTrue(
            disabled_from_rows(
                [
                    {"disability_domains": "VISION"},
                    {"disability_domains": "MOBILITY"},
                ]
            )
        )

    def test_single_farmer_counts_unlinked_rows(self):
        rows = [{"disability_domains": "VISION", "link_internal_record_id": None}]
        matched = rows_for_farmer("farmer-1", 1, rows)
        self.assertTrue(disabled_from_rows(matched))

    def test_single_farmer_without_rows_is_not_disabled(self):
        self.assertFalse(disabled_from_rows(rows_for_farmer("farmer-1", 1, [])))

    def test_multiple_farmers_count_only_linked_rows(self):
        rows = [
            {"link_internal_record_id": ""},
            {"link_internal_record_id": "farmer-2", "disability_domains": "HEARING"},
        ]
        self.assertFalse(disabled_from_rows(rows_for_farmer("farmer-1", 2, rows)))
        self.assertTrue(disabled_from_rows(rows_for_farmer("farmer-2", 2, rows)))

    def test_parent_ids_include_subject_and_row_links(self):
        parent_ids = parent_ids_for_disability_change(
            "farmer-1",
            [
                {"edit_action": "DELETE", "internal_record_id": "row-1"},
                {"edit_action": "ADD", "link_internal_record_id": "farmer-2"},
            ],
        )
        self.assertEqual(parent_ids, ["farmer-1", "farmer-2"])

    def test_parent_ids_skip_blank_and_duplicate_links(self):
        parent_ids = parent_ids_for_disability_change(
            "farmer-1",
            [
                {"link_internal_record_id": "  "},
                {"link_internal_record_id": "farmer-1"},
                {"link_internal_record_id": None},
            ],
        )
        self.assertEqual(parent_ids, ["farmer-1"])
