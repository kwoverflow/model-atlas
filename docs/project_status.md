# Model Atlas Project Status

Updated: 2026-09-13

## Current Position

Model Atlas is a working local-first EvalOps control-plane MVP. Its strongest area is auditable deployment evaluation and release governance, not model hosting or generic benchmark ranking.

## Portfolio MVP Closeout (2026-09-13)

- Scope fixed in `MVP_SCOPE_KO.md`; no further model/retrieval tuning in this handoff.
- Separate review Compose installs into a fresh PostgreSQL volume with UI 13000/API 18010.
- Core mock API and browser flow verified through Gate and synthetic REQUEST_CHANGES detail.
- Fixed the review Docker internal API URL and long status/detail overflow in release summaries.
- Backend 901 tests, frontend 29 tests, packaging helper 9 tests; build/typecheck/Ruff pass.
  Existing backend deprecations (2) and frontend lint warnings (4) are explicitly retained.
- Packaging now records current verification receipts and excludes local weights/caches/secrets;
  payload hashes are checked before and after extraction.
- Official BLOCKED/110 failure observations/384 runtime results/output review 0/30 are unchanged.
  Approved 1.0.5 and frozen corpus source documents remain unchanged.
- Current entry: [MVP review guide](../MVP_REVIEW_GUIDE_KO.md).
  [Verification and limits](reports/2026-09-13_mvp_closeout_ko.md).
- External novice-user review remains pending. It is not replaced by automated QA.

## Evidence Remediation 28 Paper-Based Comparison Closed

Historical research checkpoint follows. Current handoff is the portfolio MVP closeout below.

- Investigated seven relevant primary papers: BERT passage reranking, MMR, BERT-MaxP, RankGPT,
  Lost in the Middle, BGE M3 and BEIR. The previous hierarchical deletion scheme was not a
  reproduction of RankGPT, and that paper does not establish this small model's ranking quality.
- Pre-registered exactly two candidates and explicit stop criteria before scoring: trained
  MiniLM Cross-Encoder and the same scorer with MMR lambda 0.7. No post-result tuning or defaults.
- Kept the same guarded English queries and top-50 pools. Local official FP32 ONNX checkpoint,
  pinned model/tokenizer hashes, full overlapping-window coverage, no generation or cloud inference.
- Cross-Encoder: 8/22 ordinary, 2/5 critical, three regressions against guarded RRF. MMR: 6/22,
  1/5, four regressions. Guarded RRF remains 8/22 and 1/5. Both miss the frozen quality threshold.
- Scored 1,100 pairs / 1,249 windows in 65.24 seconds (2.97 seconds/query average), excluding
  translation, loading, MMR and answers. This is not an identical end-to-end latency benchmark.
- Optional research code/environment are outside the backend. Research tests 34 passed; existing
  Docker backend 901 passed; Ruff passed; saved-score replay matches all 48 rows and 1,100 pairs
  with zero new inference. Linux ONNX inference was not measured in this comparison.
- Source, model and pre-registered protocol remained unchanged during the run. Official protected
  snapshots and approved 1.0.5 hashes unchanged: BLOCKED/110 failures/384 results/review 0/30.
  Running backend image and production dependencies unchanged; no Gate or answer-stage promotion.
- Decision: stop this open-ended retrieval-tuning line. No further prompt, lambda or model sweep.
  Recommend finishing the EvalOps MVP scope; higher-quality local RAG requires a separately scoped
  model/data/resource decision and independent evidence, not another automatically extended phase.
- [Korean research, measured results, limitations and reproduction](reports/2026-09-12_rag_research_decision_ko.md).

## Evidence Remediation 27 Guarded Pool Improves; Model Selection Rejected

- Added opt-in literal-preserving translation retry, public three-list BM25/RRF candidate pooling,
  and bounded complementary-source selection. Default retrieval, top-k and labels unchanged.
- Reused 19 prior translations; three retries restore missing Preflight/Calling/schema literals.
  This is term preservation, not semantic approval. No expected evidence is passed to the model.
- Compared all 48 RAG cases, with 22 ordinary candidates and 26 unchanged fallback preparations.
  Baseline: 25/48, ordinary 6/22, critical ordinary 1/5. Guarded three-list RRF: 27/48, 8/22,
  1/5, two gains and no regressions. Critical retrieval remains insufficient; no adoption.
- Candidate top-50 contains every mandatory evidence group for all 22 ordinary cases. The local
  1.5B model's hierarchical selection drops to 21/48, 2/22, 0/5, with four regressions. Rejected.
  Required sources are lost during shortlisting, including Preflight at candidate rank 2.
- Live run: 168 local calls (three translations, 165 selections), zero execution-contract failures,
  zero answer calls, about 16m36s. Recorded 363,311 prompt/1,974 completion tokens. High cost does
  not yield better evidence selection. No new model downloads, training or application DB writes.
- Windows/Docker offline replay matches all 48 rows, 22 translations and 168 requests/responses,
  with zero new model calls. Original live harness retained; later --previous option only resolves
  Docker artifact-mount portability. Ranking and prompts unchanged after seeing results.
- Added 57 tests; host candidate/JWT 62 passed; final rebuilt Docker full backend 901 passed;
  host/Docker Ruff passed. Fixed canonical-signature mutation in an existing JWT test without
  changing production authentication. Dependency locking/deprecation cleanup remains open.
- Official BLOCKED/110 critical failure observations/384 results/output review 0/30/
  not_production_ready unchanged. Canonical, 1.0.4 and approved 1.0.5 evidence preserved.
  Running backend image not replaced; no Gate promotion or answer-diagnostic advancement.
- Next: isolate label-blind source-selection quality and cost, retaining the guarded pool as an
  experimental baseline. Keep regression checks and add independent questions before quality claims.
- [Protocol, results, limitations and reproduction](rag_complementary_retrieval.md).

## Evidence Remediation 26 Bilingual Retrieval Candidate Not Adopted

- Added isolated query-only English translation with the existing local qwen2.5:1.5b and fixed
  BM25 reciprocal-rank fusion. No labels or expected facts enter translation or candidate ranking.
- Compared all 48 RAG-bearing cases on finalized 1.0.5. Only 22 ordinary cases use candidates;
  26 scope/refusal/combined/Agent preparations retain baseline behavior. No default registration.
- Baseline 25/48 reachable (ordinary 6/22, critical ordinary 1/5). Original-query BM25 23/48;
  translated-query BM25 and bilingual fusion both 27/48 (ordinary 8/22, critical ordinary 0/5).
  Both have four gains and two regressions, KO-RAG-002 and KO-RAG-011. No candidate advances.
- Executed 22 serial local translation calls, zero answer-generation calls. All translation outputs
  pass structural validation, not semantic approval: the KO-RAG-002 translation omits Preflight.
  Recorded requests, raw responses, usage, model digest, fixed protocol and failure fallback policy.
- Windows and Docker offline replays match all 48 result rows with zero new model calls. Fixed
  container source inventory to hash the executed app, and retained the original live harness bytes.
- New tests 48 passed; Docker full backend 844 passed; host/Docker Ruff and image build passed.
  Restarted existing Docker containers without replacing the running backend image.
- Official BLOCKED/110 failed observations/384 results/output review 0/30/not_production_ready and
  canonical/1.0.4/approved 1.0.5 evidence preserved. All four targeted critical failures remain open.
- Next: address translation term loss and multi-source ranking, with separate versioned experiments
  and whole-pack regression checks. Aggregate retrieval gains alone cannot authorize adoption.
- [Protocol, results and reproduction](rag_bilingual_retrieval.md).

## Evidence Remediation 25 RAG Contract Review Finalized

- Validated the user's downloaded 1.0.5 attestation against the revision report and all four case
  hashes. All four decisions are approved. Preserved the downloaded bytes and notes without edits.
- Finalized only the isolated 1.0.5 review manifest: 60 prior review records preserved byte-for-byte,
  four approvals appended, 64/64 source cases approved including 20/20 critical cases. No rejections.
  Questions, expected facts, manifest and case payloads unchanged; canonical and 1.0.4 files untouched.
- `portfolio_ready=true` and `bootstrap_allowed=true` describe source-pack coverage only. They do
  not approve generated outputs, establish model quality, authorize production or promote the Gate.
- Re-audited the five ordinary critical RAG contracts after finalization: 1/5 reachable, four blocked
  at top-5. No new inference, application evidence writes, default retriever changes or Gate adoption.
- Focused host tests 32 passed; Docker full backend 796 passed. Independent hash checks verified
  finalization, original attestation, retained reviews and official evidence protection.
- Official BLOCKED/110 failed observations/384 runtime results/output review 0/30/not_production_ready
  unchanged. Running backend not replaced. Remediation 24 reports remain historical draft snapshots.
- Next: isolated, label-blind retrieval remediation on the approved 1.0.5 contracts, then fresh
  answer/citation evaluation. Do not improve scores by relaxing labels or leaking expected source IDs.
- [Finalization receipt, checks and remaining work](reports/2026-09-10_rag_contract_finalization.md).

## Evidence Remediation 24 Source-Bound RAG Contract Review Draft

- Audited five ordinary critical RAG cases against the frozen corpus. Four source replacements
  proposed; KO-RAG-002 retained. Assessments are assistant-authored, not human approvals.
- Added source-bound question facets with 14 exact quote checks, unique/existing IDs, multi-document
  requirements and default citation-budget validation. No inference or application DB writes.
- Created unfinalized 1.0.5 through the existing revision workflow: 60 retained approvals and four
  pending reviews. Source 1.0.4 and all 64 approvals untouched. Questions, retrieval queries, top_k,
  expected facts, forbidden claims, refusal requirements, criticality and weights unchanged.
- Proposed source reachability is 1/5 versus old 3/5; all four changed cases remain blocked at top-5.
  No query tuning or permissive OR groups were used to turn this diagnostic green.
- New 20 tests passed; final Docker full backend 796 passed; host/Docker Ruff and build passed.
  Running default backend unchanged; official BLOCKED/110 failures/384 results/output review 0/30
  and not_production_ready preserved. No Gate promotion or model-quality claim.
- Readable HTML audit and existing four-case attestation UI prepared. Report export is structurally
  verified semantic fallback after reader_timeout. Browser layout/click QA unavailable; URL policy
  blocked review-page automation and was not bypassed. No review selections prefilled.
- Next: targeted human review of four source changes, then label-blind Korean/English retrieval
  remediation and fresh answer attribution evaluation. Existing semantic scorer remains a limitation.
- [Audit, reproduction and limitations](reports/2026-09-10_rag_contract_alignment.md).

## Evidence Remediation 23 RAG Retrieval And Paired-Quote Diagnostics

- Added isolated SQLite FTS5 BM25/Korean-bigram retrieval, paired source/quote generation and
  non-repairing exact-source validation. No default adapter/retriever/scorer/label changes.
- Whole-pack retrieval comparison: 48 RAG-bearing cases, candidate applied only to 22 ordinary RAG
  cases; 26 fallback preparations unchanged. Reachable contracts 27/48 -> 23/48 (ordinary 8/22 ->
  4/22), four regressions and zero gains. Candidate rejected; Windows/Docker rankings agree.
- Corrected live ablation retains existing retrieval: five critical cases x baseline/paired response,
  one 1.5B model/seed, 768 output tokens. Both 0/5 strict passes; paired quotes exact in 2/5, three
  provenance failures retained. No model-quality gain or promotion. Not comparable to old 384-token runs.
- Initial eight-observation attempt invalidated because label stripping disabled JSON response_format.
  Originals retained; empty label-free shape marker and actual request-schema regression checks added.
- New 56 tests passed; final Docker full backend 776 passed; host/Docker Ruff and image build passed.
  Running default backend not replaced. Official protected evidence unchanged: BLOCKED/110 failed
  observations/384 runtime results/output human review 0/30/not_production_ready.
- Next: audit the five critical question/fact/source contracts, then address Korean-to-English source
  retrieval and answer entailment. Existing source approval is not new output approval; do not relabel
  to make candidates pass. Review material is automatically collected without granting approval.
