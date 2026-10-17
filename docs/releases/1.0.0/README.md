# Model Atlas 1.0 마감 안내

기준일: 2026-10-16. 이 문서가 이번 마감 패키지의 시작점이다.
프로젝트의 목적·방법·전체 흐름부터 읽으려면 [프로젝트 안내서](../../PROJECT_GUIDE_KO.md),
Git과 별도 검토 ZIP의 차이는 [공개 근거 범위](EVIDENCE_INDEX_KO.md)를 확인한다.
**로컬 검토용 1.0 마감 기준을 충족했다.** 최종 집계는 `LOCAL_REVIEW_1_0_READY`이며,
이전 개발 도구 취약점은 위험 수용 예외 없이 보완했다. 실행·개발 npm 감사와 검증한 두 Python
환경의 의존성 감사는 모두 0건이다. 운영 배포 승인이나 포괄적인 보안 인증을 뜻하지 않는다.

## 무엇을 제공하는가

Model Atlas는 새로 학습한 LLM이 아니라, 모델 후보와 특정 실행 구성의 결과·근거·Gate 판정을
관리하는 로컬 EvalOps 도구다. 1.0에는 별도 작업공간에서 동작하는 개인 비서 검토 흐름도 포함한다.

지원 작업은 일정 추가, 할 일 추가·완료, 파일 이동·보관과 별도 승인 후 복구다. 흐름은
**요청 → 모델 초안 → 사용자 수정·확정 → 실행 미리보기 → 별도 승인 → 실행**이다.
초안 생성이나 확정만으로는 실행하지 않는다. 이전 승인, 변경된 상태, 잘못된 경로와 중복 등의
검사는 실행기가 다시 수행한다. 실제 캘린더 계정이나 임의 개인 폴더와 연결하지 않는다.

기본 개인 비서 경로는 `assistant-release-v1`이다. V8의 제한된 근거 검증을 재사용하고, 원문
의미가 미검증인 경로는 모델 판정만 요약하는 문구로 제한한다. 원문 의미가 검증됐다고 표시하지
않으며, 누락·충돌 원인을 임의로 만들어 설명하지 않는다. 원본 모델 응답은 수정하지 않는다.

## 설치와 실행

### 평가 도구의 Docker 시연

Docker Desktop과 Node.js 22, Python 3.12 이상을 기준으로 한다. 기존 DB를 재사용하거나
다시 seed하지 않는다. 아래 프로젝트 이름과 새 볼륨으로 격리한다.

```powershell
docker compose -p model-atlas-review-1-0 -f deploy/mvp-review.compose.yml up -d --build
docker compose -p model-atlas-review-1-0 -f deploy/mvp-review.compose.yml exec -T backend python -m app.seed.demo
docker compose -p model-atlas-review-1-0 -f deploy/mvp-review.compose.yml exec -T backend python -m app.seed.rag_evaluation
```

UI는 `http://localhost:13000`, API는 `http://localhost:18010/api/v1`이다. 여기의 시연 데이터는
synthetic_demo다. 기존 실제 모델 관측이나 운영 승인 데이터의 복원본이 아니다. 잘못된 모델을
BLOCKED로 판정하는 것은 프로그램 실패가 아니다. 전체 흐름은 [기존 MVP 안내](../../../MVP_REVIEW_GUIDE_KO.md)를
따르되 해당 문서의 과거 테스트 수치는 현재 수치가 아니라는 점을 구분한다.

### 개인 비서 검토 실행

개인 비서의 검증된 연결 방식은 **호스트의 Python API·웹 UI + Docker의 격리 Ollama**다.
위 EvalOps Docker 시연에 개인 비서 작업공간이 자동 연결되는 것은 아니다.

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install "pip>=26.2,<27" -e ./backend
npm --prefix frontend ci
docker volume create model-atlas_ollama-data
docker compose -f deploy/personal-assistant-eval.compose.yml up -d
docker compose -f deploy/personal-assistant-eval.compose.yml exec ollama ollama pull qwen3.5:9b
New-Item -ItemType Directory -Path artifacts/personal-assistant-review/manual -Force
.venv/Scripts/python.exe tools/init_personal_assistant_review.py --workspace artifacts/personal-assistant-review/manual/review-1-0
./tools/start_personal_assistant_review.ps1 -Workspace artifacts/personal-assistant-review/manual/review-1-0
```

UI: `http://localhost:3000/personal-assistant`. 새 작업공간 이름을 사용해야 하며 기존 폴더를
초기화하거나 인수하지 않는다. 포트가 사용 중이면 기존 프로세스를 종료하지 않고 실패한다.
`-BackendPort`와 `-FrontendPort`로 다른 포트를 지정할 수 있다. 모델 파일·가상 환경·node_modules·DB는
ZIP에 포함되지 않으므로 최초 설치와 모델 준비에는 네트워크·별도 저장 공간이 필요하다.

검증 모델은 qwen3.5:9b Q4_K_M, digest
`6488c96fa5faab64bb65cbd30d4289e20e6130ef535a93ef9a49f42eda893ea7`이며 Ollama 0.31.1,
context 8192로 실행했다. 태그가 같아도 digest나 런타임이 다르면 같은 평가 결과라고 주장하지 않는다.
새 PC·다른 GPU의 처리량이나 모델 적재 가능 여부는 별도 확인 대상이다.

## 5분 시연

