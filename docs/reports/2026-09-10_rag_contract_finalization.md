# RAG Contract Review Finalization

2026-09-10 / Evidence Remediation 25

## Outcome

The user's downloaded attestation approved all four source changes in revision 1.0.5.
The existing finalization CLI validated the report identity, artifact hashes, complete case coverage
and individual revised-case hashes before applying those decisions. The original downloaded bytes
are retained as `reference_workload/revisions/1.0.5/review_attestation.json`.

| Item | Confirmed state |
| --- | --- |
| New decisions | 4 approved, 0 rejected |
| Approved source cases | 64/64, including 20/20 critical cases |
| Prior review records | 60 retained byte-for-byte; only four new records appended |
| Pending source reviews | 0 |
| Ordinary critical RAG retrieval | 1/5 reachable; 4 blocked at top-5 |
| Official Gate | BLOCKED |
| Official critical failures | 110 failed observations, not 110 unique cases |
| Official runtime evidence | 384 results |
| Actual-output human review target | 0/30; source approval does not count toward it |
| Production readiness | not_production_ready |

The four approved changes are KO-RAG-001, KO-RAG-MULTI-001, KO-RAG-MULTI-002 and
KO-RAG-MULTI-003. KO-RAG-002 and the other 59 unchanged cases retain their prior approvals.
The submitted review time is `2026-09-10T03:54:14.604Z`. Each submitted note is `yes`;
no detailed rationale or independent review was inferred or added on the user's behalf.
This is a user-supplied attestation with hash binding, not a cryptographically authenticated identity.

## Evidence Boundary

Only the isolated revision's review state was finalized. Its manifest and case payloads are identical
to the reviewed draft. Questions, retrieval queries, top-k, expected facts, forbidden claims,
refusal requirements, criticality and weights were not changed. The canonical pack, finalized 1.0.4,
stored official results, output review plan and running backend were not replaced or promoted.

The existing finalization schema reports `case_pack.portfolio_ready=true` and
`evidence_boundary.bootstrap_allowed=true`. These fields mean that source-review coverage and
category requirements are satisfied. They are not end-to-end model, retrieval, output-review or
production approval. `authoritative_portfolio_evidence` remains false.

Remediation 24's revision report, source alignment audit, HTML reports and draft metrics remain
historical snapshots. Read the separate `finalization_report.json` for the completed review state;
do not regenerate or rewrite the draft report to make it appear approved at creation time.

## Verification

- Original attestation copied without byte changes; revision/report/case hashes validated.
- Finalization report content hash and finalized review-manifest file hash verified independently.
- The first 60 review records still hash to the draft report's original review-manifest identity.
- Existing tests verify all unchanged cases and the preserved semantic contracts of the four changes.
- Focused host tests: 32 passed. One upstream deprecation warning and a pytest cache permission
  warning occurred; neither affected test execution. Docker full backend tests: 796 passed with
  two upstream deprecation warnings, using `-p no:cacheprovider`.
- Fresh retrieval audit on finalized 1.0.5: KO-RAG-002 reachable; the four revised cases blocked.
  The audit deliberately returns a nonzero status for blocked contracts. This is not a test failure
  or a newly observed model output. No model inference was performed in this finalization step.
- Before/after read-only snapshots confirm identical official comparison, protected records, review
  plan and eight pinned canonical/runtime-matrix/1.0.4 files. The snapshot source inventory covers
  the running backend and those pinned paths, not every new host artifact.
- The protection CLI also re-evaluates the same previously saved 60 canary outputs. Its 22/60 versus
  34/60 evaluator comparison is historical output reuse, not 60 fresh calls or a new quality gain.

Verification artifacts are under `artifacts/rag-contract-finalization/2026-09-10/`:
`before.json`, `after.json`, `official-protection.json`, `retrieval-contract-audit.json`.

### Identities

| Artifact | File SHA-256 |
| --- | --- |
| Original attestation | `7778a11b0c6405b5344377c10e3e459e8d4a7c0ca4d88142d4e58869cbbaedba` |
| Finalization report | `f5749df82dbddd96220b5c6caf2ff648d8136d4c14aa29a58e05573faf9fea6f` |
| Finalized review manifest | `662ddcced71aac5647dab9f1e42c86ef5559e287f5d4daf4c686b3511fb0737d` |
| Post-finalization retrieval audit | `2b03322833d0ba5a323a8503ed795bfe092b5c77bfb4e29008a478c975a1c5dc` |
| Official protection report | `e8a532fe6592205bd445ab3507cf3261730468da8880878defe78352457cc699` |

Revision report internal hash:
`d16e4b55f9650cac961ac50ed694985bf0fa14dbb13e336b1022560aa4300473`.

Finalization report internal hash:
`e4bdbabf2d255efaf2b16b2d4ec3f8fa06cf346ffddf9a71dd07322d7959f0d4`.

Official protected-records hash:
`22bea914a370b2420d320dd1381b0ffd694e410ddbaf8c934e128d1cab635fbc`.

File hashes above cover exact stored bytes. Internal report hashes follow the respective schema's
canonical serialization rules and are different identifiers; do not substitute one for the other.

## Reproduction

The following command was executed once from `backend/` after validating and preserving the
download. Do not rerun it on this finalized directory: the original draft-review hash is intentionally
different after four approval records have been appended.

```powershell
../.venv/Scripts/python.exe -X utf8 -m app.reference_workload.cli --repository-root .. finalize-case-revision --output-directory ../reference_workload/revisions/1.0.5 --attestation ../reference_workload/revisions/1.0.5/review_attestation.json
```

Safe test reruns from the repository root:

```powershell
.venv/Scripts/python.exe -X utf8 -m pytest -c backend/pyproject.toml backend/tests/test_reference_workload_case_revision.py backend/tests/test_reference_workload_cases.py backend/tests/test_reference_workload_contract_audit.py backend/tests/test_reference_workload_semantic_candidate.py backend/tests/test_rag_contract_alignment.py -q -p no:cacheprovider
docker compose run --rm --no-deps backend python -m pytest -q -p no:cacheprovider
```

## Next Work

1. Evaluate isolated Korean/English retrieval changes using approved 1.0.5 contracts. Search ranking
   must use only the question and corpus, never expected source IDs, required facts or approval data.
2. Check the complete RAG-bearing pack for regressions, including scope and refusal cases. Keep the
   default retriever unchanged until the candidate's evidence supports adopting it.
3. Run fresh, versioned answer/citation evaluation only after retrieval findings are recorded. Keep
   historical 1.0.4 results separate; label changes make naive before/after score claims misleading.

No further source-review action is required for these four changes. Actual-output review and any
later Gate adoption remain separate steps.