- [Technical guide](rag_grounding_diagnostics.md);
  [Korean results and limitations](reports/2026-09-10_rag_grounding.md).

## Evidence Remediation 22 Versioned Agent-Aware Critical Evaluator

- Added explicit critical-output-contract-v2 candidate evaluation. Default per-result/Gate/overview
  behavior remains legacy; unknown evaluator versions are rejected. No stored flags are rewritten.
- Reuse the strict Agent trace read schema and check case binding, plan/step/counter consistency,
  failure/policy/approval state, recovery links and nested Tool evidence before accepting Agent plans.
  A scalar single-Tool flag no longer blocks an otherwise valid Agent plan in the candidate version.
- Read-only comparison of the same 60 canary outputs: legacy 22 pass/38 fail, candidate 34 pass/26 fail.
  Only 12 Agent observations change; zero non-Agent changes and zero pass-to-fail changes in this pack.
  This is evaluator correction, not model improvement, fresh inference, review or Gate promotion.
- Added 85 tests; focused canary/evaluator 120 passed; Docker full backend 720 passed; host/Docker
  Ruff and backend build passed. Basic/adaptive Agent fixtures cover retry, memory, recovery and approval.
- Official protected records unchanged: BLOCKED/110 failures/384 results/output review 0/30/
  not_production_ready. Workflow observations remain 15 automated QA and zero participant attempts.
  Inference and prior diagnostic/case sources unchanged; no API/UI/schema or weight changes.
- Remaining candidate failures: 15 ordinary RAG, five single-Tool and six legacy recovery observations.
  Next: RAG retrieval and answer/citation remediation. Any Gate adoption requires separately versioned
  aggregate metrics/evidence and explicit re-evaluation; old snapshots must not change silently.
- [Versioning and reproduction](critical_evaluator_versions.md);
  [comparison and verification](reports/2026-09-10_critical_evaluator_v2.md).

## Evidence Remediation 21 Consolidated Critical Canary

- Re-ran all 20 known critical failure-plan cases on finalized 1.0.4 with the current default
  adapter, three existing configurations and one trial: 60 diagnostic results/metrics, no timeout/OOM.
- Existing common critical evaluator: 22 pass / 38 fail across 13 residual cases. Execution/reliability
  summaries instead report 34 successful results. Do not substitute one metric for the other.
- Identified 12 Agent outputs with successful plans, quality 1 and no execution error, but a false
  scalar tool_call_valid flag causes the common Tool predicate to fail them before Agent checks.
  A read-only counterfactual isolates that condition; no scores or historical flags were changed.
- General RAG remains 0/15; required facts fail in 14/15 and citation precision is below one in 13/15.
  Existing retrieval audit identifies two multi-document cases whose required evidence ranks
  (1,19) and (9,7) fall outside top-5. Three other cases fail despite reachable required evidence.
- Normal Tool 1/6; legacy recovery 0/6 with the previously documented fault-injection/label mismatch.
  Scope/refusal 21/21 remains bounded system behavior, not raw-model or holdout accuracy.
- Added read-only critical_canary snapshot/audit CLI, explicit coverage/provenance checks and
  raw trace export. New tests 35 passed; Docker full backend 635 passed; Ruff/build passed.
- Official evidence hash and 254 source/case file hashes unchanged. Official BLOCKED/110 failures/
  384 results/output review 0/30/not_production_ready preserved. Participant workflow observations
  remain zero; all 15 workflow records are automated QA. No adapter, weight, UI or DB schema changes.
- Next priority: versioned Agent/Tool evaluator contract correction, then retrieval and answer/citation
  remediation. Preserve this diagnostic and the official baseline; do not promote by relaxing rules.
- [Reproduction guide](critical_canary.md);
  [findings and verification](reports/2026-09-10_critical_canary.md).

## Evidence Remediation 20 End-to-End Request Workflow Validation

- Added `/structured-requests/workflow` with ten locally authored tasks that reuse the actual
  structured-request UI and services. This is a development/usability pack, not a blinded holdout.
- A new request_workflow_attempts table atomically links one new contract per attempt. Alembic
  202609100002 is applied; the original 47-table metadata hash remains unchanged (52 total tables).
- Freeze all proposal/execution records at submission, bind the end action to attempt revision and
  full request-state hash, and retain previous incorrect executions after corrections. Separate
  completed, clarification-requested and abandoned dispositions; record self-reported help/feedback.
- Reuse post-submission query diff. Block ending with unsaved draft/unchecked proposal text and
  require explicit acknowledgment. Aggregate attempts separately by source, assistance and pack hash.
- Final Docker backend 600 passed; new workflow tests 30 passed; export-verifier tests 9 passed;
  frontend 29 passed, TypeScript/build/Ruff passed. Four pre-existing navigation lint warnings remain.
  Added workflow export-tool lint/tests to backend CI; remote Actions were not dispatched.
- API QA: 12 synthetic attempts (ten matching, one deliberate misconfirmation, one abandonment).
  Browser QA: three automated attempts, including one real local-model proposal from two recorded
  generation HTTP requests, one clarification and one deliberate whitespace misconfirmation.
  Fifteen total workflow attempts are automated_qa; no participant observations have been collected.
- Ollama was stopped during the first browser generation, which failed. Started the existing runtime
  service and used its existing qwen2.5:1.5b model; retry succeeded. Failed generation is documented,
  not hidden in or counted as a successfully persisted model proposal.
- Fixed JSON download hash portability: preserve exact canonical evidence bytes alongside display
  data. Existing submissions/hashes were not rewritten. Server verifies 15/15 existing results and
  the real re-downloaded browser file passes the independent local export checker.
- All 15 existing input studies and four existing contracts are hash-identical; eleven QA contracts
  were added. Official BLOCKED/110 critical failures/384 results/output review 0/30/
  not_production_ready is unchanged. No model-weight, default adapter or external execution changes.
- Known limitation remains: wrongly confirmed values can still authorize wrong execution. This
  workflow records that limitation; it does not solve semantic intent verification or grant approval.
- Next: participant observations on the new full workflow, then evidence-led UX improvements and
  existing official failure-group remediation. Guidance and automated results are not human review.
- [Usage and technical guide](request_workflow_validation.md);
  [implementation and verification](reports/2026-09-10_request_workflows/verification.md).

## Maintenance 2026-09-10 Frontend Security

- Updated Next.js/eslint-config-next 16.2.10 -> 16.3.4 and PostCSS 8.5.16 -> 8.5.28.
  The existing PostCSS override now references the direct dependency instead of duplicating a stale pin.
  Targeted updates resolve the remaining baseline-browser-mapping, brace-expansion, browserslist and
  js-yaml advisories; sharp/nanoid and platform packages follow their updated parent dependencies.
- npm audit: 14 vulnerable package entries (1 critical/6 high/7 moderate) -> zero on the host and in
  the deployed Docker image, including development dependencies. This is a point-in-time npm audit,
  not a whole-system security certification or a change in official deployment readiness.
- Added nine synthetic browser API/CSRF tests: frontend 29 passed on host and Linux Docker builder.
  Full Docker backend 570 passed; Ruff and TypeScript passed. Frontend lint has zero errors and four
  newly surfaced pre-existing internal-navigation warnings, retained for separate maintenance.
- CI now uses npm ci, audits high/critical findings, runs tests/typecheck/lint/build. Docker also runs
  frontend tests before building and retains package-lock.json in its runtime image. Remote CI was
  not dispatched; equivalent checks and workflow parsing were performed locally.
- Rebuilt/redeployed only the frontend. Verified standalone Next.js 16.3.4, patched sharp AVIF codec,
  desktop/mobile save/edit/submit/reopen/download, local identity display and six HTTP page routes.
  External OIDC is disabled; no live external-provider login success is claimed.
- All 14 pre-existing study records and four request contracts are hash-identical. One separate
  automated_qa study was added for UI regression. Official BLOCKED/110 critical failures/384 results/
  output review 0/30/not_production_ready remains unchanged. No DB migration or evidence promotion.
- [Maintenance report](reports/2026-09-10_frontend_security/verification.md);
  raw audit/state evidence: `artifacts/maintenance/2026-09-10-frontend-security/`.
- Next: fresh, unassisted input tasks and actual contract-workflow usability checks; address the
  four navigation warnings separately without treating either activity as official model approval.

## Evidence Remediation 19 Request Scenario Validation

Query-difference follow-up, 2026-09-10: added a read-only, post-submission comparison for query
mismatches. It highlights additions/omissions and displays whitespace/control characters explicitly,
without normalization, answer repair or re-scoring. Frontend tests 20 passed; related Docker backend
tests 85 passed; lint, TypeScript, Docker build and desktop/mobile browser checks passed. The SRC-03
participant record and official Gate snapshot were identical before/after read-only QA. Existing
Next.js and other dependency audit findings remain a separate maintenance item, not fixed by this UI
change. [Implementation and verification](reports/2026-09-10_request_scenarios/query-diff/verification.md).

Participant follow-up, 2026-09-10 09:51 +09:00: all seven requested input tasks submitted as
participant_self_report; six exact matches and one query mismatch caused solely by a doubled space
in SRC-03. Two additional unsubmitted starts are preserved separately. This was assisted practice:
the conversation supplied priority guidance and the SRC-09 clarification answer. It is not independent
usability evidence, verified human review or a Gate update. [Pilot findings](reports/2026-09-10_request_scenarios/participant_pilot.md).
The implementation/automated-QA checkpoint below predates this participant follow-up.

- Added `/structured-requests/validation` with a fixed 15-case contract regression pack,
  separate outcome counts, expected/observed details, prior runs and JSON export.
- Observed 14 expected behaviors, one explicitly known limitation, zero regressions and zero errors.
  The limitation is real: a proposal matching a wrongly confirmed value can execute despite contrary
  original wording. This is not 15 successful safety cases or a model accuracy measurement.
- Runner invokes the existing contract service with synthetic proposals in disposable in-memory
  SQLite. It makes zero model calls, performs only simulated Tool execution and preserves the live
  structured-request records. Only its report is persisted in a separate table.
- Added seven input exercises with explicit automated_qa/participant_self_report provenance,
  revision/hash-bound save and submission, correction counts, elapsed time and reopen/export.
  The source is immutable but self-reported, never verified human review or official Gate evidence.
- Elapsed time includes idle/reload time; corrections count changed saved answers after first save,
  not keystrokes. The exercise is separate from the full request execution workflow. Locally authored,
  repetitive fixtures and answer keys in exported automated reports preclude a blinded holdout claim.
- Added two tables via Alembic 202609100001 (applied), retaining the original 47-table metadata hash.
  Fixed a latent import cycle by deferring the Tool module import within the lab registry helper;
  historical inference/diagnostic sources remain unchanged.
- New tests 34 passed; related tests 85 passed; host 569 passed/1 skipped; Docker 570 passed.
  Host/Docker Ruff, frontend lint/TypeScript and Docker frontend build passed. Services rebuilt/running.
- Live API smoke preserved official metrics and existing request records. Browser checks covered
  execution/filter/export, keyboard tabs, save/acknowledgment invalidation, submit/reload and desktop
  1440x1000/mobile 390x844 layouts. All four live input QA records are automated_qa, not participants.
- Prior evidence chain re-audited; finalized 1.0.4 remains 64/64 approved, critical 20/20. Official
  BLOCKED/110 critical failures/384 results/output review 0/30/not_production_ready is unchanged.
- Next: collect separately labeled participant feedback, then extend fresh tasks and test the actual
  end-to-end confirmation workflow before external execution design or official Gate re-evaluation.
- [Korean usage and technical guide](request_scenario_validation.md);
  [engineering verification](reports/2026-09-10_request_scenarios/verification.md).
  API QA SHA-256: `24341b9411e9d73ad21d546c4c4d632cd30f99eed789c6a618b4ed9c2ba6d5cd`.

## Evidence Remediation 18 User-Confirmed Structured Request Lab

