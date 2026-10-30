# Partner DCI scenarios

The full write-up is [the partner test scenarios](../../../../documentation/partner-api/test-scenarios.md). This file is the run sheet next to the locust file.

Host: `https://partner-farmer-registry.perftest.openg2p.org`

Sync and async use the same queries. Ingest is `../ingest`. `./run_all.sh` runs the three index cases. The query-type cases are started with `./run_case.sh`.

## Cases that `./run_all.sh` runs

| Tag | Index | Filter |
|---|---|---|
| `btree_fid` | btree unique | `functional_record_id` `$eq` |
| `gin_text` | GIN trigram | `search_text` `$contains` one term from `perf-seed/register_search_terms.txt` |
| `composite` | GIN + GIN + btree | `last_name` `$startsWith`, `first_name` `$startsWith`, `birth_date` `$eq` |

## DCI query types

These match `search/dci/queries`: `expression`, `predicate`, `graphql`, `idtype-value`. `gin_text` and `composite` stay in the index table above. They are expression payloads used to hit an index, not a separate query type.

`expression`, `predicate`, and `graphql` filter on `birth_date` only. Each request uses a new farmer and the seven days from that birth date (`birth_date >= day AND birth_date <= day+6`), so the page is not one shared birth date. `idtype-value` cannot express a range, so it looks up `FID`.

| Tag | `query_type` | Filter |
|---|---|---|
| `expression` | `expression` | `birth_date` `$gte` day and `$lte` day+6 |
| `predicate` | `predicate` | `birth_date` `ge` day and `le` day+6 |
| `graphql` | `graphql` | `birth_date: { gte: day, lte: day+6 }` |
| `idtype_value` | `idtype-value` | `FID` equals `functional_record_id` |

`btree_fid` and `composite` use `perf-seed/partner_search_pool.csv` (10000 real farmers). `gin_text` uses `perf-seed/register_search_terms.txt` (50000 four-letter anchors). `./prepare_dci.sh` rewrites the farmer file and registers the async WebSub topic.

Each user stays on one row. Page size is 10. After the first response, the user opens up to 10 pages of that row in random order, then picks another row.

## Pass

| Mode | Pass |
|---|---|
| sync | HTTP 200 and `header.status` is `succ` |
| async | HTTP 200 and `message.ack_status` is `ACK` |
| ingest | HTTP 200 and `response_header.response_status` is `SUCCESS` |

## Ramp

Search starts at 2 users, then +2 every 30 seconds, up to 100. If a step's successful requests/s do not rise, freeze at the previous user count. Also freeze at 1.85 cores on the partner pod, or when p99 stays over 1000 ms for two windows. Soak 5 minutes.

## Run

```bash
./prepare_dci.sh
./run_case.sh sync btree_fid
./run_case.sh sync gin_text
./run_case.sh sync composite
./run_case.sh sync expression
./run_case.sh sync predicate
./run_case.sh sync graphql
./run_case.sh sync idtype_value
./run_case.sh async btree_fid
./run_case.sh async expression
./run_case.sh async predicate
./run_case.sh async graphql
./run_case.sh async idtype_value
./run_all.sh sync
```

The UI is http://127.0.0.1:8089. `./run_all.sh` has no UI. Ingest:

```bash
cd ../ingest
./run_ingest.sh
```

Ingest keeps gender, marital status, education, income, language, crop, season, livestock, and ownership fixed. Names, dates, ids, and addresses change on every request.
