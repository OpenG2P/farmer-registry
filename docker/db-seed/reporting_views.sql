-- Farmer Registry reporting layer
-- =============================================================================
-- Flattens the register into wide, indexed materialized views that dashboards
-- (Superset) read from. Charts then stay simple SELECTs instead of repeating
-- multi-table joins and JSONB digging in every chart definition.
--
-- Grain differs from NSR, deliberately
-- ------------------------------------
-- NSR pairs household/individual. Farmer's shape is a three-level tree:
--
--     farmer ──< land ──< livestock / farm_inputs
--            └──< membership_details, score
--
-- Livestock and inputs hang off the LAND PARCEL, not the farmer (verified
-- against the seed set: 317/317 livestock and 434/434 input rows link to a land
-- id, 0 to a farmer id). So there are two views, at the two grains that answer
-- real questions:
--
--   fr_rpt_farmer — one row per farmer, everything rolled up. "How many farmers
--                   irrigate?", "cluster membership by region", "livestock heads
--                   per farmer".
--   fr_rpt_land   — one row per parcel. "Area by tenure", "land use".
--                   Area questions MUST use this view: rolling area to the farmer
--                   and then charting it double-counts nothing, but slicing by a
--                   parcel attribute (tenure, use) only makes sense per parcel.
--
-- Country-agnostic by construction
-- --------------------------------
-- Geography is unpacked from geo_code_hierarchy_json BY POSITION (ordinality),
-- never by level name. A deployment with country/region/district/ward/village and
-- one with region/zone/woreda/kebele both populate geo_1..geo_n in their own
-- order, and `fr_rpt_geo_levels` carries that deployment's actual level labels so
-- a dashboard can title the columns correctly. Nothing here assumes a country, a
-- level naming scheme, or a fixed depth.
--
-- Areas are normalised to hectares
-- --------------------------------
-- land_size is a free-text column and unit is an enum, so the raw pair cannot be
-- summed. land_size_ha is the only column charts should aggregate; the raw pair is
-- carried alongside for drill-down. A non-numeric land_size yields NULL rather
-- than failing the refresh — bad data must not take the dashboards down.
--
-- Materialized, not plain views: the JSONB unpacking over a bulk-loaded register
-- is far too slow to run per chart. Refresh after a load, LAND FIRST — fr_rpt_farmer
-- reads fr_rpt_land, so refreshing the farmer view against a stale land view
-- publishes stale holdings:
--
--   REFRESH MATERIALIZED VIEW CONCURRENTLY fr_rpt_land;
--   REFRESH MATERIALIZED VIEW CONCURRENTLY fr_rpt_farmer;
--
-- Crops are not records in this registry: what is sown each season belongs to
-- the Crop Sown Registry. A farmer carries only main_crops, the crops declared at
-- registration (Master Data CROP_COMMODITY codes). fr_rpt_farmer exposes them,
-- and fr_rpt_farmer_main_crop (a plain view, one row per farmer per declared
-- crop) answers "farmers by main crop" — it needs no refresh of its own.
--
-- (CONCURRENTLY needs the unique indexes created at the bottom, and those in turn
-- need a first non-concurrent refresh — which CREATE ... AS does for us.)
-- =============================================================================

-- fr_rpt_geo_levels is GENERATED, from Master Data.
--
-- It used to be derived here, by unpacking a registered farmer's own hierarchy.
-- That made the labels a property of the DATA: a registry installed empty — the
-- production case — produced an empty lookup, so nothing could name its own geo
-- columns. Master Data holds the country pack and knows the answer before the
-- first record exists.