- Added an isolated `/structured-requests` UI and API: persist a draft, explicitly choose priority
  value or omission, separately confirm exact query/priority, compare a proposal and explicitly
  simulate execution. Unresolved priority has no implicit default and cannot be confirmed.
- Pure comparison covers the single public create_ticket contract and exact query/priority presence.
  No model-based intent verifier, expected-label repair or confirmed-value injection into generation.
  Optional generation reuses v3 with the original request and public Tool descriptor only; fixed local
  Ollama candidates do not inherit external endpoint settings or API credentials.
- Revision/hash binding, 15-minute expiry, revocation, proposal/tool source hashes and execution-time
  revalidation fail closed. PostgreSQL row locking plus optimistic version flush precedes the local
  handler. One execution per confirmed revision; repeat calls for the same check return its receipt.
- Authentication uses server middleware identity and owner scoping. Local demo identity remains
  unverified/shared local-ui, explicitly recorded as local_unverified_assertion. An API acknowledgment
  is not proof of human review. No real external Tool execution or production security is claimed.
- Added two separate lab tables via Alembic 202609090001 (applied). Existing 47-table metadata hash and
  historical inference/diagnostic code remain unchanged; new models also use compatibility imports.
- Focused tests 49 passed; host 535 passed/1 skipped; Docker 536 passed; Ruff/frontend lint/TypeScript
  and Docker frontend build passed. Backend/worker/frontend rebuilt and restarted.
- Live PostgreSQL concurrent execution returned 200/409 with one handler invocation; same-check retry
  returned its existing receipt. Wrong priority and stale revision blocked. API and browser each
  generated one actual local-model QA proposal; these are engineering checks, not accuracy evidence.
- Browser save/confirm/block/generate/simulate/persistence checks passed at desktop/mobile widths;
  screenshots saved. Every QA request is explicitly automated, not a human attestation.
- Prior evidence chain re-audited; finalized 1.0.4 remains 64/64 approved, critical 20/20. Official
  BLOCKED/110 critical failures/384 results/output review 0/30/not_production_ready is unchanged.
- Next: independent scenario/usability validation of structured input and confirmation burden before
  authenticated external execution design or any official Gate re-evaluation.
- [Korean usage and technical guide](structured_request_contracts.md);
  [engineering verification](reports/2026-09-09_structured_requests/verification.md).
  API QA SHA-256: `cf404d557db63ae8ed7c078e9e50d8234fda58b17f747de1765ab2aff0b0c7d7`.

## Evidence Remediation 17 Request-Only Priority Verification

- Added an opt-in priority verifier after unchanged v3 generation. A separate same-model call sees
  only the original request and public selected Tool information, never proposed arguments or labels.
  Strict intent/evidence checks can veto execution without editing arguments; malformed responses,
  non-stop termination and timeouts fail closed within the shared 120-second case budget.
- Scope is create_ticket.priority only. Exact evidence quotations do not prove semantic correctness;
  wrong Tool selection, query content and external authorization are not covered. Execution fixtures
  bind to the proposed Tool, not the evaluator's expected selection; private labels cannot block calls.
- Preserved initial v1 transport failure: 28 classifier requests received HTTP 400 from Ollama grammar
  expansion of maxLength=2000. v1.1 omits that bound only from the wire schema and retains local
  length validation. Original source is archived by hash. Failed transport is not efficacy evidence.
- Corrected development: known low omissions blocked 4/4 and high preserved 4/4, but 8/19 exact
  proposals falsely blocked and 3/4 conflicting requests still accepted. No argument repair occurs.
- Fresh 16 requests x two orders x two seeds: 64 paired proposals. Unsafe accepted calls fall 24 to 4;
  exact completions fall 40 to 28 out of 52 actionable observations. Normal proposals falsely blocked:
  12/40 (30%). Clarification-required requests blocked 8/12, not all for correct semantic reasons.
- Fresh remaining unsafe approvals are all four repeats of contradictory send/omit normal instructions.
  Genuine omission, quoted example values and unspecified priority account for the 12 false blocks.
  Ticket intent classification matches 36/56; non-ticket scope controls add 8 matches (44/64 total).
- Fresh tokens rise 80,008 to 106,752 (+33.4%). All 184 HTTP responses finish normally, but eight
  classifier outputs fail local contract validation. Corrected development/fresh total 96 proposals,
  276 HTTP calls and 576 paired fault traces; cases are local, unreviewed and repeated, not a holdout.
- Independent source/journal/raw-response/usage/handler-argument audit and executed notebook passed.
  Focused tests 36 passed; host 486 passed/1 skipped; Docker 487 passed; Ruff passed. Backend/worker
  rebuilt/restarted; Alembic head unchanged. Finalized 1.0.4 remains 64/64 approved, critical 20/20.
- Candidate is not promoted: official BLOCKED, 110 critical failures, 384 results, output review 0/30,
  not_production_ready. No diagnostic DB writes, default/API registration or model-weight changes.
- Next: prefer a separately defined, user-confirmed structured request contract with explicit
  value/omission and clarification states over further same-model prompt accumulation. That UI/API
  contract was not implemented at that checkpoint; the isolated Remediation 18 lab above implements
  its first local-only version. Validation is still required before enabling real execution.
- [Technical findings and reproduction](ticket_priority_verification.md);
  executed notebook/audit: `docs/reports/2026-09-09_ticket_priority/`.
  Fresh artifact SHA-256: `eab905ab59bc1c8ee167cd1104f1fb2f75b7e794963b8f14bbf2887d22bfe2fe`.

## Evidence Remediation 16 Explicit Optional Argument Presence

- Preserved unsuccessful prompt-only v2 and added isolated v3: optional public arguments become
  required nullable fields only in the model response protocol. Null is a model-owned omission
  marker; all included values are copied unchanged and passed through the existing public guard.
  This is not expected-value repair or a runtime intent guard. Public Tool schemas remain unchanged.
- Known high regression TFB-203: v1/v2 omit high in all four repeats; v3 preserves it in all four.
  Development v3 exact/default-equivalent 16/16 versus v1 12/16. These are known development cases.
- Fresh 14-request comparison: baseline 32/56 exact and 35/56 equivalent; v1 and v3 each 50/56
  for both. v3 high 8/8, low 4/8, normal 8/8, omitted 8/8. One low request containing negated
  omission language still fails all four repeats; two wrong Tool selections also remain.
- Fresh measured tokens: v1 67,356, v3 70,062 (+4.0%). No net fresh accuracy improvement over v1.
  The v3 null ledger makes omissions auditable but cannot guarantee they match user intent.
- Three preserved experiments total 264 final outputs, 440 HTTP calls and 792 local fault traces.
  Do not pool development/fresh accuracy or count replay traces as independent model generations.
  Cases are locally authored, unreviewed and repeated across two catalog orders and two seeds.
- Independent raw-output/source/journal/usage audit and executed notebook passed. Archived the
  original v2 runner by hash before adding v3 support; old evidence resolves to that byte-exact
  source snapshot. The active CLI remains one entry point; previous frozen code stays unchanged.
- Focused tests 28 passed; host 450 passed/1 skipped; Docker 451 passed; Ruff passed. Backend and
  worker rebuilt/restarted. Alembic remains 202608040001. Finalized 1.0.4: 64/64 approved, critical 20/20.
- Official state remains BLOCKED, 110 critical failures, 384 results, output review 0/30,
  not_production_ready. No model-weight/default/API/Gate promotion or diagnostic DB writes.
- Next: separate explicit values, genuine omission and negated/quoted/conflicting instructions in
  a new request-constraint candidate and fresh cases. Preserve the new low failure as development
  evidence. Address remaining Tool-selection errors separately before real API integration.
- [Findings, protocol and reproduction](tool_optional_presence.md);
  executed notebook/audit: `docs/reports/2026-09-09_tool_presence/`.
  Fresh artifact SHA-256: `c7d745ad01978de0ce70d8f88b20e5a383e599bfa0367a04fef291943214241a`.

## Evidence Remediation 15 Exact Fidelity and Local Default Equivalence

- Added an evaluator-only, versioned default-equivalence policy. Only omitted local ticket priority
  versus explicit normal is equivalent. Exact fidelity remains separate; changed queries, high/low
  omission, invalid calls and wrong Tools remain failures. Captured/executed arguments are not repaired.
- The policy checks the local handler source hash, function, version and optional schema. It is not
  a runtime semantic guard and does not cover external services, content correctness or authorization.
- Compared unchanged baseline/two-stage adapters on 14 fresh local requests, two catalog orders and
  two seeds in the 1.5B/v1 setting: 112 final outputs, 168 HTTP calls, 336 paired fault traces.
  Cases and policy were fixed before generation, but are locally authored and not independently reviewed.
- Baseline exact 46/56, candidate exact 48/56. Default-equivalent calls are 48/56 for both. Candidate
  token usage rises 50,368 to 67,851 (+34.7%). There is no observed net default-equivalence advantage.
- Candidate preserves a conversation query in four observations but drops explicit high priority in
  all four repeats of another request. Its first stage and baseline preserve high. This is a real local
  value mismatch, not a default-only difference; the optional schema does not block it at execution time.
- Recorded a separate post-hoc addendum for the previous 144 outputs. Prior 1.5B challenge candidates
  remain exact 9/12, with default-equivalent 11/12 as an additional metric. No old result was overwritten.
- Independent raw-output/source/journal/pair/usage audit and executed notebook passed. Focused tests:
  31 passed; host regression: 422 passed/1 skipped; Docker: 423 passed. Backend/worker rebuilt and restarted.
- Official state unchanged: BLOCKED, critical failures 110, results 384, output review 0/30,
  not_production_ready. Finalized 1.0.4 remains 64/64 approved, critical 20/20. No default/API/Gate promotion.
- Next: isolate a new candidate for explicit-priority preservation, keep these failures as development
  regressions and validate on new requests before real content/authorization work or API integration.
- [Criteria, findings and reproduction](tool_default_semantics.md);
  executed notebook/audit: `docs/reports/2026-09-09_tool_default_semantics/`.
  Raw artifact SHA-256: `ed5c3b2304d89e6241f7e713480798b78f068565a690498271933d8c911abd50`.

## Evidence Remediation 14 Selected Tool Argument Generation

- Added a diagnostic-only two-stage candidate without changing the default adapter, API factory,
  frozen baseline code, model weights, finalized source cases or approval state. Stage1 retains the
  legacy full-call prompt; stage2 receives the original request and selected Tool schema only.
  The final envelope is assembled without argument repair. Actual stage responses remain available.
- Completed 144 final-output observations from 252 HTTP model calls, replayed in 432 local fault
  traces. Frozen comparison uses 72 candidate observations; six new requests in two Tool orders
  provide 36 contemporaneous baseline/candidate pairs. No runtime errors; all HTTP usage captured.
- Frozen exact Tool plus arguments: historical 43/72, current stage1 44/72, final 55/72.
  By entry: small 13/24 to 11/24; medium 16/24 to 24/24; prompt variant historical 14/24,
  current stage1 15/24, final 20/24. The small model regresses; do not enable this globally.
- New requests: baseline 19/36 versus candidate 27/36 (each candidate entry 9/12). Four 1.5B
  omissions of explicit priority=normal fail literal matching but retain the mock handler's default
  effect. Exact-value fidelity is not equivalent to broad semantic execution correctness.
- Within-candidate frozen runs have 15 improvements and 4 regressions; challenge has 11 and 3.
  Stage1 selections match paired baselines, while some first-stage arguments vary across runs.
  Challenge measured tokens rise 32,898 to 44,061 (+33.9%); local timing is not controlled SLA evidence.
- Independent raw-output/hash/journal/request/usage audit and executed notebook passed. Host tests:
  391 passed/1 skipped; Docker: 392 passed; focused tests: 24 passed. Backend/worker rebuilt after
  measurement and restarted. Source validation remains 64/64 approved, critical 20/20.
- Official state unchanged: BLOCKED, 110 critical failures, 384 results, actual output review 0/30,
  not_production_ready. The diagnostic makes no application DB writes and is not official Gate evidence.
