"""Groq speech-to-text and text-to-speech. The condo agent stays on GPT-4o-mini."""

from __future__ import annotations

import os
import re

import requests

GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
GROQ_TRANSCRIPTIONS_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_SPEECH_URL = "https://api.groq.com/openai/v1/audio/speech"
STT_PREFERENCE = ("whisper-large-v3-turbo", "whisper-large-v3")
TTS_PREFERENCE = ("canopylabs/orpheus-v1-english",)
TTS_VOICE = "troy"
MAX_SPOKEN_CHARS = 200

_stt_model: str | None = None
_tts_model: str | None = None


class VoiceConfigError(Exception):
    """Raised when Groq speech is not configured."""


def groq_api_key() -> str:
    key = (os.getenv("GROQ_API_KEY") or "").strip()
    if not key or key.startswith("your_"):
        raise VoiceConfigError("Voice is unavailable because GROQ_API_KEY is not set.")
    return key


def pick_speech_models(model_ids: list[str]) -> tuple[str, str]:
    """Choose a Whisper model and an English text-to-speech model from Groq's list."""
    stt = next((model_id for model_id in STT_PREFERENCE if model_id in model_ids), None)
    if stt is None:
        stt = next((model_id for model_id in model_ids if "whisper" in model_id.lower()), None)
    tts = next((model_id for model_id in TTS_PREFERENCE if model_id in model_ids), None)
    if tts is None:
        tts = next(
            (
                model_id
                for model_id in model_ids
                if "orpheus" in model_id.lower() and "english" in model_id.lower()
            ),
            None,
        )
    if not stt or not tts:
        raise VoiceConfigError(
            "Groq did not list a Whisper transcription model and an English text-to-speech model."
        )
    return stt, tts


def load_speech_models() -> tuple[str, str]:
    """Fetch Groq's model list once and remember the speech models."""
    global _stt_model, _tts_model
    if _stt_model and _tts_model:
        return _stt_model, _tts_model
    key = groq_api_key()
    response = requests.get(
        GROQ_MODELS_URL,
        headers={"Authorization": f"Bearer {key}"},
        timeout=20,
    )
    if response.status_code != 200:
        raise VoiceConfigError(f"Groq model list failed: {response.status_code} {response.text[:200]}")
    payload = response.json()
    model_ids = [item.get("id", "") for item in payload.get("data", []) if item.get("id")]
    _stt_model, _tts_model = pick_speech_models(model_ids)
    print(f"Groq speech models: transcribe={_stt_model} speak={_tts_model}")
    return _stt_model, _tts_model


def transcribe_audio(audio: bytes, filename: str, content_type: str) -> str:
    stt_model, _ = load_speech_models()
    response = requests.post(
        GROQ_TRANSCRIPTIONS_URL,
        headers={"Authorization": f"Bearer {groq_api_key()}"},
        data={"model": stt_model, "language": "en", "response_format": "json"},
        files={"file": (filename or "audio.wav", audio, content_type or "audio/wav")},
        timeout=60,
    )
    if response.status_code != 200:
        raise VoiceConfigError(f"Groq transcription failed: {response.status_code} {response.text[:200]}")
    return str(response.json().get("text") or "").strip()


def synthesize_speech(text: str) -> bytes:
    _, tts_model = load_speech_models()
    spoken = spoken_text(text)
    if not spoken:
        raise VoiceConfigError("Nothing to speak.")
    response = requests.post(
        GROQ_SPEECH_URL,
        headers={
            "Authorization": f"Bearer {groq_api_key()}",
            "Content-Type": "application/json",
        },
        json={
            "model": tts_model,
            "voice": TTS_VOICE,
            "input": spoken,
            "response_format": "wav",
        },
        timeout=60,
    )
    if response.status_code != 200:
        raise VoiceConfigError(f"Groq text-to-speech failed: {response.status_code} {response.text[:200]}")
    return response.content


def spoken_text(raw: str) -> str:
    """Plain text, at most two sentences, short enough for Groq speech."""
    text = _strip_unspoken_html(raw or "")
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
    spoken = " ".join(sentences[:2])
    if len(spoken) <= MAX_SPOKEN_CHARS:
        return spoken
    clipped = spoken[:MAX_SPOKEN_CHARS].rsplit(" ", 1)[0].strip()
    return clipped or spoken[:MAX_SPOKEN_CHARS].strip()


def _strip_unspoken_html(raw: str) -> str:
    text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", raw, flags=re.IGNORECASE)
    text = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(
        r"<div\b[^>]*\bid=(['\"])map\1[^>]*>(?:[\s\S]*?</div>)?",
        " ",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
