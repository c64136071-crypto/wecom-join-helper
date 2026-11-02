"""Build an auditable source/launcher ZIP, not a frozen application.

Inputs are explicit: never traverse a dirty worktree or a private release tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

# Fixed names only; never a glob, directory enumeration or Git index.
FILES = tuple('''
LICENSE README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md
.gitattributes .gitignore
requirements.txt requirements-dev.txt config.example.json portable.marker
run_app.pyw workflow.cmd JoinHelper.spec
installer/JoinHelper.iss
scripts/build_release.ps1 scripts/build_installer.ps1
scripts/frozen_smoke_test.ps1 scripts/installer_smoke_test.ps1
scripts/build_workflow_source.py
assets/wecom-rusher.ico assets/smoke/ocr-title.png
'''.split()) + tuple('wecom_rusher/' + name + '.py' for name in '''
__init__ __main__ app config logging_utils notify ocr paths release runner
schedule settings smoke state ui vision
workflow workflow_adapters workflow_cli workflow_dom workflow_start
'''.split()) + tuple('''
wecom_rusher/workflow_dom_bridge.cjs
wecom_rusher/workflow_dom_capture.cjs
wecom_rusher/owned_apps/form.html wecom_rusher/owned_apps/form.js
wecom_rusher/owned_apps/report.html wecom_rusher/owned_apps/report.js
wecom_rusher/owned_apps/server.cjs
examples/workflow-form.json examples/workflow-report.json
examples/workflow-dom-form.json examples/workflow-dom-report.json
docs/architecture.md docs/compatibility.md docs/release-checklist.md docs/troubleshooting.md
docs/workflow-runner.md docs/workflow-dom.md docs/workflow.schema.json
docs/workflow-dom-reliability.md
docs/recruitment-delivery.md docs/workflow-start.md docs/desktop-maintenance.md
docs/assets/join-helper-main.png docs/assets/join-helper-demo.gif
templates/README.md templates/join.png templates/participate.png
templates/submit.png templates/yellow_icon.png
tools/workflow/package.json tools/workflow/package-lock.json
tests/test_workflow_start.py tests/test_workflow_source.py tests/test_workflow_runner.py
tests/test_workflow_dom_reliability.py
'''.split())


def build(source: Path, archive: Path):
    if archive.exists():
        raise FileExistsError('archive_already_exists')
    source = source.resolve()
    content = {}
    for name in FILES:
        path = source / name
        if not path.resolve().is_relative_to(source):
            raise OSError('source_input_outside_root')
        current = path
        while current != source:
            if current.is_symlink() or current.is_junction():
                raise OSError('linked_source_input_rejected')
            current = current.parent
        content[name] = path.read_bytes()
    manifest = {'kind': 'source-launcher-not-exe-or-installer',
                'files': {name: hashlib.sha256(raw).hexdigest() for name, raw in content.items()}}
    archive.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as package:
        for name, raw in content.items():
            package.writestr(name, raw)
        package.writestr('SOURCE-MANIFEST.json', json.dumps(manifest, indent=2) + '\n')
    return {'kind': manifest['kind'], 'inputFiles': len(content)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = build(Path(__file__).resolve().parents[1], args.output)
    except OSError:
        print(json.dumps({'status': 'failed', 'reason': 'source_or_output_not_ready'}))
        return 2
    print(json.dumps({'status': 'completed', **result}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
