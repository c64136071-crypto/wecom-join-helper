import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import uuid

from test_workflow_dom import EVIDENCE, workflow, workflow_step, workflow_dir


class OwnedCLITests(unittest.TestCase):
    def invoke(self, p, adapter, root, label):
        source = root / 'workflow.json'
        if not source.exists():
            source.write_text(json.dumps(p), encoding='utf-8')
        command = [sys.executable, '-B', '-m', 'wecom_rusher.workflow_cli',
                   '--workflow', str(source), '--adapter', adapter, '--workspace', str(root / 'work')]
        env = dict(os.environ, OWNED_DOM_HEADLESS='0', PYTHONDONTWRITEBYTECODE='1')
        out, err = root / (label + '.stdout.txt'), root / (label + '.stderr.txt')
        with out.open('x', encoding='utf-8') as stdout, err.open('x', encoding='utf-8') as stderr:
            process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr)
            try:
                code = process.wait(timeout=85)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                self.fail('owned CLI timed out; parent-held kill-on-close Job must reclaim descendants')
        (root / (label + '.command.json')).write_text(json.dumps({'command':command,'exitCode':code,
                'pid':process.pid,'timeoutSeconds':85,'timedOut':False,'headed':True}), encoding='utf-8')
        return code, out.read_text(encoding='utf-8'), err.read_text(encoding='utf-8')

    def execute_cli(self, adapter):
        root = workflow_dir()
        form = adapter == 'owned-dom-form'
        steps = [workflow_step('locate', 'locate', 'name' if form else 'period')]
        if form:
            steps += [workflow_step('name', 'input', 'name', 'CLI-owned-Ada'),
                      workflow_step('quantity', 'input', 'quantity', 2), workflow_step('save', 'click', 'save')]
        else:
            steps += [workflow_step('period', 'input', 'period', '2026-10'), workflow_step('export', 'click', 'export'),
                      workflow_step('total', 'assert', 'total', 20)]
        steps += [workflow_step('receipt', 'assert', 'receipt', 1)]
        p = workflow(*steps)
        code, stdout, stderr = self.invoke(p, adapter, root, 'first')
        self.assertEqual(code, 0, stderr + stdout)
        summary = json.loads(stdout)
        self.assertEqual(summary['status'], 'completed')
        self.assertIs(summary['fixtureOnly'], False)
        run = root / 'work' / hashlib.sha256(p['runId'].encode()).hexdigest()
        artifacts = run / 'artifacts'
        info = json.loads((run / 'owned-dom/start.json').read_text())
        self.assertIs(info['headless'], False)
        for name in ('initial.png','final.png'):
            self.assertTrue((artifacts / name).is_file())
        self.assertTrue(json.loads((run / 'owned-dom/cleanup.json').read_text())['verified'])
        if form:
            records = json.loads((artifacts / 'app-records.json').read_text(encoding='utf-8'))
            self.assertEqual([(row['name'],row['quantity'],row['receipt']) for row in records], [('CLI-owned-Ada',2,1)])
            original = (artifacts / 'app-records.json').read_bytes()
        else:
            original = (artifacts / 'export.csv').read_bytes()
            self.assertEqual(original, b'period,total\n2026-10,20\n')
            self.assertEqual((artifacts / 'app-export.csv').read_bytes(), original)
            record = json.loads((artifacts / 'app-exports.json').read_text())[0]
            self.assertEqual(record['sha256'], hashlib.sha256(original).hexdigest())
        repeat, repeated_stdout, _ = self.invoke(p, adapter, root, 'replay')
        self.assertEqual(repeat, 2)
        self.assertEqual(json.loads(repeated_stdout)['reason'], 'run_already_reserved')
        self.assertEqual((artifacts / ('app-records.json' if form else 'export.csv')).read_bytes(), original)
        self.assertNotIn('CLI-owned-Ada', stdout + stderr + (run / 'audit.jsonl').read_text())
        (root / 'accepted-cli-evidence.json').write_text(json.dumps({'adapter':adapter,'runId':p['runId'],
            'workspace':str(root/'work'),'runDir':str(run),'headed':True,'actualCliExit':code,
            'artifactSha256':hashlib.sha256(original).hexdigest(),'replayExit':repeat,'cleanupVerified':True},indent=2),encoding='utf-8')

    def test_cli_headed_form_real_save(self):
        self.execute_cli('owned-dom-form')

    def test_cli_headed_report_real_download(self):
        self.execute_cli('owned-dom-report')


if __name__ == '__main__':
    unittest.main()
