"""Actual catalog rendering and restricted-role check on disposable CI Postgres."""
import os
import pytest
import portal_readiness as r
import login_return_migrate as migration
from test_orders_postgres import postgres
from test_auth_postgres import auth_postgres, guarded_target
from test_portal_bootstrap_postgres import prepared, runtime_password, restricted

pytestmark=pytest.mark.skipif(os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),reason='Requires disposable CI Postgres')


def test_007_is_not_ready_then_008_catalog_checks_under_restricted_role(prepared):
    import psycopg
    with restricted(prepared) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            r.check_cursor(cur)
            with pytest.raises(ValueError, match='return_constraint'):
                r.check_return_paths(cur)
    # Catalog/permission exercise is rolled back, not a production migration.
    with prepared() as conn:
        with conn.transaction():
            conn.execute((migration.DIRECTORY/(migration.VERSION+'.sql')).read_text())
            conn.execute('SET LOCAL ROLE richon_portal_login')
            with conn.cursor() as cur:
                r.check_cursor(cur)
                r.check_return_paths(cur)
            raise psycopg.Rollback()


@pytest.mark.parametrize('mutation', [
    "ALTER TABLE richon.oauth_attempts DROP CONSTRAINT oauth_attempts_return_to_check",
    "ALTER TABLE richon.oauth_attempts ADD CONSTRAINT extra_return CHECK(return_to <> '/')",
    "ALTER TABLE richon.oauth_signups DROP CONSTRAINT oauth_signups_return_to_check; ALTER TABLE richon.oauth_signups ADD CONSTRAINT oauth_signups_return_to_check CHECK(return_to IS NOT NULL)",
])
def test_invalid_or_missing_constraint_cannot_pass_startup(prepared, mutation):
    import psycopg
    with prepared() as conn:
        with conn.transaction():
            conn.execute((migration.DIRECTORY/(migration.VERSION+'.sql')).read_text())
            conn.execute(mutation)
            conn.execute('SET LOCAL ROLE richon_portal_login')
            with conn.cursor() as cur:
                with pytest.raises(ValueError, match='return_constraint'):
                    r.check_return_paths(cur)
            raise psycopg.Rollback()
