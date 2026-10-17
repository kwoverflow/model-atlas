# Personal Assistant Sandbox E2E

기존 모델 비교 평가를 보존하고, **실제 9B 추론부터 검증·승인·저장·복구까지** 확인하는 별도 실험이다.
UI나 외부 캘린더 E2E가 아니라 Python 서비스와 로컬 테스트 커넥터의 E2E다.

## 신뢰 경계

```text
사용자 요청 + 사용자가 확인한 구조화된 입력
  -> Qwen3.5 9B의 비신뢰 계획 JSON
  -> 엄격한 파싱 + 작업 범위/시간대/충돌/대상/경로 검사
  -> 변경 미리보기 + 5분 유효 승인 토큰
  -> 승인 시 계획 hash 및 DB/파일 상태 재검사
  -> 단일 작업 실행 + 영속 receipt/audit
  -> 파일 변경은 별도 승인 후 복원 가능
```

`confirmed_fields`는 사용자 확인 폼을 모사한 입력이다. 모델 응답에서 이 값을 만들어 곧바로
신뢰하면 안 된다. 자연어 요청에서 확인 폼을 만들고 사람이 검토하는 UI는 아직 없다.
테스트가 미리 작성한 입력 폼은 모델에도 제공된다. 기대 결과와 실행/취소/실패 판정은 제공하지 않는다.
이 구조화된 입력만으로도 코드가 작업을 계산할 수 있으므로, 이 실험은 LLM의 필요성이나
자유로운 자연어 비서의 완성도를 입증하는 실험이 아니다. LLM을 붙인 흐름의 실행 경계를 검증한다.

확인한 입력과 다른 응답은 변경하거나 보정하지 않고 거절한다. 무조건 거절하는 모델을 통과시키지
않도록 정상 작업 완료, 차단 대상, 승인 제어를 따로 집계한다.

## 구현 구조

| 파일 | 책임 |
| --- | --- |
| `backend/app/services/personal_assistant/contracts.py` | 제한된 입력/출력 계약, strict JSON, hash |
| `planning.py` | 시간대/DST, 중복·충돌, 대상 유일성, 사용자 확인 범위 |
| `sandbox.py` | 새 테스트 공간, SQLite, 경로 제한, 링크 차단, 파일 이동 |
| `service.py` | preview, approve, cancel, 멱등성, 영속 상태, 파일 undo |
| `scenarios.py` | 실행 전에 고정한 새 문장/데이터/독립 기대 결과 18개 |
| `run.py` | 기존 Model Atlas adapter로 실제 추론, 실행 후 DB/파일 검증 |
| `verify.py` | 소스·프로토콜 hash, 저장 상태, 원본 응답 재실행 검증 |

현재 지원 범위는 단일 일정 생성, 할 일 생성/완료, 단일 파일 이동/격리 보관이다.
일괄 작업, 반복 일정, 일정 수정/삭제, 파일 내용 검색, 외부 계정 연동은 실행하지 않는다.
`files.trash`는 OS 휴지통이 아니라 실험 폴더 안의 `trash` 격리 보관소다.
복구는 별도 승인이 필요하며 원본 위치가 이미 존재하거나 내용 hash가 바뀌었으면 차단한다.

## 실행

저장소 루트에서, backend 패키지가 설치된 Python 3.12 환경을 사용한다.
GPU runtime과 모델 준비는 [기존 평가 안내](../personal_assistant_eval/README.md)를 따른다.
출력은 지정된 artifacts 하위의 새 폴더만 허용하며 기존 결과를 덮어쓰지 않는다.

```powershell
python -m pytest backend/tests/test_personal_assistant.py experiments/personal_assistant_e2e -q
python -m experiments.personal_assistant_e2e.run --confirm-sandbox-only --output artifacts/personal-assistant-e2e/new-run
python -m experiments.personal_assistant_e2e.verify artifacts/personal-assistant-e2e/new-run --replay-output artifacts/personal-assistant-e2e/new-replay
```

실제 추론은 18개 사례 x seed 2개다. `run.py`는 하나라도 기대 흐름을 만족하지 못하면 exit code 1과
`BLOCKED`를 기록한다. 실패한 사례만 골라 재시도하거나 임계값을 바꿔 통과시키지 않는다.
`verify.py`는 새 모델 추론이 아니라 저장된 응답의 결정적 재실행이며, 검증용 새 DB와 파일을 만든다.

## 증거

- `protocol.json`: 입력 폼, 사례, 기대 결과, prompt, 설정, 실행 소스 hash
- `executed-source/`: 실제 실행 시점의 코드 사본
- `runtime.json`, `resident.json`: 실제 모델 digest, GPU 상주와 8K context 확인
- `observations.jsonl`: 원문 응답, guard 결과, 변경 전후 상태, receipt, audit
- `sandboxes/`: 사례/seed마다 독립된 실제 SQLite DB와 작은 테스트 파일
- `summary.json`: 정상 작업·차단·승인 제어를 분리한 집계
- 별도 replay 폴더의 `verification.json`: 저장 상태와 원본 응답 재실행 점검

## 한계와 운영 전 조건

- 승인자는 테스트 코드다. 실제 사용자 승인이나 로그인·권한 관리 검증이 아니다.
- 두 seed의 반복은 새로운 독립 사례가 아니며, 기존 24개 평가와 prompt·입력 계약이 다르다.
  예전 정확도 50%와 이번 전체 흐름 통과율을 직접 비교하지 않는다.
- 작업 영역은 프로그램이 새로 만든 작은 테스트 폴더다. 대규모 디렉터리, 네트워크 드라이브,
  폴더 이동, 외부 프로세스가 적대적으로 경로를 바꾸는 경쟁 조건은 지원하지 않는다.
- 전체 상태 hash를 비교하므로 무관한 변경도 재승인을 요구한다. 확장 시 리소스별 버전이 필요하다.
- 파일 이동은 같은 볼륨의 exclusive hardlink 생성 후 원본 이름 제거다. 영구 삭제나 덮어쓰기는 하지 않는다.
  DB와 파일시스템에 걸친 원자적 트랜잭션은 아니다. 도중에 프로세스가 종료되면 `executing` 기록을
  남기고 자동 재실행을 차단하지만, 중복 이름/실제 파일 상태 확인과 수동 복구가 필요할 수 있다.
- 날짜는 표준 `zoneinfo`로 계산하며 DST 공백/중복 시각은 추측하지 않고 차단한다.
- 로컬 audit/hash는 내부 일관성 증거이며 외부 인증이나 변조 방지 서명은 아니다.
- API/UI에 노출하지 않았다. 노출 전에는 사용자 인증, 권한, 확인 폼 provenance, CSRF 방어,
  실제 승인 화면, 장애 복구 및 Windows 경로 경쟁 조건 대책이 추가로 필요하다.

실측 결과: [2026-09-19 E2E 보고서](../../docs/reports/2026-09-19_personal_assistant_e2e_ko.md).
