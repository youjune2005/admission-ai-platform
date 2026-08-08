"""LLM 제공자(OpenAI / Anthropic)를 추상화한 공용 클라이언트.

환경변수에 API 키가 설정되어 있지 않으면 자동으로 "mock" 모드로 동작해
API 키 없이도 전체 시스템 흐름을 즉시 확인할 수 있도록 합니다.
"""

import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "당신은 대한민국 대학 입시행정 담당자를 돕는 AI 어시스턴트입니다. "
    "입학 전형, 지원자 상담, 서류 검토, 통계 분석, 공지/안내문 작성을 지원합니다. "
    "답변은 정확하고 간결하며, 공식 문서에 적합한 정중한 어투를 사용합니다. "
    "확실하지 않은 규정이나 수치는 추측하지 말고, 담당자의 확인이 필요하다고 안내하세요."
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

    def _friendly_error_message(self, provider: str, exc: Exception) -> str:
        detail = str(exc)
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
        from openai import OpenAI

        client = OpenAI(api_key=self.settings.openai_api_key)
        response = client.chat.completions.create(
            model=self.settings.openai_model,
            messages=[{"role": "system", "content": system_prompt}, *messages],
        )
        return response.choices[0].message.content or ""

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
