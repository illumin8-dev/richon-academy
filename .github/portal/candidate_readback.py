"""Read-only revalidation of the already-staged, owner-approved login candidate.
No new revision, traffic mutation, IAM operation, provider request or secret read.
"""
from copy import deepcopy
import re
import sys
import common as c
import edge_ops as e
import operate as op

CANDIDATE = 'richon-portal-gh-35946050229-1'
SERVING = 'richon-portal-gh-35810692921-1'
SOURCE = 'd0b2c7389b2394de9c6bfd110c3e7933a90d38f5'


def validate_service(svc, policy):
    info = c.inspect(svc, policy, boundary='edge')
    c.need(info['revision'] == CANDIDATE, 'unexpected_candidate_revision')
    c.need(c.traffic(svc) == [(SERVING, 100)], 'serving_traffic_changed')
    rows = svc['status'].get('traffic', [])
    c.need(len(rows) == 2 and sum(bool(r.get('tag')) for r in rows) == 1,
           'unexpected_traffic_rows')
    tagged = [r for r in rows if r.get('tag')]
    c.need(tagged[0].get('tag') == c.TAG and tagged[0].get('revisionName') == CANDIDATE
           and int(tagged[0].get('percent', 0)) == 0, 'candidate_tag_changed')
    c.need(c.candidate_url(svc, CANDIDATE) == e.CANDIDATE, 'candidate_url_changed')
    env = c.environment(svc['spec']['template']['spec']['containers'][0])
    refs = c.naver_references(env, boundary='edge')
    expected = {name: {'name': name, 'valueFrom': {'secretKeyRef': {'name': secret, 'key': version}}}
                for name, (secret, version) in e.NAVER_VERSIONS.items()}
    c.need(refs == expected, 'candidate_naver_references_changed')
    return info


def validate_revision(revision, name, svc, policy):
    meta = revision.get('metadata', {})
    c.need(name in (CANDIDATE, SERVING) and meta.get('name') == name
           and str(meta.get('namespace')) == c.NUMBER
           and meta.get('labels', {}).get('serving.knative.dev/service') == c.SERVICE,
           'revision_identity_mismatch')
    c.need(any(x.get('type') == 'Ready' and x.get('status') == 'True'
               for x in revision.get('status', {}).get('conditions', [])), 'revision_not_ready')
    view = deepcopy(svc)
    view['spec']['template']['spec'] = deepcopy(revision.get('spec', {}))
    view['spec']['template']['metadata']['annotations'] = deepcopy(meta.get('annotations', {}))
    view['status']['latestCreatedRevisionName'] = name
    view['status']['latestReadyRevisionName'] = name
    c.inspect(view, policy, boundary='edge')
    if name == CANDIDATE:
        declared = svc['spec']['template']['spec']
        observed = deepcopy(view['spec']['template']['spec'])
        # Read-only run35950905055 observed service name absent and this
        # immutable revision name portal-1. Cloud Run generates omitted names.
        # Match ONLY that exact one-container pair, not arbitrary names and
        # not before/after deployment configurations. All other fields match.
        if ('name' not in declared['containers'][0]
                and observed['containers'][0].get('name') == 'portal-1'):
            c.need(len(declared['containers']) == len(observed['containers']) == 1,
                   'unexpected_containers')
            for spec in (declared, observed):
                c.need(not spec['containers'][0].get('dependsOn'), 'unexpected_container_dependencies')
            for metadata in (svc['spec']['template'].get('metadata', {}), meta):
                c.need(not metadata.get('annotations', {}).get('run.googleapis.com/container-dependencies'),
                       'unexpected_container_dependencies')
            observed['containers'][0].pop('name')
        if observed != declared:
            from revision_inspection import differences
            for line in differences(svc, view):
                op.summary(line)
        c.need(observed == declared, 'candidate_template_mismatch')
    else:
        refs = c.naver_references(c.environment(view['spec']['template']['spec']['containers'][0]), boundary='edge')
        c.need(not refs, 'rollback_revision_changed')
    return view


def inspect_existing(svc, policy):
    c.need(c.read_request()['operation'] == 'inspect-edge', 'read_only_operation_required')
    info = validate_service(svc, policy)
    revisions = {name: c.gc('run', 'revisions', 'describe', name, '--region=' + c.REGION)
                 for name in (CANDIDATE, SERVING)}
    for name, revision in revisions.items():
        validate_revision(revision, name, svc, policy)
    image = c.gc('artifacts', 'docker', 'images', 'describe', c.IMAGE + ':' + SOURCE)
    digest = image.get('image_summary', {}).get('digest', '')
    c.need(re.fullmatch(r'sha256:[a-f0-9]{64}', digest)
           and info['image'] == c.IMAGE + '@' + digest, 'candidate_source_image_mismatch')
    c.need(e.access_status() == 'signin-gateway-confirmed', 'access_gateway_not_confirmed')
    e.probe_origin(c.URL)
    e.probe_origin(e.CANDIDATE)
    fresh, fresh_policy = e.get_service()
    e.unchanged(svc, policy, fresh, fresh_policy)
    validate_service(fresh, fresh_policy)
    op.summary('EXISTING CANDIDATE VERIFIED: ' + CANDIDATE)
    op.summary('SOURCE IMAGE VERIFIED: ' + SOURCE + ' / ' + digest)
    op.summary('ROLLBACK VERIFIED: ' + SERVING + ' / service URL traffic 100%; candidate tag traffic 0%.')
    op.summary('NAVER REFERENCES: both approved version 1; actual secret payloads not read.')
    op.summary('READ-ONLY: no revision created, traffic update, IAM/DB write or provider login.')
    op.summary('Access gateway observed; owner email policy and real user OAuth still require browser verification.')


def main():
    c.source(live=True)
    c.need(c.read_request()['operation'] == 'inspect-edge', 'read_only_operation_required')
    svc, policy = e.get_service()
    if any(r.get('tag') for r in svc['status'].get('traffic', [])):
        inspect_existing(svc, policy)
    else:
        e.main()


if __name__ == '__main__':
    try:
        main()
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_failure'
        print('STOP: candidate-readback / ' + code + '. No raw responses printed.', file=sys.stderr)
        raise SystemExit(1) from None
