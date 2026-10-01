-- Copies a real outgest row, its raw payload, and its transformed payload.
-- transformation_status is PROCESSED, so only the publish producer claims it.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT o.*
FROM outgoing_raw_data o
JOIN outgoing_raw_data_payloads p ON p.payload_id = o.payload_id
JOIN outgoing_transformed_data_payloads x ON x.outgest_id = o.outgest_id
JOIN outgoing_topics topic ON topic.topic_id = o.topic_id
JOIN g2p_register_farmers f ON f.internal_record_id = o.internal_record_id
WHERE o.outgest_id NOT LIKE '-perf-%'
  AND o.changed_by IS NOT NULL
  AND x.transformed_data_json IS NOT NULL
ORDER BY o.created_at DESC
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'outgest_data_publish needs one outgest row with raw and transformed payloads, a real topic, and a real farmer internal_record_id';
  END IF;
END $$;

DELETE FROM outgoing_transformed_data_payloads
WHERE outgest_id LIKE '-perf-outgest-pub-%';

DELETE FROM outgoing_raw_data
WHERE outgest_id LIKE '-perf-outgest-pub-%';

DELETE FROM outgoing_raw_data_payloads
WHERE payload_id LIKE '-perf-outgest-pub-%';

INSERT INTO outgoing_raw_data_payloads (
  payload_id, change_request_id, intake_form_submission_id,
  raw_data_json, raw_data_xml, raw_data_text
)
SELECT
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  p.change_request_id, p.intake_form_submission_id,
  p.raw_data_json, p.raw_data_xml, p.raw_data_text
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN outgoing_raw_data_payloads p ON p.payload_id = t.payload_id;

INSERT INTO outgoing_raw_data (
  outgest_id, payload_id, change_request_id, intake_form_submission_id,
  internal_record_id, register_id, data_model_id, topic_id, created_at,
  changed_by, changed_at, approved_by, approved_at, changed_by_partner_id,
  transformation_status, transformation_number_of_attempts,
  publish_status, publish_number_of_attempts
)
SELECT
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  t.change_request_id, t.intake_form_submission_id,
  t.internal_record_id, t.register_id, t.data_model_id, t.topic_id, now(),
  t.changed_by, t.changed_at, t.approved_by, t.approved_at, t.changed_by_partner_id,
  'PROCESSED', 1,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

INSERT INTO outgoing_transformed_data_payloads (
  outgest_id, payload_id, change_request_id, intake_form_submission_id,
  transformed_data_json, transformed_data_xml
)
SELECT
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  x.change_request_id, x.intake_form_submission_id,
  x.transformed_data_json, x.transformed_data_xml
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t
JOIN outgoing_transformed_data_payloads x ON x.outgest_id = t.outgest_id;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM outgoing_raw_data
  WHERE outgest_id LIKE '-perf-outgest-pub-%'
    AND publish_status = 'PENDING'
    AND transformation_status = 'PROCESSED';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'outgest_data_publish inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'outgest_data_publish pending rows: %', got;
END $$;

COMMIT;
