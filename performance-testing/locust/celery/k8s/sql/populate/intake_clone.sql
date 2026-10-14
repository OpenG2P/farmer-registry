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

  DELETE FROM dedup_results_intake_forms_vs_register
  WHERE submission_id LIKE '00000000-0000-4000-' || args.uuid_group || '-%'
     OR submission_id IN (
       SELECT submission_id::text FROM g2p_intake_form_submissions
       WHERE application_reference LIKE args.tag || '-%'
     );

  DELETE FROM dedup_results_intake_forms_vs_intake_forms
  WHERE submission_id LIKE '00000000-0000-4000-' || args.uuid_group || '-%'
     OR candidate_submission_id LIKE '00000000-0000-4000-' || args.uuid_group || '-%'
     OR submission_id IN (
       SELECT submission_id::text FROM g2p_intake_form_submissions
       WHERE application_reference LIKE args.tag || '-%'
     )
     OR candidate_submission_id IN (
       SELECT submission_id::text FROM g2p_intake_form_submissions
       WHERE application_reference LIKE args.tag || '-%'
     );

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

  -- Dedup only needs the three search fields, same as dedup_register.
  -- Copying every column of the template farmer is what makes 40000 rows sit
  -- inside this one statement.
  IF args.tag IN ('PERF-DEDUP-VS-INT', 'PERF-DEDUP-VS-REG') THEN
    INSERT INTO g2p_intake_form_farmers (
      submission_id, internal_record_id, first_name, last_name, birth_date,
      record_name, search_text,
      created_by, created_at, last_approved_at, last_approved_by, record_status
    )
    SELECT
      n.submission_id,
      CASE
        WHEN args.tag = 'PERF-DEDUP-VS-INT' THEN 'perf-int-'
        ELSE 'perf-ifrin-'
      END || lpad(n.n::text, 8, '0'),
      v.first_name,
      v.last_name,
      v.birth_date,
      v.first_name || ' ' || v.last_name,
      v.first_name,
      a.created_by, now(), now(), a.last_approved_by, a.record_status
    FROM perf_new_submissions n
    CROSS JOIN (
      SELECT
        COALESCE(f.created_by, s.created_by) AS created_by,
        COALESCE(f.last_approved_by, f.created_by, s.created_by) AS last_approved_by,
        COALESCE(NULLIF(f.record_status, ''), 'ACTIVE') AS record_status
      FROM g2p_intake_form_farmers f
      JOIN g2p_intake_form_submissions s ON s.submission_id = f.submission_id
      WHERE f.submission_id = template_id
      LIMIT 1
    ) a
    CROSS JOIN LATERAL (
      SELECT
        CASE
          WHEN args.tag = 'PERF-DEDUP-VS-INT' AND n.n <= (least(args.n, 8000) / 2) * 2
            THEN 'q7int7dup7fn' || lpad(((n.n + 1) / 2)::text, 8, '0')
          WHEN args.tag = 'PERF-DEDUP-VS-INT'
            THEN 'q7int7fn' || lpad(n.n::text, 8, '0')
          WHEN n.n <= least(args.n, 4000)
            THEN 'q7ifr7mfn' || lpad(n.n::text, 8, '0')
          ELSE 'q7ifr7fn' || lpad(n.n::text, 8, '0')
        END AS first_name,
        CASE
          WHEN args.tag = 'PERF-DEDUP-VS-INT' AND n.n <= (least(args.n, 8000) / 2) * 2
            THEN 'q7int7dup7ln' || lpad(((n.n + 1) / 2)::text, 8, '0')
          WHEN args.tag = 'PERF-DEDUP-VS-INT'
            THEN 'q7int7ln' || lpad(n.n::text, 8, '0')
          WHEN n.n <= least(args.n, 4000)
            THEN 'q7ifr7mln' || lpad(n.n::text, 8, '0')
          ELSE 'q7ifr7ln' || lpad(n.n::text, 8, '0')
        END AS last_name,
        CASE
          WHEN args.tag = 'PERF-DEDUP-VS-INT' AND n.n <= (least(args.n, 8000) / 2) * 2
            THEN DATE '1600-01-01' + ((n.n + 1) / 2)
          WHEN args.tag = 'PERF-DEDUP-VS-INT'
            THEN DATE '0600-01-01' + n.n
          WHEN n.n <= least(args.n, 4000)
            THEN DATE '1500-01-01' + n.n
          ELSE DATE '0800-01-01' + n.n
        END AS birth_date
    ) v;
  END IF;

  FOREACH tbl IN ARRAY intake_tables LOOP
    IF to_regclass(tbl) IS NULL THEN
      CONTINUE;
    END IF;
    -- Dedup rows were inserted above. Ingest still copies every section.
    IF args.tag IN ('PERF-DEDUP-VS-INT', 'PERF-DEDUP-VS-REG') THEN
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

  -- Ingest copies the template farmer, including a shared short name.
  -- Give each submission its own search fields so a later dedup cannot match the set.
  IF args.tag NOT IN ('PERF-DEDUP-VS-INT', 'PERF-DEDUP-VS-REG') THEN
    UPDATE g2p_intake_form_farmers f
    SET first_name = 'q7iri7fn' || lpad(n.n::text, 8, '0'),
        last_name = 'q7iri7ln' || lpad(n.n::text, 8, '0'),
        birth_date = DATE '0900-01-01' + n.n,
        record_name = 'q7iri7fn' || lpad(n.n::text, 8, '0') || ' ' || 'q7iri7ln' || lpad(n.n::text, 8, '0'),
        search_text = 'q7iri7fn' || lpad(n.n::text, 8, '0')
    FROM perf_new_submissions n
    WHERE f.submission_id = n.submission_id;

    IF EXISTS (
      SELECT 1
      FROM g2p_intake_form_farmers f
      JOIN perf_new_submissions n ON n.submission_id = f.submission_id
      GROUP BY f.first_name, f.last_name, f.birth_date
      HAVING count(DISTINCT f.submission_id) > 1
    ) THEN
      RAISE EXCEPTION 'intake ingest submissions share a dedup name';
    END IF;
  END IF;

  IF args.tag = 'PERF-DEDUP-VS-INT' THEN
    -- 4000 pairs (rows 1-8000). Each pair shares the three dedup fields.
    IF (
      SELECT count(*) FROM (
        SELECT first_name, last_name, birth_date
        FROM g2p_intake_form_farmers
        WHERE submission_id IN (SELECT submission_id FROM perf_new_submissions)
        GROUP BY first_name, last_name, birth_date
        HAVING count(*) = 2
      ) pairs
    ) <> (least(args.n, 8000) / 2)
    OR EXISTS (
      SELECT 1
      FROM g2p_intake_form_farmers
      WHERE submission_id IN (SELECT submission_id FROM perf_new_submissions)
      GROUP BY first_name, last_name, birth_date
      HAVING count(*) > 2
    ) THEN
      RAISE EXCEPTION 'intake-vs-intake pairs must be 1 to 1, got a group larger than 2';
    END IF;
  ELSIF args.tag = 'PERF-DEDUP-VS-REG' THEN
    -- First 4000 intakes each match one new farmer. The other intakes match none.
    DELETE FROM g2p_register_farmers
    WHERE internal_record_id >= 'perf-ifr-'
      AND internal_record_id < 'perf-ifr.';

    DELETE FROM g2p_register_farmers
    WHERE internal_record_id >= 'perf-ifr-b'
      AND internal_record_id < 'perf-ifr-c';

    INSERT INTO g2p_register_farmers (
      internal_record_id, first_name, last_name, birth_date,
      record_name, search_text,
      created_by, created_at, last_approved_at, last_approved_by, record_status
    )
    SELECT
      copies.id_prefix || lpad(src.n::text, 8, '0'),
      src.first_name, src.last_name, src.birth_date,
      src.first_name || ' ' || src.last_name,
      src.first_name,
      a.created_by, now(), now(), a.last_approved_by, a.record_status
    FROM (
      SELECT DISTINCT ON (n.n)
        n.n, f.first_name, f.last_name, f.birth_date
      FROM perf_new_submissions n
      JOIN g2p_intake_form_farmers f ON f.submission_id = n.submission_id
      WHERE n.n <= least(args.n, 4000)
      ORDER BY n.n
    ) src
    CROSS JOIN (VALUES ('perf-ifr-')) AS copies(id_prefix)
    CROSS JOIN (
      SELECT
        COALESCE(f.created_by, s.created_by) AS created_by,
        COALESCE(f.last_approved_by, f.created_by, s.created_by) AS last_approved_by,
        COALESCE(NULLIF(f.record_status, ''), 'ACTIVE') AS record_status
      FROM g2p_intake_form_farmers f
      JOIN g2p_intake_form_submissions s ON s.submission_id = f.submission_id
      WHERE f.submission_id = template_id
      LIMIT 1
    ) a;

    IF (
      SELECT count(*)
      FROM (
        SELECT f.submission_id
        FROM g2p_intake_form_farmers f
        JOIN perf_new_submissions n ON n.submission_id = f.submission_id
        JOIN g2p_register_farmers r
          ON r.first_name = f.first_name
         AND r.last_name = f.last_name
         AND r.birth_date = f.birth_date
         AND r.internal_record_id >= 'perf-ifr-'
         AND r.internal_record_id < 'perf-ifr.'
        WHERE n.n <= least(args.n, 4000)
        GROUP BY f.submission_id
        HAVING count(*) = 1
      ) ok
    ) <> least(args.n, 4000)
    OR EXISTS (
      SELECT 1
      FROM g2p_intake_form_farmers f
      JOIN perf_new_submissions n ON n.submission_id = f.submission_id
      JOIN g2p_register_farmers r
        ON r.first_name = f.first_name
       AND r.last_name = f.last_name
       AND r.birth_date = f.birth_date
       AND r.internal_record_id >= 'perf-ifr-'
       AND r.internal_record_id < 'perf-ifr.'
      WHERE n.n > least(args.n, 4000)
    ) THEN
      RAISE EXCEPTION 'intake-vs-register did not give % intakes exactly 1 farmer', least(args.n, 4000);
    END IF;
  END IF;

  IF (SELECT count(*) FROM g2p_intake_form_submissions
      WHERE application_reference LIKE args.tag || '-%') <> args.n THEN
    RAISE EXCEPTION 'intake populate inserted the wrong number of submissions for %', args.tag;
  END IF;
  RAISE NOTICE '% submissions ready: %', args.tag, args.n;
END $$;

COMMIT;
