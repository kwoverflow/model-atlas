# Model Atlas 평가·사용·기술 안내

기준일: **2026-09-13**. 처음 보는 평가자를 위한 현재 안내다.

## 1. 프로젝트의 목적

Model Atlas는 새로 학습한 언어 모델이 아니라 **로컬 AI 배포를 평가하는 EvalOps MVP**다.
모델·프롬프트·런타임·하드웨어·평가 데이터·정책을 연결하고, 왜 배포를 허용하거나 막았는지
근거를 다시 확인할 수 있게 만든다.

출발 문제는 "내 PC에서 돌아간다"와 "내 업무에 배포해도 된다" 사이의 간극이다.
평균 점수가 좋아도 중요한 요청에서 잘못된 도구 인자나 근거 없는 답을 내면 배포가 어렵다.
실험 설정과 결과가 흩어지면 변경 후 어떤 판단이 더 이상 유효하지 않은지도 알기 어렵다.

| 관점 | 토큰·하드웨어 적합성 중심 추천 | 이 프로젝트에서 추가한 것 |
| --- | --- | --- |
| 질문 | 실행 가능한 후보는 무엇인가 | 이 구성은 이 업무의 정책을 만족하는가 |
| 단위 | 모델 또는 모델 파일 | 파일 + 런타임 + 하드웨어 + 프롬프트 + suite + 정책 |
| 기준 | 메모리·문맥 길이·상대 점수 | 절대 임계값, critical case, 근거 부족, 회귀 |
| 결과 | 후보 목록 | Gate, 실패 이유, snapshot, 릴리스 검토 |
| 신뢰 | 점수만 보면 출처를 놓치기 쉬움 | 합성·로컬·운영 출처와 자동 채점·사람 검토 분리 |

이 비교는 기능 범위의 차이다. 모든 기존 제품보다 성능이 좋다는 비교 실험을 한 것은 아니다.

## 2. 페르소나

- **도입 개발자**: 한국어 사내 문서 QA나 제한된 도구 실행을 붙이기 전에 실패를 찾는다.
- **검토 책임자**: 어떤 설정·근거·정책으로 판단했는지 확인하고 변경 요청을 남긴다.
- **평가자**: mock으로 파이프라인을 재현하고 실제 모델의 한계도 숨기지 않는지 확인한다.

## 3. 현재 상태의 해석

**소프트웨어 동작 검증과 모델 성능 검증은 다르다.**

| 대상 | 상태 | 의미 |
| --- | --- | --- |
| 새 평가용 설치 | Docker + mock 시연 | GPU나 가중치 없이 기능 검토 |
| 보존된 공식 실제 평가 | BLOCKED / actual runtime 384건 | 운영 배포 통과가 아님 |
| critical failure | 110건 | 실패 관측 수이며 고유 사례 110개가 아님 |
| 목표 출력 사람 검토 | 0/30 | source case 승인과 다른 절차 |
| 승인된 1.0.5 source case | 64/64, critical 20/20 | 모델 출력이 맞았다는 뜻이 아님 |
| production readiness | not_production_ready | 운영 배포 승인을 주장하지 않음 |
| 외부 초심자 검토 | external_review_pending | 이번 자동 QA로 대체하지 않음 |

새 설치에는 원래 DB가 없다. 새 UI에서 실제 결과가 0건인 것은 정상이다.
공식 상태는 `artifacts/mvp-closeout/2026-09-13/before.json`, `after.json`에 보존했다.
[RAG 논문 적용 실험](docs/reports/2026-09-12_rag_research_decision_ko.md)은 두 후보가 사전 기준을
만족하지 못해 채택하지 않았다. 추가 튜닝은 이번 범위에서 중단했다.

## 4. 준비물과 설치

필수: Docker Desktop의 Linux 컨테이너 모드와 Compose, 최초 다운로드용 인터넷,
압축 해제 및 Docker 빌드 공간. 최소 RAM·디스크 사양은 측정하지 않았다.
자동 smoke 검증에는 호스트 Python 3.12+가 필요하다. 수동 UI 시연에는 Python·Node·GPU가 필요 없다.

압축 해제한 프로젝트 루트에서 실행한다. `.env`와 API 키는 필요 없다.

```powershell
docker compose -f deploy/mvp-review.compose.yml config --quiet
docker compose -f deploy/mvp-review.compose.yml up -d --build
docker compose -f deploy/mvp-review.compose.yml ps
docker compose -f deploy/mvp-review.compose.yml exec -T backend python -m app.seed.demo
docker compose -f deploy/mvp-review.compose.yml exec -T backend python -m app.seed.rag_evaluation
```

