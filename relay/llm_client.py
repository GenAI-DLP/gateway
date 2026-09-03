"""
LLM_PROVIDER 설정에 따라 openai_client 또는 gemini_client로 위임한다.
main.py는 이 모듈의 chat_completion만 호출하면 된다.
"""
from config import settings

if settings.llm_provider == "gemini":
    from gemini_client import GeminiError as LLMError
    from gemini_client import chat_completion
else:
    from openai_client import OpenAIError as LLMError
    from openai_client import chat_completion

__all__ = ["chat_completion", "LLMError"]