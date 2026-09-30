"""Naver references do not weaken private/edge guards or read secret values."""
from copy import deepcopy
from unittest import TestCase
import common as c
from test_automation import service
from test_edge_ops import public_policy


def paired():
    s=service(True)
    s['spec']['template']['spec']['containers'][0]['env'] += [
        {'name':name,'valueFrom':{'secretKeyRef':{'name':secret,'key':'2'}}}
        for name,secret in c.NAVER_NAMES.items()]
    return s


class NaverReferences(TestCase):
    def test_paired_fixed_names_numeric_versions_only_in_edge(self):
        s=paired(); original=deepcopy(s)
        self.assertTrue(c.inspect(s,public_policy(),boundary='edge')['enabled'])
        self.assertEqual(s,original)
        with self.assertRaises(c.Stop):c.inspect(s,{})

    def test_plaintext_missing_wrong_secret_latest_and_zero_rejected(self):
        for bad in ('latest','0','-1','1,other-secret:1',''):
            s=paired();s['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['secretKeyRef']['key']=bad
            with self.subTest(version=bad),self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')
        s=paired();s['spec']['template']['spec']['containers'][0]['env'].pop()
        with self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')
        s=paired();s['spec']['template']['spec']['containers'][0]['env'][-1]['value']='raw-secret'
        with self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')
        s=paired();s['spec']['template']['spec']['containers'][0]['env'][-1]['valueFrom']['secretKeyRef']['name']='owner-db'
        with self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')

    def test_optional_refs_do_not_change_security_guards(self):
        s=paired();s['spec']['template']['spec']['serviceAccountName']='other'
        with self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')
        s=paired();s['spec']['template']['spec']['containers'][0]['env'].append({'name':'NEW_UNKNOWN','value':'x'})
        with self.assertRaises(c.Stop):c.inspect(s,public_policy(),boundary='edge')
        self.assertEqual(c.naver_references({},boundary='edge'),{})
