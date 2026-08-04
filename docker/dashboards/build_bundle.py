#!/usr/bin/env python3
"""Build the default Farmer Registry Superset dashboard bundle.

Produces the importable ZIP that ships with NSR:

    python build_bundle.py --out fr-dashboards.zip
    superset import-dashboards -p fr-dashboards.zip -u admin

Design notes
------------
* **Deterministic UUIDs.** Every asset's uuid is uuid5(namespace, stable key),
  so re-importing the same bundle UPDATES the existing assets instead of
  creating duplicates. That is what makes this safe to run on every install and
  upgrade rather than once.

* **Portable viz types only.** The bundle has to import into Superset 4.0.1
  (currently deployed) and 6.1 (where we are heading). Only viz types verified
  present in both are used — big_number_total, pie, echarts_timeseries_bar,
  table. Notably `dist_bar` is avoided: it exists in 4.0.1 but was removed with
  the NVD3 plugin in 6.x, so a chart using it saves fine and then renders blank.

* **Adhoc metrics, not metric names.** A bare string in a chart's metric field
  is resolved against the dataset's SAVED metrics, of which a fresh dataset has
  exactly one (`count`). Anything else has to be expressed as an adhoc metric or
  the chart 400s at query time.

* **Charts read the reporting views**, not the register tables — see
  ../db-seed/reporting_views.sql. Geography is exposed as positional columns
  geo_1..geo_5, so no chart hardcodes a country's level names.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
import zipfile
from datetime import datetime, timezone

import yaml

# Fixed namespace for uuid5. Do not change it: the derived asset UUIDs are what
# let a re-import update the existing dashboards instead of duplicating them.
NS = uuid.UUID("6f1d2a54-3c7b-4f6e-9a1e-8b4c9d0e1f22")
BUNDLE = "fr_dashboards"
DB_NAME = "FR"
SCHEMA = "public"

FARMER = "fr_rpt_farmer"
LAND = "fr_rpt_land"
CROP = "fr_rpt_crop"


def uid(*parts) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def slug(name: str, limit: int = 60) -> str:
    """Filename-safe slug that always starts with an alphanumeric.

    A chart called "% with foundational ID" otherwise yields
    "__with_foundational_ID.yaml", and the importer skips files whose names
    start with an underscore — the chart vanishes from the bundle silently,
    with no error and a dashboard that is simply missing a tile.
    """
    s = "".join(ch if ch.isalnum() else "_" for ch in name).strip("_")
    return (s or "chart")[:limit]


# ---------------------------------------------------------------------------
# metric / column helpers
# ---------------------------------------------------------------------------
def simple(col, agg, label):
    return {
        "expressionType": "SIMPLE",
        "column": {"column_name": col},
        "aggregate": agg,
        "label": label,
        "hasCustomLabel": True,
    }


def sql_metric(expr, label):
    """Adhoc SQL metric — used for the percentage-of-a-boolean measures that
    make up most social protection indicators (coverage, prevalence, gaps)."""
    return {
        "expressionType": "SQL",
        "sqlExpression": expr,
        "label": label,
        "hasCustomLabel": True,
    }


# d3 format for a ratio: multiplies by 100 and appends the sign, so 0.124 -> 12.4%.
PCT_FORMAT = ".1%"


def pct(col, label):
    """Share of rows where a boolean column is true, as a RATIO (0-1).

    Returns a ratio rather than an already-multiplied percentage so the chart
    can format it with d3's "%" — which multiplies by 100 and appends the sign.
    Emitting 12.4 and formatting it as SMART_NUMBER, as this used to, printed a
    bare "12.4" with nothing to say it was a percentage. Multiplying here AND
    formatting as a percent would print "1240%".

    The private __pct__ marker tells the chart helpers to apply PCT_FORMAT; they
    pop it before the metric is serialised, so Superset never sees it.
    """
    m = sql_metric(f"AVG(CASE WHEN {col} THEN 1.0 ELSE 0 END)", label)
    m["__pct__"] = True
    return m


def pct_expr(expr, label):
    """A ratio metric from an arbitrary expression, marked like pct().

    For the conditional shares — coverage of the poorest quintile, leakage to
    the richest — where the denominator is a subset rather than every row.
    """
    m = sql_metric(expr, label)
    m["__pct__"] = True
    return m


def _fmt_for(metrics):
    """PCT_FORMAT when every metric here is a ratio from pct(), else the default.

    Mixed charts keep SMART_NUMBER: a percent format applied to a count would
    multiply it by 100.
    """
    ms = metrics if isinstance(metrics, list) else [metrics]
    flags = [bool(m.pop("__pct__", False)) if isinstance(m, dict) else False for m in ms]
    return PCT_FORMAT if flags and all(flags) else "SMART_NUMBER"


# Columns where NULL means "the question does not apply" and the reporting view
# therefore labels the value NA. Shown as the chart's description so a reader who
# meets an NA slice can find out what it means without leaving the dashboard.
NA_MEANING = {
    "education_level": "NA = not recorded for this farmer.",
    "marital_status": "NA = not recorded for this farmer.",
    "source_of_income": "NA = not recorded for this farmer.",
    "disability_type": "NA = not disabled, or not recorded.",
    "disability_severity": "NA = not disabled, or not recorded.",
    "age_band": "UNKNOWN = neither a birth date nor an estimated age was captured.",
    "farmer_cluster_role": "NA = not a member of a farmer cluster.",
    "main_tenure": "NA = this farmer holds no registered parcel.",
    "main_land_use": "NA = this farmer holds no registered parcel.",
    "main_farming_type": "NA = this farmer holds no registered parcel.",
    "main_livestock_system": "NA = no livestock recorded on the parcel.",
    "land_ownership_type": "NA = not recorded for this parcel.",
    "current_land_use": "NA = not recorded for this parcel.",
    "farming_type": "NA = not recorded for this parcel.",
    "end_use": "NA = not recorded for this planting.",
    "season": "NA = not recorded for this planting.",
}

def na_note(*dims):
    """The NA explanation for whichever of these dimensions can carry one."""
    seen, out = set(), []
    for d in dims:
        for col in (d if isinstance(d, list) else [d]):
            if isinstance(col, str) and col in NA_MEANING and col not in seen:
                seen.add(col)
                out.append(NA_MEANING[col])
    return " ".join(out) or None


# COUNT(*) as an adhoc SQL metric, NOT simple("*", "COUNT", ...). A SIMPLE
# adhoc metric names a column, and Superset validates that name against the
# dataset's real columns — "*" is not one, so every chart using it fails at
# render with "Columns missing in dataset: ['*']" even though the underlying
# SQL is perfectly valid.
COUNT = sql_metric("COUNT(*)", "Total")


# ---------------------------------------------------------------------------
# chart definitions
# ---------------------------------------------------------------------------
def big(name, dataset, metric, subheader=""):
    return {
        "name": name, "dataset": dataset, "viz_type": "big_number_total",
        "params": {"metric": metric, "subheader": subheader,
                   "y_axis_format": _fmt_for(metric)},
    }


def bar(name, dataset, x, metrics, series=None, row_limit=100, sort_desc=True):
    p = {
        "x_axis": x, "metrics": metrics, "groupby": series or [],
        "row_limit": row_limit, "orientation": "vertical",
        "x_axis_sort_asc": not sort_desc, "sort_series_type": "sum",
        "y_axis_format": _fmt_for(metrics), "rich_tooltip": True,
    }
    return {"name": name, "dataset": dataset, "viz_type": "echarts_timeseries_bar",
            "params": p, "description": na_note(x, series)}


def pie(name, dataset, groupby, metric, row_limit=25):
    return {
        "name": name, "dataset": dataset, "viz_type": "pie",
        "params": {"groupby": groupby, "metric": metric, "row_limit": row_limit,
                   "donut": True, "show_labels": True, "label_type": "key_percent",
                   "number_format": _fmt_for(metric)},
        "description": na_note(groupby),
    }


def table(name, dataset, groupby, metrics, row_limit=100):
    """A table mixes counts and ratios, so the format goes per COLUMN.

    Capture the ratio labels before _fmt_for runs — it pops the __pct__ marker,
    which must not reach Superset. Forgetting that call here was a real bug: the
    marker leaked into six exported charts, because every other helper popped it
    and this one did not.
    """
    pct_labels = [m["label"] for m in metrics
                  if isinstance(m, dict) and m.get("__pct__")]
    _fmt_for(metrics)
    return {
        "name": name, "dataset": dataset, "viz_type": "table",
        "description": na_note(groupby),
        "params": {"query_mode": "aggregate", "groupby": groupby, "metrics": metrics,
                   "row_limit": row_limit, "include_search": True,
                   "order_desc": True, "server_pagination": False,
                   "column_config": {lbl: {"d3NumberFormat": PCT_FORMAT}
                                     for lbl in pct_labels}},
    }


def build_charts():
    """Every chart, grouped by the dashboard it belongs to.

    Which view a chart reads is a correctness question, not a preference:
      FARMER — one row per farmer. "How many farmers ...", any % of farmers.
      LAND   — one row per parcel. ALL area totals: land_size_ha only sums here.
      CROP   — one row per planting. Crop mix; never sum area (it repeats per crop).
    """
    d = {}

    # -- 1. Coverage & data quality -----------------------------------------
    d["Registry Coverage & Data Quality"] = [
        big("Farmers registered", FARMER, COUNT),
        big("Land parcels registered", LAND, COUNT),
        big("Total registered area", LAND,
            simple("land_size_ha", "SUM", "Hectares"), "hectares"),
        big("% of farmers holding land", FARMER, pct("has_land", "% with land")),
        pie("Record status", FARMER, ["record_status"], COUNT),
        bar("Farmers by region", FARMER, "geo_2", [COUNT]),
        table("Data completeness by region", FARMER,
              ["geo_2"],
              [COUNT,
               pct_expr("AVG(profile_fields_present::numeric "
                        "/ NULLIF(profile_fields_expected, 0))", "% profile complete"),
               pct_expr("AVG(CASE WHEN geo_5_id IS NOT NULL THEN 1.0 ELSE 0 END)",
                        "% geo-resolved to lowest level"),
               pct_expr("AVG(CASE WHEN has_land THEN 1.0 ELSE 0 END)", "% with land")]),
        big("Parcels missing an area figure", LAND,
            sql_metric("COUNT(*) FILTER (WHERE land_size_ha IS NULL)", "Parcels"),
            "land_size not numeric, or an unrecognised unit"),
    ]

    # -- 2. Farmer demographics ---------------------------------------------
    d["Farmer Demographics"] = [
        # Not "Farmers registered" — chart names seed the uuid, so the same name
        # in two dashboards collapses into one asset and vanishes from one of them.
        big("Farmers profiled", FARMER, COUNT),
        big("% women farmers", FARMER, pct("is_female", "% women")),
        pie("Sex", FARMER, ["gender"], COUNT),
        bar("Age distribution", FARMER, "age_band", [COUNT], sort_desc=False),
        pie("Education level", FARMER, ["education_level"], COUNT),
        pie("Main source of income", FARMER, ["source_of_income"], COUNT),
        big("% reachable by phone", FARMER,
            pct("has_personal_phone", "% with a personal phone")),
        bar("Farmers by region and sex", FARMER, "geo_2", [COUNT], series=["gender"]),
        table("Demographics by region", FARMER,
              ["geo_2"],
              [COUNT,
               pct_expr("AVG(CASE WHEN is_female THEN 1.0 ELSE 0 END)", "% women"),
               simple("age", "AVG", "Average age"),
               pct_expr("AVG(CASE WHEN disabled THEN 1.0 ELSE 0 END)",
                        "% reporting a disability")]),
    ]

    # -- 3. Land & tenure ----------------------------------------------------
    d["Land & Tenure"] = [
        big("Parcels registered", LAND, COUNT),
        big("Total area", LAND, simple("land_size_ha", "SUM", "Hectares"), "hectares"),
        big("Average parcel size", LAND,
            simple("land_size_ha", "AVG", "Hectares"), "hectares"),
        big("% owner-operated", LAND, pct("is_owner_operated", "% owner-operated")),
        big("% with a title certificate", LAND,
            pct("has_title_certificate", "% titled")),
        pie("Tenure", LAND, ["land_ownership_type"], COUNT),
        pie("Current land use", LAND, ["current_land_use"], COUNT),
        bar("Farming type", LAND, "farming_type", [COUNT]),
        bar("Area by region", LAND, "geo_2",
            [simple("land_size_ha", "SUM", "Hectares")]),
        table("Tenure by region", LAND,
              ["geo_2", "land_ownership_type"],
              [COUNT, simple("land_size_ha", "SUM", "Hectares")]),
    ]

    # -- 4. Crops & cropping -------------------------------------------------
    d["Crops & Cropping"] = [
        big("Crop plantings recorded", CROP, COUNT),
        big("Distinct commodities", CROP,
            sql_metric("COUNT(DISTINCT commodity)", "Commodities")),
        big("% grown for food", CROP, pct("is_food_crop", "% for human consumption")),
        bar("Most planted commodities", CROP, "commodity", [COUNT], row_limit=15),
        pie("End use", CROP, ["end_use"], COUNT),
        pie("Season", CROP, ["season"], COUNT),
        bar("Plantings by region", CROP, "geo_2", [COUNT]),
        table("Commodity by region", CROP,
              ["geo_2", "commodity"],
              [COUNT,
               pct_expr("AVG(CASE WHEN is_food_crop THEN 1.0 ELSE 0 END)",
                        "% for food")],
              row_limit=200),
    ]

    # -- 5. Livestock, inputs & cooperatives ---------------------------------
    d["Livestock, Inputs & Cooperatives"] = [
        big("% keeping livestock", FARMER, pct("keeps_livestock", "% with livestock")),
        big("Total livestock head", FARMER,
            simple("livestock_head_total", "SUM", "Head")),
        pie("Livestock production system", LAND, ["main_livestock_system"], COUNT),
        big("% using fertiliser", FARMER, pct("fertilizer_use", "% fertiliser")),
        big("% using improved seed", FARMER,
            pct("improved_seed_use", "% improved seed")),
        big("% with machinery access", FARMER,
            pct("access_to_machinery", "% machinery")),
        big("% with finance access", FARMER, pct("access_to_finance", "% finance")),
        pie("Primary cooperative membership", FARMER,
            ["is_primary_cooperative_member"], COUNT),
        pie("Role in farmer cluster", FARMER, ["farmer_cluster_role"], COUNT),
        table("Input access by region", FARMER,
              ["geo_2"],
              [COUNT,
               pct_expr("AVG(CASE WHEN fertilizer_use THEN 1.0 ELSE 0 END)",
                        "% fertiliser"),
               pct_expr("AVG(CASE WHEN improved_seed_use THEN 1.0 ELSE 0 END)",
                        "% improved seed"),
               pct_expr("AVG(CASE WHEN access_to_finance THEN 1.0 ELSE 0 END)",
                        "% finance"),
               pct_expr("AVG(CASE WHEN uses_any_modern_input THEN 1.0 ELSE 0 END)",
                        "% any modern input")]),
    ]

    return d
# ---------------------------------------------------------------------------
# YAML emitters
# ---------------------------------------------------------------------------
def dataset_yaml(name, db_uuid, columns):
    return {
        "table_name": name,
        "main_dttm_col": None,
        "description": f"NSR reporting view {name}",
        "default_endpoint": None,
        "offset": 0,
        "cache_timeout": None,
        "schema": SCHEMA,
        "sql": None,
        "params": None,
        "template_params": None,
        "filter_select_enabled": True,
        "fetch_values_predicate": None,
        "extra": None,
        "normalize_columns": False,
        "always_filter_main_dttm": False,
        "uuid": uid("dataset", name),
        "metrics": [{
            "metric_name": "count",
            "verbose_name": "COUNT(*)",
            "metric_type": "count",
            "expression": "COUNT(*)",
            "description": None,
            "d3format": None,
            "currency": None,
            "extra": None,
            "warning_text": None,
        }],
        "columns": columns,
        "version": "1.0.0",
        "database_uuid": db_uuid,
    }


def column_entry(name, dtype):
    t = (dtype or "").upper()
    if "INT" in t:
        gen, is_dttm = "BIGINT", False
    elif any(k in t for k in ("DOUBLE", "NUMERIC", "REAL")):
        gen, is_dttm = "DOUBLE PRECISION", False
    elif "BOOL" in t:
        gen, is_dttm = "BOOLEAN", False
    elif "TIMESTAMP" in t or "DATE" in t:
        gen, is_dttm = "TIMESTAMP WITHOUT TIME ZONE", True
    else:
        gen, is_dttm = "VARCHAR", False
    return {
        "column_name": name,
        "verbose_name": None,
        "is_dttm": is_dttm,
        "is_active": True,
        "type": gen,
        "advanced_data_type": None,
        "groupby": True,
        "filterable": True,
        "expression": None,
        "description": None,
        "python_date_format": None,
        "extra": None,
    }


def chart_yaml(c, dataset_uuids):
    params = dict(c["params"])
    params.update({
        "datasource": f"{dataset_uuids[c['dataset']]}__table",
        "viz_type": c["viz_type"],
    })
    return {
        "slice_name": c["name"],
        # Superset shows this as an info icon beside the chart title, which is
        # where a reader who meets an "NA" slice will look first.
        "description": c.get("description"),
        "certified_by": None,
        "certification_details": None,
        "viz_type": c["viz_type"],
        # A mapping, not a JSON string. The REST API wants params serialised;
        # the YAML import format wants it structured, and passing a string here
        # fails validation with "Not a valid mapping type" on every chart.
        "params": params,
        "query_context": None,
        "cache_timeout": None,
        "uuid": uid("chart", c["name"]),
        "version": "1.0.0",
        "dataset_uuid": dataset_uuids[c["dataset"]],
    }


def dashboard_yaml(title, charts, native_filter_datasets):
    """Lay charts out two per row and attach a dashboard-wide gender filter."""
    pos = {
        "DASHBOARD_VERSION_KEY": "v2",
        "ROOT_ID": {"type": "ROOT", "id": "ROOT_ID", "children": ["GRID_ID"]},
        "GRID_ID": {"type": "GRID", "id": "GRID_ID", "children": [], "parents": ["ROOT_ID"]},
    }
    # Big-number tiles are narrow; everything else takes half the 12-col grid.
    row, col_used, row_idx = [], 0, 0

    def flush():
        nonlocal row, col_used, row_idx
        if not row:
            return
        rid = f"ROW-{row_idx}"
        pos[rid] = {"type": "ROW", "id": rid, "children": [c[0] for c in row],
                    "parents": ["ROOT_ID", "GRID_ID"],
                    "meta": {"background": "BACKGROUND_TRANSPARENT"}}
        pos["GRID_ID"]["children"].append(rid)
        for cid, meta in row:
            meta["parents"] = ["ROOT_ID", "GRID_ID", rid]
            pos[cid] = meta
        row, col_used, row_idx = [], 0, row_idx + 1

    for i, c in enumerate(charts):
        width = 3 if c["viz_type"] == "big_number_total" else 6
        height = 30 if c["viz_type"] == "big_number_total" else 50
        if col_used + width > 12:
            flush()
        cid = f"CHART-{i}"
        row.append((cid, {
            "type": "CHART", "id": cid, "children": [],
            "meta": {"chartId": 0, "width": width, "height": height,
                     "uuid": uid("chart", c["name"]), "sliceName": c["name"]},
        }))
        col_used += width
    flush()

    # Native filters. `gender` is the one the request called out — one control
    # that re-cuts every chart on the dashboard, which is cheaper than doubling
    # the chart count with male/female variants.
    filters = []
    for i, (col, label, ds) in enumerate(native_filter_datasets):
        filters.append({
            "id": f"NATIVE_FILTER-{uid('filter', title, col)[:8]}",
            "name": label,
            "filterType": "filter_select",
            "targets": [{"datasetUuid": ds, "column": {"name": col}}],
            "defaultDataMask": {"extraFormData": {}, "filterState": {}, "ownState": {}},
            "cascadeParentIds": [],
            "scope": {"rootPath": ["ROOT_ID"], "excluded": []},
            "type": "NATIVE_FILTER",
            "description": "",
            "chartsInScope": [],
            "tabsInScope": [],
            "controlValues": {"multiSelect": True, "enableEmptyFilter": False,
                              "searchAllOptions": False, "inverseSelection": False},
        })

    return {
        "dashboard_title": title,
        "description": None,
        "css": "",
        "slug": None,
        "uuid": uid("dashboard", title),
        "position": pos,
        "metadata": {
            "color_scheme": None,
            "refresh_frequency": 0,
            "expanded_slices": {},
            "timed_refresh_immune_slices": [],
            "cross_filters_enabled": True,
            "native_filter_configuration": filters,
        },
        "version": "1.0.0",
    }


def fetch_columns(dsn, view):
    import psycopg2
    conn = psycopg2.connect(**dsn)
    with conn.cursor() as cur:
        # pg_catalog, not information_schema: the reporting layer is built from
        # MATERIALIZED views, and Postgres deliberately omits those from
        # information_schema.columns (they aren't in the SQL standard). Querying
        # information_schema here silently returns nothing.
        cur.execute(
            """
            select a.attname, format_type(a.atttypid, a.atttypmod)
            from pg_class c
            join pg_namespace n on n.oid = c.relnamespace
            join pg_attribute a on a.attrelid = c.oid
            where n.nspname = %s and c.relname = %s
              and c.relkind in ('r', 'v', 'm')
              and a.attnum > 0 and not a.attisdropped
            order by a.attnum
            """,
            (SCHEMA, view))
        cols = [column_entry(r[0], r[1]) for r in cur.fetchall()]
    conn.close()
    if not cols:
        raise SystemExit(f"view {view} not found — run reporting_views.sql first")
    return cols


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    # Default straight into the chart. Helm's .Files.Get cannot reach outside
    # the chart directory, so that copy has to be the canonical one — keeping a
    # second copy here as well would just drift out of step with it.
    p.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "helm", "openg2p-farmer-registry", "files", "fr-dashboards.zip"))
    p.add_argument("--db-name", default=DB_NAME)
    p.add_argument("--sqlalchemy-uri",
                   default="postgresql+psycopg2://postgres:XXXXX@commons-postgresql:5432/fr",
                   help="connection string recorded in the bundle; the password "
                        "is replaced at import time by Superset if left as a "
                        "placeholder, or override per environment")
    args = p.parse_args()

    dsn = dict(
        dbname=os.environ.get("FR_DB", "fr"),
        host=os.environ.get("PGHOST", "localhost"),
        port=os.environ.get("PGPORT", "5432"),
        user=os.environ.get("PGUSER", "postgres"),
        password=os.environ.get("PGPASSWORD", ""),
    )

    db_uuid = uid("database", args.db_name)
    ds_uuids = {v: uid("dataset", v) for v in (FARMER, LAND, CROP)}

    files = {}
    files[f"{BUNDLE}/metadata.yaml"] = {
        "version": "1.0.0", "type": "Dashboard",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    files[f"{BUNDLE}/databases/{args.db_name}.yaml"] = {
        "database_name": args.db_name,
        "sqlalchemy_uri": args.sqlalchemy_uri,
        "cache_timeout": None,
        "expose_in_sqllab": True,
        "allow_run_async": False,
        "allow_ctas": False,
        "allow_cvas": False,
        "allow_dml": False,
        "allow_file_upload": False,
        # A dict, not a JSON string: the import schema loads `extra` as a nested
        # schema, so a string fails deep inside marshmallow with an unhelpful
        # "'str' object has no attribute 'get'".
        "extra": {"allows_virtual_table_explore": True},
        "uuid": db_uuid,
        "version": "1.0.0",
    }
    for view in (FARMER, LAND, CROP):
        files[f"{BUNDLE}/datasets/{args.db_name}/{view}.yaml"] = dataset_yaml(
            view, db_uuid, fetch_columns(dsn, view))

    charts_by_dash = build_charts()
    seen = set()
    for title, charts in charts_by_dash.items():
        for c in charts:
            key = c["name"]
            if key in seen:
                # Chart names are the uuid seed, so duplicates would collapse
                # into one asset and silently vanish from a dashboard.
                raise SystemExit(f"duplicate chart name: {key!r}")
            seen.add(key)
            files[f"{BUNDLE}/charts/{slug(c['name'])}.yaml"] = chart_yaml(c, ds_uuids)

        # Native filters: offer the dimension each dashboard actually slices by.
        nf = []
        if any(c["dataset"] == FARMER for c in charts):
            nf.append(("geo_2", "Region", ds_uuids[FARMER]))
            nf.append(("gender", "Gender", ds_uuids[FARMER]))
        elif any(c["dataset"] == LAND for c in charts):
            nf.append(("geo_2", "Region", ds_uuids[LAND]))
        elif any(c["dataset"] == CROP for c in charts):
            nf.append(("geo_2", "Region", ds_uuids[CROP]))
        files[f"{BUNDLE}/dashboards/{slug(title)}.yaml"] = dashboard_yaml(title, charts, nf)

    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for path, doc in files.items():
            z.writestr(path, yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))

    n_charts = sum(len(v) for v in charts_by_dash.values())
    print(f"[bundle] {args.out}")
    print(f"[bundle] {len(charts_by_dash)} dashboards, {n_charts} charts, "
          f"{len(ds_uuids)} datasets")
    for t, cs in charts_by_dash.items():
        print(f"    {t:<38} {len(cs):>2} charts")


if __name__ == "__main__":
    main()
