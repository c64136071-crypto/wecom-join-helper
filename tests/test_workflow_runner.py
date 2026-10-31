import importlib
import importlib.util
import inspect
import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
import tempfile
import threading
import time
import unittest
from typing import Any
from unittest.mock import patch


def api() -> Any:
    try:
        return importlib.import_module('wecom_rusher.workflow')
    except ModuleNotFoundError as exc:
        if exc.name != 'wecom_rusher.workflow':
            raise
        return None


def step(identifier='read1', action='read', target: str | None = 'receipt', value: Any = None,
         timeout_ms=2000, **extra) -> dict[str, Any]:
    return dict(id=identifier, action=action, target=target, value=value,
                timeout_ms=timeout_ms, **extra)


def plan(*steps, run_id='test-run', timeout_ms=10000) -> dict[str, Any]:
    return dict(version=1, runId=run_id, timeout_ms=timeout_ms,
                steps=list(steps) or [step()])


def lost_ack_worker(connection, name, output):
    """Test seam: real fixture mutation is persisted, but its ack is withheld."""
    mutation_fault_worker(connection, name, output, crash=False)


def crash_worker(connection, name, output):
    mutation_fault_worker(connection, name, output, crash=True)


def mutation_fault_worker(connection, name, output, crash):
    from wecom_rusher.workflow_adapters import create_fixture
    adapter = create_fixture(name, Path(output))
    connection.send_bytes(b'{"ok":true}')
    while True:
        message = json.loads(connection.recv_bytes())
        value = adapter.execute(message['action'], message['target'], message['value'])
        if message['action'] == 'click':
            if crash:
                os._exit(7)
            time.sleep(3)
        connection.send_bytes(json.dumps({'ok': True, 'value': value}).encode())


class SchemaTests(unittest.TestCase):
    def test_valid_plan_normalizes_into_immutable_steps(self):
        module = api()
        self.assertIsNotNone(module, 'restricted workflow validator is not implemented')
        payload = plan()
        parsed = module.validate_workflow(payload, {'receipt'})
        payload['steps'][0]['target'] = 'changed-after-validation'
        self.assertEqual(parsed.run_id, 'test-run')
        self.assertEqual(parsed.steps[0].target, 'receipt')
        self.assertIsInstance(parsed.steps, tuple)

    def test_rejects_unsafe_actions_targets_scalars_and_limits(self):
        candidates = [
            plan(step(action='shell', value='whoami')),
            plan(step(target='../window')),
            plan(step(value='not-null-for-read')),
            plan(step(action='input', value={'code': 'x'})),
            plan(step(action='input', value=float('nan'))),
            plan(step(action='input', value='x' * 4097)),
            plan(step(timeout_ms=True)),
            plan(step(timeout_ms=0)),
            plan(step(timeout_ms=10001)),
            plan(timeout_ms=60001),
            plan(run_id='../run'),
            plan(step(), step()),
            plan(*[step(str(i)) for i in range(65)]),
            dict(plan(), version=True),
            dict(plan(), retries=2),
            dict(plan(), steps=[]),
            plan(step(next='read1')),
            plan(step(next='missing')),
            plan(step(on_false='later'), step('later')),
            plan(step(action='wait', target='receipt', value=10)),
        ]
        for candidate in candidates:
            with self.subTest(candidate=repr(candidate)[:90]):
                with self.assertRaisesRegex(ValueError, '^invalid_workflow$'):
                    api().validate_workflow(candidate, {'receipt'})

    def test_forward_only_branch_and_wait_are_valid(self):
        p = plan(step('check', 'assert', value=0, on_false='finish'),
                 step('pause', 'wait', None, 10), step('finish'))
        parsed = api().validate_workflow(p, {'receipt'})
        self.assertEqual(parsed.steps[0].on_false, 'finish')


