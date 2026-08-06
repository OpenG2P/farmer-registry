-- Aggregates for the Maps surface at the third level below country (woreda).
--
-- Named by DEPTH, not by level name. fr_rpt_farmer unpacks geography
-- positionally into geo_N/geo_N_id, so this query is identical for every
-- country pack; naming the file region/zone/woreda would bake Ethiopia's
-- hierarchy into a surface meant to work for any pack.
--
-- `pcode` joins to level3.geojson. Nothing is called `name`: Evidence's map
-- input proxy is a callable and a `name` field collides with Function.name,
-- which kills the map outright.
select
    f.geo_4_id    as pcode,
    f.geo_4       as area_name,
    f.geo_3_id as parent_pcode,
    count(*)                                                                  as farmers,
    round(sum(f.total_land_ha)::numeric, 0)                                 as land_ha,
    round(100.0 * avg(case when f.is_female then 1 else 0 end), 1)          as pct_female,
    round(100.0 * avg(case when f.has_land then 1 else 0 end), 1)           as pct_with_land,
    round(100.0 * avg(case when f.has_any_title then 1 else 0 end), 1)      as pct_with_title,
    round(100.0 * avg(case when f.uses_any_modern_input then 1 else 0 end), 1) as pct_modern_input,
    round(100.0 * avg(case when f.is_primary_cooperative_member then 1 else 0 end), 1) as pct_cooperative,
    round(100.0 * avg(case when f.keeps_livestock then 1 else 0 end), 1)    as pct_livestock,
    -- COUNTS, not rates. A rate needs a denominator big enough to survive one
    -- farmer moving; a count is exact whether the area holds 12 farmers or
    -- 12,000, needs no suppression, and sums up the hierarchy. It is also the
    -- form an extension officer can act on: "318 farmers holding land with no
    -- title" is a work order, "62.1% titled" is not.
    count(*) filter (where f.has_land and not f.has_any_title)        as no_title_farmers,
    count(*) filter (where not f.uses_any_modern_input)                     as no_input_farmers,
    count(*) filter (where not f.has_land)                                  as landless_farmers
from fr_rpt_farmer f
where f.geo_4_id is not null
group by 1, 2, 3