seed는 **새 평가 DB에 한 번만** 실행한다. demo 데이터와 연결 기록을 재구성하므로
개인 평가를 시작한 뒤에는 반복하지 않는다. 기본 Compose의 기존 DB에는 실행하지 않는다.

- UI: http://localhost:13000
- API 문서: http://localhost:18010/docs
- 상태 확인: http://localhost:18010/api/v1/health
- 별도 프로젝트: `model-atlas-mvp-review`, volume: `model-atlas-mvp-review_review-db`

포트 충돌 시 실행 전 PowerShell에서 `$env:MVP_REVIEW_UI_PORT="13001"`,
`$env:MVP_REVIEW_API_PORT="18011"`을 지정하고 다시 빌드한다. URL과 smoke의 `--api-url`도 바꾼다.
같은 이름의 검토 프로젝트가 이미 있다면 새 설치로 오인하지 말고 기존 데이터인지 먼저 확인한다.

중지/재개는 다음과 같다. `down`에 `-v`를 붙이지 않으면 DB volume은 유지된다.

```powershell
docker compose -f deploy/mvp-review.compose.yml stop
docker compose -f deploy/mvp-review.compose.yml start
```

이 설정은 localhost 개발 시연용이다. 고정 DB 암호와 테스트용 trusted-header 인증이 있으므로
공인 서버에 노출하거나 운영 인증 설정으로 재사용하면 안 된다.

## 5. 10분 시연

1. **Overview**에서 `Demo / local evidence mode`와 `Not Production Ready`를 확인한다.
   이름에 Qwen이 있어도 mock 실행은 실제 Qwen 추론이 아니라는 점을 설명한다.
2. **Deployment Configurations**의 `Qwen2.5 7B Local Document Assistant`를 확인한다.
   모델 파일만이 아닌 런타임·하드웨어·프롬프트가 평가 구성이라는 점을 설명한다.
3. Overview의 **Execute Evaluation**에서 configuration은 위 이름, suite는
   `Korean Operations Assistant Acceptance Suite v1`, task는 `Korean document QA`로 선택한다.
   Adapter=`mock`, Data source=`synthetic_demo`, Max cases=`3`으로 바꾼다.
   **Check Runtime → Run Cases**를 누르면 completed, Results 3, Metrics 3, Logs 5가 표시된다.
4. **Deployment Gates**에서 같은 configuration/suite와 `Strict Local Release Policy v1`을 선택한다.
   **Review Evidence**로 출처와 부족한 조건을 확인하고 **Evaluate Gate**로 저장한다.
   이 합성 시연의 `INSUFFICIENT_EVIDENCE`는 정상이다. 통과시키려고 정답이나 정책을 바꾸지 않는다.
5. **Release Readiness → Release Decisions**에서 판단과 snapshot을 확인한다.
   아래 자동 검증을 실행하면 `Automated MVP QA (synthetic)`의 `REQUEST_CHANGES` 기록이 생긴다.
   상세 페이지의 frozen snapshot, hash, diff, Markdown/JSON export를 확인한다.

시연 완료 기준은 "모델이 통과했다"가 아니라 **실행 결과부터 배포 제한의 근거까지 추적 가능하다**이다.

## 6. 자동 검증

```powershell
python tools/verify_mvp_review.py --confirm-isolated-review --output artifacts/local-review/api-smoke.json
```

이 명령은 새 평가 DB에 합성 결과 3건과 Gate, 자동 QA 변경 요청을 추가한다.
기존 기본 포트 18000/8000, 외부 주소, 명시적 확인 없는 실행을 거부한다.
재실행은 다른 output 파일명을 지정한다. 읽기 전용이 아니라 DB에 기록을 추가하는 테스트다.
`identity_verified`는 로컬 테스트 proxy 경로의 값이며 실제 사람 인증·검토 완료가 아니다.

```powershell
docker compose -f deploy/mvp-review.compose.yml run --rm --no-deps backend python -m pytest -q
docker compose -f deploy/mvp-review.compose.yml run --rm --no-deps backend python -m ruff check app tests
python -m unittest discover -s tools/tests -p test_mvp_review.py -v
```

프론트 소스 검증은 `frontend`에서 Node 22와 `npm ci` 후 `npm test`, `npm run typecheck`,
`npm run lint`, `npm run build`를 실행한다. Docker 빌드도 프론트 테스트·production build를 수행한다.
실제 통과 수와 경고는 [공개 검토·리팩토링 보고서](docs/reports/2026-09-13_public_review_refactor_ko.md)를 따른다.
직전 UI 시연 결과는 [MVP closeout 보고서](docs/reports/2026-09-13_mvp_closeout_ko.md)에 보존했다.

