import importlib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import threading
import unittest
import uuid
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Any
from unittest.mock import patch

EVIDENCE = Path(os.environ['P3_DOM_EVIDENCE'])


def module() -> Any:
    try:
        return importlib.import_module('wecom_rusher.workflow_dom')
    except ModuleNotFoundError as exc:
        if exc.name != 'wecom_rusher.workflow_dom':
            raise
        return None


def case_dir(label):
    directory = EVIDENCE / 'cases' / (label + '-' + uuid.uuid4().hex)
    directory.mkdir(parents=True)
    return directory


class ChildEnvironmentTests(unittest.TestCase):
    def test_child_appdata_directories_exist_before_browser_spawn(self):
        import shutil
        directory = case_dir('child-appdata')
        session = module().OwnedDomSession('owned-dom-form', directory / 'artifacts')
        session.temp_dir.mkdir(parents=True)
        try:
            env = session.child_environment()
            for key in ('LOCALAPPDATA', 'APPDATA'):
                self.assertTrue(Path(env[key]).is_dir(), f'{key} directory must exist before Chrome resolves Windows folders')
                self.assertTrue(Path(env[key]).resolve().is_relative_to(session.temp_dir.resolve()))
        finally:
            shutil.rmtree(directory)


class NativeOwnershipTests(unittest.TestCase):
    def test_owned_job_tracks_and_reaps_exact_node_process(self):
        api = module()
        self.assertIsNotNone(api, 'parent-owned native resource lifetime is missing')
        job_class = getattr(api, 'OwnedJob', None)
        self.assertTrue(callable(job_class), 'parent-owned native resource lifetime is missing')
        directory = case_dir('native-job')
        job = job_class(directory / 'ownership.jsonl')
        process = None
        try:
            with (directory / 'node.stdout.txt').open('x') as out, (directory / 'node.stderr.txt').open('x') as err:
                process = subprocess.Popen([os.environ['OWNED_DOM_NODE'], '-e', 'setInterval(()=>{},1000)'],
                                           stdin=subprocess.DEVNULL, stdout=out, stderr=err)
                job.assign(process)
                self.assertIn(process.pid, job.snapshot())
                rows = [json.loads(line) for line in (directory / 'ownership.jsonl').read_text().splitlines()]
                self.assertTrue(any(row.get('pid') == process.pid and row.get('creationTime') for row in rows))
        finally:
            cleanup = job.cleanup()
            if process is not None:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=5)
        self.assertTrue(cleanup['verified'], cleanup)
        self.assertEqual(cleanup['activeMembers'], [])
        self.assertTrue(all(row['exited'] for row in cleanup['processReadback']))
        (directory / 'test-readback.json').write_text(json.dumps(cleanup, indent=2))


class OwnedServerTests(unittest.TestCase):
    def test_parent_starts_own_loopback_server_and_verifies_pid_port_cleanup(self):
        session_class: Any = getattr(module(), 'OwnedDomSession', None)
        self.assertTrue(callable(session_class), 'parent-owned server session is missing')
        directory = case_dir('owned-server')
        session = session_class('owned-dom-form', directory / 'artifacts', {'server_only': True})
        deadline = time.monotonic() + 20
        def check():
            if time.monotonic() >= deadline:
                raise TimeoutError('test_startup_deadline')
        try:
            session.start(check)
            info = session.info
            self.assertEqual(info['nodePid'], session.process.pid)
            self.assertEqual(info['instanceId'], session.instance_id)
            url = f"http://127.0.0.1:{info['httpPort']}/health"
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(url, timeout=3) as response:
                health = json.loads(response.read())
            self.assertEqual(health['instanceId'], session.instance_id)
            self.assertEqual(health['appId'], 'owned-dom-form')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            origin = f"http://127.0.0.1:{info['httpPort']}"
            normal = json.dumps({'name':'Ada','quantity':1,'inputEvents':1,'instanceId':session.instance_id}).encode()
            for data, headers in [(normal, {'Origin':'http://localhost:1'}),
                                  (b'x'*8193, {'Origin':origin}),
                                  (b'{"name":"Ada"}', {'Origin':origin})]:
                request = urllib.request.Request(origin+'/api/save',data=data,
                    headers={'Content-Type':'application/json',**headers})
                with self.subTest(kind=len(data),origin=headers['Origin']):
                    with self.assertRaises(urllib.error.HTTPError) as rejected:
                        opener.open(request,timeout=3)
                    self.assertEqual(rejected.exception.code,400)
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                opener.open(origin+'/not-an-allowed-file',timeout=3)
            self.assertEqual(rejected.exception.code,404)
            self.assertFalse((session.artifacts/'app-records.json').exists())
            self.assertTrue(session.startup_listeners['verified'])
        finally:
            cleanup = session.close()
        self.assertTrue(cleanup['verified'], cleanup)
        self.assertEqual(cleanup['listeners']['rows'], [])
        self.assertFalse(session.temp_dir.exists())


