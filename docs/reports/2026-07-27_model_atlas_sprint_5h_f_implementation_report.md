# Model Atlas Sprint 5H-F 구현 보고서

작성일: 2026-07-27

## 1. 요약

Sprint 5H-F는 Model Atlas의 운영 메트릭을 "현재 상태를 보여주는 화면"에서 "시간에 따라
검토 가능한 운영 신뢰성 증거"로 확장했다.

이번 단계에서 구현한 핵심은 다음과 같다.

- PostgreSQL 기반 운영 메트릭 스냅샷 및 정규화 포인트 보존
- 신원 세션 위생과 워커 제어 평면 가용성 SLO
- 수집 누락 구간을 실패로 반영하는 명시적 계산 규칙
- 열린 상태와 해결 상태를 보존하는 인시던트 수명주기
- HMAC-SHA256 서명, 허용 호스트, HTTPS 기본 정책을 적용한 페이징 전송
- 기존 Agent 작업의 lease, retry, dead letter, requeue 재사용
- Admin/SRE 수동 캡처 및 테스트 페이지 API
- SLO, 스냅샷, 인시던트, 전송 영수증을 통합한 Operations UI
- Prometheus 30일 보존 설정과 신규 운영 경보 규칙

이 기능은 모델 품질 점수나 배포 승인 결과를 바꾸지 않는다. Model Atlas 자체의 운영
상태가 신뢰할 수 있는지 별도의 증거로 보여주는 계층이다.

## 2. 해결하려던 문제

기존 `/operations/metrics`와 Prometheus 노출은 현재 시점의 상태를 확인하는 데는
충분했지만 다음 질문에는 답하기 어려웠다.

1. 워커와 신원 정리 상태가 지난 한 시간 동안 얼마나 안정적이었는가?
2. 수집기가 멈춰 데이터가 사라졌는데도 좋은 상태로 오인하지 않는가?
3. 경보가 언제 열리고 해결됐는지 감사할 수 있는가?
4. 페이지 전송이 실제 수신기에 도달했는지 증명할 수 있는가?
5. 수신기 장애 후 재시도와 운영자 재큐잉이 안전하게 작동하는가?
6. 여러 워커가 같은 구간을 동시에 관측해 중복 증거를 만들지 않는가?

5H-F는 이 질문을 영속 데이터, 명시적 SLO 규칙, 전송 영수증으로 답한다.

## 3. 설계 원칙

### 3.1 현재 상태와 역사 증거의 분리

기존 메트릭 집계는 그대로 유지하고, 일정 구간마다 결과를 영속 스냅샷으로 복제한다.
따라서 실시간 Prometheus 경로와 장기 감사 경로가 서로의 책임을 침범하지 않는다.

### 3.2 리더 없는 중복 방지

모든 워커가 같은 구간을 enqueue할 수 있다. 작업의 unique dedupe key와 스냅샷의 unique
bucket 제약이 최종 중복을 막는다. 별도 리더 선출 서비스가 필요하지 않다.

### 3.3 수집 누락의 실패 처리

첫 기준 스냅샷 이후 기대되는 구간 수를 계산하고, 실제 스냅샷이 없으면 good sample로
세지 않는다. 수집 프로세스가 멈춘 상태를 100% SLO로 오인하는 문제를 막는다.

### 3.4 outbox와 durable job 결합

인시던트 전환과 같은 트랜잭션에서 전송 row를 만들고, 실제 HTTP 전송은 durable Agent
job이 수행한다. 전송 장애가 인시던트 기록 자체를 롤백하지 않는다.

### 3.5 최소 정보 저장

웹훅 URL 원문, HMAC secret, 응답 본문은 데이터베이스에 저장하지 않는다. 목적지
fingerprint, payload hash, response hash, 상태 코드, 제한된 오류만 보존한다.

## 4. 구현 구조

### 데이터 계층

- `OperationalMetricSnapshot`
- `OperationalMetricPoint`
- `OperationalSLOEvaluation`
- `OperationalAlertIncident`
- `OperationalAlertDelivery`
- Alembic `202607270002`

### 서비스 계층

`backend/app/services/operational_reliability.py`가 수집, SLO 평가, 인시던트 조정, 전송
payload 생성, URL 정책 검증, 서명, 영수증 기록을 담당한다.

`backend/app/services/agent_jobs.py`는 다음 작업을 추가한다.

- `operational_observability_cycle`
- `operational_alert_delivery`

### API 계층

- `GET /api/v1/operations/reliability`
- `POST /api/v1/operations/reliability/cycles`
- `POST /api/v1/operations/reliability/test-pages`

감사는 검증된 Admin, SRE Lead, ML Ops Lead, Release Manager가 수행할 수 있다. 변경은
검증된 Admin과 SRE Lead만 가능하다.

### UI 계층

`/operations`는 다음 정보를 제공한다.

- 보존 스냅샷, SLO breach, 열린 인시던트, 전달 완료 수
- SLO observed/target/error budget/sample
- 스냅샷 연속성과 최근 핵심 지표
- 인시던트 opened/resolved 이력
- paging attempt, HTTP response, destination fingerprint
- 현재 derived alert
- 권한 기반 캡처 및 테스트 페이지 제어

## 5. SLO 규칙

