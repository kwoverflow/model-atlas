# RAG 질문·정답·근거 연결 검토

2026-09-10 / Evidence Remediation 24

## 결론

핵심 일반 RAG 5개 사례의 원문을 대조한 결과, **4건의 근거 교체 제안과 1건의 유지 의견**을
정리했다. 이는 AI가 작성한 검토안이며, 사람의 승인이나 모델 개선 결과가 아니다.
기존 1.0.4의 64건 승인은 그대로 보존했다. 새 1.0.5 초안에서는 변경되지 않은 60건의 승인만
이어받고, 변경된 4건을 검토 대기로 남겼다. 공식 Gate와 과거 점수는 변경하지 않았다.

## 사례별 판단

| 사례 | 기존 근거의 한계 | 제안 |
| --- | --- | --- |
| KO-RAG-001 | 가이드 14절은 일반 평가 관점이며 Gate와 운영 배포 허가의 관계를 직접 설명하지 않음 | `Sprint 4A Status Separation`으로 교체 |
| KO-RAG-002 | `Preflight Semantics`가 구성·정책·실행 증거·신뢰·검토·baseline·차단 전제조건을 직접 설명함 | 기존 유지 |
| KO-RAG-MULTI-001 | 개요와 `Decision Record`만으로 추천부터 서명까지의 흐름이 충분히 드러나지 않음 | 가이드 5절 + `Signed Release Decisions` |
| KO-RAG-MULTI-002 | 보고서 필드와 데모 식별자만으로 runtime 정체성과 publisher provenance를 함께 확인하는 이유를 설명하기 어려움 | `Model Identity And Attestation` + 공급망 `Purpose` |
| KO-RAG-MULTI-003 | SLO 개요·계산만으로 incident 대응 및 paging 복구 이력이 부족함 | 기존 burn-rate 문단 + `Incident Response Contract` + `Paging failed` |

네 변경 의견의 중요도는 high, 유지 의견은 informational로 기록했다. 원문과 질문을 대조한
판단이지만 독립적인 사람 검토 전이므로 확정된 라벨 오류 통계로 사용하면 안 된다.
질문의 세부 항목과 원문 14곳을 연결했고, 문자열의 정확한 일치는 14/14 확인했다.
이 검사는 의미적 충분성을 자동으로 증명하지 않는다.

## 검색 문제는 남긴다

질문, 검색 질문, `top_k=5`, 필수 사실, 금지 주장, 거절 요구, 중요도와 가중치를 변경하지 않았다.
모든 제안 근거를 요구하는 AND 조건이며, 검색이 쉬운 문단을 대체 정답으로 허용하는 OR
그룹은 추가하지 않았다. 복수 문서 사례는 두 문서 이상, 기본 최대 인용 수 3도 준수한다.

| 사례 | 기존 지정 문단 순위 | 제안 문단 순위 |
| --- | --- | --- |
| KO-RAG-001 | 1 | 46 |
| KO-RAG-002 | 5 | 5 |
| KO-RAG-MULTI-001 | 1, 19 | 36, 186 |
| KO-RAG-MULTI-002 | 9, 7 | 33, 6 |
| KO-RAG-MULTI-003 | 5, 2 | 2, 35, 16 |

고유 사례 5개 중 근거 계약 도달은 3/5에서 1/5가 된다. 변경 대상 네 건은 모두 top-5에서
막힌다. 낮은 점수 또는 점수 0의 후순위는 단순 정렬 위치일 뿐 의미적 관련성 척도가 아니다.
이를 숨기거나 질문에 정답 문서 제목을 넣지 않았다. 후속 검색 개선에서 해결할 문제다.

## 파일과 재현

- 읽기용 HTML: `reference_workload/revisions/1.0.5/source_alignment_report.html`
- 네 건의 결정·메모 입력: `reference_workload/revisions/1.0.5/revision_review.html`
- 원문 전체·인용·순위·해시: `reference_workload/revisions/1.0.5/source_alignment_audit.json`
- 변경 계약과 기존 검토 기록: 같은 디렉터리의 `revision_report.json`, `cases.jsonl`, `review_manifest.jsonl`
- 검토안 입력: `reference_workload/diagnostics/rag-contract-alignment-v1.json`
- 검증 및 초안 생성: `backend/app/reference_workload/rag_contract_alignment.py`

