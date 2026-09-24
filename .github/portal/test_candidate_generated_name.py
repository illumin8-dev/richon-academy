"""Regress only the observed missing service name / portal-1 Revision name."""
from copy import deepcopy
from unittest import TestCase
from unittest.mock import patch
import common as c
import candidate_readback as r
from test_candidate_readback import fixture


class ExactGeneratedName(TestCase):
    def test_observed_pair_matches_without_mutating_input(self):
        svc, policy, revs = fixture()
        rev = revs[r.CANDIDATE]; rev['spec']['containers'][0]['name'] = 'portal-1'
        original = deepcopy((svc, rev))
        actual = r.validate_revision(rev, r.CANDIDATE, svc, policy)
        self.assertEqual(actual['spec']['template']['spec']['containers'][0]['name'], 'portal-1')
        self.assertEqual((svc, rev), original)

    def test_other_generated_names_and_different_declared_names_fail(self):
        for declared, observed in ((None,'other'), ('app','portal-1'), ('portal-1','other'), ('portal-1',None)):
            svc, policy, revs = fixture(); rev = revs[r.CANDIDATE]
            if declared is not None: svc['spec']['template']['spec']['containers'][0]['name'] = declared
            if observed is not None: rev['spec']['containers'][0]['name'] = observed
            with patch.object(r.op, 'summary'), self.assertRaises(c.Stop):
                r.validate_revision(rev, r.CANDIDATE, svc, policy)

    def test_exact_name_does_not_hide_image_ref_port_or_unknown_differences(self):
        for mutate in (
            lambda s: s['containers'][0].update(image=c.IMAGE+'@sha256:'+'c'*64),
            lambda s: s['containers'][0]['env'][-1]['valueFrom']['secretKeyRef'].update(key='2'),
            lambda s: s['containers'][0].update(ports=[{'containerPort':9000}]),
            lambda s: s.update(unreviewed='value'),
        ):
            svc, policy, revs = fixture(); rev = revs[r.CANDIDATE]
            rev['spec']['containers'][0]['name'] = 'portal-1'; mutate(rev['spec'])
            with patch.object(r.op, 'summary'), self.assertRaises(c.Stop):
                r.validate_revision(rev, r.CANDIDATE, svc, policy)

    def test_dependencies_sidecars_and_before_after_name_checks_stay_strict(self):
        for mutate in (
            lambda rev: rev['spec']['containers'][0].update(dependsOn=['other']),
            lambda rev: rev['spec']['containers'].append({}),
            lambda rev: rev['metadata']['annotations'].update({'run.googleapis.com/container-dependencies':'{"a":["b"]}'}),
        ):
            svc, policy, revs = fixture(); rev = revs[r.CANDIDATE]
            rev['spec']['containers'][0]['name'] = 'portal-1'; mutate(rev)
            with self.assertRaises(c.Stop): r.validate_revision(rev, r.CANDIDATE, svc, policy)
        svc, _, _ = fixture(); changed = deepcopy(svc)
        changed['spec']['template']['spec']['containers'][0]['name'] = 'portal-1'
        self.assertNotEqual(c.protected(svc), c.protected(changed))
