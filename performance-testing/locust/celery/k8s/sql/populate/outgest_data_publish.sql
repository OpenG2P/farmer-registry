-- Builds a publish backlog from the farmer outgoing template and one real farmer.
-- transformation_status is PROCESSED and a transformed payload is already stored,
-- so only the publish producer claims these rows.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

INSERT INTO outgoing_topics (
  topic_id, register_id, data_model_id, websub_topic, description, is_active,
  created_at, websub_register_status, websub_register_number_of_attempts
)
SELECT
  'perf-outgest-topic-farmer',
  t.register_id,
  t.data_model_id,
  'perf/farmer',
  'perf outgest farmer',
  true,
  now(),
  'NOT_APPLICABLE',
  0
FROM outgoing_templates t
WHERE t.template_id = 'OUT-TMPL-1'
ON CONFLICT ON CONSTRAINT uix_dr_outgoing_topics DO NOTHING;

CREATE TEMP TABLE perf_source ON COMMIT DROP AS
SELECT
  f.internal_record_id,
  f.created_by AS changed_by,
  t.register_id,
  t.data_model_id,
  topic.topic_id
FROM outgoing_templates t
JOIN outgoing_topics topic
  ON topic.register_id = t.register_id
 AND topic.data_model_id = t.data_model_id
JOIN LATERAL (
  SELECT internal_record_id, created_by
  FROM g2p_register_farmers
  WHERE created_by IS NOT NULL
  LIMIT 1
) f ON true
WHERE t.template_id = 'OUT-TMPL-1'
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_source) <> 1 THEN
    RAISE EXCEPTION
      'outgest_data_publish needs outgoing template OUT-TMPL-1 and one farmer with created_by';
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
  NULL, NULL,
  '{"first_name":"Perf","last_name":"Farmer","foundational_id":"PERF","gender":"MALE","language_spoken":"","land":[],"machinery":[]}'::jsonb,
  NULL,
  '{"first_name":"Perf","last_name":"Farmer","foundational_id":"PERF","gender":"MALE","language_spoken":"","land":[],"machinery":[]}'
FROM generate_series(1, :count) AS g;

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
  NULL, NULL,
  s.internal_record_id, s.register_id, s.data_model_id, s.topic_id, now(),
  s.changed_by, now(), NULL, NULL, NULL,
  'PROCESSED', 1,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_source s;

INSERT INTO outgoing_transformed_data_payloads (
  outgest_id, payload_id, change_request_id, intake_form_submission_id,
  transformed_data_json, transformed_data_xml
)
SELECT
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  '-perf-outgest-pub-' || lpad(g::text, 8, '0'),
  NULL, NULL,
  '{"farmer_personal_details":{"demographic_info":{"name":{"given_name":"Perf"}}}}'::jsonb,
  NULL
FROM generate_series(1, :count) AS g;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM outgoing_raw_data o
  JOIN outgoing_transformed_data_payloads x ON x.outgest_id = o.outgest_id
  WHERE o.outgest_id LIKE '-perf-outgest-pub-%'
    AND o.publish_status = 'PENDING'
    AND o.transformation_status = 'PROCESSED'
    AND x.transformed_data_json IS NOT NULL;
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'outgest_data_publish inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'outgest_data_publish pending rows: %', got;
END $$;

COMMIT;
