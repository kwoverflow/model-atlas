# 선택 인자 보존 실험과 남은 한계

검증일: 2026-09-09. Evidence Remediation 16.

## 결론

**기존 high 누락 회귀는 수정 후보 v3에서 해결됐지만, 선택 인자 보존 문제가 전반적으로 해결된 것은 아니다.**
새 요청에서는 기존 두 단계 후보 v1과 v3 모두 exact 및 제한된 기본값 동등성 50/56이었다.
v3의 사용 토큰은 v1보다 약 4.0% 많았다. 기본 어댑터, API 등록, 모델 가중치, 공식 Gate는 바꾸지 않았다.

- 기존 회귀 요청 `TFB-203`: v1은 high 누락 4/4, v3은 high 보존 4/4.
- 새 high 요청 두 개: v3은 8/8 통과.
- 새 low 요청 두 개: v3은 4/8 통과. 그중 한 요청의 네 번 반복에서 모두 low가 누락됐다.
- 새 요청 전체 성적에는 v1 대비 순개선이 없다. v3은 opt-in CLI 진단 후보로만 유지한다.

## 해결하려는 문제

공개 Tool 스키마에서 `priority`가 선택 사항이라는 것은 사용자가 명시한 값도 지워도 된다는 뜻이 아니다.
기존 두 단계 후보는 Tool을 올바르게 고른 뒤 인자를 다시 생성하면서 명시한 high를 생략했다.
로컬 티켓 핸들러는 생략된 priority에 normal을 적용하므로 이는 단순 표기 차이가 아니라 요청과 다른 효과다.

[직전 단계의 평가 기준](tool_default_semantics.md)을 그대로 사용했다. exact는 전체 Tool/인자 객체의 일치이며,
제한된 기본값 동등성은 로컬 `create_ticket`의 priority 생략과 normal만 동등하게 인정한다.
high/low 누락, query 변경, 잘못된 Tool과 문서 ID는 여전히 실패다.

## 두 가지 시도

### v2: 프롬프트와 선택 인자 목록 강화

선택 인자가 있는 Tool의 두 번째 요청에 값 보존 규칙과 선택 인자 목록을 추가했다.
첫 번째 요청, 공개 스키마, 필수 인자만 있는 Tool의 두 번째 요청은 유지했다.
기존 high 회귀는 네 번 모두 남았다. 이 실패는 삭제하거나 v3 결과로 덮어쓰지 않았다.

### v3: 값 또는 생략을 명시하는 응답 형식

v3은 모델 응답 전용 스키마에서 모든 필드를 필수로 만든다. 공개 Tool의 선택 인자만 null을 허용한다.
모델은 요청된 값 또는 생략 표시 null 중 하나를 명시적으로 출력해야 한다.
실제 Tool의 공개 스키마, 핸들러 기본값, 실행 가드는 바꾸지 않았다.

```text
원래 요청 + 공개 Tool 목록
  -> 기존 1단계: Tool 선택
  -> 선택된 Tool의 공개 스키마 + 원래 요청
  -> v3 모델 응답: 모든 필드에 값 또는 허용된 null
  -> 디코더: 선택 인자의 null만 생략, 나머지 값은 그대로 복사
  -> 기존 Tool 호출 가드
  -> 로컬 장애 모의 실행 및 사후 평가
```

```json
{"query": "Rotate audit credentials", "priority": "high"}
```

위 응답은 high를 그대로 전달한다. 반면 모델이 priority를 null로 출력하면 실행 인자에서 priority를 생략한다.
평가용 정답이나 원래 요청에서 값을 추출해 채워 넣지 않는다. 원시 응답, 생략 필드, 복사 필드와 최종 호출을 모두 남긴다.
필수 필드 누락, 추가 필드, 중복 JSON 키, 필수 인자의 null, 잘못된 타입은 기존 가드 또는 디코더가 차단한다.
두 번째 생성에 실패하면 1단계 인자로 자동 복구하지 않는다.