-- ---------------------------------------------------------------------------
-- Land parcels
-- ---------------------------------------------------------------------------
-- Built first: fr_rpt_farmer rolls its per-farmer aggregates off the same CTEs.
-- The retired per-planting view. It read g2p_register_crops, which the Farmer
-- Registry no longer writes (the table and its rows are left in place on an
-- upgraded database). Dropped whichever kind it is; reporting.yaml names it
-- under `custom:` so the generator does not recreate it from the legacy table.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_matviews WHERE schemaname = current_schema()
               AND matviewname = 'fr_rpt_crop') THEN
        EXECUTE 'DROP MATERIALIZED VIEW fr_rpt_crop CASCADE';
    ELSIF EXISTS (SELECT 1 FROM pg_views WHERE schemaname = current_schema()
                  AND viewname = 'fr_rpt_crop') THEN
        EXECUTE 'DROP VIEW fr_rpt_crop CASCADE';
    END IF;
END $$;

DROP MATERIALIZED VIEW IF EXISTS fr_rpt_land CASCADE;
CREATE MATERIALIZED VIEW fr_rpt_land AS
WITH land_geo AS (
    SELECT
        l.internal_record_id AS land_id,
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_1,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_2,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_3,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_4,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_5,
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_id' END) AS geo_1_id,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_id' END) AS geo_2_id,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_id' END) AS geo_3_id,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_id' END) AS geo_4_id,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_id' END) AS geo_5_id
    FROM g2p_register_lands l,
         LATERAL jsonb_array_elements(l.geo_code_hierarchy_json -> 'hierarchy')
                 WITH ORDINALITY AS t(elem, ordinality)
    WHERE l.geo_code_hierarchy_json IS NOT NULL
    GROUP BY l.internal_record_id
),
stock AS (
    SELECT link_internal_record_id AS land_id,
           count(*)                                                      AS livestock_record_count,
           COALESCE(sum(head_count), 0)                                  AS livestock_head_total,
           string_agg(DISTINCT livestock_type, ', ' ORDER BY livestock_type) AS livestock_types,
           -- A parcel can carry several systems; take the one with most heads.
           (array_agg(livestock_system ORDER BY head_count DESC NULLS LAST))[1] AS main_livestock_system
    FROM g2p_register_livestocks
    WHERE record_status = 'ACTIVE'
    GROUP BY link_internal_record_id
),
inputs AS (
    -- A parcel may hold more than one input record; OR them so "uses fertilizer"
    -- means "on this parcel, at all".
    SELECT link_internal_record_id AS land_id,
           bool_or(fertilizer_use)      AS fertilizer_use,
           bool_or(pesticide_use)       AS pesticide_use,
           bool_or(insecticide_use)     AS insecticide_use,
           bool_or(improved_seed_use)   AS improved_seed_use,
           bool_or(access_to_machinery) AS access_to_machinery,
           bool_or(access_to_finance)   AS access_to_finance,
           string_agg(DISTINCT water_source, ', ' ORDER BY water_source) AS water_sources
    FROM g2p_register_farm_inputs
    WHERE record_status = 'ACTIVE'
    GROUP BY link_internal_record_id
)
SELECT
    l.internal_record_id                       AS land_id,
    l.link_internal_record_id                  AS farmer_id,
    l.functional_record_id,
    l.created_at,
    l.record_status,

    COALESCE(g.geo_1, fg.geo_1) AS geo_1,
    COALESCE(g.geo_2, fg.geo_2) AS geo_2,
    COALESCE(g.geo_3, fg.geo_3) AS geo_3,
    COALESCE(g.geo_4, fg.geo_4) AS geo_4,
    COALESCE(g.geo_5, fg.geo_5) AS geo_5,
    COALESCE(g.geo_1_id, fg.geo_1_id) AS geo_1_id,
    COALESCE(g.geo_2_id, fg.geo_2_id) AS geo_2_id,
    COALESCE(g.geo_3_id, fg.geo_3_id) AS geo_3_id,
    COALESCE(g.geo_4_id, fg.geo_4_id) AS geo_4_id,
    COALESCE(g.geo_5_id, fg.geo_5_id) AS geo_5_id,
    l.geo_lowest_level_value_id,
    l.latitude,
    l.longitude,

    l.land_ownership_type,
    (l.land_ownership_type = 'OWNER')          AS is_owner_operated,
    l.current_land_use,
    (l.current_land_use = 'AGRICULTURAL')      AS is_agricultural,
    l.farming_type,
    l.soil_fertility,
    l.year_of_acquisition,
    l.means_of_acquisition,
    (l.certificate_storage_id IS NOT NULL
     AND l.certificate_storage_id <> '')       AS has_title_certificate,

    -- Raw pair kept for drill-down; land_size_ha is the only summable column.
    l.land_size                                AS land_size_raw,
    l.unit                                     AS land_size_unit,
    (CASE
        WHEN l.land_size IS NULL THEN NULL
        WHEN btrim(l.land_size) !~ '^[0-9]+(\.[0-9]+)?$' THEN NULL
        ELSE btrim(l.land_size)::numeric * CASE l.unit
            WHEN 'HECTARE'      THEN 1
            WHEN 'ACRE'         THEN 0.404686
            WHEN 'SQUARE_METER' THEN 0.0001
            WHEN 'SQUARE_KM'    THEN 100
            WHEN 'SQUARE_FOOT'  THEN 0.000009290304
            WHEN 'SQUARE_YARD'  THEN 0.000083612736
            ELSE NULL
        END
     END)::numeric(18,6)                       AS land_size_ha,

    COALESCE(s.livestock_record_count, 0)      AS livestock_record_count,
    COALESCE(s.livestock_head_total, 0)        AS livestock_head_total,
    s.livestock_types,
    s.main_livestock_system,

    COALESCE(i.fertilizer_use, false)          AS fertilizer_use,
    COALESCE(i.pesticide_use, false)           AS pesticide_use,
    COALESCE(i.insecticide_use, false)         AS insecticide_use,
    COALESCE(i.improved_seed_use, false)       AS improved_seed_use,
    COALESCE(i.access_to_machinery, false)     AS access_to_machinery,
    COALESCE(i.access_to_finance, false)       AS access_to_finance,
    i.water_sources,
    (COALESCE(i.fertilizer_use, false)
     OR COALESCE(i.improved_seed_use, false)
     OR COALESCE(i.access_to_machinery, false)) AS uses_any_modern_input
