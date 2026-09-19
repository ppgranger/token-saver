---
title: Architecture
description: How Token-Saver separates processors, compression policy, opt-in Delta comparisons, quality checks, platform hooks, and local persistence.
permalink: /architecture/
nav_order: 7
---

# Token-Saver architecture

Token-Saver separates command-specific parsing from compression orchestration,
quality checks, and integrations. These boundaries let contributors add a
processor or evaluate captured output without changing platform hooks.

The design applies SOLID principles at concrete extension points: explicit
processor inventories, a shared command policy, small compression and tracking
contracts, and pure comparison and presentation functions. Default adapters
provide configuration, discovery, persistence, and host integration. Historical
entry points remain available as compatibility facades.

## Responsibilities and dependencies

```text
Claude JSON hook ----+-> command policy <- wrapper / core / CLI explain
                    |
                    +-> shell wrapper -> core -> engine -> processors
Antigravity hook ----------------------> core      |           |
                                         |     registry    diagnostics
                                         v
                                     telemetry -> tracker (SQLite)

CLI stats -> tracker queries -> pure statistics formatting
CLI compress / replay -> quality evaluation -> Compressor interface

Claude completed output -> Delta -> redaction -> processor diagnostics
                             |
                             +-> pure comparison -> rendering / size decision
                             +-> snapshot store (SQLite)
CLI delta show / clear -------> snapshot store
```

The registry supplies the ordered processor list and named fallback. The engine
uses those objects directly; it does not ask the registry to parse output.

| Module | Responsibility | Boundary |
|---|---|---|
| `src/processors/__init__.py` | Discover built-in and configured user processors. | Imports plugin code and supplies instances; discovery is skipped when callers inject processors. |
| `src/registry.py` | Order active processors, build name lookup, and collect hook patterns. | Accepts instances and disabled names; reads no configuration and imports no plugins. |
| `src/engine.py` | Select processors, apply chaining, cleanup, recovery, and acceptance thresholds. | Accepts optional processors and an `EngineSettings` reader. |
| `src/processors/` | Recognize commands and transform their output. | Implement the `Processor` contract. |
| `src/evaluation.py` | Measure a compression result and check a `QualityPolicy`. | Requires only the small `Compressor` protocol; performs no file or CLI I/O. |
| `src/replay.py` | Validate a replay manifest, read captures, and aggregate evaluations. | Filesystem adapter around evaluation; command labels are never executed. |
| `src/quality_cli.py` | Read CLI arguments/stdin and render quality results. | Connects the default engine to evaluation/replay and maps results to exit codes. |
| `src/core.py` | Adapt a compression backend to the result consumed by both hosts. | Requires the small `Compressor` protocol; delegates optional recording through compatible entry points. |
| `src/command_policy.py` | Apply shell exclusions and processor command patterns. | `CommandPolicy(patterns)` accepts explicit patterns; interception and explanation share one evaluator, independent of host JSON. |
| `src/telemetry.py` | Own optional audit logging and savings/mismatch writes. | Initializes the audit journal on first use; an injectable `SavingsWriter` factory owns write sessions and closes them on errors. |
| `src/stats_formatting.py` | Convert aggregate values into the historical savings summary. | Pure functions receive statistics and the conversion ratio; no configuration, SQLite, or terminal access. |
| `src/stats.py` | Query statistics and present terminal/JSON output. | Accepts explicit arguments without modifying the host process arguments. |
| `src/updater.py` | Coordinate release checks, source updates, and installation refresh. | Dedicated side-effecting update adapter; the CLI passes its installation root and delegates. Compression never calls it. |
| `scripts/` and `antigravity/` | Implement host protocols and shell execution where required. | Claude wraps commands before execution; Antigravity receives captured output. |
| `src/tracker.py` | Store and query local savings, sessions, and processor mismatches. | SQLite persistence, separate from output transformation. |
| `src/diagnostics.py` | Define immutable observations and classify differences between snapshots. | Pure comparison returns ordered `Change` values; no persistence or presentation. |
| `src/delta.py` | Coordinate sanitized snapshots, storage, and rendering. | Uses the same classified observations for presentation and detail preservation; does not execute commands. |
| `src/delta_redaction.py` | Mask recognized secret formats before Delta uses captured output. | Deterministic text transformation; not a universal secret detector. |
| `src/delta_store.py` | Retain private, bounded, expiring snapshots. | Separate SQLite database containing already sanitized payloads and hashed scope metadata. |
| `src/delta_cli.py` | Read snapshot details and clear retained history. | CLI presentation and status codes; does not rerun commands. |

