"""Retention expiry cleanup against guarded disposable loopback PostgreSQL only."""
from datetime import datetime,timezone
from pathlib import Path
from uuid import uuid4
import os
import sys
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'ops'))
import cleanup_account_retention as cleanup
from test_account_postgres import account_db, registered

pytestmark=pytest.mark.skipif(
    os.getenv('RICHON_EMPTY_TEST_DB')!='YES' or not os.getenv('RICHON_TEST_DATABASE_URL'),
    reason='Requires guarded disposable loopback richon_ci PostgreSQL')


def retained_row(conn,member,order_id,expires):
    conn.execute('''INSERT INTO richon.retained_order_records
        (order_id,member_id,course_id,course_title,cohort,amount_krw,currency,status,
         customer_name,customer_phone,customer_email,order_created_at,expires_at)
        VALUES(%s,%s,'test-course','테스트',NULL,1000,'KRW','pending_payment',
               '보존 이름','01012345678','retain@example.invalid',
               %s-interval '5 years',%s)''',(order_id,member,expires,expires))


def test_cleanup_removes_only_expired_retention_and_safe_failures(account_db):
    _,member=registered()
    expired='ord_'+uuid4().hex;future='ord_'+uuid4().hex
    with account_db() as conn:
        retained_row(conn,member,expired,datetime(2020,1,1,tzinfo=timezone.utc))
        retained_row(conn,member,future,datetime(2099,1,1,tzinfo=timezone.utc))
        conn.execute("""INSERT INTO richon.provider_unlink_failures
            (event_id,member_id,provider,safe_code,expires_at)
            VALUES(%s,%s,'naver','provider_unavailable',CURRENT_TIMESTAMP-interval '1 second'),
                  (%s,%s,'kakao','provider_unavailable',CURRENT_TIMESTAMP+interval '1 day')""",
            (uuid4(),member,uuid4(),member))
    counts=cleanup.cleanup(connection_url=os.environ['RICHON_TEST_DATABASE_URL'])
    assert counts['retained_order_records']==1
    assert counts['provider_unlink_failures']==1
    with account_db() as conn:
        assert conn.execute('SELECT order_id FROM richon.retained_order_records WHERE member_id=%s',(member,)).fetchall()==[(future,)]
        assert conn.execute('SELECT provider FROM richon.provider_unlink_failures WHERE member_id=%s',(member,)).fetchall()==[('kakao',)]