ZIP에는 전체 payload의 `MANIFEST.sha256`와 검증 기록을 연결한 `PACKAGE_INFO.json`이 포함된다.
검증 및 새 디렉터리로 압축 해제하는 명령은 다음과 같다. 대상 디렉터리는 존재하면 안 된다.

```powershell
python tools/verify_mvp_package.py path/to/package.zip --extract-to path/to/new-review-directory
```

해시는 파일 무결성을 확인할 뿐 배포자의 신원까지 인증하지는 않는다.
모델 가중치·DB·Docker image/volume·개인 키·실제 `.env`·의존성·캐시·기존 ZIP은 제외한다.

## 7. 구조와 코드

```text
사용자 / Next.js
  -> FastAPI 요청 검증
  -> 실행 서비스 -> adapter(mock / local runtime)
  -> raw output + 지표 + 로그 -> PostgreSQL
  -> Gate preflight -> 근거 수집 -> 정책 판정 + snapshot/hash
  -> release readiness -> 역할 검증 + 릴리스 판단/변경 요청
  -> frozen snapshot / diff / lineage / 문서 export
```

| 책임 | 코드 위치 | 확장 원칙 |
| --- | --- | --- |
| API 계약 | `backend/app/api/v1/routes`, `backend/app/schemas` | 입력 검증, 도메인 로직은 서비스로 |
| 실행 조정 | `backend/app/services/benchmark_execution.py` | 오류·지표·원문 출처 함께 보존 |
| 런타임 연결 | `backend/app/services/inference_adapters` | Adapter protocol와 factory 활용 |
| RAG 파이프라인 | `backend/app/services/rag_pipeline` | 계약·검색·채점·실행·집계 분리, 기존 facade 유지 |
| Gate | `backend/app/services/deployment_gate` | evidence/metrics/policy/reporting 책임 분리 |
| 릴리스 | `backend/app/services/release_readiness.py`, `release_decisions.py` | 판정·권한·snapshot 분리 |
| 구조화 요청 | `backend/app/services/structured_requests.py`, `request_workflows.py` | 인자 생략·충돌 명시 처리 |
| 저장 | `backend/app/models`, `backend/alembic` | 변경 시 migration과 테스트 |
| UI | `frontend/app`, `frontend/components`, `frontend/lib` | API 타입과 화면별 책임 유지 |
| 실험 | `experiments/retrieval_research` | 선택적 의존성, 공식 runtime과 분리 |

주요 기법은 adapter/factory, 서비스 계층, 정책 평가, 버전·해시 기반 증거 연결,
불변 snapshot과 변경 감지, 근거 부족 시 보수적 차단이다. 모델 재학습 프로젝트는 아니다.
상세 구조와 운영 확장 이력은 [architecture](docs/architecture.md), [data contract](docs/data_contract.md)에 있다.
현재 시연은 핵심 평가/검토만 포함하며 모든 운영 확장을 새 환경에서 검증했다는 뜻은 아니다.
확장 위치, 회귀 검증, 공개 패키징 규칙은 [CONTRIBUTING.md](CONTRIBUTING.md)를 따른다.

## 8. 한계와 외부 검토

- 실제 모델의 실패와 출력 검토 부족은 남아 있다. mock 성공으로 해소할 수 없다.
- 같은 데이터로 반복한 연구는 독립 holdout이 아니며 외부 일반화 성능을 보장하지 않는다.
- API 장애 시 일부 서버 렌더링 화면이 빈 상태로 대체될 수 있다. 데이터가 갑자기 0이면 health와
  `docker compose -f deploy/mvp-review.compose.yml logs --tail 50 backend frontend`를 확인한다.
- backend 의존성 범위와 Docker base tag는 완전히 고정되지 않았다. 새 설치가 동일 byte가 되는
  offline 재현을 보장하지 않는다. 최초 설치는 네트워크가 필요하다.
- UI는 영어 중심이며 일부 과거 Sprint 표시가 남는다. 접근성 전수 감사, 외부 사용성 시험,
  운영 보안 감사는 이번 자동 검증에 포함되지 않는다.

다음은 기능 추가가 아니라 **프로젝트를 모르는 1명이 위 절차를 수행하는 외부 검토**다.
설치 성공, 3건 실행, Gate가 막힌 이유를 스스로 설명할 수 있는지, mock과 실제 성능을
혼동했는지, 막힌 화면을 기록한다. 결과를 받기 전에는 외부 평가 통과로 표기하지 않는다.

기존 `EVALUATOR_GUIDE_KO.md`, `docs/golden_demo.md`는 승인 corpus의 원문으로 보존했다.
과거 수치·실행 명령과 현재 안내가 다르면 이 문서와 현재 검증 보고서를 먼저 읽는다.
