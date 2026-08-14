"""Central configuration for the bulk seed generator. See README.md for the
full flow this drives."""

import os

DATA_VOLUME_TIERS = {
    "smoke": 10_000,
    "primary": 10_000_000,
    "stretch": 50_000_000,
    "stress": 100_000_000,
}

# Generation order = topological order of this graph: every table lists the
# parent it links to via link_internal_record_id, and how many child rows
# each parent row gets (sampled independently per parent from the range).
# "household" has parent=None: its count is derived from the farmer target
# via AVG_FARMERS_PER_HOUSEHOLD, and it is generated first.
AVG_FARMERS_PER_HOUSEHOLD = (2, 3)

RATIOS = {
    # table_key: (register_mnemonic, parent_table_key, (min_per_parent, max_per_parent))
    "household": ("Household", None, None),
    "farmer": ("Farmer", "household", AVG_FARMERS_PER_HOUSEHOLD),
    "household_member": ("HouseholdMember", "household", (3, 5)),
    "land": ("Land", "farmer", (1, 2)),
    "crop": ("Crop", "land", (1, 3)),
    "livestock": ("Livestock", "farmer", (0, 1)),
    "farm_inputs": ("FarmInputs", "farmer", (1, 1)),
    "membership_details": ("MembershipDetails", "farmer", (1, 1)),
}

# Tables that get a *_history twin row for every generated record (1:1, not
# a sample -- see README "History rows").
HISTORY_TABLES = [
    "household", "farmer", "household_member", "land", "crop",
    "livestock", "farm_inputs", "membership_details",
]

# Search-text anchors: 4-char substrings embedded in Farmer first_name so
# search_in_a_register / pg_trgm has guaranteed, high-cardinality matches.
# Kept small and assigned round-robin (not randomly) so every anchor gets a
# roughly equal, large share of farmers -- 10,000 anchors over e.g. a 10M
# farmer target left ~1,000 farmers/anchor on average with random assignment
# variance on top; 100 anchors round-robin gives every anchor exactly
# target_farmers // 100 (+/-1) matches, deterministically.
SEARCH_ANCHOR_COUNT = 100
SEARCH_ANCHOR_LENGTH = 4

# Reduced field list for Farmer.search_text (see README: "Why search_text is
# generator-computed, not ORM-computed"). Other tables keep their full
# production field list (see generators/*.py).
FARMER_SEARCH_TEXT_FIELDS = [
    "functional_record_id", "first_name", "last_name", "middle_name",
    "foundational_id", "birth_date", "address_line_1", "address_line_2",
]

# id scheme prefixes, mirrored from
# farmer-extension/.../id_generator/g2p_id_generator_service.py
ID_PREFIXES = {
    "Household": "HH-",
    "Farmer": "FR-",
}
DEFAULT_ID_PREFIX = "DEFAULT-"

# table_key -> (live tablename, history tablename, register_mnemonic)
TABLE_NAMES = {
    "household": ("g2p_register_households", "g2p_register_history_households", "Household"),
    "farmer": ("g2p_register_farmers", "g2p_register_history_farmers", "Farmer"),
    "household_member": ("g2p_register_household_members", "g2p_register_history_household_members", "HouseholdMember"),
    "land": ("g2p_register_lands", "g2p_register_history_lands", "Land"),
    "crop": ("g2p_register_crops", "g2p_register_history_crops", "Crop"),
    "livestock": ("g2p_register_livestocks", "g2p_register_history_livestocks", "Livestock"),
    "farm_inputs": ("g2p_register_farm_inputs", "g2p_register_history_farm_inputs", "FarmInputs"),
    "membership_details": ("g2p_register_membership_details", "g2p_register_history_membership_details", "MembershipDetails"),
}

BATCH_SIZE = 75_000
RANDOM_SEED = 42

DB_DSN = os.environ.get(
    "SEED_DB_DSN", "postgresql://postgres:postgres@localhost:5432/g2p_registry"
)
DEFER_INDEXES = False

OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))
SEED_MANIFEST_PATH = os.path.join(OUTPUT_DIR, "seed_manifest.json")
