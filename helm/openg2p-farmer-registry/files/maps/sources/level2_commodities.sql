-- The crops farmers in each zone declare they mainly grow, for a stacked
-- composition bar.
--
-- Long format (one row per zone per crop) because that is what a stacked series
-- wants. Capped to the leading crops so the bar stays readable; everything else
-- is folded into 'Other' rather than dropped. A farmer declaring several main
-- crops counts once under each, so the bars are farmer-crop declarations, not
-- a partition of the zone's farmers.
--
-- Reads main_crops, declared at registration (Master Data CROP_COMMODITY codes).
-- What is actually sown each season is the Crop Sown Registry's, not this
-- registry's, and is not mapped here.
--
-- This is the Farmer Registry's analogue of a social registry's poverty
-- quintile breakdown: the composition question that makes an area's profile
-- legible at a glance. It deliberately does NOT use computed_score — that is
-- populated for only a fraction of farmers, so a score-based split would
-- describe the subset that happens to have been scored, not the zone.
with ranked as (
    select main_crop as commodity, count(*) as n
    from fr_rpt_farmer_main_crop
    where main_crop is not null
    group by 1
    order by n desc
    limit 8
)
select
    c.geo_3        as area_name,
    c.geo_2        as parent_area_name,
    case when r.commodity is null then 'Other' else c.main_crop end as commodity,
    count(distinct c.farmer_id) as farmers
from fr_rpt_farmer_main_crop c
left join ranked r on r.commodity = c.main_crop
where c.geo_3 is not null
group by 1, 2, 3
