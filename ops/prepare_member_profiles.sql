-- 리치온 회원정보 저장 공간 준비 / 사용자 승인 2-2 / 2026-09-25
-- Neon SQL Editor: richon-academy / production / neondb / neondb_owner.
-- 기존 회원/주문 행, 서버 설정, 개인정보 수집 버전은 변경하지 않습니다.
-- 아래 전체를 실행하세요. DO 블록 한 문장 안에서 생성/권한/기록을 처리합니다.
-- 검사 실패는 DO 블록의 모든 변경을 롤백합니다. 성공 후 반복 실행하지 마세요.
-- 재실행 시 이미 존재하는 테이블/적용 이력을 덮어쓰지 않고 중단합니다.
-- 런타임 배포용 SQL이 아닙니다. 공개 홈페이지/컨테이너에 포함하지 않습니다.

DO $prepare_profile$
DECLARE
    runtime_oid oid;
    column_info record;
    privilege_name text;
    insert_columns constant text[] := ARRAY[
        'member_id','name','phone','email','age_range','gender',
        'consultation_consent','over14_confirmed','terms_version','privacy_version'];
BEGIN
    PERFORM pg_catalog.set_config('search_path', 'pg_catalog, pg_temp', true);
    PERFORM pg_catalog.set_config('lock_timeout', '5s', true);
    IF current_database() <> 'neondb' OR current_user <> 'neondb_owner' THEN
        RAISE EXCEPTION 'DB009_STOP_WRONG_DATABASE_OR_OWNER';
    END IF;
    IF NOT pg_try_advisory_xact_lock(726426, 1) THEN
        RAISE EXCEPTION 'DB009_STOP_OTHER_MIGRATION_RUNNING';
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_namespace
                   WHERE nspname='richon' AND nspowner=current_user::regrole)
       OR NOT EXISTS (SELECT 1 FROM pg_class
                      WHERE oid=to_regclass('richon.schema_migrations')
                        AND relkind='r' AND relowner=current_user::regrole)
       OR NOT EXISTS (SELECT 1 FROM pg_class
                      WHERE oid=to_regclass('richon.members')
                        AND relkind='r' AND relowner=current_user::regrole) THEN
        RAISE EXCEPTION 'DB009_STOP_BASE_SCHEMA_NOT_OWNED';
    END IF;
    SELECT oid INTO runtime_oid FROM pg_roles
    WHERE rolname='richon_portal_login'
      AND NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole
      AND NOT rolreplication AND NOT rolbypassrls;
    IF runtime_oid IS NULL OR EXISTS (SELECT 1 FROM pg_auth_members WHERE member=runtime_oid) THEN
        RAISE EXCEPTION 'DB009_STOP_RUNTIME_ROLE_NOT_RESTRICTED';
    END IF;
    IF NOT has_schema_privilege(runtime_oid, 'richon', 'USAGE')
       OR has_schema_privilege(runtime_oid, 'richon', 'CREATE')
       OR has_schema_privilege(runtime_oid, 'public', 'CREATE')
       OR has_database_privilege(runtime_oid, current_database(), 'CREATE') THEN
        RAISE EXCEPTION 'DB009_STOP_RUNTIME_SCHEMA_PRIVILEGES';
    END IF;
    IF EXISTS (
        SELECT 1 FROM (VALUES
        ('001_pending_orders', '2ee1de528bca4622667a10edae12159ab4b380270ce05b82b717d03c7d5a1d50'),
        ('002_auth_foundation', '08f556a816d5796b594e3688e5ada0baa3d45991b56e6711ae3c491413e369c5'),
        ('007_oauth_handoff', 'c207ec0e84e70d40c81bca382db40346d3a211445f28375deac623dbce1b9aed'),
        ('008_login_return_paths', 'd5ad120da7e2f0c19fe75c9028f681e4cb12ca44fc06c5dea0c8af30aa538255')
        ) AS expected(version, checksum)
        LEFT JOIN richon.schema_migrations AS actual USING(version)
        WHERE actual.checksum IS DISTINCT FROM expected.checksum
    ) THEN
        RAISE EXCEPTION 'DB009_STOP_DEPENDENCY_CHECKSUM_MISMATCH';
    END IF;
    IF to_regclass('richon.member_profiles') IS NOT NULL
       OR EXISTS (SELECT 1 FROM richon.schema_migrations WHERE version='009_member_profiles') THEN
        RAISE EXCEPTION 'DB009_STOP_ALREADY_PRESENT_CHECK_INSTEAD_OF_REPEATING';
    END IF;
    FOREACH privilege_name IN ARRAY ARRAY['SELECT','INSERT','UPDATE','DELETE','TRUNCATE','TRIGGER','REFERENCES'] LOOP
        IF has_table_privilege(runtime_oid, 'richon.schema_migrations', privilege_name) THEN
            RAISE EXCEPTION 'DB009_STOP_RUNTIME_HAS_MIGRATION_ACCESS';
        END IF;
    END LOOP;

