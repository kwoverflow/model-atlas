# Tool Argument Validation

## Decision And Scope

OpenAI-compatible adapter v21 uses `bounded-tool-call-contract-v2` for standalone Tool calls.
It replaces v1's argument repair with a non-repairing execution guard. This is a measurement and
execution-boundary correction, not a new language model or evidence of better model accuracy.

The guard does not change Tool selection, fill missing values, remove extra fields, trim strings,
truncate identifiers, coerce types, or infer failure simulation from request wording. It may unwrap
a single native Tool envelope and serialize its arguments canonically. The raw response is retained.

Agent, RAG, and multi-step Tool paths are outside this guard's scope. Mock adapters and direct
legacy executor calls retain their existing behavior. Do not interpret this as a system-wide
authorization layer or a guarantee of semantic correctness.

## Data Flow

1. Benchmark preparation builds public Tool descriptors from the registered tools, not expected
   case labels. It resolves the document catalog from the configured retrieval corpus.
2. Preparation verifies any configured corpus hash/version against the loaded corpus, and derives
   document IDs from its actual chunks. Other corpora are not merged into this catalog.
3. The model receives public Tool descriptors and, when available, the corpus's document IDs and
   provenance. Private expected Tool names, argument labels, and scoring contracts are not inputs
   to the argument guard. The opt-in compact prompt includes public catalog data in its input hash.
4. The adapter strictly parses one JSON Tool call, validates its unchanged arguments against the
   selected public schema, and checks document membership and explicit failure authorization.
5. Guard rejection sets `tool_call_valid=false` and `error_type=tool_argument_guard_rejected`.
   The executor receives the rejection reason and records a skipped step with zero handler attempts.
   Tool selection remains separately measurable; a correct selection does not authorize bad args.
6. Raw/normalized argument hashes, validation errors, corpus hash, and execution eligibility are
   stored in `metadata_json.tool_call_contract`. Historical result records are not rewritten.

Code ownership: `tool_call_contract.py` owns validation, `benchmark_execution.py` owns corpus
resolution and trusted preparation, the inference adapter attaches the audit, and `tool_execution.py`
enforces the skip. Registry definitions and fixture implementations are unchanged.

An optional environment-owned fault path now projects a separate public registry without
`simulate_failure`; the default registry and legacy handlers remain unchanged. Its executor
receives trusted fault settings separately from the model. See
[Environment-Owned Tool Fault Scenarios](tool_fault_scenarios.md) for this diagnostic-only path.

## Configuration

For a separate document-enabled Deployment Configuration, set `retrieval_config_json.corpus_id`
to a loaded corpus. Pin `corpus_version` and `corpus_hash` when reproducibility matters. Missing
catalogs, mismatched pins, and document IDs absent from the selected corpus fail closed.

`_tool_document_context` is internal prepared runtime state. Benchmark preparation replaces any
supplied value with the server-resolved context. Public input `available_document_ids` is not
trusted as validation authority. A configured corpus is not a substitute for user/document ACLs.

Legacy model-argument failure simulation defaults to disabled. To reproduce an isolated legacy
recovery experiment, the operator may set:

```json
{
  "tool_failure_simulation": "transient_once"
}
```

The other supported mode is `permanent`. This setting only authorizes an already present, matching
model argument. It never inserts `simulate_failure`. A missing required simulation remains a
failure of the existing recovery evaluation. Natural-language requests, including negations such
as "do not retry", cannot authorize simulation. Existing configurations are not silently rewritten.

For new fault-fixture experiments, prefer the separate `tool_fault_scenario` configuration above.
It does not authorize or insert a model `simulate_failure` argument, cannot be combined with legacy
authorization, and rejects legacy expected labels rather than silently removing them.

The Tool selection prompt remains opt-in through `tool_selection_prompt`. Enabling it does not
disable v2 argument validation. There is no switch to restore v1 argument repair in adapter v21.

## Validation Limits

- Supported schema subset: explicit primitive/object/array types, properties, required fields,
  boolean additionalProperties, items, enum, and string lengths. Descriptions/titles are metadata.
  Other constraints, including references/patterns/combinators, are rejected instead of ignored.
- Duplicate JSON keys, non-finite numbers, ambiguous envelopes, and unknown Tool names are rejected.
- Document membership proves only that an ID exists in the chosen corpus. It does not prove that
  the selected document answers the request, that an operator can access it, or that fixture output
  is the real document content. These require separate semantic, authorization, and integration work.
- Query relevance is explicitly `not_verified`. A nonempty schema-valid query may still be wrong.
- Existing success metrics are based on deterministic local fixtures, not external service success.
- Raw output, schema validity, guard eligibility, actual execution, and task correctness are
  different measurements. Lower measured success after removing repair is not model degradation.

## Reproduce The Offline Audit

Run from the repository root in PowerShell:

```powershell
.venv/Scripts/python.exe tools/audit_tool_argument_contract.py `
  --input artifacts/reference-workload/tool-selection-challenge-v20.json `
  --expected-sha256 cb3a7e6a6ee873d969ce096a25072461f87cd102667305d1b4369ffecc5b4d24 `
  --output artifacts/reference-workload/tool-argument-audit-repeat.json

.venv/Scripts/python.exe -m pytest tools/test_audit_tool_argument_contract.py -q
```

The auditor checks input identity, observation uniqueness, missing metrics, and the historical v1
compiler version. It applies v2 to saved raw responses without inference, Tool execution, DB writes,
or changes to the original evidence. Outputs refuse overwriting. The default post-hoc catalog is
the locked finalized 1.0.4 corpus; it was not supplied to the historical model prompts.

Observation grain is runtime entry x challenge case x trial. These locally authored cases are not
independently held-out or human-reviewed. Guard-allowed counts are eligibility, not measured v2
execution success. Block reasons overlap. Keep this audit separate from fresh runtime diagnostics
and from the authoritative Portfolio/Gate evidence.
