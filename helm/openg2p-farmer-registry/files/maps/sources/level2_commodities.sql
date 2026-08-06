-- The crops actually grown in each zone, for a stacked composition bar.
--
-- Long format (one row per zone per commodity) because that is what a stacked
-- series wants. Capped to the leading commodities so the bar stays readable;
-- everything else is folded into 'Other' rather than dropped, so the shares
-- still sum to the zone's crop records.
--
-- This is the Farmer Registry's analogue of a social registry's poverty
-- quintile breakdown: the composition question that makes an area's profile
-- legible at a glance. It deliberately does NOT use computed_score — that is
-- populated for only a fraction of farmers, so a score-based split would
-- describe the subset that happens to have been scored, not the zone.
with ranked as (
    select commodity, count(*) as n
    from fr_rpt_crop
    where commodity is not null
    group by 1
    order by n desc
    limit 8
)
select
    c.geo_3        as area_name,
    c.geo_2        as parent_area_name,
    case when r.commodity is null then 'Other' else c.commodity end as commodity,
    count(*)       as crops
from fr_rpt_crop c
left join ranked r on r.commodity = c.commodity
where c.geo_3 is not null
group by 1, 2, 3
