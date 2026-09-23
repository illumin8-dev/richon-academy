"""Pure metadata safety tests: no cloud, provider requests, or database calls."""
from copy import deepcopy
from unittest.mock import Mock
import pytest
import portal_readiness as r


def expression(paths=None):
    return "CHECK ((return_to = ANY (ARRAY[" + ', '.join("'"+p+"'::text" for p in sorted(paths or r.RETURN_PATHS)) + "])))"


def record(table, **changes):
    result = dict(name=table+'_return_to_check', validated=True, noinherit=False,
                  definition=expression(), columns=[7], column=7)
    result.update(changes)
    return tuple(result.values())


def test_exact_known_catalog_expression():
    assert r.constraint_paths(expression()) == r.RETURN_PATHS
    cur = Mock(); cur.fetchall.side_effect = [[record('oauth_attempts')], [record('oauth_signups')]]
    r.check_return_paths(cur)
    assert cur.execute.call_count == 2
    for call in cur.execute.call_args_list:
        assert 'pg_constraint' in call.args[0]
        assert 'schema_migrations' not in call.args[0]
        assert call.args[1][0] in ('oauth_attempts', 'oauth_signups')


@pytest.mark.parametrize('changes', [
    {'name':'other'}, {'validated':False}, {'noinherit':True},
    {'definition':expression(r.RETURN_PATHS - {'/'})},
    {'definition':expression(r.RETURN_PATHS | {'/evil'})},
    {'columns':[7, 8]}, {'columns':None}, {'column':8},
])
def test_invalid_catalog_definition_fails_closed(changes):
    cur=Mock();cur.fetchall.return_value=[record('oauth_attempts', **changes)]
    with pytest.raises(ValueError):r.check_return_paths(cur)


@pytest.mark.parametrize('value', [None, '', 'CHECK (true)', expression()+' OR true',
    expression().replace("'/'::text", "' /'::text"),
    expression().replace("'/apply.html'", "'/apply .html'"),
    expression().replace("'/'::text", "'/'::text, '/'::text"),
    expression().replace('::text','::varchar'),
    expression().replace("'/'::text", "concat('/', '')"), 'x'*2049,
])
def test_parser_rejects_nonliteral_broadened_or_oversized_expression(value):
    with pytest.raises(ValueError):r.constraint_paths(value)


@pytest.mark.parametrize('rows', [[], [record('oauth_attempts'), record('oauth_attempts')]])
def test_missing_or_extra_return_checks_refused(rows):
    cur=Mock();cur.fetchall.return_value=deepcopy(rows)
    with pytest.raises(ValueError):r.check_return_paths(cur)


@pytest.mark.parametrize('enabled',[False,True])
def test_only_enabled_oauth_requires_new_constraint_at_startup(monkeypatch,enabled):
    from unittest.mock import MagicMock,Mock
    monkeypatch.setenv('RICHON_OAUTH_ENABLED','true' if enabled else 'false')
    connection=MagicMock();monkeypatch.setattr(r.db,'_connect',lambda _:connection)
    monkeypatch.setattr(r.db,'database_url',lambda:'synthetic')
    role=Mock();paths=Mock();monkeypatch.setattr(r,'check_cursor',role);monkeypatch.setattr(r,'check_return_paths',paths)
    r.verify_database()
    role.assert_called_once();assert paths.call_count==int(enabled)