```powershell
# 저장소 루트에서 실행. 이미 존재하는 초안은 덮어쓰지 않는다.
.venv/Scripts/python.exe -m pytest -c backend/pyproject.toml backend/tests/test_rag_contract_alignment.py
# 새로운 버전의 계획을 준비한 경우 backend에서 실행한다.
../.venv/Scripts/python.exe -m app.reference_workload.rag_contract_alignment --repository-root .. --plan ../reference_workload/diagnostics/rag-contract-alignment-v1.json
```

기존 revision 생성·검토·확정 로직을 재사용했다. 원문 인용·ID·중복·복수 문서·인용 수 제한을
검증하고, 입력에 query나 필수 사실 변경 필드를 추가하면 거절한다. 이전 버전 전체 파일
해시와 새 보고서 해시를 기록한다. 모델 추론 0회, application DB 쓰기 0회다.

HTML 보고서는 공유 보고서 형식의 `source_alignment.artifact-v3.json`에서 생성했다.
표시용 집계는 해시를 검증한 audit JSON에 SQLite JSON1 쿼리를 실행해 재계산한다.
`tools/build_rag_alignment_report.py`에 실제 쿼리와 원본 집계 일치 검사가 있다.

## 검증과 한계

- 새 테스트 20개 통과, 최종 Docker 전체 backend **796개 통과**, host/Docker Ruff 통과.
- 잘못된 인용, 알 수 없는 ID, 누락·중복 사례, 불필요한 근거, 다중 문서 축소, 최대 인용 수
  초과를 거절한다. 변경되지 않은 60개 사례와 모든 의미 계약의 보존도 검사한다.
- 기존 1.0.4 파일, corpus와 공식 기록은 보존됐다. 공식 상태는 BLOCKED, critical 실패 관측
  110, runtime 결과 384, 출력 사람 검토 0/30, not_production_ready다.
- 기본 backend는 교체하지 않았다. 새 이미지는 별도 테스트에만 사용했다.
- 읽기용 HTML의 내용·원본 payload 일치와 구조를 확인했다. 공용 reader의 자동 패키징이
  `reader_timeout`으로 실패해 동일 공용 빌더의 semantic fallback을 내보냈다. 차트의 정적
  SVG와 브라우저 반응형·상호작용 QA는 완료하지 못했고, 표와 본문이 대체 내용을 제공한다.
  이 제한은 `source_alignment_report.html.verification.json`에 기록돼 있다.
- 검토 HTML의 자동 브라우저 접근은 URL 정책에 의해 차단됐다. 우회하지 않았다. 구조 검사로
  결정 입력 4쌍, 기본 선택 0개, 외부 script 0개를 확인했다. 결정·메모·검토자·직접 검토 확인
  없이는 내보내기를 중단하는 기존 스크립트를 확인했다. 실제 클릭·다운로드 QA는 미수행이다.
- 기존의 짧은 필수 사실과 표현에 민감한 의미 점수는 유지했다. 이번 초안만으로 답변 전체의
  사실성이나 모델 성능을 인증할 수 없다. 시간 추세나 독립 표본에 대한 분석도 아니다.

## 다음 행동

읽기용 보고서를 참고해 검토 화면의 네 건을 승인 또는 거절하고 메모를 남긴다. 검토자 이름과
직접 검토 확인을 입력한 뒤 `검토 증명 다운로드`로 파일을 받는다. 검토 내용이 자동 승인되거나
DB에 적용되지는 않는다. 증명 파일을 검증한 뒤 별도 확정을 진행하며, 승인되더라도 검색 및
새 출력 평가가 통과하기 전에는 Gate를 승격하지 않는다.

Audit content SHA-256: `61b6a4f8db753df297f15f34ebc2b144513fb0d74b2041020cb5f35ed9c3c0ee`.

Revision report SHA-256: `d16e4b55f9650cac961ac50ed694985bf0fa14dbb13e336b1022560aa4300473`.

공식 기록 보호: `artifacts/rag-contract-alignment/2026-09-10/official-protection.json`.
