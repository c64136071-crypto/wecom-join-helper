"""Only explicit fixtures; never discover windows or scan the repository."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


class WorkflowStartTests(unittest.TestCase):
    def invoke(self, *args, cwd=ROOT):
        return subprocess.run([sys.executable, '-B', '-m', 'wecom_rusher.workflow_start', *map(str, args)],
                              cwd=cwd, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                              capture_output=True, text=True, encoding='utf-8', timeout=90)

    def test_file_dependency_check_works_without_desktop_imports_or_workspace(self):
        result = self.invoke('--check')
        self.assertEqual(result.returncode, 0, 'file-only dependency entry is unavailable: ' + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report['ready'])
        self.assertEqual(report['mode'], 'file')
        self.assertEqual(set(report['checks']), {'python'})

    def test_selected_file_examples_persist_outputs_and_reject_replay(self):
        for example, filename in [('form', 'records.json'), ('report', 'export.csv')]:
            with self.subTest(example=example), tempfile.TemporaryDirectory() as directory:
                workspace = Path(directory) / 'work'
                args = ('--example', example, '--workspace', workspace)
                first = self.invoke(*args)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(json.loads(first.stdout)['status'], 'completed')
                artifact = next(workspace.glob('*/artifacts/' + filename))
                original = artifact.read_bytes()
                if example == 'form':
                    self.assertEqual(json.loads(original), [{'name': 'Ada', 'quantity': 2}])
                else:
                    self.assertEqual(original, b'period,total\n2026-10,20\n')
                replay = self.invoke(*args)
                self.assertEqual(replay.returncode, 2)
                self.assertEqual(json.loads(replay.stdout)['reason'], 'run_already_reserved')
                self.assertEqual(artifact.read_bytes(), original)

    def test_missing_workspace_and_unsafe_example_never_dispatch(self):
        for args, message in [((), 'workspace'), (('--example', 'https://example.invalid'), 'invalid choice')]:
            result = self.invoke(*args)
            self.assertEqual(result.returncode, 2)
            self.assertIn(message, result.stderr)

    def test_cancel_marker_is_forwarded_without_creating_workspace(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / 'stop'
            marker.touch()
            result = self.invoke('--workspace', root / 'work', '--cancel-file', marker)
            self.assertEqual(result.returncode, 130, result.stderr)
            self.assertEqual(json.loads(result.stdout)['reason'], 'cancelled')
            self.assertFalse((root / 'work').exists())

    def test_dom_missing_dependencies_report_fixed_remedy_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = ('--mode', 'dom', '--node', root / 'missing.exe', '--playwright', root / 'missing-package',
                    '--browser', root / 'missing-browser.exe')
            result = self.invoke('--check', *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn('dependency_not_ready', result.stdout)
            report = json.loads(result.stdout)
            self.assertFalse(report['ready'])
            self.assertFalse(report['checks']['node']['ready'])
            self.assertIn('npm ci', report['remedy'])
            run = self.invoke(*args, '--workspace', root / 'work')
            self.assertEqual(run.returncode, 2)
            self.assertEqual(json.loads(run.stdout)['reason'], 'dependency_not_ready')
            self.assertFalse((root / 'work').exists())


    @unittest.skipUnless(os.name == 'nt', 'Windows command wrapper')
    def test_windows_launcher_works_from_another_directory(self):
        launcher = ROOT / 'workflow.cmd'
        self.assertTrue(launcher.is_file(), 'portable command launcher is missing')
        with tempfile.TemporaryDirectory() as directory:
            payload = subprocess.list2cmdline([str(launcher), '--check'])
            command = '"' + os.environ['COMSPEC'] + '" /d /s /c "' + payload + '"'
            result = subprocess.run(command, cwd=directory, capture_output=True, text=True, timeout=20,
                                    env=dict(os.environ, WORKFLOW_PYTHON=sys.executable, PYTHONDONTWRITEBYTECODE='1'))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(json.loads(result.stdout)['ready'])

    def test_dom_choices_use_existing_cli_and_restore_child_only_bindings(self):
        from wecom_rusher.workflow_start import main
        before = {key: os.environ.get(key) for key in
                  ('OWNED_DOM_NODE', 'OWNED_DOM_PLAYWRIGHT', 'OWNED_DOM_BROWSER', 'OWNED_DOM_HEADLESS')}
        for example in ('form', 'report'):
            observed = []
            def invoke(args):
                observed.append(args)
                self.assertEqual(os.environ['OWNED_DOM_HEADLESS'], '0')
                self.assertEqual(os.environ['OWNED_DOM_NODE'], str((ROOT / 'node.exe').resolve()))
                return 17
            with patch('wecom_rusher.workflow_start.dependency_report', return_value={'ready': True}), \
                 patch('wecom_rusher.workflow_cli.main', side_effect=invoke):
                try:
                    code = main(['--mode', 'dom', '--example', example, '--workspace', 'owned-output',
                                 '--node', 'node.exe', '--playwright', 'playwright', '--browser', 'chrome.exe'])
                except SystemExit as exc:
                    self.fail('ready DOM example was rejected instead of delegated: ' + str(exc))
            self.assertEqual(code, 17)
            self.assertIn('owned-dom-' + example, observed[0])
            self.assertIn(str(ROOT / 'examples' / ('workflow-dom-' + example + '.json')), observed[0])
            self.assertEqual(before, {key: os.environ.get(key) for key in before})


if __name__ == '__main__':
    unittest.main()
