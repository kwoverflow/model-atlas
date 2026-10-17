# 1.0 공개 검증 자료의 범위

문서 기준일: 2026-10-17. 프로그램의 현재 설명은 [프로젝트 안내서](../../PROJECT_GUIDE_KO.md)를 따른다.
파일이 Git에 있다는 것, 모델 응답을 다시 검증할 수 있다는 것, 실제 사용·배포 승인은 서로 다르다.

## Git에 포함하는 것

공개 검토에 필요한 소스·합성 테스트·실험 도구·문서와 **선별한 검증 receipt·테스트 보고서·화면**을
포함한다. `artifacts` 전체를 추가하지 않으며 모델 가중치, 설치 환경, DB, 비밀키, 사용자 파일,
실행 로그(`*.log`), 개별 실험의 가변 작업공간은 제외한다. 감사 명령의 검토용 텍스트 출력은
버전·결과 확인용으로 선별한다.

| 읽을 자료 | 의미 |
| --- | --- |
| [1.0 마감 집계](../../../artifacts/personal-assistant-release/2026-10-16/closeout-security-v1/verification.json) | 로컬 검토 준비도·검사 목록·참조 해시·감사 범위 |
| [모델 회귀 요약](../../../artifacts/personal-assistant-release/2026-10-16/regression-v1/summary.json) | 164개 기존 사례 × 2시드의 결과, 새로운 blind 평가 아님 |
| [실제 모델 브라우저 검증](../../../artifacts/personal-assistant-release/2026-10-16/security-v1/browser/browser-e2e.json) | 합성 작업공간의 21항목과 모델 요청 11개 |
| [최종 화면 검사](../../../artifacts/personal-assistant-release/2026-10-16/security-v1/layout-final/layout.json) | 3개 뷰포트·버튼·선택 메뉴 대비 확인 |
| [새 Docker 핵심 흐름](../../../artifacts/personal-assistant-release/2026-10-16/security-v1/clean-install-api.json) | mock 실행·Gate·릴리스 검토 33항목, 운영 승인 없음 |
| [Windows Python 감사](../../../artifacts/personal-assistant-release/2026-10-16/security-v1/python-audit.json) / [Linux 감사](../../../artifacts/personal-assistant-release/2026-10-16/security-v1/python-container-audit.json) | 설치된 제삼자 패키지 각 50개의 당시 알려진 취약점 검사 |
| [검증 보고서](../../reports/2026-10-16_release_1_0_security_ko.md) | 구현 변경, 실패 후 보완, 해석 한계와 재검증 절차 |

검증 receipt의 원문 해시는 보존했다. 하지만 **Git의 선별 자료만으로 receipt의 모든 원시 관측과
동결 소스를 재계산할 수 있다고 주장하지 않는다.** 과거 보고서의 나머지 생성물은 별도 ZIP 자료다.
기존 결과는 2026-10-16 측정이며, 이번 PR에서 새로 실행한 검사와 GitHub CI 결과는 PR에 구분한다.

## 10월 17일 PR 소스 재검증

Git index를 별도 디렉터리에 내보내 검사했다. Python 의존성은 기존 호스트 가상환경을 재사용했고,
프런트는 새 `npm ci`로 설치했다. 신규 모델 추론·전체 역사 재생·새 Linux 환경 검증은 실행하지 않았다.

