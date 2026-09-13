# 실제 요청 흐름 검증 구현 보고서

작성일: 2026-09-10. Evidence Remediation 20.

## 결론

새 로컬 과제 10개를 기존 요청 계약 화면과 연결하고, 수행 이력·모델/수동 제안·실행·도움 여부·중단을
분리해 수집하는 기능을 구현했다. Docker에 반영했고 브라우저에서 실제 로컬 모델 제안 생성부터
모의 실행과 제출까지 확인했다. **사람의 독립 사용성 검증은 아직 수행하지 않았다.**

공식 상태는 `BLOCKED / critical failures 110 / runtime results 384 / output review 0/30 /
not_production_ready`로 동일하다. 입력 연습·워크플로 과제·공식 모델 출력 검토는 서로 별개다.

## 구현 내용

- `/structured-requests/workflow`: 새 과제 10개, 출처 선택, 과제별 재접속, 실제 계약 화면, 종료·피드백,
  결과·문자 차이·JSON 내보내기, 출처/도움 여부/팩 해시별 전체 집계와 수행 기록 페이지 이동.
- 기존 `StructuredRequestLab`을 재사용한다. 원래 요청은 과제 화면에서 읽기 전용이고 query와
  우선순위를 자동 완성하지 않는다. 과제 키는 생성·실행 경로에 제공하지 않는다.
- 하나의 실제 계약을 과제에 연결하며 생성과 연결을 단일 트랜잭션으로 처리한다.
- 과제 버전과 계약 전체 상태 해시로 종료를 바인딩한다. 제안 추가·실행 뒤 오래된 확인 요청은 차단한다.
- 종료 시 모든 제안·실행을 고정한다. 기존 요청 화면의 최신 20개 조회 제한을 증거 스냅샷에 적용하지 않는다.
- 처음 잘못 실행한 뒤 수정하여 성공하더라도 과거 실행 오류를 지우지 않는다.
- 기존 입력 판정 기준·모델 어댑터·공식 Gate 정책·외부 실행 권한은 변경하지 않는다.

새 테이블은 `request_workflow_attempts` 하나, Alembic head는 `202609100002`다.
기존 47개 테이블의 고정 메타데이터 해시는 그대로이며 총 테이블은 실험 테이블 5개를 포함해 52개다.

## 검증 결과

| 검사 | 관찰 결과 |
| --- | --- |
| 새 워크플로 백엔드 검사 | 30 passed |
| 최종 Docker 전체 백엔드 검사 | 600 passed, 기존 의존성 경고 2 |
| 내보내기 검증 도구 검사 | 9 passed |
| 프런트 테스트 | 29 passed, 호스트 및 Docker 빌더 |
| TypeScript | 통과 |
| 프런트 lint | 전체 검사 오류 0·기존 경고 4, 마지막 변경 파일 검사 오류·경고 0 |
| backend Ruff 및 새 CLI Ruff | 통과 |
| Docker backend/frontend build | 통과, 재배포 완료 |
| PostgreSQL migration | `202609100002 (head)` |
| 실제 API 검사 | 12개 자동 QA 시도에서 예상 관찰 모두 확인 |
| 브라우저 검사 | 자동 QA 3개, 데스크톱·모바일·다운로드·재접속 확인 |
| 기존 진단 증거 감사 | `diagnostic_only_with_false_block_and_false_allow_caveats` 유지 |

최초 전체 회귀 검사에서 새 모델의 호환성 export 누락과 추가 테이블 목록 누락으로 2개가 실패했다.
호환성 모듈과 실험 테이블 목록을 보완했으며, 기존 메타데이터 기대 해시는 변경하지 않았다.
이후 598개가 통과했고 내보내기 회귀 검사 2개를 추가한 최종 검사에서는 600개가 통과했다.

호스트 시험의 `.pytest_cache` 권한 경고는 이후 `-p no:cacheprovider`로 캐시 쓰기 없이 실행했다.
원격 GitHub Actions는 실행하지 않았다. 기존 네 내부 페이지 이동 lint 경고와 외부 OIDC 실계정
재검증은 이번 범위에 포함하지 않았다.

