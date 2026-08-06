---
title: Farmer Registry — Coverage & Practice
---

<!--
  Farmer Registry map surface.

  1. Nothing here names a level. Sources are level1/2/3_summary (the reporting
     views unpack geography positionally) and boundaries are level1/2/3.geojson,
     so the same page works for any country pack.
  2. The source namespace is `registry`, not `fr` — the Evidence project ships a
     single connection called `registry` and each registry's maps image drops its
     own queries into it. A page that names its own registry stops resolving the
     moment the image is built.
  3. The same four measures appear at every level — farmers, titled land, modern
     input use, cooperative membership — and below the top level each is shown
     against the level above, so a number reads as "better or worse than its
     parent" rather than as a bare figure.

  Depth -> level name for the installed pack. The page addresses levels by
  DEPTH; these are only the labels.

    level1.geojson = region  (heading: Regions)
    level2.geojson = zone    (heading: Zones)
    level3.geojson = woreda  (heading: Woredas)
-->

```sql national
select
  sum(farmers)                                             as farmers,
  sum(land_ha)                                             as land_ha,
  round(100.0 * sum(farmers * pct_with_title) / nullif(sum(farmers),0), 1)      as pct_with_title,
  round(100.0 * sum(farmers * pct_modern_input) / nullif(sum(farmers),0), 1)    as pct_modern_input,
  sum(no_title_farmers)                                    as no_title_farmers
from (
  select farmers, land_ha, pct_with_title/100.0 as pct_with_title,
         pct_modern_input/100.0 as pct_modern_input, no_title_farmers
  from registry.level1_summary
) x
```

# Farmer Registry — Coverage & Practice

<Grid cols=4>
  <BigValue data={national} value=farmers title="Farmers registered" fmt='#,##0' />
  <BigValue data={national} value=land_ha title="Land recorded (ha)" fmt='#,##0' />
  <BigValue data={national} value=pct_with_title title="Holding a title" fmt='0.0"%"' />
  <BigValue data={national} value=pct_modern_input title="Using modern inputs" fmt='0.0"%"' />
</Grid>

```sql l1
select * from registry.level1_summary order by farmers desc
```

```sql l1_head
-- The selected top-level area, each measure expressed as a delta against the
-- national figure, so the number carries its own benchmark.
with nat as (
  select round(avg(pct_with_title),1)   as n_title,
         round(avg(pct_modern_input),1) as n_input,
         round(avg(pct_cooperative),1)  as n_coop
  from registry.level1_summary
)
select r.*,
       round(r.pct_with_title   - nat.n_title, 1) as d_title,
       round(r.pct_modern_input - nat.n_input, 1) as d_input,
       round(r.pct_cooperative  - nat.n_coop, 1)  as d_coop
from registry.level1_summary r cross join nat
where r.pcode = '${inputs.sel_l1.pcode}'
```

<div class="split">
<div>

<AreaMap
  data={l1}
  geoJsonUrl='/geo/level1.geojson'
  areaCol=pcode
  geoId=pcode
  value=pct_with_title
  valueFmt='0.0'
  name=sel_l1
  startingLat=9.1
  startingLong=40.5
  startingZoom=5.2
  height=400
/>

</div>
<div>

<!-- HEADING:1 -->
## Region{#if l1_head.length}: {l1_head[0].area_name}{/if}

<Grid cols=2>
  <BigValue data={l1_head} value=farmers title="Farmers" fmt='#,##0' />
  <BigValue data={l1_head} value=pct_with_title title="Holding a title" fmt='0.0"%"'
            comparison=d_title comparisonTitle="vs national" comparisonFmt='0.0"pp"' />
  <BigValue data={l1_head} value=pct_modern_input title="Modern inputs" fmt='0.0"%"'
            comparison=d_input comparisonTitle="vs national" comparisonFmt='0.0"pp"' />
  <BigValue data={l1_head} value=pct_cooperative title="In a cooperative" fmt='0.0"%"'
            comparison=d_coop comparisonTitle="vs national" comparisonFmt='0.0"pp"' />
</Grid>

</div>
</div>

```sql l2_in_l1
select * from registry.level2_summary
where parent_pcode = '${inputs.sel_l1.pcode}'
order by farmers desc
```

