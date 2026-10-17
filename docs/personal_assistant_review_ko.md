# 개인 비서 초안 검토: 사용 및 유지보수

## 범위

기존 일정 추가, 할 일 추가·완료, 파일 이동·보관 작업을 개선한 로컬 실험 기능이다.
새 도구나 모델 학습 기능을 추가하지 않는다. 현재는 별도 샌드박스의 SQLite 일정·할 일과
합성 파일만 변경한다. 실제 캘린더 계정, 개인 문서 폴더, 외부 서비스에는 연결하지 않는다.
기본 설정에서는 API가 비활성화되어 있으며 `PERSONAL_ASSISTANT_WORKSPACE`를 지정해야 한다.

## 1.0 현재 실행 경로

현재 앱의 기본 초안 경로는 `assistant-release-v1`이다. [1.0 마감 안내](releases/1.0.0/README.md)와
[최종 보안·검증 보고서](reports/2026-10-16_release_1_0_security_ko.md)를 먼저 읽는다.
프로젝트의 목적과 두 흐름은 [프로젝트 안내서](PROJECT_GUIDE_KO.md)에 정리했다. V8은 동결된
실험으로 보존하고 앱 경로에서는 미검증 설명을 판정만 기술하는 문구로 제한한다. 요청·문서 의미·
설명 정책 상태를 따로 표시하며, 원본 의미가 미검증인 것을 확인됐다고 승격하지 않는다.
프로젝트의 1.0 버전 번호는 운영 배포나 자율 실행 승인이 아니다.

## 화면 사용

1. `/personal-assistant`에서 요청을 입력하고 **초안 생성**을 누른다.
2. 작업, 제목, 시각·시간대, 경로를 확인한다. 모델 원문과 수정 내역을 펼쳐 비교한다.
3. 필요한 값을 수정하고 **수정 저장**을 누른다. 저장하지 않은 수정은 **수정 취소**로 되돌린다.
4. 확인 체크박스를 선택하고 **확정 및 미리보기**를 누른다. 이 단계는 실행하지 않는다.
5. 변환된 시각과 실제 작업 대상을 확인한 후 **승인하고 실행** 또는 **취소**를 선택한다.
6. 완료된 파일 작업은 **복구 미리보기** 후 별도로 승인해야 원래 위치로 복구된다.
7. 중단된 파일 작업은 **상태 확인 및 복구**로 대조한다. 파일이 변경되었거나 상태가
   모호하면 자동 처리를 중단한다. 임의 삭제, 덮어쓰기, 무조건 재시도는 하지 않는다.

확정 이후 다시 수정하면 이전 승인은 무효다. 다른 창의 오래된 버전도 실행할 수 없다.
승인은 5분 후 만료되며, 작업공간이 변경되었을 때도 새 미리보기가 필요하다.
입력 시각은 `2026-12-15T08:30:00`처럼 UTC offset 없는 현지 시각이다.
파일 경로는 `Inbox/review-demo.txt`처럼 작업 폴더 안의 상대 경로다.

모델 응답이 검증에 실패해도 원문은 남는다. 사용자가 폼을 직접 작성하여 새로 확정할 수
있지만, 이 결과를 모델이 올바르게 이해했다고 평가하지 않는다. 파일 보관은 영구 삭제가 아니다.

[기존 10개 흐름의 자동 검증](../experiments/personal_assistant_persona_e2e/README.md)을 기본으로
사용한다. 원본 정확도, 수정 없는 완료, 제한된 수정 후 완료를 분리하며 사람이 반드시 10건을
직접 검토할 필요는 없다. [수동 점검 표](personal_assistant_manual_pilot_ko.md)는 선택적 UX
확인용으로 남긴다. 합성 페르소나가 실제 사용자 만족도나 독립 사람 검토를 증명하지는 않는다.
## 실험 이력

이하의 기본값 `legacy`와 채택 보류는 **각 실험 당시의 기록**이다. 현재 기본 경로는 위의
1.0 실행 경로를 따른다. 실험의 코드·점수·실패를 소급 수정하지 않는다.

[런타임 A/B 결과](reports/2026-10-11_personal_assistant_runtime_ab_ko.md)의 후보 경로는
채택 조건을 충족하지 못했으므로 기본 모델 호출은 변경하지 않았다.

