-- Copies a real score-compute queue row. The score definition and the
-- linked register record stay the ones already in the database.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_template ON COMMIT DROP AS
SELECT q.*
FROM g2p_score_compute_queue q
JOIN g2p_register_score_definitions d
  ON d.score_definition_id = q.score_definition_id
WHERE q.queue_id NOT LIKE '-perf-%'
  AND q.link_internal_record_id IS NOT NULL
  AND q.contributing_attribute_values IS NOT NULL
ORDER BY q.queue_id
LIMIT 1;

DO $$
BEGIN
  IF (SELECT count(*) FROM perf_template) <> 1 THEN
    RAISE EXCEPTION
      'score_compute needs one existing queue row with a score definition and a link_internal_record_id';
  END IF;
END $$;

DELETE FROM g2p_score_compute_queue
WHERE queue_id LIKE '-perf-score-%';

INSERT INTO g2p_score_compute_queue (
  queue_id, register_id, link_internal_record_id, score_definition_id, score_type,
  change_request_id, submission_id, contributing_attribute_values,
  compute_status, compute_no_of_attempts
)
SELECT
  '-perf-score-' || lpad(g::text, 8, '0'),
  t.register_id, t.link_internal_record_id, t.score_definition_id, t.score_type,
  t.change_request_id, t.submission_id, t.contributing_attribute_values,
  'PENDING', 0
FROM generate_series(1, :count) AS g
CROSS JOIN perf_template t;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_score_compute_queue
  WHERE queue_id LIKE '-perf-score-%' AND compute_status = 'PENDING';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'score_compute inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'score_compute pending rows: %', got;
END $$;

COMMIT;
