# Workload Model

The endpoints below are the **real routes** of the OpenG2P Registry platform
(`registry-platform/apis/...`) that the Farmer Registry exposes. Paths are
relative to each service's API root; all are POST JSON unless noted (the
platform uses POST action-style endpoints under a base path, e.g.
`/register-data/search_in_a_register`).

## Register mnemonics under test (Farmer Registry)

- **Registers:** `Farmer`, `Household`, `HouseholdMember`
- **Supporting tables:** `Land`, `Crop`, `Livestock`, `FarmInputs`,
  `MembershipDetails`, `PovertyScore`
- Each register/table has a `*_history` twin (every edit writes a snapshot).

## Endpoint catalogue

### staff-portal-api — reads

| Endpoint (base `/register-data`) | Class | Notes |
|---|---|---|
| `search_in_a_register` | Search | Paginated; the dominant read; exercise text + attribute filters. |
| `get_subject_record` | Record read | Fetch one record by id. |
| `get_section_records` / `get_tab_records` | Record read | Section/tab materialisation. |
| `get_record_history` / `get_number_of_versions` / `get_version_dates` / `get_versions_for_a_date` | Record read | Version/history reads (join `*_history`). |
| `get_deduplication_register_results` / `get_deduplication_change_request_results` | Dedup | `pg_trgm` fuzzy — DB CPU/IO heavy. |
| `get_schema_definition_for_register_section` | Metadata read | Cacheable. |
| Metadata controllers: schemas, attributes, tabs, sections, data-models, registry-config, themes, languages | Metadata read | Mostly static/cacheable; light. |

### staff-portal-api — writes

| Endpoint | Class | Notes |
|---|---|---|
| `/intake-form-data/save_intake_form_submission` | Write (intake) | INSERT route into a register. |
| `/intake-form-data/finalize_intake_form_submission` | Write (intake) | Commits the record + history. |
| `/intake-form-data/approve_intake_form_submission` / `reject_…` | Write (intake) | Workflow transitions. |
| `/intake-form-data/search_in_intake_form_submissions` | Search | |
| `/change-requests/create_change_request` | Write (CR) | EDIT route; writes record + `*_history`. |
| `/change-requests/approve_change_request` / `reject_…` | Write (CR) | May trigger AWE approval + webhook. |
| `/verifications/add_verification` | Write (verif) | |
| `/documents/upload_documents` | Write (doc) | Streams to MinIO. |
| `/documents/get_file_url` | Read (doc) | Pre-signed URL generation. |
| `/register-data/get_scores` / `get_score_history` | Record read | Domain scores (PMT etc.). |

### partner-api — ingestion & DCI

| Endpoint | Class | Notes |
|---|---|---|
| `/partner/ingest_data` | **Async ingestion** | Accepts payload, enqueues to Celery; measure as throughput. |
| `/sync/search` , `/dci/registry` | Search (DCI) | Standards-compliant partner search. |

### Async pipelines (Celery — throughput, not latency)

- **Ingestion** — partner/bulk records → validation → enrichment → register write.
- **Outgestion** — event publishing / outbound templates (WebSub/DCI).
- **Deduplication** — `pg_trgm`-based candidate matching over the register.
- **Score computation** — PMT/poverty scores.

Measured by: records/sec, end-to-end latency, Redis queue depth, worker
CPU/mem, and backlog-drain time — **not** RPS/p95.

## Why writes are heavier than a naive CRUD

A single logical "create"/"edit" in this platform typically does **more than one
table write**:
- a `*_history` snapshot row in addition to the live row (change-management),
- a change-request / intake workflow transition,
- an **audit-log** emission (non-blocking middleware → audit-manager),
- possibly an **AWE** approval webhook round-trip.

Size write-path expectations accordingly; don't model them as single-row inserts.

## Blended workload mix (proposed)

Registries are **read-heavy with write bursts**. Start from this mix for the
blended capacity + soak runs, then adjust to the customer's real ratios if known:

| Bucket | Share | Composition |
|---|--:|---|
| Reads | **70%** | 55% search (`search_in_a_register`), 30% record read (`get_subject_record` / sections / tabs), 15% dedup + metadata |
| Writes | **20%** | 50% intake save/finalize, 35% change-request create/approve, 15% verification/document |
| DCI / partner search | **10%** | `sync/search` / `dci/registry` |

Async ingestion runs as a **separate** throughput scenario (Phase 5), optionally
overlaid at a fixed background rate during a blended run to measure contention.

## Notes for the load script

- **Auth:** acquire an OIDC token once per simulated user via Keycloak password
  grant against the release's `staff` realm client, cache it, refresh on expiry.
  See [`locust/`](locust/). Do not fetch a token per request (you'd benchmark
  Keycloak, not the registry).
- **Data realism:** search terms and record ids must hit the **seeded** data
  (random ids across the full id space) so reads aren't all cache hits on a hot
  row. Parameterise from a seed manifest (see [`04-data-seeding.md`](04-data-seeding.md)).
- **Write idempotency / growth:** write tasks grow the DB during the run; either
  pre-size for it or measure write throughput in a bounded window and account
  for table growth in interpretation.
