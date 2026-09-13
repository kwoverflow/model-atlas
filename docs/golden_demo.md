# Golden Demo

The Golden Demo shows how runtime evidence becomes a Gate decision and an auditable release record. It is not a model-quality showcase. Failure is useful when it is visible, attributable, and governed.

## Prerequisites

- Docker Desktop with Docker Compose;
- the repository root as the current directory;
- optional Ollama runtime for the real local path.

## Start and Seed

```bash
make up
```

In another terminal:

```bash
make seed
make seed-tool-calling
make seed-rag
make seed-reliability
make seed-agent
make seed-agent-adaptive
docker compose run --rm backend python -m app.seed.captured_local
```

Open http://localhost:3000.

## Path 0: Executable Tool Calling Pack

This path does not require a downloaded model and exercises actual local handler execution.

1. Open **Execute Benchmark**.
2. Select `Executable Tool Calling Evaluation Suite`.
3. Select the `Tool calling` task and its prompt version.
4. Keep adapter `mock`, data source `local_authored`, and max cases at least 10.
5. Run the cases and open **Inspect Tool Trace**.
6. Confirm 10 tool cases, 12 calls, one recovered retry, and one multi-step case.
7. Open **Deployment Gates** and select `Executable Tool Calling Policy`.
8. Review Evidence, then evaluate the Gate.

The deterministic expected Gate verdict is `APPROVED`. Evidence Trust remains subject to judge
coverage, and Production Readiness remains `NOT_PRODUCTION_READY` because the cases are locally
authored.

## Path 0B: RAG Evaluation Pack

This path executes deterministic retrieval before generation and evaluates citation/claim evidence.

1. Open **Execute Benchmark**.
2. Select `Qwen2.5 7B Local RAG Assistant`.
3. Select `RAG Grounded Answer Evaluation Suite`.
4. Select the `Korean document QA` task and its prompt version.
5. Keep adapter `mock`, data source `local_authored`, and max cases at least 10.
6. Run the cases and open **Inspect RAG Trace**.
7. Confirm retrieval recall, citation precision/recall, and groundedness are 100% and unsupported
   claims are 0%.
8. Open **Deployment Gates** and select `RAG Grounded Answer Policy`.
9. Review Evidence, then evaluate the Gate.

The deterministic expected Gate verdict is `APPROVED`. This validates the evaluation pipeline, not
production retrieval quality. Evidence Trust and Production Readiness remain separate.

## Path 0C: Runtime Reliability Pack

This path produces 30 repeated-trial records and compares two deterministic runtime profiles.

1. Open **Execute Benchmark**.
2. Select `Qwen2.5 7B Reliability Runtime A`.
3. Select `Runtime Reliability Evaluation Suite` and the `Korean document QA` task/prompt.
4. Select **Reliability** mode, five trials, concurrency four, and a 2,000 ms timeout.
5. Keep adapter `mock`, data source `local_authored`, and max cases at least six.
6. Run trials and open **Inspect Reliability Trace**.
7. Confirm 30/30 success, ten context-stress trials, no timeout/OOM, full coverage, and P99 below
   2,000 ms.
8. Open **Deployment Gates**, select `Runtime Reliability Policy`, review evidence, and evaluate.
9. Repeat steps 2-6 with `Qwen2.5 7B Reliability Runtime B`.
10. Open **Runtime Reliability**, select both run IDs, and compare.

The deterministic Runtime A Gate verdict is `APPROVED`. Runtime A is recommended over Runtime B
because success/error rates tie and Runtime A has lower P99 latency. This validates orchestration,
trace, comparison, and policy behavior; it is not a hardware performance claim.

## Path 0D: Bounded Agent Operations Pack

This path evaluates one plan-first Agent runtime through memory, retrieval, registered tools,
recovery, response validation, semantic replay, and the Deployment Gate.

1. Open **Execute Benchmark**.
2. Select `Qwen2.5 7B Bounded Operations Agent`.
3. Select `Bounded Agent Operations Evaluation Suite`.
4. Select the `Korean document QA` task and prompt.
5. Keep adapter `mock`, data source `local_authored`, and max cases at least eight.
6. Run all cases and open **Inspect Agent Trace**.
7. Confirm 8/8 tasks, 24/24 steps, zero policy violations, full memory provenance, and one recovered
   tool retry.
8. Use **Replay Trace** on a case and confirm `Semantic match`.
9. Open **Deployment Gates**, select `Bounded Agent Operations Policy`, review evidence, and
   evaluate.

