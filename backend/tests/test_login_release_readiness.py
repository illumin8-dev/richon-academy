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


def test_actual_postgres_varchar_catalog_shape():
    definition="CHECK (((return_to)::text = ANY ((ARRAY["+', '.join("'"+path+"'::character varying" for path in sorted(r.RETURN_PATHS))+"])::text[])))"
    assert r.constraint_paths(definition)==r.RETURN_PATHS
    for bad in (definition+' OR true',definition.replace('::text[]','::varchar[]'),
                definition.replace("'/'::character varying","' /'::character varying")):
        with pytest.raises(ValueError):r.constraint_paths(bad)


@pytest.mark.parametrize(('row','expected'),[
    ((True,False,False),'freeform'),
    ((False,True,True),'legacy'),
    ((True,False,True),'visual'),
])
def test_calendar_rollout_accepts_only_reviewed_grant_profiles(row,expected):
    cur=Mock();cur.fetchone.return_value=row
    assert r.calendar_grant_profile(cur)==expected


@pytest.mark.parametrize('row',[
    (True,True,True),(True,True,False),(False,False,False),(False,False,True),(False,True,False)
])
def test_calendar_rollout_rejects_mixed_or_missing_grant_profile(row):
    cur=Mock();cur.fetchone.return_value=row
    with pytest.raises(ValueError,match='calendar_grant_profile_mismatch'):
        r.calendar_grant_profile(cur)
