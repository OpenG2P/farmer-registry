-- Copies one FINAL submission and its intake-section rows.
-- The template must already have a g2p_intake_form_farmers row, so the person exists.
-- New rows get new submission ids and new internal_record_ids.
-- functional_record_id is left empty because that column is unique.
-- link_internal_record_id is rewritten to the new ids inside this cohort.

BEGIN;

CREATE TEMP TABLE perf_args ON COMMIT DROP AS
SELECT
  :count::int AS n,
  :'tag' AS tag,
  :'dedup_vs_register' AS dedup_vs_register,
  :'dedup_vs_intake' AS dedup_vs_intake,
  :'approval' AS approval,
  :'draft' AS draft,
  :'ingest' AS ingest,
  :'uuid_group' AS uuid_group;

DO $$
DECLARE
  args perf_args%ROWTYPE;
  template_id uuid;
  tbl text;
  src_count int;
  cols text;
  selects text;
  intake_tables text[] := ARRAY[
    'g2p_intake_form_farmers',
    'g2p_intake_form_households',
    'g2p_intake_form_household_members',
    'g2p_intake_form_lands',
    'g2p_intake_form_crops',
    'g2p_intake_form_livestocks',
    'g2p_intake_form_farm_inputs',
    'g2p_intake_form_membership_details'
  ];
