"""Chat model factory: OpenAI and/or Gemini, selected from env keys."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def _is_rate_limited(exc: Exception) -> bool:
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if code in {429, "429", "RESOURCE_EXHAUSTED"}:
        return True
    text = str(exc).lower()
    return any(
        needle in text
        for needle in (
            "429",
            "resource_exhausted",
            "resource exhausted",
            "rate limit",
            "quota exceeded",
            "exceeded your current quota",
        )
    )


class FallbackChatModel:
    """Try primary, then backup on rate-limit / quota errors."""

    def __init__(self, primary: Any, backup: Any | None = None):
        self.primary = primary
        self.backup = backup

    def invoke(self, messages):
        try:
            return self.primary.invoke(messages)
        except Exception as exc:
            if self.backup is not None and _is_rate_limited(exc):
                return self.backup.invoke(messages)
            raise


def _message_text(message: Any) -> str:
    content = getattr(message, "content", message)
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text", "")))
            else:
                parts.append(str(getattr(item, "text", item)))
        return "".join(parts)
    return str(content)


class GeminiChatModel:
    """Thin google-genai wrapper with the same .invoke(messages) surface as ChatOpenAI."""

    def __init__(self, *, api_key: str, model: str, temperature: float = 0.0):
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise ImportError(
                "google-genai is required for Gemini. Install with: pip install google-genai"
            ) from exc

        self._client = genai.Client(api_key=api_key)
        self._types = types
        self.model = model
        self.temperature = temperature

    def invoke(self, messages):
        system_chunks: list[str] = []
        user_chunks: list[str] = []
        for message in messages:
            name = type(message).__name__
            role = getattr(message, "type", None) or getattr(message, "role", "")
            text = _message_text(message)
            if name == "SystemMessage" or role in {"system", "developer"}:
                system_chunks.append(text)
            else:
                user_chunks.append(text)

        contents = "\n\n".join(user_chunks).strip() or " "
        config_kwargs: dict[str, Any] = {"temperature": self.temperature}
        if system_chunks:
            config_kwargs["system_instruction"] = "\n\n".join(system_chunks)

        resp = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._types.GenerateContentConfig(**config_kwargs),
        )
        text = getattr(resp, "text", None) or ""
        usage = getattr(resp, "usage_metadata", None)
        prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
        completion_tokens = int(
            getattr(usage, "candidates_token_count", 0)
            or getattr(usage, "completion_token_count", 0)
            or 0
        )
        return SimpleNamespace(
            content=text,
            response_metadata={
                "token_usage": {
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                }
            },
        )


def build_chat_models(settings) -> tuple[Any, Any]:
    """Return (llm, llm_hard) for the active provider. OpenAI construction is unchanged."""
    if settings.llm_provider == "openai" and settings.openai_api_key:
        from langchain_openai import ChatOpenAI

        llm = ChatOpenAI(model=settings.model)
        llm_hard = ChatOpenAI(model=settings.model_hard)
        return llm, llm_hard

    if settings.llm_provider == "gemini" and settings.google_api_key:
        primary = GeminiChatModel(
            api_key=settings.google_api_key, model=settings.gemini_model
        )
        backup = None
        fallback = settings.gemini_model_fallback
        if fallback and fallback != settings.gemini_model:
            backup = GeminiChatModel(
                api_key=settings.google_api_key, model=fallback
            )
        wrapped = FallbackChatModel(primary, backup)
        return wrapped, wrapped

    return None, None