**null은 모델이 선택한 생략 표시이지 의도가 옳다는 보증이 아니다.** 실제로 새 low 사례에서 잘못된 null이 발생했다.
이 디코더는 정답 보정기나 실행 전 의도 검증기가 아니다. 현재 선택 인자 생략은 공개 스키마상 허용되므로
잘못된 null도 로컬 핸들러 실행까지 갈 수 있으며, 비교기는 이를 사후 실패로 기록한다.
nullable 응답 형식은 현재 로컬 Tool 계약 범위만 검증했다. 본래 null을 실제 값으로 받는 외부 Tool에 그대로 적용하면 안 된다.

## 실험 방법

- 런타임과 모델: 기존 Ollama 환경의 `qwen2.5:1.5b`, 기존 `operator-assistant-ko-v1` 설정. 모델/런타임 식별자를 이전 증거와 대조했다.
- 개발 집합: 이전 실험의 티켓 요청 4개. high, low, normal, 생략 각 1개다.
- 새 집합: 로컬 작성 요청 14개. 티켓 네 조건 각 2개와 다른 다섯 Tool의 요청 6개다.
- 각 집합은 Tool 목록 정순/역순, seed 42/43, 기본 방식/v1/해당 수정 후보로 비교했다.
- 후보 실행 순서를 조건마다 순환했다. temperature 0, 호출당 max_tokens 256, 케이스 시간 예산 120초, 동시성 1이다.
- v2 개발 실험 실패 후 v3을 만들었고, v3 개발 확인 후 코드를 고정한 상태로 새 집합을 실행했다. 새 결과를 보고 이번 v3을 다시 튜닝하지 않았다.
- 정답은 평가기에만 전달한다. 모델은 공개 요청과 Tool 정보만 받으며, 장애 환경과 평가 정책도 입력에 넣지 않는다.
- 요청은 독립적인 사람 검토를 받지 않았다. 56개 관측은 14개 요청의 반복이며, 독립 요청 56개나 통계적으로 확정된 일반 성능을 뜻하지 않는다.

총 264개 최종 출력, 실제 HTTP 모델 호출 440회, 세 장애 환경에서의 재생 추적 792개를 기록했다.
재생 추적은 같은 최종 출력을 재사용한 것이며 별도의 모델 생성이 아니다. 개발과 새 집합의 정확도를 합산하지 않는다.
모든 HTTP 응답은 stop으로 종료했고 런타임 오류는 없었다.

## 결과

### 개발 요청: v2와 v3은 별도 실험

| 실험 | 방식 | 관측 수 | exact | 기본값 동등성 포함 | 토큰 합계 |
| --- | --- | ---: | ---: | ---: | ---: |
| v2 개발 | 기본 | 16 | 14 | 16 | 14,385 |
| v2 개발 | v1 | 16 | 12 | 12 | 18,844 |
| v2 개발 | v2 | 16 | 12 | 12 | 21,200 |
| v3 개발 | 기본 | 16 | 14 | 16 | 14,385 |
| v3 개발 | v1 | 16 | 12 | 12 | 18,844 |
| v3 개발 | v3 | 16 | 16 | 16 | 20,228 |

v2의 지시문 강화만으로는 high 누락을 해결하지 못했다. v3의 개발 집합 통과는 이미 알고 있던 회귀에 대한 확인이다.

### 새 요청: v3은 v1과 전체 성적 동일

| 항목 | 기본 방식 | v1 | v3 |
| --- | ---: | ---: | ---: |
| 관측 수 | 56 | 56 | 56 |
| Tool 선택 일치 | 54 | 54 | 54 |
| exact | 32 | 50 | 50 |
| 기본값 동등성 포함 | 35 | 50 | 50 |
| 입력+출력 토큰 합계 | 50,804 | 67,356 | 70,062 |
| 케이스 지연 중앙값 | 0.865초 | 1.385초 | 1.387초 |

v3 토큰은 v1 대비 +4.0%, 기본 방식 대비 +37.9%다. 토큰은 캡처된 HTTP 사용량을 합산했다.
지연은 호스트 부하, 캐시, 실행 순서 등을 통제한 SLA 측정이 아니므로 차이를 성능 우위로 해석하지 않는다.

