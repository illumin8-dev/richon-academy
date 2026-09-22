"""HTTP cookie expiry regressions. Synthetic session values, no external calls."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from http.cookies import SimpleCookie
from zoneinfo import ZoneInfo

import pytest
from fastapi import Response
import auth_core as core
import auth_http as auth


@pytest.mark.parametrize('zone', [
    ZoneInfo('Etc/UTC'), ZoneInfo('UTC'), ZoneInfo('Asia/Seoul'),
    ZoneInfo('Europe/Berlin'), timezone.utc, timezone(timedelta(hours=5, minutes=30)),
])
def test_cookie_expiry_preserves_instant_for_database_timezones(zone):
    expiry = datetime(2030, 1, 1, 12, tzinfo=zone)
    response = Response()
    auth.set_session_cookie(response, core.IssuedSession('A' * 43, expiry))
    cookies = SimpleCookie()
    cookies.load(response.headers['set-cookie'])
    cookie = cookies[auth.COOKIE]
    assert parsedate_to_datetime(cookie['expires']) == expiry
    assert cookie['secure'] and cookie['httponly']
    assert cookie['samesite'] == 'lax' and cookie['path'] == '/'
    assert not cookie['domain']
    assert cookie['max-age'] == str(core.SESSION_SECONDS)
    assert response.headers['cache-control'] == 'no-store'


def test_cookie_rejects_timezone_free_expiry_before_setting_headers():
    response = Response()
    with pytest.raises(ValueError, match='session_expiry_timezone_required'):
        auth.set_session_cookie(response, core.IssuedSession('A' * 43, datetime(2030, 1, 1)))
    assert 'set-cookie' not in response.headers
