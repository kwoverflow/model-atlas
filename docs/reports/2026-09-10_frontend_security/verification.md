# 프런트엔드 보안 패치와 회귀 검증

작성일: 2026-09-10. 대상: Model Atlas 프런트엔드 npm 의존성, 기존 CI/Docker 검증 흐름.

## 결론

호스트와 재배포된 Docker 컨테이너에서 개발 의존성을 포함한 `npm audit`의 보고 항목이
**14개에서 0개로 감소**했다. 초기 값은 critical 1 / high 6 / moderate 7이었다.
이 숫자는 취약 패키지 항목 수이며, 서로 독립적인 취약점 14개나 실제 침해 14건을 의미하지 않는다.

기존 모델·평가·입력 판정 로직은 변경하지 않았다. 공식 상태는 여전히
`BLOCKED / critical failure 110 / runtime results 384 / output review 0/30 / not_production_ready`다.
이번 audit 통과만으로 프로젝트 전체의 보안이나 배포 적합성이 증명되는 것은 아니다.

## 변경한 의존성

| 항목 | 이전 | 이후 |
| --- | --- | --- |
| Next.js | 16.2.10 | 16.3.4 |
| eslint-config-next | 16.2.10 | 16.3.4 |
| PostCSS | 8.5.16 | 8.5.28 |
| sharp | 0.34.5 | 0.35.4 |
| nanoid | 3.3.15 | 3.3.18 |
| baseline-browser-mapping | 2.10.41 | 2.11.21 |
| brace-expansion (1.x / 5.x) | 1.1.15 / 5.0.7 | 1.1.18 / 5.0.9 |
| browserslist | 4.28.4 | 4.28.9 |
| js-yaml | 4.3.0 | 4.3.2 |

Next.js와 연동 ESLint 설정은 같은 버전으로 고정했다. 기존 PostCSS override의 구버전 중복
지정을 `$postcss` 참조로 바꿔 직접 의존성과 일치시켰다. 이후 남은 취약 간접 의존성 네 종류만
지정해 갱신했다. React·Tailwind의 메이저 전환이나 무관한 앱 코드 리팩터링은 하지 않았다.
`npm audit fix --force`도 사용하지 않았다.