새 내보내기 검증 도구의 lint와 9개 테스트도 기존 backend CI job에 연결했다.

## 자동 QA와 실제 모델 호출의 구분

API QA는 실제 PostgreSQL과 계약 서비스를 사용하지만 **합성 제안만** 입력했다.
과제 10개는 기준과 일치하고, 별도 오확정 1개는 불일치, 중단 1개는 중단으로 관찰했다.
이는 모델이 과제 10개를 맞혔다는 결과가 아니다.

브라우저 QA:

| 과제·시도 | 결과 | 제안 출처 |
| --- | --- | --- |
| WF-01 / `088d33f2-e225-4dd5-880b-44f95e6b07b8` | 기준 일치, 모의 실행 1회 | 실제 로컬 모델 제안 1개 |
| WF-09 / `5ff7add2-2448-4324-9018-a51071291844` | 추가 확인 요청, 계약·실행 없음 | 제안 없음 |
| WF-05 / `07d4fc34-ac73-4aee-be7c-731c63e7c4d8` | 의도적인 공백 누락·오확정, 불일치 보존 | 합성 수동 제안 1개 |

WF-01의 첫 생성은 Ollama가 꺼져 있어 실패했다. 기존 runtime 프로필 서비스를 시작하고 이미
저장된 `qwen2.5:1.5b`를 사용해 재시도했다. 새 모델 다운로드나 가중치 변경은 없었다.
성공한 제안 하나의 생성 기록에는 HTTP 요청 본문 2개가 있다. 실패한 첫 시도는 제안 개수에
포함되지 않으며 메모와 본 보고서에 별도로 보존했다. 이 표는 안정성·정확도 측정이 아니다.

총 15개 워크플로 시도는 모두 `automated_qa`다. 기준 일치 12, 의도적 불일치 2, 중단 1,
진행 중 0이며 참가자 기록은 0이다. WF-05 도움 버튼 클릭도 자동 조작이며 사람의 도움 요청이 아니다.
기존 입력 연습의 자가 보고 결과는 이 집계에 포함하지 않는다.

## 화면 검사

데스크톱 1440×1000, 모바일 390×844에서 확인했다. 페이지 수준 가로 넘침은 없었고,
모바일 표는 자체 가로 스크롤을 유지했다. 최종 문자 차이 영역은 client/scroll width가 모두 358px였다.

입력 수정 시 확정 체크 해제, 미저장 초안 및 미검증 JSON의 종료 차단, 종료 확인 전 제출 비활성화,
재저장 횟수, 도움 카운터, 모델 생성·모의 실행, 추가 확인 요청, 재접속, JSON 파일 다운로드를 확인했다.
모바일 WF-05는 두 공백을 한 공백으로 바꾼 오류를 그대로 남기고 누락 문자 1개로 표시했다.

- [데스크톱 결과](desktop-result.png)
- [모바일 과제 목록](mobile-catalog.png)
- [모바일 문자 차이 결과](mobile-query-diff-top.png)

스크롤 중 전체 페이지 캡처에서는 고정 모바일 헤더가 중간에 잡히는 캡처 특성이 있었다.
최종 공유 캡처는 맨 위로 이동한 뒤 다시 촬영했다. 초기 캡처를 근거로 레이아웃 통과를 판단하지 않았다.

## 내보내기 해시 보완

초기 브라우저 다운로드를 재계산하자 숫자 `0.0 → 0` 직렬화 때문에 해시가 일치하지 않았다.
브라우저 파일의 값만 다시 JSON으로 만드는 방식은 서버의 원래 해시 바이트를 보존하지 못했다.

수정 후 조회 API가 저장된 결과에서 `evidence.canonical_json`과 그 해시 검증 결과를 함께 제공한다.
**기존 DB의 제출 결과·시각·해시는 수정하지 않았다.** canonical 문자열의 UTF-8 해시를 계산하고,
표시 결과·시도 ID·출처가 그 문자열과 같은지도 별도 CLI에서 검사한다. 숫자 0과 0.0은 동등하게
보되 false와 0은 구분한다. 이것은 콘텐츠 무결성 검사이며 서명·실명·독립성 검증이 아니다.

