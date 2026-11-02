"""Safe example launcher, separate from the original GUI entrypoint."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def dependency_report(mode, node, playwright, browser):
    checks = {'python': {'ready': sys.version_info >= (3, 12),
                        'version': '.'.join(map(str, sys.version_info[:3])), 'required': '>=3.12'}}
    if mode == 'dom':
        checks.update(windows={'ready': os.name == 'nt'},
                      node={'ready': False, 'required': '>=20'},
                      playwright={'ready': False, 'required': '1.56.1 (pinned)'},
                      browser={'ready': Path(browser).is_file(),
                               'check': 'executable presence only; real owned startup is a separate gate'})
        try:
            if Path(node).is_file():
                result = subprocess.run([node, '--version'], capture_output=True, text=True, timeout=10)
                version = result.stdout.strip().removeprefix('v')
                checks['node'].update(version=version, ready=result.returncode == 0 and int(version.split('.')[0]) >= 20)
                if checks['node']['ready'] and Path(playwright).is_dir():
                    probe = "const p=process.argv[1]; const m=require(p); console.log(JSON.stringify({version:require(require('node:path').join(p,'package.json')).version,api:typeof m.chromium.connectOverCDP==='function'}))"
                    result = subprocess.run([node, '-e', probe, playwright], capture_output=True, text=True, timeout=10)
                    data = json.loads(result.stdout) if result.returncode == 0 else {}
                    checks['playwright'].update(version=data.get('version'),
                                                ready=data.get('version') == '1.56.1' and data.get('api') is True)
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass  # Fixed public diagnostics, never echo a dependency's raw error.
    ready = all(item['ready'] for item in checks.values())
    return {'mode': mode, 'ready': ready, 'reason': 'dependencies_ready' if ready else 'dependency_not_ready',
            'checks': checks, 'remedy': 'Use Python >=3.12; for DOM use Windows, Node >=20, npm ci --prefix tools/workflow --cache .runtime/npm-cache --ignore-scripts, and an installed Chrome executable; see docs/workflow-start.md.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Restricted owned examples; never existing apps')
    parser.add_argument('--check', action='store_true', help='Check dependencies without opening apps')
    parser.add_argument('--mode', choices=('file', 'dom'), default='file')
    parser.add_argument('--node', type=Path, help='Trusted Node executable (default: PATH)')
    parser.add_argument('--playwright', type=Path, help='Trusted pinned package directory')
    parser.add_argument('--browser', type=Path, help='Installed Chrome executable; never a profile')
    parser.add_argument('--example', choices=('form', 'report'), default='form')
    parser.add_argument('--workspace', type=Path, help='Owned persistent output directory; preserve reservations')
    parser.add_argument('--cancel-file', type=Path, help='Stop when this owned marker exists')
    args = parser.parse_args(argv)
    node = str((args.node or Path(shutil.which('node') or 'missing-node')).resolve())
    playwright = str((args.playwright or ROOT / 'tools/workflow/node_modules/playwright').resolve())
    browser = str((args.browser or Path(os.environ.get('PROGRAMFILES', 'C:/Program Files')) / 'Google/Chrome/Application/chrome.exe').resolve())
    report = dependency_report(args.mode, node, playwright, browser)
    if args.check or not report['ready']:
        print(json.dumps(report, sort_keys=True))
        return 0 if report['ready'] else 2
    if args.workspace is None:
        parser.error('--workspace is required to run an example; use --check for dependencies')
    from .workflow_cli import main as run_cli
    prefix = 'dom-' if args.mode == 'dom' else ''
    adapter = ('owned-dom-' if args.mode == 'dom' else '') + args.example
    workflow = ROOT / 'examples' / f'workflow-{prefix}{args.example}.json'
    command = ['--workflow', str(workflow), '--adapter', adapter, '--workspace', str(args.workspace)]
    if args.cancel_file is not None:
        command += ['--cancel-file', str(args.cancel_file)]
    bindings = {'OWNED_DOM_NODE': node, 'OWNED_DOM_PLAYWRIGHT': playwright,
                'OWNED_DOM_BROWSER': browser, 'OWNED_DOM_HEADLESS': '0'} if args.mode == 'dom' else {}
    previous = {key: os.environ.get(key) for key in bindings}
    try:
        os.environ.update(bindings)
        return run_cli(command)
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


if __name__ == '__main__':
    raise SystemExit(main())