- Next: separate optional-value fidelity from semantic default equivalence, test fresh independent
  requests and remaining Tool-selection errors, then validate real content/authorization before
  considering API integration or promotion. The candidate remains opt-in CLI only.
- [Technical findings and reproduction](tool_two_stage_argument_generation.md);
  executed notebook and audit: `docs/reports/2026-09-09_tool_two_stage/`.
  Raw artifact SHA-256: `f122e1e6cb38c349b00d8d35769f279a21786a16139f1ab4834eff36558f0ca8`.

## Evidence Remediation 13 Paired Tool Model Baseline

- Added an isolated, versioned 12-case Korean Tool diagnostic with ordinary business arguments.
  Cases are locally authored and not human-reviewed. Finalized 1.0.4 and its legacy recovery labels
  remain unchanged; there is no automatic source-case migration or approval.
- Ran 72 actual generations: 12 cases x three existing runtime/prompt entries x two trials. Each
  output is replayed unchanged in normal, transient-once, and permanent environments (216 traces).
  Expected labels and fault settings are excluded from model inputs; actual HTTP bodies are saved.
- Selection 59/72, public schema validity 72/72, guard eligibility 72/72, normal fixture success
  59/72, exact Tool plus explicit values 43/72. Sixteen fixture successes contain wrong values.
  Exact calls by entry: small 13/24, medium 16/24, prompt variant 14/24. No runtime errors occurred.
- Normal/transient fixtures each pass 59/72; permanent fixtures pass 59/72 while Tool success is
  0/72. All 13 wrong selections are not exercised in each mode. Retries remain executor-controlled;
  this is not evidence of model recovery ability or a comparison with legacy recovery totals.
- Database-free evidence runner; no new official Benchmark/Portfolio/Gate records. Independent
  notebook/SQLite reconciliation passed for all 72 generations and 216 paired traces. Raw artifact
  hash: `27975681d2f2b53bad53c44d19346e5d9d7a47fa28f32a7d226faeecd388497f`.
- Host regression: 367 passed/1 skipped; Docker: 368 passed; new tests: 11 passed; Ruff passed.
  Backend/worker rebuilt and restarted. Source validation remains 64/64 approved, critical 20/20.
- Official state remains BLOCKED, 110 critical failures, 384 results, and actual output review
  0/30. `not_production_ready` remains in effect. No model weights or default prompts were changed.
- Next: isolate argument generation as an opt-in candidate, test requested-value preservation and
  selection regressions against the frozen baseline plus new requests, then validate real content
  and authorization. Small local exact-literal samples cannot establish general model superiority.
- Technical guide: [Paired Tool Fault Model Baseline](tool_fault_model_baseline.md).
  Canonical report input and executed notebook: `docs/reports/2026-09-09_tool_fault_baseline/`.

## Evidence Remediation 12 Environment-Owned Tool Faults

- Completed the fault-injection separation step. An opt-in, persisted `tool-fault-scenario-v1`
  controls normal, transient-once, and permanent faults before local Tool handlers. The public
  registry omits `simulate_failure`; generated arguments are not repaired or rewritten.
- Trusted fault state stays outside model inputs. Independent trials record injected failures and
  real handler invocations separately in v2 traces. Invalid calls are blocked before either occurs.
- Fixture compliance is separate from Tool success: a permanent-failure fixture can pass because
  execution fails and stops. Retries are executor-controlled, not model reasoning or recovery.
- Separate Deployment Configurations and `data_source=tool_fault_fixture_diagnostic` are required.
  Per-run fault overrides, legacy recovery labels, and unsupported Agent/RAG/multi-step workflows
  are rejected. Gate evaluation rejects fault configurations; evidence collection excludes their
  diagnostic run source even if configuration settings later change.
- Host and Docker scripted checks each passed 54/54: six Tools x three modes x three trials.
  Normal and transient calls each succeeded 18/18; permanent calls succeeded 0/18 as intended.
  Each environment recorded 36 injected faults and 36 handler invocations. No model inference or
  database writes were performed by these checks; implementation, corpus, and manifest hashes match.
- Verification: host 356 passed/1 skipped (Windows symlink), Docker 357 passed, focused new tests
  50 passed, host/Docker Ruff passed. Dependency deprecation warnings remain. Backend and Agent
  worker rebuilt/restarted; backend healthy; Alembic head remains `202608040001`.
- Finalized 1.0.4 validation remains 64/64 approved, critical 20/20, same locked corpus. Official
  overview still reports BLOCKED, 110 critical failures, 384 results, and 0/30 output reviews.
  No source-case migration, new authoritative evidence, or production-readiness promotion occurred.
- Next: create a separate compatible diagnostic case set and establish a fair model-generation
  baseline, then assess argument semantics and real document/authorization behavior. This step
  does not establish improved model accuracy or broad recovery ability.
- Technical contract, reproduction commands, artifact hashes, and limitations:
  [Environment-Owned Tool Fault Scenarios](tool_fault_scenarios.md).

## Evidence Remediation 11 Non-Repairing Tool Arguments

- Adapter v21 uses `bounded-tool-call-contract-v2`. It preserves model arguments, rejects invalid
  schema/JSON, checks IDs against the configured corpus, and requires explicit runtime authorization
  for failure simulation. Rejected calls cannot invoke the Tool handler.
- This supersedes v1 argument repair described in the historical Remediation 9/10 sections below.
  Tool selection prompts remain legacy by default; the compact candidate is still opt-in.
- Offline audit of the same 72 v20 raw responses: 53 had been changed by v1; schema-valid 50/72,
  v2-eligible 15/72, correct selection plus eligibility 10/72. Of 56 prior successes, 46 are blocked.
  These are changed validation/authorization rules, not 46 independently proven grading errors or
  measured new-model execution successes. The old prompts had no trusted document catalog.
- Fresh finalized-1.0.4 diagnostic: selection 44/48, actual fixture success 5/48 (4, 1, 0 by entry),
  timeout/OOM zero. Normal Tool success 5/30; recovery 0/18 under disabled failure simulation and
  unchanged recovery labels. This is not a fair before/after recovery-model comparison.
- Runtime traces: all 36 guard rejections had zero handler attempts; 48/48 argument hashes match.
  Query relevance, document ACLs/content, Agent/RAG/multi-step boundary coverage remain unverified.
- Tests: host 306 passed/1 skipped, Docker 307 passed, audit tool 4 passed; Ruff and notebook count
  reconciliation passed. Backend/worker rebuilt, source 64/64 and critical 20/20 validation unchanged.
- Official overview remains BLOCKED: 110 critical failures, 384 results, 0/30 actual output reviews.
  No authoritative promotion; `not_production_ready` remains in effect.
- Next: separate fault injection from model arguments, test schema-specific argument generation,
  add real document/authorization checks, then expand repeat evaluation and output review.
- Technical guide: `docs/tool_argument_validation.md`. Korean review:
  `docs/reports/2026-09-09_model_atlas_evidence_remediation_11_tool_arguments.md`.
  HTML delivery is withheld after a portable-renderer horizontal-overflow QA failure; canonical
  report input and the verified companion notebook are retained with the Markdown review.

## Evidence Remediation 10 Tool Selection Candidate

- Added `public-tool-selection-prompt-v1` and the final OpenAI-compatible adapter v20.
- The new compact public-input prompt is opt-in. Default configurations retain legacy prompts
  because the experimental candidate introduced two case-level regressions despite a better total.
- Same finalized-1.0.4 Tool/recovery comparison: selection and normalized execution `41/48 -> 43/48`.
  Small baseline `10/16 -> 13/16`, medium candidate `15/16 -> 15/16`, prompt variant `16/16 -> 15/16`.
- New local challenge requests: selection `46/72 -> 56/72`. Final v20 opt-in execution reproduced
  `56/72`; reversing catalog order produced `65/72`, demonstrating material order sensitivity.
- Raw argument validity decreased `54/72 -> 50/72`; normalized argument validity increased
  `67/72 -> 72/72`. These are separate measurements, not an unconditional raw-model improvement.
- Added secret-label invariance, public-instruction preservation, custom/new Tool, schema fallback,
  execution-path isolation, and activation/default tests. Final host suite: 282 passed, 1 skipped;
  Docker suite: 283 passed; Ruff passed. Backend rebuilt and healthy; Agent worker rebuilt and running.
- Source cases, the default runtime matrix, existing Deployment Configurations, Portfolio Results,
  and Gates remain unchanged. The default system's seven residual Tool selections are not claimed
  to be fixed. Official overview remains BLOCKED with 110 critical failures and 0/30 output reviews.
- Next: evaluate argument semantics and compiler boundaries, retain separate raw/normalized
  evidence, and address selection regressions/order sensitivity before candidate promotion.
- Usage: `docs/tool_selection_diagnostics.md`. Evidence and limitations:
  `docs/reports/2026-09-07_model_atlas_evidence_remediation_10_tool_selection.md`.

## Evidence Remediation 9 Tool Contract Diagnostic

- Added `bounded-tool-call-contract-v1` to the OpenAI-compatible adapter v18.
- The compiler uses only the public request and `available_tools` Registry descriptors. It never
  reads the expected Tool name, expected argument schema, or example arguments.
- Model Tool selection and raw output remain unchanged. The compiler only normalizes arguments for
  the Tool the model selected, and records every removal, fill, and replacement in
  `metadata_json.tool_call_contract`.
- Normal calls now remove unrequested failure fixtures; explicit transient-recovery requests add
  `simulate_failure=transient_once`; blank required query/document identifiers are recovered from
  the public request; unknown Tool selections remain failures.
- In an isolated 48-result before/after diagnostic, successful execution improved from `14/48` to
  `41/48`, and argument validity improved from `14/48` to `42/48`, while selection stayed exactly
  `41/48` in both runs.
- The medium candidate improved from `5/16` to `15/16`; its only remaining failure was a wrong Tool
  selection. The prompt variant improved from `5/16` to `16/16`. The 0.5B baseline improved from
  `4/16` to `10/16`, with six residual Tool-selection failures.
- All 15 correctly selected recovery calls retried once and recovered. No canonical case pack,
  finalized revision, Portfolio, or Gate was modified; production readiness remains
  `not_production_ready`.

## Evidence Remediation 8 Finalized And Diagnosed

- Added `rag-semantic-contract-v2`: all facts inside a group are required, while one complete,
  explicitly reviewed group is sufficient. The legacy `required_facts` list remains the primary
  group.
- Added `rag-bounded-answer-contract-v1` for scope and refusal cases. It derives the exact allowed
  answer from only the public query and selected source claim, without evaluator ground-truth
  leakage.
- Upgraded the RAG evaluation trace and summary to v5, the RAG scorer to v5, and the
  OpenAI-compatible adapter to v17. Traces now expose alternative fact-group matches and bounded
  answer-contract status.
- Rebuilt the Docker backend, Agent worker, and frontend; Alembic remains at head. The app detail
  screen was checked at desktop and mobile sizes.
- Actual finalized-1.0.3 diagnostic after the answer-contract change: strict RAG success `15/21`,
  bounded-answer compliance `21/21`, retrieval/selection/citation `21/21`, refusal `12/12`,
  groundedness `1.0`, unsupported-claim rate `0.0`, timeout `0`, and OOM `0`.
- The only six remaining failures are `KO-RAG-SCOPE-002/003` in each configuration. They fail the
  unchanged v1 required-fact labels while satisfying the selected evidence and answer contract.
- Reviewer `김대건` approved both isolated `1.0.4` semantic changes through a v2 attestation bound
  to report and case hashes. Final validation is 64/64 approved, critical 20/20,
  `portfolio_ready=true`, and `bootstrap_allowed=true`.
- Actual finalized-1.0.4 diagnostic: strict RAG success `21/21`, semantic contract `21/21`, bounded
  answer `21/21`, retrieval/selection/citation `21/21`, refusal `12/12`, groundedness `1.0`,
  unsupported-claim rate `0.0`, timeout `0`, and OOM `0`.
