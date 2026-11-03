"""Remote Speech-to-Text adapter using Hugging Face InferenceClient."""
from __future__ import annotations
import io
import logging
import os
import time
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

DEFAULT_STT_MODEL = "openai/whisper-large-v3"
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB


class STTAdapter:
    """Transcribes audio via HF remote inference. Never loads models locally."""

    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: float = 45.0,
    ) -> None:
        self.token = token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_API_KEY")
        self.model = model or os.getenv("HF_STT_MODEL", DEFAULT_STT_MODEL)
        self.provider = provider or os.getenv("HF_STT_PROVIDER")
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
                logger.error("Could not initialize HF InferenceClient for STT: %s", exc)
        return self._client

    def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> Dict[str, Any]:
        """Transcribe audio bytes. Returns dict with 'text', 'model', 'latency_ms'."""
        if not self.is_configured():
            return {"error": "STT not configured: HF_TOKEN is missing.", "text": None, "model": self.model}

        if not audio_bytes:
            return {"error": "Empty audio provided.", "text": None, "model": self.model}

        if len(audio_bytes) > MAX_AUDIO_BYTES:
            return {"error": f"Audio exceeds maximum allowed size ({MAX_AUDIO_BYTES} bytes).", "text": None, "model": self.model}

        client = self._get_client()
        if client is None:
            return {"error": "Failed to initialize HF client.", "text": None, "model": self.model}

        start_ms = time.monotonic() * 1000
        try:
            audio_file = io.BytesIO(audio_bytes)
            result = client.automatic_speech_recognition(audio=audio_file, model=self.model)
            latency_ms = time.monotonic() * 1000 - start_ms

            # Result is either a string or an object with .text
            text = result if isinstance(result, str) else getattr(result, "text", str(result))
            logger.info("STT transcribed %d bytes in %.0f ms via %s", len(audio_bytes), latency_ms, self.model)
            return {
                "text": text.strip() if text else "",
                "model": self.model,
                "latency_ms": round(latency_ms, 1),
                "error": None,
            }
        except Exception as exc:
            latency_ms = time.monotonic() * 1000 - start_ms
            logger.error("STT inference failed: %s", exc)
            return {"error": str(exc), "text": None, "model": self.model, "latency_ms": round(latency_ms, 1)}
