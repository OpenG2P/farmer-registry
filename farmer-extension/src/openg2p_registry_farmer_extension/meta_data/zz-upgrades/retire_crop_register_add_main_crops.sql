-- Upgrade: retire the Crop child register; add the farmer's declared Main crops.
--
-- Why this file exists
-- --------------------
-- Every other file under meta_data/ is an INSERT (most now upsert with ON
-- CONFLICT ... DO UPDATE), and the db-seed Job runs them with ON_ERROR_STOP=0.
-- On a fresh install that is all it takes. On an install that already holds the
-- metadata, an insert or upsert can only add or overwrite the rows the files
-- carry -- it never removes one -- so removing the Crop register would never
-- reach it (nor, before the upserts, would adding the Main crops widget).
--
-- This file brings such an install to the same metadata a fresh install gets.
-- It sorts after every other directory (zz-), runs after the inserts and after
-- the model migration, and is idempotent: on a fresh install, or on a second
-- run, every statement matches nothing.
--
-- What it does NOT touch: data. The g2p_register_crops / _history_ / intake
-- tables and their rows stay in the database. Crop facts now belong to the Crop
-- Sown Registry; nothing in the Farmer Registry reads those tables any more.

-- 1. Crop register metadata: tabs, sections, schema, definition.
DELETE FROM "public"."g2p_intake_form_ui_tab_sections"
 WHERE section_id = 'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2';

DELETE FROM "public"."g2p_register_ui_tab_sections"
 WHERE section_id = 'farmer_crop_crop_details_section_01';

DELETE FROM "public"."g2p_register_ui_tabs"
 WHERE tab_id = 'farmer_crop_tab';

DELETE FROM "public"."g2p_register_sections"
 WHERE section_id IN ('farmer_crop_crop_details_section_01',
                      'a7d69d0c-ed5b-4d78-b2b5-90dfe40c8aa2')
    OR section_register_id = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

DELETE FROM "public"."g2p_register_schemas"
 WHERE register_id = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

DELETE FROM "public"."g2p_register_definitions"
 WHERE register_id = '5fa096f8-ffdc-4b0a-ab16-9ca386c23310';

-- 2. Main crops widget, in the empty third panel of the farmer's
--    socio-economic section (and the Household register's view of that same
--    farmer section). Same JSON as g2p_register_sections.sql. Only replaces the
--    panel while it is still the empty placeholder, so a deployment that has
--    put something else there is left alone.
UPDATE "public"."g2p_register_sections"
   SET section_ui_schema = jsonb_set(
         section_ui_schema,
         '{panels,0,panels,2}',
         '{"widgets": [{"widget": "multi-select", "widget-id": "main_crops", "widget-type": "input", "widget-label": "main_crops", "widget-readonly": false, "widget-required": false, "widget-data-path": "a1a4d25a-1cd4-4356-abac-985a0b3c6bcd.main_crops", "widget-data-helptext": "main_crops_help", "widget-data-tooltip": "main_crops_help", "widget-data-source": {"type": "api", "method": "POST", "params": {"attribute_id": "CROP_COMMODITY"}, "service": "attributes", "endpoint": "values", "labelKey": "value_display", "valueKey": "value_code"}}], "panel-id": "panel_farming", "panel-title": "farming_details", "panel-orientation": "vertical"}'::jsonb)
 WHERE section_id IN ('farmer_farmer_socio_economic_and_health_section_04',
                      'household_farmer_socio_economic_and_health_section_04')
   AND section_ui_schema #>> '{panels,0,panels,2,panel-id}' = 'panel_empty_3';

-- 3. Labels: add the Main crops strings, drop the Crop register's.
UPDATE "public"."registry_languages"
   SET domain_translation = (
         (domain_translation::jsonb
            - 'Crop' - 'add_crop' - 'crops' - 'farmer_crops' - 'farmer_crops_tab'
            - 'register_fr_farmer_crops' - 'intake_fr_farmer_crops'
            - 'commodity' - 'planted_date' - 'season' - 'end_use'
            - 'FOOD_HUMAN_CONSUMPTION' - 'FEED_ANIMALS' - 'BIOFUELS_NONFOOD'
            - 'KHARIF' - 'RABI' - 'ZAYED' - 'PERENNIAL')
         || '{"farming_details": "Farming Details", "main_crops": "Main crops", "main_crops_help": "Crops the farmer mainly grows, as declared at registration"}'::jsonb
       )::json
 WHERE language_code = 'en'
   AND domain_translation IS NOT NULL
   AND NOT (domain_translation::jsonb ? 'main_crops_help'
            AND NOT domain_translation::jsonb ? 'add_crop');
