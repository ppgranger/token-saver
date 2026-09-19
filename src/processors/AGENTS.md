# Processor contract

- Follow the root Google Python style policy. Import `from src.processors import
  base` and subclass `base.Processor`; describe supported output and preservation
  limits in docstrings. Use explicit loops for multi-stage parsing instead of
  comprehensions with multiple `for` clauses.
- Implement a concrete `Processor` with a stable `name`, numeric `priority`,
  anchored `hook_patterns`, `can_handle(command)`, and `process(command, output)`.
  Discovery and hook-pattern collection are automatic; do not add a second
  manual registry. Equal priorities are ordered by name.
- Keep hook patterns and routing predicates aligned. A processor should not
  intercept unrelated command names, filename substrings, or flags belonging
  to another tool. Test positive and negative matches and launcher variants.
- Respect priority ranges in `base.py`; `999` belongs to the generic fallback.
  Choose lower priority numbers only when a tested routing override requires it.
- Return the original text for empty, short, dense, or unrecognized shapes when
  no safe transformation exists. Do not invent a success summary from ambiguous
  output. Keep deterministic output and visible omission markers when truncating.
- `handles_failure = True` is a preservation promise: provide a failure fixture
  and prove actionable failure details survive. Set `wants_exit_code = True`
  only with an implementation accepting the optional keyword argument.
- For redaction, implement `redacted_secrets()` accurately for the current
  command/input. The engine uses it to prevent raw fallback; do not claim a
  whole processor always redacts when only some supported inputs do.
- Reuse shared critical-line and parsing helpers where semantics match.
  Processors must not execute commands, perform network requests, or write
  tracking data. Chaining must remain bounded and avoid repeated processors.

For a new processor, add routing/output tests, a case in
`tests/failure_fixtures.py`, and engine/hook integration coverage. Run processor,
precision, pattern-consistency, processor-count, user-processor, and compression
ratchet tests. Update docs and public counts named by the consistency tests;
auto-discovery does not update those files. See `docs/AGENTS.md` for docs pages.