후속 `compact-grounded-v1` 후보는 입력을 축소하고 공개 요청의 명확한 제목을 디코딩 제약에
사용한다. [동일 조건 144회 비교](reports/2026-10-11_personal_assistant_accuracy_stabilization_ko.md)에서
초안 정확도는 개선됐지만 상위 경로의 모델 거절 판단이 실패해 **기본값은 여전히 `legacy`**다.
후보를 명시적으로 선택하려면 새 합성 작업공간을 초기화한 뒤 서버 시작 전에 설정한다.

금지 경로 후속 검사에서는 긴 정책 프롬프트 후보 V2와 공개 경로 정책·디코딩 후보 V3를
별도로 검증했다. V3는 금지 경로 판단을 개선했지만 경로 문자열을 제목으로 가진 정상 할 일을
거절하는 오탐이 남아 채택을 차단했다. **기본값은 `legacy`로 유지한다.** 후보들은 합성 실험용
명시적 옵션이며, [후속 결과와 제한](reports/2026-10-11_personal_assistant_path_boundary_ko.md)에
실패와 적용 범위를 기록한다. 다른 표현이나 실제 개인 데이터에 대한 안전 보장은 없다.

2026-10-15의 `compact-role-grounded-v4`는 명확한 단일 할 일 생성 명령의 제목 역할을
바인딩해 기존 제목 오탐을 보완했다. 다만 [352회 전체 재실행](reports/2026-10-15_personal_assistant_role_grounding_ko.md)에서
시간대·생략 우선순위 추측과 기존 할 일 완료 오탐이 남았다. 후보는 실험용 명시적 옵션이며
**기본값은 계속 `legacy`**다. 제목 생성 보완이 모든 작업 종류의 의미 정확도를 보장하지 않는다.

후속 `compact-field-grounded-v5`는 시간대·우선순위 출처와 생략 여부, ID 기반 완료 역할을
추가했다. [432회 전체 비교와 재생 검증](reports/2026-10-15_personal_assistant_field_provenance_ko.md)에서
정상 intent는 100/116에서 106/116으로 개선됐지만 마감 누락의 새 회귀와 문맥 분류 오탐이
발견됐다. **V5도 채택하지 않았으며 기본값은 `legacy`다.** 후보는 선택적 실험 경로이고,
출처 검증은 요청 필드의 완전성이나 실제 사용자 검토를 보장하지 않는다.

`compact-complete-grounded-v6`는 [생성 필드 완전성 검증](reports/2026-10-16_personal_assistant_completeness_ko.md)의
실험 후보로 추가했다. 요청에서 확인한 마감·시작·길이도 필수 필드로 연결하고 여러 인용 값의
제목 역할과 문맥 분류를 분리한다. 기존 108개는 두 시드 모두 통과했지만 신규 사례의 불필요한
확인·거절이 남아 **V6도 기본 채택하지 않았다**. 비교 기준의 초기 타임아웃 한 건도 보존했다.
지원하지 않는 문맥의 기존 compact 응답에까지 필드 근거 보장을 주장하지 않는다.

`compact-decision-grounded-v7`는 [결정·설명과 근거 충분성 검토](reports/2026-10-16_personal_assistant_decision_consistency_ko.md)를
위한 명시적 실험 경로다. 지원 문법의 역할·필드·공개 상태 근거에 결정과 설명을 연결하며,
불충분한 근거는 별도로 기록한다. 문서 설명에서 실행 여부의 근거와 내용의 의미 근거가 같은
것은 아니다. V7은 고정 비교와 원문 재생을 통과했지만, 보조 감사에서 문서의 부정·조건·파일명
역할을 잘못 요약하는 충분성 반례가 확인됐다. **기본값은 계속 `legacy`**이며 문서 내용 설명의
근거까지 충분하다고 주장하지 않는다. 주 비교 통과와 최종 기본 채택을 구분한다.

`compact-semantic-grounded-v8`은 [행동 판단과 내용 설명 근거 분리](reports/2026-10-16_personal_assistant_semantic_evidence_ko.md)를
적용한 후속 실험 경로다. 문서의 작업·금지·조건·인자 출처를 제한된 전체 문법에서 확인하고,
미지원 내용은 원문 보존과 명시적 미검증으로 구분한다. 설명 바인딩과 의미 검증은 별개이며,
해석 유보를 의미 해석 성공률에 합산하지 않는다. **기본값은 계속 `legacy`**이며, 주 평가·원문
재생·자동 테스트와 후보의 실제 브라우저 통합·기본 전환 승인은 서로 다른 단계다.

