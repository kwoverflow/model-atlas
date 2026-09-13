# 공개 검토 패키지와 유지보수 리팩토링

기준일: 2026-09-13. 이번 작업은 기능·모델 성능 확대가 아니라 **평가 가능한 제출본과 변경하기 쉬운 코드 구조**를 만드는 작업이다.
처음 보는 평가자는 [MVP_REVIEW_GUIDE_KO.md](../../MVP_REVIEW_GUIDE_KO.md)를 먼저 읽는다.

## 1. 무엇을 정리했는가

기존 `backend/app/services/rag_evaluation.py`는 약 1,280줄에 데이터 계약, 기본 corpus,
검색, 실행 준비, 채점, 집계가 모여 있었다. 기존 정의 41개를 다음 7개 모듈로 이동했다.

| 모듈 | 책임 |
| --- | --- |
| `contracts.py` | 버전 상수와 불변 dataclass |
| `corpus.py` | 결정적 데모 corpus와 registry |
| `retrieval.py` | lexical 검색, 순위와 retrieval trace |
| `text.py` | 토큰화·정규화·거절 표현 감지 |
| `scoring.py` | 출력 검증, 인용·근거·의미 계약 채점 |
| `execution.py` | adapter 입력 준비, 평가 결과 연결 |
| `summaries.py` | trace 집계와 summary 생성 |

모두 `backend/app/services/rag_pipeline` 아래에 있다. 기존 `rag_evaluation.py`는 명시적
재수출 facade로 남겨 호출부의 import를 유지했다. 내부 모듈은 facade를 역참조하지 않는다.
새 프레임워크나 플러그인 시스템은 넣지 않았다. 기존 Adapter/Factory, 서비스 계층,
불변 데이터 계약 패턴을 유지했다. 확장 위치와 규칙은 [CONTRIBUTING.md](../../CONTRIBUTING.md)에 정리했다.

## 2. 무엇을 바꾸지 않았는가

- 점수 임계값, 토큰화 규칙, 검색 동점 정렬, JSON 직렬화, trace 버전을 바꾸지 않았다.
- 이동 전후 41개 정의의 AST가 일치하는지 확인했다. import와 파일 배치만 분리했다.
- 대표 검색 5종과 각각의 정상·잘못된 JSON·없는 인용 결과를 지문으로 고정해 비교했다.
- 기존 공개 import 9종의 객체 동일성과 내부 의존성의 비순환성을 테스트했다.
- 승인된 1.0.5 corpus 원문 14개, 200개 chunk와 case/manifest/review manifest 해시를 보존했다.
- 원래 실제 평가 DB와 원래 backend 이미지는 변경하지 않았다. 별도의 검토용 backend만 재빌드했다.

Python dataclass의 `__module__`은 새 모듈을 가리킨다. JSON API 계약은 유지하지만 과거 pickle의
복원 호환성까지 보장한다는 주장은 하지 않는다. 이번 리팩토링은 새 모델 추론 성능 실험이 아니다.

## 3. 실행한 검증

| 검증 | 결과 |
| --- | --- |
| Windows backend 전체 테스트 | 915 passed, 1 skipped, 경고 1 |
| Linux Docker backend 전체 테스트 | 916 passed, 경고 2 |
| backend 및 검토 도구 Ruff | 통과 |
| frontend 테스트 | 29 passed |
| frontend typecheck / production build | 통과 |
| frontend ESLint | 오류 0, 기존 경고 4 |
| npm audit | 현재 발견된 취약점 0 |
| 패키지·안전 대상·공개 검사 도구 테스트 | 15 passed |
| workflow evidence export 테스트 | 9 passed |
| 격리 검토 API smoke | HTTP·불변 조건 33개 통과 |

Windows의 생략 테스트는 Linux에서 실행했다. backend 경고는 Starlette/httpx와 AnyIO의
deprecated API 관련이며, frontend 경고는 기존 내부 페이지 이동 방식 4곳이다.
Node 테스트에는 experimental type stripping/module-type 경고도 있었다. 이를 오류 없이 통과한 것과
경고가 전혀 없는 것을 혼동하지 않는다.

원문 결과는 `artifacts/public-review/2026-09-13/verification.json`, JUnit XML과
`api-smoke.json`에 있다. 화면 검증과 이미지는 직전 `artifacts/mvp-closeout/2026-09-13` 기록이다.
이번에는 UI 소스를 수정하지 않았으며 새 접근성 전수 검사나 독립 사용자 검토를 주장하지 않는다.

## 4. 유지된 실제 평가 상태

**BLOCKED / not_production_ready**다. 실제 결과 384건, critical failure 관측 110건,
목표 출력 사람 검토 0/30은 변하지 않았다. source case 승인 64/64와는 별개다.
새 smoke는 검토용 DB에 `synthetic_demo` 3건과 `REQUEST_CHANGES`를 추가했을 뿐,
사람 검토나 운영 배포 승인을 만들지 않았다.

`before.json`과 `after.json`의 보호된 공식 기록은 동일하다. 이 snapshot은 원래 실행 이미지의
소스도 읽으므로, 그 소스 해시가 같다는 사실을 로컬 리팩토링 코드가 같다는 뜻으로 해석하면 안 된다.
로컬 기존 backend 파일 중 변경한 것은 `rag_evaluation.py`이며 새 pipeline 모듈을 추가했다.
로컬 코드의 동작 보존은 AST·회귀 테스트·재빌드한 검토 API로 별도 확인했다.

## 5. 공개 저장소와 ZIP의 범위

[GitHub 저장소](https://github.com/kwoverflow/model-atlas)에는 소스·문서·선별한 최신 검증 근거를 둔다.
[검토 Release](https://github.com/kwoverflow/model-atlas/releases)에는 과거의 비밀정보 없는 근거까지
포함한 별도 ZIP, SHA-256, 압축 검증 결과를 둔다. 과거 보고서는 당시 체크포인트 기록이며 현재 승인 상태를 덮어쓰지 않는다.

제외 항목은 실제 `.env`, 비밀키, DB, 모델 가중치, 의존성, 캐시, 로그, 다른 프로젝트와 과거 ZIP이다.
개별 파일과 전체 ZIP의 해시를 검증한다. 공개 검사는 작업 폴더가 아니라 **실제로 staged된 Git blob**도
검사하므로, staging 후 파일만 지워 놓는 실수를 탐지한다. 이 검사는 일부 고신뢰 패턴 검사이며
정식 보안·개인정보 감사의 대체물이 아니다. 공개 저장소의 라이선스는 아직 선택하지 않았다.

GitHub Actions는 backend·frontend·도구 테스트와 공개 payload 검사를 반복한다.
원격 CI 결과는 Actions 실행 기록에서, 최종 ZIP 추출·해시는 ZIP 옆 sidecar에서 확인한다.
검토 제출은 완료할 수 있지만 **외부 평가 통과는 평가자의 결과를 받은 뒤에만** 표기해야 한다.

## 6. 다음 변경 원칙

새 기능부터 늘리기보다 외부 평가자 1명이 설치·3건 mock 실행·차단 근거 설명을 완료하는지 확인한다.
그 피드백에 따라 문서·오류 상태·작은 UX 문제부터 고친다. 성능 개선을 다시 시작할 때는 새 holdout,
사전 채택 기준, 별도 실험 경로를 사용하고 공식 계약을 조용히 변경하지 않는다.
