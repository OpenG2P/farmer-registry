import unittest
from datetime import date
from types import SimpleNamespace

from openg2p_registry_farmer_extension.register_domain.services.utils.household_roster import (
    apply_household_roster_counts,
    compute_household_roster_counts,
    union_roster_people,
)


def _person(**kwargs) -> dict:
    payload = {"record_status": "ACTIVE"}
    payload.update(kwargs)
    return payload


class HouseholdRosterTests(unittest.TestCase):
    def test_adding_elderly_member_overwrites_elderly_and_size(self):
        existing = [
            _person(gender="FEMALE", estimated_age=65),
            _person(gender="MALE", estimated_age=70),
            _person(gender="FEMALE", estimated_age=30),
        ]
        before = compute_household_roster_counts(existing)
        self.assertEqual(before.number_of_elderly_members, 2)
        self.assertEqual(before.size_of_group, 3)
        self.assertEqual(before.number_of_female_members, 2)
        self.assertEqual(before.number_of_male_members, 1)

        after = compute_household_roster_counts(
            existing + [_person(gender="MALE", estimated_age=62)]
        )
        self.assertEqual(after.number_of_elderly_members, 3)
        self.assertEqual(after.size_of_group, 4)
        self.assertEqual(after.number_of_male_members, 2)
        self.assertEqual(after.number_of_female_members, 2)

    def test_adding_child_overwrites_children_count(self):
        existing = [
            _person(gender="MALE", estimated_age=40),
            _person(gender="FEMALE", estimated_age=8),
        ]
        before = compute_household_roster_counts(existing)
        self.assertEqual(before.number_of_children, 1)
        self.assertEqual(before.size_of_group, 2)

        after = compute_household_roster_counts(
            existing + [_person(gender="FEMALE", estimated_age=3)]
        )
        self.assertEqual(after.number_of_children, 2)
        self.assertEqual(after.size_of_group, 3)
        self.assertEqual(after.number_of_female_members, 2)

    def test_seed_age_cutoffs_from_birth_date(self):
        today = date(2026, 9, 9)
        people = [
            _person(gender="MALE", birth_date="2009-09-10"),
            _person(gender="FEMALE", birth_date="2008-09-09"),
            _person(gender="MALE", birth_date="1966-09-09"),
            _person(gender="FEMALE", birth_date="1966-09-10"),
        ]
        counts = compute_household_roster_counts(people, today=today)
        self.assertEqual(counts.number_of_children, 1)
        self.assertEqual(counts.number_of_elderly_members, 1)
        self.assertEqual(counts.size_of_group, 4)

    def test_farmer_and_member_with_same_foundational_id_count_once(self):
        members = [
            _person(
                internal_record_id="member-1",
                foundational_id="FID-1",
                first_name="Rita",
                last_name="Das",
                gender="FEMALE",
                estimated_age=40,
            )
        ]
        farmers = [
            _person(
                internal_record_id="farmer-1",
                foundational_id="FID-1",
                first_name="Rita",
                last_name="Das",
                gender="FEMALE",
                estimated_age=40,
            )
        ]
        people = union_roster_people(members, farmers)
        counts = compute_household_roster_counts(people)
        self.assertEqual(counts.size_of_group, 1)
        self.assertEqual(counts.number_of_female_members, 1)

    def test_overlay_person_wins_over_matching_member(self):
        members = [
            _person(
                internal_record_id="member-1",
                foundational_id="FID-1",
                gender="FEMALE",
                estimated_age=40,
                link_internal_record_id="hh-1",
            )
        ]
        farmers = [
            _person(
                internal_record_id="farmer-1",
                foundational_id="FID-1",
                gender="FEMALE",
                estimated_age=61,
                link_internal_record_id="hh-1",
            )
        ]
        overlay = _person(
            internal_record_id="farmer-1",
            foundational_id="FID-1",
            gender="FEMALE",
            estimated_age=61,
            link_internal_record_id="hh-1",
        )
        people = union_roster_people(
            members, farmers, overlay_person=overlay, overlay_household_id="hh-1"
        )
        counts = compute_household_roster_counts(people)
        self.assertEqual(counts.size_of_group, 1)
        self.assertEqual(counts.number_of_elderly_members, 1)

    def test_unlinked_farmer_is_counted_in_addition_to_members(self):
        members = [
            _person(
                internal_record_id="member-1",
                foundational_id="FID-CHILD",
                gender="MALE",
                estimated_age=10,
            )
        ]
        farmers = [
            _person(
                internal_record_id="farmer-1",
                foundational_id="FID-HEAD",
                gender="FEMALE",
                estimated_age=61,
            )
        ]
        people = union_roster_people(members, farmers)
        counts = compute_household_roster_counts(people)
        self.assertEqual(counts.size_of_group, 2)
        self.assertEqual(counts.number_of_children, 1)
        self.assertEqual(counts.number_of_elderly_members, 1)
        self.assertEqual(counts.number_of_male_members, 1)
        self.assertEqual(counts.number_of_female_members, 1)

    def test_inactive_people_are_excluded(self):
        people = [
            _person(gender="MALE", estimated_age=70),
            _person(gender="FEMALE", estimated_age=8, record_status="INACTIVE"),
        ]
        counts = compute_household_roster_counts(people)
        self.assertEqual(counts.size_of_group, 1)
        self.assertEqual(counts.number_of_children, 0)
        self.assertEqual(counts.number_of_elderly_members, 1)

    def test_apply_household_roster_counts_overwrites_existing_values(self):
        household = SimpleNamespace(
            size_of_group=5,
            number_of_children=1,
            number_of_elderly_members=2,
            number_of_female_members=3,
            number_of_male_members=2,
        )
        aggregates = compute_household_roster_counts(
            [
                _person(gender="MALE", estimated_age=70),
                _person(gender="MALE", estimated_age=65),
                _person(gender="FEMALE", estimated_age=62),
            ]
        )
        apply_household_roster_counts(household, aggregates)
        self.assertEqual(household.size_of_group, 3)
        self.assertEqual(household.number_of_elderly_members, 3)
        self.assertEqual(household.number_of_children, 0)
        self.assertEqual(household.number_of_male_members, 2)
        self.assertEqual(household.number_of_female_members, 1)


if __name__ == "__main__":
    unittest.main()
