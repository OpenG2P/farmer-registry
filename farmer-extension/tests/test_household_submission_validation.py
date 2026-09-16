import unittest
from types import SimpleNamespace

from openg2p_registry_core.errors import G2PRegistryException
from openg2p_registry_farmer_extension.register_domain.services.household_submission_validation import (
    validate_household_roster,
)


def _hh(size=3, male=2, female=1):
    return SimpleNamespace(size_of_group=size, number_of_male_members=male, number_of_female_members=female)


def _m(gender, head=False, rel=None):
    return {"gender": gender, "is_head": head, "relationship_to_the_head": rel}


VALID = [_m("MALE", True), _m("MALE", False, "CHILD"), _m("FEMALE", False, "SPOUSE")]


class HouseholdSubmissionValidationTests(unittest.TestCase):
    def assertRejected(self, household, members, needle):
        with self.assertRaises(G2PRegistryException) as ctx:
            validate_household_roster(household, members)
        self.assertIn(needle, str(ctx.exception.message if hasattr(ctx.exception, "message") else ctx.exception))

    def test_valid_roster_passes(self):
        validate_household_roster(_hh(), VALID)

    def test_missing_household_rejected(self):
        self.assertRejected(None, VALID, "Household information must be entered")

    def test_no_members_rejected(self):
        self.assertRejected(_hh(), [], "Household members must be entered")

    def test_member_count_must_match_size(self):
        self.assertRejected(_hh(size=4, male=3), VALID, "size_of_group is 4 but 3 member(s)")

    def test_exactly_one_head_required(self):
        self.assertRejected(_hh(), [_m("MALE", False, "SPOUSE"), _m("MALE", False, "CHILD"), _m("FEMALE", False, "CHILD")], "must be marked as the head")
        self.assertRejected(_hh(), [_m("MALE", True), _m("MALE", True), _m("FEMALE", False, "CHILD")], "Only one household member")

    def test_non_head_needs_relationship_and_head_is_self(self):
        self.assertRejected(_hh(), [_m("MALE", True), _m("MALE", False, None), _m("FEMALE", False, "CHILD")], "required for every member")
        self.assertRejected(_hh(), [_m("MALE", True, "CHILD"), _m("MALE", False, "CHILD"), _m("FEMALE", False, "CHILD")], "other than SELF")
        validate_household_roster(_hh(), [_m("MALE", True, "SELF"), _m("MALE", False, "CHILD"), _m("FEMALE", False, "SPOUSE")])

    def test_gender_tally_must_match(self):
        self.assertRejected(_hh(), [_m("MALE", True), _m("FEMALE", False, "SPOUSE"), _m("FEMALE", False, "CHILD")], "1 male / 2 female")

    def test_orm_rows_and_dicts_both_accepted(self):
        rows = [SimpleNamespace(**m) for m in VALID]
        validate_household_roster({"size_of_group": 3, "number_of_male_members": 2, "number_of_female_members": 1}, rows)


if __name__ == "__main__":
    unittest.main()