FROM g2p_register_lands l
LEFT JOIN land_geo g  ON g.land_id  = l.internal_record_id
LEFT JOIN stock    s  ON s.land_id  = l.internal_record_id
LEFT JOIN inputs   i  ON i.land_id  = l.internal_record_id
-- Parcel geo is often blank while the farmer's is set; fall back so map and
-- region charts do not silently drop parcels.
LEFT JOIN LATERAL (
    SELECT
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_1,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_2,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_3,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_4,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_5,
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_id' END) AS geo_1_id,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_id' END) AS geo_2_id,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_id' END) AS geo_3_id,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_id' END) AS geo_4_id,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_id' END) AS geo_5_id
    FROM g2p_register_farmers pf,
         LATERAL jsonb_array_elements(pf.geo_code_hierarchy_json -> 'hierarchy')
                 WITH ORDINALITY AS t(elem, ordinality)
    WHERE pf.internal_record_id = l.link_internal_record_id
      AND pf.geo_code_hierarchy_json IS NOT NULL
) fg ON TRUE;

COMMENT ON MATERIALIZED VIEW fr_rpt_land IS
    'One row per land parcel with its livestock and input use rolled in. '
    'Area questions belong here: land_size_ha is normalised to hectares and is '
    'the only summable area column.';


-- ---------------------------------------------------------------------------
-- Farmers
-- ---------------------------------------------------------------------------
DROP MATERIALIZED VIEW IF EXISTS fr_rpt_farmer CASCADE;
CREATE MATERIALIZED VIEW fr_rpt_farmer AS
WITH geo AS (
    SELECT
        f.internal_record_id AS farmer_id,
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_1,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_2,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_3,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_4,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_mnemonic' END) AS geo_5,
        MAX(CASE WHEN t.ordinality = 1 THEN t.elem ->> 'level_value_id' END) AS geo_1_id,
        MAX(CASE WHEN t.ordinality = 2 THEN t.elem ->> 'level_value_id' END) AS geo_2_id,
        MAX(CASE WHEN t.ordinality = 3 THEN t.elem ->> 'level_value_id' END) AS geo_3_id,
        MAX(CASE WHEN t.ordinality = 4 THEN t.elem ->> 'level_value_id' END) AS geo_4_id,
        MAX(CASE WHEN t.ordinality = 5 THEN t.elem ->> 'level_value_id' END) AS geo_5_id
    FROM g2p_register_farmers f,
         LATERAL jsonb_array_elements(f.geo_code_hierarchy_json -> 'hierarchy')
                 WITH ORDINALITY AS t(elem, ordinality)
    WHERE f.geo_code_hierarchy_json IS NOT NULL
    GROUP BY f.internal_record_id
),
holding AS (
    -- Roll the parcel view up to the farmer. Reusing fr_rpt_land keeps one
    -- definition of "hectares" and of "uses an input" instead of two that drift.
    SELECT farmer_id,
           count(*)                                   AS parcel_count,
           sum(land_size_ha)                          AS total_land_ha,
           count(*) FILTER (WHERE land_size_ha IS NULL) AS parcels_missing_area,
           bool_or(is_owner_operated)                 AS owns_any_parcel,
           bool_or(has_title_certificate)             AS has_any_title,
           sum(livestock_head_total)                  AS livestock_head_total,
           bool_or(fertilizer_use)                    AS fertilizer_use,
           bool_or(improved_seed_use)                 AS improved_seed_use,
           bool_or(access_to_machinery)               AS access_to_machinery,
           bool_or(access_to_finance)                 AS access_to_finance,
           bool_or(uses_any_modern_input)             AS uses_any_modern_input,
           -- Largest parcel decides the headline tenure / use / system.
           (array_agg(land_ownership_type   ORDER BY land_size_ha DESC NULLS LAST))[1] AS main_tenure,
           (array_agg(current_land_use      ORDER BY land_size_ha DESC NULLS LAST))[1] AS main_land_use,
           (array_agg(farming_type          ORDER BY land_size_ha DESC NULLS LAST))[1] AS main_farming_type,
           (array_agg(main_livestock_system ORDER BY livestock_head_total DESC NULLS LAST))[1] AS main_livestock_system
    FROM fr_rpt_land
    GROUP BY farmer_id
),
member AS (
    SELECT link_internal_record_id AS farmer_id,
           bool_or(is_primary_cooperative_member) AS is_primary_cooperative_member,
           bool_or(is_cooperative_union_member)   AS is_cooperative_union_member,
           bool_or(is_farmer_cluster_member)      AS is_farmer_cluster_member,
           (array_agg(farmer_cluster_role) FILTER (WHERE farmer_cluster_role IS NOT NULL))[1] AS farmer_cluster_role,
           string_agg(DISTINCT primary_cooperative_name, ', ') AS cooperative_names
    FROM g2p_register_membership_details
    WHERE record_status = 'ACTIVE'
    GROUP BY link_internal_record_id
),
score AS (
    -- Latest score per farmer, whatever the deployment calls its score type.
    SELECT DISTINCT ON (link_internal_record_id)
           link_internal_record_id AS farmer_id,
           computed_score,
           score_type,
           computed_at
    FROM g2p_register_scores
    ORDER BY link_internal_record_id, computed_at DESC
)
SELECT
    f.internal_record_id                       AS farmer_id,
    f.functional_record_id,
    f.created_at,
    f.registration_date,
    f.record_status,

    g.geo_1, g.geo_2, g.geo_3, g.geo_4, g.geo_5,
    g.geo_1_id, g.geo_2_id, g.geo_3_id, g.geo_4_id, g.geo_5_id,
    f.geo_lowest_level_value_id,
    f.latitude,
    f.longitude,

    f.gender,
    f.marital_status,
    f.education_level,
    f.occupation,
    f.language_spoken,
    f.source_of_income,
    f.disabled,
    f.disability_type,
    f.disability_severity,
    f.has_personal_phone,

    -- birth_date is a DATE; estimated_age covers the records captured without one.
    -- Computed once in the LATERAL below rather than inlined per band, so the two
    -- columns cannot disagree.
    a.age,
    (CASE
        WHEN a.age IS NULL THEN 'UNKNOWN'
        WHEN a.age < 25    THEN 'UNDER_25'
        WHEN a.age < 35    THEN '25_34'
        WHEN a.age < 50    THEN '35_49'
        WHEN a.age < 65    THEN '50_64'
        ELSE '65_PLUS'
     END)                                      AS age_band,
    (f.gender = 'FEMALE')                      AS is_female,

    COALESCE(h.parcel_count, 0)                AS parcel_count,
    h.total_land_ha,
    COALESCE(h.parcels_missing_area, 0)        AS parcels_missing_area,
    (COALESCE(h.parcel_count, 0) > 0)          AS has_land,
    COALESCE(h.owns_any_parcel, false)         AS owns_any_parcel,
    COALESCE(h.has_any_title, false)           AS has_any_title,
    h.main_tenure,
    h.main_land_use,
    h.main_farming_type,
    h.main_livestock_system,

    -- Declared at registration (Master Data CROP_COMMODITY codes). The JSONB
    -- list is kept for drill-down; main_crop_codes is its readable label, and
    -- fr_rpt_farmer_main_crop has one row per declared crop for grouping.
    mc.main_crops,
    mc.main_crop_codes,
    COALESCE(mc.main_crop_count, 0)            AS main_crop_count,
    (COALESCE(mc.main_crop_count, 0) > 0)      AS has_main_crops,

    COALESCE(h.livestock_head_total, 0)        AS livestock_head_total,
    (COALESCE(h.livestock_head_total, 0) > 0)  AS keeps_livestock,

    COALESCE(h.fertilizer_use, false)          AS fertilizer_use,
    COALESCE(h.improved_seed_use, false)       AS improved_seed_use,
    COALESCE(h.access_to_machinery, false)     AS access_to_machinery,
    COALESCE(h.access_to_finance, false)       AS access_to_finance,
    COALESCE(h.uses_any_modern_input, false)   AS uses_any_modern_input,

    COALESCE(m.is_primary_cooperative_member, false) AS is_primary_cooperative_member,
    COALESCE(m.is_cooperative_union_member, false)   AS is_cooperative_union_member,
    COALESCE(m.is_farmer_cluster_member, false)      AS is_farmer_cluster_member,
    m.farmer_cluster_role,
    m.cooperative_names,

    sc.computed_score,
    sc.score_type,
    sc.computed_at                             AS score_computed_at,

    -- Completeness, for the data-quality panel. Deliberately counts the fields an
    -- extension officer is expected to capture, not every nullable column.
    (
        (f.gender            IS NOT NULL)::int +
        (f.birth_date        IS NOT NULL OR f.estimated_age IS NOT NULL)::int +
        (f.education_level   IS NOT NULL)::int +
        (f.source_of_income  IS NOT NULL)::int +
        (f.geo_code_hierarchy_json IS NOT NULL)::int +
        (COALESCE(h.parcel_count, 0) > 0)::int
    )                                          AS profile_fields_present,
    6                                          AS profile_fields_expected