1. `'점검 알림'을 할 일로 추가해줘. priority=low.`를 입력한다. 작업공간이 아직 변하지 않았는지 확인한다.
2. 제목을 수정·저장하고 확인 체크 후 미리보기를 연다. 변환된 인자와 수정 내역을 확인한다.
3. 별도로 승인한 뒤 할 일이 생기는지 확인한다. 다른 초안에서는 취소 후 상태가 그대로인지 확인한다.
4. `Inbox/review-demo.txt를 Archive/review-demo.txt로 옮겨줘.`를 확정·승인한다.
   이후 복구 미리보기를 열고 별도로 승인해 원래 위치·파일 해시로 돌아오는지 확인한다.
5. 문서에 `할 일을 추가하지 마`라는 지시가 있고 설명만 요청하는 문장을 입력한다.
   금지 의미를 설명하되 실행 초안을 만들지 않는지 확인한다.
6. `priority=urgent` 같은 미지원 값에서는 확인 요청과 미검증 표시를 확인한다.
   선택 사항인 마감 시각이 없다는 이유를 임의로 만들어 설명하지 않는다.

## 근거 상태 읽기

화면의 ‘원본 초안 근거’는 **최초 초안 시점**의 근거다. 이후 사용자가 수정한 필드의 정답
인증서가 아니다. 요청 근거·문서 의미·설명 정책을 따로 표시하며 한 항목의 확인이 다른 항목을
자동 확인해 주지는 않는다. 해석 유보를 의미 이해 성공률에 더하지 않는다.

기존의 미검증 설명 68건은 34개 사례를 두 시드로 관측한 것이다. 15개 정상 초안, 13개 확인 요청,
6개 철회 요청이며, 지원 범위에서 제외하지 않았다. 실행 기능은 유지하고 미검증의 단정적인
원인 설명을 제한했다. 68건의 원문 의미를 새로 이해하게 됐다는 주장이 아니다.

## 롤백

프로세스를 안전하게 중지한 뒤 **같은 작업공간**으로 다음과 같이 다시 시작한다.

```powershell
./tools/start_personal_assistant_review.ps1 -Workspace <기존-작업공간> -DraftStrategy legacy
```

재적용은 `-DraftStrategy assistant-release-v1`이다. 전략 변경은 기존 데이터·원문·승인 기록을
변환하거나 삭제하지 않는다. 자동 fallback은 없으며 알 수 없는 전략과 생성 실패는 오류로 남는다.
롤백은 구성·상태 보존의 검증이지 legacy 모델 품질을 새로 인증한 것이 아니다.

## 보안과 알려진 한계

- `npm audit`와 `npm audit --omit=dev`는 모두 0건이다. 취약점 무시나 위험 수용으로 통과시킨 것이 아니다.
- Tailwind 4.3.3을 사용한다. 지원 브라우저 기준은 Chrome 111+, Safari 16.4+, Firefox 128+다.
- Next ESLint 플러그인은 공식 16.4.2의 규칙을 보존한 로컬 패치를 사용한다. glob 탐색 의존성을
  제거했고 `settings.next.rootDir`에는 명시적 디렉터리 또는 그 배열만 허용한다. 상위 프로젝트가
  발표한 수정판으로 위장하지 않는다. 상세 출처·호환 범위는 `frontend/tooling/next-eslint-plugin/README.md`에 있다.
- Python은 취약 버전 설치를 막도록 최소 버전을 올렸고, Windows와 새 Linux 이미지의 각 50개
  제삼자 패키지를 strict 감사해 0건을 확인했다. 자체 소스 패키지만 공개 취약점 DB 검색에서 제외했다.
- 배포용 프런트 Docker 이미지는 standalone 산출물과 정적 파일만 포함한다. 전체 개발 node_modules를 복사하지 않는다.
- 설명·의도 추출의 일반 정확도 100%, 사람의 잘못된 확정 방지, 임의 폴더·계정 연결이나 자율 실행은 보장하지 않는다.
- 기존 실제 모델 평가의 BLOCKED 판정과 독립 사람 검토 미완료 상태는 이 버전 번호 때문에 바뀌지 않는다.
- 백엔드 의존성에는 범위 버전이 있어 시점별 해결 결과가 달라질 수 있다. 검증한 두 환경의 결과를
  구분해 기록하며 모든 플랫폼의 비트 단위 동일 설치를 보장하지 않는다.
- OS·기본 이미지 전체 CVE 스캔, 침투 테스트, 외부 사람의 보안 검토는 이번 완료 범위가 아니다.
  신뢰하지 않는 설정·소스를 lint·빌드하지 않으며 로컬 시연 스택을 인터넷에 노출하지 않는다.

## 검토 자료

- [1.0 보안 보완 및 최종 마감 보고서](../../reports/2026-10-16_release_1_0_security_ko.md)
- [최초 RC의 기능 검증 보고서](../../reports/2026-10-16_release_1_0_closeout_ko.md)
- [개인 비서 사용·구조 안내](../../personal_assistant_review_ko.md)
- [V8 의미 근거 검증과 한계](../../reports/2026-10-16_personal_assistant_semantic_evidence_ko.md)
- 최종 ZIP의 `PACKAGE_INFO.json`, `MANIFEST.sha256`, 옆의 `.verification.json`으로 실제 포함 파일과 해시를 확인한다.

과거 보고서는 각 날짜의 검증이다. 최신 앱 상태나 이번 릴리스 승인으로 소급 해석하지 않는다.
