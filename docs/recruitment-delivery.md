# Source delivery: restricted workflow extension

This entry separates three existing capabilities. The GUI application's published
v1.0.10 installer/portable build remains the legacy visual helper. The workflow
extension is delivered as source, not a new validated installer or general RPA
product. Its fixed CLI never connects itself to WeCom or another existing app.

## 1. File fixture: the smallest reproducible entry

From this source repository, use an existing Python 3.12+ interpreter. This path
uses only the standard library; it does not import OCR/GUI dependencies or open a
browser. No global package installation, Java or Maven change is required.

Example in PowerShell, for a separately intended first demonstration:

```powershell
python --version
$workspace = Join-Path $env:LOCALAPPDATA 'JoinHelper\owned-fixture-20261101'
if (Test-Path $workspace) { throw 'Preserve the existing reservation; reconcile its result before doing anything else.' }
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-form.json --adapter form --workspace $workspace
```

Expected outcome, not a fabricated execution log: exit 0 and a redacted summary
with `status=completed`, `fixtureOnly=true`. Under the SHA-256 reservation folder,
`artifacts/records.json` contains the synthetic example `[{"name":"Ada","quantity":2}]`;
`audit.jsonl` contains status observations, not raw field values. The fixed report
fixture separately uses `examples/workflow-report.json` and adapter `report`.
See [runner semantics](workflow-runner.md) and [workflow shape](workflow.schema.json).

Keep the reservation. Do not change run IDs/workspaces to replay an unknown
mutation, delete the old directory, or interpret process termination as rollback.
The same run in the same workspace rejects instead of retrying a write.

## 2. Two owned web apps: real DOM, explicit dependencies

The same kernel also implements `owned-dom-form` and `owned-dom-report`. They
create two disposable loopback web apps with their own browser context, input
fields, server-side records and CSV download. This is actual DOM control, not a
file fixture, Windows native UIA or arbitrary third-party application support.

It requires Windows, an existing Node executable, an existing Node Playwright
package, and an existing Chrome executable. Bind `OWNED_DOM_NODE`,
`OWNED_DOM_PLAYWRIGHT`, `OWNED_DOM_BROWSER` only in the calling child process using
trusted local paths. Do not use a personal browser profile, an existing CDP
endpoint, or a company window. Nothing here installs a browser or changes network
settings. See [owned DOM usage](workflow-dom.md) for exact lifecycle and scope.

With those paths verified and permission to create the two disposable apps:

```text
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-dom-form.json --adapter owned-dom-form --workspace <new-owned-local-workspace>
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-dom-report.json --adapter owned-dom-report --workspace <another-new-owned-local-workspace>
```

Replace the explicitly marked workspace placeholders. Successful application
records/receipts are in `artifacts/app-records.json`; report evidence includes both
`artifacts/app-export.csv` and browser-downloaded `artifacts/export.csv`, bound to
app instance/receipt and exact bytes. Owned-process/listener/profile cleanup is
recorded in `owned-dom/cleanup.json`. `fixtureOnly=false` does not imply a
third-party application or physical-device test.

The accepted local source scope includes two headed DOM workflows, conservative
unknown-ACK handling, replay rejection, cancellation, identity/navigation refusal
and precise owned-resource cleanup. Earlier documents called them candidates at
the time they were written; that wording is historical, not a pending approval
for the accepted unchanged source. The source release does not rerun that entire
acceptance or publish private local logs.

## 3. Tests and publication boundary

The previous 106-test and install/uninstall claims belong to legacy v1.0.10, not a
summed new-runner total. Runner, DOM, CLI and independent-review populations are
separate and can overlap.

Public CI runs the core/file-fixture test files. It deliberately excludes
`test_workflow_dom.py` and `test_workflow_dom_cli.py`: those require an explicit
owned `P3_DOM_EVIDENCE` root and verified Node/Playwright/browser bindings. Their
module imports must not be mistaken for a clean-machine CI setup. The tests remain
in source for explicitly authorized local use; no browser test is claimed as a CI
pass when excluded. Avoid whole-repository discovery in a private working tree
with protected untracked screenshots or release directories.

The source preview has no new installer, portable GUI package, compatibility
matrix, production success rate or industrial validation. Existing GUI entrypoints,
core safety policy and version string are unchanged. No private screenshots,
company material, configuration values or unrelated release artifacts are part of
this extension. Checksums establish byte identity, not data provenance, signatures
or power-loss durability.
