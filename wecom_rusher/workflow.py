"""One restricted execution loop for fixtures and owned DOM; legacy entrypoint unchanged."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import multiprocessing
import os
import re
import time
from pathlib import Path
from typing import Any, cast

from .workflow_adapters import CAPABILITIES as FIXTURE_CAPABILITIES, MAX_MESSAGE_BYTES, fixture_worker
from .workflow_dom import DOM_CAPABILITIES, OwnedDomSession

CAPABILITIES = {**FIXTURE_CAPABILITIES, **DOM_CAPABILITIES}


@dataclass(frozen=True)
class Step:
    id: str
    action: str
    target: str | None
    value: Any
    timeout_ms: int
    next: str | None = None
    on_false: str | None = None


@dataclass(frozen=True)
class Plan:
    run_id: str
    timeout_ms: int
    steps: tuple[Step, ...]


def validate_workflow(payload: dict[str, Any], capabilities: set[str]) -> Plan:
    def require(condition):
        if not condition:
            raise ValueError('invalid_workflow')

    def identifier(value):
        return isinstance(value, str) and re.fullmatch(r'[A-Za-z][A-Za-z0-9_-]{0,63}', value)

    def integer(value, low, high):
        return type(value) is int and low <= value <= high

    require(type(payload) is dict and set(payload) == {'version', 'runId', 'timeout_ms', 'steps'})
    require(type(payload['version']) is int and payload['version'] == 1)
    require(identifier(payload['runId']))
    require(integer(payload['timeout_ms'], 1, 60000))
    items: Any = payload['steps']
    require(type(items) is list and 1 <= len(items) <= 64)
    steps = []
    for raw in items:
        required = {'id', 'action', 'target', 'value', 'timeout_ms'}
        require(type(raw) is dict and required <= set(raw) <= required | {'next', 'on_false'})
        item = cast(dict[str, Any], raw)
        require(identifier(item['id']))
        action, target, value = item['action'], item['target'], item['value']
        require(type(action) is str and action in {'locate', 'read', 'click', 'input', 'wait', 'assert'})
        require(integer(item['timeout_ms'], 1, 10000))
        require(value is None or type(value) in {str, int, float, bool})
        require(not isinstance(value, str) or len(value) <= 4096)
        require(type(value) is not float or math.isfinite(value))
        require(type(value) is not int or abs(value) <= 10**12)
        if action == 'wait':
            require(target is None and integer(value, 0, 10000))
        else:
            require(isinstance(target, str) and target in capabilities)
        if action in {'locate', 'read', 'click'}:
            require(value is None)
        require('on_false' not in item or action == 'assert')
        for key in ('next', 'on_false'):
            require(key not in item or identifier(item[key]))
        steps.append(Step(**item))
    positions = {s.id: i for i, s in enumerate(steps)}
    require(len(positions) == len(steps))
    for i, s in enumerate(steps):
        for destination in (s.next, s.on_false):
            require(destination is None or destination in positions and positions[destination] > i)
    try:
        require(len(json.dumps(payload, ensure_ascii=True, allow_nan=False).encode('utf-8')) <= 65536)
    except (TypeError, OverflowError, RecursionError):
        raise ValueError('invalid_workflow') from None
    return Plan(payload['runId'], payload['timeout_ms'], tuple(steps))


@dataclass
class RunResult:
    status: str
    reason: str
    completed_steps: int
    values: dict[str, Any]
    artifact_dir: Path


class WorkflowStop(Exception):
    pass


def _checkpoint(deadline, total_deadline, cancel_event):
    if cancel_event is not None and cancel_event.is_set():
        raise WorkflowStop('cancelled')
    now = time.monotonic()
    if now >= total_deadline:
        raise WorkflowStop('total_timeout')
    if now >= deadline:
        raise WorkflowStop('step_timeout')
    return now


def _receive(connection, process, deadline, total_deadline, cancel_event):
    while True:
        now = _checkpoint(deadline, total_deadline, cancel_event)
        if connection.poll(min(0.01, deadline - now, total_deadline - now)):
            reply = json.loads(connection.recv_bytes(MAX_MESSAGE_BYTES))
            if time.monotonic() >= min(deadline, total_deadline):
                continue  # Late replies are not success.
            if not reply['ok']:
                raise WorkflowStop(reply['reason'])
            return reply.get('value')
        if not process.is_alive():
            raise WorkflowStop('worker_exited')


def _audit(handle, event):
    """Do not dispatch a mutation until its intent has been flushed and fsynced."""
    handle.write(json.dumps(event, sort_keys=True) + '\n')
    handle.flush()
    os.fsync(handle.fileno())


def run_workflow(payload, adapter_name, workspace, *, cancel_event=None) -> RunResult:
    started = time.monotonic()
    if adapter_name not in CAPABILITIES:
        raise ValueError('invalid_adapter')
    plan = validate_workflow(payload, set(CAPABILITIES[adapter_name]))
    total_deadline = started + plan.timeout_ms / 1000
    root = Path(workspace)
    run_hash = hashlib.sha256(plan.run_id.encode('utf-8')).hexdigest()
    run_dir = root / run_hash
    output = run_dir / 'artifacts'
    if cancel_event is not None and cancel_event.is_set():
        return RunResult('cancelled', 'cancelled', 0, {}, output)
    try:
        root.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir()  # Atomic reservation; even malformed/incomplete old runs stay blocked.
    except FileExistsError:
        return RunResult('rejected', 'run_already_reserved', 0, {}, output)
    except OSError:
        return RunResult('failed', 'workspace_error', 0, {}, output)
    dom = adapter_name in DOM_CAPABILITIES
    parent: Any
    child: Any
    process: Any
    if dom:
        parent = OwnedDomSession(adapter_name, output, {'headless': os.environ.get('OWNED_DOM_HEADLESS') == '1'})
        child = process = None
    else:
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe()
        process = context.Process(target=fixture_worker, args=(child, adapter_name, str(output)), daemon=True)
    result = RunResult('failed', 'not_started', 0, {}, output)
    journal = None
    pending_mutation = False
    try:
        journal = (run_dir / 'audit.jsonl').open('x', encoding='utf-8')
        _audit(journal, {'event': 'run_started', 'runHash': run_hash})
        output.mkdir()
        if dom:
            parent.start(lambda: _checkpoint(total_deadline, total_deadline, cancel_event))
        else:
            process.start()
            child.close()
            _receive(parent, process, total_deadline, total_deadline, cancel_event)
        positions = {step.id: i for i, step in enumerate(plan.steps)}
        index = 0
        while index < len(plan.steps):
            step = plan.steps[index]
            if cancel_event is not None and cancel_event.is_set():
                raise WorkflowStop('cancelled')
            deadline = time.monotonic() + step.timeout_ms / 1000
            if time.monotonic() >= total_deadline:
                raise WorkflowStop('total_timeout')
            if step.action in {'input', 'click'}:
                _audit(journal, {'event': 'intent', 'index': index, 'action': step.action})
                # Journal I/O is included in both deadlines. Check again before dispatch.
                if cancel_event is not None and cancel_event.is_set():
                    raise WorkflowStop('cancelled')
                if time.monotonic() >= min(deadline, total_deadline):
                    raise WorkflowStop('total_timeout' if time.monotonic() >= total_deadline else 'step_timeout')
                pending_mutation = True
            parent.send_bytes(json.dumps({'action': step.action, 'target': step.target,
                                          'value': step.value}, ensure_ascii=True).encode('utf-8'))
            value = _receive(parent, parent if dom else process, deadline, total_deadline, cancel_event)
            if pending_mutation:
                _audit(journal, {'event': 'acknowledged', 'index': index, 'action': step.action})
                pending_mutation = False
            # A persisted ACK remains known even if its audit consumed the budget.
            _checkpoint(deadline, total_deadline, cancel_event)
            destination = step.next
            if step.action == 'assert' and (type(value) is not type(step.value) or value != step.value):
                if step.on_false is None:
                    raise WorkflowStop('assertion_failed')
                destination = step.on_false
            _audit(journal, {'event': 'step_completed', 'index': index, 'action': step.action})
            # Do not accept/count this step or dispatch the next one after a late audit.
            _checkpoint(deadline, total_deadline, cancel_event)
            if step.action == 'read':
                result.values[step.id] = value
            result.completed_steps += 1
            index = positions[destination] if destination is not None else index + 1
        if cancel_event is not None and cancel_event.is_set():
            raise WorkflowStop('cancelled')
        if time.monotonic() >= total_deadline:
            raise WorkflowStop('total_timeout')
        result.status = result.reason = 'completed'
    except WorkflowStop as exc:
        result.reason = str(exc)
        result.status = 'timed_out' if result.reason.endswith('_timeout') else 'failed'
        if result.reason == 'cancelled':
            result.status = 'cancelled'
    except (EOFError, ValueError):
        result.reason = 'worker_io_error'
    except OSError:
        result.reason = 'io_error'
    finally:
        if dom:
            try:
                if not parent.close()['verified']:
                    result.status, result.reason = 'failed', 'cleanup_failed'
            except (OSError, ValueError):
                result.status, result.reason = 'failed', 'cleanup_failed'
        else:
            child.close()
            parent.close()
        if process is not None and process.pid is not None:
            process.join(0.2)
            if process.is_alive():
                process.terminate()
                process.join(0.2)
            if process.is_alive():
                process.kill()
                process.join(0.2)
            if process.is_alive():
                result.status, result.reason = 'failed', 'cleanup_failed'
            else:
                process.close()
        if pending_mutation:
            result.status = 'unknown'
        if journal is not None:
            try:
                _audit(journal, {'event': 'execution_finished', 'status': result.status,
                                 'reason': result.reason, 'completedSteps': result.completed_steps})
            except OSError:
                result.status = 'unknown' if pending_mutation else 'failed'
                result.reason = 'audit_error'
            try:
                journal.close()
            except OSError:
                result.status = 'unknown' if pending_mutation else 'failed'
                result.reason = 'audit_close_error'
    # Cleanup and evidence finalization consume the total budget too. Their OS I/O
    # is not forcibly preemptible, but a late close must never publish success.
    if result.status == 'completed':
        if cancel_event is not None and cancel_event.is_set():
            result.status = result.reason = 'cancelled'
        elif time.monotonic() >= total_deadline:
            result.status, result.reason = 'timed_out', 'total_timeout'
    return result