- Scope 002 and Scope 003 satisfied reviewed semantic group index 1 and citation group index 1 in
  all three configurations, producing six actual alternative-semantic matches.
- No canonical case pack, finalized 1.0.3, historical Result, authoritative Portfolio evidence, or
  Gate was rewritten. Diagnostic success is narrow contract evidence, not general model-quality or
  production approval; production readiness remains `not_production_ready`.

## Evidence Remediation 7 Finalized And Diagnosed

- Added `rag-evidence-contract-v2` with AND-within-group and OR-between-group semantics.
- Preserved legacy `relevant_chunk_ids` as the primary group and model-input secrecy boundary.
- Applied best-group matching consistently to retrieval, deterministic selection, and citations.
- Added contract version, acceptable groups, matched group indexes, and satisfaction flags to
  retrieval/evaluation trace v3/v4 and scorer v4.
- Finalized isolated case pack `1.0.3` after hash-bound human approval of exactly
  `KO-RAG-SCOPE-002`, `KO-RAG-SCOPE-003`, and `KO-REFUSE-002`.
- Finalized pack validation: 64/64 approved cases, 20/20 approved critical cases,
  `portfolio_ready=true`, and retrieval audit `3/3` reachable with zero blocked.
- Actual 21-result Ollama diagnostic: strict RAG success `14/21`, citation and deterministic
  evidence-selection contracts `21/21`, alternative-group matches `9`, refusal `12/12`,
  groundedness `1.0`, and unsupported-claim rate `0.0`.
- Remaining failures are six required-fact alignment failures for `KO-RAG-SCOPE-002/003` and one
  forbidden-claim violation from the 0.5B model on `KO-RAG-SCOPE-001`.
- The diagnostic did not rewrite canonical cases, historical Results, Portfolio evidence, or Gates;
  production readiness remains `not_production_ready`.

## Evidence Remediation 6 Completed

- Query-only deterministic sentence selection over retrieved top-k evidence.
- Selected chunk, source rank, extracted claim, confidence, abstention, and selector provenance.
- Strict citation and source-claim enums for scope/refusal evaluation categories.
- Bounded deterministic refusal answers derived from only the public query and selected evidence.
- RAG retrieval/evaluation/summary v2/v3/v3 and scorer v3 with historical trace compatibility.
- RAG trace UI support for selected evidence, confidence, and selection recall.
- Final 21-result Ollama diagnostic: JSON `21/21`, groundedness `1.0`, unsupported rate `0.0`,
  refusal `12/12`, and strict RAG success `11/21`.
- Three single-ID ground-truth conflicts recorded without mutating finalized `1.0.2` or canonical
  Portfolio/Gate evidence.

## Sprint 4A Completed

- Central evidence source and score trust classification.
- Legacy `captured_local -> local_authored` normalization.
- Configurable judge and production evidence thresholds.
- Adapter and scorer descriptors with persisted provenance.
- Gate evidence snapshot v2 and release readiness snapshot v2.
- Trust-aware release and production readiness mapping.
- Frozen release decision trust and snapshot drift detection.
- Non-persisting Gate Preflight API and UI flow.
- Control-plane Overview API with workflow, blockers, and next actions.
- Discover / Validate / Release / Audit navigation.
- Gate report hierarchy focused on decision reasons and actions.
- Release Readiness separation of Gate, Evidence Trust, Release, and Production states.
- Judge Review coverage metrics.
- Golden Demo documentation for deterministic fixture and local Ollama.

## Sprint 4B Completed

- Versioned, bounded local Tool Registry with six deterministic tools.
- Single-call, OpenAI-native-shaped, and multi-step call parsing.
- Registry and case-level argument schema validation.
- Actual in-process handler execution with output validation.
- Retryable and permanent failure classification with a maximum attempt limit.
- Retry recovery and ordered multi-step trace capture.
- Trace persistence in result metadata and execution logs without a DB migration.
- Executable tool scorer v2 and heuristic scorer registry v2.
- Tool selection, argument, execution, sequence, and retry Gate metrics.
- Reproducible ten-case suite and tool-specific Acceptance Policy.
- Tool Registry and benchmark execution detail APIs.
- Benchmark Tool Trace UI and Gate-to-trace navigation.
- Gate evidence snapshot v3 with tool registry and trace provenance.

## Sprint 4C Completed

- Versioned local corpus registry with stable corpus hash.
- Deterministic lexical retriever with version, top-k, and minimum-score configuration.
- Immutable RAG deployment configuration using `retrieval_config_json`.
- Retrieval before adapter generation with ground-truth leakage prevention.
- Structured answer, citation, and atomic-claim output contract.
- Retrieval recall, citation precision/recall, groundedness, and unsupported-claim evaluation.
- RAG scorer and five Gate metrics.
- Ten-case local RAG suite and dedicated Acceptance Policy.
- Corpus/retriever APIs and RAG trace UI.
- Gate-to-RAG-trace navigation for critical failures.
- Gate evidence snapshot v4 with corpus, retriever, and RAG trace provenance.

## Sprint 4D Completed

- Repeated trials with one persisted result, metric, log stream, and trace per attempt.
- Bounded concurrency over frozen adapter snapshots without cross-thread ORM access.
- OpenAI-compatible case timeout propagation and reliability-mode exception capture.
- Separate success, timeout, OOM, and error states.
- P50/P95/P99 latency, TTFT, throughput, per-case variance, trial coverage, and context-stress
  summaries.
- Seven reliability Gate metrics and a dedicated Acceptance Policy.
- Six-case, 30-trial seed pack with Runtime A/B fixtures.
- Same-suite runtime comparison API and UI.
- Benchmark reliability controls and scan-oriented trial detail.
- Gate-to-reliability-trace navigation for critical failures.
- Gate evidence snapshot v5 with runtime reliability provenance.
- `p99` metric aggregation migration.

## Sprint 5A Completed

- Plan-first bounded Agent executor with five allowlisted actions and hard per-action limits.
- Sanitized Agent context that keeps expected action contracts out of real adapter input.
- Versioned operational-memory registry with content hashes and allowlisted reads.
- Deterministic task-local memory writes with `persisted=false`.
- Existing Tool Registry and RAG retriever reuse inside Agent steps.
- Retry recovery, action-sequence, policy-violation, and final-response evidence.
- Agent scorer, eight Gate metrics, eight-case suite, and dedicated Acceptance Policy.
- Agent runtime and memory-registry APIs.
- Non-persisting semantic replay with version checks, signatures, and changed paths.
- Agent trace and replay UI plus Gate-to-trace navigation.
- Gate evidence snapshot v6 with Agent runtime, execution, and memory provenance.

## Sprint 5B Completed

- Agent runtime/context/trace/summary v2 with v1 trace-read compatibility.
- Versioned observations for every executed base and recovery step.
- One-shot replan and two-step recovery budgets with predeclared branch selection.
- External approved, denied, and pending human checkpoint decisions.
- Guarded-action enforcement and fail-closed checkpoint halting.
- Decision actor, reason, source, policy version, and SHA-256 hash provenance.
- Seven additional Gate metrics and critical-case halt/replan/approval fields.
- Five-case Adaptive Agent Operations suite and dedicated policy.
- Approval controls, recovery trace UI, and Gate snapshot v7 provenance.

## Sprint 5C Completed

- Persistent `agent_approval_checkpoints` state with request, decision, revocation, and resume
  hashes.
- Verified trusted-header identities, role policy, separation of duties, and one-hour secure
  default expiry.
- Optimistic versions and row locks for decision, revocation, and resume transitions.
- Idempotent synchronous resume baseline that replays the stored plan. Sprint 5D supersedes its
  mutation behavior with append-only child revisions.
- Execution-detail Agent approval control panel; benchmark creation no longer self-attests a
  wildcard approval.
- Optional one-call live-replan callback with tokens, latency, cost, model, provider, and response
  hash provenance.
- Verified production Agent evidence import with normalized trace hash, source-event deduplication,
  bounded-trace validation, and fixture provenance rejection.
- Additive Alembic revision `202607130001` and Agent Control Plane documentation.

## Sprint 5D Completed

- Append-only child `BenchmarkRun`, `BenchmarkResult`, and `InferenceMetric` revisions with
  parent/root lineage and evidence hashes.
- Latest-revision-only Gate aggregation, evidence snapshot v8, automatic stale/readiness blocking,
  and superseding Gate links.
- Durable PostgreSQL jobs for resume, reconciliation, and production traffic evidence with dedupe,
  row locks, leases, expiry recovery, bounded retry, and result/error records.
- Docker Compose Agent worker with backend health dependency and periodic checkpoint/Gate
  reconciliation.
- Strict HS256 bearer JWT validation with expiry/time/issuer/audience checks and trusted-proxy
  exact-host/CIDR enforcement.
- OpenAI-compatible, one-shot live replan provider with strict JSON, bounded timeout/tokens, cost
  provenance, environment-only secrets, and network-free recorded replay.
- Per-source HMAC-SHA256 traffic batches with verified machine identity, canonical signatures,
  dedupe, and atomic multi-event import.
- Async resume job UI, revision lineage links, stale Gate warning/rerun action, and production
  replan configuration controls.
- Additive Alembic revision `202607130002` and Agent Orchestration documentation.

## Sprint 5E Completed

- OIDC discovery, direct JWKS configuration, RS256 verification, cache TTLs, and unknown-key
  refresh while retaining static HS256 compatibility.
- Worker registration, heartbeats, online/offline state, queue health, latency/duration summaries,
  dead-letter metadata, and verified-role requeue.
- HMAC v2 traffic signatures with key IDs, nonce replay protection, clock-skew checks, gzip bounds,
  receipt persistence, source health, and a reference outbox collector.
- Append-only release operational actions for stale detection, review request, acknowledgement,
  revocation, and replacement lineage.
- Durable `model_validation_campaign` jobs that reuse the benchmark execution engine.
- Runtime validation JSON/Markdown reports with source cohorts, comparisons, judge calibration,
  Evidence Trust, and configured-versus-observed model identity.
- Dedicated `/model-validation` UI, CLI export, Ollama profile, and Make helpers.
- Additive Alembic revisions `202607170001` through `202607170004`.
- Real Ollama `qwen2.5:0.5b` campaign completed on the first attempt with five results and five
  metrics.

## Sprint 5F Completed

- Server-observed Ollama manifests, SHA-256 artifact digests, verified operator provenance, and
  idempotent artifact attestations.
- Digest-pinned immutable deployment configurations and model-validation report v2 with explicit
  missing, verified, digest-mismatch, and model-mismatch states.
- Append-only judge review decisions with verified-role RBAC, separation of duties, prior/applied
  score snapshots, rationales, and review hashes.
- Browser Authorization Code + PKCE, state/nonce verification, RS256 ID-token verification,
  short-lived HttpOnly sessions, shell sign-in controls, and a Keycloak development profile.
- JSON and Prometheus operational metrics, derived alerts, Operations UI, Prometheus/Alertmanager
  examples, and a reference alert sink.
- Versioned Tool/RAG isolation registry, fail-closed execution preflight, persisted preflight
  evidence, UI, and hardened Docker examples.
- Additive Alembic revisions `202607200001` through `202607200003`.
- Matching `qwen2.5:0.5b` configuration and five-case actual runtime campaign with two verified
  human review decisions, including one critical case.
- Desktop and 390px mobile browser QA, including select overflow and hydration consistency fixes.

## Sprint 5G Completed

- Fail-closed compact JWS verification against configured JWKS, issuer, algorithm, key ID, issued
  time, statement ID, size, and replay policy.
- in-toto-style model statements binding the observed artifact digest, runtime attestation and
  manifest hashes, and canonical CycloneDX SBOM digest.
- Immutable supply-chain attestations with separated append-only revocation actions.
- Signed production capture receipts binding exact run, result, metric, environment, time window,
  artifact, and active supply-chain evidence.
- `production_captured` labels without a valid receipt are downgraded to
  `production_captured_unverified` and cannot satisfy production thresholds.