FROM g2p_register_farmers f
LEFT JOIN geo     g  ON g.farmer_id  = f.internal_record_id
LEFT JOIN holding h  ON h.farmer_id  = f.internal_record_id
LEFT JOIN member  m  ON m.farmer_id  = f.internal_record_id
LEFT JOIN score   sc ON sc.farmer_id = f.internal_record_id
-- main_crops is a JSONB list; anything else (NULL, a stray scalar) reads as none
-- rather than failing the refresh.
CROSS JOIN LATERAL (
    SELECT CASE WHEN jsonb_typeof(f.main_crops) = 'array' THEN f.main_crops END AS main_crops,
           (SELECT string_agg(c, ', ' ORDER BY c)
              FROM jsonb_array_elements_text(
                     CASE WHEN jsonb_typeof(f.main_crops) = 'array'
                          THEN f.main_crops ELSE '[]'::jsonb END) AS c) AS main_crop_codes,
           (CASE WHEN jsonb_typeof(f.main_crops) = 'array'
                 THEN jsonb_array_length(f.main_crops) END)          AS main_crop_count
) mc
CROSS JOIN LATERAL (
    SELECT COALESCE(
        CASE WHEN f.birth_date IS NOT NULL
             THEN date_part('year', age(f.birth_date))::int END,
        f.estimated_age) AS age
) a;

