# Model Atlas 1.0 기술 마감 보고서

> 이 문서는 최초 RC 시점의 기록이다. 이후 위험 수용 대신 취약 의존성을 보완했고,
> [보안 후속 마감 보고서](2026-10-16_release_1_0_security_ko.md)의 최종 집계는
> `LOCAL_REVIEW_1_0_READY`다. 아래의 보안 대기 상태·의존성 수치는 RC 당시를 뜻한다.

기준일: 2026-10-16. 범위는 [1.0 설치·사용·검토 안내](../releases/1.0.0/README.md)를 따른다.
기능 확장이나 새 모델 탐색이 아니라 기존 흐름의 적용·회귀·설치·패키징 마감이다.
**현재 개발 도구 위험의 릴리스 범위 승인은 대기 중**이다. 아래의 기술 통과와 전체 보안 감사
통과를 혼동하지 않는다. 외부 인간 검토와 운영·자율 실행 승인은 주장하지 않는다.

## 구현과 미검증 경로 처리

V8과 이전 실험의 동결 소스는 수정하지 않았다. 앱 전용 `release_generation.py`를 추가하고
API가 이 경로를 호출하도록 연결했다. 환경 설정·시작 도구의 기본 전략은 `assistant-release-v1`,
명시적 롤백은 `legacy`다. 역사적 실험용 `generation.py`의 기본값과 동결 검증은 그대로 보존했다.

미검증 34개는 정상 초안 15개, 확인 요청 13개, 철회 6개다. 지원 범위 밖으로 재분류하지 않았다.
이 경로는 원문 의미를 충분히 입증하지 못하므로 판정만 기술하는 고정 설명을 실제 디코딩
스키마에서 적용한다. 마감·우선순위 등 원인을 임의로 만들어 설명하지 않으며 의미 근거를
검증됨으로 승격시키지 않는다. 기존 intent와 결정 제약·승인·실행기 검사는 유지한다.

화면은 최초 초안의 요청 근거, 문서 의미, 설명 정책을 따로 표시한다. 생성 검증 실패 시
잘못된 원문 설명을 본문에 확정적인 안내처럼 표시하지 않는다. 원문은 상세에 보존한다.
사용자의 후속 수정이 원래 모델 초안의 근거를 소급 수정하지 않는다는 점도 표시한다.

## 모델 회귀와 재생

알려진 164개 시나리오를 시드 42·1729로 328회 실행했다. 이전에 관측한 사례의 회귀 확인이며
새로운 blind holdout이나 실사용 오류율 추정이 아니다. 후보 정책은 관측 전에 한 번 고정했고
재시도·원문 보정·관측 후 튜닝은 없다.

| 검사 | 결과 |
| --- | ---: |
| 정상 intent | 158/158 |
| 지정 보수적 결정 | 156/156 |
| 엄격 계약·독립 작업 흐름 | 328/328 |
| 승인 전 상태·외부 센티널 불변 | 328/328 |
| 설명 정책 | 328/328 |
| 지원 문서 의미 해석 | 24/24 |
| 문서의 미지원 내용 유보 | 8/8, 의미 이해 성공에 합산하지 않음 |
| 실행·완료·근거 오류 | 0 |
| 원문 재생 | 328/328, 추가 모델 호출 0 |
| 동결/현재 소스 | 56/56 일치 |

원문 설명 근거가 미검증인 68건은 여전히 그 상태다. 바뀐 것은 과도한 설명을 허용하지 않는
정책이지, 그 문장의 일반 의미 정확도를 증명한 것이 아니다. 임의의 새 문장에도 동일 성능이
나온다고 주장하지 않는다. 소스 기반 사실과 정직한 유보를 분리한다.

프로토콜 SHA-256: `13724e7ea494deba38496c8ade17ce3037248924a1579b22dfec66d3ef77aee5`.
관측 SHA-256: `b230dfdf64b318e76fa0062ecdc02ddbc274a8aefeb93b1b68dd4c3520269dfb`.

## 앱 통합·보존

