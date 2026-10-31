"""Restricted fixture/owned-DOM CLI; the legacy entrypoint is unchanged."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import signal
import threading

from .workflow import CAPABILITIES, DOM_CAPABILITIES, run_workflow


class Cancellation:
    def __init__(self, marker: Path | None):
        self.event = threading.Event()
        self.marker = marker

    def is_set(self):
        return self.event.is_set() or self.marker is not None and self.marker.exists()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('invalid_workflow')
        result[key] = value
    return result


def _reject_constant(_value):
    raise ValueError('invalid_workflow')


def load_workflow(path: Path):
    if not path.is_file():
        raise ValueError('invalid_workflow')
    with path.open('rb') as handle:
        raw = handle.read(65537)
    if len(raw) > 65536:
        raise ValueError('invalid_workflow')
    return json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restricted fixtures or two new owned local DOM apps; never existing windows')
    parser.add_argument('--workflow', type=Path, required=True)
    parser.add_argument('--adapter', choices=sorted(CAPABILITIES), required=True)
    parser.add_argument('--workspace', type=Path, required=True,
                        help='Owned persistent fixture workspace; preserve it to reject replays')
    parser.add_argument('--cancel-file', type=Path,
                        help='Stop when this caller-owned marker exists; contents are never read')
    args = parser.parse_args(argv)
    fixture_only = args.adapter not in DOM_CAPABILITIES
    cancellation = Cancellation(args.cancel_file)
    previous = signal.signal(signal.SIGINT, lambda _signum, _frame: cancellation.event.set())
    try:
        try:
            payload = load_workflow(args.workflow)
            result = run_workflow(payload, args.adapter, args.workspace, cancel_event=cancellation)
            summary = {'status': result.status, 'reason': result.reason,
                       'completedSteps': result.completed_steps, 'fixtureOnly': fixture_only}
        except (ValueError, UnicodeError, RecursionError):
            summary = {'status': 'rejected', 'reason': 'invalid_workflow', 'fixtureOnly': fixture_only}
        except OSError:
            summary = {'status': 'failed', 'reason': 'input_io_error', 'fixtureOnly': fixture_only}
    finally:
        signal.signal(signal.SIGINT, previous)
    # Never echo workflow values, identifiers, raw exceptions or read results to logs/console.
    print(json.dumps(summary, sort_keys=True))
    return {'completed': 0, 'cancelled': 130, 'timed_out': 3, 'unknown': 4}.get(summary['status'], 2)


if __name__ == '__main__':
    raise SystemExit(main())
