"""Migration control-flow tests; SQL integration remains in disposable DB CI."""
import hashlib
from unittest.mock import MagicMock
import pytest
import login_return_migrate as migration


def checksum(version):
    return hashlib.sha256((migration.DIRECTORY / (version + '.sql')).read_bytes()).hexdigest()


def connection(monkeypatch, rows):
    conn = MagicMock()
    conn.__enter__.return_value = conn
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.side_effect = rows
    monkeypatch.setattr(migration.db, 'database_url', lambda: 'mock-only')
    monkeypatch.setattr(migration.db, '_connect', lambda _: conn)
    return conn, cur


def ledger_rows(existing=None):
    return [(checksum(v),) for v in migration.DEPENDENCIES] + [existing]


def test_existing_checksum_never_reapplies_ddl(monkeypatch):
    _, cur = connection(monkeypatch, ledger_rows((checksum(migration.VERSION),)))
    assert migration.apply_migration() is False
    assert all('ALTER TABLE' not in str(call.args[0]) for call in cur.execute.call_args_list)


def test_forward_migration_runs_once_in_connection_transaction(monkeypatch):
    conn, cur = connection(monkeypatch, ledger_rows())
    assert migration.apply_migration() is True
    statements = [call.args[0] for call in cur.execute.call_args_list]
    assert sum('ALTER TABLE' in s for s in statements) == 1
    assert statements[-1].startswith('INSERT INTO richon.schema_migrations')
    assert any('pg_advisory_xact_lock' in s for s in statements)
    assert any('lock_timeout' in s for s in statements)
    assert conn.__exit__.call_args.args[0] is None


@pytest.mark.parametrize('index', [0, 1, 2, 3])
def test_bad_dependency_or_own_checksum_blocks_before_ddl(monkeypatch, index):
    rows = ledger_rows((checksum(migration.VERSION),))
    rows[index] = ('wrong-checksum',)
    _, cur = connection(monkeypatch, rows)
    with pytest.raises(ValueError):
        migration.apply_migration()
    assert not any('ALTER TABLE' in str(call.args[0]) for call in cur.execute.call_args_list)


def test_ddl_failure_never_writes_success_ledger(monkeypatch):
    conn, cur = connection(monkeypatch, ledger_rows())
    def execute(statement, *args):
        if 'ALTER TABLE' in statement:
            raise RuntimeError('synthetic rollback')
    cur.execute.side_effect = execute
    with pytest.raises(RuntimeError):
        migration.apply_migration()
    assert not any(str(call.args[0]).startswith('INSERT INTO richon.schema_migrations')
                   for call in cur.execute.call_args_list)
    assert conn.__exit__.call_args.args[0] is RuntimeError