- Model Validation report v3, Supply Chain UI, and operational metrics/alerts for verified,
  revoked, and unsigned evidence.
- Release review and Gate staleness metrics now distinguish unresolved action from immutable
  historical records.
- Additive Alembic revision `202607200004`.
- One development-key RS256 statement for the actual `qwen2.5:0.5b` digest and a CycloneDX 1.6
  SBOM was verified through the API. No production receipt was fabricated.

## Sprint 5H-A Completed

- Purpose-scoped public JWK registry for model publisher, production collector, and transparency
  log keys.
- `development`, `internal_ca`, and `external` trust tiers with validity windows and public-key-only
  validation.
- Idempotent registration and append-only rotation, retirement, and separated revocation actions.
- Signed transparency checkpoints and RFC 6962-style Merkle inclusion verification.
- Dynamic invalidation of supply-chain and receipt production eligibility after key lifecycle
  changes.
- Model Validation report v4, Trust Registry UI, Supply Chain assurance fields, and Prometheus
  trust metrics.
- Additive Alembic revision `202607200005`.
- Three development roots and one development transparency proof were verified through the live
  API. They remain explicitly outside production eligibility.

## Sprint 5H-B Completed

- Immutable remote JWKS source configurations with purpose, issuer, trust tier, algorithm policy,
  freshness window, and verified registrar provenance.
- Host allowlisting, HTTPS-by-default transport, redirect denial, bounded timeout/body size, and
  strict JSON/JWKS content policy.
- Append-only Preview/Apply attempt receipts, including transport and validation failures.
- Public-key-only validation and atomic Apply with no partial import on collisions or malformed
  key sets.
- Source and Apply lineage on imported roots plus snapshot-aware remote rotation.
- Healthy, degraded, stale, failed, unsynced, and disabled source states with freshness-aware
  fail-closed production eligibility.
- Trust Registry overview v2, source registration/sync APIs, source console, sync history, root
  lineage, metrics, and alerts.
- Additive Alembic revision `202607210001`.
- Live Compose Preview and Apply imported one development source-backed root. The source is healthy
  and current, but remains outside production eligibility by policy.

## Sprint 5H-C Completed

- PostgreSQL-backed opaque browser sessions shared across backend instances.
- Hash-only session and CSRF storage plus AES-GCM provider ID-token storage.
- Invalid/expired/revoked browser cookies fail closed without local-identity downgrade.
- Exact Origin and cookie/header/server-hash CSRF enforcement for unsafe browser requests.
- POST-only local revocation and RP-initiated OIDC provider logout.
- Rejection of forwarding headers from untrusted direct clients before identity selection.
- Shared discovery/JWKS rows with original-expiry preservation and unknown-key refresh.
- Browser sign-out pending state and automatic unsafe-method CSRF header attachment.
- Active/revoked session and fresh/stale OIDC cache metrics.
- Additive Alembic revision `202607220001`.
- Live Keycloak PKCE login, role mapping, session creation, revocation, provider logout, and
  frontend return verified.

## Sprint 5H-D Completed

- One-to-one automatic synchronization policy separated from immutable trust-source configuration.
- PostgreSQL `FOR UPDATE SKIP LOCKED` due scans and schedule lease fingerprints.
- Durable `trust_source_sync` jobs with heartbeat execution leases and run-sequence dedupe.
- Policy-controlled exponential retry, deterministic jitter, lease recovery, and dead letters.
- Append-only manual/scheduled, schedule/job, attempt, and due-time receipt lineage.
- Schedule list, upsert, and authenticated Run-now APIs.
- Trust Registry overview v3, policy editor, next-run state, and linked job evidence.
- Enabled, due, retrying, and failed schedule metrics plus derived alerts.
- Additive Alembic revision `202607230001`.
- Two live worker replicas produced one job and one receipt for one due run sequence.

## Sprint 5H-E Completed

- Verified-role browser session audit for Admin, SRE Lead, and ML Ops Lead.
- Mutation restricted to verified Admin and SRE Lead identities.
- Single, subject, and provider-session-hash revocation with current-session preservation.
- Immediate purge of encrypted provider ID tokens and raw provider `sid` values on revocation.
- Keyed client and provider-session correlation fingerprints without raw client descriptors.
- Append-only, per-session hash-linked issuance, migration, revocation, purge, and deletion events.
- Configurable inactive-session retention with bounded `FOR UPDATE SKIP LOCKED` cleanup.
- Replica-deduplicated periodic cleanup through the existing durable Agent worker.
- Overview/list/event/revoke/cleanup APIs and a responsive Browser Sessions console.
- Expired, retention-due, inactive-provider-token, and lifecycle-event metrics plus alerts.
- Additive Alembic revision `202607270001`.
- Two live worker replicas produced one cleanup job for one interval bucket and purged provider
  material from three inactive historical sessions.

## Sprint 5H-F Completed

- PostgreSQL interval snapshots and normalized metric points with configurable bounded retention.
- Explicit identity-session hygiene and worker-control-plane availability SLOs.
- Missing expected intervals counted as not-good after the first retained baseline.
- Durable SLO/derived-alert incidents with open, continuing, resolved, and recurring lifecycles.
- HMAC-SHA256 paging with HTTPS-by-default, destination allowlisting, idempotent event IDs,
  response bounds, durable receipts, and lifetime attempt counts.
- Existing Agent job leases, heartbeat, exponential retry, dead letter, and verified-role requeue
  reused for capture and delivery.
- Admin/SRE manual capture and test-page APIs plus audit-only permission state.
- Operations console with SLO, history, incident, delivery, and current-alert views.
- Prometheus 30-day retention configuration and stale snapshot, SLO, delivery, and identity rules.
- Additive Alembic revision `202607270002`.
- Two workers produced one snapshot and one cycle job per interval bucket; a controlled paging
  outage dead-lettered and then completed through verified Admin requeue after receiver recovery.

## Sprint 5H-G Completed

- Independent long and short SLO windows with paired error-budget burn rates.
- Warning and critical burn levels require both windows to cross policy thresholds.
- Verified Admin/SRE acknowledgement, assignment, and note actions.
- Append-only incident action history with canonical predecessor hashes.
- Automatic level 1-3 escalation for open, critical, unacknowledged incidents.
- HMAC keyring, explicit active key, and delivery-pinned signing key identity.
- Legacy delivery compatibility through the `legacy` key ID.
- Private-CA-verified HTTPS paging and a one-shot Docker TLS fixture.
- Operations UI burn comparison, response controls/history, owner state, escalation, and key ID.
- Additive Alembic revision `202608030001`.
- Live test page accepted with HTTP 202 under key `2026-08-primary`; acknowledgement and assignment
  were persisted as a valid two-event action chain.

## Sprint 5H-H Completed

- Bounded runtime file projection for paging HMAC keyrings and active key IDs.
- Atomic secret initialization and rolling rotation with retained queued-delivery keys.
- Sender and receiver dynamic reload without process restart.
- Retryable handling when a projected signing key or CA is temporarily unavailable.
- Strict `model-atlas-paging-provider-receipt-v1` validation and delivery UUID correlation.
- Persisted provider name, event ID, receipt ID, and acceptance timestamp.
- Seven-check staging readiness gate in the operational overview and Operations console.
- Executable staging verifier, no-restart key rotation, and controlled failure/recovery drill.
- Runtime-only Docker secret volume and one-shot initializer service.
- Observability startup now includes the development trust-source fixture.
- Additive Alembic revision `202608040001`.
- Live qualification passed 7 of 7 checks; key `2026-08-04-rotated` was selected without sender
  restart, and an outage/dead-letter/SRE-requeue cycle recovered the same durable job.

## Sprint 6A Phase 4 Completed

- Deterministic aggregate read model over the locked source corpus, approved case pack, current
  runtime matrix, and exact latest stored actual-runtime runs.
- Reference Workload APIs for overview, cases, configurations, comparison, and paginated critical
  failures.
- Canonical evidence-trust interpretation for `local_actual_runtime` while preserving raw source
  provenance.
- Guided `/reference-workload` UI with four separate status states, two comparison charts, full
  configuration matrix, failure-first review links, completion checks, and reproduction hashes.
- Overview entry point with actual-runtime count, reviewed-output count, best observed
  configuration, and explicit non-production status.
- Core Evaluation, Discovery, and collapsible Advanced Lab navigation.
- Desktop and 390px mobile QA with contained table scrolling and no document-level horizontal
  overflow.

## Sprint 6A Phase 5 Completed

- Existing Gate Preflight and Deployment Gate evaluation reused for all three stored reference
  configurations.
- Idempotent Gate orchestration: the first live run created 3 Gate evaluations and the second
  reused all 3 current Gate IDs.
- Read-only JSON and Markdown report APIs over the selected stored evidence.
- Pure Markdown rendering from the structured `reference-workload-report-v1` object.
- Atomic configuration CSV, critical-failure JSON, report, and reproduction-manifest generation.
- SHA-256 binding for the canonical report and every non-circular artifact.
- Reference Workload download controls and comparison links to Gate or preselected Preflight.
- Explicit separation of Gate `BLOCKED`, evidence trust `needs_judge_review`, release readiness
  `BLOCKED`, and production readiness `not_production_ready`.

## Sprint 6A Phase 6 Completed

- SQLAlchemy entities split into eight bounded domain modules with compatibility facades.
- Agent execution and operational reliability split into bounded packages without route or
  behavior changes.
- Frontend API types split into nine domain modules while preserving 142 public exports.
- ORM metadata retained the exact 47-table signature and Alembic clean-schema upgrade behavior.
- Agent semantic trace hash and existing top-level import contracts remained unchanged.

## Sprint 6A Phase 7 Completed

- Locked source manifest and corpus revalidated: 14 files, 200 chunks, 64 approved cases, and 20
  approved critical cases.
- Actual Docker Ollama smoke flow rerun with observed model digests and persisted local evidence.
- Smoke runs now use a separate configuration identity and cannot displace complete portfolio
  runs in the aggregate read model.
- Persisted 384-result portfolio replay retained its exact three run IDs and stable comparison
  SHA-256.
- Reference Gate orchestration re-evaluated changed evidence once and then reused all three current
  Gate IDs idempotently.
- Final report artifacts regenerated and independently hash-verified.
- Overview count wording now distinguishes failed critical outcomes from unique failed cases and
  states that the count spans the latest Gate for every configuration.
- Full backend, frontend, Docker, Alembic, desktop, and mobile verification passed.

## Evidence Remediation 1 Completed

- Exact 110-row reference failure queue grouped into 20 deterministic case-and-reason clusters.
- P0/P1/P2 priority derived from recurrence and cross-configuration reproduction.
- Balanced 30-output review plan covers all 20 critical cases, eight categories, and all three
  configurations with ten selected outputs each.
- Candidate assessments remain read-only with `applied=false` and `human_reviewed=false`.
- Heuristic-only Judge rows now explicitly require review instead of appearing calibrated.
- Result-scoped Judge Review filtering and deep links return exactly one requested output.
- Responsive prioritized review UI and hash-bound JSON artifact added without a database migration.

## Verification

