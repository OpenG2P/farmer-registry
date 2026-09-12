# What db-seed actually does — "seeding" vs configuration

**Status:** review note, 2026-08-06. No code was changed to produce it.
**Scope:** Farmer Registry (`fr`), the `openg2p-registry` platform it extends, and
Master Data Service. NSR shares the same platform machinery, so the findings apply
there too.

**Why this exists.** Everything the install does to the database is currently called
"seeding" — the image is `…-db-seed`, the Job is `fr-db-seed`, the Helm block is
`dbSeed.*`, and the doc page is "Data seeding". But most of what runs is *required
configuration* that must be applied on every install including production. Calling
it seeding makes it sound optional and demo-only, which is the opposite of true.

---

## 1. The six steps, classified

The order and gating live in the **platform's** entrypoint
(`registry-platform/docker/db-seed/entrypoint.sh`); FR inherits it and only supplies
the variant-specific loaders.

| # | Step | Env flag | What it really is | Idempotent? |
|---|---|---|---|---|
| 1 | `meta_data/*.sql` → registry DB | *(always, ungated)* | **Configuration** — register definitions, schemas, UI tabs/sections, themes, languages, message templates, VC views, input mechanisms | mostly (`ON CONFLICT`) |
| 2 | `load_geo_data.py` → **master_data** DB | `LOAD_GEO_DATA` | **Reference-data bootstrap**, written into *another service's* database | yes |
| 2b | `load_attributes_from_mds.py` → registry DB | `LOAD_ATTRIBUTES` | **Copy** of MDS code lists into `g2p_attributes*` — see §2 | yes |
| 2c | `sync_geo_widgets.py` | `SYNC_GEO_WIDGETS` | **Configuration rewrite** — retargets geo dropdowns to the loaded country | yes |
| 3 | `load_sample_data.py` | `LOAD_SAMPLE_DATA` | **Sample data** — genuinely seeding | **no** |
| 4 | `upload_images.py` → MinIO | `LOAD_IMAGES` | Sample data (profile photos) | yes |
| 5 | `upload_templates.py` → MinIO | `LOAD_TEMPLATES` | **Configuration** — Jinja render templates | yes |
| 6 | `awe_meta_data/*.sql` → **AWE** DB | `AWE_DB_SEED_ENABLED` | **Configuration** in another service's DB (approval policy, stages, callback secret) | yes, after the Aug-2026 `ON CONFLICT` fix |

Outside db-seed, later in the same Helm hook chain:

| Weight | Job | Classification |
|---|---|---|
| 11–13 | `sanity-pm-seed`, `sanity-cm-seed`, `sanity-data-seed` | **Test fixtures** (only when `sanity.runE2e=true`; never deleted) |
| 40 | `bulk-sample` | **Bulk data** (100,000 farmers) |
| 45 | `reporting-views` | **Configuration** (views the dashboards read) |
| 50 | `dashboards` | **Configuration** (Superset import) |

**Only steps 3, 4, bulk, and the sanity fixtures are seeding.** Step 1 in particular
is not optional in any environment — the registry cannot function without it.

---

## 2. Finding: attributes are still copied into the registry DB

The working assumption was that, under the new design, *attributes come live from
Master Data and are not written to the registry DB.* Traced end to end, that is
**true for geo but not for attributes.**

Evidence:

* The UI's backend proxy has a switch — `backend?: "default" | "masterdata"`
  (`registry-platform/ui/staff-ui/src/app/api/_lib/backend-proxy.ts:19,65`).
* Of **181** API routes under `ui/staff-ui/src/app/api`, exactly **2** pass
  `backend: "masterdata"`, and both are geo:
  `master-data/get-all-g2p-geo-levels/route.ts` and
  `master-data/geo-level-values/route.ts`.
* `/api/attributes/values/route.ts` — the route every dropdown uses — passes **no**
  `backend`, so it proxies to the **registry's own staff-api**
  (`/attributes/get_attribute_values`), which reads the registry's own
  `g2p_attributes` / `g2p_attribute_values` tables
  (`core/.../models/g2p_attributes.py`).
* `load_attributes_from_mds.py` **writes** those tables:
  `INSERT INTO "public"."g2p_attributes" … ON CONFLICT (attribute_id) DO UPDATE`
  (lines ~206, 220, 264), reading MDS over HTTP
  (`/attributes/get_all_attributes`, `/attributes/get_attribute_values`).
* Its own docstring states the intent: *"each registry copies them into its OWN
  tables at install. After that the registry validates against its own copy and has
  no runtime dependency on MDS — an outage stops installs, not registrations."*

So attributes are **copy-on-install by design**, deliberately trading live accuracy
for independence from an MDS outage.

**Open question.** If the direct-read design is meant to apply to attributes too,
step 2b does not get renamed — it **disappears**, along with the registry's
attribute tables as a source of truth. That decision should be settled *before* any
renaming, because it changes the classification rather than the label.

### Related wrinkle: three overlapping sources for one concept

FR ships four attribute SQL files in `meta_data/lookup-data/`:

```
g2p_attributes.sql              g2p_attributes_defaults.sql
g2p_attribute_values.sql        g2p_attribute_values_defaults.sql
```

Combined with the MDS pack (step 2b), the same code lists can arrive from up to
three places, with the pack winning on conflict. Worth collapsing regardless of the
naming decision.

---

## 3. Suggested vocabulary

| Term | Means | Covers |
|---|---|---|
| **Configuration** (or *initialisation*) | Required on every install; the registry cannot run without it | meta_data SQL, templates, geo-widget sync, AWE policy, reporting views, dashboards |
| **Reference data** | Country/domain code lists and geo hierarchy | geo bootstrap, MDS attribute pack |
| **Sample data** | Demo records; off in production | `load_sample_data`, profile images |
| **Bulk data** | Volume/performance generation; off in production | `generate_fr_bulk_sample` |
| **Test fixtures** | Created by and for the sanity e2e; never deleted | sanity pm/cm/data seed Jobs |

---

## 4. Where the misleading name is baked in

| Surface | Current | Cost to change |
|---|---|---|
| Docker image | `openg2p-farmer-registry-db-seed` | high — platform + FR + NSR + CI |
| Helm hook Job | `fr-db-seed` | high — referenced in docs, runbooks, muscle memory |
| Helm values | `registry.dbSeed.*` | high — breaking for existing releases |
| Env flags | `LOAD_*`, `AWE_DB_SEED_ENABLED` | medium — platform entrypoint + both registries |
| Flag *descriptions* in `questions.yaml` | — | **low** |
| Doc page | "Data seeding" (FR + NSR) | **low** |

The docs and the Rancher question descriptions can be corrected cheaply and deliver
most of the clarity. Renaming the image/Job/values keys is a breaking change across
four repos and should be a deliberate, separate decision.

---

## 5. Recommended next steps

1. **Settle §2** — is attributes-direct-read landed, planned, or geo-only? This
   determines whether step 2b is renamed or removed.
2. **Cheap fixes now** — restructure the FR/NSR "Data seeding" pages around the
   five terms in §3, and reword the `questions.yaml` descriptions so required
   configuration is not presented as optional seeding.
3. **Collapse the three attribute sources** (§2) into one.
4. **Decide separately** whether the image/Job/values rename is worth the breakage.