```powershell
$env:PERSONAL_ASSISTANT_DRAFT_STRATEGY = 'compact-grounded-v1'
.\tools\start_personal_assistant_review.ps1 -Workspace <새로 초기화한 합성 작업공간> -DraftStrategy compact-grounded-v1
```

`PERSONAL_ASSISTANT_DRAFT_STRATEGY=legacy`로 설정하고 백엔드를 재시작하면 기존 경로로
돌아간다. 현재 환경 변수가 없으면 `assistant-release-v1`이다. 알 수 없는 값은 다른 모델 경로로 대체하지 않고
생성 오류로 기록한다. 생성 실패 시 자동 재시도나 대체 호출은 없으며 폼 수정·확정·승인은
기존처럼 각각 명시적 사용자 동작이다. 후보 선택은 자율 실행 허용이나 안전성 인증이 아니다.

## 새 작업공간 실행

저장소 루트의 PowerShell에서 실행한다. `.venv`와 `frontend/node_modules`는 기존 설치 안내대로
준비하고, 변경된 백엔드 의존성은 `.venv/Scripts/python.exe -m pip install "pip>=26.2,<27" -e ./backend`로 설치한다.

```powershell
docker compose -f deploy/personal-assistant-eval.compose.yml up -d
docker compose -f deploy/personal-assistant-eval.compose.yml exec ollama ollama pull qwen3.5:9b
New-Item -ItemType Directory -Path artifacts/personal-assistant-review/manual -Force
.venv/Scripts/python.exe tools/init_personal_assistant_review.py --workspace artifacts/personal-assistant-review/manual/workspace-01
.\tools\start_personal_assistant_review.ps1 -Workspace artifacts/personal-assistant-review/manual/workspace-01
```

초기화는 기존 디렉터리를 인수하지 않는다. 새 폴더 이름을 지정해야 하며 자동 덮어쓰기나
이전 결과 삭제는 없다. Compose는 기존 `model-atlas_ollama-data` 모델 캐시 볼륨을 사용한다.
볼륨이 없는 새 PC에서는 원래 설치 절차로 준비해야 한다. 컨테이너 런타임은 포트 `11435`다.

시작 도구는 백엔드·프런트엔드를 loopback에 바인딩하고 준비 여부를 확인한 뒤 URL과 PID를
출력한다. 기본 포트 `18000`, `3000`이 사용 중이면 다른 프로세스를 종료하지 않고 실패한다.
`-BackendPort 18001 -FrontendPort 3001`처럼 두 포트를 지정할 수 있다.
`-BackendOnly`는 같은 포트의 백엔드만 재시작할 때 사용한다. 포트를 바꿀 때는 프런트엔드도
새 API 주소로 다시 시작해야 한다. 로그는 지정 작업공간의 `server-logs`에 저장된다.

## 코드 책임

