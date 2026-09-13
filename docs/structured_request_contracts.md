# 사용자 확정 요청 계약

작성일: 2026-09-09 · Evidence Remediation 18 · 로컬 실험 기능

후속 단계(2026-09-10): [고정 시나리오 자동 검사와 입력 검증](request_scenario_validation.md)을 추가했다.
아래 검증 수치는 이 단계 당시 기록이며, 후속 결과는 별도 문서에 보존한다.

## 결론

사용자가 정확한 `query`와 우선순위의 **값 지정 또는 생략**을 저장하고 별도로 확정한 뒤,
생성된 Tool 호출이 그 계약과 일치할 때만 모의 실행하는 UI/API를 추가했다.
자연어 해석을 또 다른 모델 호출에 맡기지 않고, 실행에 필요한 일부 항목을 명시적 입력으로 바꾼다.

이 기능은 새로 학습한 모델도, 모델 정확도 향상 실험도 아니다. 사용자가 확정한 입력이
적절한지, 원래 자연어와 의미상 일치하는지까지 자동으로 증명하지 않는다.
공식 결과는 여전히 `BLOCKED`, critical failure **110**, actual runtime result **384**,
실제 출력 검토 **0/30**, `not_production_ready`다.

## 해결하려는 문제

[이전 우선순위 검증 실험](ticket_priority_verification.md)에서 같은 모델의 추가 자연어
검증은 오실행 일부를 줄였지만, 올바른 생략을 거절하거나 모순된 지시를 허용했다.
`priority`가 선택 인자라는 스키마만으로는 사용자가 생략을 원했는지 판단할 수 없다.

이번 단계의 기준은 다음처럼 좁고 명확하다.

| 확정 계약 | 허용하는 제안 | 차단하는 예 |
| --- | --- | --- |
| `set: low` | `priority: "low"` | 우선순위 없음, `normal`, `high` |
| `set: normal` | `priority: "normal"` | 우선순위 없음 |
| `set: high` | `priority: "high"` | 우선순위 없음, `low` |
| `omit` | `priority` 키 없음 | `priority: "normal"`, `null` |
| `unresolved` | 없음 | 확정 및 실행 모두 불가 |

`query`도 공백과 대소문자를 포함한 정확한 문자열 비교를 한다. `create_ticket` 이외의 Tool,
공개 스키마에 없는 인자, 잘못된 JSON은 차단한다. 런타임에서 생략 시 `normal`을 적용하더라도
계약의 **명시적 normal 지정과 인자 생략을 동등하게 보지 않는다**.

## 사용 순서

