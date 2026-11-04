CREATE TEMP TABLE celery_case_count (name text, eligible bigint);

DO $$
DECLARE
  r record;
  n bigint;
BEGIN
  FOR r IN SELECT * FROM celery_case_def ORDER BY name LOOP
    BEGIN
      EXECUTE format(
        'SELECT COUNT(*) FROM %I WHERE %I = ''PENDING'' AND (%s)',
        r.table_name, r.col, r.extra
      ) INTO n;
    EXCEPTION
      WHEN undefined_table THEN
        n := NULL;
    END;
    INSERT INTO celery_case_count VALUES (r.name, n);
  END LOOP;
END $$;

SELECT name, eligible
FROM celery_case_count
ORDER BY eligible DESC NULLS LAST, name;
