# Model Atlas Sprint 4A Evaluator Guide

Date: 2026-07-10

Status note: This is the historical Sprint 4A review snapshot. For current implementation and
verification results, see `2026-07-10_model_atlas_sprint_4b_implementation_report.md`.

## Executive Summary

Model Atlas is not another local-model recommender. It is a local-first EvalOps control plane that evaluates a concrete deployment configuration against a versioned workload and acceptance policy, then preserves an auditable release decision.

Candidate Discovery remains useful, but it only answers what should be tested. Deployment Gate answers whether the selected artifact, runtime, hardware, prompt, context, and generation configuration passes a specific workload policy.

Sprint 4A closes a major interpretation risk: a policy pass is no longer visually or programmatically confused with strong evidence or production readiness.

## Problem Being Solved

Typical local-model selection tools focus on:

- parameter count and quantization;
- context length;
- GPU and VRAM fit;
- tokens per second and latency;
- aggregate benchmark scores.

Those dimensions help shortlist a model. They do not provide workload-specific release governance, critical-case blocking, evidence provenance, baseline comparison, signer authorization, or a frozen decision record.

Model Atlas adds that missing decision layer.

## Why Evidence Trust Matters

The same numeric score can come from very different evidence:

- a synthetic demonstration case;
- an operator-authored local case;
- a production-captured case;
- an external benchmark;
- a heuristic scorer;
- an unapplied candidate label;
- an applied model judge;
- explicit human review.

Sprint 4A classifies source trust and score trust independently. `captured_local` is explicitly treated as `local_authored`, not production evidence. Heuristic-only evidence cannot quietly become release-ready, and locally authored evidence can be useful for a reproducible demo without being labeled production-ready.

## Heuristic Scoring: Useful but Insufficient

Deterministic scorers are valuable because they are fast, local, reproducible, and explainable. Current scorers inspect JSON shape, tool and argument matching, reference-context overlap, and non-empty text output.

They remain proxies. They can miss semantic correctness, unsupported claims, ambiguous tool intent, and domain-specific harm. Model Atlas therefore records the scorer ID, method, version, capabilities, input/output schema versions, and registry version, then requires judge coverage before stronger readiness states are allowed.

## Sprint 4A Changes

- Central Evidence Trust service and thresholds.
- Source and score provenance separation.
- Gate evidence snapshot v2 with implementation provenance.
- Trust-aware Release Readiness and Production Readiness.
- Frozen release trust and snapshot diff after label changes.
- Non-persisting Gate Preflight.
- Workflow-oriented Overview and navigation.
- Decision-first Gate report hierarchy.
- Judge Review coverage summary.
- Minimal adapter and scorer extension descriptors.

## Ten-minute Evaluation

### Minute 0-2: Product framing

Open Overview and verify:

- ranking is not presented as authorization;
- evidence mode is visible;
- the six workflow steps are linked;
- latest Gate, Evidence Trust, Production Readiness, blockers, and next actions are visible.

### Minute 2-4: Preflight

Open Deployment Gates, select a configuration, suite, and policy, then click **Review Evidence**.

Verify:

- completed runs, result count, metric count;
- active and critical case counts;
- source and score distributions;
- judge and critical review coverage;
- baseline selection;
- warnings and blocking preconditions;
- no Gate Evaluation is created by Preflight.

### Minute 4-6: Gate decision

Evaluate the Gate and verify the report order:

1. status summary;
2. decision reason;
3. blockers;
4. next actions;
5. evidence trust;
6. critical cases;
7. policy rules;
8. metrics and regression;
9. provenance and raw snapshot.

### Minute 6-8: Readiness and judge coverage

Open Judge Review and Release Readiness. Confirm Gate Verdict, Evidence Trust, Release Readiness, and Production Readiness are independent. A local demo may be ready to promote while remaining not production-ready.

### Minute 8-10: Audit

Create an allowed release decision or request changes. Inspect the frozen snapshot, signer identity, approval policy, hashes, current snapshot diff, and experiment lineage.

## Expected Demo Failures

A small local model may fail structured output, tool selection, grounded answer, or latency checks. This should not be hidden. A successful Model Atlas demo shows that the failure:

- appears as a critical case or failed policy rule;
- affects the Gate correctly;
- creates a useful next action;
- remains traceable to the benchmark run and result;
- prevents an unsupported readiness claim.

## Compatibility and Engineering Judgment

Sprint 4A uses additive JSON fields and existing metadata columns. No new evidence-trust table or database enum was introduced. Existing routes and stored records remain readable. Legacy snapshots without trust metadata display an explicit fallback state.

The extension design deliberately stops at descriptors and protocols. It does not introduce a marketplace, dynamic loading, agent orchestration, RAG, or infrastructure deployment before the evaluation contracts are stable.

## Verification Evidence

```text
Backend pytest: 84 passed
Backend Ruff: passed
Frontend typecheck: passed
Frontend lint: passed
Frontend production build: passed
```

## Current Limits

- Bundled evidence is not a substitute for production-captured workload data.
- Production readiness is an interpretation state, not an infrastructure deployment action.
- Trusted identity headers are an integration boundary, not full SSO/OIDC.
- Heuristic scoring still needs domain calibration.
- No executable tool workflow, RAG pipeline, runtime stress pack, or production monitoring is included yet.

## Recommended Next Work

Sprint 4B should implement an executable Tool Calling Evaluation Pack that captures tool selection, argument validation, actual execution, failures, retries, recovery, and multi-step sequences through the existing evidence and release contracts.