class OwnedBrowserTests(unittest.TestCase):
    def test_new_browser_reads_actual_bound_dom_and_is_fully_reclaimed(self):
        session_class = module().OwnedDomSession
        self.assertTrue(callable(getattr(session_class, 'command', None)), 'real browser DOM command path is missing')
        directory = case_dir('real-dom-read')
        session = session_class('owned-dom-form', directory / 'artifacts', {'headless': True})
        until = time.monotonic() + 30
        def check():
            if time.monotonic() >= until:
                raise TimeoutError('test_startup_deadline')
        try:
            session.start(check)
            self.assertEqual(session.command('read', 'receipt', None, check), 0)
            self.assertIn(session.info['browserPid'], session.job.records)
            self.assertTrue(Path(session.info['profilePath']).is_relative_to(session.temp_dir))
            self.assertTrue((directory / 'artifacts' / 'initial.png').is_file())
            self.assertEqual(len(session.ports), 2)
        finally:
            cleanup = session.close()
        self.assertTrue(cleanup['verified'], cleanup)
        self.assertFalse(Path(session.info['profilePath']).exists())


class DomActionTests(unittest.TestCase):
    @contextmanager
    def session(self, label='dom-action', app='owned-dom-form', control=None):
        directory = case_dir(label)
        session = module().OwnedDomSession(app, directory / 'artifacts', {'headless': True})
        until = time.monotonic() + 40
        def check():
            if time.monotonic() >= until:
                raise TimeoutError('test_budget')
        try:
            original = module().publish_json
            def publish(path, data):
                if Path(path).name == 'start.json' and control:
                    (Path(path).parent / 'test-control.json').write_text(json.dumps(control), encoding='utf-8')
                original(path, data)
            with patch('wecom_rusher.workflow_dom.publish_json', side_effect=publish):
                session.start(check)
            yield session, check
        finally:
            cleanup = session.close()
            self.assertTrue(cleanup['verified'], cleanup)

    def test_input_uses_real_dom_input_events(self):
        with self.session('input-events') as (session, check):
            self.assertIsNone(session.command('input', 'name', 'Ada', check))
            self.assertEqual(session.command('read', 'name', None, check), 'Ada')
            observations = [json.loads(line) for line in (session.artifacts / 'dom-observations.jsonl').read_text().splitlines()]
            self.assertGreaterEqual(observations[-1]['inputEvents'], 1)

    def test_wait_keeps_bound_page_and_observes_duration(self):
        with self.session('dom-wait') as (session, check):
            started = time.monotonic()
            self.assertIsNone(session.command('wait', None, 100, check))
            self.assertGreaterEqual(time.monotonic() - started, 0.1)
            self.assertEqual(session.command('read', 'receipt', None, check), 0)

    def test_redirect_popup_and_off_origin_requests_are_blocked(self):
        with self.session('request-gates', control={'securityProbe':True}) as (session, check):
            try:
                session.command('input','name','Ada',check)
            except OSError:
                pass  # A latched refusal may race with completion of this input.
            expected = {'redirect_blocked','popup_blocked','external_request_blocked'}
            until = time.monotonic()+3
            events = set()
            while time.monotonic()<until:
                events = {row['event'] for row in map(json.loads,(session.directory/'node-events.jsonl').read_text().splitlines())}
                if expected <= events:
                    break
                time.sleep(0.01)
            self.assertTrue(expected <= events, sorted(events))
            with self.assertRaisesRegex(OSError,'target_identity_changed'):
                session.command('read','receipt',None,check)
            requests = [json.loads(line) for line in (session.artifacts/'app-requests.jsonl').read_text().splitlines()]
            self.assertFalse(any(row['path']=='/health' for row in requests), requests)

    def test_save_commits_app_storage_before_receipt(self):
        with self.session('form-save') as (session, check):
            session.command('input', 'name', 'Ada', check)
            self.assertIsNone(session.command('click', 'save', None, check))
            self.assertEqual(session.command('read', 'receipt', None, check), 1)
            records = json.loads((session.artifacts / 'app-records.json').read_text(encoding='utf-8'))
            self.assertEqual(records, [{'name': 'Ada', 'quantity': 1, 'inputEvents': 1,
                                        'receipt': 1, 'instanceId': session.instance_id}])

    def test_typed_input_quantity_is_saved_as_integer(self):
        with self.session('typed-quantity') as (session, check):
            session.command('input', 'name', 'Ada', check)
            session.command('input', 'quantity', 2, check)
            session.command('click', 'save', None, check)
            self.assertEqual(json.loads((session.artifacts / 'app-records.json').read_text())[0]['quantity'], 2)

    def test_typed_input_period_fires_change_and_filters_total(self):
        with self.session('typed-period', 'owned-dom-report') as (session, check):
            self.assertEqual(session.command('read', 'receipt', None, check), 0)
            session.command('input', 'period', '2026-09', check)
            self.assertEqual(session.command('read', 'period', None, check), '2026-09')
            self.assertEqual(session.command('read', 'total', None, check), 99)

    def test_export_download_bytes_match_app_record(self):
        import hashlib
        with self.session('report-export', 'owned-dom-report') as (session, check):
            session.command('input', 'period', '2026-09', check)
            session.command('click', 'export', None, check)
            expected = b'period,total\n2026-09,99\n'
            self.assertEqual((session.artifacts / 'export.csv').read_bytes(), expected)
            self.assertEqual((session.artifacts / 'app-export.csv').read_bytes(), expected)
            receipts = json.loads((session.artifacts / 'app-exports.json').read_text())
            self.assertEqual(receipts, [{'period': '2026-09', 'total': 99, 'receipt': 1,
                                        'instanceId': session.instance_id, 'length': len(expected),
                                        'sha256': hashlib.sha256(expected).hexdigest()}])
            self.assertEqual(session.command('read', 'receipt', None, check), 1)


