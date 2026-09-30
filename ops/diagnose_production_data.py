"""Read-only production inventory for admin/mypage data-boundary validation.

Owner Cloud Shell only. Prints aggregate counts, never customer/member/order rows,
identifiers, names, contact data, OAuth subjects, cookies, tokens, DSNs or secrets.
No SQL write statement, Cloud Run deployment, IAM change or feature-flag mutation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'ops')]

import prepare_account_lifecycle as base

REQUIRED_FLAGS=(
    'RICHON_ACCOUNT_ENABLED',
    'RICHON_MARKETING_CONSENT_ENABLED',
    'RICHON_COURSE_DOMAIN_ENABLED',
    'RICHON_MONTHLY_ENABLED',
    'RICHON_MANUAL_ENABLED',
)


class Stop(Exception):
    pass


def need(value,code):
    if not value:
        raise Stop(code)


def env_value(service,name):
    values=[item.get('value','') for item in
            service['spec']['template']['spec']['containers'][0].get('env',[])
            if item.get('name')==name]
    need(len(values)<=1,'duplicate_feature_flag')
    return values[0] if values else ''


def validate_source():
    need(subprocess.run(['git','diff','--quiet'],cwd=ROOT).returncode==0
         and subprocess.run(['git','diff','--cached','--quiet'],cwd=ROOT).returncode==0,
         'tracked_checkout_not_clean')
    need((ROOT/'backend/migrations/016_course_entitlements.sql').is_file(),'course_schema_source_missing')
    need((ROOT/'backend/migrations/017_monthly_runtime_hardening.sql').is_file(),'legacy_schema_source_missing')


def ca_bundle():
    import ssl
    candidates=(
        ssl.get_default_verify_paths().cafile,
        '/etc/ssl/certs/ca-certificates.crt',
        '/etc/pki/tls/certs/ca-bundle.crt',
    )
    for value in candidates:
        if value and Path(value).is_file():
            return value
    raise Stop('system_ca_bundle_missing')


def connect(url):
    try:
        import psycopg
    except ImportError:
        raise Stop('psycopg_missing') from None
    return psycopg.connect(
        url,
        connect_timeout=10,
        prepare_threshold=None,
        sslmode='verify-full',
        sslrootcert=ca_bundle(),
    )


def diagnose_connection(url,expected_role,prefix):
    base.validate_dsn(url,expected_role)
    try:
        with connect(url) as conn:
            conn.read_only=True
            row=conn.execute('SELECT current_database(),current_user').fetchone()
            need(row==(base.DATABASE,expected_role),prefix+'_wrong_database_identity')
    except Stop:
        raise
    except Exception as exc:
        raise Stop(base.connection_failure_code(prefix,exc)) from None


def one(cur,statement):
    cur.execute(statement)
    row=cur.fetchone()
    need(row is not None and len(row)==1 and type(row[0]) is int and row[0]>=0,'invalid_count_result')
    return row[0]


def inventory(cur):
    cur.execute('SELECT current_database(),current_user')
    need(cur.fetchone()==(base.DATABASE,base.OWNER_ROLE),'wrong_database_identity')

    cur.execute("""SELECT
        count(*) FILTER(WHERE status='active')::bigint,
        count(*) FILTER(WHERE status='disabled')::bigint,
        count(*) FILTER(WHERE status='withdrawn')::bigint,
        count(*) FILTER(WHERE role='admin' AND status<>'withdrawn')::bigint
        FROM richon.members""")
    member_row=cur.fetchone()
    need(member_row is not None and len(member_row)==4
         and all(type(v) is int and v>=0 for v in member_row),'invalid_member_counts')
    active,disabled,withdrawn,admins=member_row

    cur.execute("""SELECT
        count(*) FILTER(WHERE provider='kakao')::bigint,
        count(*) FILTER(WHERE provider='naver')::bigint
        FROM richon.auth_identities""")
    identity_row=cur.fetchone()
    need(identity_row is not None and len(identity_row)==2
         and all(type(v) is int and v>=0 for v in identity_row),'invalid_identity_counts')
    kakao,naver=identity_row

    cur.execute("""SELECT
        count(*)::bigint,
        count(*) FILTER(WHERE email_enabled AND sms_enabled)::bigint
        FROM richon.member_marketing_consents""")
    marketing_row=cur.fetchone()
    need(marketing_row is not None and len(marketing_row)==2
         and all(type(v) is int and v>=0 for v in marketing_row),'invalid_marketing_counts')
    marketing_rows,marketing_enabled=marketing_row

    cur.execute("""SELECT
        count(*)::bigint,
        count(*) FILTER(WHERE status='pending_payment')::bigint,
        count(*) FILTER(WHERE EXISTS(
            SELECT 1 FROM richon.member_order_links l WHERE l.order_id=o.order_id))::bigint
        FROM richon.orders o""")
    order_row=cur.fetchone()
    need(order_row is not None and len(order_row)==3
         and all(type(v) is int and v>=0 for v in order_row),'invalid_order_counts')
    orders,pending_orders,linked_orders=order_row

    cur.execute("""SELECT
        count(*)::bigint,
        count(*) FILTER(WHERE member_id IS NOT NULL)::bigint
        FROM richon.enrollment_learners""")
    learner_row=cur.fetchone()
    need(learner_row is not None and len(learner_row)==2
         and all(type(v) is int and v>=0 for v in learner_row),'invalid_learner_counts')
    learners,member_linked_learners=learner_row

    cur.execute("""SELECT
        count(*) FILTER(WHERE grant_state='pending')::bigint,
        count(*) FILTER(WHERE grant_state='confirmed')::bigint,
        count(*) FILTER(WHERE grant_state='cancelled')::bigint
        FROM richon.monthly_enrollment_terms""")
    term_row=cur.fetchone()
    need(term_row is not None and len(term_row)==3
         and all(type(v) is int and v>=0 for v in term_row),'invalid_monthly_term_counts')
    term_pending,term_confirmed,term_cancelled=term_row

    cur.execute("""SELECT
        count(*)::bigint,
        count(*) FILTER(WHERE archived_at IS NULL)::bigint,
        count(*) FILTER(WHERE archived_at IS NOT NULL)::bigint
        FROM richon.manual_enrollments""")
    manual_row=cur.fetchone()
    need(manual_row is not None and len(manual_row)==3
         and all(type(v) is int and v>=0 for v in manual_row),'invalid_manual_counts')
    manual_total,manual_active,manual_archived=manual_row

    cur.execute("""SELECT
        count(*) FILTER(WHERE e.status='SCHEDULED')::bigint,
        count(*) FILTER(WHERE e.status='ACTIVE')::bigint,
        count(*) FILTER(WHERE e.status='COMPLETED')::bigint,
        count(*) FILTER(WHERE e.status='CANCELLED')::bigint,
        count(*) FILTER(WHERE e.status='SUSPENDED')::bigint,
        count(*) FILTER(WHERE l.member_id IS NOT NULL)::bigint
        FROM richon.course_enrollments e
        JOIN richon.enrollment_learners l USING(learner_id)""")
    course_row=cur.fetchone()
    need(course_row is not None and len(course_row)==6
         and all(type(v) is int and v>=0 for v in course_row),'invalid_course_enrollment_counts')
    scheduled,course_active,completed,cancelled,suspended,member_linked_course=course_row
    course_enrollments=scheduled+course_active+completed+cancelled+suspended

    result={
        'members':{
            'non_withdrawn':active+disabled,
            'active':active,'disabled':disabled,'withdrawn':withdrawn,
            'admins_non_withdrawn':admins,
            'profiles':one(cur,'SELECT count(*)::bigint FROM richon.member_profiles'),
        },
        'login':{'kakao_identities':kakao,'naver_identities':naver},
        'marketing':{'rows':marketing_rows,'enabled':marketing_enabled},
        'orders':{
            'total':orders,'pending_payment':pending_orders,
            'linked':linked_orders,'unlinked':orders-linked_orders,
        },
        'legacy':{
            'month_rules':one(cur,'SELECT count(*)::bigint FROM richon.course_month_rules'),
            'learners':learners,'member_linked_learners':member_linked_learners,
            'monthly_enrollments':one(cur,'SELECT count(*)::bigint FROM richon.monthly_enrollments'),
            'terms_pending':term_pending,'terms_confirmed':term_confirmed,'terms_cancelled':term_cancelled,
            'manual_learners':one(cur,'SELECT count(*)::bigint FROM richon.manual_learners'),
            'manual_enrollments':manual_total,'manual_active':manual_active,'manual_archived':manual_archived,
            'manual_terms':one(cur,'SELECT count(*)::bigint FROM richon.manual_terms'),
        },
        'course_domain':{
            'programs':one(cur,'SELECT count(*)::bigint FROM richon.course_programs'),
            'runs':one(cur,'SELECT count(*)::bigint FROM richon.course_runs'),
            'sessions':one(cur,'SELECT count(*)::bigint FROM richon.course_sessions'),
            'enrollments':course_enrollments,
            'scheduled':scheduled,'active':course_active,'completed':completed,
            'cancelled':cancelled,'suspended':suspended,
            'member_linked_enrollments':member_linked_course,
        },
    }
    need(result['orders']['unlinked']>=0,'linked_order_count_invalid')
    need(manual_total<=result['legacy']['monthly_enrollments'],'manual_monthly_count_invalid')
    need(member_linked_course<=course_enrollments,'course_member_link_count_invalid')
    return result


def main():
    stage='source'
    owner_url=runtime_url=None
    try:
        validate_source()
        stage='cloud-target'
        project=base.gj('projects','describe',base.PROJECT)
        need(str(project.get('projectNumber'))==base.PROJECT_NUMBER,'wrong_gcp_project')
        _,owner_version=base.secret_ref(base.OWNER_SERVICE,base.OWNER_SECRET)
        portal_service,runtime_version=base.secret_ref(base.PORTAL_SERVICE,base.RUNTIME_SECRET)
        for flag in REQUIRED_FLAGS:
            need(env_value(portal_service,flag)=='true','required_feature_not_enabled_'+flag.lower())

        print('TARGET=richon-academy / production Neon / aggregate read-only inventory')
        print('NO_WRITES=YES / NO_CUSTOMER_ROWS=YES / NO_IDENTIFIERS=YES / NO_SECRET_OUTPUT=YES')

        stage='secret-access'
        owner_url=base.access(base.OWNER_SECRET,owner_version)
        runtime_url=base.access(base.RUNTIME_SECRET,runtime_version)
        owner_target=base.validate_dsn(owner_url,base.OWNER_ROLE)
        runtime_target=base.validate_dsn(runtime_url,'richon_portal_login')
        need(owner_target.hostname.replace('-pooler.','.')==
             runtime_target.hostname.replace('-pooler.','.'),'database_endpoint_mismatch')
        diagnose_connection(owner_url,base.OWNER_ROLE,'owner')
        diagnose_connection(runtime_url,'richon_portal_login','runtime')
        print('TLS_MODE=verify-full / TLS_CA=system-file')

        stage='aggregate-read'
        with connect(owner_url) as conn:
            conn.read_only=True
            with conn.cursor() as cur:
                cur.execute("SET LOCAL statement_timeout='15s'")
                result=inventory(cur)

        print('PRODUCTION_DATA_BOUNDARY=PASS')
        print('COUNTS='+json.dumps(result,sort_keys=True,separators=(',',':')))
        print('DATABASE_CHANGED=NO / CLOUD_CHANGED=NO')
        return 0
    except (Stop,base.Stop,ValueError,Exception,KeyboardInterrupt) as exc:
        if isinstance(exc,(Stop,base.Stop)):
            code=str(exc)
        elif isinstance(exc,ValueError):
            code=str(exc) or 'inventory_validation_failed'
        else:
            code=type(exc).__name__
        print('STOP: '+stage+' / '+code+'. No secrets or customer rows printed.',file=sys.stderr)
        return 1
    finally:
        owner_url=runtime_url=None


if __name__=='__main__':
    raise SystemExit(main())