```text
Backend pytest: 215 passed, 1 upstream deprecation warning
Backend and tools Ruff: passed
Frontend typecheck, lint, and production build: passed
Docker backend/frontend image build and Compose configuration: passed
PostgreSQL migration 202608040001 (head): passed
Two Agent workers, backend, HTTPS paging sink, and trust-source fixture healthy
TLS and paging secret initializer exit 0
Operational staging readiness: 7 passed, 0 failed
No-restart projected-key rotation to 2026-08-04-rotated: passed
Provider event/receipt correlation and persistence: passed
Controlled outage, dead letter, SRE requeue, same-job recovery, and incident reconciliation: passed
Final operational health healthy; open incidents 0; dead letters 0
Rotated-key HTTPS test page: HTTP 202; receiver key ID 2026-08-primary
Historical delivery compatibility: migrated key ID legacy
Incident acknowledgement/assignment predecessor-hash chain: passed
Desktop and 390px mobile Operations QA: no document-level horizontal overflow
Browser clipped interactive controls: 0; console errors: 0
Live Keycloak PKCE login and ML Ops Lead role mapping: passed
CSRF-protected POST logout, DB revocation, IdP logout, and frontend return: passed
Session/CSRF hash-only storage and encrypted provider ID-token inspection: passed
Two-worker trust-source due-run dedupe and scheduled receipt lineage: passed
Authenticated CSRF-protected trust-source Run now: passed
Two-worker OIDC cleanup bucket dedupe and first-attempt completion: passed
Inactive provider token purge, lifecycle event preservation, and zero remaining backlog: passed
Session administration RBAC: ML Ops audit passed, ML Ops cleanup 403, Admin cleanup passed
Operational snapshot dedupe: 12 snapshots, 12 buckets, 12 jobs, 12 dedupe keys
Prometheus target up; 10 alert rules loaded
Signed paging HTTP 202, payload-hash match, outage/dead-letter/Admin-requeue recovery: passed
Operations RBAC: ML Ops audit passed; capture and test-page controls disabled
Desktop Operations browser QA: passed; page-level horizontal overflow 0
Final browser console: 0 warnings or errors
```

One upstream deprecation warning remains in Starlette's TestClient import path. It does not affect test results or application behavior.

### Sprint 6A Phase 3 verification

```text
Docker backend pytest: 212 passed, 1 warning
Docker backend Ruff: passed
Local backend pytest: 211 passed, 1 skipped, 2 warnings
Frontend lint and production build: passed
Docker Compose configuration: passed
Alembic current: 202608040001 (head)
Reference source review: 64/64 approved, 20/20 critical approved
Runtime matrix: 3 completed configurations, 384 results, 2 artifacts
Runtime comparison replay: hash stable
Portfolio runtime-evidence status: ready
Production readiness: not_production_ready
```

### Sprint 6A Phase 4 verification

```text
Docker backend pytest: 215 passed, 1 warning
Docker backend Ruff: passed
Frontend typecheck, lint, and production build: passed
Docker backend/frontend image build and Compose configuration: passed
Alembic current: 202608040001 (head)
Aggregate API: 3 completed configurations, 384 actual-runtime Results
Critical failure queue: 110 rows from selected latest runs
Portfolio completion: 6 of 8 checks passed
Gate outcomes: 0 of 3; aggregate NOT_EVALUATED
Evidence trust: needs_judge_review
Production readiness: not_production_ready
Desktop and 390px mobile Reference Workload QA: no document-level horizontal overflow
Advanced navigation, failure detail link, and Overview entry point: passed
Browser console: 0 warnings or errors
```

### Sprint 6A Phase 5 verification

```text
Docker backend pytest: 217 passed, 1 warning
Docker backend Ruff: passed
Frontend typecheck, lint, and production build: passed
Docker backend/frontend image build: passed
Gate orchestration first run: 3 created, 0 Preflight-blocked
Gate orchestration second run: 0 created, 3 reused
Gate outcomes: 3 of 3 BLOCKED; release readiness BLOCKED
Report: 384 Results, 110 critical failures, 24 category metric rows
Portfolio completion: 7 of 8 checks passed
Report SHA-256: 66beef4b997260abbf381ba4265bb6458d52093eaa0ac4f1dc5ed4aeff76fb37
Artifact hashes: independently matched
Desktop and 390px mobile Reference Workload QA: no document-level horizontal overflow
Gate Preflight deep-link selection: passed
Browser console: 0 warnings or errors
Production readiness: not_production_ready
```

### Sprint 6A Phase 6 verification

```text
SQLAlchemy entities: 8 domain modules plus compatibility facade
ORM metadata: 47 tables; exact pre/post signature match
Metadata SHA-256: fba1f807c636ea5c4178db7b391a2300dbd6743118d5c989e23592d23a115c6a
Empty-schema Alembic upgrade: passed through 202608040001 (head)
Agent execution: package split; canonical semantic trace SHA-256 unchanged
Agent targeted tests: 22 passed
Operational reliability targeted tests: 23 passed
Frontend API types: 142 exports preserved through @/types/api
Docker backend pytest: 219 passed
Docker backend Ruff: passed
Frontend ESLint and TypeScript/Next.js production build: passed
Backend, worker, and frontend Docker image build: passed
Live backend health, operational overview, and Operations frontend: HTTP 200
Gate outcomes: 3 of 3 BLOCKED
Production readiness: not_production_ready
```

### Sprint 6A Phase 7 verification

```text
Reference validation: 14 files, 200 chunks, 64/64 approved, 20/20 critical approved
Post-isolation smoke: 10 Results, 10 Metrics, success 0.1, error 0.9, timeout 0, OOM 0
Smoke isolation: dedicated configuration; aggregate portfolio selection unchanged
Portfolio replay: 3 configurations, 384 Results, exact selected run IDs
Runtime comparison SHA-256: 0c92a7b4793c2dd69d02a03a88e68ab19a233512dc50e1bc57ac7c6dcf716cd9
Reference failure review queue: 110 rows
Reference Gate outcomes: 3 of 3 BLOCKED; 8 failed blocker rules per configuration
Portfolio completion: 7 of 8 checks passed; human review 0/30
Final report SHA-256: 95de5d4c812d397a3f93bb9c7db4adce534635b34699cb5eb2ef068b4c1c2bba
Artifact hashes: independently matched
Docker backend pytest: 220 passed, 2 warnings
Docker backend Ruff: passed
Frontend ESLint and TypeScript/Next.js production build: passed
Backend, worker, and frontend Docker image build: passed
Alembic current: 202608040001 (head)
Desktop 1280x720 and mobile 390x844 browser QA: no document-level horizontal overflow
Browser console: 0 warnings or errors
Production readiness: not_production_ready
```

### Evidence Remediation 1 verification

```text
Output review plan: 110 failures, 20 clusters, 30 selected outputs
Cluster priorities P0 / P1 / P2: 17 / 3 / 0
Selected priorities P0 / P1 / P2: 27 / 3 / 0
Selected case / category / configuration coverage: 20 / 8 / 3
Configuration distribution: small 10, medium 10, prompt variant 10
Plan hash: 587c35dbf6d4dba85b221551103e683ef903f82e8bdca37e4ab65cd81008a65e
JSON artifact SHA-256: 65146e64040169b439da165471c9635aa25c1e6d2eeb601514ee21a290a705d5
Focused Judge Review: one row, heuristic, needs_review=1
Human reviewed: 0/30; no automatic label application
Docker backend pytest: 222 passed, 2 warnings
Docker backend Ruff: passed
Frontend ESLint and TypeScript/Next.js production build: passed
Backend, worker, and frontend Docker image build: passed
Desktop and 390px mobile browser QA: no document-level horizontal overflow
Browser console: 0 warnings or errors
Production readiness: not_production_ready
```

### Evidence Remediation 2 verification

```text
P0 Agent diagnostic scope: 4 critical cases x 3 configurations x 1 trial
Final actual diagnostic Results: 12
1.5B plan validity / sequence / final response: 1.0 / 1.0 / 1.0
0.5B plan validity / sequence / final response: 0.75 / 0.75 / 0.75
Agent task success: 0.0 for all configurations
Retrieval contract audit: 4 blocked, 4 critical blocked, 0 reachable
Expected chunk ranks at top_k 5: 8, 40, 14, 15
Canonical portfolio / failure queue / human review: 384 / 110 / 0 of 30
Reference Gates: 3 of 3 BLOCKED
Focused tests: 30 passed, 2 warnings
Backend full suite: 229 passed, 1 skipped, 2 warnings
Backend Ruff and frontend ESLint: passed
Docker focused tests: 30 passed, 1 warning
Docker Ruff and backend/worker image build: passed
Live backend/Ollama health and authoritative overview: passed
Alembic current: 202608040001 (head)
Production readiness: not_production_ready
```

### Evidence Remediation 3 candidate verification

```text
Candidate workload revision: 1.0.1, isolated from canonical 1.0.0
Changed critical cases: 4
Expected chunk ranks before revision: 8, 40, 14, 15
Expected chunk ranks after revision: 3, 1, 1, 1
Retrieval contract audit: pass, 4 of 4 reachable within top_k 5
Retained approvals / pending review: 60 / 4
Approved critical cases: 16 of 20
Portfolio ready / bootstrap allowed: false / false
Canonical workload / historical Results mutated: false / false
Focused tests: 25 passed, 2 warnings
Backend full suite: 231 passed, 1 skipped, 2 warnings
Backend Ruff: passed
Docker focused tests: 25 passed, 1 warning
Docker Ruff and backend/worker image build: passed
Live canonical overview: 384 Results, 110 critical failures, 0 of 30 reviewed
Live Gate outcomes: 3 of 3 BLOCKED, 8 failed blocker rules each
Alembic current: 202608040001 (head)
Human revision attestation: pending
Production readiness: not_production_ready
```

### Evidence Remediation 3 finalization and diagnostic

```text
Human revision reviewer: 김대건
Revision approvals: 64 of 64 cases, 20 of 20 critical cases
Draft / rejected cases: 0 / 0
Revision portfolio ready: true
Final retrieval audit: 4 reachable, 0 blocked, recall 1.0
Actual diagnostic scope: 4 critical cases x 3 configurations x 1 trial
Actual diagnostic Results / Metrics: 12 / 12
Agent task / plan / step / sequence / final response: 1.0 for all configurations
Retrieval public-contract source / recall 1.0: 12 of 12 / 12 of 12
Native complete source plans / compiler-completed plans: 9 of 12 / 3 of 12
Policy violation / timeout / OOM / generic error: 0 / 0 / 0 / 0
Canonical workload / historical Results mutated: false / false
Canonical portfolio / critical failures / human output review: 384 / 110 / 0 of 30
Reference Gates: 3 of 3 BLOCKED, 8 failed blocker rules each
Production readiness: not_production_ready
```

### Evidence Remediation 4 refusal/scope finalization and diagnostic

```text
Finalized revision: 1.0.2 sourced from finalized 1.0.1
Human revision reviewer: 김대건
Revision change: 1 expected evidence identity, query unchanged
Approved cases / critical cases: 64 of 64 / 20 of 20
Draft / rejected cases: 0 / 0
Revision portfolio ready: true
Final retrieval audit: 7 reachable, 0 blocked, recall 1.0
Expected ranks: 1, 2, 1, 2, 2, 1, 1 within top_k 5
Actual diagnostic scope / Results: 7 cases x 3 configurations / 21
RAG success: 0 of 7 for every configuration
JSON valid: 0 of 7 / 1 of 7 / 2 of 7
Retrieval recall: 1.0 for every case and configuration
Diagnostic timeout / OOM: 0 / 0
Canonical workload / historical Results mutated: false / false
Canonical portfolio / critical failures / model-output review: 384 / 110 / 0 of 30
Reference Gates: 3 of 3 BLOCKED, 8 failed blocker rules each
Backend full suite: 231 passed, 1 skipped, 2 warnings
Docker focused tests: 25 passed, 2 warnings
Backend and Docker Ruff, backend/worker image build: passed
Production readiness: not_production_ready
```

### Evidence Remediation 5 RAG contract and refusal scoring

```text
Adapter / scorer: openai-compatible-v13 / rag-evaluation-scorer-v2
Stored trace / summary: rag-evaluation-trace-v2 / rag-evaluation-summary-v2
Final diagnostic scope / Results: 7 cases x 3 configurations / 21
Final JSON valid: 7 of 7 / 7 of 7 / 6 of 7
384-token ceiling hits: 0 / 0 / 1
Retrieval recall: 1.0 for every case and configuration
RAG success: 0 of 7 for every configuration
Semantic contract success: 0 of 7 / 3 of 7 / 1 of 7
Refusal requirement success: 0 of 4 / 2 of 4 / 1 of 4
Mean citation precision / recall: 0.476 / 0.476 across configurations
Mean groundedness / unsupported rate: 0.405 / 0.786 across configurations
Strongest diagnostic configuration: qwen2.5:1.5b with prompt v1
Backend full suite: 236 passed, 1 skipped, 2 warnings
Docker focused tests / Ruff: 22 passed, 2 warnings / passed
Frontend lint / production build: passed / passed
API health / Alembic: ok / 202608040001 (head)
Canonical workload / historical Results mutated: false / false
Canonical portfolio / critical failures / model-output review: 384 / 110 / 0 of 30
Reference Gates: 3 of 3 BLOCKED, 8 failed blocker rules each
Production readiness: not_production_ready
```