| 코드 | 책임 |
| --- | --- |
| `services/personal_assistant/inference.py` | 로컬 런타임 호출, 공개 계약 전달, 반환값 JSON Schema 검증 |
| `stable_inference.py` | 후보의 공개 입력 축소, 제목 출처 기록, 결정별 디코딩 제약, 미완료 출력 보존 |
| `path_grounded_inference.py` | 제한된 공개 파일 명령·원본 위치, 실행기와의 어휘 정책 일치, 동적 제약 위반 표시. 채택 미달 실험 후보 |
| `role_grounded_inference.py` | 명확한 단일 할 일 생성 명령의 제목·작업 역할과 공개 중복 상태 바인딩. 범용 의미 분석기나 기본 경로가 아님 |
| `request_evidence.py` | 제한된 공개 문맥에서 시간대·우선순위 출처 위치, 명시·생략·기본·충돌 구분. 문맥 분류 오탐과 필드 완전성 한계가 있음 |
| `field_grounded_inference.py` | 필드 근거 기반 디코딩·원문 재검증, 공개 ID·상태 기반 완료 역할. 채택 미달 V5 실험 후보 |
| `creation_evidence.py` | V6의 제목·필드·문맥 분리, 표준 날짜·시간 검증과 근거 기록. 제한된 입력 문법만 지원 |
| `complete_grounded_inference.py` | V6의 요청 필드 완전성·값 디코딩 제약, 이전 완료·경로 정책 재사용과 원문 검증 |
| `decision_evidence.py` | 지원 요청의 결정·확인 필드·설명 근거 묶음. 문서 내부 의미의 충분성 한계가 있음 |
| `decision_grounded_inference.py` | V7의 결정·설명 실제 디코딩 제약과 원문 검증, 공개 입력 해시 기록 |
| `semantic_evidence.py` | V8의 행동·내용·설명 근거 분리, 제한 문법의 의미와 원문 위치, 미검증 유보 |
| `semantic_grounded_inference.py` | V8의 실제 설명 디코딩 제약과 원문 재검증. 기존 실행·승인 계약 유지 |
| `release_generation.py` | 앱 1.0 경로. V8 재사용, 미검증 의미의 중립 설명 제한, 명시적 과거 경로 롤백 |
| `generation.py` | 명시적 경로 선택, 기존 경로 유지, 실패 시 임의 대체 호출 방지 |
| `contracts.py`, `planning.py` | 닫힌 작업 계약, 결정적 시각 변환 및 대상·충돌 검증 |
| `sandbox.py`, `service.py` | 제한된 저장소, 미리보기, 승인·취소, 실행 결과와 기존 복구 계획 |
| `reviews.py` | 원문·수정본 분리, 버전 바인딩, 검토 상태 및 처리 기록 |
| `locking.py`, `recovery.py` | 실행·복구 간 OS 잠금, 중단된 두 파일 경로의 제한적 상태 대조 |
| `api/v1/routes/personal_assistant.py` | 사용자별 작업공간, loopback·역할·Origin·명시적 작업 헤더 검사 |
| `PersonalAssistantReview.tsx` | 사용자 상호작용 및 저장·확정·승인 상태 관리 |
| `personal-assistant/ReviewFields.tsx`, `AssistantWorkspace.tsx` | 입력 폼과 현황 표시 |
| `lib/personalAssistant.ts` | API 클라이언트, 표시 계약 및 원문 대비 수정 항목 |

백엔드 경로의 기준은 `backend/app`, 프런트엔드는 `frontend/components`다.
이전 V2 평가용 초안 처리 계약은 변경하지 않았다. 새 검토 흐름은 별도 `ReviewService`다.
모델에게 사용자의 확정 값이나 평가 정답을 제공하지 않는다. 사용자 수정본은 모델 추론 이후에
별도 저장되며, 코드가 그 수정본으로 실행 계획을 만든다.

확정마다 버전이 증가하고 내용 해시·작업공간 상태 해시·계획 해시로 승인을 바인딩한다.
원문 해시와 수정 내역은 추적을 위한 것이며, 로컬 SQLite 기록을 독립 서명된 인간 검토 증거로
간주하지 않는다. OS 잠금은 프로세스 종료 시 해제된다. 동일 실행 요청의 반복은 기존 결과를
반환하며 신규 실행과 별도 기록한다.

실행 중 OS 잠금으로 거절된 두 번째 승인은 즉시 거절을 반환한다. 실행자가 SQLite 쓰기
트랜잭션을 보유할 수 있어 이 경우에는 같은 DB에 거절 감사 이벤트를 쓰지 않는다.
호출자에게는 `workspace_execution_in_progress`가 전달되며 이후 명시적 재요청은 가능하다.

## 검증 재실행

```powershell
.venv/Scripts/python.exe -m pytest backend/tests/test_personal_assistant_reviews.py -q -p no:cacheprovider
.venv/Scripts/python.exe tools/probe_personal_assistant_schema.py --output artifacts/personal-assistant-review/manual/schema-probe.json
node tools/smoke_personal_assistant_review.mjs --output artifacts/personal-assistant-review/manual/browser
```

브라우저 검증에는 Playwright와 Chromium이 필요하다. 설치된 모듈을 찾지 못하면
`--playwright-module <설치된 모듈 경로>`를 지정한다. 다른 포트는 `--url`, `--api`로 전달한다.
각 브라우저 전체 검증은 새로운 작업공간에서 실행한다. 일정 충돌을 피하려고 기존 데이터를
지우는 방식은 사용하지 않는다. 합성 요청과 승인 클릭을 자동화한 테스트이며 인간 검토를
대체하거나 독립 인간 확인으로 승격하지 않는다.