| 새 티켓 조건 | v3 exact | 해석 |
| --- | ---: | --- |
| 명시 high | 8/8 | 두 요청의 반복 조건에서 보존 |
| 명시 low | 4/8 | 한 요청은 통과, 다른 요청은 네 번 모두 누락 |
| 명시 normal | 8/8 | 명시된 기본값도 보존 |
| priority 생략 | 8/8 | 불필요한 값을 추가하지 않음 |

### 남은 실패

1. `TFB-304`: low를 명시하고 "우선순위를 생략하라는 요청이 아닙니다"라고 적은 요청에서 v1과 v3 모두 네 번 실패했다.
   v3 원시 응답에는 `priority: null`이 있으며 query는 유지된다. 부정 표현이 포함된 요청에서 생략 의도를 잘못 판정한 것으로 보이지만,
   별도의 대조 실험 없이 해당 표현만이 원인이라고 단정하지 않는다.
2. `TFB-311`: 장애 검색 요청에서 목록 정순의 두 반복 모두 문서 조회 Tool을 골랐다.
   미등록 document_id가 생성되어 기존 가드가 실행을 차단했다. 인자 생성만 바꾼 v3은 1단계 Tool 선택 오류를 해결하지 않는다.

v3의 새 집합 null 생략은 총 12회다. 요청된 생략 8회와 잘못된 low 생략 4회가 포함된다.
필수 인자만 있는 Tool의 24개 비교 조건에서는 v1/v3의 실제 2단계 HTTP 요청 본문이 같았다.
동일한 입력/seed라도 재생성된 모델 출력이 항상 같다는 보장은 하지 않는다.

## 코드와 증거 구조

| 파일 | 책임 |
| --- | --- |
| `backend/app/services/inference_adapters/presence_aware_tool.py` | 실패한 v2의 프롬프트 전용 변경, 재현을 위해 보존 |
| `backend/app/services/inference_adapters/nullable_presence_tool.py` | v3 응답 전용 스키마, 엄격한 디코딩, 두 단계 생성 |
| `backend/app/reference_workload/tool_presence_diagnostic.py` | 버전 선택 CLI, 기존 증거/런타임 검증, 실제 HTTP 캡처, 장애 재생, 평가 |
| `reference_workload/diagnostics/tool-presence-fresh-v1.json` | 실행 전에 고정한 새 요청 및 평가용 정답 |
| `backend/tests/test_presence_aware_tool.py` | 값 보존/무보정, 비공개 정답 비의존, 오류 차단, 요청 캡처와 회귀 테스트 |
| `tools/review_tool_presence.py` | 애플리케이션 평가기를 호출하지 않는 별도 재계산 및 노트북 생성 |

기존 구현과 각 실험 당시 소스 해시를 검증한다. v2 이후 활성 실행기에 v3 선택 기능을 추가하기 전에
v2 당시 실행기를 바이트 그대로 보관했다. 이전 v2 증거는 현재 파일 대신 해당 해시의 보관본과 대조한다.
보관본은 실행하거나 수정하지 않는 출처 증거이며, 실제 실행 진입점은 하나다.

- 보관 경로: `reference_workload/diagnostics/source_snapshots/tool_presence_diagnostic/`
- 보관본 SHA-256: `b7d943862520ff973ac98074f6db8b0cf920749cb22a445ceefd29c69dd58c28`

| 원시 결과 | SHA-256 |
| --- | --- |
| `artifacts/reference-workload/tool-presence-development-v2.json` | `a314ae6f3d8061e3f033356a0aa5e7a10ace0d2ea4148a603bdea5c668983f2d` |
| `artifacts/reference-workload/tool-presence-development-v3.json` | `ae831f9c65194d7cbe758ecc2614c19266d02f430943dcd01bf5af0142d752ac` |
| `artifacts/reference-workload/tool-presence-fresh-v3.json` | `c7d745ad01978de0ce70d8f88b20e5a383e599bfa0367a04fef291943214241a` |

