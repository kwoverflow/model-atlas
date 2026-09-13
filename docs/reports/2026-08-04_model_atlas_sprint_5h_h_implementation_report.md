# Model Atlas Sprint 5H-H 구현 및 검증 보고서

작성일: 2026-08-04

## 1. 요약

Sprint 5H-H는 5H-G에서 구현한 HMAC 서명 기반 HTTPS 페이징을 실제 스테이징 환경에
연결할 수 있는 형태로 강화했다. 핵심은 다음 세 가지다.

1. 비밀 값을 환경 변수에 고정하지 않고 런타임 파일 projection으로 주입하고, 서비스
   재시작 없이 active key를 교체한다.
2. HTTP 2xx만으로 전송 성공을 인정하지 않고, 정확한 delivery UUID와 연결된 공급자
   수신 확인서를 검증하고 저장한다.
3. 정상 전송, 키 교체, 수신기 장애, dead letter, 감사 가능한 requeue와 복구를 반복 가능한
   명령으로 검증한다.

결과적으로 Model Atlas의 운영 화면은 단순히 "웹훅 호출 성공"을 보여 주는 수준을 넘어,
어떤 키로 어떤 이벤트를 전송했고 외부 공급자가 어떤 receipt로 언제 수락했는지를
추적할 수 있게 되었다.

## 2. 해결하려던 문제

5H-G까지의 구조에는 아래와 같은 현실적인 운영 공백이 있었다.

- Compose 또는 프로세스 환경 변수에 비밀 값을 장기간 고정하면 교체와 접근 통제가
  어렵다.
- 이미 큐에 들어간 delivery와 active key 교체 시점이 충돌하면 재시도 가능한 작업이
  복구 불가능해질 수 있다.
- 웹훅 서버의 HTTP 202가 실제 on-call 공급자의 이벤트 수락을 의미한다고 단정할 수 없다.
- 공급자 응답을 DB delivery와 연결하지 않으면 운영자와 평가자가 end-to-end 증거를
  확인하기 어렵다.
- 정상 상태만 검증하면 수신기 장애, 재시도 소진, dead letter, requeue 이후의 실제 복구
  동작을 보장할 수 없다.
- observability profile에서 trust-source fixture가 빠지면 운영 상태가 지속적으로
  degraded 되지만 시작 명령만으로 이를 예방하기 어려웠다.

## 3. 구현 내용

### 3.1 런타임 secret projection

- `backend/app/core/secret_projection.py`
  - 최대 65,536바이트의 bounded read
  - UTF-8, 빈 값, JSON string map 형식 검증
- `backend/app/operations/paging_secrets.py`
  - 무작위 HMAC key 초기화
  - active/retiring key 동시 생성
  - atomic replace 및 제한된 파일 권한
  - 이전 active key를 보존하는 rolling rotation
  - 로그에는 secret을 출력하지 않고 key ID와 개수만 출력
- sender와 receiver 모두 매 요청 또는 delivery마다 projection을 다시 읽는다.
- delivery는 enqueue 시점의 `signing_key_id`를 보존하므로 교체 전에 큐에 들어간 작업도
  retiring key로 재시도할 수 있다.
- 일시적인 key/CA projection 장애는 permanent configuration failure가 아니라 retryable
  delivery failure로 처리한다.

### 3.2 공급자 receipt 상관관계

필수 receipt 모드에서는 다음 조건을 모두 만족해야 성공으로 저장한다.

- `schema_version`이 `model-atlas-paging-provider-receipt-v1`
- `accepted`가 `true`
- `provider`가 설정된 공급자 ID와 일치
- `provider_event_id`가 정확한 delivery UUID와 일치
- `receipt_id`가 bounded printable identifier
- `accepted_at`이 timezone-aware이고 허용된 freshness 범위 안에 존재

잘못되거나 관계없는 2xx 응답은 성공으로 간주하지 않고 retryable error로 남긴다. 검증된
receipt는 `provider_name`, `provider_event_id`, `provider_receipt_id`,
`provider_accepted_at`으로 영속화한다.

### 3.3 스테이징 readiness gate

운영 overview schema를 `model-atlas-operational-reliability-v3`으로 확장하고 일곱 가지
readiness check를 제공한다.

| 검사 | 의미 |
| --- | --- |
| `paging_enabled` | durable paging 활성화 |
| `secure_destination` | allowlisted HTTPS 목적지 |
| `ca_verification` | system trust 또는 projected CA 검증 |
| `projected_keyring` | 유효한 runtime key projection |
| `rolling_key_rotation` | active key와 retiring key 동시 존재 |
| `provider_receipt_contract` | strict correlated receipt 활성화 |
| `recent_provider_receipt` | 최근 end-to-end receipt 영속화 |

`tools/verify_operational_staging.py`는 test page를 생성하고 job 완료와 7/7 readiness를
polling하며, 하나라도 실패하면 nonzero로 종료한다.

### 3.4 장애 및 복구 drill

`tools/run_operational_failure_drill.ps1`는 다음 흐름을 자동화한다.

1. paging sink 중지
2. test page 생성
3. bounded retry 소진과 dead-letter 확인
4. `finally`에서 sink 재시작
5. SRE identity로 동일 job requeue
6. 완료 및 correlated receipt 확인
7. operational capture를 실행해 transient incident reconciliation 확인
8. health, open incident, dead-letter count, readiness와 delivery ID를 JSON으로 출력

