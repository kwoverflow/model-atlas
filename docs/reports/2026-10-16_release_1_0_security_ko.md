# Model Atlas 1.0 보안 보완 및 최종 마감 보고서

기준일: 2026-10-16. **로컬 검토용 1.0 마감 기준 충족: `LOCAL_REVIEW_1_0_READY`.**
개발 도구 위험을 수용하는 예외 없이, 실제 의존성 경로를 보완했다.
최종 근거는 [27항목 마감 집계](../../artifacts/personal-assistant-release/2026-10-16/closeout-security-v1/verification.json)다.
이 문서는 [최초 RC 보고서](2026-10-16_release_1_0_closeout_ko.md)의 보안 대기 상태를 갱신한다.

## 해결한 원인

### 프런트엔드

처음에는 전체 npm 감사에 high 7개·moderate 2개 패키지 항목이 남았다. 전파된 의존성
항목 수이며 서로 다른 CVE 9개라는 뜻은 아니다. 수정판이 없는 `braces`를 사용하는
Tailwind 3과 Next ESLint 플러그인의 `fast-glob` 경로가 핵심이었다.

1. Tailwind 4.3.3과 공식 `@tailwindcss/postcss`로 전환했다. 불필요해진 autoprefixer를 제거했다.
2. Next ESLint 플러그인은 공식 16.4.2를 출처가 명확한 로컬 패키지로 고정했다.
   54개 컴파일 파일 중 53개는 원본과 바이트가 동일하다. 규칙 구현·타입·내보내기는 보존하고,
   `utils/get-root-dirs.js`만 제한된 명시적 디렉터리 탐색으로 교체했다.
3. 로컬 버전은 `16.4.2-model-atlas.1`이다. 공식 수정판으로 위장하거나 취약점 ID를 무시하지 않았다.
   취약 glob 코드와 관련 의존성 노드를 실제 설치 트리에서 제거했다.
4. `settings.next.rootDir`의 glob 패턴은 명시적으로 거부한다. 단일 앱의 기본 경로와 명시적
   절대·상대 경로, 경로 배열은 유지한다. 미래 모노레포는 glob 대신 명시적 경로 배열을 사용한다.
5. npm의 로컬 패키지 설치 설정과 Docker COPY를 함께 보완해 Windows `npm ci`와 새 Linux
   빌드 모두 같은 패치를 설치하는지 검증했다.

Biome 자동 이관도 검토했지만 현재 67개 린트 설정 중 약 40%만 완전히 대응해 채택하지 않았다.
기존 React·Hooks·Next 규칙을 버리는 방식으로 감사 수치만 낮추지 않았다. 임시 Biome 의존성은 없다.

로컬 패치 출처, 공식 tarball SHA-512, 원본별 SHA-256, MIT 라이선스와 호환 경계는
[패치 안내](../../frontend/tooling/next-eslint-plugin/README.md)와 `UPSTREAM.json`에 포함했다.
향후 Next 업데이트 때 이 패치를 재검토해야 하며 자동 덮어쓰기는 금지한다.

### Python과 설치 도구

프런트 감사에서 멈추지 않고 실제 Windows Python 환경을 추가 감사했다. 최초 결과는
AnyIO·cryptography·pip·PyJWT·pypdf 5개 패키지의 47개 취약점 레코드였다.
여기에는 중복 ID가 있으므로 독립 취약점 47개라고 해석하지 않는다.

최소 요구 버전은 AnyIO 4.14.2, cryptography 50.0.0, PyJWT 2.15.0, pypdf 6.19.0으로
올렸고, 설치 도구 pip도 26.2 이상으로 갱신했다. 실제 검증 환경에는 AnyIO 4.15.1,
cryptography 50.0.2, PyJWT 2.15.1, pypdf 6.21.0, pip 26.2.1이 설치됐다.

`pip-audit==2.10.1`은 앱 환경 밖에서 실행한다. 설치된 **모든 제삼자 패키지의 정확한 버전**을
내보내 `--strict --no-deps --disable-pip`으로 감사한다. 의존성을 생략하는 것이 아니라 이미
설치된 전체 목록을 대상으로 재해결을 막는 방식이다. 자체 소스 `model-atlas-backend==1.0.0`만
공개 패키지 DB 검색에서 제외한다. 그 외 감사 누락·실패를 성공으로 처리하거나 ID를 무시하지 않는다.

## 검증 결과

| 검증 | 최종 결과 |
| --- | --- |
| npm 전체 개발·실행 의존성 감사 | 0건 |
| npm 실행 의존성 감사 | 0건 |
| Windows Python 제삼자 50개 | 알려진 취약점 0건 |
| 새 Linux 이미지 Python 제삼자 50개 | 알려진 취약점 0건 |
| Windows 백엔드 전체 테스트 | 1,261 통과, 2 건너뜀 |
| 새 Linux 백엔드 전체 테스트 | 1,263 통과 |
| 프런트 테스트 | 39 통과 |
| 도구 테스트 | 29 통과 |
| 린트·타입 검사·프로덕션 빌드 | 통과, 기존 린트 경고 4개 유지 |
| 보안 의존성 변경 후 실제 모델 브라우저 검증 | 21항목 통과, 모델 요청 11개, 모델 출력 수정 0개 |
| 기존 모델 관측 재생 | 328건 통과, 모델 호출 0개, 동결 소스 56개 일치 |
| 최종 CSS 모바일·데스크톱 | 3개 뷰포트 통과, 가로 넘침·버튼 넘침·페이지 오류 없음 |
| 새 Docker API 설치 시연 | HTTP·불변식 33항목 통과 |
| 최종 standalone Docker UI | Overview·Gate·Release 3개 페이지, 모바일 통과 |
| 기존 사용자 작업공간 | 상태·검토 기록·파일 해시 보존 |