## SOLID in practice

| Principle | Concrete boundary |
|---|---|
| Single responsibility | Processors parse; command policy decides eligibility; the wrapper executes; telemetry owns recording; stores persist; pure functions compare and format. |
| Open/closed | New processors supply command patterns and optional diagnostics; the policy, engine, and wrapper need no tool-specific branch. |
| Substitutability | Processors retain signatures and return shapes; the default diagnostic method declines with `None`. Injected compression backends retain status/metadata contracts and are used even when falsey. |
| Interface segregation | Evaluation requires only compression; core additionally consumes routing metadata. Telemetry requires only writer operations and closing, not database queries or presentation. |
| Dependency inversion | Engine processors/settings, policy patterns, compression backends, and telemetry writer factories are explicit dependencies. Domain comparison and formatting take values rather than reading global configuration. |

These are working boundaries, not a requirement to add an interface around every
function. The `open_store()` integration seam supplies the default persistence
adapter; format recognition remains entirely inside processors.

## Shared routing and optional recording

`CommandPolicy(patterns)` compiles an explicit inventory and applies the existing
shell exclusions. `is_compressible()` and `explain_decision()` use one evaluator,
so the explanation cannot drift from interception. `default_policy()` discovers
processors lazily and caches its inventory for the process; construct a new policy
for another inventory. A registry failure disables interception and records a
content-free warning. The Claude hook keeps JSON and command rewriting; core,
the wrapper, and the CLI do not import the hook adapter. Destructive-command
auto-approval checks remain an additional rule in the Claude adapter.

`core.compress()` accepts a structural `core.Compressor`: the existing
`compress()` signature plus read-only access to `last_event`. It creates the
default engine only when none is supplied. Its result tuple and historical
recording functions remain compatible. Importing core or compressing output alone
does not create an audit log or savings database.

`telemetry` owns those effects. Its audit handler opens lazily with UTF-8 and
reports initialization, write, or rotation failures without dumping the audit
record or traceback. Each savings/mismatch operation creates a writer through an
optional factory and closes it on both success and failure. A writer only needs
`record_saving`, `record_mismatch`, and `close`; SQLite queries and schemas stay
inside the concrete tracker. An empty mismatch batch opens no writer.

Statistics formatting receives aggregate values and an explicit conversion
ratio. The tracker retains its old formatting methods as thin compatibility
facades. `stats.main(argv=None)` reads process arguments only when no list is
provided; the CLI passes its own list without modifying `sys.argv`. Query
connections close even when an intermediate read fails. Tracker initialization
and recovery reuse the same schema, including indexes.

The CLI delegates update operations to `updater.update(repo_dir)`. This dedicated
adapter owns release fetching, Git/archive selection, installation refresh, and
progress messages. CLI parsing and compression have no responsibility for those
steps. Tests replace remote fetching and subprocess execution; they never update
a real user installation.

## Processor extension contract

A processor provides a stable name, priority, anchored hook patterns,
`can_handle(command)`, and `process(command, output)`. Discovery finds concrete
processor subclasses automatically. The registry sorts them by `(priority,
name)` and requires exactly one fallback named `generic`, at priority `999`,
after all other processors. Disabling processors does not remove that fallback.

