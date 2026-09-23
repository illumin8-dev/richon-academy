"""Read-only diagnostics tested entirely with fake command results."""
import importlib.util
import io
import json
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[2] / 'ops/check_portal_preflight.py'
spec = importlib.util.spec_from_file_location('portal_preflight_diagnostic', PATH)
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class PreflightDiagnosticTests(unittest.TestCase):
    def result(self, step, *, failure=False, existing=False):
        values = {
            'active-account': [{'account': 'PRIVATE-ACCOUNT', 'status': 'ACTIVE'}],
            'project-metadata': {'projectNumber': '756298505437'},
            'service-list': [{'metadata': {'name': 'richon-portal'}}] if existing else [],
            'kakao-key-versions': [{'name': 'PRIVATE-METADATA', 'state': 'ENABLED'}],
            'kakao-secret-versions': [{'name': 'PRIVATE-METADATA', 'state': 'ENABLED'}],
        }
        out = b'' if step.startswith('source-') else json.dumps(values.get(step, {'PRIVATE': 'VALUE'})).encode()
        return subprocess.CompletedProcess(p.CHECKS[step], int(failure), out, b'PRIVATE-STDERR permission denied')

    def test_allowlist_has_only_reads_and_never_reads_secret_payloads(self):
        allowed = {('auth', 'list'), ('projects', 'describe'), ('projects', 'get-iam-policy'),
                   ('run', 'services', 'describe'), ('run', 'services', 'get-iam-policy'),
                   ('run', 'services', 'list'), ('iam', 'service-accounts', 'describe'),
                   ('secrets', 'versions', 'list')}
        for step, args in p.CHECKS.items():
            if args[0] == 'gcloud':
                self.assertTrue(any(tuple(args[1:1+len(prefix)]) == prefix for prefix in allowed))
                self.assertIn('--project=richon-academy', args)
                self.assertNotIn('access', args)
            else:
                self.assertIn(step, {'source-status', 'source-history'})

    def test_error_hints_are_only_fixed_codes(self):
        cases = [('reauthentication PRIVATE', 'authorization_required'),
                 ('invalid_grant PRIVATE', 'authorization_required'),
                 ('PERMISSION_DENIED PRIVATE', 'permission_denied'),
                 ('SERVICE_DISABLED PRIVATE', 'api_not_enabled'),
                 ('NOT_FOUND PRIVATE', 'resource_not_found'),
                 ('Name resolution PRIVATE', 'network_or_service_error'),
                 ('unrecognized arguments PRIVATE', 'invalid_cli_arguments'),
                 ('postgresql://PRIVATE', 'unclassified_error')]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(p.error_hint(raw.encode()), expected)

    def test_unknown_command_name_cannot_execute(self):
        with patch.object(p.subprocess, 'run') as run:
            with self.assertRaises(KeyError):
                p.read('secrets-access')
            run.assert_not_called()

    def test_read_failure_has_no_command_or_secret_content(self):
        with patch.object(p.subprocess, 'run', return_value=self.result('project-metadata', failure=True)):
            with self.assertRaises(p.CheckFailed) as exc:
                p.read('project-metadata')
        self.assertEqual(str(exc.exception), 'permission_denied')

    def test_timeouts_and_os_errors_do_not_leak(self):
        cases = [(subprocess.TimeoutExpired(['PRIVATE'], 90, b'PRIVATE', b'PRIVATE'), 'command_timeout'),
                 (OSError('PRIVATE'), 'command_could_not_start')]
        for error, message in cases:
            with self.subTest(message=message), patch.object(p.subprocess, 'run', side_effect=error):
                with self.assertRaises(p.CheckFailed) as exc:
                    p.read('project-metadata')
                self.assertEqual(str(exc.exception), message)

    def test_invalid_json_or_shape_does_not_leak(self):
        for output in (b'PRIVATE-INVALID', b'"PRIVATE"', b'null', b'[]', b'\xff'):
            with self.subTest(output=output), patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output)):
                with self.assertRaises(p.CheckFailed) as exc:
                    p.read('project-metadata')
                self.assertEqual(str(exc.exception), 'invalid_response')

    def test_empty_account_and_secret_versions_are_distinct(self):
        for step, code in [('active-account', 'no_active_account'), ('kakao-key-versions', 'no_enabled_secret_version')]:
            with self.subTest(step=step), patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'[]')):
                with self.assertRaises(p.CheckFailed) as exc:
                    p.read(step)
                self.assertEqual(str(exc.exception), code)

    def test_wrong_project_is_blocked(self):
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'{"projectNumber":"OTHER"}')):
            with self.assertRaisesRegex(p.CheckFailed, '^wrong_project$'):
                p.read('project-metadata')

    def test_dirty_tree_never_outputs_filenames(self):
        with patch.object(p.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, b'?? PRIVATE.env')):
            with self.assertRaisesRegex(p.CheckFailed, '^clean_checkout_required$'):
                p.read('source-status')

    def run_main(self, *, existing=False, fail_at=None):
        called = []
        def fake_run(args, **kwargs):
            step = next(key for key, command in p.CHECKS.items() if command == args)
            called.append(step)
            self.assertNotIn('shell', kwargs)
            self.assertEqual(kwargs['stdin'], subprocess.DEVNULL)
            self.assertEqual(kwargs['env']['CLOUDSDK_CORE_LOG_HTTP'], 'false')
            self.assertEqual(kwargs['timeout'], 90)
            return self.result(step, failure=step == fail_at, existing=existing)
        out, err = io.StringIO(), io.StringIO()
        with patch.object(p.subprocess, 'run', side_effect=fake_run), redirect_stdout(out), redirect_stderr(err):
            code = p.main()
        self.assertNotIn('PRIVATE', out.getvalue() + err.getvalue())
        return code, called, out.getvalue(), err.getvalue()

    def test_readonly_success_does_not_start_setup(self):
        code, called, out, err = self.run_main()
        self.assertEqual(code, 0)
        self.assertNotIn('portal-service', called)
        self.assertIn('Setup was NOT run.', out)
        self.assertEqual(err, '')

    def test_existing_portal_is_only_read(self):
        code, called, out, err = self.run_main(existing=True)
        self.assertEqual(code, 0)
        self.assertIn('portal-service', called)
        self.assertIn('portal-service-iam', called)

    def test_first_failure_stops_later_reads(self):
        code, called, out, err = self.run_main(fail_at='project-metadata')
        self.assertEqual(code, 1)
        self.assertEqual(called[-1], 'project-metadata')
        self.assertEqual(err.strip(), 'CHECK FAILED: project-metadata / permission_denied')
        self.assertNotIn('PREFLIGHT READ CHECKS PASSED', out)

    def test_unexpected_exception_does_not_leak(self):
        err = io.StringIO()
        with patch.object(p, 'read', side_effect=RuntimeError('PRIVATE')), redirect_stderr(err):
            self.assertEqual(p.main(), 1)
        self.assertEqual(err.getvalue().strip(), 'CHECK FAILED: source-status / diagnostic_interrupted')


if __name__ == '__main__':
    unittest.main()
