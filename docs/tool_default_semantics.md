# 명시 인자 보존과 로컬 기본값 동등성

검증일: 2026-09-09. Evidence Remediation 15.

## 결론

**평가 기준을 분리했으며, 새 요청에서는 분리형 후보를 기본 방식보다 우수하다고 판단할 근거를 얻지 못했다.**
명시 인자 exact는 기본 46/56, 후보 48/56이지만, 확인된 기본값 차이를 인정하면 둘 다 48/56이다.
후보의 사용 토큰은 34.7% 더 많았다. 또한 `high`를 명시한 한 요청의 네 번 실행에서 후보가 모두 priority를 생략했다.
프롬프트·모델·기본 어댑터·공식 Gate는 변경하지 않았고, 후보는 진단용으로만 유지한다.

## 분리한 기준

| 지표 | 의미 |
| --- | --- |
| `exact_call` | 선택 Tool과 전체 인자 객체가 평가용 정답과 정확히 일치한다. 명시된 인자의 생략과 불필요한 인자 추가도 실패다. |
| `default_equivalent_call` | 정확히 일치하거나, 검증한 로컬 기본값 차이만 존재한다. 현재 허용하는 차이는 `create_ticket.priority` 생략과 `normal`뿐이다. |
| `default_only_difference` | exact는 실패하지만 위의 제한된 기본값 동등성은 통과한다. 원래 실패를 숨기지 않고 따로 표시한다. |
| `execution_eligible` | 기존 공개 스키마와 문서 ID 가드를 통과한다. 요청 의도까지 충족했다는 뜻은 아니다. |

`default_equivalent_call`은 **일반적인 의미 정확도 지표가 아니다.** 다른 query, 대소문자나 공백 변경,
잘못 선택한 Tool, 알 수 없는 문서 ID, 추가 필드, 잘못된 형식을 동등하다고 인정하지 않는다.
`high` 또는 `low`를 요청했는데 생략한 경우도 실패다.

```text
expected: {query: "a", priority: "normal"}
actual:   {query: "a"}
-> exact=false, default_equivalent=true

expected: {query: "a", priority: "high"}
actual:   {query: "a"}
-> exact=false, default_equivalent=false
```

비교에 쓰는 사본에만 기본값을 투영하고 해시를 비교한다. 모델 출력, 저장된 실제 인자, 실행기에 전달한 인자는 채우거나 고치지 않는다.
평가 정책과 정답은 모델 입력에 추가하지 않는다. 선택된 Tool 생성 프롬프트도 그대로 유지했다.

### 정책 범위

- 버전: `local-tool-default-equivalence-v1`.
- 대상: `create_ticket-fault-fixture-v1` 로컬 모의 핸들러의 선택 인자 `priority`.
- 구현 파일 SHA-256, 핸들러 함수, Tool 버전, 선택 인자 스키마를 확인한다. 변경되면 정책 검토 전 비교를 거부한다.
- 실제 핸들러에 생략/normal/high를 전달하는 테스트로 기본값 가정을 확인했다. 외부 티켓 서비스에는 이 가정을 적용하지 않는다.
- 전체 핸들러 파일 해시를 고정했으므로 관련 없는 핸들러 편집도 정책 재검토를 요구할 수 있다. 자동으로 새 구현에 가정을 이식하지 않기 위한 보수적 제한이다.

**이 비교기는 사후 평가기이며, 실시간 의미 검증이나 실행 차단 장치가 아니다.**
`priority`는 공개 스키마상 선택 인자이므로, high 누락도 형식 검증을 통과한다.
이번에는 모의 도구가 실제로 기본값 normal을 적용했고 비교기가 이를 요청과 다른 값으로 판정했다.
실제 외부 도구에 연결하기 전에 별도의 요청 제약 보존과 권한 검증이 필요하다.

## 새 요청 비교

실제 생성: 2026-09-09 07:22:59~07:25:52 UTC, 한국·일본 시간 16:22:59~16:25:52.
Ollama 0.31.1, `qwen2.5:1.5b` Q4_K_M, `operator-assistant-ko-v1`.
모델 digest, 런타임 메타데이터, 기존 구현 11개 파일을 이전 증거와 대조했다.

