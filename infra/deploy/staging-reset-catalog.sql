-- Read-only catalog of a MineFleet database for staging-reset (#532).
-- One "kind|key|value" line per object, deterministic order, no row content except the
-- digests of the preserved reference tables. Run as the database superuser (RLS bypass is
-- needed for exact counts) inside a READ ONLY transaction.
\set ON_ERROR_STOP on
\pset format unaligned
\pset tuples_only on
\pset pager off
BEGIN TRANSACTION READ ONLY;

WITH ext_objects AS (
  SELECT objid FROM pg_depend WHERE deptype = 'e'
), rels AS (
  SELECT c.oid, n.nspname, c.relname, c.relkind, c.relispartition, c.relrowsecurity,
         c.relforcerowsecurity, pg_get_userbyid(c.relowner) AS owner, c.relacl
    FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
   WHERE n.nspname IN ('public', 'app') AND c.relkind IN ('r', 'p', 'v', 'm', 'S')
)
SELECT regexp_replace(line, '\s+', ' ', 'g') FROM (
  SELECT 'ext|' || extname || '|' || extversion AS line FROM pg_extension
  UNION ALL
  SELECT 'role|' || rolname || '|super=' || rolsuper || ',bypassrls=' || rolbypassrls
         || ',login=' || rolcanlogin || ',inherit=' || rolinherit
    FROM pg_roles WHERE rolname IN ('mf_owner', 'mf_app')
  UNION ALL
  SELECT 'schema|' || nspname || '|owner=' || pg_get_userbyid(nspowner) || ',acl=' || coalesce(nspacl::text, '')
    FROM pg_namespace WHERE nspname IN ('public', 'app')
  UNION ALL
  -- audit_event monthly partitions depend on the creation date: reported apart, never compared by name.
  SELECT CASE WHEN r.relispartition THEN 'partition|' ELSE 'rel|' END
         || r.nspname || '.' || r.relname || '|kind=' || r.relkind::text || ',owner=' || r.owner
         || ',rls=' || r.relrowsecurity || ',force=' || r.relforcerowsecurity
         || ',acl=' || coalesce(r.relacl::text, '')
    FROM rels r
  UNION ALL
  SELECT 'col|' || r.nspname || '.' || r.relname || '.' || a.attname || '|'
         || format_type(a.atttypid, a.atttypmod) || ',notnull=' || a.attnotnull
         || ',default=' || coalesce(pg_get_expr(d.adbin, d.adrelid), '')
    FROM rels r JOIN pg_attribute a ON a.attrelid = r.oid AND a.attnum > 0 AND NOT a.attisdropped
    LEFT JOIN pg_attrdef d ON d.adrelid = r.oid AND d.adnum = a.attnum
   WHERE r.relkind IN ('r', 'p', 'v', 'm') AND NOT r.relispartition
  UNION ALL
  SELECT 'con|' || r.nspname || '.' || r.relname || '.' || con.conname || '|' || pg_get_constraintdef(con.oid)
    FROM pg_constraint con JOIN rels r ON r.oid = con.conrelid
   WHERE NOT r.relispartition
  UNION ALL
  SELECT 'idx|' || r.nspname || '.' || r.relname || '.' || i.relname || '|' || pg_get_indexdef(i.oid)
    FROM pg_index x JOIN pg_class i ON i.oid = x.indexrelid JOIN rels r ON r.oid = x.indrelid
   WHERE NOT r.relispartition
  UNION ALL
  SELECT 'trg|' || r.nspname || '.' || r.relname || '.' || t.tgname || '|' || pg_get_triggerdef(t.oid)
         || ',enabled=' || t.tgenabled::text
    FROM pg_trigger t JOIN rels r ON r.oid = t.tgrelid
   WHERE NOT t.tgisinternal AND NOT r.relispartition
  UNION ALL
  SELECT 'pol|' || schemaname || '.' || tablename || '.' || policyname || '|' || cmd || ',roles='
         || array_to_string(roles, ',') || ',permissive=' || permissive
         || ',using=' || coalesce(qual, '') || ',check=' || coalesce(with_check, '')
    FROM pg_policies WHERE schemaname IN ('public', 'app')
  UNION ALL
  SELECT 'seq|' || schemaname || '.' || sequencename || '|' || data_type || ',start=' || start_value
         || ',inc=' || increment_by || ',min=' || min_value || ',max=' || max_value || ',cycle=' || cycle
    FROM pg_sequences WHERE schemaname IN ('public', 'app')
  UNION ALL
  SELECT 'fn|' || n.nspname || '.' || p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')|'
         || md5(pg_get_functiondef(p.oid)) || ',owner=' || pg_get_userbyid(p.proowner)
         || ',acl=' || coalesce(p.proacl::text, '')
    FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
   WHERE n.nspname IN ('public', 'app') AND p.prokind IN ('f', 'p')
     AND p.oid NOT IN (SELECT objid FROM ext_objects)
  UNION ALL
  SELECT 'view|' || r.nspname || '.' || r.relname || '|' || md5(pg_get_viewdef(r.oid))
    FROM rels r WHERE r.relkind IN ('v', 'm')
) catalog
ORDER BY 1;

-- Exact row counts of every table (partition children included, partitioned parents excluded).
SELECT 'rows|' || n.nspname || '.' || c.relname || '|'
       || (xpath('/row/n/text()',
                 query_to_xml(format('SELECT count(*) AS n FROM ONLY %I.%I', n.nspname, c.relname),
                              false, true, '')))[1]::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('public', 'app') AND c.relkind = 'r'
 ORDER BY 1;

-- Rows owned by a tenant other than the platform tenant (must be zero in a reset candidate).
SELECT 'foreign_tenant_rows|' || n.nspname || '.' || c.relname || '|'
       || (xpath('/row/n/text()',
                 query_to_xml(format(
                   'SELECT count(*) AS n FROM ONLY %I.%I WHERE tenant_id IS DISTINCT FROM %L::uuid',
                   n.nspname, c.relname, '00000000-0000-4000-8000-000000000001'), false, true, '')))[1]::text
  FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
 WHERE n.nspname IN ('public', 'app') AND c.relkind = 'r'
   AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id'
                AND a.attnum > 0 AND NOT a.attisdropped)
 ORDER BY 1;

-- Content digests of the preserved reference tables (row text sorted; no values printed).
SELECT 'ref|' || t || '|' || (xpath('/row/d/text()', query_to_xml(format(
         'SELECT count(*) || '':'' || coalesce(md5(string_agg(x::text, E''\n'' ORDER BY x::text)), ''empty'') AS d FROM public.%I x',
         t), false, true, '')))[1]::text
  FROM unnest(ARRAY['alembic_version', 'spatial_ref_sys', 'role', 'role_allowed_scope', 'saas_plan',
                    'license_category_ref', 'vehicle_category_template',
                    'vehicle_category_document_template', 'vehicle_category_template_license']) AS t
 ORDER BY 1;

-- Alembic revision (also covered by the alembic_version digest).
SELECT 'alembic|head|' || version_num FROM public.alembic_version;

-- Platform tenant identity (the bootstrap depends on it).
SELECT 'platform_tenant|' || tenant_id || '|' || code || ',' || kind || ',' || status
  FROM public.tenant WHERE tenant_id = '00000000-0000-4000-8000-000000000001';

ROLLBACK;