최초 프로덕션 빌드와 보안 패치 후 빌드에서 각각 11개 실제 모델 요청·21개 확인을 통과했다.
자동 모델 보정은 0회이며 제목 수정·이전 승인 무효화용 수정은 의도적인 사용자 동작 두 번이다.
이 결과를 모델 자체의 일반 정확도나 실제 사람 만족도로 해석하지 않는다.

승인 전 불변, 수정·확정·별도 승인, 취소, 파일 이동·보관과 별도 복구 승인, 문서 금지 설명,
미지원 우선순위의 정직한 유보, 금지 경로, 뉴욕 겨울 시각 변환, 완료 ID 처리와 변경된 상태의
이전 승인 거절을 확인했다. 원문과 검토 기록은 재조회 후에도 보존됐다.

레이아웃은 1440×1000, 390×844, 320×740에서 읽기 전용으로 확인했다. 문서 가로 넘침과 버튼
텍스트 넘침, 초기 화면의 헤더·제목 중첩이 없었고 페이지 오류는 0건이다. 전체 앱의 접근성
전수 검사나 모든 모바일 상호작용 검사를 의미하지 않는다. 화면 크기 변경 직후 sticky 위치가
남는 캡처를 피하도록 최종 레이아웃 자료는 scroll=0에서 별도로 생성했다.

QA 작업공간에서 release → legacy → release로 재시작하고 상태·검토 13개의 해시가 유지됨을
확인했다. 별도 모델 호출은 없었으며 legacy 품질을 재인증한 것은 아니다.
기존 사용자 작업공간도 적용 전후 상태·검토 해시가 같았다. 일정·할 일·검토는 빈 상태,
`Inbox/review-demo.txt`는 63바이트·SHA-256
`ce5866238cdf7f257e9dd40abd8c0087077c63a6e182416eb8d0ff5ae9586632`를 유지했다.

## 설치와 테스트

새 Docker 프로젝트 `model-atlas-1-0-qa-20261016`와 새 PostgreSQL 볼륨에서 migration·seed·빌드를
확인했다. 원래 DB·공식 평가 기록·Ollama 캐시는 초기화하지 않았다. 새 DB의 mock 평가부터
원문·지표·로그·Gate preflight·판정·릴리스 변경 요청·snapshot·diff·export까지 33개 확인을 통과했다.
판정은 INSUFFICIENT_EVIDENCE/not_production_ready이며 실제 승인이나 사람 검토를 만들지 않았다.

Windows 백엔드 전체는 1,261 passed·2 skipped였다. 생략은 기존 심볼릭 링크 권한 제약이며
Starlette/httpx 경고 한 건이 있다. 새 Linux 검사에서 테스트의 Ollama 탐색과 배포 CORS 설정
의존을 발견해 테스트 fixture만 분리했다. 실제 앱의 네트워크·권한 검사를 완화한 것이 아니다.

프런트 테스트 33개, 타입 검사, 프로덕션 빌드를 확인했다. lint의 기존 탐색 경고 4개는 남는다.
검증용 `.next-*` 산출물은 Git·Docker build context·lint·ZIP에서 제외한다. 최종 도구·실험·Linux
전체 결과와 ZIP 검증은 최종 receipt를 따른다.

최종 Windows 결과는 **1,261 passed·2 skipped**, 새 Linux 결과는 **1,263 passed**다.
개인 비서 실험은 **241 passed**, 도구 검사는 **24 passed**다. 프런트 테스트·타입·lint는 보안
업데이트 뒤 다시 실행했고, Docker의 최종 frontend도 Next 16.4.2를 사용하는 것을 확인했다.
ESLint·Tailwind·braces·fast-glob 개발 패키지가 runner의 node_modules에 없음을 별도로 검사했다.

## 보안 감사

첫 설치의 npm 감사에서 실행 패키지를 포함한 13건을 발견했다. Next.js 16.3.4에서 16.4.2로
같은 major 안에서 업데이트하고 eslint-config-next를 맞췄다. 허용 범위 내 brace-expansion,
source-map-js 잠금도 갱신했다. 패치 후 실행 의존성 감사(`npm audit --omit=dev`)는 **0건**이다.
이는 감사 데이터베이스와 해당 잠금 파일에 대한 결과이지 전체 소프트웨어 보안 인증이 아니다.

