-- Approved and FINAL so the ingest worker accepts the row.
-- Both dedup columns are FAILED so the dedup producers stay idle.
\set tag 'PERF-INTAKE-INGEST'
\set dedup_vs_register 'FAILED'
\set dedup_vs_intake 'FAILED'
\set approval 'APPROVED'
\set draft 'FINAL'
\set ingest 'PENDING'
\set uuid_group '8003'