화면: [요청 계약](http://localhost:3000/structured-requests)
또는 `Advanced Lab > Request Contracts`.

1. `새 요청`에서 원래 요청과 실제 전달할 `query`를 입력한다.
2. 우선순위를 `값 지정` 후 직접 선택하거나 `생략`으로 정한다. 기본 상태는 `미확정`이며,
   `값 지정`을 선택해도 기본값을 자동 입력하지 않는다.
3. `초안 저장`을 누른다. 오른쪽 저장값과 계약 해시를 확인한다.
4. 확인 체크박스를 선택하고 `요청 확정`을 누른다. 확정은 15분 동안 유효하다.
5. `로컬 모델 제안 생성`을 누르거나, 직접 준비한 제안 JSON을 붙여 넣고 `제안 검증`을 누른다.
6. 일치 판정의 제안을 선택해 `모의 실행`을 누른다. 실제 외부 티켓은 생성되지 않는다.
7. 입력 수정, 취소, 만료 후에는 초안을 다시 저장하고 재확정한다. 저장하면 버전이 증가한다.
   실행은 확정한 버전당 1회다. 새로고침이나 서버 재시작 후에도 저장된 요청과 기록은 남는다.

직접 입력할 수 있는 제안 형식의 예:

```json
{"tool_name":"create_ticket","arguments":{"query":"점검 요청","priority":"low"}}
```

이 예는 문서 예시일 뿐이며, 화면은 확정값을 복사해 모델 제안을 자동 작성하지 않는다.
자동 QA가 만든 `AUTOMATED QA` 요청은 기능 검사 기록이며 사람의 검토 완료가 아니다.

## 처리 구조

```text
원래 자연어 요청 -----------------> 로컬 모델(v3) ------> 제안 원문/생성 기록
                                                          |
사용자 구조화 입력 -> 초안 저장 -> 별도 확정                |
                       |           |                      v
                       |     revision + SHA-256 -> 공개 스키마 + 정확한 인자 비교
                       |                                  |
                       +-> 수정 시 이전 확정 무효          v
                                                명시적 모의 실행 요청
                                                          |
                                            DB 잠금 + 현재 계약 재검증
                                                          |
                                            실행권 선점(flush) 후 로컬 핸들러
                                                          |
                                                실행 영수증 + 변경 이력
```

모델에는 원래 자연어 요청과 공개 Tool 설명만 전달한다. 별도로 확정한 `query`, 우선순위,
확정 여부, 계약 해시나 평가 정답을 프롬프트에 전달하지 않는다. 원래 자연어에 사용자가 쓴 값은
물론 입력에 포함된다. 검사 과정은 모델 호출 없이 동작하며 제안 인자를 수정하지 않는다.

생성기는 기존 `NullablePresenceToolAdapter`를 재사용한다. 그 프로토콜에서 모델이 출력한
`null`은 선택 인자 생략으로 변환될 수 있다. 이후 계약 검사는 그 **제안 결과**를 검사한다.
직접 제출한 공개 Tool 호출의 `priority: null`은 유효한 공개 호출이 아니므로 차단한다.
API에는 생성 메타데이터와 실제 요청 본문을 보존해 이 두 경계를 구분한다.

## 코드 책임

| 파일 | 책임 |
| --- | --- |
| `backend/app/schemas/structured_requests.py` | 명시적 값/생략/미확정 타입, 입력 길이, 추가 필드 거절, boolean 확인 |
| `backend/app/services/structured_ticket_contract.py` | 공개 호출 검증과 순수한 인자 비교, 정규화 해시 |
| `backend/app/services/structured_requests.py` | 소유권, 버전, 확정, 만료, 모델 제안 기록, 잠금 및 모의 실행 |
| `backend/app/models/structured_requests.py` | 요청과 제안 검사 기록을 위한 별도 DB 모델 |
| `backend/app/api/v1/routes/structured_requests.py` | 서버가 확인한 운영자 정보와 HTTP 입력 경계 |
| `frontend/components/StructuredRequestLab.tsx` | 저장·확정·검증·실행 상태와 입력 화면 |
| `frontend/types/structuredRequests.ts` | 프런트엔드 API 타입 |
| `tools/smoke_structured_requests.py` | 로컬 API 동시성 및 생성 연결 재검사 |

기존 패턴대로 스키마, 순수 비교 함수, 상태를 관리하는 서비스, API, UI를 분리했다.
일반화된 플러그인 실행기를 추가하지 않았다. 다른 Tool을 지원하려면 해당 Tool의 구조화 입력,
비교 정책, 권한 및 부작용 모델을 따로 설계해야 한다.

DB migration `202609090001`은 `202608040001` 뒤에 요청/검사 테이블 2개만 추가한다.
기존 47개 테이블 구조 해시 검증은 유지한다. 기존 모델 import 호환 경로에도 새 타입을 등록했다.

## API 계약

기준 경로: `/api/v1/structured-requests`.
쓰기 요청은 `x-model-atlas-lab-action: 1` 헤더가 필요하다.
표의 `{id}`는 요청 ID다. `{check_id}`는 해당 요청에 저장된 검사 ID다.

| 메서드 / 경로 | 동작 |
| --- | --- |
| `GET /` | 본인 요청 목록, 기본 20개, 최대 50개 |
| `POST /` | 초안 생성 |
| `GET /{id}` | 요청, 확정, 변경 이력, 최근 검사 20개 |
| `PUT /{id}` | 현재 버전/해시를 지정한 새 초안 저장 |
| `POST /{id}/confirm` | 현재 버전/해시와 `acknowledged: true`로 확정 |
| `POST /{id}/revoke` | 현재 확정 취소 |
| `POST /{id}/checks` | 별도 제안을 저장하고 현재 계약과 비교 |
| `POST /{id}/generate` | 확정·미사용 계약에 대해 로컬 모델 제안 생성 |
| `POST /{id}/checks/{check_id}/execute` | DB의 제안을 다시 검증하고 모의 실행 |

생성 이외의 버전 지정 요청은 `expected_revision`, `expected_hash`를 포함한다.
초안 수정은 `draft`, 제안 검사는 `proposal`을 추가한다. 실행 API는 클라이언트가 보낸
판정이나 대체 인자를 신뢰하지 않고 저장된 원문을 다시 읽는다.
미확정 초안에 대한 API 검사 기록은 생성될 수 있지만 허용 판정을 받지 못한다.

## 실행 경계

- 현재 버전과 계약 해시, 확정 연결, 15분 만료, 미사용 여부를 실행 직전에 다시 검사한다.
- 제안 원문 SHA-256과 공개 Tool/로컬 핸들러의 계약 및 소스 해시를 확인한다.
- PostgreSQL 행 잠금과 SQLAlchemy optimistic version을 사용하고, 핸들러 호출 전에 실행권을
  `flush`한다. 같은 버전의 다른 검사 결과를 실행하려는 요청은 거절한다.
- 이미 실행한 같은 검사 ID는 기존 영수증만 반환한다. 이후 버전이 바뀌거나 취소되어도 이는
  과거 결과 조회에 해당하며 새로운 실행이 아니다.
- 모델 응답을 기다리는 동안 DB 트랜잭션을 잡아두지 않는다. 응답 후 다시 현재 요청을 읽어
  수정·취소·만료·실행 여부를 확인한다.
- 모델은 현재 `qwen2.5:1.5b`, temperature 0, seed 42, 응답 토큰 상한 256, 호출 예산 120초다.
  별도의 동일 모델 자연어 우선순위 검증 호출은 없다.
- 로컬 Ollama 주소만 후보로 사용하며 전역 외부 API URL과 API 키를 상속하지 않는다.
  호스트/DNS/프록시 자체에 대한 보안 보장은 별도 배포 경계의 책임이다.

## 인증과 제한

운영자 정보는 기존 인증 미들웨어에서 가져오며 요청 본문으로 바꿀 수 없다.
인증 활성 환경에서 미인증 요청은 401이고, 허용 역할이 아닌 인증 운영자는 403이다.
인증 사용자 간에는 소유자별로 조회·변경을 제한한다. 기존 브라우저 로그인 CSRF도 적용된다.
Origin이 있는 쓰기 요청은 기존 허용 출처 목록에 있어야 한다.

**현재 로컬 데모에서는 신원이 검증되지 않은 공용 `local-ui`를 사용한다.**
확정 기록은 `local_unverified_assertion`이며 다중 사용자 인증이나 사람이 읽었다는 증거가 아니다.
인증 운영자 기록도 API 확인 의사 표시일 뿐, 독립 검토의 사실 자체를 증명하지 않는다.
로컬 API 접근이 가능한 다른 프로그램도 확인 요청을 보낼 수 있다.

실행 대상은 소스 해시로 제한한 `simulated create_ticket`뿐이다. 외부 서비스에 대한
exactly-once, 장애 복구, 서명된 불변 감사 저장소, 조직 수준 권한 위임을 구현한 것은 아니다.
DB 관리자에 의한 조작까지 방어하지 않으며, 변경 이력은 외부 불변 감사 저장소가 아니다.
모델 생성 전역 동시성 제한, 오래된 실험 기록 정리 및 전체 목록 페이지 이동은 후속 작업이다.

이 구조는 입력을 확인하는 사용자 부담을 추가한다. 잘못 확정한 입력 자체의 위험은 남는다.
의미 검토, 민감정보 판단, 본문 내용의 안전성, 다른 Tool 및 다단계 Agent 실행은 범위 밖이다.

## 검증 결과

| 검사 | 2026-09-09 결과 |
| --- | --- |
| 새 기능 테스트 | 49개 통과 |
| 전체 호스트 백엔드 | 535개 통과, 환경 조건부 1개 건너뜀 |
| 전체 Docker 백엔드 | 536개 통과 |
| Ruff / 프런트엔드 lint / TypeScript / Docker 프런트엔드 build | 통과 |
| PostgreSQL 동시 실행 | HTTP 200 1건, 409 1건, 핸들러 호출 1회 |
| 재요청 | 기존 영수증 반환, 추가 실행 없음 |
| 실제 로컬 모델 연결 | API/브라우저 각 1개 QA 제안 생성 확인 |
| 브라우저 흐름 | 저장, 값 선택, 별도 확정, 불일치 차단, 생성, 모의 실행, 재시작 후 복구 확인 |
| 화면 | 데스크톱 1440×1000, 모바일 390×844, 페이지 가로 넘침 없음 |
| 기존 고정 증거 | Remediation 17까지 독립 재감사 통과, 1.0.4 자료 검증 통과 |

새 테스트는 low/normal/high/생략 조합 16개, 무효 JSON·추가 인자·잘못된 Tool/query,
미확정·만료·취소·수정·변조, 동시 버전 충돌, 소유권·역할·Origin, 모델 입력 분리,
생성 도중 수정/취소 및 생성 실패를 포함한다. 기존 TestClient 의존성 deprecation 경고는 남아 있다.

두 실제 모델 호출 흐름의 성공은 연결 스모크 테스트 결과다. 홀드아웃 평가나 정확도 비교가 아니며
일반적인 오류율 감소를 주장할 수 없다. 모든 QA 확인은 자동화된 테스트 입력이었다.

- [API QA 원본](../artifacts/structured-requests/2026-09-09-api-smoke.json)
- API QA SHA-256: `cf404d557db63ae8ed7c078e9e50d8234fda58b17f747de1765ab2aff0b0c7d7`
- [화면 검증 기록](reports/2026-09-09_structured_requests/verification.md)

## 재현

프로젝트 루트에서 실행한다. 아래 스모크 명령은 새 `AUTOMATED QA` 요청과 기록을 DB에 만든다.
실제 외부 실행이나 공식 평가 결과는 만들지 않으며, 기존 출력 파일은 덮어쓰지 않는다.

```powershell
docker compose build backend agent-worker frontend
docker compose up -d --no-deps backend agent-worker frontend
docker compose exec -T backend alembic current
docker compose exec -T backend python -m pytest -q -p no:cacheprovider
.venv/Scripts/python.exe tools/smoke_structured_requests.py --generate --output artifacts/structured-requests/new-api-smoke.json
```

Ollama에 `qwen2.5:1.5b`가 준비되어 있어야 생성이 가능하다. 모델 연결 없이 계약 API만 확인하려면
`--generate`를 생략한다. 만료된 요청은 저장·재확정해야 하며, 오래된 QA 파일의 `allowed`는
당시 판정이지 현재 실행 허가가 아니다.

## 다음 단계

독립 사용자 시나리오로 확정 입력의 정확성, 입력 시간, 실수 수정 흐름, 불필요한 차단을 먼저
검증한다. 원래 요청이 모호하거나 모순될 때 사람이 어떤 값을 확정했는지 별도 검토가 필요하다.
그 결과로 구조화 계약의 적용 범위와 입력 부담을 판단한 뒤, 인증 강제 및 실제 서비스별 실행
권한·멱등성·장애 복구를 설계한다. 공식 Gate 재평가는 후보와 검토 기준을 따로 승인한 이후다.
