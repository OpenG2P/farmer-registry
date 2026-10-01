-- A topic is unique per register and data model, so this does not insert copies.
-- It marks that many existing topics PENDING. The register and data model stay real.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_topics ON COMMIT DROP AS
SELECT t.topic_id
FROM outgoing_topics t
JOIN g2p_register_definitions d ON d.register_id = t.register_id
WHERE t.websub_topic IS NOT NULL
  AND t.data_model_id IS NOT NULL
ORDER BY t.topic_id
LIMIT :count;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got FROM perf_topics;
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION
      'outgest_topic_register needs % existing topics. Found %. A topic cannot be copied because (data_model_id, register_id) is unique.',
      (SELECT n FROM perf_n), got;
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
