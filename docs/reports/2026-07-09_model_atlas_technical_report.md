# Model Atlas 기술 보고서

작성일: 2026-07-09

## 1. 목적

Model Atlas는 로컬 AI 모델을 단순 추천하는 도구가 아니라, 특정 배포 구성에 대해
증거 기반으로 배포 가능 여부를 판단하고 감사 가능한 release sign-off를 남기는
local-first EvalOps 시스템이다.

이 프로젝트가 해결하려는 문제는 다음과 같다.

- 모델 후보 비교만으로는 실제 운영 배포 승인 근거가 부족하다.
- synthetic demo 데이터와 production-captured evidence를 구분하지 않으면 승인 판단이 위험하다.
- prompt, benchmark, gate, baseline, release sign-off가 흩어지면 나중에 재현과 감사가 어렵다.
- 로컬 런타임(Ollama, LM Studio 등)을 쓰는 환경에서도 구조화된 MLOps 흐름이 필요하다.

## 2. 현재 핵심 기능

- Candidate Discovery: 모델 artifact 후보를 deterministic score로 랭킹한다.
- Deployment Gate: deployment configuration, evaluation suite, acceptance policy를 기준으로
  `APPROVED`, `CONDITIONAL`, `BLOCKED`, `INSUFFICIENT_EVIDENCE` verdict를 만든다.
- Benchmark Execution: mock 또는 OpenAI-compatible local runtime으로 evaluation case를 실행한다.
- Scorer Registry: JSON, tool-call, grounded answer, text fallback scorer를 registry로 분리했다.
- Judge Label Review: heuristic, candidate label, applied judge label 상태를 검토한다.
- Prompt Regression: prompt version별 성능과 active baseline delta를 비교한다.
- Deployment Baseline: 승인된 gate를 active baseline으로 promote하고 supersession을 추적한다.
- Experiment Lineage: prompt, run, gate, baseline, release sign-off를 append-only timeline으로 연결한다.
- Release Readiness: gate, baseline, judge review, prompt risk, lineage를 하나의 snapshot으로 묶는다.
- Signed Release Decision: frozen readiness snapshot, signer identity, approval policy, signature hash, decision hash를 저장하고 snapshot JSON/diff를 제공한다.

## 3. 기술 명세

### Backend

- FastAPI
- Pydantic v2
- SQLAlchemy 2.x
- Alembic
- PostgreSQL for runtime
- SQLite for fast isolated tests
- pytest
- Ruff

### Frontend

- Next.js
- React
- TypeScript
- Tailwind CSS
- lucide-react icons

### Runtime

- Docker Compose
- PostgreSQL 16
- Optional Ollama runtime profile
- OpenAI-compatible local endpoint adapter

## 4. 데이터 구조

주요 decision 흐름은 다음 엔티티로 구성된다.

- `DeploymentConfiguration`: 배포 가능한 구체 구성과 configuration hash.
- `EvaluationSuite`: workload별 versioned evaluation case 묶음.
- `AcceptancePolicy`: absolute threshold 기반 정책.
- `GateEvaluation`: evidence snapshot, scorecard, verdict, decision hash.
- `DeploymentBaseline`: active baseline과 supersession history.
- `ReleaseDecision`: frozen readiness snapshot, signer identity, approval policy, signature hash, decision hash.
- `ExperimentLineageEvent`: append-only operational timeline.

`ReleaseDecision`은 다음 값을 저장한다.

- gate/suite/policy/deployment scope
- decision: `APPROVE_RELEASE`, `REQUEST_CHANGES`, `REJECT_RELEASE`
- release readiness status
- signer identity JSON
- identity verification state
- approval policy JSON
- signature statement
- signature hash
- snapshot JSON
- snapshot hash
- snapshot diff export
- decision hash

## 5. Release Decision Identity 설계

이번 확장에서 signer identity를 별도 서비스로 분리했다.

- `app/services/operator_identity.py`
  - self-attested local UI signer를 정규화한다.
  - trusted header 기반 identity를 검증된 signer로 기록한다.
- `app/middleware/operator_identity.py`
  - reverse proxy/auth middleware가 주입한 trusted header를 request state로 정규화한다.
- `app/services/release_approval_policy.py`
  - `release-approval-rbac-v1` 정책으로 verified signer와 release role을 검증한다.

지원하는 trusted headers:

- `x-model-atlas-operator-id`
- `x-model-atlas-operator-name`
- `x-model-atlas-operator-role`
- `x-model-atlas-identity-provider`

현재 UI 입력은 `auth_source = self_attested`, `identity_verified = false`로 저장된다.
향후 reverse proxy, SSO, 사내 인증 middleware가 위 헤더를 주입하면
`auth_source = trusted_header`, `identity_verified = true`로 저장된다.

이 구조를 택한 이유:

- 지금 당장 무거운 인증 서버를 붙이지 않아도 release sign-off audit contract를 만들 수 있다.
- 향후 인증 방식이 바뀌어도 release decision API와 DB 모델을 크게 바꾸지 않아도 된다.
- signer identity, signature hash, decision hash가 분리되어 감사 범위가 명확하다.
- approval policy result가 별도로 저장되어 나중에 왜 허용되었는지 추적할 수 있다.

