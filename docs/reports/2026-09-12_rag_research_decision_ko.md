# RAG 개선 연구와 유한한 검증 계획

작성일: 2026-09-12. 논문 조사와 적용 실험을 구분한 기술 검토 문서.

## 왜 접근을 바꿨는가

이전 실험에서 22개 일반 RAG 질문 모두의 필수 근거가 후보 50개 안에 있었다.
문제는 검색 후보 부재가 아니라 최종 선택이었다. 1.5B 범용 생성 모델의 단계별 문단
선택은 필수 근거 충족을 6/22에서 2/22로 떨어뜨렸고, 168회 호출에 약 16분 36초가 들었다.
따라서 새로운 프롬프트나 후보 확장을 계속 추가하는 근거가 부족하다.

현재 판정은 승인된 특정 근거 문단 집합을 top-5 안에 포함했는지 검사한 것이다.
실패가 곧 모든 대체 문단의 의미적 부적절성을 증명하는 것은 아니지만, 이 평가를 통과하려고
정답 문단을 주입하거나 승인된 계약을 완화하지 않는다. 검색 성공과 답변 정확도도 다르다.

## 논문에서 확인한 내용

| 연구 | 확인한 방법 또는 결과 | 이번 프로젝트에서의 판단 |
| --- | --- | --- |
| [Nogueira & Cho, Passage Re-ranking with BERT, 2019](https://arxiv.org/abs/1901.04085) | 질문과 문단을 함께 입력해 관련성을 학습하는 검색 재정렬 | 후보 확보 후 최종 순위가 나쁜 현재 병목에 직접 적용 |
| [Carbonell & Goldstein, MMR, 1998](https://doi.org/10.1145/290941.291025) | 관련성과 이미 선택한 문서와의 중복을 함께 고려 | 관련성 순위만 쓰는 방식과, 중복을 억제하는 방식을 분리 비교 |
| [Dai & Callan, Deeper Text Understanding for IR, 2019](https://arxiv.org/html/1905.09217) | 겹치는 문단을 독립 평가하고 최고 문단 점수로 합치는 MaxP 등 비교 | 모델 길이 한계를 넘는 입력을 임의 절단하지 않는 데 적용 |
| [Sun et al., RankGPT, 2023](https://arxiv.org/abs/2304.09542) | LLM 순위 생성과 sliding-window 재정렬, 검색 전용 소형 모델로의 증류 | 논문의 성과가 작은 범용 모델에 자동 이전되지는 않음. 기존 탈락 방식은 논문의 순열 방식 재현도 아님 |
| [Liu et al., Lost in the Middle, 2023](https://arxiv.org/abs/2307.03172) | 긴 문맥에서 근거 위치에 따라 활용 성능이 달라짐 | 다수 문단 일괄 선택의 위험 근거. 현재 실패가 이 현상 때문이라고 단정하지 않음 |
| [Chen et al., BGE M3, 2024](https://arxiv.org/abs/2402.03216) | 다국어 및 dense/sparse/multi-vector 검색 지원 | 번역 의존을 줄일 장기 후보이나, 현재 top-50의 근거 충족이 이미 22/22라 이번에는 검색기 교체를 보류. 임베딩 논문과 별도 reranker 모델을 혼동하지 않음 |
| [Thakur et al., BEIR, 2021](https://arxiv.org/abs/2104.08663) | 서로 다른 도메인에서 검색 모델의 일반화와 계산 비용 비교 | 같은 개발 질문을 반복 개선한 결과를 일반 성능으로 주장하지 않도록 평가 범위 제한 |

논문별 벤치마크 수치는 이 프로젝트의 예상 성능으로 옮겨 쓰지 않았다. 위 내용은 관련 연구
7편의 표적 조사이며, 모든 최신 검색 연구를 포괄하는 체계적 문헌고찰은 아니다.

## 실제 적용 방법

기존 번역과 후보 50개를 고정하고 두 후보만 구현했다.

1. **Cross-Encoder**: 검색 관련성으로 학습된 `cross-encoder/ms-marco-MiniLM-L6-v2`로
   모든 질문-문단 쌍을 점수화한 후 상위 5개 선택.
2. **Cross-Encoder + MMR**: 같은 관련성 점수와 TF-IDF cosine 문단 유사도를 사용해,
   관련성을 유지하면서 중복을 줄이는 5개 문단 선택. 가중치는 실험 전 0.7로 고정.

검색 전용 모델의 공식 FP32 ONNX 파일은 약 91MB이며 Apache-2.0 모델이다.
[모델 카드](https://huggingface.co/cross-encoder/ms-marco-MiniLM-L6-v2)와
[공식 재정렬 문서](https://www.sbert.net/examples/sentence_transformer/applications/retrieve_rerank/README.html)를
확인했다. 영어 모델이므로 기존에 보존해 둔 영어 번역과 영문 원문을 이용한다.
이 실험으로 한국어 직접 검색 능력까지 입증했다고 주장하지 않는다.

CPU용 ONNX Runtime과 Hugging Face Tokenizers를 사용한다. 문단이 512토큰 입력을 넘으면
64토큰씩 겹치는 구간으로 나누고, 모든 원문 토큰이 포함되는지 확인한다. 문단 점수는 구간
최댓값으로 합친다. 이는 MaxP 원리의 적용이며 논문의 모델, 학습, 구간 설정을 그대로
재현한 것은 아니다. MMR의 sigmoid 점수 또한 보정된 정확도 확률이 아니다.

새 패키지와 모델은 실험용 가상환경/아티팩트 경로에만 추가했다. 서비스 코드, 운영 의존성,
API, UI, 기본 검색기, 승인 기록은 바꾸지 않았다. 외부 추론 API 호출, 학습, 신규 번역,
답변 생성, 사람 검토 자동 승인은 하지 않는다.

## 끝나지 않는 반복을 막는 기준

실행 전 [고정 프로토콜](../../experiments/retrieval_research/protocol.md)을 작성하고 사본을 보관했다.
다음 임계치는 논문에서 나온 상수가 아니라 이번 프로젝트의 진행 여부를 결정하기 위한
사전 엔지니어링 기준이다.

- 유망 후보: 일반 질문 12/22 이상, 핵심 질문 3/5 이상, 기본 검색과 개선 RRF 양쪽 대비
  회귀 0건, 실행 오류 0건, 질문당 평균 점수화 10초 미만.
- 답변 실험 진행 조건: 핵심 검색 5/5, 회귀와 오류 없음. 이것도 운영 승인과는 별개다.
- 비교는 두 방식 한 번만. 결과 확인 후 가중치 탐색, 프롬프트 교체, 모델 추가 시험을 하지 않는다.
- 둘 다 기준 미달이면 이번 검색 튜닝 경로를 종료한다. 또 다른 단계 이름을 붙여 연장하지 않는다.
- 유망하더라도 기본 적용은 하지 않는다. 독립 평가 질문과 실제 답변/인용 검증이 필요하다.

현재 22개 질문은 이미 여러 번 관찰한 개발 자료다. 같은 질문의 단순 표현 변경을 독립
평가라고 부르지 않는다. 독립 질문의 출처와 평가자는 개발 실험과 분리되어야 한다.

## 결과

**결론: 계산 비용과 일부 핵심 사례는 개선됐지만, 채택 기준은 충족하지 못했다.
두 후보 모두 채택하지 않고 이번 검색 튜닝 경로를 종료한다.**

| 방식 | 전체 RAG 48건 | 일반 22건 | 핵심 일반 5건 | 개선 RRF 대비 회귀 |
| --- | ---: | ---: | ---: | ---: |
| 기본 lexical | 25 | 6 | 1 | 2 |
| 기존 용어 보존 RRF | 27 | 8 | 1 | 0 |
| 이번 Cross-Encoder | 27 | 8 | 2 | 3 |
| 이번 Cross-Encoder + MMR | 25 | 6 | 1 | 4 |

전체 수치에는 실험 대상이 아닌 26건 중 성공 19건이 공통으로 포함된다. 원문 범위 밖 요청,
거절, 도구 결합, Agent 등의 준비 과정은 그대로다. 표의 모든 수치는 **필수 근거 충족 건수**이며,
답변 정확도나 독립 테스트 성능이 아니다.

Cross-Encoder는 RRF 대비 KO-RAG-006, KO-RAG-012, KO-RAG-MULTI-002를 새로 충족했다.
반대로 KO-RAG-009, KO-RAG-011, KO-RAG-MULTI-008을 잃어 일반 질문 총 성공은 8건으로 같다.
핵심 다중 근거 사례 KO-RAG-MULTI-002의 개선은 확인되지만 5개 핵심 계약을 해결한 것은 아니다.
MMR은 이 개선 일부를 다시 잃었으며, 중복 감소가 필수 근거 전체 확보와 같지 않음을 보여준다.

실행 오류는 0건. 1,100개 질문-문단 쌍을 1,249개 구간으로 점수화했고, 129개 쌍은 2개 이상의
구간을 사용했다. 실제 최대 구간 수는 3개였다. 문단별 구간 점수와 최댓값을 전부 보존했다.

점수화 시간은 **총 65.24초, 질문당 평균 2.97초**였다. 모델 로딩과 TF-IDF 준비는 약 1.17초다.
이전 생성형 실험의 약 16분 36초에는 번역 재시도도 포함되고 이번 점수화에는 번역, 다운로드,
MMR 후처리, 답변 생성이 포함되지 않는다. 측정 시 기존 Docker 테스트도 실행 중이었다.
따라서 엄밀한 동일 조건 전체 파이프라인 속도 배수로 제시하지 않는다. 다만 생성형 문단 선택을
검색 전용 점수화로 대체하면 이 장비에서 훨씬 적은 시간으로 실험할 수 있음을 관측했다.

## 검증과 보존

- 연구 테스트 34개 통과. 실제 ONNX 관련성 sanity check, 긴 입력 전체 토큰 포함,
  입력 예산, MMR 중복 억제, 평가 레이블 변조 시 입력 불변, 사전 임계치 등을 검사했다.
- 기존 Docker 백엔드 901개 통과. upstream deprecation warning 2건은 남아 있다.
- 48개 결과 행, 22개 점수 기록, 1,100개 쌍의 저장 점수, 판정, 코드 인벤토리가 재생과 일치했다.
  재생 시 새 모델 점수화는 0건이다. 이번 연구 후보의 Linux ONNX 실측은 하지 않았다.
- 모델 가중치와 토크나이저 파일 해시를 확인하고 로컬에서만 실행했다.
  서비스 가상환경과 Docker 운영 이미지에 연구 의존성을 넣지 않았다.
- 실행 전후 소스/모델 인벤토리 및 고정 프로토콜 사본이 일치했다. 결과를 본 뒤 연구 코드를
  수정하거나 가중치를 바꿔 다시 실험하지 않았다.
- 기존 `compare_snapshots` 검증으로 공식 평가 불변과 보호 대상 소스 변경 0건을 확인했다.
  승인된 1.0.5 질문, manifest, 검토 기록의 해시도 유지됐다.
- 공식 상태는 `BLOCKED`, critical 실패 관측 110건, 기존 결과 384건, 출력 사람 검토 0/30,
  `not_production_ready`다. 소스 승인과 생성 결과 승인을 혼동하지 않았다.

아티팩트 경로는 `artifacts/rag-research/2026-09-12/`다.

| 파일 | SHA-256 |
| --- | --- |
| `live.json` | `75cb6ac112af20ebac3f65d7f39d7691dff2f47180cc167617ff81b944df7ec2` |
| `live.scores.jsonl` | `676ff262b653f17bcec70c49e2c7468dc52d36a972b6eeed8f73f93b29ff69b5` |
| `replay.json` | `e310ff39e6049574ddf87f22dad69ad0f1dea15dd949bfb825ea08e388c7737b` |
| `protocol-frozen.md` | `42d467bd4014b75b02009fb8f2cadd0e5f9fbda4718b39f008a6665829908337` |
| `before.json` | `8b39423bcdfca12c57e3ae5e4266758c24a69e4f624560cbeee1efd5143bdabc` |
| `after.json` | `a1345dcc69397bda7290d872572b0a306a52d17a7f5b9d1dca1fa3e5d49a2d70` |

실행 보고서 내부 content hash:
`0d1e00737be072e6c6c26a4e79fb534f589942c407dc518f4e65ac5df1520c26`.
모델 revision은 `233902d25c440f23af6f7d6e94d2946bac0bee0a`이며 다운로드 파일의
해시와 실행 환경 패키지 버전은 `live.json`에 기록되어 있다.

## 구조와 재현

| 경로 | 역할 |
| --- | --- |
| `experiments/retrieval_research/ranker.py` | ONNX/Tokenizer 입력 검증, 전체 구간 평가, 관련성 정렬과 MMR |
| `experiments/retrieval_research/run.py` | 기존 입력 해시 검증, 제한 실행, 기록, 전체 비교와 재생 |
| `experiments/retrieval_research/test_ranker.py` | 네트워크 다운로드 없는 단위/로컬 모델/고정 자료 테스트 |
| `experiments/retrieval_research/protocol.md` | 실행 전에 정한 두 후보와 진행·중단 조건 |
| `experiments/retrieval_research/requirements.txt` | 운영 패키지와 분리한 연구 의존성 |

프로젝트 루트에서 다음 명령은 **추론을 새로 하지 않고** 저장된 점수로 검증한다.
출력과 저널 파일이 이미 존재하면 덮어쓰지 않으므로 새 파일명을 사용한다.

```powershell
.venv-rag-research/Scripts/python.exe -X utf8 -m experiments.retrieval_research.run `
  --repository-root . `
  --previous artifacts/rag-complementary/2026-09-12/live.json `
  --replay artifacts/rag-research/2026-09-12/live.json `
  --replay-sha256 75cb6ac112af20ebac3f65d7f39d7691dff2f47180cc167617ff81b944df7ec2 `
  --output artifacts/rag-research/2026-09-12/replay-check.json
```

가상환경을 다시 준비해야 할 때:

```powershell
.venv/Scripts/python.exe -m venv .venv-rag-research
.venv-rag-research/Scripts/python.exe -m pip install -e backend -r experiments/retrieval_research/requirements.txt
$env:RAG_RESEARCH_MODEL_DIR=(Resolve-Path artifacts/rag-research/models/minilm-l6).Path
.venv-rag-research/Scripts/python.exe -m pytest experiments/retrieval_research/test_ranker.py -q -p no:cacheprovider
```

직접 의존성은 고정했지만 전체 전이 의존성 lockfile은 아니다. 재생은 저장된 점수 검증이며,
다른 환경의 새 FP32 추론이 비트 단위로 동일하다는 증거는 아니다. 테스트 중 기존 아티팩트가
필요한 고정 자료 테스트와 로컬 모델이 필요한 테스트가 있음을 유의한다.

## 여기서의 결정

논문 기반 방법을 적용할 수 있고 실행 비용을 줄일 수 있음은 확인했다. 그러나 **이 데이터에서
높은 검색 품질을 확보했다고 결론 낼 수는 없다.** 이번 두 후보의 실패로 모든 Cross-Encoder,
MMR 또는 다국어 검색이 부적합하다고 일반화해서도 안 된다.

이제 같은 22개 질문을 기준으로 프롬프트, 가중치, 단계 이름을 계속 추가하는 작업은 멈춘다.
제품 목표는 평가 가능한 모델을 반드시 합격시키는 것이 아니라, 실패까지 신뢰성 있게 드러내는
EvalOps 플랫폼이라는 점을 유지한다. 실패한 작은 모델을 합격시키는 것이 플랫폼 완성의 필수
조건은 아니다. 반면 높은 품질의 로컬 RAG 자체가 별도 필수 목표라면, 독립 질문과 도메인별
관련성 학습 자료, 선택할 모델, 장비 예산을 먼저 명시한 별도 결정이 필요하다.

**권고는 평가 플랫폼 MVP의 범위를 확정하고 마감하는 것이다.** 로컬 RAG 품질 연구는 별도
목표로 분리하고, 데이터나 모델 조건이 바뀌기 전에는 동일한 튜닝 경로를 재개하지 않는다.
공식 Gate를 녹색으로 만들기 위한 레이블 변경이나 사람 검토 자동 승인은 하지 않는다.