신원 세션 위생:

```text
retention_due == 0 AND inactive_provider_token == 0
```

워커 제어 평면 가용성:

```text
worker_online >= 1 AND expired_lease_count == 0
```

기본 목표는 두 SLO 모두 1시간 창에서 99%다. 최소 표본 3개 전에는 `insufficient`,
이후 목표 이상은 `met`, 미만은 `breached`다.

## 6. 페이징 보안 및 실패 정책

- 운영 기본값은 paging 비활성
- HTTPS 기본 강제
- 목적지 호스트 allowlist
- URL credential/query/fragment 금지
- redirect 미추적
- 32자 이상 HMAC secret
- timeout 및 response body 크기 제한
- canonical JSON payload 서명
- event ID와 idempotency key 일치
- 전달 완료 작업 replay 시 재전송 금지

네트워크 오류, HTTP 5xx, 408, 429는 retryable이다. 잘못된 설정, 응답 크기 초과, 그 외
4xx는 permanent failure로 분류한다.

## 7. 검증 결과

### 정적 및 테스트 검증

```text
Backend pytest: 179 passed
Backend Ruff: passed
Frontend TypeScript: passed
Frontend ESLint: passed
Frontend production build: passed
Upstream warning: Starlette TestClient deprecation 1건
```

### Docker 및 데이터베이스

```text
PostgreSQL migration: 202607270002 (head)
Backend health: healthy
Paging sink health: healthy
Prometheus target: up
Prometheus rules: 10 loaded
Agent worker replicas: 2
```

중복 방지 확인 시점의 결과:

```text
Snapshots: 12
Unique snapshot buckets: 12
Observability cycle jobs: 12
Unique cycle dedupe keys: 12
```

두 워커가 같은 구간을 관찰해도 중복 스냅샷이나 중복 작업이 생기지 않았다.

### 서명 전송

Admin 테스트 페이지는 첫 시도에서 HTTP 202로 완료됐다. 데이터베이스의 delivery
payload hash와 개발 수신기의 receipt payload hash가 일치했다.

### 장애와 복구

1. paging sink를 중지했다.
2. critical 테스트 페이지를 enqueue했다.
3. 네 번의 연결 실패 후 job과 delivery가 failed/dead-letter 상태가 됐다.
4. sink를 복구했다.
5. 검증된 Admin 사유로 동일 job을 requeue했다.
6. 재큐잉 첫 시도에서 HTTP 202로 완료됐고 동일 event ID 영수증이 생성됐다.

이 과정에서 재큐잉 이후의 실제 네트워크 시도가 lifetime attempt 수에 포함되지 않던
결함을 발견했다. 실행마다 누적 카운터를 증가시키도록 수정하고 반복 attempt number를
사용한 회귀 테스트를 추가했다.

### 브라우저와 권한

Keycloak `ML Ops Lead` 로그인으로 `/operations`를 검증했다.

- SLO, 인시던트, 전송 이력 읽기 성공
- `Run capture` 비활성
- `Test page` 비활성
- 문서 수준 가로 overflow 0
- 버튼 텍스트 overflow 0
- 브라우저 warning/error 0

Admin/SRE 변경 권한은 API 테스트와 실제 Admin trusted-header 전송으로 별도 검증했다.

## 8. 운영 시 의미

5H-F 이후 Model Atlas는 "현재 워커가 켜져 있다"는 단일 상태뿐 아니라 다음을 설명할
수 있다.

- 어느 구간이 수집됐는가
- 어느 구간이 누락됐는가
- 목표 대비 실제 신뢰성은 얼마인가
- 어떤 경보가 열리고 해결됐는가
- 어느 payload가 어느 목적지로 몇 번 시도됐는가
- 수신기가 어떤 event ID와 hash를 수락했는가
- 장애 후 누가 어떤 사유로 재큐잉했는가

이는 평가 결과의 신뢰성뿐 아니라 평가 시스템 자체의 운영 신뢰성을 검토할 수 있게
한다.

## 9. 남은 한계

- 개발 paging sink는 메모리 기반이며 HA 서비스가 아니다.
- HMAC은 공유 비밀 기반 인증이며 공개키 비부인성을 제공하지 않는다.
- SLO 엔진은 Model Atlas 제어 평면 전용이며 범용 PromQL SLO 플랫폼이 아니다.
- 운영 TLS, secret manager, 외부 on-call roster, acknowledgement/escalation은 포함하지
  않는다.
- 다중 리전 합의나 범용 분산 workflow engine을 제공하지 않는다.
- 현재 99% 창에서 한 번의 과거 신원 위생 실패가 실제 breach로 남아 있다. 최신
  interval은 정상이며, 창이 이동하면 정책에 따라 자동 해결된다.

## 10. 다음 권장 단계

다음 단계는 외부 시스템과의 신뢰 경계를 실제 운영 수준으로 끌어올리는 것이 좋다.

1. staging TLS와 secret manager를 사용하는 실제 paging destination 연동
2. 외부 publisher 또는 internal CA 기반 공급망 서명
3. 목표 7B GPU 하드웨어 실행과 검토된 production capture receipt
4. 필요한 IdP의 back-channel logout 및 secret rotation 복구 훈련
5. 작업별 OS 또는 Kubernetes sandbox 실행