The deterministic expected Gate verdict is `APPROVED`. The memory-write case shows
`task_local_simulated` and `persisted=false`. This demonstrates bounded evaluation and governance,
not an autonomous production agent or durable memory system.

## Path 0E: Adaptive Agent Operations Pack

This path evaluates versioned observations, authenticated persistent checkpoints, guarded actions,
resume, bounded replanning, and recovery-specific Gate metrics.

1. Open **Execute Benchmark**.
2. Select `Qwen2.5 7B Adaptive Operations Agent`.
3. Select `Adaptive Agent Operations Evaluation Suite` and the Korean document QA task/prompt.
4. Keep adapter `mock`, data source `local_authored`, and max cases at least five.
5. Run all cases and open **Inspect Agent Trace**.
6. Confirm three successful tasks and two `pending_approval` traces. The first
   `Adaptive Agent Operations Policy` Gate is `BLOCKED`.
7. Copy the run UUID from the detail URL and approve and resume both records with a trusted demo
   identity:

```powershell
$runId = "<benchmark-run-uuid>"
$base = "http://localhost:18000/api/v1"
$headers = @{
  "x-model-atlas-operator-id" = "demo-mlops-approver"
  "x-model-atlas-operator-name" = "Demo ML Ops Approver"
  "x-model-atlas-operator-role" = "ML Ops Lead"
  "x-model-atlas-identity-provider" = "golden-demo"
}
$checkpoints = Invoke-RestMethod "$base/agents/checkpoints?benchmark_run_id=$runId"
$childRunIds = @()
foreach ($checkpoint in $checkpoints) {
  $decisionBody = @{
    decision = "approved"
    reason = "Reviewed bounded action evidence for the golden demo."
    expected_version = $checkpoint.version
  } | ConvertTo-Json
  $approved = Invoke-RestMethod `
    "$base/agents/checkpoints/$($checkpoint.id)/decision" `
    -Method Post -Headers $headers -ContentType "application/json" -Body $decisionBody
  $resumeBody = @{ expected_version = $approved.version } | ConvertTo-Json
  $job = Invoke-RestMethod "$base/agents/checkpoints/$($checkpoint.id)/resume-jobs" `
    -Method Post -Headers $headers -ContentType "application/json" -Body $resumeBody
  do {
    Start-Sleep -Milliseconds 500
    $job = Invoke-RestMethod "$base/agents/jobs/$($job.id)"
  } while ($job.status -in @("queued", "leased", "running"))
  if ($job.status -ne "completed") {
    throw "Resume job failed: $($job.last_error)"
  }
  $childRunIds += $job.result_json.benchmark_run_id
}
$childRunIds
```

8. Refresh the original run and confirm it remains unchanged with three successful and two pending
   traces. The two checkpoint records are now `resumed` and link to separate child revision runs.
9. Open both child run IDs. Each contains one successful revision with verified decision provenance.
10. Confirm failed triggering steps remain visible and are marked `recovered_by_replan`.
11. Replay one resumed approval case and one recovery case; both should report `Semantic match`.
12. Confirm the first Gate is `stale`, then evaluate a new `Adaptive Agent Operations Policy` Gate.
    Its latest-root evidence contains five logical cases and the expected verdict is `APPROVED`.

The browser UI queues and polls the same durable jobs when the deployment's identity proxy supplies
a trusted identity context. The API sequence above is the deterministic local demonstration of
that boundary. `make up` includes the `agent-worker` service that processes these jobs.

## Path A: Fast Deterministic Fixture

This path validates the OpenAI-compatible transport and end-to-end UI without downloading a model.

Windows:

```powershell
.\.venv\Scripts\python.exe tools\openai_compatible_fixture.py --host 0.0.0.0 --port 1234
```

macOS or Linux with an active project environment:

```bash
python tools/openai_compatible_fixture.py --host 0.0.0.0 --port 1234
```

In **Execute Benchmark** choose:

- adapter: `openai_compatible`;
- base URL: `http://host.docker.internal:1234` when the backend is in Docker;
- data source: `local_authored`;
- a deployment configuration and the captured local suite.

The fixture is deterministic integration evidence. It is not a real model-quality claim.

## Path B: Real Local Ollama

```bash
docker compose --profile runtime up -d ollama
docker compose exec ollama ollama pull qwen2.5:0.5b
docker compose run --rm backend python -m app.seed.captured_local
```

In **Execute Benchmark** choose:

