# Query 문자 차이 표시

작성일: 2026-09-10. 범위: 제출된 입력 검증 결과의 읽기 전용 UI 개선.

## 변경

[입력 파일럿](../participant_pilot.md)의 SRC-03은 공백 하나 때문에 불일치했지만,
기존 JSON 표시만으로는 차이를 찾기 어려웠다. 제출 후 query 불일치 결과에 두 문자열의
추가/누락 문자 강조, 코드 포인트 수, 일반 공백 수, 비가시 문자 기호를 추가했다.

- `RequestInputStudy.tsx`: 제출 시각·저장 입력·결과의 query 불일치가 있을 때만 표시.
- `RequestQueryDiff.tsx`: 기준/제출값 비교, 밑줄·배경 강조, 위치/코드 포인트 title,
  화면 읽기 프로그램용 문자 설명. 넓은 화면은 2열, 작은 화면은 1열이다.
- `requestTextDiff.ts`: 원문에 대한 차이 계산과 공백·제어문자 표시를 분리한 순수 함수.
- `requestTextDiff.test.mjs`: Node 기본 테스트 러너 기반 회귀 검사.
- `package.json` / lock: 런타임 의존성 `diff` 9.0.0 고정, 테스트 명령 추가.

문자 차이 계산은 [jsdiff의 diffChars](https://github.com/kpdecker/jsdiff#api)를 사용한다.
비교 단위는 유니코드 코드 포인트이며 공백·대소문자·정규화 차이를 무시하지 않는다.
원본 문자열은 그대로 보존하고, 표시는 별도 토큰으로 변환한다. 원문은 React 텍스트로
렌더링하며 HTML로 해석하는 API를 사용하지 않는다.

SP/TAB/LF/CR/NBSP를 별도 표시하고, 다른 공백·제어·포맷·기본 비가시 코드 포인트는
U+ 코드로 표시한다. LF/CR은 비교 영역에서 실제 줄 이동 대신 표시 기호를 사용한다.
일반 공백 수는 U+0020만 센다. 다른 종류의 공백을 일반 공백으로 합산하지 않는다.

백엔드, API 입력, DB, 시나리오 팩, 채점, 다운로드 원문, 공식 증거는 수정하지 않았다.
추가/누락 개수는 표시용 문자열 편집량이며 모델 토큰 수나 의미 오류 개수가 아니다.
코드 포인트 수는 사용자에게 보이는 글자 묶음(grapheme) 수와 다를 수 있다.
반복 문자에는 여러 정렬이 가능하며, 강조 위치는 비교 라이브러리가 선택한 정렬이다.

## 검증 결과

| 검사 | 결과 |
| --- | --- |
| `npm.cmd run test:request-diff` | 20개 통과 |
| `npm.cmd run lint` | 통과 |
| `npm.cmd run typecheck` | 통과 |
| `docker compose build frontend` | 통과, TypeScript 포함 |
| 관련 Docker 백엔드 검사 | 85개 통과, 기존 의존성 경고 2개 |
| `docker compose up -d --no-deps frontend` | 완료 |
| 기존 SRC-03 및 공식 Gate 전후 비교 | JSON 값 동일 |

20개 테스트는 동일/빈 문자열, 추가/삭제/치환, 앞뒤 공백, 실제 중복 공백, 탭, CRLF,
NBSP, 영폭 문자, 보조 평면 코드 포인트, 정규화·대소문자 차이, 1,000자 입력을 포함한다.
그중 하나는 4,096개 짧은 문자열 쌍의 원문 복원과 동일 문자 정렬을 확인한다.
이 테스트 수는 백엔드 시나리오 정확도나 참여자 수가 아니다.
호스트 Node 22.14.0에서 타입 제거의 experimental/module-type 경고가 있었지만 검사는 통과했다.

### 실제 화면

기존 기록을 조회하는 방식으로 검사했으며 새 입력·제출·참여자 기록을 생성하지 않았다.

- SRC-03 `21866481-0f30-43f3-95d9-c6c9e7ffc228`:
  기준 8 코드 포인트/공백 2개, 제출 9 코드 포인트/공백 3개.
  추가 1개/누락 0개, `4번째 · U+0020 · SP · 추가` 강조를 확인했다.
- 제출된 일치 기록: query 비교 영역 없음.
- 시작만 한 미제출 기록: 비교 영역과 기준 입력 모두 없음.
- 우선순위만 불일치한 자동 QA 기록: query 비교 영역 없음.
- 1440x1000 및 390x844에서 화면을 확인했다. 페이지 scrollWidth/clientWidth는 각각
  1440/1440, 390/390이었다. 비교 영역도 각각 550/550, 356/356으로 가로 넘침이 없었다.
- 모바일의 기존 기록 표는 별도 가로 스크롤을 유지한다. 차이 표시는 세로로 배치된다.

[데스크톱](desktop.png) · [모바일](mobile.png)

최종 원본 재조회에서 SRC-03의 입력·해시·불일치 판정·제출 시각·10.944초 기록·수정 횟수는
변경 전과 동일했다. 공식 Gate도 BLOCKED / 110 critical failures / 384 runtime results /
출력 검토 0/30 / not_production_ready로 동일했다.

### 별도 유지보수 항목

설치/빌드의 npm audit에서 기존 Next.js의 critical 및 다른 의존성 경고를 확인했다.
새 `diff` 의존성은 확인한 audit 취약 패키지 목록에 없었지만, 이는 프로젝트 전체의
보안 안전성을 뜻하지 않는다. 이번 작은 UI 개선에서 Next.js 등 기존 프레임워크를 일괄
업그레이드하거나 `npm audit fix --force`를 실행하지 않았다. 별도 보안 패치와 회귀 검증이 필요하다.

이번 턴에는 백엔드 전체 570개 검사를 재실행하지 않았다. 백엔드 변경은 없으며 관련 85개를
재실행했다. 실제 스크린리더·다른 브라우저군의 수동 검증은 하지 않았다. 문자 비교 자체의
효과를 검증하는 추가 참여자 실험도 아직 없다.

## 재현

`frontend/`에서:

```powershell
npm.cmd ci
npm.cmd run test:request-diff
npm.cmd run lint
npm.cmd run typecheck
```

프로젝트 루트에서:

```powershell
docker compose exec -T backend python -m pytest -q tests/test_request_scenarios.py tests/test_structured_requests.py tests/test_model_module_compatibility.py
docker compose build frontend
docker compose up -d --no-deps frontend
```

[화면](http://localhost:3000/structured-requests/validation)의 입력 검증 탭에서
기준 불일치인 기존 SRC-03 기록을 열면 추가 공백을 확인할 수 있다. 새로 시험하거나
기존 결과를 수정할 필요는 없다.