Next.js의 [Windows 서버 보안 공지](https://github.com/vercel/next.js/security/advisories/GHSA-p293-qw3h-jr36)는
16.3.3 이전의 해당 버전 범위를 취약 대상으로 설명한다. 선택한
[16.3.4 릴리스](https://github.com/vercel/next.js/releases/tag/v16.3.4)는 16.3.3의 후속 패치다.
PostCSS는 [8.5.28 릴리스](https://github.com/postcss/postcss/releases/tag/8.5.28)를 사용했다.
현재 서버는 Linux 컨테이너지만 Windows 호스트 개발 경로와 다른 이미지 처리 공지도 고려해
의존성 자체를 패치했다. 어떤 공격이 실제로 성공하는지 시험한 것은 아니다.

전체 플랫폼별 sharp/SWC와 부모 패키지에 따른 부속 변경은
[의존성 변경 목록](../../../artifacts/maintenance/2026-09-10-frontend-security/dependency-changes.json)에 보존했다.
lockfile SHA-256은 호스트와 배포 컨테이너가 동일하다.

```text
f7eea74ccabfca5be8a42173311dbb3acd91ea5431df0eea9cfad20316def6f4
```

## 검증 파이프라인

- `.github/workflows/ci.yml`: 설치를 `npm ci`로 바꾸고 audit, 프런트 테스트, 빌드 단계를 추가했다.
  audit는 high 이상이면 실패한다. moderate도 보고되지만 해당 단계의 차단 임계치는 아니다.
- `frontend/Dockerfile`: 빌드 전 `npm test`를 실행하고 런타임 이미지에도 lockfile을 포함한다.
- `frontend/tests/browserApi.test.mjs`: 기존 API helper에 대한 합성 데이터 테스트 9개를 추가했다.
  실제 사용자 쿠키나 로그인 세션을 읽지 않는다.
- 요청의 credentials 포함, 쓰기 메서드의 CSRF 전달, 정확한 쿠키 이름 구분, 요청 필드 보존,
  document 없는 환경, 401 응답 전달, 네트워크 실패 전파를 검사한다.
- 기존 문자 차이 테스트 20개는 유지하며 `npm test`로 함께 실행한다.

| 검사 | 결과 |
| --- | --- |
| 호스트 `npm ci` | 성공, audit 0 |
| 호스트 `npm audit --json` | 모든 심각도 0 |
| Docker `npm audit --include=dev --json` | 모든 심각도 0 |
| 호스트 프런트 테스트 | 29 passed |
| Linux Docker 빌더 프런트 테스트 | 29 passed |
| 프런트 TypeScript | 통과 |
| 프런트 lint | 오류 0, 경고 4 |
| Docker 프런트 빌드 | 성공, Next.js 16.3.4 |
| Docker 전체 백엔드 테스트 | 570 passed, 기존 의존성 경고 2 |
| Docker 백엔드 Ruff | 통과 |
| CI YAML 파싱과 단계 확인 | 통과 |
| 이전 진단 증거 체인 audit | 통과, 기존 한계 판정 유지 |
| 확정된 1.0.4 case pack validate | ready, 승인 64/64, critical 20/20 |
| Alembic | 202609100001 (head), 변경 없음 |

CI 파일은 수정하고 동일 명령을 로컬/Docker에서 검증했지만, 원격 GitHub Actions 실행은
요청하거나 확인하지 않았다. 백엔드 Python 의존성 업데이트 및 전체 OS 이미지 취약점 스캔은
이번 npm 보안 패치 범위에 포함되지 않는다.

실제 런타임의 일반/standalone 경로에서 모두 Next.js 16.3.4를 확인했다.
sharp 0.35.4 / libvips 8.18.6에서 합성 2x2 이미지의 AVIF 인코딩·디코딩 후 PNG 변환이
성공했다(96바이트). 이는 정상 코덱 동작 검사이며 취약점 공격 재현 검사가 아니다.

## 브라우저와 데이터 보존

브라우저에서 `automated_qa` 출처로 SRC-03을 시작했다. 올바른 query/high를 먼저 저장하고,
확인 체크 후 공백 하나를 추가했다. 체크 해제와 제출 차단을 확인한 다음 재저장·확인·제출했다.
결과는 revision 2 / 수정 저장 1회 / query 불일치였고, 추가 공백 표시가 유지됐다.
새로고침 후 재열기와 JSON 다운로드도 확인했다.

새 자동 QA 기록 ID: `e672ec86-300b-4a9c-8c38-18957869e5b6`.
[저장된 API 결과](../../../artifacts/maintenance/2026-09-10-frontend-security/browser-qa-study.json).
이 기록의 21.985초는 자동화 중 대기를 포함한 경과 시간이며 사람의 사용성 측정값이 아니다.
다운로드 파일도 같은 ID/hash/source와 `gate_evidence=false`인 것을 확인했다.

- 데스크톱 1440x1000 / 모바일 390x844 시각 검사: 새 겹침이나 페이지 가로 넘침 없음.
- 모바일 비교 영역 clientWidth/scrollWidth: 356/356. 기존 기록 표의 독립 가로 스크롤은 유지.
- [데스크톱 화면](desktop.png) · [모바일 화면](mobile.png).
- `/`, `/structured-requests`, `/structured-requests/validation`, `/reference-workload`,
  `/release-decisions`, `/session-administration` 모두 HTTP 200을 확인했다.
- 공식 평가 화면에서도 실제 결과 384개, Blocked, 검토 출력 0개를 확인했다.

보안 작업 시작 시 보존한 입력 기록 14건과 요청 계약 4건을 ID별 JSON SHA-256으로 비교했다.
**기존 기록 전부 동일**하며 새로 생긴 기록은 위 자동 QA 입력 1건뿐이다.
이는 각 API에서 최대 50개까지 조회한 목록 기준이며 전체 DB의 포렌식 비교라는 뜻은 아니다.
기존 미제출 사용자 기록도 수정하거나 삭제하지 않았다.

인증 설정은 외부 OIDC 비활성, local-ui 미검증 모드였다. 브라우저의 로컬 신원 표시,
API helper 테스트, 백엔드의 OIDC/세션/인증 테스트를 확인했지만 실제 외부 제공자에 대한
로그인·로그아웃 왕복은 수행하지 않았다. 이 검증을 위해 인증을 끄거나 우회하지 않았다.

## 남은 경고

새 Next.js ESLint 규칙이 기존 내부 이동 방식 네 곳을 경고한다.
AgentApprovalControlPanel, JudgeLabelImportForm, ModelValidationConsole, ReleaseDecisionForm의
`window.location` 기반 이동이다. 보안 오류와 별개이며, 전체 재로딩이 필요한 기존 흐름인지
검토한 뒤 Router 이동 전환 여부를 판단해야 한다. 이번에는 경고를 숨기거나 동작을 바꾸지 않았다.

Node 테스트의 TypeScript 타입 제거/module-type 경고와 백엔드 기존 deprecation 경고도 남아 있다.
알려진 npm 항목 0개는 시점 의존적인 결과로, 미공개 취약점·인증 배포 설정·OS 라이브러리까지
포괄하는 안전 보장이 아니다. 모델의 공식 승인 상태도 바꾸지 않았다.

## 증거와 재현

증거 폴더: `artifacts/maintenance/2026-09-10-frontend-security/`.

- [변경 전 audit](../../../artifacts/maintenance/2026-09-10-frontend-security/audit-before.json)
- [변경 후 호스트 audit](../../../artifacts/maintenance/2026-09-10-frontend-security/audit-after-host.json)
- [변경 후 Docker audit](../../../artifacts/maintenance/2026-09-10-frontend-security/audit-after-docker.json)
- [변경 전 의존성 기준](../../../artifacts/maintenance/2026-09-10-frontend-security/dependency-baseline.json)
- [상태 비교](../../../artifacts/maintenance/2026-09-10-frontend-security/state-comparison.json)
- [이전 상태](../../../artifacts/maintenance/2026-09-10-frontend-security/state-before.json) /
  [이후 상태](../../../artifacts/maintenance/2026-09-10-frontend-security/state-after.json)

`frontend/`에서:

```powershell
npm.cmd ci
npm.cmd audit --audit-level=high
npm.cmd test
npm.cmd run typecheck
npm.cmd run lint
npm.cmd run build
```

프로젝트 루트에서:

```powershell
docker compose exec -T backend python -m pytest -q
docker compose exec -T backend python -m ruff check app tests
docker compose build frontend
docker compose up -d --no-deps frontend
docker compose exec -T -e NPM_CONFIG_UPDATE_NOTIFIER=false frontend npm audit --include=dev --json --loglevel=error
```

검증 도중 npm의 업데이트 안내가 JSON 뒤에 섞여 최초 Docker audit 파싱이 실패했다.
재실행에서는 업데이트 안내를 비활성화하고 audit의 구조화 출력을 그대로 보존했다.
취약점 결과를 필터링하거나 실패를 성공으로 간주한 것은 아니다.