def workflow(*steps, run_id=None, timeout_ms=60000):
    return {'version': 1, 'runId': run_id or 'dom-' + uuid.uuid4().hex,
            'timeout_ms': timeout_ms, 'steps': list(steps)}


def workflow_step(identifier, action, target=None, value=None, timeout_ms=10000):
    return {'id': identifier, 'action': action, 'target': target, 'value': value, 'timeout_ms': timeout_ms}


def workflow_dir():
    # Keep the owned Windows fixture below MAX_PATH after the kernel's 64-char reservation.
    directory = EVIDENCE / 'w' / uuid.uuid4().hex[:8]
    directory.mkdir(parents=True)
    return directory


class KernelDomTests(unittest.TestCase):
    def test_kernel_form_uses_same_execution_loop_and_app_commit(self):
        from wecom_rusher.workflow import run_workflow
        p = workflow(workflow_step('name', 'input', 'name', 'Ada'),
                     workflow_step('quantity', 'input', 'quantity', 2),
                     workflow_step('save', 'click', 'save'),
                     workflow_step('receipt', 'read', 'receipt'),
                     workflow_step('verify', 'assert', 'receipt', 1))
        result = run_workflow(p, 'owned-dom-form', workflow_dir())
        self.assertEqual((result.status, result.reason), ('completed', 'completed'))
        self.assertEqual(result.values, {'receipt': 1})
        self.assertEqual(json.loads((result.artifact_dir / 'app-records.json').read_text())[0]['quantity'], 2)
        self.assertTrue(json.loads((result.artifact_dir.parent / 'owned-dom/cleanup.json').read_text())['verified'])

    def test_kernel_report_uses_same_execution_loop_and_download(self):
        from wecom_rusher.workflow import run_workflow
        p = workflow(workflow_step('period', 'input', 'period', '2026-10'),
                     workflow_step('export', 'click', 'export'),
                     workflow_step('total', 'read', 'total'),
                     workflow_step('verify', 'assert', 'receipt', 1))
        result = run_workflow(p, 'owned-dom-report', workflow_dir())
        self.assertEqual(result.status, 'completed')
        self.assertEqual(result.values, {'total': 20})
        self.assertEqual((result.artifact_dir / 'export.csv').read_bytes(), b'period,total\n2026-10,20\n')
        self.assertTrue(json.loads((result.artifact_dir.parent / 'owned-dom/cleanup.json').read_text())['verified'])