각 결과 옆의 `.observations.jsonl`은 실행 중 쌓인 관측 기록이다. 결과 파일과 내용/해시를 대조한다.
별도 검증기는 조건별 분모, 원시 출력, exact/기본값 동등성, HTTP 본문/사용량, null 생략 내역, 실행 인자의 일치를 재검산한다.
후보의 최종 `raw_output`은 조립된 호출 객체다. 네이티브 2단계 모델 응답은 별도 메타데이터와 HTTP 캡처에 있으므로 혼동하지 않는다.

실행한 [검증 노트북](reports/2026-09-09_tool_presence/reproduce.ipynb)과
[재계산 결과](reports/2026-09-09_tool_presence/audit.json)를 함께 제공한다.

## 재검증

프로젝트 루트의 PowerShell에서 저장된 증거만 검증한다. 모델을 재호출하거나 DB를 변경하지 않는다.

```powershell
py -3.12 tools/review_tool_presence.py --notebook
.venv/Scripts/python.exe -m ruff check tools/review_tool_presence.py
```

노트북 실행에는 Python 3.12와 nbformat, nbclient, ipykernel이 필요하다. 이번에는 해당 패키지가 있는 시스템 Python을 사용했다.
Windows ZMQ 이벤트 루프 호환 경고가 발생했지만 모든 셀은 정상 실행됐다.

새 모델 실행은 backend 디렉터리에서 기존 결과와 다른 출력 경로를 지정한다.
기존 출력이나 journal이 존재하면 실행기가 거부한다. 아래 재실행은 새 요청 집합을 다시 사용하므로 새로운 holdout 평가가 아니다.

```powershell
../.venv/Scripts/python.exe -m app.reference_workload.tool_presence_diagnostic --repository-root .. --cohort fresh --candidate v3 --output ../artifacts/reference-workload/tool-presence-fresh-v3-rerun-01.json
../.venv/Scripts/python.exe -m pytest tests/test_presence_aware_tool.py -q -p no:cacheprovider
../.venv/Scripts/python.exe -m pytest -q -p no:cacheprovider
../.venv/Scripts/python.exe -m ruff check app tests
```

저장된 세 실험을 위한 노트북은 위 재실행 파일을 자동으로 포함하지 않는다. 추가 보고서에는 새로운 출처와 분모를 명시해야 한다.

## 최종 검증과 적용 범위

- 새 집중 테스트 28개 통과, 호스트 전체 450개 통과/1개 건너뜀, Docker 전체 451개 통과.
- 호스트와 Docker의 app/tests Ruff, 별도 감사 스크립트 Ruff 통과. 기존 라이브러리 deprecation 경고는 남아 있다.
- backend/agent-worker 이미지를 다시 빌드하고 재시작했다. backend와 Ollama 정상 상태, frontend와 worker 실행 상태를 확인했다.
- Alembic `202608040001 (head)`. 데이터베이스 스키마 변경은 없다.
- 최종 1.0.4 원본 검증: 64/64 승인, critical 20/20. 코퍼스 14개 파일의 해시와 기존 승인 기록을 유지했다.
- 공식 API 상태: `BLOCKED`, critical 실패 110, 실제 런타임 결과 384, 결과 검토 0/30, `not_production_ready`.

진단 실행은 애플리케이션 DB에 결과를 추가하지 않는다. 코드가 Docker 이미지에 포함되더라도 기본 API 어댑터에는 등록하지 않았으며,
이 실험을 공식 Gate 통과 근거로 승격하지 않았다. 실제 콘텐츠 정확성, 외부 Tool 권한, 운영 안전성은 별도 검증이 필요하다.

## 다음 단계

우선순위는 부정 표현과 명시적 생략 의도를 구분하는 요청 제약 검증이다. 이번 low 실패는 개발용 회귀로 고정하고,
명시 값 보존, 실제 생략 요청, 부정/인용/상충 지시를 분리한 새 요청으로 별도 후보를 평가한다.
실행 전 차단을 도입한다면 사후 평가 정답에 의존하지 않는 별도 계약과 검증 근거가 필요하다.
Tool 선택 오류는 인자 보존 문제와 별도로 다룬다. 두 항목 모두 새 증거를 얻기 전에는 기본 적용하지 않는다.