-- BEGIN CANONICAL 009 (bytes between markers match the approved migration)
-- Explicit owner migration only. Never invoked by app startup or auto-deploy.
-- No existing member, order, identity or session rows are rewritten.
CREATE TABLE richon.member_profiles (
 member_id uuid PRIMARY KEY REFERENCES richon.members(member_id),
 name varchar(80) NOT NULL CHECK (length(btrim(name)) > 0),
 phone varchar(16) NOT NULL CHECK (phone ~ '^(01[016789][0-9]{7,8}|\+[1-9][0-9]{7,14})$'),
 email varchar(254) NOT NULL CHECK (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
 age_range varchar(8) CHECK (age_range IN ('14-19','20-29','30-39','40-49','50-59','60-69','70+')),
 gender varchar(8) CHECK (gender IN ('female','male')),
 consultation_consent boolean NOT NULL,
 over14_confirmed boolean NOT NULL CHECK (over14_confirmed),
 terms_version varchar(64) NOT NULL CHECK (terms_version='member-info-v1'),
 privacy_version varchar(64) NOT NULL CHECK (privacy_version='member-info-v1'),
 consented_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CHECK (consultation_consent OR (age_range IS NULL AND gender IS NULL))
);
REVOKE ALL ON richon.member_profiles FROM PUBLIC;
-- No unique contact indexes: shared email/telephone does not imply one identity.
-- END CANONICAL 009

    GRANT SELECT ON richon.member_profiles TO richon_portal_login;
    GRANT INSERT (member_id, name, phone, email, age_range, gender,
                  consultation_consent, over14_confirmed, terms_version, privacy_version)
        ON richon.member_profiles TO richon_portal_login;
    INSERT INTO richon.schema_migrations(version, checksum)
        VALUES ('009_member_profiles', '5372fd5ad06a64e851f1bbc5915b6a9b0d81c328dd6793b73e93c6fa47459238');

    -- Reject unexpected default grants rather than removing another role's access.
    -- These tests occur after all writes; failure rolls everything back.
    IF EXISTS (
        SELECT 1 FROM pg_class t CROSS JOIN LATERAL aclexplode(t.relacl) a
        WHERE t.oid='richon.member_profiles'::regclass AND a.grantee<>t.relowner
          AND (a.grantee<>runtime_oid OR a.privilege_type<>'SELECT' OR a.is_grantable)
    ) OR EXISTS (
        SELECT 1 FROM pg_attribute c
        CROSS JOIN LATERAL aclexplode(c.attacl) a
        WHERE c.attrelid='richon.member_profiles'::regclass AND a.grantee<>current_user::regrole
          AND (a.grantee<>runtime_oid OR a.privilege_type<>'INSERT'
               OR NOT (c.attname=ANY(insert_columns)) OR a.is_grantable)
    ) THEN
        RAISE EXCEPTION 'DB009_STOP_UNEXPECTED_DEFAULT_GRANT';
    END IF;
    IF NOT has_table_privilege(runtime_oid, 'richon.member_profiles', 'SELECT') THEN
        RAISE EXCEPTION 'DB009_STOP_SELECT_NOT_GRANTED';
    END IF;
    FOREACH privilege_name IN ARRAY ARRAY['INSERT','UPDATE','DELETE','TRUNCATE','TRIGGER','REFERENCES','SELECT WITH GRANT OPTION'] LOOP
        IF has_table_privilege(runtime_oid, 'richon.member_profiles', privilege_name) THEN
            RAISE EXCEPTION 'DB009_STOP_EXCESS_TABLE_PRIVILEGE';
        END IF;
    END LOOP;
    FOR column_info IN SELECT attname FROM pg_attribute
        WHERE attrelid='richon.member_profiles'::regclass AND attnum>0 AND NOT attisdropped
    LOOP
        IF has_column_privilege(runtime_oid, 'richon.member_profiles', column_info.attname, 'INSERT')
           IS DISTINCT FROM (column_info.attname=ANY(insert_columns))
           OR NOT has_column_privilege(runtime_oid, 'richon.member_profiles', column_info.attname, 'SELECT')
           OR has_column_privilege(runtime_oid, 'richon.member_profiles', column_info.attname, 'UPDATE')
           OR has_column_privilege(runtime_oid, 'richon.member_profiles', column_info.attname, 'REFERENCES')
           OR has_column_privilege(runtime_oid, 'richon.member_profiles', column_info.attname, 'INSERT WITH GRANT OPTION') THEN
            RAISE EXCEPTION 'DB009_STOP_COLUMN_PRIVILEGE_MISMATCH';
        END IF;
    END LOOP;
END
$prepare_profile$;

-- Read-back only. All six results must be true (t). No customer rows are read.
SELECT
    to_regclass('richon.member_profiles') IS NOT NULL AS profile_table_exists,
    EXISTS (SELECT 1 FROM richon.schema_migrations
            WHERE version='009_member_profiles' AND checksum='5372fd5ad06a64e851f1bbc5915b6a9b0d81c328dd6793b73e93c6fa47459238') AS migration_009_recorded,
    has_table_privilege('richon_portal_login', to_regclass('richon.member_profiles'), 'SELECT') AS runtime_select_ok,
    (SELECT bool_and(has_column_privilege('richon_portal_login', to_regclass('richon.member_profiles'), col, 'INSERT'))
       FROM unnest(ARRAY['member_id','name','phone','email','age_range','gender','consultation_consent',
                         'over14_confirmed','terms_version','privacy_version']) AS names(col)) AS runtime_insert_ok,
    NOT has_any_column_privilege('richon_portal_login', to_regclass('richon.member_profiles'), 'UPDATE') AS runtime_update_blocked,
    NOT has_table_privilege('richon_portal_login', to_regclass('richon.member_profiles'), 'DELETE') AS runtime_delete_blocked;
