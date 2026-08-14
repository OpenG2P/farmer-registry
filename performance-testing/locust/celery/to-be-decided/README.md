# Celery / async-pipeline test tooling — deferred

Explicitly out of scope while the API-tier (`locust/api/`) Volume-Tier ×
Pod-Scale matrix is the focus — see
[`../../documentation/test-scenarios.md`](../../documentation/test-scenarios.md)
§1/§2. Revisit once that's done.

When it's picked back up: measuring `partner-api /partner/ingest_data`
throughput needs records/sec, Redis queue depth, worker CPU/mem, and
backlog-drain time — none of that is Locust-request-latency shaped the way
the API Steps are, so it likely isn't a Locust script at all (or only partly
one, for the submission step). Design the template shape fresh at that
point rather than reusing the API-tier CSVs as-is.
