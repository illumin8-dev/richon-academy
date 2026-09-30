"""Owner-run, fixed-target PRIVATE portal bootstrap. No external side effects on import.
No live routes, OAuth requests, public IAM, deployment trust expansion or customer writes.
Run through prepare_portal.sh in a clean, pinned checkout; confirm PREPARE explicitly.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit, urlunsplit, quote, unquote, parse_qsl

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
import db
import portal_readiness as readiness
from portal_credentials import create_runtime_role, CredentialLoggingUnsafe

PROJECT = 'richon-academy'
NUMBER = '756298505437'
REGION = 'asia-southeast1'
SERVICE = 'richon-portal'
OLD_SERVICE = 'richon-backend-test'
RUNTIME = 'richon-portal@richon-academy.iam.gserviceaccount.com'
BUILDER = 'richon-build@richon-academy.iam.gserviceaccount.com'
REPOSITORY = 'richon-portal-ci'
DB_SECRET = 'richon-portal-database-url'
MARKER = 'richon-portal-bootstrap-v1'
HOSTS = frozenset({'ep-gentle-night-b3h5xlji.c-4.ap-southeast-1.aws.neon.tech',
                   'ep-gentle-night-b3h5xlji-pooler.c-4.ap-southeast-1.aws.neon.tech'})
BASE = '49bf0346e834a929f5072c5bf2b99d40237fe936'
MIGRATIONS = ('001_pending_orders', '002_auth_foundation', '003_portal_read_models', '007_oauth_handoff')
OFF = {'RICHON_EDGE_ENABLED':'false', 'RICHON_AUTH_ENABLED':'false', 'RICHON_OAUTH_ENABLED':'false',
       'RICHON_PORTAL_ENABLED':'false', 'RICHON_MONTHLY_ENABLED':'false', 'RICHON_MANUAL_ENABLED':'false'}
STAGE = 'preflight'


class Stop(Exception):
    pass


def need(ok, code):
    if not ok:
        raise Stop(code)


def command(args, *, data=None, timeout=120):
    result = subprocess.run(args, input=data, capture_output=True, timeout=timeout, cwd=ROOT)
    if result.returncode:
        # Tool stderr can include secret values or DSNs. Never copy it to a log.
        raise Stop('command_failed')
    return result.stdout.decode('utf-8')


def gc(*args, data=None, timeout=120):
    return command(['gcloud', *args, '--project='+PROJECT, '--quiet'], data=data, timeout=timeout)


def gj(*args):
    return json.loads(gc(*args, '--format=json'))


def private(policy, service):
    need(not any(m in ('allUsers','allAuthenticatedUsers') for b in policy.get('bindings', []) for m in b.get('members', [])), 'public_iam_not_allowed')
    need(service.get('metadata', {}).get('annotations', {}).get('run.googleapis.com/invoker-iam-disabled', 'false') == 'false', 'iam_check_required')


def validate_dsn(value, role):
    need(isinstance(value, str) and not any(c.isspace() for c in value), 'invalid_database_url')
    u = urlsplit(value)
    need(u.scheme in ('postgres','postgresql') and u.hostname in HOSTS and u.port in (None,5432)
         and unquote(u.username or '') == role and bool(u.password) and u.path == '/neondb' and not u.fragment, 'wrong_database_target')
    need(all(k in ('sslmode','channel_binding') for k,v in parse_qsl(u.query, strict_parsing=True)), 'unexpected_database_options')
    return u


def runtime_url(owner, password):
    u = validate_dsn(owner, 'neondb_owner')
    netloc = quote(readiness.ROLE, safe='')+':'+quote(password, safe='')+'@'+u.hostname
    if u.port:
        netloc += ':'+str(u.port)
    return urlunsplit(('postgresql', netloc, '/neondb', u.query, ''))


def enabled_version(secret):
    rows = gj('secrets','versions','list',secret,'--filter=state:ENABLED')
    ids = [r['name'].split('/')[-1] for r in rows if r.get('state') == 'ENABLED']
    need(ids and all(re.fullmatch(r'[1-9][0-9]*', x) for x in ids), 'enabled_secret_version_required')
    return max(ids, key=int)


def access(secret, version):
    return gc('secrets','versions','access',version,'--secret='+secret).strip()


def schema(cur):
    cur.execute("SET LOCAL statement_timeout='20s'")
    cur.execute("SET LOCAL lock_timeout='10s'")
    cur.execute('SELECT pg_advisory_xact_lock(726426,1)')
    cur.execute('SELECT version,checksum FROM richon.schema_migrations')
    recorded = dict(cur.fetchall())
    sqls = {v:(ROOT/'backend/migrations'/ (v+'.sql')).read_bytes() for v in MIGRATIONS}
    hashes = {v:hashlib.sha256(s).hexdigest() for v,s in sqls.items()}
    need(recorded.get(MIGRATIONS[0]) == hashes[MIGRATIONS[0]], 'base_schema_mismatch')
    for version in MIGRATIONS:
        if version in recorded:
            need(recorded[version] == hashes[version], 'schema_checksum_mismatch')
    changed = []
    for version in MIGRATIONS[1:]:
        if version not in recorded:
            cur.execute(sqls[version].decode('utf-8'))
            cur.execute('INSERT INTO richon.schema_migrations(version,checksum) VALUES(%s,%s)', (version, hashes[version]))
            changed.append(version)
    return changed


def grant_runtime(cur, password, conn):
    from psycopg import sql
    role = sql.Identifier(readiness.ROLE)
    cur.execute('SELECT shobj_description(oid,\'pg_authid\') FROM pg_roles WHERE rolname=%s', (readiness.ROLE,))
    existing = cur.fetchone()
    if existing is None:
        # Neon rejects pre-hashed passwords. Bind the original value over the
        # existing verify-full TLS connection, only after checking safe logging.
        need(readiness.ROLE == 'richon_portal_login', 'unexpected_runtime_role')
        try:
            create_runtime_role(cur, password)
        except CredentialLoggingUnsafe:
            raise Stop('credential_logging_not_safe') from None
        cur.execute(sql.SQL('COMMENT ON ROLE {} IS {}').format(role, sql.Literal(MARKER)))
    else:
        need(existing[0] == MARKER, 'unmanaged_database_role')
    cur.execute(sql.SQL('GRANT USAGE ON SCHEMA richon TO {}').format(role))
    for table in readiness.READ:
        cur.execute(sql.SQL('GRANT SELECT ON richon.{} TO {}').format(sql.Identifier(table), role))
    for op, grants in (('INSERT', readiness.INSERT), ('UPDATE', readiness.UPDATE)):
        for table, columns in grants.items():
            cur.execute(sql.SQL('GRANT {} ({}) ON richon.{} TO {}').format(sql.SQL(op), sql.SQL(',').join(map(sql.Identifier, columns)), sql.Identifier(table), role))
    for table in readiness.DELETE:
        cur.execute(sql.SQL('GRANT DELETE ON richon.{} TO {}').format(sql.Identifier(table), role))
    # Neon owner is not SUPERUSER; do not assume it can SET ROLE to a new role.
    readiness.check_role(cur)


def secret_grant(name):
    gc('secrets','add-iam-policy-binding',name,'--member=serviceAccount:'+RUNTIME,'--role=roles/secretmanager.secretAccessor','--condition=None')


def validate_existing(service, policy):
    private(policy, service)
    need(service['metadata'].get('labels', {}).get('managed-by') == MARKER, 'unmanaged_portal_service')
    spec = service['spec']['template']['spec']
    need(spec.get('serviceAccountName') == RUNTIME and len(spec.get('containers',[])) == 1, 'unexpected_portal_runtime')
    env = {r['name']:r for r in spec['containers'][0].get('env',[])}
    need(all(env.get(k,{}).get('value') == v for k,v in OFF.items()), 'active_portal_must_not_be_overwritten')


def setup():
    global STAGE
    need(shutil.which('gcloud') and shutil.which('git'), 'cloud_shell_required')
    need(not os.getenv('DATABASE_URL'), 'unset_shell_database_url_first')
    need(not command(['git','status','--porcelain','--untracked-files=all']).strip(), 'clean_checkout_required')
    command(['git','merge-base','--is-ancestor',BASE,'HEAD'])
    sha = command(['git','rev-parse','HEAD']).strip()
    need(bool(re.fullmatch('[a-f0-9]{40}',sha)), 'invalid_source_commit')
    need(str(gj('projects','describe',PROJECT)['projectNumber']) == NUMBER, 'wrong_project')
    old = gj('run','services','describe',OLD_SERVICE,'--region='+REGION)
    old_policy = gj('run','services','get-iam-policy',OLD_SERVICE,'--region='+REGION)
    private(old_policy, old)
    env = {e['name']:e for e in old['spec']['template']['spec']['containers'][0].get('env',[])}
    ref = env.get('DATABASE_URL',{}).get('valueFrom',{}).get('secretKeyRef',{})
    need(ref.get('name') == 'richon-database-url' and re.fullmatch(r'[1-9][0-9]*',str(ref.get('key',''))), 'existing_db_secret_reference_required')
    gj('iam','service-accounts','describe',BUILDER)
    policy = gj('projects','get-iam-policy',PROJECT)
    private(policy, {})
    need(not any('serviceAccount:'+RUNTIME in b.get('members',[]) for b in policy.get('bindings',[])), 'runtime_project_grants_not_allowed')
    need(any(b.get('role') == 'roles/run.builder' and not b.get('condition') and 'serviceAccount:'+BUILDER in b.get('members',[]) for b in policy.get('bindings',[])), 'existing_build_identity_not_ready')
    svcs = gj('run','services','list','--region='+REGION)
    existing = [s for s in svcs if s.get('metadata',{}).get('name') == SERVICE]
    if existing:
        validate_existing(gj('run','services','describe',SERVICE,'--region='+REGION),gj('run','services','get-iam-policy',SERVICE,'--region='+REGION))
    versions = {s:enabled_version(s) for s in ('richon-kakao-rest-api-key','richon-kakao-client-secret')}
    print('Project: richon-academy / region: asia-southeast1 / NEW private service: richon-portal')
    print('Creates login tables 002/003/007, a restricted DB role, a dedicated runtime identity,')
    print('one DB secret and a portal image repository. Existing order rows are not changed.')
    print('Binds numbered Kakao secret versions without displaying values. No public access,')
    print('Cloudflare changes, OAuth requests, customer imports, or deployment trust changes.')
    print('1 CPU / 512 MiB / min 0 / max 1. Build, image storage and runtime charges may apply.')
    if input('Type PREPARE to perform these changes: ').strip() != 'PREPARE':
        print('Cancelled. No cloud or database changes made.')
        return 0
    STAGE = 'database-target-check'
    owner = access('richon-database-url',str(ref['key']))
    validate_dsn(owner,'neondb_owner')
    with db._connect(owner) as conn:
        conn.read_only = True
        need(conn.execute('SELECT current_database(),current_user').fetchone() == ('neondb','neondb_owner'), 'wrong_connected_database')
        need(conn.execute("SELECT checksum FROM richon.schema_migrations WHERE version='001_pending_orders'").fetchone() == (hashlib.sha256((ROOT/'backend/migrations/001_pending_orders.sql').read_bytes()).hexdigest(),), 'base_schema_mismatch')
        role_exists = conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(readiness.ROLE,)).fetchone() is not None
    STAGE = 'runtime-and-secret'
    accounts = gj('iam','service-accounts','list')
    present = next((a for a in accounts if a.get('email') == RUNTIME),None)
    if present:
        need(present.get('description') == MARKER and not present.get('disabled'), 'unmanaged_runtime_identity')
    else:
        gc('iam','service-accounts','create','richon-portal','--display-name=Richon private portal','--description='+MARKER)
    # No project-wide role is granted to the new runtime.
    records = gj('secrets','list')
    existing_secret = next((s for s in records if s['name'].split('/')[-1] == DB_SECRET), None)
    if existing_secret:
        need(existing_secret.get('labels',{}).get('managed-by') == MARKER, 'unmanaged_portal_secret')
        rows = gj('secrets','versions','list',DB_SECRET,'--filter=state:ENABLED')
        if rows:
            dbversion = enabled_version(DB_SECRET)
            runtime = access(DB_SECRET,dbversion)
            password = unquote(validate_dsn(runtime,readiness.ROLE).password)
        else:
            need(not role_exists, 'database_role_without_secret')
            password=secrets.token_urlsafe(32);runtime=runtime_url(owner,password)
            dbversion=json.loads(gc('secrets','versions','add',DB_SECRET,'--data-file=-','--format=json',data=runtime.encode()))['name'].split('/')[-1]
    else:
        need(not role_exists, 'database_role_without_secret')
        password=secrets.token_urlsafe(32);runtime=runtime_url(owner,password)
        gc('secrets','create',DB_SECRET,'--replication-policy=automatic','--labels=managed-by='+MARKER)
        dbversion=json.loads(gc('secrets','versions','add',DB_SECRET,'--data-file=-','--format=json',data=runtime.encode()))['name'].split('/')[-1]
    if role_exists:
        # Do not rotate or adopt a role whose stored credential no longer matches.
        with db._connect(runtime) as c:
            need(c.execute('SELECT current_user').fetchone() == (readiness.ROLE,), 'runtime_credentials_mismatch')
    STAGE = 'schema-and-minimum-grants'
    with db._connect(owner) as conn:
        with conn.cursor() as cur:
            schema(cur)
            grant_runtime(cur,password,conn)
    with db._connect(runtime) as conn:
        conn.read_only=True
        with conn.cursor() as cur:
            readiness.check_cursor(cur)
    print('PASS: login schema and restricted DB access (existing orders unchanged).')
    for secret in (DB_SECRET, *versions):
        # Retry only bounded IAM propagation for the new service account.
        for attempt in range(6):
            try:
                secret_grant(secret)
                break
            except Stop:
                if attempt == 5: raise
                time.sleep(5)
    STAGE = 'build'
    repos = gj('artifacts','repositories','list','--location='+REGION)
    repo = next((r for r in repos if r['name'].split('/')[-1] == REPOSITORY),None)
    if repo:
        need(repo.get('format')=='DOCKER' and repo.get('labels',{}).get('managed-by')==MARKER,'unmanaged_image_repository')
    else:
        gc('artifacts','repositories','create',REPOSITORY,'--location='+REGION,'--repository-format=docker','--labels=managed-by='+MARKER)
    image=f'{REGION}-docker.pkg.dev/{PROJECT}/{REPOSITORY}/portal:{sha}'
    with tempfile.TemporaryDirectory(prefix='richon-portal-source-') as tmp:
        stage=Path(tmp)/'source';stage.mkdir()
        # Copy only tracked files allowed by the reviewed Dockerfile, never local secrets.
        allow=(ROOT/'backend/Dockerfile.portal.dockerignore').read_text().splitlines()
        paths=['backend/Dockerfile.portal','backend/Dockerfile.portal.dockerignore']
        paths += [s[1:] for s in allow if s.startswith('!backend/') and not s.endswith('/') and '*' not in s]
        for path in paths:
            source=ROOT/path
            need(source.is_file() and not source.is_symlink() and '..' not in Path(path).parts,'unsafe_build_path')
            content=command(['git','show','HEAD:'+path])
            dest=stage/path;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(content)
        config={'steps':[{'name':'gcr.io/cloud-builders/docker','args':['build','--pull','-f','backend/Dockerfile.portal','-t',image,'.']}],
                'images':[image],'timeout':'900s','serviceAccount':f'projects/{PROJECT}/serviceAccounts/{BUILDER}',
                'options':{'logging':'CLOUD_LOGGING_ONLY'}}
        config_path=Path(tmp)/'build.json';config_path.write_text(json.dumps(config))
        result=json.loads(gc('builds','submit',str(stage),'--config='+str(config_path),'--region='+REGION,'--async','--format=json',timeout=180))
        if isinstance(result,list):need(len(result)==1,'unexpected_build_result');result=result[0]
        build_id=result['id'];need(bool(re.fullmatch('[a-f0-9-]{36}',build_id)),'invalid_build_id')
        print('Build ID: '+build_id)
        for _ in range(100):
            build=gj('builds','describe',build_id,'--region='+REGION)
            if build['status']=='SUCCESS':break
            need(build['status'] in ('QUEUED','WORKING','PENDING'),'build_failed')
            time.sleep(10)
        else:raise Stop('build_wait_timeout')
        digest=next((x['digest'] for x in build.get('results',{}).get('images',[]) if x.get('name')==image),None)
        need(bool(re.fullmatch(r'sha256:[a-f0-9]{64}',digest or '')),'build_digest_missing')
    STAGE = 'private-deployment'
    pinned=image.rsplit(':',1)[0]+'@'+digest
    bindings={'DATABASE_URL':DB_SECRET+':'+str(dbversion),'KAKAO_CLIENT_ID':'richon-kakao-rest-api-key:'+versions['richon-kakao-rest-api-key'],
              'KAKAO_CLIENT_SECRET':'richon-kakao-client-secret:'+versions['richon-kakao-client-secret']}
    values={**OFF,'RICHON_BOOTSTRAP_VERIFY':'true','KAKAO_APP_ID':'1585992','RICHON_OAUTH_ORIGIN':'https://richonacademy.com',
            'RICHON_AUTH_ALLOWED_ORIGINS':'https://richonacademy.com'}
    # Never change a running/activated portal on a retry.
    current = gj('run','services','list','--region='+REGION)
    if any(s.get('metadata',{}).get('name') == SERVICE for s in current):
        validate_existing(gj('run','services','describe',SERVICE,'--region='+REGION),gj('run','services','get-iam-policy',SERVICE,'--region='+REGION))
    gc('run','deploy',SERVICE,'--region='+REGION,'--image='+pinned,'--service-account='+RUNTIME,
       '--no-allow-unauthenticated','--cpu=1','--memory=512Mi','--min=0','--max=1','--min-instances=0','--max-instances=1',
       '--concurrency=20','--timeout=60s','--port=8080','--cpu-throttling','--labels=managed-by='+MARKER,
       '--set-env-vars='+','.join(k+'='+v for k,v in values.items()),
       '--set-secrets='+','.join(k+'='+v for k,v in bindings.items()),timeout=600)
    STAGE = 'verify-private-ready'
    svc=gj('run','services','describe',SERVICE,'--region='+REGION)
    validate_existing(svc,gj('run','services','get-iam-policy',SERVICE,'--region='+REGION))
    need(any(c.get('type')=='Ready' and c.get('status')=='True' for c in svc.get('status',{}).get('conditions',[])), 'portal_not_ready')
    need(svc['spec']['template']['spec']['containers'][0]['image']==pinned,'deployed_image_mismatch')
    need(gj('run','services','describe',OLD_SERVICE,'--region='+REGION)['spec']==old['spec'], 'existing_service_changed_externally')
    need(gj('run','services','get-iam-policy',OLD_SERVICE,'--region='+REGION)==old_policy,'existing_service_policy_changed_externally')
    url=svc['status']['url'];u=urlsplit(url)
    need(u.scheme=='https' and u.hostname.startswith('richon-portal-') and u.hostname.endswith('.run.app'), 'unexpected_portal_url')
    print('PORTAL PRIVATE READY')
    print('Service URL: '+url)
    print('Startup verified the actual restricted DB connection. Browser access and login remain blocked.')
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(setup())
    except (Exception,KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, Stop) else type(exc).__name__
        print('STOP: '+STAGE+' / '+code+'. Setup not confirmed. Do not paste secrets.',file=sys.stderr)
        raise SystemExit(1) from None
