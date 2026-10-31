# Restricted workflow runner — fixtures and isolated owned DOM

This is an additive software candidate, not a general RPA product or a verified
third-party desktop controller. `form` / `report` remain file fixtures. The fixed
`owned-dom-form` / `owned-dom-report` extension uses two new local web apps through
the same execution loop; see [owned DOM scope and usage](workflow-dom.md).
The existing `run_app.pyw`, `wecom_rusher`
legacy CLI/app, one-attempt runner, UI adapter and processed-card state remain
unchanged. Nothing automatically connects the new runner to WeCom.

## Run without installing desktop dependencies

From the source root, using an existing Python 3.12+ interpreter:

```powershell
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-form.json --adapter form --workspace <owned-persistent-workspace>
python -B -m wecom_rusher.workflow_cli --workflow examples/workflow-report.json --adapter report --workspace <owned-persistent-workspace>
python -B -m unittest discover -s tests -p test_workflow_runner.py -v
```

Replace `<owned-persistent-workspace>` with an explicitly chosen writable test
directory. No paths are taken from workflow values. This CLI uses only the Python
standard library; it does not import the GUI app, OCR, mouse, keyboard or window APIs.
Do not install or change global dependencies just to run these fixtures.

The form fixture stores `[{"name":"Ada","quantity":2}]` in `records.json`.
The report fixture filters its fixed trusted data by period and exports the CSV
`period,total\n2026-10,20\n`. These are actual file-backed fixture outputs, not real
application receipts. The fixtures are different business scenarios sharing one
kernel; all form/report decisions live in `workflow_adapters.py`.

## Contract and restrictions

`docs/workflow.schema.json` documents the shape. `validate_workflow` is the
runtime authority (standard-library checks, no JSON Schema package required).
The JSON file and normalized ASCII-escaped JSON must each be at most 65536 bytes.
Duplicate JSON keys, NaN/Infinity, unknown fields and non-scalar values are rejected.
Identifiers contain 1–64 ASCII letters/digits/underscore/hyphen, starting with a letter.
Numbers must be finite, integer literals have magnitude at most 10^12, strings at
most 4096 characters. Deadline/wait/version integers must be lexical integers,
not booleans or float literals. JSON Schema cannot express every lexical or
cross-step runtime rule; passing a third-party shape validator is not authorization.

A plan has `version=1`, opaque `runId`, total `timeout_ms` (1–60000), and 1–64
steps. Each step requires `id/action/target/value/timeout_ms` (1–10000). IDs are
unique; optional `next` and assertion-only `on_false` must name a strictly later
step. Default is the next array element. No backward jumps, loops, expressions,
eval, shell actions, arbitrary code, plugin imports or retry fields exist.
The entire plan is validated and copied into immutable step objects before any
workspace files or worker are created.

| Action | Fixture behavior |
|---|---|
| locate | Require one semantic target in the bound fixture; no window discovery |
| read | Read the current fixture field/receipt; raw result is API memory only |
| input | Validate and assign a fixture field; treated as a mutation |
| click | Execute an allowlisted fixture operation (save/export); treated as a mutation |
| wait | Milliseconds in `value`, null target, cancellable by killing the fixture worker |
| assert | Strict type-and-value equality against an actual fixture read; fail closed or take `on_false` |

Form capabilities: `name`, `quantity`, `save`, `receipt`. Name is a nonempty string
of at most 128 characters; quantity is an integer from 1 to 10000. Report
capabilities: `period`, `export`, `total`, `receipt`; period is `2026-10` or
`2026-09`. Action/target role and field validity are rechecked by the trusted
adapter. Every target access rechecks fixture identity and unique-match metadata,
including immediately before mutations. Reordering a fixture's field dictionary
is not a DPI/layout/window compatibility test. Identity and ambiguous-match tests
are simulations, not UIA/DOM observation.

## Cancellation and complete execution deadline

One persistent `spawn` subprocess owns the fixture session for the run. The
parent polls its bounded JSON pipe, cancellation and monotonic step/total
deadlines. Worker startup, validation, reservation and journal overhead consume
the total execution budget. Each step budget starts before intent logging and
dispatch; late responses are not accepted. File parsing before entering the
runner is bounded in size, but not included in the plan execution deadline.

Use Ctrl+C in the fixture CLI, a caller-owned `--cancel-file <marker>` (existence
only; contents are never read), or the API `cancel_event.is_set()` contract.
Pre-cancellation creates no workspace. Cancellation/timeouts stop later steps,
then close IPC, bounded-join, terminate and if necessary kill/join the owned worker.
No thread is abandoned to execute a delayed mutation after return. Worker startup,
OS process operations, local filesystem/fsync and cleanup can add latency; this
is not an end-to-end hard-real-time SLA, and not suitable for untrusted adapters
or wedged/network filesystems. The workspace must be trusted, local and exclusively
owned by the operator, without hostile concurrent filesystem modification.

## Conservative replay and audit semantics

Each run atomically reserves `<workspace>/<SHA256(runId)>/` before worker startup.
The directory is never removed automatically. The same runId in the same workspace
is rejected on any later attempt—even for a changed plan, another adapter, an
incomplete/corrupt journal, a cancelled run or a confirmed successful run. There is
no resume/retry option. Atomic directory reservation also rejects concurrent starts.

Before every input/click, parent audit writes `intent`, flushes and fsyncs before
dispatch. A success reply is recorded as `acknowledged`; an exception, process exit,
cancellation or timeout with an unacknowledged mutation returns `unknown`.
Terminating the worker does not undo an already-created output file or an external
commit. Unknown results require manual reconciliation, not another click. An
adapter rejection after dispatch is also conservatively unknown. A lost-ack test
uses a real fixture file write and intentionally withholds the IPC reply.

Reservations cover normal process restarts on the preserved local filesystem,
not a power-loss-proof transaction database. Changing runId/workspace, deleting
reservations or an administrator editing files bypasses this local guard; this is
not global business idempotency. There is no automatic recovery of unknown results.
Real applications will require application-specific receipts, durable identity,
transaction recovery and session ownership before being attached.

`audit.jsonl` records only the run hash, step ordinal, action and fixed status/reason
codes: no workflow values, targets, step IDs, raw exceptions or read contents.
`execution_finished` is an execution observation, not proof that the subsequent
journal close succeeded. Only the returned result/CLI exit after worker cleanup
and journal close is the outcome; audit or close failures cannot report completed.
Fixture artifacts intentionally contain the fixture's business data, so they are
not automatically public/redacted audit logs. Keep workspaces private as needed.

CLI prints a redacted JSON summary. Exit codes: 0 completed; 2 rejected/failed;
3 timed out without an unacknowledged mutation; 4 unknown; 130 cancelled without
an unacknowledged mutation. With unknown mutation + cancellation, exit is 4.

## Acceptance boundary

The software tests exercise file fixtures, schema/CLI rejection, forward branches,
late/blocked execution, total startup/cumulative budgets, cancellation, process
cleanup, conservative lost-ack/crash handling, same-run reservation, redaction and
simulated identity/ambiguity. Legacy core tests use fakes, never real WeCom.
The fixture evidence above does not establish GUI control. The separate owned-DOM
candidate exercises two self-owned web apps, not Windows UIA, third-party software,
OCR generalization, DPI/occlusion/modal/focus tolerance, a desktop success rate,
an installed package, physical equipment or production business acceptance.
No existing application can be selected by changing a title, URL or selector in
workflow JSON; those fields do not exist. Independent review remains coordinator-owned.