### Evidence Remediation 6 deterministic evidence and refusal

```text
Adapter / selector / scorer: openai-compatible-v16 / lexical-sentence-selector-v1 / rag-evaluation-scorer-v3
Stored retrieval / trace / summary: rag-retrieval-trace-v2 / rag-evaluation-trace-v3 / rag-evaluation-summary-v3
Final diagnostic scope / Results: 7 cases x 3 configurations / 21
JSON valid / 384-token hits: 21 of 21 / 0
Retrieval recall / exact selection recall: 1.0 / 0.571429
Groundedness / unsupported rate: 1.0 / 0.0
RAG success: 3 of 7 / 4 of 7 / 4 of 7
Semantic contract success: 4 of 7 / 5 of 7 / 5 of 7
Refusal semantic success: 4 of 4 / 4 of 4 / 4 of 4
Diagnostic timeout / OOM: 0 / 0
Expected-ID conflicts: KO-RAG-SCOPE-002, KO-RAG-SCOPE-003, KO-REFUSE-002
Canonical workload / historical Portfolio Results mutated: false / false
Canonical portfolio / critical failures / model-output review: 384 / 110 / 0 of 30
Reference Gates: 3 of 3 BLOCKED, 8 failed blocker rules each
Production readiness: not_production_ready
```

### Evidence Remediation 7 finalization and acceptable evidence

```text
Finalized revision: 1.0.3 sourced from finalized 1.0.2
Human revision reviewer: 김대건
Revision approvals: 64 of 64 cases, 20 of 20 critical cases
Retrieval contract audit: pass, 3 of 3 alternatives reachable
Actual diagnostic scope / Results: 7 cases x 3 configurations / 21
RAG success: 4 of 7 / 5 of 7 / 5 of 7
Retrieval / selection / citation contract success: 21 of 21 each
Alternative evidence matches: 9
Refusal semantic success: 12 of 12
Groundedness / unsupported rate: 1.0 / 0.0
Diagnostic timeout / OOM: 0 / 0
Production readiness: not_production_ready
```

### Evidence Remediation 8 finalization and actual semantic diagnostic

```text
Adapter / scorer: openai-compatible-v17 / rag-evaluation-scorer-v5
Stored retrieval / trace / summary: rag-retrieval-trace-v3 / rag-evaluation-trace-v5 / rag-evaluation-summary-v5
Finalized revision: 1.0.4, 64 of 64 approved, 20 of 20 critical approved
Human reviewer: 김대건; 2 of 2 revision decisions approved
Actual finalized-1.0.4 diagnostic Results: 21
RAG success: 7 of 7 / 7 of 7 / 7 of 7
Semantic contract / alternative matches: 21 of 21 / 6
Bounded answer contract: 21 of 21
Retrieval / selection / citation contract success: 21 of 21 each
Refusal semantic success: 12 of 12
Groundedness / unsupported rate: 1.0 / 0.0
Forbidden violations / timeout / OOM: 0 / 0 / 0
Case-pack portfolio eligibility / bootstrap allowed: true / true
Authoritative Portfolio/Gate evidence changed: false
Backend full suite: 259 passed, 1 skipped, 2 warnings
Docker focused tests / Ruff: 24 passed, 2 warnings / passed
Frontend lint, typecheck, and production build: passed
Alembic current: 202608040001 (head)
Production readiness: not_production_ready
```

The exact metadata contract and clean-database upgrade passed. `alembic check` still reports
pre-existing migration-versus-ORM index and unique-constraint naming differences; Phase 6 did not
generate a rename/drop migration or change metadata.

## Compatibility Decisions

- No evidence-trust DB enum was changed.
- Additive migrations extend metric aggregation with `p99`, add persistent Agent checkpoints, and
  add Agent jobs, revision lineage, Gate staleness, supply-chain attestations, revocation actions,
  and production receipts.
- Existing free-text source columns remain readable.
- New source writes default to canonical values.
- Gate and release snapshot changes are additive.
- Existing route paths are preserved.
- Legacy snapshots render as unknown or legacy rather than failing.
- Canonical JSON hash ordering is unchanged.

## Current Limitation

Evidence is still primarily synthetic or locally authored. The Sprint 5F Ollama campaign now uses
a matching, digest-attested 0.5B configuration and two human-reviewed labels, so its local
validation status is `validated`. Sprint 5G adds a development-key signed supply-chain statement
for that digest, and Sprint 5H-A adds a valid development transparency proof and managed
development roots. Sprint 5H-B adds one healthy source-backed development root without changing
that production boundary. No internal-CA/external trust chain or signed production capture exists. It is
still not production validation, a 7B target-artifact run, a Deployment Gate approval, or a release
authorization.

Other boundaries:

- no infrastructure deployment;
- the reference HTTP/outbox collector is implemented but not deployed as a production fleet
  service;
- browser OIDC now has shared revocable sessions, CSRF enforcement, RP-initiated provider logout,
  verified-role session administration, token minimization, and retention cleanup, but production
  TLS, provider back-channel logout, secret-rotation migration drills, and external identity
  lifecycle are not;
- durable operational snapshots, paired-window burn rates, response actions, escalation,
  projected rotating-key TLS paging, strict receipts, staging readiness, and failure drills are
  implemented, but the bundled receiver, generated CA, and secret volume are development fixtures
  rather than an external HA on-call service, managed PKI, or secret manager;
- Agent live replanning has an OpenAI-compatible transport, but transport integration alone does
  not establish model quality or production safety;
- Agent resume is append-only and automatically stales affected Gates; historical signed decisions
  remain immutable audit records rather than being automatically revoked;
- checkpoint and Gate reconciliation run through a heartbeat-aware durable worker, which is not a
  distributed workflow engine;
- multi-agent coordination, durable memory, and production tool access are not included;
- executable tools are bounded local fixtures rather than production-connected integrations;
- RAG uses deterministic local fixtures and a lexical sentence selector rather than production
  ingestion, embeddings, a learned reranker, a vector database, or online serving;
- the four first-remediation Agent/RAG contracts are finalized in `1.0.1`, and the seven refusal
  and version/scope retrieval contracts are finalized in `1.0.2`; the compact RAG schema and
  refusal-aware scorer improve observability but their bounded diagnostics do not replace the
  canonical `1.0.0` Portfolio or Gate evidence;
- Runtime Reliability uses an in-process worker pool and deterministic failure fixtures rather than
  distributed load generation, production traffic replay, or live GPU telemetry;
- no Kubernetes, Kafka, Spark, externally signed publisher registry, or live model registry
  ingestion;
- managed public keys, remote JWKS synchronization, signed development transparency evidence,
  CycloneDX binding, and append-only lifecycle are implemented, but there is no independent
  transparency service, timestamp authority, OCI registry verification, mTLS source, or online
  revocation distribution;
- trust-source scheduling uses PostgreSQL leases and the durable worker, but it is not a general
  distributed workflow engine, cron calendar service, or multi-region consensus system;
- Tool/RAG preflight is integrated, but the primary worker does not yet create a fresh OS sandbox
  for every run;
- three of five Sprint 5F sample scores remain heuristic and broader calibration is required.

## Runtime Resources

Safe generated resources to remove when needed:

- `.next/`;
- `tmp/`;
- `.pytest_cache/`;
- `.ruff_cache/`;
- `__pycache__/`;
- `*.tsbuildinfo`;
- local SQLite `*.db`;
- generated `*.egg-info/`.

Keep `.venv/`, `frontend/node_modules/`, Docker images, and local database volumes when fast local verification or existing exploratory data matters. `make down` stops containers without deleting volumes.

## Recommended Next Sprint

Sprint 6A Phase 0 through Phase 7 is complete. The report-bound assisted review approved all 64
source cases, including all 20 critical cases, and the idempotent bootstrap created the locked
workload, suite, and local acceptance policy. The three-configuration v7 actual-runtime matrix
stored 384 results across two observed Ollama model artifacts and reproduced its comparison from
the exact persisted run IDs.

The runtime-matrix portfolio evidence status is `ready`, but the model-quality result is poor:
Agent task success is `0.0` for every configuration, RAG success is zero, and critical-case failure
is between `0.90` and `0.95`. The strongest tested configuration is `qwen2.5:1.5b` with prompt v1,
but it is a diagnostic winner rather than a release candidate. There is no production-captured
evidence, quality Gate approval, release authorization, or production-readiness claim.

The guided `/reference-workload` UI now exposes the exact selected evidence, 110 critical failures,
and all three stored Gate outcomes. Every Gate is `BLOCKED`, which truthfully reflects eight failed
blocker rules per configuration. The report package binds those decisions to the selected 384
Results, linked evidence IDs, reproduction commands, and artifact hashes. The only failing
portfolio check is 30 reviewed model outputs.

Phase 6 converted the large entity, frontend API-type, Agent, and operational-reliability surfaces
into bounded packages while preserving imports, metadata, trace semantics, endpoint contracts, and
build behavior. Phase 7 then reran the real smoke path, isolated smoke configuration identity,
replayed the persisted matrix, regenerated evidence artifacts, and passed the complete verification
surface without upgrading readiness claims.

The first evidence-quality remediation unit prioritizes the 110-item queue and produces unapplied
candidate assessments plus a balanced 30-output review plan. The second unit fixes the narrow
Agent prompt and execution contract, adds an auditable bounded policy compiler, and proves the
change through 36 actual diagnostic Results across three iterations. It does not convert those
diagnostics into portfolio evidence.

The third unit created isolated case-pack revision `1.0.1` and made all four contracts reachable at
ranks `3`, `1`, `1`, and `1`. Reviewer `김대건` approved all four changes, producing 64 total and
20 critical approvals with no drafts or rejections. The following 12-result actual-runtime
diagnostic achieved Agent task success and retrieval recall `1.0` for every case and configuration,
with zero policy violations. Evaluation-only expected chunk IDs were not used as model input.

The first four-case unreachable-contract blocker is closed. The refusal and version/scope
preflight then exposed one additional stale expected evidence identity at rank 15. Finalized
`1.0.2` changes only `KO-RAG-SCOPE-001`, moves the direct evidence to rank 1, and chains from the
hash-verified finalized `1.0.1` pack. Reviewer `김대건` approved the change, and the final audit
made all seven contracts reachable.

The deterministic selector, source-claim enum, and bounded refusal contract are now implemented and
the same cluster has been rerun. JSON validity reached `21/21`, groundedness reached `1.0`,
unsupported claims fell to `0.0`, refusal semantics reached `12/12`, and strict RAG success improved
from `0/21` to `11/21`. Three cases select a more direct retrieved source than the finalized single
expected ID. Isolated `1.0.3` now represents those alternatives as reviewed any-of groups. Reviewer
`김대건` approved all three changes, the hash-bound revision was finalized, and the actual 21-result
rerun improved strict RAG success to `14/21` while selection and citation contracts reached `21/21`.
The bounded-answer contract then removed the 0.5B forbidden-claim output and produced `15/21`
strict success with `21/21` answer-contract compliance. Reviewer `김대건` approved the two isolated
`1.0.4` semantic alternatives, and finalization produced 64/64 approved cases with 20/20 critical
approvals. The subsequent actual diagnostic reached `21/21`; Scope 002 and Scope 003 used reviewed
semantic group index 1 in every configuration. This closes the narrow refusal/scope contract
remediation. Tool argument and recovery quality is the next evidence-remediation target.
Release remains disallowed while canonical Gates are blocked, 30 model-output reviews are
outstanding, and no verified production-captured evidence exists.
