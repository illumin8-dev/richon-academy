"""Owner-run production preparation for account lifecycle (DB010 + exact runtime grants).

This script is intentionally interactive, fixed to the reviewed Richon production
targets, and never prints database URLs, passwords, secret payloads, or customer
rows. It does NOT deploy Cloud Run and does NOT enable RICHON_ACCOUNT_ENABLED.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import parse_qsl, unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import db
import account_migrate
import member_profile
import portal_readiness as ready

PROJECT = "richon-academy"
PROJECT_NUMBER = "756298505437"
REGION = "asia-southeast1"
OWNER_SERVICE = "richon-backend-test"
PORTAL_SERVICE = "richon-portal"
OWNER_SECRET = "richon-database-url"
RUNTIME_SECRET = "richon-portal-database-url"
OWNER_ROLE = "neondb_owner"
DATABASE = "neondb"
MINIMUM_SOURCE = "38013be54f5584a857c7485d709f00baf632b597"
HOSTS = frozenset({
    "ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech",
    "ep-gentle-night-b3h5xlji-pooler.c-4.ap-southeast-1.aws.neon.tech",
})
CONFIRM = "APPLY_DB010"


class Stop(Exception):
    """Safe fixed error code only."""


def need(value, code):
    if not value:
        raise Stop(code)


def command(args, *, timeout=120):
    result = subprocess.run(args, cwd=ROOT, stdin=subprocess.DEVNULL,
                            capture_output=True, timeout=timeout, check=False)
    if result.returncode:
        raise Stop("command_failed")
    return result.stdout.decode("utf-8").strip()


def gc(*args, timeout=120):
    return command(["gcloud", *args, "--project="+PROJECT, "--quiet"], timeout=timeout)


def gj(*args):
    try:
        value = json.loads(gc(*args, "--format=json"))
    except (ValueError, UnicodeError):
        raise Stop("invalid_cloud_response") from None
    return value


def validate_source():
    need(command(["git","merge-base","--is-ancestor",MINIMUM_SOURCE,"HEAD"]) == "",
         "required_source_not_present")
    need(command(["git","rev-parse","--verify","HEAD"]).strip() != "", "invalid_source")
    # Untracked .venv is intentionally allowed; tracked/staged edits are not.
    diff = subprocess.run(["git","diff","--quiet"], cwd=ROOT).returncode
    staged = subprocess.run(["git","diff","--cached","--quiet"], cwd=ROOT).returncode
    need(diff == 0 and staged == 0, "tracked_checkout_not_clean")
    need((ROOT/"backend/migrations/010_account_lifecycle.sql").is_file(), "db010_missing")
    need((ROOT/"backend/portal_readiness.py").is_file(), "readiness_missing")


def secret_ref(service, expected_name):
    svc = gj("run","services","describe",service,"--region="+REGION)
    env = svc["spec"]["template"]["spec"]["containers"][0].get("env", [])
    refs = [e.get("valueFrom",{}).get("secretKeyRef",{}) for e in env
            if e.get("name") == "DATABASE_URL"]
    need(len(refs) == 1, "database_secret_reference_missing")
    ref = refs[0]
    need(ref.get("name") == expected_name, "unexpected_database_secret")
    version = str(ref.get("key",""))
    need(bool(re.fullmatch(r"[1-9][0-9]*", version)), "numbered_secret_version_required")
    return svc, version


def account_flag(service):
    env = service["spec"]["template"]["spec"]["containers"][0].get("env", [])
    values = [e.get("value","") for e in env if e.get("name") == "RICHON_ACCOUNT_ENABLED"]
    need(len(values) <= 1, "duplicate_account_flag")
    return values[0] if values else ""


def access(name, version):
    return gc("secrets","versions","access",version,"--secret="+name)


def validate_dsn(value, role):
    need(isinstance(value,str) and value and not any(c.isspace() for c in value),
         "invalid_database_url")
    u=urlsplit(value)
    need(u.scheme in ("postgres","postgresql"), "invalid_database_url")
    need(u.hostname in HOSTS and u.port in (None,5432), "wrong_database_host")
    need(unquote(u.username or "") == role and bool(u.password), "wrong_database_role")
    need(u.path == "/"+DATABASE and not u.fragment, "wrong_database_name")
    try:
        pairs=parse_qsl(u.query, strict_parsing=True)
    except ValueError:
        raise Stop("invalid_database_options") from None
    need(all(k in ("sslmode","channel_binding") for k,_ in pairs),
         "unexpected_database_options")
    return u


def dependency_readback(cur):
    for version in account_migrate.DEPENDENCIES:
        cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s",(version,))
        need(cur.fetchone() == (account_migrate.checksum(version),),
             "dependency_mismatch_"+version)


def grant_account(cur):
    from psycopg import sql
    role=sql.Identifier(ready.ROLE)

    for table in ready.ACCOUNT_READ:
        cur.execute(sql.SQL("GRANT SELECT ON richon.{} TO {}").format(
            sql.Identifier(table), role))

    for table,columns in ready.ACCOUNT_INSERT.items():
        cur.execute(sql.SQL("GRANT INSERT ({}) ON richon.{} TO {}").format(
            sql.SQL(",").join(map(sql.Identifier,columns)),
            sql.Identifier(table), role))

    for table,columns in ready.ACCOUNT_UPDATE.items():
        cur.execute(sql.SQL("GRANT UPDATE ({}) ON richon.{} TO {}").format(
            sql.SQL(",").join(map(sql.Identifier,columns)),
            sql.Identifier(table), role))

    for table in ready.ACCOUNT_DELETE:
        cur.execute(sql.SQL("GRANT DELETE ON richon.{} TO {}").format(
            sql.Identifier(table), role))

    cur.execute("SELECT to_regclass('richon.enrollment_learners') IS NOT NULL")
    enrollment = cur.fetchone() == (True,)
    if enrollment:
        cur.execute(sql.SQL(
            "GRANT SELECT (member_id) ON richon.enrollment_learners TO {}"
        ).format(role))
        cur.execute(sql.SQL(
            "GRANT UPDATE (member_id,name,nickname,email,phone) "
            "ON richon.enrollment_learners TO {}"
        ).format(role))
    return enrollment


def apply(owner_url, runtime_url):
    migration=account_migrate.VERSION
    path=account_migrate.DIRECTORY/(migration+".sql")
    checksum=hashlib.sha256(path.read_bytes()).hexdigest()

    # Confirm both credentials and targets BEFORE any write transaction.
    with db._connect(owner_url) as conn:
        conn.read_only=True
        need(conn.execute("SELECT current_database(),current_user").fetchone()
             == (DATABASE,OWNER_ROLE), "wrong_owner_connection")
        dependency_readback(conn.cursor())

    with db._connect(runtime_url) as conn:
        conn.read_only=True
        need(conn.execute("SELECT current_database(),current_user").fetchone()
             == (DATABASE,ready.ROLE), "wrong_runtime_connection")

    changed=False
    enrollment=False

    # Migration + all grants + owner-side exact privilege checks are atomic.
    with db._connect(owner_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='30s'")
            cur.execute("SET LOCAL lock_timeout='10s'")
            cur.execute("SELECT pg_advisory_xact_lock(726426,1)")
            dependency_readback(cur)
            cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s",
                        (migration,))
            old=cur.fetchone()
            if old is None:
                cur.execute(path.read_text())
                cur.execute("INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)",
                            (migration,checksum))
                changed=True
            else:
                need(old == (checksum,), "db010_checksum_mismatch")

            enrollment=grant_account(cur)
            ready.check_role(cur)

    # Independent readback using the actual restricted runtime credential.
    with db._connect(runtime_url) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            cur.execute("SET LOCAL statement_timeout='10s'")
            ready.check_cursor(cur)

    with db._connect(owner_url) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            cur.execute("SELECT checksum FROM richon.schema_migrations WHERE version=%s",
                        (migration,))
            need(cur.fetchone() == (checksum,), "db010_readback_failed")
            cur.execute("""SELECT
                to_regclass('richon.oauth_account_attempts') IS NOT NULL,
                to_regclass('richon.oauth_link_confirmations') IS NOT NULL,
                to_regclass('richon.account_withdrawals') IS NOT NULL,
                to_regclass('richon.provider_unlink_failures') IS NOT NULL,
                to_regclass('richon.retained_order_records') IS NOT NULL""")
            need(cur.fetchone() == (True,True,True,True,True),
                 "db010_tables_missing")
            cur.execute("SELECT to_regclass('richon.manual_learners') IS NOT NULL")
            manual=cur.fetchone() == (True,)

    return changed,enrollment,manual


def main():
    stage="source"
    try:
        validate_source()

        stage="cloud-target"
        project=gj("projects","describe",PROJECT)
        need(str(project.get("projectNumber")) == PROJECT_NUMBER, "wrong_gcp_project")

        owner_service,owner_version=secret_ref(OWNER_SERVICE,OWNER_SECRET)
        portal_service,runtime_version=secret_ref(PORTAL_SERVICE,RUNTIME_SECRET)
        need(account_flag(portal_service) != "true", "account_feature_already_enabled")

        print("TARGET=richon-academy / production Neon / account feature remains OFF")
        print("SOURCE=OK")
        print("SCOPE=DB010 + exact richon_portal_login account grants + readback")
        print("NO_DEPLOY=YES / NO_PROVIDER_CALLS=YES / NO_CUSTOMER_ROW_PRINTS=YES")

        if input("Type "+CONFIRM+" to continue: ").strip() != CONFIRM:
            print("CANCELLED: no database changes made.")
            return 0

        stage="secret-access"
        owner_url=access(OWNER_SECRET,owner_version)
        runtime_url=access(RUNTIME_SECRET,runtime_version)
        validate_dsn(owner_url,OWNER_ROLE)
        validate_dsn(runtime_url,ready.ROLE)

        # The readiness contract for account actions requires the approved profile policy.
        os.environ["RICHON_TERMS_VERSION"]=member_profile.VERSION
        os.environ["RICHON_PRIVACY_VERSION"]=member_profile.VERSION
        os.environ["RICHON_ACCOUNT_ENABLED"]="true"

        stage="database"
        changed,enrollment,manual=apply(owner_url,runtime_url)

        print("DB010="+("APPLIED" if changed else "ALREADY_APPLIED"))
        print("ENROLLMENT_TABLE="+("YES" if enrollment else "NO"))
        print("MANUAL_TABLE="+("YES" if manual else "NO"))
        print("RUNTIME_MINIMUM_PRIVILEGES=PASS")
        print("RUNTIME_READBACK=PASS")
        print("ACCOUNT_FEATURE=OFF")
        print("ACCOUNT_DB_PREP=PASS")
        return 0
    except (Stop,Exception,KeyboardInterrupt) as exc:
        code=str(exc) if isinstance(exc,Stop) else type(exc).__name__
        print("STOP: "+stage+" / "+code+". No secrets printed.",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