BEGIN
  SELECT * INTO args FROM perf_args;
  IF args.n IS NULL OR args.n < 1 THEN
    RAISE EXCEPTION 'count must be a positive integer';
  END IF;

  SELECT s.submission_id INTO template_id
  FROM g2p_intake_form_submissions s
  JOIN g2p_intake_form_farmers f ON f.submission_id = s.submission_id
  WHERE s.draft_status = 'FINAL'
    AND s.created_by IS NOT NULL
    AND s.form_id IS NOT NULL
    AND s.register_id IS NOT NULL
    AND s.application_reference NOT LIKE 'PERF-%'
  ORDER BY s.first_created_at DESC
  LIMIT 1;

  IF template_id IS NULL THEN
    RAISE EXCEPTION
      'intake populate needs one FINAL submission that has a g2p_intake_form_farmers row and a created_by';
  END IF;

  FOREACH tbl IN ARRAY intake_tables LOOP
    IF to_regclass(tbl) IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format(
      'DELETE FROM %I WHERE submission_id IN (
         SELECT submission_id FROM g2p_intake_form_submissions
         WHERE application_reference LIKE %L
       )',
      tbl, args.tag || '-%'
    );
  END LOOP;

  DELETE FROM g2p_intake_form_submissions
  WHERE application_reference LIKE args.tag || '-%';

  CREATE TEMP TABLE perf_new_submissions ON COMMIT DROP AS
  SELECT
    g AS n,
    ('00000000-0000-4000-' || args.uuid_group || '-' || lpad(g::text, 12, '0'))::uuid AS submission_id,
    args.tag || '-' || lpad(g::text, 8, '0') AS application_reference
  FROM generate_series(1, args.n) AS g;

  INSERT INTO g2p_intake_form_submissions (
    submission_id, application_reference, form_id, register_id,
    draft_status, approval_status, approved_by, approved_at, remarks,
    finalized_at, first_created_at, last_updated_at, created_by, submission_source,
    partner_id, register_ingest_process_status, register_ingest_process_attempts,
    number_of_verifications_required, number_of_verifications_done,
    deduplication_status_vs_intake_forms, deduplication_intake_forms_attempts,
    deduplication_status_vs_register, deduplication_register_forms_attempts
  )
  SELECT
    n.submission_id, n.application_reference, s.form_id, s.register_id,
    args.draft, args.approval,
    CASE WHEN args.approval = 'APPROVED' THEN s.created_by ELSE NULL END,
    CASE WHEN args.approval = 'APPROVED' THEN now() ELSE NULL END,
    'celery-perf:' || args.tag,
    now(), now(), now(), s.created_by, s.submission_source,
    s.partner_id, args.ingest, 0,
    s.number_of_verifications_required, s.number_of_verifications_done,
    args.dedup_vs_intake, 0,
    args.dedup_vs_register, 0
  FROM perf_new_submissions n
  CROSS JOIN g2p_intake_form_submissions s
  WHERE s.submission_id = template_id;

  CREATE TEMP TABLE perf_id_map (
    submission_id uuid,
    old_id text,
    new_id text,
    PRIMARY KEY (submission_id, old_id)
  ) ON COMMIT DROP;

  FOREACH tbl IN ARRAY intake_tables LOOP
    IF to_regclass(tbl) IS NULL THEN
      CONTINUE;
    END IF;
    EXECUTE format(
      'SELECT count(*)::int FROM %I WHERE submission_id = %L',
      tbl, template_id
    ) INTO src_count;
    IF src_count = 0 THEN
      CONTINUE;
    END IF;

    -- Unique columns are rewritten per copied row. Nullable unique columns stay
    -- NULL when the template value is NULL, because PostgreSQL allows many NULLs.
    EXECUTE format($q$
      SELECT string_agg(quote_ident(c.column_name), ', ' ORDER BY c.ordinal_position),
             string_agg(
               CASE
                 WHEN c.column_name = 'internal_record_id' THEN 'c.new_id'
                 WHEN c.column_name = 'submission_id' THEN 'c.new_submission_id'
                 WHEN c.column_name = 'functional_record_id' THEN 'NULL'
                 WHEN c.column_name = 'foundational_id'
                   THEN 'CASE WHEN c.foundational_id IS NULL THEN NULL ELSE c.new_id END'
                 WHEN c.column_name = 'application_reference'
                   THEN 'c.new_application_reference || ''-'' || c.new_id'
                 WHEN u.column_name IS NOT NULL
                   THEN format('CASE WHEN c.%%I IS NULL THEN NULL ELSE c.new_id END', c.column_name)
                 ELSE format('c.%%I', c.column_name)
               END,
               ', ' ORDER BY c.ordinal_position
             )
      FROM information_schema.columns c
      LEFT JOIN (
        SELECT DISTINCT a.attname AS column_name
        FROM pg_index i
        JOIN pg_class t ON t.oid = i.indrelid
        JOIN pg_namespace n ON n.oid = t.relnamespace
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY (i.indkey)
        WHERE i.indisunique
          AND n.nspname = 'public'
          AND a.attnum > 0
          AND i.indnkeyatts = 1
          AND t.relname IN (%L, %L)
      ) u ON u.column_name = c.column_name
      WHERE c.table_schema = 'public'
        AND c.table_name = %L
    $q$, tbl, replace(tbl, 'g2p_intake_form_', 'g2p_register_'), tbl)
      INTO cols, selects;

    EXECUTE format(
      'CREATE TEMP TABLE perf_copy ON COMMIT DROP AS
       SELECT n.submission_id AS new_submission_id,
              n.application_reference AS new_application_reference,
              src.internal_record_id AS old_id,
              gen_random_uuid()::text AS new_id,
              src.*
       FROM %I src
       CROSS JOIN perf_new_submissions n
       WHERE src.submission_id = %L',
      tbl, template_id
    );

    INSERT INTO perf_id_map (submission_id, old_id, new_id)
    SELECT new_submission_id, old_id, new_id FROM perf_copy;

    EXECUTE format(
      'INSERT INTO %I (%s) SELECT %s FROM perf_copy c',
      tbl, cols, selects
    );

    DROP TABLE perf_copy;
  END LOOP;

  FOREACH tbl IN ARRAY intake_tables LOOP
    IF to_regclass(tbl) IS NULL THEN
      CONTINUE;
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM information_schema.columns
      WHERE table_schema = 'public' AND table_name = tbl AND column_name = 'link_internal_record_id'
    ) THEN
      CONTINUE;
    END IF;
    EXECUTE format(
      'UPDATE %I dst
       SET link_internal_record_id = m.new_id
       FROM perf_id_map m
       WHERE dst.submission_id = m.submission_id
         AND dst.link_internal_record_id = m.old_id',
      tbl
    );
  END LOOP;

  IF (SELECT count(*) FROM g2p_intake_form_submissions
      WHERE application_reference LIKE args.tag || '-%') <> args.n THEN
    RAISE EXCEPTION 'intake populate inserted the wrong number of submissions for %', args.tag;
  END IF;
  RAISE NOTICE '% submissions ready: %', args.tag, args.n;
END $$;

COMMIT;
