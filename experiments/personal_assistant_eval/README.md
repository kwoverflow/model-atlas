# Personal Assistant Evaluation

한국어 일정, 할 일, 가상 파일 관리에 맞는 **업무별 로컬 모델 비교**다.
기존 Model Atlas의 `OpenAICompatibleAdapter`, JSON schema validator,
`evaluate_policy_rules`를 사용한다. 공식 reference workload나 DB는 변경하지 않는다.

## 범위와 안전 경계

- 가상의 일정·할 일·파일 목록만 모델에 전달한다. 실제 사용자 파일을 읽지 않는다.
- 출력은 계획 JSON이다. 도구 호출 실행, 파일 이동·삭제, 캘린더 변경 기능은 없다.
- 새 추론은 실제 GPU runtime에서 수행한다. 입력 사례는 사람이 사용한 운영 로그가 아니라
  이번 평가를 위해 작성한 `local_authored_synthetic` 데이터다.
- 모델의 계획 생성 능력을 비교하는 것이며, 완성된 개인 비서나 native tool-calling 검증은 아니다.
- 평가 결과는 로컬 artifacts에만 저장한다. 사용자 장비 정보·결과를 GitHub에 자동 게시하지 않는다.

## 고정한 평가 조건

| 항목 | 값 |
| --- | --- |
| 사례 | 일정 8, 할 일 8, 파일 8 |
| 반복 | 각 사례 seed 42와 1729로 2회 |
| 초기 후보 | 설치된 Qwen2.5 1.5B, Qwen3.5 4B, Qwen3.5 9B |
| 공통 설정 | context 8192, concurrency 1, temperature 0, max_tokens 768 |
| 추론 | reasoning_effort=none, JSON object mode |
| 시간 | warm end-to-end latency; 로딩 warmup 별도 |
| 시각 기준 | 2026-09-19 09:00, Asia/Tokyo; 연말 사례만 시각 변경 |
| 결과 | 원문 JSON strict parse, 필수·허용 인자 검증, 계획과 기대 결과 비교 |

이 작은 입력은 긴 문맥 성능을 검증하지 않는다. 48회 관측은 독립 사례 48개가 아니다.
temperature=0의 반복은 제한적인 재현성 점검이며 다양한 대화·오류 분포의 검증이 아니다.
RRULE/날짜 문자열은 선언된 형식을 정확히 비교한다. 동치 표현까지 모두 허용하는 의미 평가가 아니다.
reason의 존재는 확인하지만 설명의 유창성·의미는 자동 채점하지 않는다.

통과 조건은 전체 24개 사례와 각각 2개 seed의 커버리지, 계획 정답률 90% 이상,
schema 유효성 100%, critical failure 0, 탐지된 위험 계획 0, runtime error 0,
p95 latency 8초 이하다. p95는 nearest-rank로 계산한다.
통과하더라도 `PASS_FOR_SUPERVISED_PILOT`일 뿐 운영 승인이나 무인 실행 승인이 아니다.
잘못된 schema는 별도 실패로 차단한다. 위험 계획 수가 0이라는 사실만으로 안전하다고 해석하지 않는다.

## 재현

Python 3.12 환경에서 `pip install -e ./backend`를 먼저 실행한다.
아래 Compose는 NVIDIA GPU를 요구하고 기존 `model-atlas_ollama-data` volume을 사용한다.
평가 서버는 loopback 11435에만 노출하며 cloud 기능을 끈다. 기존 11434 runtime은 재설정하지 않는다.
완전히 새 설치라면 먼저 `docker volume create model-atlas_ollama-data`로 빈 cache를 만든다.
모델은 필요한 때 따로 내려받으며 가중치는 Git 저장소에 포함하지 않는다.

```powershell
docker compose -f deploy/personal-assistant-eval.compose.yml up -d
docker compose -f deploy/personal-assistant-eval.compose.yml exec -T ollama ollama pull qwen2.5:1.5b
docker compose -f deploy/personal-assistant-eval.compose.yml exec -T ollama ollama pull qwen3.5:4b
docker compose -f deploy/personal-assistant-eval.compose.yml exec -T ollama ollama pull qwen3.5:9b
python -m pytest experiments/personal_assistant_eval -q
python -m experiments.personal_assistant_eval.run --confirm-synthetic-only --output artifacts/personal-assistant/new-run
```

output은 새 폴더여야 한다. 기존 결과를 덮어쓰거나 완료한 결과만 골라 재시도하지 않는다.
`--models`로 선언된 후보 일부만 별도의 run에서 평가할 수 있다.
실제 API나 파일 connector를 나중에 연결하려면 별도 승인·경로 제한·원자적 처리·감사 로그·복구가 필요하다.

## 파일과 읽는 순서

1. `protocol.json`: 실행 전 고정한 사례·기대값·정책·프롬프트·소스 hash·장비
2. `runtime.json`: 런타임 버전과 모델 digest
3. `*.jsonl`: 모든 응답 원문, 실패, 지연시간, GPU·resident 관측
4. `*.summary.json`: 후보별 평가와 세부 정책 판단
5. `comparison.json`, `comparison.md`: 최종 비교

이번 결과의 실행 소스는 `executed-source`에 별도로 보존했다. 소스 원문 hash와 현재 AST,
144개 관측의 누락·중복, 원문 응답의 점수와 Gate를 다시 검증할 수 있다.

```powershell
python -m experiments.personal_assistant_eval.verify artifacts/personal-assistant/2026-09-19/gpu-v1
```

이 검증은 저장된 증거의 내부 일관성 검사이며 외부 인증이나 독립 평가가 아니다.

모델별 digest와 실제 loaded context/VRAM을 함께 확인한다. 파일 다운로드 크기와 VRAM은 다르다.
GPU memory는 호출 후 관측값이며 peak sampling이 아니다. host GPU 사용량은 다른 앱도 포함한다.
기존 어댑터의 `ttft_ms`는 비스트리밍 전체 지연과 같으므로 이 평가에서는 TTFT로 보고하지 않는다.
새 run에서 실패를 수정할 때는 기존 결과를 보존하고 새 protocol 버전으로 비교한다.

## 후보 선정 자료

확인일: 2026-09-19. 모델 페이지의 대형 모델 benchmark를 작은 후보의 실측 성능으로 가져오지 않는다.

- [Ollama Qwen3.5 4B](https://ollama.com/library/qwen3.5:4b): Q4_K_M, 약 3.4GB 다운로드
- [Ollama Qwen3.5 9B](https://ollama.com/library/qwen3.5:9b): Q4_K_M, 약 6.6GB 다운로드
- [Ollama 호환 API](https://docs.ollama.com/api/openai-compatibility): JSON mode와 reasoning_effort 제어
- [Ollama thinking](https://docs.ollama.com/capabilities/thinking): 추론 모드 설정과 출력 구분

이 후보군 안에서만 추천한다. 다른 모델 계열이나 reasoning-enabled 설정까지 검증한 결과는 아니다.
