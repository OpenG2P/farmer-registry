"""Canonical identifiers for everything the sanity e2e creates.

Every row the suite writes carries one of these markers, so the whole fixture
set can be found — and later deleted — with a single predicate per table. The
suite deliberately does NOT clean up after itself: the records are left in place
so a failed run can be inspected. See `TEARDOWN_SQL` for the removal statements.

Nothing here may collide with seeded sample data: the `SANITY` marker never
appears in openg2p-data demography, and the ids are fixed UUIDs so a re-run
updates rather than duplicates.
"""

# Marker embedded in search_text — the DCI query the e2e sends looks for exactly
# this, so the search can never match seeded sample data.
SEARCH_MARKER = "SANITYE2E"

# `created_by` stamped on every row the suite writes — the teardown predicate.
CREATED_BY = "sanity-e2e"

# Fixed so a re-run is idempotent (ON CONFLICT DO UPDATE) rather than additive.
FARMER_INTERNAL_ID = "00000000-5a11-4e2e-8000-000000000001"
FARMER_FUNCTIONAL_ID = "SANITY-FARMER-0001"
FARMER_FOUNDATIONAL_ID = "SANITY-UIN-0001"

# The injected farmer's demographics. The e2e asserts these exact values come
# back through the DCI template, so they must stay in sync with the assertions.
FARMER = {
    "first_name": "Sanity",
    "middle_name": "E2E",
    "last_name": "Testfarmer",
    "gender": "FEMALE",
    "birth_date": "1990-01-01",
    "marital_status": "SINGLE",
    "education_level": "CAN_READ_AND_WRITE",
    "language_code": "en",
}

# The field the change-request test edits. `middle_name` is a free-text field
# that lives in a real, editable UI section (farmer personal-identification), so
# the change-request API accepts it — and the DCI test does not assert it, so
# changing it cannot break the data-sharing assertions.
CR_FIELD = "middle_name"
CR_VALUE_INITIAL = "SANITYMID"
CR_VALUE_UPDATED = "SANITYMOD"

# The DCI search matches on `search_text`. Approving a change request updates the
# record through the ORM, which REGENERATES search_text from the record's fields
# and so drops any value not derived from a real column (the manual marker). The
# functional_record_id IS a search-text field, so searching for it survives an
# approved change request — which is why the DCI search targets it, not the
# manual marker.
SEARCH_TOKEN = FARMER_FUNCTIONAL_ID

# The suite's OWN Keycloak identity, provisioned by sanity.keycloak_seed with a
# NON-temporary password. The shipped demo users cannot be used: keycloak-init
# sets their password as temporary, so Keycloak forces UPDATE_PASSWORD and the
# password grant fails with "Account is not fully set up".
STAFF_USERNAME = "sanity-e2e"

# Roles the test user needs on the registry's Keycloak client. These expand to
# the changeRequest:create / changeRequest:approve / register:view /
# registerHistory:view permissions the CR flow requires.
STAFF_ROLES = ["Operations Administrator", "Technical Administrator"]

# Tags the approver_rule rows sanity.awe_seed adds to the SHIPPED policy's
# stages, so they are identifiable; the shipped demo-user rules are untouched.
AWE_RULE_MARKER = "sanity-e2e"

# Statements that remove everything the suite created. Not run automatically —
# provided so an operator can clean an environment on demand.
#
# Registry rows are keyed on internal_record_id, not created_by: the farmer row
# carries created_by='sanity-e2e' (set by our SQL), but the change-request and
# history rows are stamped by the registry with the *user's display name*
# ("Sanity E2E"), so internal_record_id is the one reliable marker across all
# three tables.
TEARDOWN_SQL = {
    "registry": [
        f"DELETE FROM g2p_register_history_farmers WHERE internal_record_id = '{FARMER_INTERNAL_ID}';",
        f"DELETE FROM g2p_register_change_requests WHERE internal_record_id = '{FARMER_INTERNAL_ID}';",
        f"DELETE FROM g2p_register_farmers WHERE internal_record_id = '{FARMER_INTERNAL_ID}';",
    ],
    "awe": [
        # Orphaned approval requests/tasks for the sanity farmer's change requests
        # (run BEFORE the registry deletes, while the CR ids are still resolvable),
        # then the approver rule the suite added.
        f"DELETE FROM approver_rule WHERE rule_value::text LIKE '%{AWE_RULE_MARKER}%';",
    ],
    # Keycloak (admin API, not SQL): delete user STAFF_USERNAME from the staff realm.
}
