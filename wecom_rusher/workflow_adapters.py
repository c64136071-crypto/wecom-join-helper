"""Trusted, file-backed simulations only. No UIA/DOM, window or input APIs."""
from __future__ import annotations

import json
from pathlib import Path
import time


MAX_MESSAGE_BYTES = 65536
CAPABILITIES = {
    'form': frozenset({'name', 'quantity', 'save', 'receipt'}),
    'report': frozenset({'period', 'export', 'total', 'receipt'}),
}


class FixtureGuard:
    def __init__(self, name):
        self.expected_identity = f'owned-fixture:{name}'
        self.identity = self.expected_identity
        self.matches = {target: 1 for target in CAPABILITIES[name]}

    def guard(self, target):
        if self.identity != self.expected_identity:
            raise ValueError('target_identity_changed')
        if self.matches.get(target) != 1:
            raise ValueError('target_not_unique')


class FormFixture(FixtureGuard):
    def __init__(self, output: Path):
        super().__init__('form')
        self.output = output
        self.fields = {'name': '', 'quantity': 0}
        self.records = []

    def execute(self, action, target, value):
        if action == 'wait':
            time.sleep(value / 1000)
            return None
        if target not in CAPABILITIES['form']:
            raise ValueError('unsafe_target')
        self.guard(target)
        if action == 'locate':
            return True
        if action in {'read', 'assert'}:
            if target == 'receipt':
                return len(self.records)
            if target in self.fields:
                return self.fields[target]
            raise ValueError('adapter_rejected')
        if action == 'input':
            if target == 'name' and isinstance(value, str) and 1 <= len(value) <= 128:
                self.fields[target] = value
            elif target == 'quantity' and type(value) is int and 1 <= value <= 10000:
                self.fields[target] = value
            else:
                raise ValueError('adapter_rejected')
            return None
        if action == 'click' and target == 'save' and self.fields['name'] and self.fields['quantity']:
            self.records.append(dict(self.fields))
            with (self.output / 'records.json').open('w', encoding='utf-8') as handle:
                json.dump(self.records, handle, ensure_ascii=False)
            return None
        raise ValueError('adapter_rejected')


class ReportFixture(FixtureGuard):
    def __init__(self, output: Path):
        super().__init__('report')
        self.output = output
        self.period = ''
        self.total = 0
        self.receipt = 0
        self.rows = (('2026-10', 12), ('2026-10', 8), ('2026-09', 99))

    def execute(self, action, target, value):
        if action == 'wait':
            time.sleep(value / 1000)
            return None
        if target not in CAPABILITIES['report']:
            raise ValueError('unsafe_target')
        self.guard(target)
        if action == 'locate':
            return True
        if action in {'read', 'assert'} and target in {'period', 'total', 'receipt'}:
            return getattr(self, target)
        if action == 'input' and target == 'period' and value in {'2026-10', '2026-09'}:
            self.period = value
            return None
        if action == 'click' and target == 'export' and self.period:
            self.total = sum(amount for period, amount in self.rows if period == self.period)
            with (self.output / 'export.csv').open('w', encoding='utf-8', newline='') as handle:
                handle.write(f'period,total\n{self.period},{self.total}\n')
            self.receipt += 1
            return None
        raise ValueError('adapter_rejected')


def create_fixture(name, output):
    if name == 'form':
        return FormFixture(output)
    if name == 'report':
        return ReportFixture(output)
    raise ValueError('invalid_adapter')


def fixture_worker(connection, name, output):
    """One persistent trusted fixture session; never loads user Python plugins."""
    try:
        adapter = create_fixture(name, Path(output))
        connection.send_bytes(b'{"ok":true,"value":null}')
        while True:
            raw = connection.recv_bytes(MAX_MESSAGE_BYTES)
            if not raw:
                break
            step = json.loads(raw)
            try:
                value = adapter.execute(step['action'], step['target'], step['value'])
                reply = {'ok': True, 'value': value}
            except Exception:
                reply = {'ok': False, 'reason': 'adapter_rejected'}
            connection.send_bytes(json.dumps(reply, ensure_ascii=True).encode('utf-8'))
    except (EOFError, OSError):
        pass
    finally:
        connection.close()