## 6. 코드 구조

### Backend 책임 분리

- `app/services/deployment_gate/evidence.py`: evidence collection, canonical JSON, stable hash.
- `app/services/deployment_gate/evaluator.py`: gate evaluation orchestration.
- `app/services/deployment_gate/baselines.py`: baseline promotion and supersession.
- `app/services/release_readiness.py`: readiness snapshot 생성과 Markdown export.
- `app/services/operator_identity.py`: signer identity normalization.
- `app/middleware/operator_identity.py`: trusted operator identity middleware.
- `app/services/release_approval_policy.py`: release decision RBAC policy.
- `app/services/release_decisions.py`: release decision 생성, policy/readiness validation, snapshot diff, snapshot/signature/decision hash.
- `app/services/experiment_lineage.py`: append-only lineage event materialization.

### Frontend 책임 분리

- `app/release-readiness/page.tsx`: release snapshot과 sign form.
- `components/ReleaseDecisionForm.tsx`: client-side sign-off workflow.
- `app/release-decisions/page.tsx`: signed decision list.
- `app/release-decisions/[id]/page.tsx`: frozen snapshot detail, snapshot JSON export, current snapshot diff.
- `app/experiment-lineage/page.tsx`: release sign-off까지 포함한 timeline.
- `lib/releaseDecisionPresentation.ts`: release decision label, tone, operator policy, date/id formatting helper.

## 7. 주요 기능 흐름

1. Benchmark evidence가 저장된다.
2. Deployment Gate가 evidence를 수집하고 policy rule을 평가한다.
3. Gate verdict와 decision hash가 저장된다.
4. Approved gate는 active baseline으로 promote할 수 있다.
5. Release readiness snapshot이 gate, baseline, judge review, prompt regression, lineage를 묶는다.
6. Operator가 release decision을 서명한다.
7. Operator identity middleware가 trusted header identity를 request state에 저장한다.
8. API는 signer identity를 정규화하고 approval policy를 평가한다.
9. snapshot hash, signature hash, decision hash를 만든다.
10. release decision record와 `release_decision_signed` lineage event를 같은 transaction에 저장한다.
11. UI에서 decision history, detail, snapshot diff, lineage timeline을 확인한다.

## 8. 안전 규칙

- Synthetic-only evidence는 `APPROVED`를 만들 수 없다.
- `APPROVE_RELEASE`는 readiness status가 `READY` 또는 `READY_TO_PROMOTE`일 때만 허용된다.
- `APPROVE_RELEASE`, `REJECT_RELEASE`는 verified identity와 승인된 release role을 요구한다.
- `REQUEST_CHANGES`는 어떤 readiness 상태에서도 감사 기록으로 남길 수 있다.
- Release decision은 gate verdict, benchmark evidence, baseline을 변경하지 않는다.
- Release decision은 frozen snapshot을 저장하므로 나중에 같은 화면 상태를 재현할 수 있다.
- Snapshot diff는 volatile `generated_at`을 제외하고 현재 readiness snapshot과 비교한다.

## 9. 검증 결과

로컬 검증:

- Backend tests: 57 passed
- Backend Ruff: passed
- Frontend typecheck: passed
- Frontend lint: passed
- Frontend build: passed

Docker 검증:

- `docker compose up -d --build`: passed
- Alembic migrations applied through backend startup.
- Backend API health: 200 OK
- Release decision detail page: 200 OK
- Experiment lineage release sign-off filter: 200 OK
- Markdown export: 200 OK
- Snapshot JSON export and snapshot diff: passed
  - snapshot JSON export: 200 OK
  - snapshot diff: 200 OK, path-level drift returned
- Trusted-header release decision verification: passed
  - `identity_verified = true`
  - signer identity provider: `docker-local-proxy`
  - signature hash stored
- RBAC policy verification: passed
  - verified `Release Manager` can sign allowed decisions
  - reviewer-only `ML Engineer` is rejected for `REJECT_RELEASE`
- Docker backend pytest: 57 passed, 1 warning
- Docker frontend lint: passed

## 10. 확장 포인트

가장 자연스러운 다음 단계는 다음 순서다.

1. Lineage event detail drawer 또는 상세 페이지 추가.
2. Production-captured evidence import와 judge-label calibration을 실제 운영 데이터로 반복 검증.

## 11. 결론

현재 Model Atlas는 후보 추천 도구에서 한 단계 더 나아가, 로컬 AI 배포 승인에 필요한
evidence, policy, baseline, readiness, sign-off, lineage를 연결하는 구조를 갖췄다.

특히 release decision identity, approval policy, signature hash를 분리한 덕분에, 지금은 local UI와
trusted header middleware 기반으로 작동하면서도 나중에 사내 인증, SSO, 더 엄격한 release approval로
확장할 수 있는 여지를 남겼다.
