"""Restricted diagnostic-capture regressions; real owned Chrome test is explicit opt-in."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class DiagnosticCaptureTests(unittest.TestCase):
    def check_case(self, case):
        helper = ROOT / 'wecom_rusher/workflow_dom_capture.cjs'
        self.assertTrue(helper.is_file(), 'diagnostic screenshot timeout isolation is missing')
        node = shutil.which('node')
        self.assertIsNotNone(node, 'Node is required for these helper tests')
        script = r'''
const assert=require('node:assert/strict');
const {captureDiagnostic}=require(process.argv[1]);
const scenario=process.argv[2];
(async()=>{
  const events=[]; let checked=0, captures=0;
  const timeout=new Error('PRIVATE-DIAGNOSTIC-DATA'); timeout.name='TimeoutError';
  const failure=new Error('PRIVATE-IO-DATA');
  const page={screenshot:async options=>{
    captures++; assert.equal(options.path,'owned-final.png'); assert.equal(options.timeout,5000);
    if(scenario!=='normal') throw scenario==='io-error'?failure:timeout;
  }};
  const guard=async()=>{checked++; if(scenario==='identity-error') throw new Error('target_identity_changed');};
  const record=event=>{if(scenario==='log-error') throw new Error('diagnostic_log_failed'); events.push(event);};
  const call=()=>captureDiagnostic(page,'owned-final.png',guard,record);
  if(scenario==='io-error') await assert.rejects(call,/PRIVATE-IO-DATA/);
  else if(scenario==='identity-error') await assert.rejects(call,/target_identity_changed/);
  else if(scenario==='log-error') await assert.rejects(call,/diagnostic_log_failed/);
  else await call();
  assert.equal(captures,1);
  if(scenario==='normal') {assert.equal(checked,1); assert.deepEqual(events,[]);}
  if(scenario==='timeout'||scenario==='redacted') {
    assert.equal(checked,1); assert.deepEqual(events,[{event:'diagnostic_screenshot_timeout'}]);
    assert.ok(!JSON.stringify(events).includes('PRIVATE'));
  }
  if(scenario==='identity-error') assert.equal(checked,1);
  if(scenario==='io-error') {assert.equal(checked,0); assert.deepEqual(events,[]);}
  console.log(JSON.stringify({case:scenario,passed:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
        result = subprocess.run([str(node), '-e', script, str(helper), case],
                                capture_output=True, text=True, encoding='utf-8', timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)['passed'])

    def test_snapshot_timeout_is_diagnostic_and_rechecks_identity(self):
        self.check_case('timeout')

    def test_normal_capture_rechecks_identity_without_warning(self):
        self.check_case('normal')

    def test_non_timeout_errors_are_not_swallowed(self):
        self.check_case('io-error')

    def test_changed_identity_after_timeout_is_not_success(self):
        self.check_case('identity-error')

    def test_warning_persistence_error_is_not_success(self):
        self.check_case('log-error')

    def test_diagnostic_warning_never_contains_raw_error_data(self):
        self.check_case('redacted')


class SourceDependencyTests(unittest.TestCase):
    def test_source_manifest_includes_capture_dependency_and_regression(self):
        builder = runpy.run_path(str(ROOT / 'scripts/build_workflow_source.py'))
        required = {'wecom_rusher/workflow_dom_capture.cjs', 'tests/test_workflow_dom_reliability.py',
                    'docs/workflow-dom-reliability.md'}
        self.assertTrue(required <= set(builder['FILES']), 'source delivery omits the new capture dependency or its regression/docs')


@unittest.skipUnless(os.environ.get('WORKFLOW_RELIABILITY_EVIDENCE'), 'explicit owned-browser evidence root required')
class OwnedMinimizedSaveTests(unittest.TestCase):
    def test_real_receipt_survives_post_save_snapshot_timeout(self):
        evidence = Path(os.environ['WORKFLOW_RELIABILITY_EVIDENCE']).resolve()
        evidence.mkdir(parents=True, exist_ok=False)
        source = evidence / 's'
        files = ['wecom_rusher/' + name for name in (
            '__init__.py', 'workflow.py', 'workflow_adapters.py', 'workflow_cli.py', 'workflow_dom.py',
            'workflow_dom_bridge.cjs', 'owned_apps/server.cjs', 'owned_apps/form.html', 'owned_apps/form.js',
            'owned_apps/report.html', 'owned_apps/report.js')]
        helper = ROOT / 'wecom_rusher/workflow_dom_capture.cjs'
        if helper.exists():
            files.append('wecom_rusher/workflow_dom_capture.cjs')
        source_hashes = {}
        for name in files:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            raw = (ROOT / name).read_bytes()
            target.write_bytes(raw)
            source_hashes[name] = hashlib.sha256(raw).hexdigest()
        bridge = source / 'wecom_rusher/workflow_dom_bridge.cjs'
        text = bridge.read_text(encoding='utf-8')
        old = "      const before = Number(await page.locator('[data-target=\"receipt\"]').textContent());\n      await locator.click({timeout: 5000});"
        new = old + "\n      const pageCdp=await context.newCDPSession(page);\n      const target=await pageCdp.send('Target.getTargetInfo');\n      const browserCdp=await browser.newBrowserCDPSession();\n      const ownWindow=await browserCdp.send('Browser.getWindowForTarget',{targetId:target.targetInfo.targetId});\n      await browserCdp.send('Browser.setWindowBounds',{windowId:ownWindow.windowId,bounds:{windowState:'minimized'}});\n      event({event:'test_owned_window_minimized',windowId:ownWindow.windowId});\n      await pageCdp.detach(); await browserCdp.detach();"
        assert text.count(old) == 1
        text = text.replace(old, new)
        old = '  const server = createOwnedServer(root, config, appPath);'
        assert text.count(old) == 1
        text = text.replace(old, "  fs.writeFileSync(path.join(root,'test-control.json'),JSON.stringify({delayBeforeCommitMs:750}));\n" + old)
        bridge.write_text(text, encoding='utf-8')
        plan = {'version': 1, 'runId': 'reliability-save', 'timeout_ms': 60000, 'steps': [
            {'id': 'name', 'action': 'input', 'target': 'name', 'value': 'Ada', 'timeout_ms': 10000},
            {'id': 'save', 'action': 'click', 'target': 'save', 'value': None, 'timeout_ms': 10000},
            {'id': 'verify', 'action': 'assert', 'target': 'receipt', 'value': 1, 'timeout_ms': 10000}]}
        workflow = evidence / 'plan.json'
        workflow.write_text(json.dumps(plan), encoding='utf-8')
        workspace = evidence / 'w'
        command = [sys.executable, '-B', '-m', 'wecom_rusher.workflow_cli', '--workflow', str(workflow),
                   '--adapter', 'owned-dom-form', '--workspace', str(workspace)]
        env = dict(os.environ, OWNED_DOM_HEADLESS='0', PYTHONDONTWRITEBYTECODE='1',
                   TEMP=str(evidence), TMP=str(evidence), TMPDIR=str(evidence))
        with (evidence / 'stdout.txt').open('xb') as out, (evidence / 'stderr.txt').open('xb') as err:
            child = subprocess.Popen(command, cwd=source, env=env, stdout=out, stderr=err, stdin=subprocess.DEVNULL)
            with (evidence / 'started.json').open('x', encoding='utf-8') as handle:
                json.dump({'pid': child.pid, 'command': command, 'sourceHashes': source_hashes,
                    'testBridgeSha256': hashlib.sha256(bridge.read_bytes()).hexdigest(),
                    'fixtureChanges': 'delay only own server; minimize only own created window after save click'}, handle, indent=2)
            try:
                code = child.wait(timeout=85)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=10)
                self.fail('owned child deadline exceeded; keep evidence and verify cleanup before further launches')
        directory = workspace / hashlib.sha256(plan['runId'].encode()).hexdigest()
        cleanup = json.loads((directory / 'owned-dom/cleanup.json').read_text(encoding='utf-8'))
        records = json.loads((directory / 'artifacts/app-records.json').read_text(encoding='utf-8'))
        self.assertTrue(cleanup['verified'], cleanup)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['receipt'], 1)
        summary = json.loads((evidence / 'stdout.txt').read_text(encoding='utf-8'))
        with (evidence / 'outcome.json').open('x', encoding='utf-8') as handle:
            json.dump({'exitCode': code, 'summary': summary, 'receipt': 1, 'cleanupVerified': True,
                'expected': 'completed after snapshot timeout; app receipt and identity, not screenshot, acknowledge save'}, handle, indent=2)
        self.assertEqual((code, summary['status']), (0, 'completed'),
                         'a confirmed app save must not become unknown solely because a diagnostic screenshot times out')
        events = [json.loads(line) for line in (directory / 'owned-dom/node-events.jsonl').read_text().splitlines()]
        self.assertTrue(any(row['event'] == 'diagnostic_screenshot_timeout' for row in events))
        self.assertTrue(any(row['event'] == 'test_owned_window_minimized' for row in events))


if __name__ == '__main__':
    unittest.main()
