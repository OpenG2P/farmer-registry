-- One topic is allowed per register and data model (uix_dr_outgoing_topics).
-- This inserts the missing topic for each register on the farmer data model,
-- then marks that many PENDING. The count cannot exceed the number of registers.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;

INSERT INTO outgoing_topics (
  topic_id, register_id, data_model_id, websub_topic, description, is_active,
  created_at, websub_register_status, websub_register_number_of_attempts
)
SELECT
  'perf-outgest-topic-' || d.register_mnemonic,
  d.register_id,
  t.data_model_id,
  'perf/' || lower(d.register_mnemonic),
  'perf outgest ' || d.register_mnemonic,
  true,
  now(),
  'NOT_APPLICABLE',
  0
FROM g2p_register_definitions d
CROSS JOIN outgoing_templates t
WHERE t.template_id = 'OUT-TMPL-1'
ON CONFLICT ON CONSTRAINT uix_dr_outgoing_topics DO NOTHING;

CREATE TEMP TABLE perf_topics ON COMMIT DROP AS
SELECT topic.topic_id
FROM outgoing_topics topic
JOIN outgoing_templates t ON t.data_model_id = topic.data_model_id
JOIN g2p_register_definitions d ON d.register_id = topic.register_id
WHERE t.template_id = 'OUT-TMPL-1'
  AND topic.websub_topic IS NOT NULL
ORDER BY topic.topic_id
LIMIT :count;

DO $$
DECLARE
  got int;
  available int;
BEGIN
  SELECT count(*) INTO got FROM perf_topics;
  SELECT count(*) INTO available
  FROM outgoing_topics topic
  JOIN g2p_register_definitions d ON d.register_id = topic.register_id
  WHERE topic.data_model_id = (
    SELECT data_model_id FROM outgoing_templates WHERE template_id = 'OUT-TMPL-1'
  );
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION
      'outgest_topic_register can mark % topics. Asked for %. (data_model_id, register_id) is unique, and there are % registers.',
      available, (SELECT n FROM perf_n), available;
  END IF;
END $$;

UPDATE outgoing_topics t
SET websub_register_status = 'PENDING',
    websub_register_number_of_attempts = 0,
    websub_register_latest_error_code = NULL
FROM perf_topics p
WHERE t.topic_id = p.topic_id;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM outgoing_topics t
  JOIN perf_topics p ON p.topic_id = t.topic_id
  WHERE t.websub_register_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'outgest_topic_register updated % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'outgest_topic_register pending rows: %', got;
END $$;

COMMIT;
