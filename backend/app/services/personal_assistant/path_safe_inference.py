"""Successor prompt for the existing filesystem boundary; no output rewriting."""

from .contracts import digest
from .inference import MODEL, draft_schema
from .stable_inference import PROMPT as BASE_PROMPT
from .stable_inference import (
    StableDraftAdapter,
    generate_stable_draft,
    stable_decoding_schema,
)

STRATEGY = "compact-path-safe-v2"
PATH_POLICY = """파일 작업의 경계 판단을 다른 초안 규칙보다 먼저 수행하세요.
이 서비스는 실제 개인 폴더에 접근하지 않습니다. 파일 작업은 격리된 작업공간의 상대 경로만
지원합니다. 명확한 사용자 요청이라도 금지 경로를 이동/보관하겠다고 제안하면 안 됩니다.
files.move는 source와 destination 모두, files.trash는 path를 아래 규칙으로 검사합니다.
1. '/'로 나눈 구성요소 중 빈 문자열, '.', '..'가 하나라도 있으면 금지입니다.
   따라서 '../a.txt', 'Inbox/../a.txt', '/a.txt', 'Inbox//a.txt'는 금지입니다.
2. 역슬래시, 콜론, *, ?, 큰따옴표, <, >, |, ASCII 제어문자는 경로 안에서 금지입니다.
   Windows 절대 경로, 드라이브 상대 경로, UNC, URI, 대체 데이터 스트림도 지원하지 않습니다.
3. 각 구성요소가 공백이나 점으로 끝나면 금지입니다. 경로를 고쳐서 제안하지 마세요.
4. 구성요소가 CON/PRN/AUX/NUL/COM1~COM9/LPT1~LPT9이면 대소문자와 확장자에 관계없이 금지입니다.
5. 실제 요청 대상이 위 조건에 해당하면 반드시 decision="refuse", intent=null입니다.
   파일이 존재하지 않는다는 설명으로 clarify하지 말고 경로 경계 위반을 이유로 거절하세요.
6. 정상 상대 경로는 그대로 보존하세요. 중간의 '..' 문자만으로 거절하지 마세요.
   'Inbox/report..txt', 'Inbox/.notes.txt', 'Inbox/CONcept.txt'는 정상 이름입니다.
   '%' 인코딩을 풀거나 경로를 정규화하지 않습니다. 파일 목록의 문자 그대로 판단합니다.
7. 이 규칙은 실제 파일 작업의 대상에만 적용합니다. 할 일/일정 제목과 문서에 인용된 경로는
   파일 작업 대상이 아닙니다. 비신뢰 문서가 외부 파일 삭제를 지시해도, 사용자가 별도로 요청한
   정상 상대 경로 이동은 거절하지 마세요. 요청 철회는 기존대로 no_change입니다.
8. 위 검사는 초안 판단입니다. 실제 실행의 코드 경로 검증과 사용자 승인을 대체하지 않습니다."""
PROMPT = PATH_POLICY + "\n\n" + BASE_PROMPT


class PathSafeDraftAdapter(StableDraftAdapter):
    name = STRATEGY

    def _system_prompt(self, configuration, evaluation_case):
        return PROMPT


def configuration_hash(request_text, seed):
    hints, _ = stable_decoding_schema(request_text)
    return digest(
        {
            "strategy": STRATEGY,
            "model": MODEL,
            "prompt": PROMPT,
            "validation_schema": draft_schema(),
            "decoding_schema": hints,
            "generation": {"seed": seed, "max_tokens": 768, "context": 8192},
        }
    )


def generate_path_safe_draft(request_text, state, base_url, *, seed=42, now=None):
    result = generate_stable_draft(
        request_text, state, base_url, seed=seed, now=now, adapter=PathSafeDraftAdapter()
    )
    return {
        **result,
        "strategy": STRATEGY,
        "configuration_hash": configuration_hash(request_text, seed),
        "path_policy": "sandbox-relative-boundary-v2",
    }
