"""Remote Text-to-Speech adapter using Hugging Face InferenceClient."""
from __future__ import annotations
import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

DEFAULT_TTS_MODEL = "facebook/mms-tts-eng"
MAX_TEXT_LENGTH = 500


class TTSAdapter:
    """Synthesizes speech via HF remote inference. Never loads models locally."""

    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: float = 45.0,
    ) -> None:
        self.token = token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_API_KEY")
        self.model = model or os.getenv("HF_TTS_MODEL", DEFAULT_TTS_MODEL)
        self.provider = provider or os.getenv("HF_TTS_PROVIDER")
        self.timeout = timeout
        self._client = None

    def is_configured(self) -> bool:
        return bool(self.token)

    def _get_client(self):
        if self._client is None and self.token:
            try:
                from huggingface_hub import InferenceClient
                kwargs: Dict[str, Any] = {"token": self.token, "timeout": self.timeout}
                if self.provider:
                    kwargs["provider"] = self.provider
                self._client = InferenceClient(**kwargs)
            except Exception as exc:
                logger.error("Could not initialize HF InferenceClient for TTS: %s", exc)
        return self._client

    def synthesize(self, text: str) -> Dict[str, Any]:
        """Synthesize text to speech. Returns dict with 'audio_bytes', 'model', 'latency_ms'."""
        if not self.is_configured():
            return {"error": "TTS not configured: HF_TOKEN is missing.", "audio_bytes": None, "model": self.model}

        if not text or not text.strip():
            return {"error": "Empty text provided.", "audio_bytes": None, "model": self.model}

        if len(text) > MAX_TEXT_LENGTH:
            text = text[:MAX_TEXT_LENGTH]
            logger.warning("TTS text truncated to %d chars", MAX_TEXT_LENGTH)

        client = self._get_client()
        if client is None:
            return {"error": "Failed to initialize HF client.", "audio_bytes": None, "model": self.model}

        start_ms = time.monotonic() * 1000
        try:
            audio = client.text_to_speech(text=text.strip(), model=self.model)
            latency_ms = time.monotonic() * 1000 - start_ms

            # audio is bytes
            audio_bytes = audio if isinstance(audio, bytes) else bytes(audio)
            logger.info("TTS synthesized %d chars → %d bytes in %.0f ms via %s",
                        len(text), len(audio_bytes), latency_ms, self.model)
            return {
                "audio_bytes": audio_bytes,
                "content_type": "audio/flac",
                "model": self.model,
                "latency_ms": round(latency_ms, 1),
                "error": None,
            }
        except Exception as exc:
            latency_ms = time.monotonic() * 1000 - start_ms
            logger.error("TTS inference failed: %s", exc)
            return {"error": str(exc), "audio_bytes": None, "model": self.model, "latency_ms": round(latency_ms, 1)}
