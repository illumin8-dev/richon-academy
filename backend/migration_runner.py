"""Shared execution engine for reviewed SQL migrations with standard ledger semantics."""


def apply_standard_migration(
    *,
    db_module,
    directory,
    version,
    dependencies,
    checksum,
    connection_url=None,
    advisory_slot=1,
):
    target=db_module.database_url() if connection_url is None else connection_url
    with db_module._connect(target) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='15s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute(f'SELECT pg_advisory_xact_lock(726426,{advisory_slot})')
            for dependency in dependencies:
                cur.execute(
                    'SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                    (dependency,),
                )
                if cur.fetchone() != (checksum(dependency),):
                    raise ValueError('dependency_mismatch')
            cur.execute(
                'SELECT checksum FROM richon.schema_migrations WHERE version=%s',
                (version,),
            )
            existing=cur.fetchone()
            if existing:
                if existing != (checksum(version),):
                    raise ValueError('migration_mismatch')
                return False
            cur.execute((directory/(version+'.sql')).read_text())
            cur.execute(
                'INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)',
                (version,checksum(version)),
            )
    return True