최종 API에서 15개 제출 기록의 기존 해시가 모두 검증됐다. WF-01을 브라우저에서 다시 다운로드한
`request-workflow-088d33f2-e225-4dd5-880b-44f95e6b07b8 (1).json`도 실제 CLI 검증을 통과했다.
해시는 처음 제출한 `ad12f52b37075bec9717f8cbdde72ded46d66e18f8e2c71c5ee8c69ddc15ec6a`와 같다.

보고서용 묶음을 만드는 중 PowerShell 객체 변환이 날짜 문자열 표현까지 변경하는 문제도
동일 검증 도구가 찾아냈다. 최종 묶음은 HTTP JSON 원문에서 날짜를 문자열로 유지해 다시
생성했으며 3개 기록 모두 CLI 검증을 통과했다. DB 제출 기록은 변경하지 않았다.

초기 `2026-09-10-browser-qa.json`과 API QA 보고서는 당시 형식을 남긴 기록이다.
최종 공유·해시 검증에는 [canonical 포함 브라우저 증거](../../../artifacts/request-workflows/2026-09-10-browser-qa-canonical.json)를 사용한다.

## 기존 데이터 보존

기존 입력 연습 15건과 요청 계약 4건의 API 응답 해시가 모두 이전과 같았다.
자동 QA용 계약 11개가 새로 추가됐고, 공식 Gate/실패/리뷰/준비 상태는 동일했다.
이는 해당 API-visible 레코드 비교이며 전체 DB에 대한 포렌식 비교라는 뜻은 아니다.

- [변경 전 상태](../../../artifacts/request-workflows/2026-09-10-state-before.json)
- [변경 후 상태](../../../artifacts/request-workflows/2026-09-10-state-after.json)
- [상태 대조](../../../artifacts/request-workflows/2026-09-10-state-comparison.json)
- [실제 API QA](../../../artifacts/request-workflows/2026-09-10-api-qa.json)

백엔드·프런트엔드를 재배포하고 Ollama를 실행했다. DB 볼륨과 기존 worker는 유지했다.
프런트 의존성은 직전 보안 패치 버전을 유지했다. 원본 코퍼스·과거 추론/진단 소스는 편집하지 않았다.

## 재현 명령

프로젝트 루트에서 실행한다. API QA 재실행은 별도의 자동 QA 시도와 계약을 추가한다.

```powershell
docker compose --profile runtime up -d db backend frontend ollama
docker compose run --rm --no-deps backend pytest -q
docker compose exec -T backend ruff check app tests
.venv/Scripts/python.exe -m pytest tools/test_verify_request_workflow_export.py -q -p no:cacheprovider
.venv/Scripts/python.exe tools/smoke_request_workflows.py --output artifacts/request-workflows/new-api-qa.json
.venv/Scripts/python.exe tools/verify_request_workflow_export.py artifacts/request-workflows/2026-09-10-browser-qa-canonical.json
```

API QA 출력 파일이 이미 있으면 덮어쓰지 않고 실패한다. 단순 확인만 필요하면 검증 도구 명령을 쓴다.

## 남은 판단

잘못 확정한 입력을 제안이 그대로 따라가면 실행될 수 있다는 기존 한계는 그대로다.
이번 결과 화면은 이를 사후에 드러내지만 일반적인 의미 해석 안전장치를 구현한 것은 아니다.
연결된 계약은 다른 일반 계약 화면에서 이후 수정할 수 있고, 제출 결과는 종료 시점만 대표한다.

이제 참여자가 과제를 직접 수행한 관찰이 필요하다. 확인 부담과 중단 원인을 정리한 다음,
기존 공식 실패 그룹의 개선 후보와 실제 모델 출력 검토를 진행한다. 외부 실제 실행이나 Gate 승격은 하지 않았다.

[참여자 사용·기술 안내](../../request_workflow_validation.md)