Adding a tool family normally means adding its processor and tests, then updating
its documentation and public counts. It should not require tool-specific
branches in the engine or hooks. See the
[processor reference](processors/index.md) and the
[contributor guide](https://github.com/ppgranger/token-saver/blob/main/CONTRIBUTING.md).

The optional capabilities on `Processor` have behavioral obligations:

- `handles_failure` opts into processing output from a known failed command.
  Otherwise the engine selects the generic fallback for that failure.
- `wants_exit_code` means `process()` also accepts the `exit_code` keyword.
- `redacted_secrets()` identifies calls whose redacted result must survive the
  compression-ratio acceptance check. The engine exposes this fact in
  `last_event["redacted"]`; adapters must not reparse the original output after
  such a result, because custom masking rules may be unknown to them.
- `chain_to` requests secondary processors; the engine bounds chaining and
  avoids revisiting a processor.
- `diagnostics(command, output, *, exit_code=None)` optionally returns a
  `diagnostics.Snapshot` for complete, supported output. Its default returns
  `None`, so existing processors need no changes. The caller sanitizes input
  before parsing; uncertain formats must decline rather than infer results.

Implementations must remain compatible with these contracts. Precision tests,
failure fixtures, and the compression ratchet check concrete cases; they do not
establish that every possible output format is lossless.

## Delta comparison boundary

The experimental [Delta integration](delta.md) operates after a single Claude
wrapper execution. The wrapper first obtains the ordinary compression result,
then offers the completed output and actual status to `delta.apply()`. Disabled
Delta, missing session context, unsupported shell syntax, oversized input, and
unsupported statuses retain ordinary behavior. Chains, dry runs, stdin captures,
Antigravity, and the portable quality commands do not use this integration.
An ordinary result marked as redacted also bypasses Delta: preserving a
processor's masking takes precedence over constructing a snapshot from raw text.

For eligible input, Delta masks recognized secrets before asking
`CompressionEngine.diagnostics()` to delegate to the selected processor. The
engine has no pytest- or Ruff-specific branches. The existing test and lint
processors opt into the diagnostic contract. Parsers provide stable identifiers,
complete diagnostic details, explicitly observed passing test IDs, a current
summary, and retained surrounding context. They perform no persistence.
Pytest traceback frame separators remain inside their failure block. Parametrized
identities are matched against complete failure titles rather than split at
punctuation that may belong to a test parameter.
Repeated multiline short summaries are omitted only after matching a complete
exception block already retained verbatim in the primary traceback. Partial or
different summaries remain in context. Rendering and retrieval therefore retain
the original evidence once without classifying unknown text as boilerplate.

Delta hashes the session, real working directory, exact command, family, schema,
and Token-Saver version into a comparison scope. It reads the latest snapshot,
stores the full current snapshot, and calls the pure `diagnostics.compare()`
once. The resulting immutable `Change` observations drive both rendering and
the rule requiring full fresh details (`needs_detail`). Each current
diagnostic remains named. New and changed details are shown fully; only identical
details are summarized. Absence from the current inventory means `NOT OBSERVED`
unless an explicit passing test observation supports `PASSED`.

The sanitized ordinary result wins when it is no larger than the Delta rendering
and contains every full new or changed diagnostic block. Thus unchanged repeats
emit Delta only when shorter, while fresh diagnostic preservation can produce a
larger result than v2 compression. The stored snapshot becomes a baseline in
either case, so retained baselines do not always have a retrieval hint shown.

`delta_store.Store` owns SQLite transactions, private data paths, a 1 MiB payload
limit, read-time expiry, and a global retained-run cap. It does not sanitize its
own inputs or recover corrupt data by deleting it. The integration owns failure
isolation and records content-free diagnostics. Once masking has occurred,
fallback output must retain it. `delta show` validates a stored snapshot and
sanitizes presentation again; `delta clear` removes history across all scopes.
Insertion order selects the latest snapshot and enforces the count cap. Records
dated in the future after a backward clock adjustment are discarded on access,
so a clock change cannot extend retention or evict a fresh result in their favor.

The three Delta configuration settings are global/environment-only because they
control retaining captured output. They are separate from ordinary compression
thresholds and from the metadata-only savings database. This boundary keeps
stateless `compress()` behavior and existing processor extension points intact.

## Construct an engine with explicit dependencies

An application can choose its processor set without loading configured user
plugins. Supplying settings also separates engine thresholds from the default
configuration reader:

```python
from src import engine
from src.processors import generic
from src.processors import git

compressor = engine.CompressionEngine(
    [git.GitProcessor(), generic.GenericProcessor()],
    settings={
        "enabled": True,
        "disabled_processors": [],
        "min_input_length": 1,
        "min_compression_ratio": 0.0,
        "max_chain_depth": 3,
        "recover_critical_lines": 20,
    },
)

output, processor_name, changed = compressor.compress(
    "git status",
    "On branch main\nnothing to commit, working tree clean\n",
    exit_code=0,
)
```

`EngineSettings` only requires a `get(key)` method. A supplied reader must provide
the engine's required values; a partial mapping is not automatically merged with
defaults. These settings govern the engine, while built-in processor-specific
limits still come from `src.config`. A fully isolated application also needs
processors whose configuration it controls.

With no explicit dependencies, `CompressionEngine()` retains discovery and the
shared configuration reader. Threshold reads remain live across configuration
reloads; the processor registry and its disabled set are assembled at engine
construction. The return shape stays `(output, processor_name, was_compressed)`.
A true flag can represent redaction even when the result is not shorter.

## Evaluate quality independently of storage and the CLI

The `evaluation.Compressor` protocol requires just the existing `compress()`
signature; unlike the core contract, evaluation needs no routing metadata.
The engine satisfies it without inheriting from another base class. Tests or
other applications can supply an alternative implementation of that signature.

```python
from src import evaluation

result = evaluation.evaluate(
    compressor,
    "git status",
    "On branch main\nnothing to commit, working tree clean\n",
    exit_code=0,
    policy=evaluation.QualityPolicy(
        max_tokens=100,
        must_preserve=("main",),
    ),
)

report = result.report()
print(report["passed"], report["compressed_tokens"])
```

A policy can limit estimated output tokens, require a minimum savings percentage,
or require exact substrings to exist in both the original and compressed output.
Violations are reported; evaluation never discards additional text to force a
budget to pass. Token estimates use `ceil(characters / chars_per_token)`, not a
model tokenizer or billing measurement.

`Evaluation` retains compressed text for callers that need it. Its `report()`
contains metrics and violation identifiers, excluding command strings, captured
output, and required substring contents. Replay adds the manifest's case names
and aggregate totals. The `compress --format json` CLI intentionally includes
compressed output as well as those metrics.

## Replay and platform adapters

Replay reads UTF-8 captures named by a versioned JSON manifest. It validates the
schema and limits, bounds input reads, and resolves captures inside the manifest
directory. The adapter supplies captured text and the optional original exit
status to evaluation. It does not run the commands named in the manifest or
record them as new command executions.

`quality_cli.py` owns argument handling and presentation. Quality commands return
status `0` for passing checks, `1` for policy violations, and `2` for invalid
input. New output formats belong in this adapter; quality rules belong in
evaluation; capture-loading changes belong in replay.

The hooks have different responsibilities. Claude's pre-tool adapter checks
eligibility and rewrites accepted commands through `wrap.py`, which executes
them and preserves execution status. Antigravity's after-tool adapter transforms
already captured output. Shared core functions connect compression results to
audit and tracking. The savings SQLite database stores command metadata and size
measurements, not complete captured output; command strings themselves may still
contain sensitive information. Opting into Delta creates a separate store of
sanitized diagnostic snapshots, including captured context, with its own
retention limits. See the [Delta storage details](delta.md#local-storage-and-retention).

## Evidence and deliberate limits

Behavioral checks exercise independently configured engines and command policies,
comparison without storage, injected writers that fail, audit failures after file
opening, explicit statistics arguments, and the historical rendering contracts.
A runtime-only copied tree proves that core eligibility and CLI explanation work
without the Claude adapter package. Installed-tree smoke tests require the new
runtime modules and execute real compression and Delta retrieval. The broader
failure corpus, shell tests, and compression ratchet protect preserved behavior.

SOLID is a design discipline, not a score certified by a passing test suite.
Built-in processors still read shared configuration; default discovery and policy
inventories are process-local. Tracker formatting methods remain compatibility
facades. The dedicated updater remains an imperative adapter that prints progress
and applies installation changes. Those are explicit integration responsibilities,
not hidden claims of universal purity.
Introduce another boundary when it isolates an independent change, resource
lifetime, or replaceable dependency; avoid interfaces that merely rename a call.
