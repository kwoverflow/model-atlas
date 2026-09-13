# Tool Selection Diagnostics

## Status And Activation

`public-tool-selection-prompt-v1` is an experimental, opt-in prompt contract in the
OpenAI-compatible adapter v21 (introduced in v20). Missing configuration or `"legacy"` preserves the previous
Tool prompt. The default runtime matrix and existing Deployment Configurations are unchanged.
Unknown setting values raise an error instead of silently selecting a different mode.

To evaluate the candidate, create a separate Deployment Configuration and add this field to its
`runtime_config_json`:

```json
{
  "tool_selection_prompt": "public-tool-selection-prompt-v1"
}
```

Keep its existing runtime URL, model, prompt bundle, and other settings. The existing configuration
fingerprint includes `runtime_config_json`, so an enabled candidate has a distinct identity. Do not
rewrite a configuration attached to historical evidence. Run it using the existing Benchmark
Execution workflow; the canonical reference runtime matrix does not enable this option.

## Architecture

1. `tool_selection_prompt.py` projects the public request, public instruction, and available Tool
   descriptors into a compact catalog. It never receives evaluator labels or selects a Tool.
2. Exact, known registry descriptions have Korean presentation labels. Custom descriptions are
   preserved, including when a custom Tool reuses a familiar Tool name.
3. The response schema allows every supplied Tool name. The model still chooses the Tool and
   generates its arguments in one inference call.
4. `tool_call_contract.py` v2 preserves arguments and rejects invalid calls without repairing them.
5. Existing Tool execution validates arguments and produces a trace. Raw output remains available.

The contract applies only to `tool_single_step` and `tool_failure_recovery` cases with standalone
Tool schemas. Agent, RAG, multi-step, legacy categories, malformed catalogs, and schemas requiring
unsupported projection retain their existing presentation. It requires runtime JSON-schema output
support. The structural response schema does not validate the selected Tool's individual arguments;
that remains the Registry/executor's responsibility.

Audit metadata is stored under `metadata_json.tool_selection_prompt`, including contract version,
public-input hash, candidate names, and `selection_overridden=false`. Configured system prompts and
public request instructions are preserved. Case IDs, titles, private expected schemas, trial numbers,
and timeout metadata are not included in the compact model input.

## Reproduce The Challenge

From the repository root in PowerShell, with the existing local Ollama models available:

```powershell
.venv/Scripts/python.exe tools/run_tool_selection_diagnostic.py `
  --variant legacy --output artifacts/reference-workload/tool-selection-legacy-repeat.json

.venv/Scripts/python.exe tools/run_tool_selection_diagnostic.py `
  --variant current --output artifacts/reference-workload/tool-selection-candidate-repeat.json

.venv/Scripts/python.exe tools/run_tool_selection_diagnostic.py `
  --variant current --tool-order reversed `
  --output artifacts/reference-workload/tool-selection-reversed-repeat.json
```

Run inference comparisons sequentially. Output files are never overwritten. `--trials 2` enables
repeat trials; `--base-url`, `--small-model`, and `--medium-model` allow explicit runtime selection.
The runner uses the existing three matrix prompt/model configurations, temperature 0, seed 42,
and a 384-token generation limit. It observes model digests before running. It does not modify
the database, official reference cases, human approvals, Portfolio evidence, or Gates.

The legacy variant replays only the v18 Tool prompt path with the current v2 argument guard, not a
complete installation of every historical v18 application component. New runs include the public
document catalog from locked finalized 1.0.4 (override with `--manifest`) in both prompt variants.
Failure simulation is disabled in this challenge runner. Historical v18-v20 artifacts retain their
original v1 compiler behavior and are not exactly reproduced by the current runner. Results retain runtime/model
observations, source/fixture hashes, raw output, normalized output, selection, argument validity,
latency, token counts, and errors. Inspect failures as well as aggregate totals.

## Evidence Boundaries

- The 24 challenge cases contain Korean paraphrases, English requests, negation/contrast, and
  recovery wording. They are locally authored and not independently held-out or human-approved.
- Keep selection accuracy, raw argument validity, normalized argument validity, and normalized
  execution success separate. Successful local fixture execution does not prove semantic
  correctness of an identifier, argument, or real external operation.
- Two catalog orders are a sensitivity check, not an exhaustive permutation test. Do not choose
  the best observed ordering and present that result as general model accuracy.
- The compact projection targets this bounded workload, not arbitrary conversational Tool flows.
- Promotion requires review of regressions, repeated/full-workload evaluation, and appropriate
  output review. A better diagnostic total does not authorize a release or production deployment.

See `reports/2026-09-07_model_atlas_evidence_remediation_10_tool_selection.md` for measured results
and the decision to retain legacy defaults.

See `tool_argument_validation.md` for the v21 execution boundary, configuration, and offline audit.
