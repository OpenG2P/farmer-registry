# Partner DCI scenarios

The full write-up is [the partner test scenarios](../../../../documentation/partner-api/test-scenarios.md). This file is the run sheet next to the locust file.

Host: `https://partner-farmer-registry.perftest.openg2p.org`

Sync and async use the same three queries. Ingest is `../ingest`.

## Cases that `./run_all.sh` runs

| Tag | Index | Filter |
|---|---|---|
| `btree_fid` | btree unique | `functional_record_id` `$eq` |
| `gin_text` | GIN trigram | `search_text` `$contains` one term from `perf-seed/register_search_terms.txt` |
| `composite` | GIN + GIN + btree | `last_name` `$startsWith`, `first_name` `$startsWith`, `birth_date` `$eq` |

`btree_fid` and `composite` use `perf-seed/partner_search_pool.csv` (10000 real farmers). `gin_text` uses `perf-seed/register_search_terms.txt` (50000 four-letter anchors). `./prepare_dci.sh` rewrites the farmer file and registers the async WebSub topic.

Each user stays on one row. Page size is 10. After the first response, the user opens up to 10 pages of that row in random order, then picks another row.

## Pass

| Mode | Pass |
|---|---|
| sync | HTTP 200 and `header.status` is `succ` |
| async | HTTP 200 and `message.ack_status` is `ACK` |
| ingest | HTTP 200 and `response_header.response_status` is `SUCCESS` |

## Ramp

4 users, then +4 every 30 seconds, up to 100. If a step's successful requests/s do not rise, freeze at the previous user count. Also freeze at 1.85 cores on the partner pod, or when p99 stays over 1000 ms for two windows. Soak 5 minutes.

## Run

```bash
./prepare_dci.sh
./run_case.sh sync btree_fid
./run_case.sh sync gin_text
./run_case.sh sync composite
./run_case.sh async btree_fid
./run_all.sh sync
```

The UI is http://127.0.0.1:8089. `./run_all.sh` has no UI. Ingest:

```bash
cd ../ingest
./run_ingest.sh
```

Ingest keeps gender, marital status, education, income, language, crop, season, livestock, and ownership fixed. Names, dates, ids, and addresses change on every request.