- adapter: `openai_compatible`;
- base URL: `http://ollama:11434`;
- model: `qwen2.5:0.5b`;
- data source: `local_authored`;
- the captured local evaluation suite.

Then open **Model Validation**:

1. Select the source deployment configuration and captured-local suite.
2. Select **Local runtime** and use `http://ollama:11434` with `qwen2.5:0.5b`.
3. Sign in or supply a verified maintenance identity.
4. Select **Attest Runtime**. The server observes the manifest and redirects to a digest-pinned
   `Qwen2.5 0.5B Attested Local Runtime` configuration.
5. Queue five cases against that matching configuration.
6. Confirm the durable job completes and the report shows actual runtime evidence, a matching
   digest, and `verified` attestation.
7. Open **Judge Review** and record verified decisions for at least one critical and one
   representative standard case.
8. Refresh Model Validation. Local evidence may become `validated`, while release authorization
   and production readiness must remain false.

The original 7B configuration remains available as a useful mismatch demonstration. Do not run the
0.5B model under that scope and present it as target-artifact evidence. Use the attested 0.5B
configuration or execute and attest the actual 7B artifact.

## Ten-minute Walkthrough

1. Open **Overview**. Point out the evidence-mode banner, six workflow steps, latest statuses, and prioritized actions.
2. Open **Candidate Discovery**. Explain that ranking chooses candidates but does not authorize deployment.
3. Open **Model Validation**, attest the runtime, and create local evidence through a durable job.
4. Confirm actual runtime, model/digest identity, attestation, evidence cohorts, and reviewed-label
   coverage.
5. Open **Deployment Gates** and select configuration, suite, policy, and optional baseline.
6. Click **Review Evidence**. Confirm completed runs, result and metric counts, source/score
   distribution, review coverage, and baseline.
7. Click **Evaluate Gate** only after Preflight succeeds.
8. On the Gate report, read the four status concepts, blockers, next actions, trust, and critical
   cases before metrics.
9. Open **Judge Review**, then **Release Readiness**.
10. Sign an allowed decision or request changes, then inspect **Release Decisions** and
    **Experiment Lineage**.

## Expected States

Before reviewed labels are applied, local runtime results commonly produce:

```text
Gate Verdict: policy-dependent
Evidence Trust: NEEDS_JUDGE_REVIEW
Production Readiness: NOT_PRODUCTION_READY
```

After sufficient local labels are applied:

```text
Evidence Trust: LOCAL_DEMO_READY
Release Readiness: READY_TO_PROMOTE or READY
Production Readiness: NOT_PRODUCTION_READY
```

With a matching verified digest, the separate Model Validation status can be `validated`. That
does not change the Gate, readiness, or production status shown above.

Production readiness requires enough `production_captured` results, configured judge coverage, reviewed critical cases, an approved Gate, an active baseline, and no open review or prompt-regression risk.

## Expected Model Failures

`qwen2.5:0.5b` may fail JSON formatting, tool selection, argument shape, grounded answers, or latency rules. This is an expected demo outcome. The evaluator should inspect whether Model Atlas:

- surfaces the failed case;
- explains the blocking rule;
- recommends a next action;
- prevents an unsupported production-readiness claim;
- preserves the evidence and decision hashes.

## Judge-label Follow-up

For individual evidence, use **Judge Review** to append an approved candidate, override, or
rejection with a verified reviewer identity and rationale. The decision keeps prior and applied
scores plus a stable review hash.

For batch evidence, use the provided JSONL example for a dry run, then apply only after review:

```bash
docker compose run --rm backend python -m app.seed.import_judge_labels \
  --benchmark-run-id BENCHMARK_RUN_ID \
  --path /data/seed/judge_labels.example.jsonl
```

Add `--apply` to mutate matched result labels. The next Release Readiness snapshot will recompute trust, while an existing release decision retains its frozen trust state. Snapshot diff will expose the change.

## Troubleshooting

- No runtime health: verify the base URL from the backend container, not only from the host browser.
- `missing attestation`: use **Attest Runtime** with an allowed server-side runtime host.
- `digest mismatch` or `model mismatch`: stop and rerun the configured artifact; never relabel the
  mismatched run as target evidence.
- No Preflight results: confirm the completed run references the same deployment configuration and suite.
- `NEEDS_JUDGE_REVIEW`: apply enough labels and include at least one reviewed critical case for local-demo readiness.
- `NOT_PRODUCTION_READY`: this is expected for `local_authored` evidence.
- Approval disabled: check readiness status, verified operator identity, and allowed release role.