### 3.5 Docker 및 개발 명령

- runtime-only named volume `paging-secrets`
- one-shot `paging-secrets-init` profile service
- backend, worker, sink에 read-only key projection mount
- observability 시작 시 trust-source profile과 fixture를 함께 기동
- `make operational-staging-verify`
- `make operational-failure-drill`
- `make paging-key-rotate KEY_ID=<new-id>`

### 3.6 운영 UI

Operations console에 다음 항목을 추가했다.

- projected secret source 상태
- 사용 가능한 key 수와 active key ID
- provider ID와 strict receipt 상태
- 7개 readiness check 및 종합 ready 상태
- delivery별 provider, event ID, receipt ID, accepted time

## 4. 데이터 및 마이그레이션

Alembic revision `202608040001`은 `operational_alert_deliveries`에 아래 필드를 additive하게
추가한다.

- `provider_name`
- `provider_event_id`
- `provider_receipt_id`
- `provider_accepted_at`

기존 delivery와 API route를 유지하며, 과거 row는 새 필드가 null인 상태로 계속 읽을 수
있다.

## 5. 검증 결과

### 5.1 자동화 검증

```text
Backend pytest: 186 passed, 1 upstream Starlette TestClient warning
Backend and tools Ruff: passed
Frontend typecheck: passed
Frontend lint: passed
Frontend production build: passed
```

경고는 외부 Starlette TestClient import 경로의 deprecation warning이며 테스트 결과나
애플리케이션 동작에는 영향을 주지 않는다.

### 5.2 Docker end-to-end 검증

- DB migration head `202608040001`
- backend와 frontend 정상
- Agent worker 2개 정상
- PostgreSQL, paging sink, trust-source fixture 정상
- Prometheus, Alertmanager, alert sink 정상
- TLS와 paging secret initializer 정상 종료
- readiness 7/7 통과
- 운영 health `healthy`, open incident 0, dead letter 0

### 5.3 무중단 키 교체

- 기존 active key: `development-primary`
- 신규 active key: `2026-08-04-rotated`
- 기존 key를 retiring key로 유지
- sender와 receiver 재시작 없이 신규 test page 전송 성공
- delivery에 신규 signing key ID와 일치하는 provider receipt 저장

### 5.4 장애 복구

- sink 중단 상태에서 delivery failure와 dead letter 도달 확인
- 동일 job을 감사 가능한 API로 requeue
- sink 복구 후 동일 job 완료
- reconciliation job 완료 및 transient incident 0 확인
- 최종 dead-letter count 0
- 최종 operational health `healthy`
- staging readiness true

### 5.5 UI 검증

- 데스크톱 1280 x 720
- 모바일 390 x 844
- 문서 수준 horizontal overflow 0
- table overflow는 각 table container 내부로 제한
- browser console warning/error 0

## 6. 신뢰성과 보안 측면의 개선

- secret material을 문서, 로그, rotation 결과에 노출하지 않는다.
- 파일 크기와 문자열 형식을 제한해 비정상 projection 입력을 조기에 차단한다.
- 빈 key/secret, 정규화 중복 key ID, 짧은 key는 fail-closed 하며 수신기의 일시적 projection
  오류는 HTTP 503으로 durable retry에 연결한다.
- 목적지 HTTPS, host allowlist, TLS CA verification과 HMAC signature를 함께 적용한다.
- event ID와 provider receipt를 묶어 replay와 오인된 성공 판정을 줄인다.
- active key 교체와 queued delivery의 signing identity를 분리해 rolling rotation을 가능하게
  한다.
- 일시적 secret/CA projection 실패는 기존 durable retry 정책을 재사용한다.
- readiness와 drill을 코드로 제공해 운영자의 수동 확인 편차를 줄인다.

## 7. 명시적 한계

이번 Sprint는 외부 시스템과의 실제 계약을 검증할 수 있는 adapter boundary와 harness를
완성한 것이다. 아래 항목을 이미 연결했다고 주장하지 않는다.

- Vault, AWS/GCP/Azure secret manager 또는 Kubernetes Secrets Store CSI
- 상용 paging/on-call 공급자
- 조직의 managed PKI와 인증서 자동 갱신
- multi-region delivery 또는 공급자 장애 조정
- 공급자 측 acknowledgement callback과 양방향 상태 동기화

번들 `paging-sink`는 단일 프로세스 in-memory 개발 verifier이며 Docker CA와 secret volume도
개발 fixture다.

## 8. 다음 권장 단계

1. 실제 staging orchestrator에서 secret projection과 최소 권한 mount를 연결한다.
2. 실제 paging 공급자 adapter가 receipt v1 계약을 반환하도록 구현한다.
3. 조직 managed PKI 또는 system trust를 적용하고 인증서 갱신 drill을 수행한다.
4. staging deployment마다 verifier 결과와 failure drill JSON을 release evidence로 보관한다.
5. 기존 모델 측 과제로 돌아가 target 7B GPU, 외부 publisher trust, reviewed production
   capture를 확보한다.

상세 운영 계약과 실행 절차는 `docs/staging_paging_qualification.md`를 기준으로 한다.
