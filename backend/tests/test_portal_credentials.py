"""No live services or credentials. Regression for Neon's plaintext-only API."""
from pathlib import Path
import sys
from unittest.mock import Mock
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'ops'))
import portal_credentials as credentials


SAFE_VALUES = {
    'log_min_messages': 'warning', 'debug_print_parse': 'off',
    'debug_print_rewritten': 'off', 'debug_print_plan': 'off',
    'log_statement': 'none', 'log_min_duration_statement': '-1',
    'log_min_duration_sample': '-1', 'log_transaction_sample_rate': '0',
    'log_min_error_statement': 'panic', 'log_error_verbosity': 'terse',
    'log_parameter_max_length_on_error': '0', 'pg_stat_statements.track': 'top',
    'auto_explain.log_min_duration': None, 'pgaudit.log': None,
}


def cursor(values=None):
    cur = Mock()
    cur.fetchall.return_value = list((SAFE_VALUES if values is None else values).items())
    return cur


def test_password_is_bound_and_never_rendered_into_client_sql(capsys):
    cur = cursor(); password = 'P' * 43
    credentials.create_runtime_role(cur, password)
    calls = cur.execute.call_args_list
    assert len(calls) == 3
    assert calls[-1].args == ('SELECT pg_temp.richon_create_portal_login(%s)', (password,))
    assert all(password not in call.args[0] for call in calls)
    assert 'SECURITY INVOKER' in calls[1].args[0]
    assert 'SECURITY DEFINER' not in calls[1].args[0]
    assert 'CREATE FUNCTION pg_temp.' in calls[1].args[0]
    assert 'NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS' in calls[1].args[0]
    assert 'SET log_' not in calls[1].args[0]
    assert capsys.readouterr().out == '' and capsys.readouterr().err == ''


@pytest.mark.parametrize('name,value', [
    ('log_statement', 'all'), ('log_statement', 'ddl'),
    ('log_min_messages', 'debug1'), ('debug_print_parse', 'on'),
    ('debug_print_rewritten', 'on'), ('debug_print_plan', 'on'),
    ('log_min_duration_statement', '0'), ('log_min_duration_sample', '0'),
    ('log_transaction_sample_rate', '1'), ('log_min_error_statement', 'error'),
    ('log_error_verbosity', 'default'), ('log_parameter_max_length_on_error', '-1'),
    ('pg_stat_statements.track', 'all'), ('auto_explain.log_min_duration', '0'),
    ('pgaudit.log', 'all'),
])
def test_unsafe_logging_fails_before_sending_any_password(name, value):
    cur = cursor({**SAFE_VALUES, name: value})
    with pytest.raises(credentials.CredentialLoggingUnsafe):
        credentials.create_runtime_role(cur, 'P' * 43)
    assert cur.execute.call_count == 1
    assert 'P' * 43 not in str(cur.execute.call_args)


def test_missing_setting_fails_closed():
    settings = dict(SAFE_VALUES); settings.pop('log_statement')
    cur = cursor(settings)
    with pytest.raises(credentials.CredentialLoggingUnsafe):
        credentials.create_runtime_role(cur, 'P' * 43)
    assert cur.execute.call_count == 1


@pytest.mark.parametrize('password', [None, '', 'short', 'x' * 44, "x'" * 22,
                                     'SCRAM-SHA-256$4096:placeholder', 'x' * 42 + '\n'])
def test_invalid_or_hashed_password_never_reaches_sql(password):
    cur = cursor()
    with pytest.raises(ValueError, match='invalid_bootstrap_password'):
        credentials.create_runtime_role(cur, password)
    cur.execute.assert_not_called()


def test_helper_is_created_only_after_guard_passes():
    cur = cursor(); cur.fetchall.side_effect = RuntimeError('synthetic read failure')
    with pytest.raises(RuntimeError):
        credentials.create_runtime_role(cur, 'P' * 43)
    assert cur.execute.call_count == 1


@pytest.mark.parametrize('track', [None, 'none', 'top'])
def test_missing_or_top_level_statement_tracker_is_accepted(track):
    cur = cursor({**SAFE_VALUES, 'pg_stat_statements.track': track})
    credentials.create_runtime_role(cur, 'P' * 43)
    assert cur.execute.call_count == 3
