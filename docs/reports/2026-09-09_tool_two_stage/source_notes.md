# Two-Stage Tool Diagnostic Validation

## Assessment

Share with caveats, as local engineering evidence only. No production or Gate promotion.
Raw model run: 2026-09-09 06:05:12 to 06:10:11 UTC (15:05:12 to 15:10:11 UTC+9).
The technical findings and reproduction instructions are in `../../tool_two_stage_argument_generation.md`.

## Sources and Grain

- Source: `artifacts/reference-workload/tool-two-stage-diagnostic-v1.json`.
- SHA-256: `f122e1e6cb38c349b00d8d35769f279a21786a16139f1ab4834eff36558f0ca8`.
- Historical baseline SHA-256: `27975681d2f2b53bad53c44d19346e5d9d7a47fa28f32a7d226faeecd388497f`.
- Journal SHA-256: `b164472fa5fc01ce08e36864219f84e0c09147a7da25c910b00d749d76416219`.
- 144 final-output observations, 252 actual generation HTTP calls, 432 paired fault replays.
- 72 frozen-cohort candidate observations; challenge has 36 baseline and 36 candidate observations.
- Each challenge variant has 18 case-entry pairs, each viewed in two Tool orders, not 36 independent cases.

## Checks Performed

`tools/audit_tool_two_stage.py` recomputes exact calls directly from captured JSON and private labels.
It does not import application scoring functions. It checks source hashes, immutable baseline inputs,
journal equality, expected observation keys, no duplicates, request hashes, paired request parity,
unmodified second-stage argument values, fixed Tool selection, unchanged replayed arguments, blocked
handler invocations, and HTTP token totals. All 144 observations have complete measured usage.
All 252 HTTP completions have finish reason `stop`. No runtime error rows were excluded.

The `reproduce.ipynb` notebook executed top-to-bottom and saved `audit.json` with detailed mismatches.
System Python 3.12 with nbformat/nbclient/ipykernel was used. A non-fatal Windows ZMQ event-loop
compatibility warning occurred; execution completed. This is a notebook/Markdown technical handoff;
no dashboard, chart, HTML or pixel-level visual QA is claimed.

Host backend: 391 passed, 1 skipped. Docker backend: 392 passed. New safety tests: 24 passed.
The Windows-only symlink skip is pre-existing. Dependency deprecation warnings remain.
Backend and worker images rebuilt after model measurement, then restarted; no concurrent image build
was included in the inference timing window. Timing still has uncontrolled cache/host effects.

## Findings and Caveats

- Frozen exact calls: historical 43/72, current stage1 44/72, candidate final 55/72.
- Challenge exact calls: baseline 19/36, candidate 27/36. All three candidate entries score 9/12.
- Within-candidate frozen transitions: 15 improvements, 4 regressions. Challenge: 11 improvements, 3 regressions.
- Tool selections match the corresponding baseline selections, but repeated-run arguments can vary.
- The four 1.5B challenge omissions of explicit priority=normal fail literal matching; the local ticket
  handler's default is also normal. Do not equate these with semantic execution failures.
- Small-model frozen accuracy regresses. Selected-schema generation is not universally preferable.
- Challenge tokens increase 32,898 to 44,061 (+33.9%). Timing is descriptive, not an SLA estimate.
- Candidate schema metrics apply to an assembled envelope. Actual stage outputs are separately retained.
- Requests were locally authored and unreviewed; no independent holdout, real external-service ACL,
  content-validity, general semantic correctness or model-driven recovery claim is supported.

## Official State

Read-only overview at 2026-09-09 06:14:33 UTC: BLOCKED; 110 critical failures; 384 actual-runtime
results; actual output review 0/30; not_production_ready. Finalized 1.0.4 source validation remains
64/64 approved and critical 20/20; its 14-file corpus hash is unchanged.

There are no incomplete execution checks for this diagnostic handoff. Independent evaluation,
human review, real content/authorization tests and a promotion decision remain future requirements,
not completed work. The opt-in candidate is intentionally absent from the application adapter factory.
