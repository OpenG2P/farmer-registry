-- Copies a raw ingest that already classified once, plus its payload.
-- Only classification_status is PENDING. No classified row is created;
-- the worker creates that.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT r.*
FROM incoming_raw_data r
JOIN incoming_raw_data_payloads p ON p.ingest_id = r.ingest_id
JOIN g2p_partners partner ON partner.partner_id = r.partner_id
WHERE r.ingest_id NOT LIKE '-perf-%'
  AND r.classification_status = 'PROCESSED'
  AND r.data_model_id IS NOT NULL
ORDER BY r.receipt_date_time DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'ingest_data_classification needs one PROCESSED incoming_raw_data row with a payload and a real partner_id';
  END IF;
END $$;

DELETE FROM incoming_raw_data_payloads
WHERE ingest_id LIKE '-perf-ingest-class-%';

DELETE FROM incoming_raw_data
WHERE ingest_id LIKE '-perf-ingest-class-%';

INSERT INTO incoming_raw_data (
  ingest_id, partner_id, data_model_id, ingest_message_id, ingest_correlation_id,
  receipt_date_time, classification_status, classification_number_of_attempts
)
SELECT
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  t.partner_id, t.data_model_id,
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  now(), 'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

INSERT INTO incoming_raw_data_payloads (
  ingest_id, raw_data_json, raw_data_xml, raw_data_text
)
SELECT
  '-perf-ingest-class-' || lpad(g::text, 8, '0'),
  p.raw_data_json, p.raw_data_xml, p.raw_data_text
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN incoming_raw_data_payloads p ON p.ingest_id = t.ingest_id;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM incoming_raw_data
  WHERE ingest_id LIKE '-perf-ingest-class-%'
    AND classification_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'ingest_data_classification inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'ingest_data_classification pending rows: %', got;
END $$;

COMMIT;