| 자료 | 결과 |
| --- | --- |
| [백엔드 테스트](../../../artifacts/pr-preparation/2026-10-17/backend-tests.xml) | 1,261 통과·2 건너뜀 |
| [개인 비서 실험 테스트](../../../artifacts/pr-preparation/2026-10-17/experiment-tests.xml) | 241 통과 |
| [검토·공개 도구](../../../artifacts/pr-preparation/2026-10-17/tools-tests.txt) / [workflow export](../../../artifacts/pr-preparation/2026-10-17/workflow-tools-tests.xml) | 29 통과 / 9 통과 |
| [프런트 테스트](../../../artifacts/pr-preparation/2026-10-17/frontend-tests.txt) / [빌드](../../../artifacts/pr-preparation/2026-10-17/frontend-build.txt) | 39 통과 / production build 통과 |
| [npm 전체 감사](../../../artifacts/pr-preparation/2026-10-17/npm-audit.json) / [실행 감사](../../../artifacts/pr-preparation/2026-10-17/npm-runtime-audit.json) | 당시 알려진 취약점 0건 |
| [Python 감사](../../../artifacts/pr-preparation/2026-10-17/python-audit.json) / [검사 pin 목록](../../../artifacts/pr-preparation/2026-10-17/python-audit-requirements.txt) | 호스트 제삼자 패키지 50개, 취약점 0건 |
| [V6 고정 규칙 재검사](../../../artifacts/pr-preparation/2026-10-17/completeness-lint-ruff-017.txt) | Ruff 0.17.1에서도 기존 정책 통과 |

타입·린트 결과도 같은 디렉터리에 선별 보존한다. 초기 린트 검사에서 발견한 실행 위치 의존성은
CI 명령의 작업 폴더를 맞춰 해결했다. 이후 첫 원격 CI에서는 새 Ruff 0.17의 기본 규칙 변경으로
V6 린트가 실패했다. [명시적 V6 설정](../../../tools/ruff-frozen-completeness.toml)은 당시 Ruff 0.15의
기본 규칙 `E4/E7/E9/F`를 보존한다. 동결 소스·해시는 바꾸지 않으며 다른 코드의 린트 정책도 유지한다.
문서 링크 검사와 최종 공개 패턴 검사는 준비 중인 정확한 소스·index를 대상으로 별도 수행했다.
원격 Linux CI의 최종 상태는 GitHub PR Checks에서 확인한다.

## 전체 재생에 필요한 별도 ZIP

2026-10-16 마감 때 생성·압축 해제·검증한 파일은 다음과 같다.

- 파일: `model-atlas-1.0.0-local-review-20261016.zip`
- 크기: 38,270,358 bytes
- SHA-256: `f779802a33c180cdd265eeef86576cfe1280b92bd547422eccf1e594cb890a57`
- 내부 파일: 11,083개 항목, manifest 대상 파일 11,082개
- 검증: 압축 해제 후 해시 확인, 공개용 패턴 검사 통과. 보안 인증이나 개인정보 부재의 완전한 보증은 아님.

이 ZIP은 로컬에서 제공한 **10월 16일 스냅샷**이다. GitHub Release 자산이나 PR 첨부 파일로
업로드했다고 주장하지 않는다. 이번 PR의 10월 17일 신규 문서는 해당 ZIP에 소급 포함되지 않는다.
현재 PR 소스·문서는 PR 커밋을 기준으로 확인한다.

기존 관측 328건을 새 모델 호출 없이 재생하려면 ZIP의 원시 관측·선행 비교·동결 소스가
원래 상대 경로에 있어야 한다. 새 체크아웃만으로 다음 명령을 실행하면 자료 누락으로 실패할 수 있다.

```powershell
.venv/Scripts/python.exe -m experiments.personal_assistant_release.verify --source artifacts/personal-assistant-release/2026-10-16/regression-v1 --output artifacts/manual-replay/new-run
```

출력은 새 디렉터리를 사용한다. 재생을 위해 개인 데이터나 이전 DB를 복원하지 않는다.
실제 모델을 다시 평가하려면 별도의 런타임·동일 모델 digest·새 작업공간과 사전 고정한 조건이 필요하다.
재생은 저장된 관측의 일관성 확인이지 새 모델 성능 측정이나 독립 인간 검토가 아니다.

## PR 검토 순서

1. 프로젝트 안내서에서 목적·두 Flow·지원 범위를 확인한다.
2. API·초안 생성·검토·실행의 코드 책임과 승인 경계를 확인한다.
3. 합성 단위 테스트·타입·린트·빌드·의존성 감사 결과를 확인한다.
4. 선별한 receipt와 필요하면 별도 전체 ZIP을 확인한다.
5. 운영 배포·자율 실행·외부 인간 검토로 잘못 승격한 표현이 없는지 확인한다.