기존 328건은 새로운 blind holdout도, 이번 환경에서 새로 발생한 328개 모델 응답도 아니다.
모델·동결 판단 소스는 변경하지 않았다. 이번에는 기존 응답을 갱신된 Python 환경에서 재생하고,
별도로 실제 모델 요청 11개로 네트워크·초안·확정·승인·취소·파일 복구 흐름을 확인했다.
문서 의미가 미검증인 68개 관측의 근거 상태 역시 의미 검증 완료로 바꾸지 않았다.

검증 중 발견한 이식성·화면 문제도 숨기지 않았다. 새 린트 테스트의 `/app` 경로 가정을
수정한 뒤 Docker 39개 테스트를 다시 통과했다. 최초 API smoke는 이미지 재기동 중 연결이
끊겨 실패했고, 기동 완료 후 다시 33항목을 확인했다. Tailwind CSS 레이어 때문에 발생한
메뉴 대비 회귀는 전역 기본 스타일을 `base` 레이어로 옮겨 보완했다. 최종 화면 검사는
선택 메뉴의 흰색 텍스트와 기본 버튼 14px까지 확인한다. 앞선 실패 기록을 성공으로 바꾸지 않았다.

Windows 테스트에는 기존 Starlette/httpx 경고, AnyIO 별칭 경고와 pytest 캐시 쓰기 경고가
있었다. Linux에는 Starlette/httpx 경고가 하나 있다. 성공 수치에 이를 숨기지 않으며,
경고가 취약점 또는 제품 오작동이라는 판정을 자동으로 의미하지는 않는다.

## 재발 방지와 재검증

CI는 npm 전체 감사를 low 이상에서도 실패하도록 강화했고, Python의 설치된 전체 버전을
별도 감사 환경에서 strict 검사한다. 패치 출처 해시, 실제 설치 파일, 위험 패턴 거부,
실제 ESLint 위반 감지도 프런트 테스트에 포함한다. 위험 수용 플래그는 사용하지 않았다.

```powershell
npm --prefix frontend ci
npm --prefix frontend audit
npm --prefix frontend audit --omit=dev
npm --prefix frontend test
.venv/Scripts/python.exe tools/export_backend_audit_requirements.py --output <새-감사-목록.txt>
uv tool run --from pip-audit==2.10.1 pip-audit --strict --no-deps --disable-pip -r <새-감사-목록.txt>
```

설치·마감은 [1.0 안내](../releases/1.0.0/README.md)를 따른다. 감사 목록은 설치 잠금 파일이나
휠 공급망 무결성 인증서가 아니다. Python 범위 버전은 두 환경에서 서로 다르게 해결될 수 있으며,
각 환경의 버전 목록과 감사 결과를 별도로 남겼다. 새 설치와 업데이트마다 감사를 재실행한다.

## 완료 범위와 남은 경계

완료 범위는 **로컬 검토용 프로그램 1.0의 의존성 보완·기능 회귀·설치·자료 마감**이다.
GitHub 원격 커밋·태그·Release 게시는 이 작업에서 하지 않았다. 새 모델 학습이나 가중치 배포도 아니다.

OS·기본 이미지 전체 CVE 스캔, 침투 테스트, 외부 인간 보안 검토, 운영 IDP·비밀 관리·인터넷
노출 인증은 수행하지 않았다. 취약점 DB는 시점별로 바뀌므로 0건은 영구 안전 보장이 아니다.
신뢰하지 않는 소스·설정은 lint·빌드하지 않는다. Tailwind 4의 브라우저 기준도 적용된다.
기존 모델 BLOCKED, 외부 검토 pending, 운영 not_production_ready, 자율 실행 blocked는 그대로다.

최종 ZIP은 RC와 별도 이름으로 생성하며 `PACKAGE_INFO.json`이 이번 마감 집계를 참조한다.
실제 압축·해제·해시·공개용 패턴 검사는 ZIP 옆 생성된 검증 파일을 기준으로 확인한다.

## 근거

- [전체 npm 감사 로그](../../artifacts/personal-assistant-release/2026-10-16/closeout-security-v1/full-audit.txt)
- [Windows Python 감사](../../artifacts/personal-assistant-release/2026-10-16/security-v1/python-audit.json)
- [Linux Python 감사](../../artifacts/personal-assistant-release/2026-10-16/security-v1/python-container-audit.json)
- [브라우저 검증](../../artifacts/personal-assistant-release/2026-10-16/security-v1/browser/browser-e2e.json)
- [최종 화면 검증](../../artifacts/personal-assistant-release/2026-10-16/security-v1/layout-final/layout.json)
- [Docker API 시연](../../artifacts/personal-assistant-release/2026-10-16/security-v1/clean-install-api.json)
- [공식 braces 보안 공지](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
- [공식 PostCSS selector 공지](https://github.com/advisories/GHSA-rj75-hqrm-r3gf)
- [Tailwind 공식 전환·브라우저 기준](https://tailwindcss.com/docs/upgrade-guide)
- [공식 Next 플러그인 npm 메타데이터](https://registry.npmjs.org/@next%2feslint-plugin-next/16.4.2)
- [PyPA pip-audit](https://github.com/pypa/pip-audit)
