# Model Atlas Sprint 5H-G 구현 보고서

작성일: 2026-08-03  
범위: 다중 구간 SLO burn-rate, 인시던트 대응, TLS 페이징, HMAC 키 순환

## 1. 요약

Sprint 5H-G는 5H-F에서 만든 영속 운영 관측 기능을 실제 인시던트 대응 단계로
확장했다. 이전에는 SLO 위반과 페이지 전송 여부를 확인할 수 있었지만, 최근 장애와
지속 장애를 구분하거나 누가 인시던트를 확인했는지, 담당자가 누구인지, 키 교체 중
어떤 키로 전송됐는지를 한 흐름에서 증명하기 어려웠다.

이번 단계에서 다음을 구현했다.

- 1시간 장기 창과 5분 단기 창을 함께 평가하는 SLO burn-rate
- 두 창이 동시에 예산을 빠르게 소모할 때만 상승하는 warning/critical 신호
- Admin/SRE의 확인, 담당자 배정, 메모와 해시 연결 감사 이력
- 미확인 critical 인시던트의 최대 3단계 자동 에스컬레이션
- 여러 HMAC 키를 동시에 수용하고 새 전송 키를 선택하는 무중단 회전 계약
- 사설 CA를 검증하는 HTTPS 페이징과 개발용 Docker TLS fixture
- 위 상태와 조작을 통합한 Operations UI

## 2. 해결하려는 문제

단일 시점의 상태나 단일 SLO 창만 보면 짧고 강한 장애와 오래 지속된 낮은 수준의
장애를 구분하기 어렵다. 또한 페이지를 보냈다는 기록만으로는 대응 책임과 시간 흐름을
설명할 수 없다. 운영 키를 교체할 때 큐에 남아 있던 재시도 이벤트가 어떤 키를 써야
하는지도 불명확해질 수 있다.

5H-G는 다음 원칙으로 이 문제를 해결한다.

1. 동일한 영속 스냅샷에서 장기·단기 창을 독립 계산한다.
2. 두 창의 burn-rate가 함께 임계값을 넘을 때만 높은 심각도를 부여한다.
3. 대응 행위는 현재 상태와 별도의 append-only 감사 이벤트로 남긴다.
4. 전송 생성 시 key ID를 고정해 재시도와 requeue의 암호학적 의도를 보존한다.
5. TLS 인증서와 호스트를 실제 검증하고 개발 fixture임을 명시한다.

## 3. 구조와 동작

### 3.1 SLO 평가

`OperationalSLOEvaluation`은 장기·단기 관측 비율, 두 burn-rate, burn alert level을
저장한다. 각 창에서 첫 보존 스냅샷 이후 누락된 예정 구간은 not-good으로 계산한다.
최소 샘플 미만이면 `insufficient`이며 높은 burn 경보를 만들지 않는다.

기본 임계값은 warning `6.0x`, critical `14.4x`다. 장기와 단기 값이 모두 같은
임계값 이상일 때만 해당 수준이 된다. 일반적인 SLO breach는 계속 인시던트로 남지만,
다중 창 critical이 아니면 warning 심각도를 사용한다.

### 3.2 인시던트 대응

인시던트 현재 상태에는 확인 시간·확인자, 담당자, 에스컬레이션 수준이 추가됐다.
대응 행위는 `OperationalAlertIncidentAction`에 별도로 기록된다.

- `acknowledged`: verified Admin/SRE가 대응 시작을 확인
- `assigned`: 현재 담당자 설정
- `note`: 조사 메모 추가
- `escalated`: 제어 루프가 자동 생성

각 이벤트는 이전 이벤트 해시를 포함해 순서를 검증할 수 있다. 확인된 인시던트는 자동
에스컬레이션 대상에서 제외된다.

### 3.3 키 순환과 TLS

발신자는 JSON keyring과 active key ID를 읽는다. delivery outbox 생성 시 key ID를
저장하며 이후 active key가 바뀌어도 기존 delivery는 저장된 키를 사용한다. 수신자는
새 키, 폐기 예정 키, legacy 키를 동시에 검증할 수 있다. API와 DB에는 key ID만 남고
비밀키는 남지 않는다.

Docker observability profile은 `paging-tls-init`이 개발 CA와 서버 인증서를 named
volume에 만들고, paging sink는 TLS 1.2 이상으로 서비스한다. backend와 worker는 CA만
읽기 전용으로 마운트하고 `paging-sink` 호스트 인증서를 검증한다.

## 4. 주요 변경 파일