class ExecutionTests(unittest.TestCase):
    def form_plan(self, **kwargs):
        return plan(step('find', 'locate', 'name'),
                    step('name', 'input', 'name', 'Ada'),
                    step('quantity', 'input', 'quantity', 2),
                    step('pause', 'wait', None, 5),
                    step('save', 'click', 'save'),
                    step('receipt-read', 'read', 'receipt'),
                    step('verify', 'assert', 'receipt', 1), **kwargs)

    def test_form_workflow_executes_six_actions_and_reads_actual_receipt(self):
        run: Any = getattr(api(), 'run_workflow', None)
        self.assertTrue(callable(run), 'workflow executor is not implemented')
        with tempfile.TemporaryDirectory() as directory:
            result = run(self.form_plan(), 'form', Path(directory))
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.completed_steps, 7)
            self.assertEqual(result.values['receipt-read'], 1)
            self.assertEqual(json.loads((result.artifact_dir / 'records.json').read_text()),
                             [{'name': 'Ada', 'quantity': 2}])

    def test_report_uses_same_kernel_and_writes_actual_csv(self):
        self.assertIn('report', api().CAPABILITIES, 'second fixture adapter is missing')
        workflow = plan(step('period', 'input', 'period', '2026-10'),
                        step('export', 'click', 'export'),
                        step('total', 'read', 'total'),
                        step('verify', 'assert', 'total', 20))
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'report', Path(directory))
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.values['total'], 20)
            self.assertEqual((result.artifact_dir / 'export.csv').read_bytes(),
                             b'period,total\n2026-10,20\n')

    def test_step_deadline_stops_slow_action_and_reaps_worker(self):
        workflow = plan(step('slow', 'wait', None, 500, timeout_ms=100),
                        step('not-read'))
        before = {p.pid for p in multiprocessing.active_children()}
        with tempfile.TemporaryDirectory() as directory:
            start = time.monotonic()
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('timed_out', 'step_timeout'))
            self.assertLess(time.monotonic() - start, 1.5)
            self.assertEqual(result.completed_steps, 0)
            self.assertEqual(result.values, {})
        self.assertEqual({p.pid for p in multiprocessing.active_children()}, before)

    def test_total_deadline_covers_cumulative_actions(self):
        workflow = plan(step('first', 'wait', None, 400),
                        step('second', 'wait', None, 400), timeout_ms=700)
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('timed_out', 'total_timeout'))
            self.assertLess(result.completed_steps, 2)

    def test_total_deadline_includes_worker_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(plan(timeout_ms=1), 'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('timed_out', 'total_timeout'))
            self.assertEqual(result.completed_steps, 0)


    def test_pre_cancelled_run_has_no_files_or_worker(self):
        self.assertIn('cancel_event', inspect.signature(api().run_workflow).parameters,
                      'executor has no cancellation channel')
        event = threading.Event()
        event.set()
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'not-created'
            result = api().run_workflow(self.form_plan(), 'form', workspace, cancel_event=event)
            self.assertEqual((result.status, result.reason), ('cancelled', 'cancelled'))
            self.assertFalse(workspace.exists())

    def test_cancellation_interrupts_running_wait(self):
        self.assertIn('cancel_event', inspect.signature(api().run_workflow).parameters,
                      'executor has no cancellation channel')
        event = threading.Event()
        timer = threading.Timer(0.4, event.set)
        with tempfile.TemporaryDirectory() as directory:
            timer.start()
            try:
                start = time.monotonic()
                result = api().run_workflow(plan(step('wait', 'wait', None, 2000, timeout_ms=3000)),
                                            'form', Path(directory), cancel_event=event)
                self.assertEqual(result.status, 'cancelled')
                self.assertLess(time.monotonic() - start, 1.5)
                self.assertEqual(result.completed_steps, 0)
            finally:
                timer.cancel()
                timer.join()


    def test_failed_assertion_can_only_branch_forward_without_skipped_effect(self):
        workflow = plan(step('check', 'assert', 'receipt', 99, on_false='finish'),
                        step('skipped', 'input', 'quantity', -1), step('finish'))
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.completed_steps, 2)
            self.assertEqual(result.values, {'finish': 0})

    def test_success_branch_skips_unselected_steps(self):
        workflow = plan(step('check', 'assert', 'receipt', 0, next='finish'),
                        step('skipped', 'read'), step('finish'))
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.completed_steps, 2)
            self.assertEqual(result.values, {'finish': 0})

    def test_assertion_failure_without_branch_stops_later_steps(self):
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(plan(step('check', 'assert', 'receipt', 99), step('later')),
                                        'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('failed', 'assertion_failed'))
            self.assertEqual(result.values, {})


    def test_completed_run_id_cannot_be_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = api().run_workflow(self.form_plan(), 'form', workspace)
            self.assertEqual(first.status, 'completed')
            original = (first.artifact_dir / 'records.json').read_bytes()
            second = api().run_workflow(self.form_plan(), 'form', workspace)
            self.assertEqual((second.status, second.reason), ('rejected', 'run_already_reserved'))
            self.assertEqual(second.completed_steps, 0)
            self.assertEqual((first.artifact_dir / 'records.json').read_bytes(), original)

    def test_lost_mutation_ack_is_unknown_and_persistently_blocks_replay(self):
        workflow = self.form_plan()
        workflow['steps'][4]['timeout_ms'] = 100
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with patch('wecom_rusher.workflow.fixture_worker', lost_ack_worker):
                result = api().run_workflow(workflow, 'form', workspace)
            self.assertEqual((result.status, result.reason), ('unknown', 'step_timeout'))
            self.assertEqual(json.loads((result.artifact_dir / 'records.json').read_text()),
                             [{'name': 'Ada', 'quantity': 2}])
            replay = api().run_workflow(workflow, 'form', workspace)
            self.assertEqual(replay.status, 'rejected')
            events = [json.loads(line) for line in (result.artifact_dir.parent / 'audit.jsonl').read_text().splitlines()]
            self.assertTrue(any(e.get('event') == 'intent' and e.get('action') == 'click' for e in events))
            self.assertFalse(any(e.get('event') == 'acknowledged' and e.get('action') == 'click' for e in events))


class ReliabilityCoverageTests(unittest.TestCase):
    """Coverage-only counterexamples for existing safety behavior, not new RED claims."""
    def test_invalid_later_step_prevents_all_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory) / 'work'
            with self.assertRaisesRegex(ValueError, '^invalid_workflow$'):
                api().run_workflow(plan(step('write', 'input', 'name', 'Ada'),
                                        step('unsafe', 'shell', 'name', 'ignored')), 'form', workspace)
            self.assertFalse(workspace.exists())

    def test_crash_after_real_fixture_write_is_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('wecom_rusher.workflow.fixture_worker', crash_worker):
                result = api().run_workflow(ExecutionTests().form_plan(), 'form', Path(directory))
            self.assertEqual(result.status, 'unknown')
            self.assertTrue((result.artifact_dir / 'records.json').is_file())
            self.assertEqual(api().run_workflow(plan(), 'form', Path(directory)).status, 'rejected')

    def test_cancel_after_write_without_ack_remains_unknown(self):
        event = threading.Event()
        observed = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def observe():
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline:
                    if list(root.glob('*/artifacts/records.json')):
                        observed.append(True)
                        event.set()
                        return
                    time.sleep(0.005)
                event.set()
            observer = threading.Thread(target=observe)
            observer.start()
            try:
                with patch('wecom_rusher.workflow.fixture_worker', lost_ack_worker):
                    result = api().run_workflow(ExecutionTests().form_plan(), 'form', root, cancel_event=event)
            finally:
                observer.join(5)
            self.assertEqual(observed, [True])
            self.assertEqual((result.status, result.reason), ('unknown', 'cancelled'))
            self.assertFalse(observer.is_alive())

    def test_concurrent_same_run_reservation_allows_only_one_worker(self):
        results = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = plan(step('wait', 'wait', None, 500))
            worker = threading.Thread(target=lambda: results.append(api().run_workflow(workflow, 'form', root)))
            worker.start()
            try:
                deadline = time.monotonic() + 3
                while not list(root.glob('*/audit.jsonl')) and time.monotonic() < deadline:
                    time.sleep(0.005)
                self.assertTrue(list(root.glob('*/audit.jsonl')))
                second = api().run_workflow(workflow, 'form', root)
                self.assertEqual((second.status, second.reason), ('rejected', 'run_already_reserved'))
            finally:
                worker.join(5)
            self.assertFalse(worker.is_alive())
            self.assertEqual([r.status for r in results], ['completed'])

    def test_audit_fsync_failure_never_dispatches(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch('wecom_rusher.workflow.os.fsync', side_effect=OSError('PRIVATE-IO-DETAIL')):
                result = api().run_workflow(ExecutionTests().form_plan(), 'form', Path(directory))
            self.assertEqual(result.status, 'failed')
            self.assertEqual(result.completed_steps, 0)
            self.assertFalse(list(Path(directory).glob('*/artifacts/records.json')))
            self.assertEqual(api().run_workflow(plan(), 'form', Path(directory)).status, 'rejected')

    def test_final_audit_failure_cannot_publish_completed(self):
        real_audit = api()._audit
        def failing_final(handle, event):
            if event['event'] == 'execution_finished':
                raise OSError('PRIVATE-CLOSEOUT-DETAIL')
            real_audit(handle, event)
        with tempfile.TemporaryDirectory() as directory:
            with patch('wecom_rusher.workflow._audit', side_effect=failing_final):
                result = api().run_workflow(plan(), 'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('failed', 'audit_error'))

    def test_code_shaped_string_is_only_input_data(self):
        code = "__import__('builtins').print('NEVER_EVALUATE')"
        workflow = plan(step('data', 'input', 'name', code), step('read', 'read', 'name'))
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual(result.status, 'completed')
            self.assertEqual(result.values['read'], code)


class FixtureGuardTests(unittest.TestCase):
    def test_identity_change_after_locate_rejects_mutation(self):
        from wecom_rusher.workflow_adapters import create_fixture
        with tempfile.TemporaryDirectory() as directory:
            adapter: Any = create_fixture('form', Path(directory))
            self.assertTrue(adapter.execute('locate', 'name', None))
            adapter.identity = 'different-fixture-window'
            with self.assertRaisesRegex(ValueError, '^target_identity_changed$'):
                adapter.execute('input', 'name', 'must-not-write')
            self.assertEqual(adapter.fields['name'], '')

    def test_missing_or_similar_targets_are_not_arbitrarily_selected(self):
        from wecom_rusher.workflow_adapters import create_fixture
        for count in (0, 2):
            with self.subTest(matches=count), tempfile.TemporaryDirectory() as directory:
                adapter: Any = create_fixture('form', Path(directory))
                adapter.matches = {'name': count}
                with self.assertRaisesRegex(ValueError, '^target_not_unique$'):
                    adapter.execute('input', 'name', 'must-not-write')
                self.assertEqual(adapter.fields['name'], '')

    def test_semantic_targets_survive_fixture_layout_reordering(self):
        from wecom_rusher.workflow_adapters import create_fixture
        with tempfile.TemporaryDirectory() as directory:
            adapter: Any = create_fixture('form', Path(directory))
            adapter.fields = {'quantity': 0, 'name': ''}
            adapter.execute('input', 'name', 'Ada')
            self.assertEqual(adapter.execute('read', 'name', None), 'Ada')


class StepCloseoutRegressionTests(unittest.TestCase):
    """R1: accepting an IPC reply is not the end of the step budget."""
    def check_delayed_audit(self, stage, mutation=False, total_timeout=False):
        real_audit = api()._audit
        injected = []
        def slow_audit(handle, event):
            real_audit(handle, event)
            if event['event'] == stage and event.get('index') == 0:
                injected.append(stage)
                time.sleep(0.7 if total_timeout else 0.3)
        first = step('first', 'input', 'name', 'Ada', timeout_ms=2000 if total_timeout else 100) if mutation else step('first', timeout_ms=100)
        workflow = plan(first, step('later'), timeout_ms=600 if total_timeout else 10000)
        with tempfile.TemporaryDirectory() as directory:
            with patch('wecom_rusher.workflow._audit', side_effect=slow_audit):
                result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual(injected, [stage])
            self.assertEqual((result.status, result.reason),
                             ('timed_out', 'total_timeout' if total_timeout else 'step_timeout'))
            self.assertEqual(result.completed_steps, 0)
            self.assertEqual(result.values, {})
            events = [json.loads(line) for line in (result.artifact_dir.parent / 'audit.jsonl').read_text().splitlines()]
            self.assertFalse(any(e.get('index') == 1 for e in events))
            if mutation:
                self.assertTrue(any(e.get('event') == 'acknowledged' for e in events))
                self.assertNotEqual(result.status, 'unknown', 'durably known ACK must stay known')

    def test_slow_step_completed_log_stops_before_acceptance_and_next_dispatch(self):
        self.check_delayed_audit('step_completed')

    def test_slow_acknowledgement_stops_but_does_not_turn_known_mutation_unknown(self):
        self.check_delayed_audit('acknowledged', mutation=True)

    def test_acknowledgement_also_rechecks_total_deadline(self):
        self.check_delayed_audit('acknowledged', mutation=True, total_timeout=True)


class FinalDeadlineTests(unittest.TestCase):
    def test_total_deadline_also_rejects_late_final_audit_completion(self):
        real_audit = api()._audit
        reached_final = []
        def late_final(handle, event):
            real_audit(handle, event)
            if event['event'] == 'execution_finished':
                reached_final.append(True)
                time.sleep(0.8)
        with tempfile.TemporaryDirectory() as directory:
            with patch('wecom_rusher.workflow._audit', side_effect=late_final):
                result = api().run_workflow(plan(timeout_ms=700), 'form', Path(directory))
            self.assertEqual(reached_final, [True])
            self.assertEqual((result.status, result.reason), ('timed_out', 'total_timeout'))


class UnicodeBoundaryTests(unittest.TestCase):
    def test_schema_legal_unicode_value_reaches_assertion_not_ipc_failure(self):
        workflow = plan(step('unicode', 'assert', 'receipt', '中' * 4096))
        with tempfile.TemporaryDirectory() as directory:
            result = api().run_workflow(workflow, 'form', Path(directory))
            self.assertEqual((result.status, result.reason), ('failed', 'assertion_failed'))


class CLITests(unittest.TestCase):
    def invoke(self, *arguments):
        self.assertIsNotNone(importlib.util.find_spec('wecom_rusher.workflow_cli'),
                             'standalone fixture CLI is not implemented')
        return subprocess.run([sys.executable, '-B', '-m', 'wecom_rusher.workflow_cli', *map(str, arguments)],
                              capture_output=True, text=True, encoding='utf-8', timeout=15)

    def test_cli_runs_form_and_redacts_input_from_console_and_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            workflow = plan(step('private-id', 'input', 'name', 'PRIVATE-DATA-SENTINEL'),
                            step('read', 'read', 'name'))
            source = root / 'workflow.json'
            source.write_text(json.dumps(workflow), encoding='utf-8')
            command = ('--workflow', source, '--adapter', 'form', '--workspace', root / 'work')
            output = self.invoke(*command)
            self.assertEqual(output.returncode, 0, output.stderr)
            self.assertEqual(json.loads(output.stdout)['status'], 'completed')
            audit = next((root / 'work').glob('*/audit.jsonl')).read_text()
            for private in ('PRIVATE-DATA-SENTINEL', 'private-id', 'test-run'):
                self.assertNotIn(private, output.stdout + output.stderr + audit)
            repeat = self.invoke(*command)
            self.assertEqual(repeat.returncode, 2)
            self.assertEqual(json.loads(repeat.stdout)['reason'], 'run_already_reserved')

    def test_cli_rejects_unsafe_and_malformed_json_before_workspace_creation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'invalid.json'
            for raw in [json.dumps(plan(step(action='eval', value='SECRET-CODE'))),
                        '{"version":1,"version":1}', '{"x":NaN}', ' ' * 65537]:
                with self.subTest(raw=raw[:40]):
                    source.write_text(raw, encoding='utf-8')
                    result = self.invoke('--workflow', source, '--adapter', 'form', '--workspace', root / 'work')
                    self.assertEqual(result.returncode, 2)
                    self.assertEqual(json.loads(result.stdout)['reason'], 'invalid_workflow')
                    self.assertNotIn('SECRET-CODE', result.stdout + result.stderr)
                    self.assertFalse((root / 'work').exists())

    def test_cli_preexisting_cancel_file_exits_without_dispatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'workflow.json'
            source.write_text(json.dumps(plan()), encoding='utf-8')
            cancel = root / 'stop'
            cancel.touch()
            result = self.invoke('--workflow', source, '--adapter', 'form', '--workspace', root / 'work',
                                 '--cancel-file', cancel)
            self.assertEqual(result.returncode, 130)
            self.assertEqual(json.loads(result.stdout)['status'], 'cancelled')
            self.assertFalse((root / 'work').exists())


if __name__ == '__main__':
    unittest.main()
