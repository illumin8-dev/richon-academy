"""Read-only inspection when latest-ready differs from the serving revision.
Never print API values, metadata keys supplied by the API, or credential material.
A pending candidate is inspected, never promoted by this module.
"""
from copy import deepcopy
import re
import common as c

NONCE = 'client.knative.dev/nonce'
# Only these fixed field names may be emitted; unknown fields become a count.
SPEC_FIELDS = ('serviceAccountName', 'containerConcurrency', 'timeoutSeconds', 'containers', 'volumes')
ANNOTATIONS = ('autoscaling.knative.dev/minScale', 'autoscaling.knative.dev/maxScale',
               'run.googleapis.com/client-name', 'run.googleapis.com/client-version',
               'run.googleapis.com/cpu-throttling', 'run.googleapis.com/startup-cpu-boost')
CONTAINER_FIELDS = ('name', 'image', 'env', 'ports', 'resources', 'startupProbe', 'livenessProbe',
                    'command', 'args', 'volumeMounts', 'dependsOn', 'workingDir')


def serving_view(svc, policy, revision):
    traffic = c.traffic(svc)
    c.need(len(traffic) == 1 and traffic[0][1] == 100, 'unreviewed_traffic_split')
    name = traffic[0][0]
    meta = revision.get('metadata', {})
    c.need(meta.get('name') == name and str(meta.get('namespace')) == c.NUMBER
           and meta.get('labels', {}).get('serving.knative.dev/service') == c.SERVICE,
           'unexpected_serving_revision')
    c.need(any(x.get('type') == 'Ready' and x.get('status') == 'True'
               for x in revision.get('status', {}).get('conditions', [])), 'serving_revision_not_ready')
    view = deepcopy(svc)
    view['spec']['template'] = {'metadata': deepcopy(meta), 'spec': deepcopy(revision.get('spec', {}))}
    view['status']['latestCreatedRevisionName'] = name
    view['status']['latestReadyRevisionName'] = name
    c.inspect(view, policy)
    return view


def differences(svc, serving):
    """Fixed diagnostic labels only. This is not a deployment approval check."""
    current = svc['spec']['template']
    expected = c.intended(serving, 'configure-internal-login')['spec']['template']
    actual_spec = deepcopy(current['spec'])
    expected_spec = deepcopy(expected['spec'])
    for spec in (actual_spec, expected_spec):
        for container in spec.get('containers', []):
            container['env'] = sorted(container.get('env', []), key=lambda item: item['name'])
    out = ['DIAGNOSTIC template spec after approved env: ' + ('same' if actual_spec == expected_spec else 'different')]
    for key in SPEC_FIELDS:
        if actual_spec.get(key) != expected_spec.get(key):
            out.append('DIAGNOSTIC differing spec field: ' + key)
    other = (set(actual_spec) | set(expected_spec)) - set(SPEC_FIELDS)
    count = sum(actual_spec.get(k) != expected_spec.get(k) for k in other)
    if count:
        out.append('DIAGNOSTIC other spec field differences: ' + str(count))
    for actual, previous in zip(actual_spec.get('containers', []), expected_spec.get('containers', [])):
        for key in CONTAINER_FIELDS:
            if actual.get(key) != previous.get(key):
                out.append('DIAGNOSTIC differing container field: ' + key)
        other = (set(actual) | set(previous)) - set(CONTAINER_FIELDS)
        count = sum(actual.get(k) != previous.get(k) for k in other)
        out.append('DIAGNOSTIC other container field differences: ' + str(count))
        actual_env = {x['name']: x for x in actual.get('env', [])}
        previous_env = {x['name']: x for x in previous.get('env', [])}
        for key in sorted(set(c.PLAIN) | set(c.INTERNAL) | set(c.SECRET_NAMES)):
            if actual_env.get(key) != previous_env.get(key):
                out.append('DIAGNOSTIC differing environment field: ' + key)
    labels = current.get('metadata', {}).get('labels', {})
    old_labels = expected.get('metadata', {}).get('labels', {})
    out.append('DIAGNOSTIC template label client.knative.dev/nonce: ' +
               ('different' if labels.get(NONCE) != old_labels.get(NONCE) else 'same'))
    # A Revision has system labels not present on the service template. Compare
    # declared template keys only and state this limitation explicitly.
    count = sum(labels[k] != old_labels.get(k) for k in labels if k != NONCE)
    out.append('DIAGNOSTIC other declared template label differences: ' + str(count))
    annotations = current.get('metadata', {}).get('annotations', {})
    old_annotations = expected.get('metadata', {}).get('annotations', {})
    for key in ANNOTATIONS:
        if annotations.get(key) != old_annotations.get(key):
            out.append('DIAGNOSTIC differing template annotation: ' + key)
    count = sum(annotations[k] != old_annotations.get(k) for k in annotations if k not in ANNOTATIONS)
    out.append('DIAGNOSTIC other declared template annotation differences: ' + str(count))
    out.append('DIAGNOSTIC historical service-level metadata is not reconstructed; promotion remains separately guarded.')
    return out


def inspect_pending(state, probe, summary):
    c.need(state['request']['operation'] == 'inspect', 'wrong_operation')
    svc, policy = state['before'], state['policy']
    latest = c.inspect(svc, policy)
    traffic = c.traffic(svc)
    c.need(len(traffic) == 1 and traffic[0][1] == 100, 'unreviewed_traffic_split')
    name = traffic[0][0]
    c.need(isinstance(name, str) and re.fullmatch(c.SERVICE + r'-[a-z0-9-]+', name), 'invalid_serving_revision')
    if name == latest['revision']:
        serving = svc
    else:
        revision = c.gc('run', 'revisions', 'describe', name, '--region=' + c.REGION)
        serving = serving_view(svc, policy, revision)
        for line in differences(svc, serving):
            summary(line)
    active = c.inspect(serving, policy)
    summary('Serving revision: ' + name + ' / traffic: 100 / login configuration: ' +
            ('enabled' if active['enabled'] else 'disabled'))
    probe(c.URL, active['enabled'], authenticated=False)
    probe(c.URL, active['enabled'])
    if name != latest['revision']:
        candidate = c.candidate_url(svc, latest['revision'])
        probe(candidate, latest['enabled'], authenticated=False)
        probe(candidate, latest['enabled'])
        summary('Pending candidate: ' + latest['revision'] + ' / service traffic: 0 / private boundary verified')
    fresh, fresh_policy = c.get_service()
    c.need(fresh['spec'] == svc['spec'] and c.traffic(fresh) == traffic
           and fresh['status']['latestCreatedRevisionName'] == svc['status']['latestCreatedRevisionName']
           and c.policy_key(fresh_policy) == c.policy_key(policy), 'service_changed_during_inspection')
    summary('PORTAL INSPECT PASSED. No deployment or DB/customer writes. Real Kakao login is not tested here.')


if __name__ == '__main__':
    import sys
    import operate as op
    try:
        c.source(live=True)
        inspect_pending(op.load(), op.probe, op.summary)
    except (Exception, KeyboardInterrupt) as exc:
        code = str(exc) if isinstance(exc, c.Stop) else 'unexpected_failure'
        print('STOP: revision-inspection / ' + code + '. No raw responses printed.', file=sys.stderr)
        raise SystemExit(1) from None
