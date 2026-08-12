"""LLM 제공자(OpenAI / Anthropic)를 추상화한 공용 클라이언트.

환경변수에 API 키가 설정되어 있지 않으면 자동으로 "mock" 모드로 동작해
API 키 없이도 전체 시스템 흐름을 즉시 확인할 수 있도록 합니다.
"""

import logging
from collections.abc import Iterator

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "당신은 대한민국 대학 입시행정 담당자를 돕는 AI 어시스턴트입니다. "
    "입학 전형, 지원자 상담, 서류 검토, 통계 분석, 공지/안내문 작성을 지원합니다. "
    "답변은 정확하고 간결하며, 공식 문서에 적합한 정중한 어투를 사용합니다. "
    "확실하지 않은 규정이나 수치는 추측하지 말고, 담당자의 확인이 필요하다고 안내하세요. "
    "표나 명세서를 요청받으면 반드시 GitHub Flavored Markdown 표로 작성하세요. "
    "표는 헤더 행 바로 다음에 |---|---| 형태의 구분 행을 넣고 모든 행의 열 개수를 동일하게 유지하세요. "
    "다단 헤더는 '상위 항목/하위 항목'처럼 한 행으로 평탄화하고, Markdown 표를 코드 블록(```)이나 "
    "ASCII 아트로 감싸지 마세요. 사용자가 제공하지 않은 값은 추측하지 말고 '{입력 필요}'로 표시하세요. "
    "등록금 명세서/예산안 요청 시에는 [별지 제8호 서식] 열 순서 "
    "(구분|대학, 계열|과정|세분|학기|학년(학기)|학생수|입학금/1인당 금액|입학금/금액|"
    "수업료/1인당 금액|수업료/금액|합계|비고)를 반드시 지키고 소계·합계·총계 행을 포함하세요. "
    "시스템이 동일 내용으로 PDF 양식도 함께 생성합니다."
)


class LLMService:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def provider(self) -> str:
        if self.settings.llm_provider != "mock" and self._has_key(self.settings.llm_provider):
            return self.settings.llm_provider
        return "mock"

    def _has_key(self, provider: str) -> bool:
        if provider == "openai":
            return bool(self.settings.openai_api_key)
        if provider == "anthropic":
            return bool(self.settings.anthropic_api_key)
        return False

    def chat(self, messages: list[dict[str, str]], system: str | None = None) -> str:
        """messages: [{"role": "user"|"assistant", "content": str}, ...]"""
        provider = self.provider
        system_prompt = system or SYSTEM_PROMPT

        try:
            if provider == "openai":
                return self._chat_openai(messages, system_prompt)
            if provider == "anthropic":
                return self._chat_anthropic(messages, system_prompt)
            return self._chat_mock(messages, system_prompt)
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM 호출 실패 (provider=%s)", provider)
            return self._friendly_error_message(provider, exc)

    def stream_chat(
        self,
        messages: list[dict[str, str]],
        system: str | None = None,
    ) -> Iterator[str]:
        """LLM에서 생성되는 텍스트 조각을 도착 즉시 반환합니다."""
        provider = self.provider
        system_prompt = system or SYSTEM_PROMPT

        try:
            if provider == "openai":
                yield from self._stream_openai(messages, system_prompt)
                return
            if provider == "anthropic":
                yield from self._stream_anthropic(messages, system_prompt)
                return

            mock_text = self._chat_mock(messages, system_prompt)
            for start in range(0, len(mock_text), 4):
                yield mock_text[start : start + 4]
        except Exception as exc:  # noqa: BLE001
            logger.exception("LLM 스트리밍 호출 실패 (provider=%s)", provider)
            yield self._friendly_error_message(provider, exc)

    def _openai_client(self):
        """Cursor 샌드박스 HTTP_PROXY가 OpenAI 호출을 가로채 403을 내는 것을 방지합니다."""
        from openai import OpenAI
        import httpx

        return OpenAI(
            api_key=self.settings.openai_api_key,
            http_client=httpx.Client(trust_env=False, timeout=60.0),
        )

    def _friendly_error_message(self, provider: str, exc: Exception) -> str:
        detail = str(exc)
        if "ProxyError" in detail or "403 Forbidden" in detail:
            return (
                f"[AI 응답 실패] 네트워크 프록시 때문에 {provider.upper()} API에 연결하지 못했습니다. "
                "백엔드를 일반 터미널에서 다시 실행하거나 프록시 설정을 확인해주세요."
            )
        if "insufficient_quota" in detail or "429" in detail:
            return (
                f"[AI 응답 실패] {provider.upper()} API 사용량/결제 한도(quota)를 초과했습니다. "
                "OpenAI/Anthropic 콘솔에서 결제 정보 또는 사용량 한도를 확인해주세요."
            )
        if "401" in detail or "invalid_api_key" in detail or "authentication" in detail.lower():
            return (
                f"[AI 응답 실패] {provider.upper()} API 키가 올바르지 않습니다. "
                "backend/.env의 API 키를 다시 확인해주세요."
            )
        return f"[AI 응답 실패] {provider.upper()} 호출 중 오류가 발생했습니다: {detail[:200]}"

    def _chat_openai(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        client = self._openai_client()
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )
        return response.choices[0].message.content or ""

    def _stream_openai(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]:
        client = self._openai_client()
        stream = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
            stream=True,
        )
        for chunk in stream:
            token = chunk.choices[0].delta.content
            if token:
                yield token

    def _chat_anthropic(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.settings.anthropic_api_key)
        response = client.messages.create(
            model=self.settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        )
        return "".join(block.text for block in response.content if hasattr(block, "text"))

    def _stream_anthropic(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> Iterator[str]:
        from anthropic import Anthropic

        client = Anthropic(api_key=self.settings.anthropic_api_key)
        with client.messages.stream(
            model=self.settings.anthropic_model,
            max_tokens=1024,
            system=system_prompt,
            messages=messages,
        ) as stream:
            yield from stream.text_stream

    def _chat_mock(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        last_user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        return (
            "[MOCK 응답 - .env에 OPENAI_API_KEY 또는 ANTHROPIC_API_KEY를 설정하면 "
            "실제 AI 응답으로 전환됩니다]\n\n"
            f"질문 요약: {last_user[:200]}\n"
            "실제 서비스에서는 이 부분에 입시 데이터/규정을 참고한 AI 답변이 표시됩니다."
        )


_llm_service: LLMService | None = None


def get_llm_service() -> LLMService:
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service


def reset_llm_service() -> None:
    """설정 변경 후 싱글톤을 다시 만들 때 사용합니다."""
    global _llm_service
    _llm_service = None