COMMENT ON MATERIALIZED VIEW fr_rpt_farmer IS
    'One row per farmer with land, main crops, livestock, input, membership and score '
    'rolled up. Use fr_rpt_land for anything sliced by a parcel attribute.';


-- ---------------------------------------------------------------------------
-- Indexes
-- ---------------------------------------------------------------------------
-- Unique indexes are what allow REFRESH ... CONCURRENTLY (refresh without
-- blocking readers — a dashboard mid-query keeps the old snapshot).
CREATE UNIQUE INDEX fr_rpt_farmer_pk ON fr_rpt_farmer (farmer_id);
CREATE UNIQUE INDEX fr_rpt_land_pk   ON fr_rpt_land   (land_id);

-- Geo indexes back the region drill-down, which filters progressively by level.
CREATE INDEX fr_rpt_farmer_geo    ON fr_rpt_farmer (geo_1, geo_2, geo_3);
CREATE INDEX fr_rpt_land_geo      ON fr_rpt_land   (geo_1, geo_2, geo_3);

-- The columns the shipped dashboards group by.
CREATE INDEX fr_rpt_farmer_sex    ON fr_rpt_farmer (gender);
CREATE INDEX fr_rpt_farmer_band   ON fr_rpt_farmer (age_band);
CREATE INDEX fr_rpt_farmer_ftype  ON fr_rpt_farmer (main_farming_type);
CREATE INDEX fr_rpt_farmer_cluster ON fr_rpt_farmer (is_farmer_cluster_member);
CREATE INDEX fr_rpt_land_tenure   ON fr_rpt_land   (land_ownership_type);
CREATE INDEX fr_rpt_land_use      ON fr_rpt_land   (current_land_use);
CREATE INDEX fr_rpt_land_ftype    ON fr_rpt_land   (farming_type);