```sql l2_head
-- Same measures again, now against the PARENT REGION rather than national —
-- the relevant benchmark once you are inside a parent area.
with parent as (
  select pct_with_title as p_title, pct_modern_input as p_input, pct_cooperative as p_coop
  from registry.level1_summary
  where pcode = '${inputs.sel_l1.pcode}'
)
select z.*,
       round(z.pct_with_title   - parent.p_title, 1) as d_title,
       round(z.pct_modern_input - parent.p_input, 1) as d_input,
       round(z.pct_cooperative  - parent.p_coop, 1)  as d_coop
from registry.level2_summary z cross join parent
where z.pcode = '${inputs.sel_l2.pcode}'
```

<div class="split">
<div>

<AreaMap
  data={l2_in_l1}
  geoJsonUrl='/geo/level2.geojson'
  areaCol=pcode
  geoId=pcode
  value=pct_with_title
  valueFmt='0.0'
  name=sel_l2
  height=400
/>

</div>
<div>

<!-- HEADING:2 -->
## Zone{#if l2_head.length}: {l2_head[0].area_name}{/if}

<Grid cols=2>
  <BigValue data={l2_head} value=farmers title="Farmers" fmt='#,##0' />
  <BigValue data={l2_head} value=pct_with_title title="Holding a title" fmt='0.0"%"'
            comparison=d_title comparisonTitle="vs region" comparisonFmt='0.0"pp"' />
  <BigValue data={l2_head} value=pct_modern_input title="Modern inputs" fmt='0.0"%"'
            comparison=d_input comparisonTitle="vs region" comparisonFmt='0.0"pp"' />
  <!-- downIsGood: a rising count of land held without a title is bad news, so
       the delta must not be coloured green when it goes up. -->
  <BigValue data={l2_head} value=no_title_farmers title="Land, no title" fmt='#,##0' />
</Grid>

</div>
</div>

```sql commodities
select * from registry.level2_commodities
where area_name = '${inputs.sel_l2.area_name}'
order by crops desc
```

### What is grown here{#if l2_head.length}: {l2_head[0].area_name}{/if}

<BarChart
  data={commodities}
  x=commodity
  y=crops
  swapXY=true
  title="Crop records by commodity"
/>

```sql l3_in_l2
select * from registry.level3_summary
where parent_pcode = '${inputs.sel_l2.pcode}'
order by farmers desc
```

```sql l3_head
with parent as (
  select pct_with_title as p_title, pct_modern_input as p_input
  from registry.level2_summary
  where pcode = '${inputs.sel_l2.pcode}'
)
select w.*,
       round(w.pct_with_title   - parent.p_title, 1) as d_title,
       round(w.pct_modern_input - parent.p_input, 1) as d_input
from registry.level3_summary w cross join parent
where w.pcode = '${inputs.sel_l3.pcode}'
```

<div class="split">
<div>

<AreaMap
  data={l3_in_l2}
  geoJsonUrl='/geo/level3.geojson'
  areaCol=pcode
  geoId=pcode
  value=pct_with_title
  valueFmt='0.0'
  name=sel_l3
  height=400
/>

</div>
<div>

<!-- HEADING:3 -->
## Woreda{#if l3_head.length}: {l3_head[0].area_name}{/if}

<Grid cols=2>
  <BigValue data={l3_head} value=farmers title="Farmers" fmt='#,##0' />
  <BigValue data={l3_head} value=land_ha title="Land (ha)" fmt='#,##0' />
  <BigValue data={l3_head} value=pct_with_title title="Holding a title" fmt='0.0"%"'
            comparison=d_title comparisonTitle="vs zone" comparisonFmt='0.0"pp"' />
  <BigValue data={l3_head} value=pct_modern_input title="Modern inputs" fmt='0.0"%"'
            comparison=d_input comparisonTitle="vs zone" comparisonFmt='0.0"pp"' />
</Grid>

</div>
</div>

### Woredas in this zone

<DataTable data={l3_in_l2} rows=15 search=true>
  <Column id=area_name title="Woreda" />
  <Column id=farmers title="Farmers" fmt='#,##0' />
  <Column id=land_ha title="Land (ha)" fmt='#,##0' />
  <Column id=pct_with_title title="Titled" fmt='0.0"%"' />
  <Column id=pct_modern_input title="Modern inputs" fmt='0.0"%"' />
  <Column id=no_title_farmers title="Land, no title" fmt='#,##0' />
  <Column id=landless_farmers title="Landless" fmt='#,##0' />
</DataTable>

<!-- PACK-ATTRIBUTION:START — generated by sync_pack.py, do not edit -->
<!-- PACK-ATTRIBUTION:END -->