class DomBoundaryTests(unittest.TestCase):
    """Real owned DOM negative controls; passing inherited predicates are coverage-only."""
    def run_owned(self, p, control=None, event=None, workspace=None):
        from wecom_rusher.workflow import run_workflow
        workspace = workspace or workflow_dir()
        original = module().publish_json
        def publish(path, data):
            path = Path(path)
            if path.name == 'start.json' and control:
                self.assertTrue(path.is_relative_to(EVIDENCE))
                (path.parent / 'test-control.json').write_text(json.dumps(control), encoding='utf-8')
            original(path, data)
        with patch('wecom_rusher.workflow_dom.publish_json', side_effect=publish):
            result = run_workflow(p, 'owned-dom-form', workspace, cancel_event=event)
        cleanup = json.loads((result.artifact_dir.parent / 'owned-dom/cleanup.json').read_text())
        self.assertTrue(cleanup['verified'], cleanup)
        self.assertEqual(cleanup['job']['activeMembers'], [])
        self.assertTrue(all(row['exited'] for row in cleanup['job']['processReadback']))
        # Even a startup-time cancellation must read back ports published during shutdown.
        published_ports = set()
        for filename, key in [('server-info.json','httpPort'),('browser-info.json','cdpPort')]:
            info = result.artifact_dir.parent / 'owned-dom' / filename
            if info.exists():
                published_ports.add(json.loads(info.read_text())[key])
        self.assertEqual(set(cleanup['listeners']['queriedPorts']), published_ports)
        (result.artifact_dir.parent / 'test-outcome.json').write_text(json.dumps({
            'status':result.status,'reason':result.reason,'completedSteps':result.completed_steps,
            'controls':control or {},'cleanupVerified':True}, indent=2), encoding='utf-8')
        return result, workspace

    def save_plan(self, timeout=1500):
        return workflow(workflow_step('name', 'input', 'name', 'Ada'),
                        workflow_step('save', 'click', 'save', timeout_ms=timeout),
                        workflow_step('must-not-run', 'input', 'name', 'NEVER-DISPATCH'))

    def test_ambiguous_target_rejects_before_mutation(self):
        p = workflow(workflow_step('find', 'locate', 'name'), workflow_step('later','input','name','Ada'))
        result, _ = self.run_owned(p, {'duplicateName':True})
        self.assertEqual((result.status,result.reason), ('failed','target_not_unique'))
        self.assertEqual(result.completed_steps, 0)
        self.assertFalse((result.artifact_dir / 'app-records.json').exists())

    def test_identity_changes_after_locate_and_input_stops_save(self):
        p = workflow(workflow_step('find','locate','name'),workflow_step('name','input','name','Ada'),
                     workflow_step('save','click','save'))
        result, _ = self.run_owned(p, {'identityAfterInput':True})
        self.assertEqual((result.status,result.reason), ('unknown','target_identity_changed'))
        self.assertEqual(result.completed_steps, 1)
        self.assertFalse((result.artifact_dir / 'app-records.json').exists())

    def test_compact_reordered_layout_still_saves_once(self):
        p = workflow(workflow_step('name','input','name','Ada'),workflow_step('quantity','input','quantity',2),
                     workflow_step('save','click','save'),workflow_step('receipt','assert','receipt',1))
        result, _ = self.run_owned(p, {'compact':True})
        self.assertEqual(result.status,'completed')
        self.assertEqual(len(json.loads((result.artifact_dir/'app-records.json').read_text())),1)

    def test_delayed_wait_hits_step_budget_without_later_dispatch(self):
        p = workflow(workflow_step('wait','wait',value=2000,timeout_ms=150),
                     workflow_step('later','input','name','Ada'))
        result, _ = self.run_owned(p)
        self.assertEqual((result.status,result.reason),('timed_out','step_timeout'))
        self.assertEqual(result.completed_steps,0)
        self.assertEqual(len(list((result.artifact_dir.parent/'owned-dom/requests').glob('*.json'))),1)

    def test_delayed_app_save_is_not_accepted_or_followed(self):
        result, _ = self.run_owned(self.save_plan(timeout=150), {'delayBeforeCommitMs':2500})
        self.assertEqual((result.status,result.reason),('unknown','step_timeout'))
        self.assertEqual(result.completed_steps,1)
        self.assertEqual(len(list((result.artifact_dir.parent/'owned-dom/requests').glob('*.json'))),2)

    def test_total_deadline_includes_dom_startup_and_late_resource_cleanup(self):
        result, _ = self.run_owned(workflow(workflow_step('read','read','receipt'),timeout_ms=1))
        self.assertEqual((result.status,result.reason),('timed_out','total_timeout'))
        self.assertEqual(result.completed_steps,0)

    def observe_then_cancel(self, workspace, p, suffix, event, stop, observed):
        path = workspace / hashlib.sha256(p['runId'].encode()).hexdigest() / suffix
        until = time.monotonic()+40
        while not stop.is_set() and time.monotonic()<until:
            if path.exists():
                observed.set()
                event.set()
                return
            time.sleep(0.005)

    def test_cancel_interrupts_actual_dom_wait(self):
        p = workflow(workflow_step('wait','wait',value=3000,timeout_ms=5000),
                     workflow_step('later','input','name','Ada'))
        root, event, stop, observed = workflow_dir(), threading.Event(), threading.Event(), threading.Event()
        thread = threading.Thread(target=self.observe_then_cancel,
            args=(root,p,'owned-dom/requests/000001.json',event,stop,observed))
        thread.start()
        try:
            result, _ = self.run_owned(p,event=event,workspace=root)
        finally:
            stop.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(observed.is_set())
        self.assertEqual((result.status,result.reason),('cancelled','cancelled'))
        self.assertEqual(result.completed_steps,0)

    def test_cancel_after_server_started_reads_late_owned_resources(self):
        p = workflow(workflow_step('read','read','receipt'))
        root, event, stop, observed = workflow_dir(), threading.Event(), threading.Event(), threading.Event()
        thread = threading.Thread(target=self.observe_then_cancel,
            args=(root,p,'owned-dom/server-info.json',event,stop,observed))
        thread.start()
        try:
            result, _ = self.run_owned(p,event=event,workspace=root)
        finally:
            stop.set(); thread.join(3)
        self.assertTrue(observed.is_set())
        self.assertFalse(thread.is_alive())
        self.assertEqual((result.status,result.reason),('cancelled','cancelled'))
        self.assertEqual(result.completed_steps,0)
        cleanup = json.loads((result.artifact_dir.parent/'owned-dom/cleanup.json').read_text())
        self.assertGreaterEqual(len(cleanup['listeners']['queriedPorts']),1)

    def test_committed_lost_ack_is_unknown_and_replay_is_reserved(self):
        from wecom_rusher.workflow import run_workflow
        p = self.save_plan()
        result, root = self.run_owned(p,{'dropAck':True})
        self.assertEqual((result.status,result.reason),('unknown','step_timeout'))
        self.assertEqual(result.completed_steps,1)
        raw = (result.artifact_dir/'app-records.json').read_bytes()
        self.assertEqual(len(json.loads(raw)),1)
        self.assertEqual(len(list((result.artifact_dir.parent/'owned-dom/requests').glob('*.json'))),2)
        replay = run_workflow(p,'owned-dom-form',root)
        self.assertEqual((replay.status,replay.reason),('rejected','run_already_reserved'))
        self.assertEqual((result.artifact_dir/'app-records.json').read_bytes(),raw)
        audit = [json.loads(line) for line in (result.artifact_dir.parent/'audit.jsonl').read_text().splitlines()]
        self.assertFalse(any(row.get('event')=='acknowledged' and row.get('action')=='click' for row in audit))

    def test_cancel_after_actual_commit_stays_unknown(self):
        p = self.save_plan(timeout=7000)
        root, event, stop, observed = workflow_dir(), threading.Event(), threading.Event(), threading.Event()
        thread = threading.Thread(target=self.observe_then_cancel,
            args=(root,p,'artifacts/app-records.json',event,stop,observed))
        thread.start()
        try:
            result, _ = self.run_owned(p,{'dropAck':True},event=event,workspace=root)
        finally:
            stop.set(); thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertTrue(observed.is_set())
        self.assertEqual((result.status,result.reason),('unknown','cancelled'))
        self.assertEqual(len(json.loads((result.artifact_dir/'app-records.json').read_text())),1)
        self.assertEqual(result.completed_steps,1)


if __name__ == '__main__':
    unittest.main()
