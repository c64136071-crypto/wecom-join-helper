# Two self-owned DOM applications — restricted candidate

This extension controls **only two disposable local web applications**, not existing
browser tabs, Windows native UIA, WeCom, company applications or a general RPA system.
`owned-dom-form` saves inventory records; `owned-dom-report` filters fixed data and
downloads CSV. Both use the original `run_workflow` loop, validator, persistent run
reservation, audit, forward branches, cancellation and deadlines. The original
`form` / `report` file-fixture adapters and old desktop entrypoint remain unchanged.
A passing implementer run is a candidate, not independent approval.

## Trusted dependencies and launch

Windows, an already-installed Python, Node.js, Node Playwright and system Chrome
are required. This project does not install browsers/packages or change policies.
The operator supplies the previously verified executable/package locations through
**child-process-only** `OWNED_DOM_NODE`, `OWNED_DOM_PLAYWRIGHT`, `OWNED_DOM_BROWSER`.
They are trusted toolchain bindings, never workflow fields. `OWNED_DOM_HEADLESS=1`
is for developer headless runs; unset it or use `0` for the default headed mode.
Never use a real user profile, an existing CDP endpoint or port9222.

From the source root, inside that configured child process:

```text
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-dom-form.json --adapter owned-dom-form --workspace <new-owned-local-workspace>
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-dom-report.json --adapter owned-dom-report --workspace <another-new-owned-local-workspace>
```

The batch evidence recorder supplies the verified paths and isolated environment;
its real CLI tests explicitly set headed mode. Do not modify global environment
variables or company Java/Maven settings. Keep a reasonably short workspace path:
the kernel adds a 64-character reservation and Chrome/Windows add profile suffixes.
An overly deep Windows path is not a reason to drop profile isolation or safety flags.

These fixed example run IDs are reserved permanently in each chosen workspace.
A repeat must reject, including after unknown/cancelled outcomes. Do not change
run IDs or workspaces to blindly repeat an uncertain mutation. A fresh workspace
is appropriate only for a separately intended independent demonstration, not recovery.

## Actions, receipts and actual outputs

Workflow version/size/scalar limits and six actions are unchanged. There are no
URL, JavaScript, shell, plugin, selector, download filename or retry fields.

| Adapter | Targets | Typed input | Mutation/output |
|---|---|---|---|
| owned-dom-form | name, quantity, save, receipt | name nonempty <=128 UTF-16 code units; quantity integer1..10000 | real fill/input events, submit click, own HTTP POST; app-records.json persisted before receipt |
| owned-dom-report | period, export, total, receipt | period exactly2026-10 or2026-09 | real select/change event, export click, browser download |

The form's default quantity is1. Its app records include input-event count,
instanceId and monotonically increasing receipt. Report totals are20 for2026-10
and99 for2026-09. Expected CSV is UTF-8 with LF, e.g. `period,total\n2026-10,20\n`.
The server independently preserves `app-export.csv` and `app-exports.json` with
receipt, instance, byte length and SHA-256; the browser saves actual downloaded
bytes to the fixed `export.csv`. Tests compare the raw bytes and app receipt,
not merely receipt0 or an adapter-authored summary.

Run output remains `<workspace>/<SHA256(runId)>/`:

- `audit.jsonl`: redacted execution observations (not the authoritative final outcome).
- `artifacts/`: app records, app export metadata/bytes, downloaded CSV, DOM-event
  count observations and real initial/final PNG screenshots. These application
  artifacts intentionally contain owned test values and are not redacted logs.
- `owned-dom/`: Node/browser stdout/stderr, PID/creation-time Job ownership,
  startup/resource receipts, bounded JSON IPC and exact cleanup report.

CLI summaries correctly use `fixtureOnly=false` for the DOM adapters and true
for file fixtures. Read values and test data are not printed. Existing exit codes
remain:0 completed;2 rejected/failed;3 timed out;4 unknown;130 cancelled. Unknown
with cancellation remains4.

## Fail-closed boundary and lifecycle

A new profile and redirected HOME/AppData/temp are created for each new session.
**Both owned LOCALAPPDATA and APPDATA directories must be mkdir'ed before Chrome**;
the accepted browser recovery depends on this. HTTP and CDP use owned random
literal127.0.0.1 ports, excluding formal ports. No browser/user-window discovery occurs.
The parent owns the native kill-on-close Job and retains process handles/times.
Node waits for parent assignment before creating its server/browser; a pre-start
stop marker prevents late resource creation. No killable daemon worker owns the Job.

Every target access checks canonical origin/path, appId, instanceId, one frame and
one visible exact semantic locator. Inputs are typed and fixed-role validated;
mutations recheck identity before acknowledgement. Routes are fixed, response/IPC
payloads bounded. Off-origin requests, other navigations/frames, redirects and
popups are refused; context refusal is latched so later steps cannot resume after
a popup is closed. Redirect checks use a single no-redirect/no-retry owned fetch,
not a follow-then-inspect response. Download paths ignore suggested filenames.
The own server also validates Host/Origin, exact body keys, input types/limits and
instance binding. Fixed application assets/paths are not arbitrary file serving.

The parent polls cancellation and frozen step/total monotonic deadlines. Startup,
action, screenshot/IPC acknowledgement, audit and final cleanup consume budget;
late replies cannot be accepted. The OS/filesystem is not forcibly preemptible or
hard-real-time. Cleanup has bounded independent grace/kill/readback stages; shutdown
keeps observing Job membership and discovers final resource receipts after drain.
It verifies retained exact-process exit, recorded listener absence and owned-temp
removal. No process-name/port-based kill occurs.

A durable server commit followed by missing/delayed ACK remains **unknown**. Killing
Chrome/Node is not a transaction rollback. The preserved reservation rejects replay,
no subsequent action is sent, and manual artifact reconciliation is required.
A rejected mutation after dispatch is also conservatively unknown; this does not
claim that it committed. Workspace trust and local reservation limits are unchanged.

## Tests and intentionally limited fixture controls

Run the explicit affected modules only, with `P3_DOM_EVIDENCE` and all TEMP/AppData
under a newly authorized owned evidence directory; never run root hygiene discovery
against protected screenshots/release trees. `test_workflow_dom.py` covers actual
DOM actions, app storage/downloads, identity/ambiguity, compact/reordered layout,
delay, cancellation, unknown/replay and precise cleanup. `test_workflow_dom_cli.py`
runs the two headed project CLI workflows, reads raw app outputs and checks replay.
`test_workflow_runner.py` remains the separate33-test fixture/kernel regression.
Do not add overlapping suite/method/CLI populations into one advertised total.

Tests may create a bounded `test-control.json` only inside their new own application
root before the parent's start handshake. The fixture can delay a commit, drop its
ACK, change identity, duplicate a target, reorder layout or exercise redirect/popup/
off-origin gates against the same owned listener. No workflow/CLI fault-injection
option, generic HTTP debug endpoint, arbitrary selector or arbitrary script is
exposed. Test controls and supplied images have no relationship.

This candidate does not establish third-party/native cross-application operation,
DPI/focus/occlusion tolerance, a production success rate, physical devices or
industrial image performance. It does not install/publish a package, change a
resume or automatically continue any later batch.
