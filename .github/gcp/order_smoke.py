"""Bounded HTTP verification on the existing private test service; no deployment.

Only the fixed synthetic course/identities below may be used. Real order reads,
SQL, secret payload reads, PG calls and service configuration writes are absent.
The two idempotency keys are stable: a repeated run cannot create more orders.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import re
from threading import Barrier
import urllib.error
import urllib.request
from uuid import uuid4

from guard import IMAGE_BASE, SERVICE_URL, inspect_service, require

COURSE = 'verify-20260922-4d5529da96f34e299d222a4ac3cd1d63'
TITLE = '[검증전용/판매금지] 주문 저장 테스트'
COHORT = 'synthetic-20260922'
KEY = 'e3bf8332-3eaa-440e-b6be-0eb31a895799'
CONCURRENT_KEY = '5b381f60-7708-4e41-9e38-0668c1b28071'
REVISION = 'richon-backend-test-ci-35671247419-1'
IMAGE = IMAGE_BASE + '@sha256:608204d4a06a6397f28819e3d78d605574533eeb58f69c6698299a66020b426c'
BODY = dict(course_id=COURSE, customer_name='검증전용 가상신청자',
            customer_phone='01000000000', customer_email='order-smoke@example.invalid')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def mode(path: Path) -> str:
    request = json.loads(path.read_text(encoding='utf-8'))
    require(isinstance(request, dict), 'invalid_request')
    operation = request.get('operation')
    require(operation in {'deploy', 'order-smoke'}, 'invalid_operation')
    if operation == 'order-smoke':
        require(request == {'operation': 'order-smoke', 'course_id': COURSE,
                            'allow_synthetic_orders': True}, 'unapproved_fixture')
    else:
        require(request == {'operation': 'deploy'}, 'invalid_deploy_request')
    return operation


def pinned_service(service: dict, policy: dict) -> None:
    inspect_service(service, policy)
    require(service['spec']['template']['spec']['containers'][0]['image'] == IMAGE,
            'unexpected_running_image')
    status = service['status']
    require(status.get('latestReadyRevisionName') == REVISION and
            status.get('latestCreatedRevisionName') == REVISION, 'unexpected_running_revision')
    active = [row for row in status.get('traffic', []) if row.get('percent', 0) > 0]
    require(sum(row['percent'] for row in active) == 100 and
            all(row.get('revisionName') == REVISION for row in active), 'unexpected_traffic')


def request(path: str, token: str, payload=None, key=None):
    require(path in {'/health', '/orders'}, 'unapproved_path')
    headers = {'Accept': 'application/json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    data = None
    if payload is not None:
        require(isinstance(payload, dict) and payload.get('course_id') == COURSE,
                'unapproved_course')
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    if key:
        headers['Idempotency-Key'] = key
    req = urllib.request.Request(SERVICE_URL + path, data=data, headers=headers)
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(req, timeout=45)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        code = response.code
        require(not 300 <= code < 400, 'redirect_refused')
        raw = response.read(8193)
        require(len(raw) <= 8192, 'oversized_response')
        # Never print the raw body: an unexpected server might echo input data.
        if code in {401, 403}:
            return code, None
        require(response.headers.get('Cache-Control') == 'no-store', 'cache_policy_failed')
        return code, json.loads(raw)


def checked_order(result):
    status, body = result
    require(status in {200, 201}, 'order_creation_failed')
    require(isinstance(body, dict) and set(body) == {
        'order_id', 'course_id', 'course_title', 'cohort', 'amount_krw',
        'currency', 'status', 'created_at'}, 'unexpected_order_fields')
    require(bool(re.fullmatch(r'ord_[a-f0-9]{32}', body.get('order_id', ''))), 'invalid_order_id')
    require(body['course_id'] == COURSE and body['course_title'] == TITLE and
            body['cohort'] == COHORT and body['amount_krw'] == 1000 and
            body['currency'] == 'KRW' and body['status'] == 'pending_payment',
            'order_snapshot_mismatch')
    return body


def verify(token: str, send=request):
    require(bool(token), 'missing_token')
    require(send('/health', '')[0] in {401, 403}, 'anonymous_access_not_blocked')
    require(send('/orders', '', BODY, KEY)[0] in {401, 403}, 'anonymous_write_not_blocked')
    require(send('/health', token) == (200, {'status': 'ok'}), 'process_unhealthy')
    first = send('/orders', token, BODY, KEY)
    saved = checked_order(first)
    retry = send('/orders', token, BODY, KEY)
    require(retry[0] == 200 and checked_order(retry) == saved, 'retry_mismatch')
    changed = send('/orders', token, {**BODY, 'customer_name': '다른 가상신청자'}, KEY)
    require(changed == (409, {'detail': 'idempotency_conflict'}), 'conflict_not_rejected')
    for extra in ({'amount_krw': 1}, {'status': 'paid'}):
        require(send('/orders', token, {**BODY, **extra}, str(uuid4())) ==
                (422, {'detail': 'invalid_request'}), 'forged_input_not_rejected')
    incomplete = dict(BODY)
    incomplete.pop('customer_email')
    require(send('/orders', token, incomplete, str(uuid4())) ==
            (422, {'detail': 'invalid_request'}), 'missing_input_not_rejected')
    barrier = Barrier(4)

    def parallel(_):
        barrier.wait(timeout=10)
        return send('/orders', token, BODY, CONCURRENT_KEY)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(parallel, range(4)))
    copies = [checked_order(result) for result in results]
    require(all(item == copies[0] for item in copies), 'concurrent_retry_mismatch')
    require(sum(code == 201 for code, _ in results) <= 1, 'multiple_created_responses')
    require(copies[0]['order_id'] != saved['order_id'], 'different_keys_shared_order')
    # Codes and synthetic order IDs only; no tokens, PII or raw bodies.
    return {'course_id': COURSE, 'sequential_statuses': [first[0], retry[0]],
            'concurrent_statuses': sorted(code for code, _ in results),
            'order_ids': [saved['order_id'], copies[0]['order_id']],
            'checks': ['anonymous_blocked', 'committed_response', 'idempotency',
                       'conflict_409', 'price_and_status_422', 'missing_input_422',
                       'four_concurrent_requests_one_order'],
            'database_readback': 'Must be independently verified through Neon.'}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode-only', action='store_true')
    parser.add_argument('--metadata-only', action='store_true')
    args = parser.parse_args()
    operation = mode(Path('.github/test-deploy.request'))
    if args.mode_only:
        print('operation=' + operation)
        return 0
    require(operation == 'order-smoke', 'not_an_order_verification_request')
    root = Path(os.environ['RUNNER_TEMP'])
    pinned_service(json.loads((root / 'richon-service.json').read_text()),
                   json.loads((root / 'richon-policy.json').read_text()))
    if args.metadata_only:
        print('PASS: expected private test revision; no changes made.')
        return 0
    receipt = verify(os.environ.get('TEST_ID_TOKEN', ''))
    print('PASS: existing private Cloud Run order API checks passed.')
    print(json.dumps(receipt, ensure_ascii=False, sort_keys=True))
    with open(os.environ['GITHUB_STEP_SUMMARY'], 'a', encoding='utf-8') as summary:
        summary.write('## Order HTTP checks PASS\nNo deployment, IAM or schema change. No PG call.\n')
        summary.write('```json\n' + json.dumps(receipt, indent=2, ensure_ascii=False) + '\n```\n')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        # HTTP/driver exception messages or tracebacks may contain credentials.
        print('FAIL: order verification not confirmed; inspect the fixed test fixture and safe job steps.')
        raise SystemExit(1)