Next의 취약 영향 조건과 패치는 [프로젝트 보안 공지](https://github.com/advisories/GHSA-vcvr-r3jv-pc5j),
[공식 16.4.2 릴리스](https://github.com/vercel/next.js/releases/tag/v16.4.2)를 확인했다.
해당 공지는 공격자 제어 SVG 입력 등의 조건을 설명하며 이 프로젝트가 실제 공격을 받았다는 뜻은 아니다.

전체 개발 환경에는 high 7건·moderate 2건이 남는다. 주된 원인은 ESLint/Tailwind의 glob 경로와
braces·PostCSS 계열이며, [braces 공지](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)는
깊게 중첩한 패턴의 스택 고갈 위험을 기술한다. 신뢰한 저장소 설정만 빌드·lint하고 외부 glob/CSS를
입력하지 않는 제한을 둔다. 이는 노출 제한에 대한 판단이지 취약 코드가 고쳐졌다는 뜻이 아니다.
이 수치는 의존성 전파를 포함한 패키지 항목 수이며 고유 CVE 일곱 개를 의미하지 않는다.

프런트 Docker runner는 전체 개발 node_modules와 소스 대신 standalone·static·public만 포함한다.
개발 도구 포함 여부와 실행 Next 버전은 최종 이미지에서 별도로 확인한다. 개발 환경 취약점을
포함해 전체 0건이 필요한 기준이라면 정식 릴리스가 아니라 RC로 남겨야 한다. 정책을 몰래 낮추거나
무조건 `npm audit fix --force`로 프레임워크를 바꾸지 않았다.

## 산출물과 최종 판정

소스·필요 문서·비밀값 없는 증거·전체 manifest를 ZIP에 포함하고 압축 해제 후 해시를 다시
확인한다. 모델 가중치·실제 DB와 SQLite sidecar·로그·비밀키·설치 의존성·개발 빌드는 제외한다.
ZIP은 오프라인 실행 이미지가 아니며 새 설치에는 의존성과 모델 준비가 필요하다.

최종 릴리스 상태는 생성된 검증 receipt와 ZIP 옆 검증 자료를 따른다. 개발 도구 위험의 사용자
범위 확인 전에는 ‘전체 보안 감사 통과’ 또는 ‘운영 배포 준비 완료’라고 표시하지 않는다.

현재 집계 상태는 **`CANDIDATE_PENDING_DEVELOPMENT_RISK_DECISION`**이다. 기능 마감 조건을
남긴 것이 아니라, 확인을 요청한 개발 도구 위험 범위의 선택이 아직 없기 때문이다. 기존의 전체
의존성 CI 감사 기준을 조용히 완화하지 않았다. 이번에는 원격 커밋·푸시·GitHub Release를 만들지 않았다.

- [모델 회귀 결과](../../artifacts/personal-assistant-release/2026-10-16/regression-v1/summary.json)
- [원문 재생](../../artifacts/personal-assistant-release/2026-10-16/replay-v1/verification.json)
- [보안 패치 후 브라우저 통합](../../artifacts/personal-assistant-release/2026-10-16/browser-v2/browser-e2e.json)
- [최종 레이아웃](../../artifacts/personal-assistant-release/2026-10-16/layout-v2/layout.json)
- [롤백](../../artifacts/personal-assistant-release/2026-10-16/rollback.json)
- [재적용](../../artifacts/personal-assistant-release/2026-10-16/rollforward.json)
- [기존 작업공간 보존](../../artifacts/personal-assistant-release/2026-10-16/live-after.json)
- [새 DB 핵심 흐름](../../artifacts/personal-assistant-release/2026-10-16/clean-install-api.json)
- [새 설치 UI](../../artifacts/personal-assistant-release/2026-10-16/deployment-ui/deployment-ui.json)
- [최종 마감 집계와 보안 범위](../../artifacts/personal-assistant-release/2026-10-16/closeout-v2/verification.json)
