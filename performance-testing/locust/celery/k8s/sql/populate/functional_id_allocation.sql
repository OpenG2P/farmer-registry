-- One queue row per real farmer. id_updation_status stays NOT_APPLICABLE
-- so the updation producer does not claim this cohort.

BEGIN;

CREATE TEMP TABLE perf_n ON COMMIT DROP AS SELECT :count::int AS n;


CREATE TEMP TABLE perf_farmers ON COMMIT DROP AS
SELECT f.internal_record_id, d.register_id, f.created_by
FROM g2p_register_farmers f
CROSS JOIN (
  SELECT register_id
  FROM g2p_register_definitions
  WHERE lower(register_mnemonic) = 'farmer'
  LIMIT 1
) d
WHERE f.created_by IS NOT NULL
ORDER BY f.internal_record_id
LIMIT :count;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got FROM perf_farmers;
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION
      'functional_id_allocation needs % farmers in g2p_register_farmers with created_by, found %',
      (SELECT n FROM perf_n), got;
  END IF;
END $$;

DELETE FROM g2p_functional_id_generation_queue
WHERE queue_id LIKE '-perf-func-alloc-%';

INSERT INTO g2p_functional_id_generation_queue (
  queue_id, register_id, internal_record_id,
  id_allocation_status, id_allocation_no_of_attempts,
  id_updation_status, id_updation_no_of_attempts
)
SELECT
  '-perf-func-alloc-' || lpad(row_number() OVER (ORDER BY internal_record_id)::text, 8, '0'),
  register_id,
  internal_record_id,
  'PENDING', 0,
  'NOT_APPLICABLE', 0
FROM perf_farmers;

DO $$
DECLARE
  got int;
BEGIN
  SELECT count(*) INTO got
  FROM g2p_functional_id_generation_queue
  WHERE queue_id LIKE '-perf-func-alloc-%'
    AND id_allocation_status = 'PENDING'
    AND id_updation_status = 'NOT_APPLICABLE';
  IF got <> (SELECT n FROM perf_n) THEN
    RAISE EXCEPTION 'functional_id_allocation inserted % rows, wanted %', got, (SELECT n FROM perf_n);
  END IF;
  RAISE NOTICE 'functional_id_allocation pending rows: %', got;
END $$;

COMMIT;
