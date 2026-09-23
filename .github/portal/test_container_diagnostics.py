"""Only fixed names, never API values, in container difference diagnostics."""
import unittest
import revision_inspection as ri
from test_revision_inspection import fixture


class ContainerDiagnosticTests(unittest.TestCase):
    def test_nested_unknown_keys_and_values_are_not_echoed(self):
        state, revision = fixture(); svc = state['before']
        old = ri.serving_view(svc, {}, revision)
        svc['spec']['template']['spec']['containers'][0]['PRIVATE-KEY'] = 'PRIVATE-VALUE'
        text = '\n'.join(ri.differences(svc, old))
        self.assertNotIn('PRIVATE', text)
        self.assertIn('other container field differences: 1', text)

    def test_known_fields_show_names_only(self):
        state, revision = fixture(); svc = state['before']
        old = ri.serving_view(svc, {}, revision)
        container = svc['spec']['template']['spec']['containers'][0]
        container['name'] = 'PRIVATE-VALUE'
        container['env'][-1] = {'name': 'RICHON_EDGE_SECRET', 'value': 'PRIVATE-VALUE'}
        text = '\n'.join(ri.differences(svc, old))
        self.assertNotIn('PRIVATE', text)
        self.assertIn('differing container field: name', text)
        self.assertIn('differing environment field: RICHON_EDGE_SECRET', text)


if __name__ == '__main__':
    unittest.main()