- 새 요청 14개: 티켓 기본값 명시·생략·high·low 각 1개, 나머지 다섯 Tool은 각 2개.
- Tool 목록 정순·역순 x seed 42·43 x 기본·후보 = 최종 출력 112개, 방식당 56개.
- 실제 HTTP 생성 호출은 168회다. 기본 56회, 두 단계 후보 112회이며 모든 응답은 `stop`으로 종료했다.
- 최종 출력을 세 장애 환경에서 재사용한 추적은 336개다. 독립 모델 생성 336개가 아니다.
- 기본/후보 순서를 AB/BA로 교대했다. temperature 0, 호출당 max_tokens 256, 케이스 시간 예산 120초, 동시성 1이다.
- 새 요청과 평가 정책을 모델 실행 전에 고정했다. 요청은 로컬에서 작성했고 사람의 독립 검토를 받지 않았으므로 독립 holdout으로 주장하지 않는다.
- 14개 요청을 반복한 관측이지 독립 요청 112개가 아니다. 특히 high 실패 네 건은 한 요청의 두 순서·두 seed 반복이다.

| 항목 | 기본 방식 | 분리형 후보 |
| --- | ---: | ---: |
| 관측 수 | 56 | 56 |
| Tool 선택 일치 | 52 | 52 |
| 엄격한 인자 exact | 46 | 48 |
| 제한된 기본값 동등성 포함 | 48 | 48 |
| 기본값 차이만 존재 | 2 | 0 |
| 정상 모의 도구 성공 | 52 | 52 |
| 입력+출력 토큰 합계 | 50,368 | 67,851 |
| 케이스 지연 중앙값 | 0.833초 | 1.299초 |

토큰은 HTTP 응답의 실측 사용량을 합산했다. 지연은 캐시·실행 순서·호스트 영향을 통제한 SLA 실험이 아니다.
이전 12개 요청 실험의 지연이나 정확도와 직접 증감 비교하지 않는다. 요청 집합이 달라졌다.

### 개선과 회귀

- 기본 방식은 인자 생략을 요청한 `TFB-202`의 역순 조건에서 normal을 명시했다. exact는 2회 실패하지만 로컬 기본값 기준으로는 동등하다.
- 후보는 대화 query를 바꾼 기본 방식의 `TFB-213` 오류 4회를 해결했다.
- 반면 후보는 `TFB-203`에서 명시한 high를 4회 모두 생략했다. 기본 방식과 후보의 1단계에서는 네 번 모두 high를 보존했다.
- 후보 내부 1단계 대비 exact는 6회 개선/4회 회귀, 기본값 동등성은 4회 개선/4회 회귀다. 제한된 동등성 기준의 순개선은 0회다.
- 기본/후보 56쌍의 1단계 HTTP 본문이 모두 같았고 선택 Tool의 변화는 0건이었다. 장애 검색 요청의 Tool 선택 오류 네 건은 양쪽 모두 남았다.
- 후보는 그 네 건에서 잘못 선택한 문서 조회에 미등록 document_id를 생성했고, 기존 문서 가드가 실행 전에 차단했다.

정상 모의 도구 성공 52/56을 의도 충족률로 해석해서는 안 된다. 후보의 high 누락처럼 형식은 맞지만
요청과 다른 효과를 내는 호출이 포함된다. 후보의 스키마 통과율은 조립된 호출 객체 기준이며 네이티브 모델 출력 형식 준수율과도 다르다.

## 과거 결과의 별도 해석

이전 `tool-two-stage-diagnostic-v1.json`의 144개 최종 출력은 새 모델 호출 없이 읽기 전용으로 다시 비교했다.
결과는 새 파일의 `historical_addendum`에만 저장했다. 이전 원본·저널·exact 점수·해시는 변경하지 않았다.

이전 새 요청의 1.5B/v1·v2 후보는 여전히 exact 9/12다. 생략한 normal을 인정하는 별도 지표는 각각 11/12다.
이는 **사후 추가 분석**이지 새 성능 증거도, 기존 점수를 11/12로 교체한 것도 아니다.
새 요청 실험의 48/56과 분모를 합치지 않는다.

