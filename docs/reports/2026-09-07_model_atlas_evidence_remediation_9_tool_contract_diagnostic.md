# Model Atlas Evidence Remediation 9: Tool Contract Diagnostic

Date: 2026-09-07  
Status: implementation and isolated diagnostic complete  
Authority: non-authoritative diagnostic evidence

## Objective

Improve Tool argument validity and bounded transient-failure recovery without changing the model's
Tool selection, exposing evaluator ground truth, or rewriting finalized case packs and canonical
Portfolio evidence.

## Baseline Finding

The three existing Portfolio configurations selected the correct Tool in 41 of 48 scoped calls,
but only 14 calls had valid arguments and executed successfully. The dominant failures were:

- normal calls emitted `simulate_failure` even though the user did not request failure injection;
- recovery calls omitted `simulate_failure=transient_once`;
- some required `query` values were empty;
- generated arguments included fields outside the selected Tool schema.

The isolated pre-change diagnostic confirmed the same shape:

| Configuration | Run ID | Selection | Arguments | Execution | Recovered calls |
| --- | --- | ---: | ---: | ---: | ---: |
| `small-baseline` | `04141170-1364-40ee-98fc-a5c9dd9f19bc` | 10/16 | 4/16 | 4/16 | 0 |
| `medium-candidate` | `69b26219-409d-4a87-a5d1-2ad4330c0123` | 15/16 | 5/16 | 5/16 | 4 |
| `prompt-variant` | `eeb1649c-37b9-4697-ae7f-3a25b328498a` | 16/16 | 5/16 | 5/16 | 4 |

Artifact:
`artifacts/reference-workload/runtime-matrix-diagnostic-tool-contract-pre-v18.json`  
SHA-256: `05d5a0be20314fd59df0b9afe1628ede6117a3562beb287c11fc655baf6a9869`

## Implementation

`bounded-tool-call-contract-v1` runs after JSON extraction and before local Tool execution.

1. It reads only the public request and the public `available_tools` descriptors.
2. It accepts only a single recognized Tool call and never changes the model-selected Tool.
3. It drops arguments absent from the selected Tool's Registry schema.
4. It removes failure simulation unless the request explicitly asks for transient or permanent
   failure behavior.
5. It adds `transient_once` only when the public request explicitly describes a transient failure
   or bounded retry.
6. It repairs blank required query/document fields from the public request and respects string
   limits and enums.
7. It preserves `raw_output`, stores the compiled call as `normalized_output`, and records changes
   under `metadata_json.tool_call_contract`.

Every audit record declares `source=public_request_and_tool_registry` and
`uses_expected_tool_contract=false`. Unit tests also bind that boundary. The adapter descriptor is
now `openai-compatible-v18` with capability `bounded_tool_call_contract`.

## Actual Result

| Configuration | Run ID | Selection | Arguments | Execution | Recovery cases |
| --- | --- | ---: | ---: | ---: | ---: |
| `small-baseline` | `6a2480df-505c-4355-8652-47d793c8ee40` | 10/16 | 11/16 | 10/16 | 3/6 |
| `medium-candidate` | `55b3b0ad-228c-4ed0-acea-4f8f9f33e501` | 15/16 | 15/16 | 15/16 | 6/6 |
| `prompt-variant` | `4475f1b5-a0f6-46fc-b834-608345b9f84f` | 16/16 | 16/16 | 16/16 | 6/6 |

Across all 48 calls:

- Tool selection stayed exactly `41/48` before and after;
- argument validity improved from `14/48` to `42/48`;
- execution success improved from `14/48` to `41/48`;
- recovered calls increased from 8 to 15;
- all 15 correctly selected recovery calls made two attempts and recovered;
- all 48 final results contain a public-contract audit record.

Final artifact:
`artifacts/reference-workload/runtime-matrix-diagnostic-tool-contract-v18.json`  
SHA-256: `539d91fbea9a462d7da6e882e6fe1df2caf4573ef2a69059f24819f3820f835c`

## Rejected Iterations And Guards

A strict Tool-name response schema and a duplicated bilingual routing guide were tested and
rejected because they reduced 0.5B selection accuracy. They are not present in the final code.

A proposed Tool Registry v2 description change was blocked by the workload lineage validator:
suite inputs cannot change under the same workload version. The source-document edit was reverted,
its manifest hash restored, and Registry v1 remains active. This preserved finalized 1.0.4 and its
corpus identity.

## Residual Risk

The remaining seven failures are Tool-selection errors: six from the 0.5B baseline and one
`KO-TOOL-005` error from the medium candidate. The compiler intentionally leaves these visible.
Improving them requires a separately measured Tool-selection change, not broader argument repair.

This diagnostic does not replace canonical Portfolio or Gate evidence. Production readiness remains
`not_production_ready`.