- `backend/app/core/config.py`: SLO 창·burn·에스컬레이션·keyring·CA 설정
- `backend/app/models/entities.py`: 평가, 인시던트, action, delivery 필드
- `backend/alembic/versions/202608030001_operational_incident_response.py`: additive migration
- `backend/app/services/operational_reliability.py`: 계산, action, escalation, 서명, TLS
- `backend/app/operations/paging_sink.py`: 다중 키 검증과 HTTPS 수신
- `backend/app/operations/paging_tls.py`: 개발 인증서 초기화
- `backend/app/api/v1/routes/operations.py`: incident action API
- `frontend/components/OperationalReliabilityConsole.tsx`: 대응 콘솔
- `frontend/types/api.ts`: v2 응답 타입
- `docker-compose.yml`: TLS initializer, volume, keyring 설정
- `deploy/observability/.env.observability.example`: 5H-G 운영 예시

## 5. API와 권한

새 mutation API:

```text
POST /api/v1/operations/reliability/incidents/{incident_id}/actions
```

payload는 `action_type`, 8~500자의 `reason`, 배정 시 `assignee`를 받는다. verified
Admin과 SRE Lead만 실행할 수 있다. ML Ops Lead와 Release Manager는 overview와 action
history를 감사할 수 있지만 mutation은 할 수 없다.

overview schema는 `model-atlas-operational-reliability-v2`, 권한 정책은
`operational-reliability-rbac-v2`, 새 paging payload는
`model-atlas-paging-event-v2`다. 수신기는 전환 중 기존 v1 payload도 허용한다.

## 6. 검증 결과

자동 검증:

- backend pytest: 181 passed, upstream TestClient 경고 1개
- backend Ruff: passed
- frontend TypeScript: passed
- frontend ESLint: passed
- frontend production build: passed
- Compose config: passed
- PostgreSQL Alembic: `202608030001 (head)`

Docker 통합 검증:

- backend healthy
- Agent worker 2개 online
- HTTPS paging sink healthy
- TLS initializer exit 0
- test delivery `9106e35c-07c7-4727-aaca-444c77dbdce9` HTTP 202
- 수신 receipt의 signing key ID: `2026-08-primary`
- 기존 delivery의 migrated key ID: `legacy`
- queued 0, failed 0인 전달 상태 확인

인시던트 action 검증:

- 확인 action hash: `e1a66ed721fe9d6f...`
- 배정 action의 `previous_action_hash`가 위 확인 action hash와 일치
- 현재 담당자 `platform-on-call` 반영

브라우저 검증:

- 기본 데스크톱 viewport에서 document-level horizontal overflow 없음
- 390 x 844 모바일 viewport에서 document-level horizontal overflow 없음
- 모바일 표 3개는 페이지가 아닌 각 표 내부에서 스크롤
- 잘린 interactive element 0
- response history에 확인·배정 이벤트와 hash prefix 표시
- browser console error 0

## 7. 호환성과 마이그레이션

라우트는 additive이며 기존 metrics/alerts API를 제거하지 않았다. migration은 기존 SLO,
incident, delivery row에 안전한 기본값을 넣은 뒤 새 제약을 적용한다. 기존 delivery는
`legacy` key ID로 표시되어 과거 전송을 계속 읽을 수 있다.

기존 paging event v1은 receiver에서 계속 허용하지만 새 sender는 v2를 생성한다. 단일
`OPERATIONAL_PAGING_HMAC_SECRET`도 legacy 호환 경로로 유지된다.

## 8. 제한사항

- bundled paging sink는 메모리 기반 개발 verifier이며 HA on-call 시스템이 아니다.
- keyring은 환경 설정 기반이며 Vault/KMS 같은 외부 secret manager는 아직 연결하지
  않았다.
- 개발 CA는 staging/production 인증서로 사용할 수 없다.
- 자동 에스컬레이션 시점은 capture interval만큼 지연될 수 있다.
- action hash chain은 외부 transparency log에 anchor되지 않는다.
- 기본 burn 임계값은 시작 정책이며 실제 서비스 SLO에 맞춰 조정해야 한다.

## 9. 다음 권장 단계

다음 단계는 5H-G 계약을 외부 staging 서비스에 연결하는 것이다.

1. Vault/KMS 또는 orchestrator secret projection으로 keyring 공급
2. 실제 staging paging provider adapter와 수신 acknowledgement correlation
3. 인증서 갱신·만료·CA 교체 drill
4. burn 정책별 alert noise와 detection latency 측정
5. action hash의 독립 저장소 또는 transparency anchor
6. Kubernetes 환경의 rolling key rotation과 failure injection

5H-G 결과로 Model Atlas는 단순히 "현재 상태가 나쁘다"를 보여주는 수준을 넘어,
"얼마나 빠르게 예산을 쓰고 있으며 누가 언제 대응했고 어떤 신뢰 경로로 페이지가
전달됐는가"를 하나의 감사 가능한 흐름으로 설명할 수 있게 됐다.
