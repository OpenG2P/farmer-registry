-- Upgrade: functional IDs for Farmer and Household; household and member
-- fields from 1.2; dedicated intake-form sections for farm inputs and livestock.
--
-- Why this file exists
-- --------------------
-- Same reason as retire_crop_register_add_main_crops.sql: an install that
-- already holds the metadata must end up with what a fresh install gets. Most
-- metadata files now upsert (ON CONFLICT ... DO UPDATE), which brings changed
-- rows across, but an upsert can neither add a column nor remove a row the
-- files no longer carry. Idempotent: on a fresh install, or on a second run,
-- every statement matches nothing.

-- 1. Functional IDs are generated for Farmer and Household (G2P-5538). The
--    register definitions upsert sets this too; kept here so the switch does
--    not depend on that file's ON CONFLICT clause.
UPDATE "public"."g2p_register_definitions"
   SET functional_id_generation_required = TRUE
 WHERE register_id IN ('a1a4d25a-1cd4-4356-abac-985a0b3c6bcd',   -- Farmer
                       '9055ab43-c85d-4833-bd00-ca657bb72644')   -- Household
   AND functional_id_generation_required IS DISTINCT FROM TRUE;

-- 2. Columns 1.2 added to existing tables (G2P-5604/5616/5607). The staff API
--    adds them on start-up (add_missing_columns in app.py); this repeats it
--    for an install whose API has not migrated yet. Nullable, no default, so
--    existing rows stay valid. IF EXISTS: a table the API has not created yet
--    is created whole, with the columns, by its first migration.
ALTER TABLE IF EXISTS "public"."g2p_register_households"
  ADD COLUMN IF NOT EXISTS number_of_elderly_members INTEGER;
ALTER TABLE IF EXISTS "public"."g2p_register_history_households"
  ADD COLUMN IF NOT EXISTS number_of_elderly_members INTEGER;
ALTER TABLE IF EXISTS "public"."g2p_intake_form_households"
  ADD COLUMN IF NOT EXISTS number_of_elderly_members INTEGER;

ALTER TABLE IF EXISTS "public"."g2p_register_household_members"
  ADD COLUMN IF NOT EXISTS is_head BOOLEAN,
  ADD COLUMN IF NOT EXISTS relationship_to_the_head VARCHAR;
ALTER TABLE IF EXISTS "public"."g2p_register_history_household_members"
  ADD COLUMN IF NOT EXISTS is_head BOOLEAN,
  ADD COLUMN IF NOT EXISTS relationship_to_the_head VARCHAR;
ALTER TABLE IF EXISTS "public"."g2p_intake_form_household_members"
  ADD COLUMN IF NOT EXISTS is_head BOOLEAN,
  ADD COLUMN IF NOT EXISTS relationship_to_the_head VARCHAR;

-- land_size (text -> numeric) is NOT converted here: the API does it on
-- start-up (convert_land_size_to_numeric in app.py), before it writes a land
-- row, together with the reporting views that read the column.

-- 3. The farmer intake form now uses intake-only farm-input and livestock
--    sections (their parent lookup lists the lands of the form being filled,
--    not register lands). Drop the old placements of the register sections, or
--    an upgraded form would show both. Only while they still point at the old
--    sections, so a placement a deployment has repointed is left alone.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
 WHERE (tab_section_id = 'tab_section_8'
        AND section_id = 'farmer_farm_input_farm_input_details_section_01')
    OR (tab_section_id = 'tab_section_10'
        AND section_id = 'farmer_livestock_livestock_details_section_01');
