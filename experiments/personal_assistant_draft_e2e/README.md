# Personal Assistant Draft E2E V2

LLM이 한국어 요청에서 입력 폼 초안을 추출하고, 코드가 실행 시각과 논리 절대 경로를 생성한다.
기존 V1 실험과 실행 소스는 보존하고 별도의 계약/평가 디렉터리를 추가했다.

```text
자연어 + 기존 일정/할 일/파일 목록
  -> LLM: operation, 제목, 현지 시각, IANA 시간대, 상대 경로 초안
  -> 별도로 확인한 입력과 대조
  -> 코드: 시간대 변환, 종료 시각 계산, 경로 생성, 충돌/중복 검사
  -> 미리보기 -> 승인/취소 -> 실제 테스트 DB/파일 변경 -> receipt/audit
```

모델 입력에 `confirmed_fields`, 기대 결과, 실행/차단 라벨은 없다.
확인할 필드는 테스트가 미리 작성했으며, 승인은 테스트 코드가 수행한다.
사람의 실제 확인 화면이나 자유로운 자연어 비서의 완성도를 검증한 것은 아니다.
잘못 추출한 값을 자동으로 고치지 않으며 확인한 입력과 다르면 실행을 거절한다.
현재 UI에서 사람이 수정한 초안을 수용하는 별도 확정 단계는 후속 구현 과제다.

## 계약과 코드

`backend/app/services/personal_assistant/drafts.py`의 `Draft`와 `DraftAssistantService`가 새 계약이다.
모델 출력은 다음과 같다.

```json
{
  "decision": "propose",
  "intent": {
    "operation": "calendar.create",
    "title": "Consultation",
    "local_start": "2026-11-05T08:10:00",
    "source_timezone": "America/New_York",
    "duration_minutes": 50
  },
  "reason": "Draft for review"
}
```

`local_start`에는 UTC offset이 없다. 최종 `start_at`과 `end_at`은 표준 `zoneinfo`와 경과 분으로
코드가 계산한다. 파일은 모델이 상대 경로만 제안하고 기존 경로 검증을 거쳐 코드가 도구 인자를 만든다.
거절/질문/변경 없음은 `intent:null`이다. 필수 키 누락, 중복 JSON 키, 추가 동작, 확인하지 않은 값은 거절한다.
기본 시간대와 null/생략은 공개 계약대로 비교하며 요청하지 않은 마감이나 우선순위를 만들지 않는다.

이전 승인 서비스와 샌드박스 저장소를 재사용한다. 기존 V1 메서드와 파일은 변경하지 않았다.
실행은 단일 일정 생성, 할 일 생성/완료, 단일 파일 이동/격리 보관에 한정한다.
일괄 처리, 실제 캘린더 계정, 임의 개인 폴더, OS 휴지통은 이 실험에 포함하지 않는다.

## 재현

저장소 루트의 Python 3.12 환경에서 backend를 설치하고 GPU Ollama 런타임을 준비한다.
런타임 준비 방법은 [기존 모델 평가 안내](../personal_assistant_eval/README.md)를 따른다.

```powershell
python -m pytest backend/tests/test_personal_assistant_drafts.py experiments/personal_assistant_draft_e2e -q
python -m experiments.personal_assistant_draft_e2e.run --confirm-sandbox-only --output artifacts/personal-assistant-draft-e2e/new-run
python -m experiments.personal_assistant_draft_e2e.verify artifacts/personal-assistant-draft-e2e/new-run --replay-output artifacts/personal-assistant-draft-e2e/new-replay
```

20개 고정 사례를 2개 seed로 실행한다. 40개 기대 흐름과 40개 schema 검사 모두 통과해야
`SANDBOX_DRAFT_E2E_PASS`이며, 그 외에는 `BLOCKED`와 exit code 1을 남긴다.
차단해야 하는 요청이 차단돼도 모델의 JSON 형식이 틀리면 최종 Gate를 통과하지 않는다.
일반 정상 작업의 거절은 성공으로 세지 않는다. runtime 오류와 실행 계층 오류도 별도로 기록한다.

출력은 `artifacts/personal-assistant-draft-e2e` 아래의 새 디렉터리여야 한다.
실행 전 protocol과 소스를 저장하고 원문 응답, 실제 변경 전후 상태, audit와 모델 digest를 남긴다.
검증기는 저장된 원문을 새 샌드박스에서 재실행한다. 재실행은 추가 모델 추론이나 외부 인증이 아니다.

## 현재 결과

2026-10-11 실행은 **34/40 기대 흐름, schema 38/40, 최종 BLOCKED**다.
새 시간대 변환, 파일 보관/복구, stale 승인 차단은 검증됐지만 제목 따옴표와 현지 시각 offset,
거절 응답의 `intent` 누락이 남았다. 이전 30/36과는 입력 계약과 사례가 달라 직접적인 성능 향상률로 비교하지 않는다.

[상세 결과와 당면 과제/계획](../../docs/reports/2026-10-11_personal_assistant_draft_e2e_and_plan_ko.md).