-- ---------------------------------------------------------------------------
-- Farmers by main crop
-- ---------------------------------------------------------------------------
-- One row per farmer per declared main crop, with the farmer's geography and
-- the dimensions charts slice by. A plain view over fr_rpt_farmer: always as
-- current as that snapshot, nothing to refresh. COUNT(*) here counts
-- farmer-crop declarations; COUNT(DISTINCT farmer_id) counts farmers. Recreated
-- on every run because the DROP ... CASCADE of fr_rpt_farmer above removes it.
CREATE VIEW fr_rpt_farmer_main_crop AS
SELECT
    f.farmer_id,
    f.functional_record_id,
    c.main_crop,
    f.main_crop_count,
    f.geo_1, f.geo_2, f.geo_3, f.geo_4, f.geo_5,
    f.geo_1_id, f.geo_2_id, f.geo_3_id, f.geo_4_id, f.geo_5_id,
    f.gender,
    f.is_female,
    f.age_band,
    f.main_farming_type,
    f.record_status
FROM fr_rpt_farmer f
CROSS JOIN LATERAL jsonb_array_elements_text(f.main_crops) AS c(main_crop)
WHERE f.main_crops IS NOT NULL;

COMMENT ON VIEW fr_rpt_farmer_main_crop IS
    'One row per farmer per declared main crop (Master Data CROP_COMMODITY code). '
    'COUNT(DISTINCT farmer_id) for farmers; never sum farmer measures here.';