## 코드와 재현

| 파일 | 책임 |
| --- | --- |
| `backend/app/reference_workload/tool_argument_equivalence.py` | 버전 고정 기본값 정책, 비변경 비교, 원본·비교용 해시와 사유 기록 |
| `backend/app/reference_workload/tool_default_semantics_diagnostic.py` | 기존 증거 검증, 사후 부록, 새 요청 쌍 비교, 중간 JSONL 보존 |
| `backend/tests/test_tool_argument_equivalence.py` | 기본값/비기본값/잘못된 입력/실행 인자 보존/정책 변경/출력 보호 테스트 |
| `reference_workload/diagnostics/tool-default-semantics-v1.json` | 모델 호출 전에 고정한 로컬 요청 14개 |
| `tools/review_tool_default_semantics.py` | 앱 평가기를 가져오지 않는 독립 재계산과 노트북 생성 |

저장소 루트에서 저장된 결과만 검증한다. 이 명령은 모델이나 애플리케이션 DB를 사용하지 않는다.

```powershell
.venv/Scripts/python.exe tools/review_tool_default_semantics.py
py -3.12 tools/review_tool_default_semantics.py --notebook
```

노트북 옵션은 nbformat/nbclient/ipykernel이 있는 시스템 Python 3.12를 사용한다.
일반 감사 모드는 표준 라이브러리만 필요하다. 현재 감사기는 문서화된 v1 증거에 고정되어 있다.

실제 추론을 다시 실행하려면 Ollama를 켜고 `backend`에서 새 경로를 지정한다.

```powershell
../.venv/Scripts/python.exe -m app.reference_workload.tool_default_semantics_diagnostic --repository-root .. --output ../artifacts/reference-workload/tool-default-semantics-rerun.json
```

기존 출력 또는 저널이 있으면 실행 전에 거부한다. 비교 중 오류가 발생해도 이미 관측한 행을 저널에 남기고 중단한다.
자동 재개는 지원하지 않는다. 다른 모델·정책·프롬프트의 실험은 새로운 버전과 별도 증거로 만들어야 한다.

- 원본: `artifacts/reference-workload/tool-default-semantics-diagnostic-v1.json`
- 원본 SHA-256: `ed5c3b2304d89e6241f7e713480798b78f068565a690498271933d8c911abd50`
- 저널 SHA-256: `13cd0c6e9647bbae31d55a95adfa3f438201962cd5c2bec16cb4aa5febb281a7`
- 실행된 노트북과 독립 감사: `docs/reports/2026-09-09_tool_default_semantics/`

## 검증과 남은 조건

새 테스트 31개 통과. 호스트 전체 422개 통과/1개 건너뜀, Docker 전체 423개 통과.
독립 감사에서 원본·소스·저널 해시, 분모·중복, 56쌍의 본문 일치, 단계별 인자 보존, 실측 토큰 합계,
새 점수와 과거 부록을 재계산했다. 노트북은 처음부터 끝까지 실행했다. 비치명적인 Windows ZMQ 경고와 기존 테스트 의존성 경고는 남아 있다.
UI 변경은 없으며 화면·차트·HTML 시각 검증을 수행했다는 주장은 하지 않는다.

백엔드/worker는 모델 측정 후 재빌드·재시작했다. Finalized 1.0.4는 64/64 승인, critical 20/20과 기존 corpus hash를 유지한다.
2026-09-09 07:31:20 UTC 공식 overview 확인 결과는 `BLOCKED`, critical failure 110건, 실제 결과 384건,
실제 출력 검토 0/30, `not_production_ready`다. 이 진단은 공식 평가나 검토 승인으로 등록하지 않았다.

다음 범위는 **단계 사이에서 명시한 우선순위가 사라지는 회귀를 해결할 별도 후보**다.
이번 실패를 개발용 회귀 사례로 고정하고, 다른 미관측 요청으로 high/low/기본값 보존을 다시 확인해야 한다.
정답으로 인자를 채우거나 이전 실패를 성공으로 덮어쓰지 않는다. 그 후 실제 문서 내용·권한·독립 검토가 확보되어야 API 통합을 검토한다.
