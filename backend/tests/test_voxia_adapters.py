"""Unit tests for Voxia adapters (mocked HF clients)."""
from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch


class TestSTTAdapter:
    def test_not_configured_without_token(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token=None)
        # Patch env to not have HF tokens
        with patch.dict("os.environ", {}, clear=True):
            adapter2 = STTAdapter(token=None)
            assert not adapter2.is_configured()

    def test_configured_with_token(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token="hf_test_token")
        assert adapter.is_configured()

    def test_transcribe_returns_error_when_not_configured(self):
        from novora.voxia.adapters.stt import STTAdapter
        with patch.dict("os.environ", {}, clear=True):
            adapter = STTAdapter(token=None)
            result = adapter.transcribe(b"fake audio")
            assert result["error"] is not None
            assert result["text"] is None

    def test_transcribe_empty_audio(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token="hf_test")
        result = adapter.transcribe(b"")
        assert result["error"] is not None

    def test_transcribe_oversized_audio(self):
        from novora.voxia.adapters.stt import STTAdapter, MAX_AUDIO_BYTES
        adapter = STTAdapter(token="hf_test")
        large = b"x" * (MAX_AUDIO_BYTES + 1)
        result = adapter.transcribe(large)
        assert result["error"] is not None
        assert "size" in result["error"]

    def test_transcribe_success_with_mock(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_client.automatic_speech_recognition.return_value = "Hello world"
        adapter._client = mock_client
        result = adapter.transcribe(b"fake audio bytes")
        assert result["text"] == "Hello world"
        assert result["error"] is None
        assert result["latency_ms"] >= 0

    def test_transcribe_handles_object_response(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token="hf_test")
        mock_client = MagicMock()
        resp = MagicMock()
        resp.text = "Transcribed text"
        mock_client.automatic_speech_recognition.return_value = resp
        adapter._client = mock_client
        result = adapter.transcribe(b"audio data")
        assert result["text"] == "Transcribed text"

    def test_transcribe_handles_exception(self):
        from novora.voxia.adapters.stt import STTAdapter
        adapter = STTAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_client.automatic_speech_recognition.side_effect = RuntimeError("API Error")
        adapter._client = mock_client
        result = adapter.transcribe(b"audio data")
        assert result["error"] is not None
        assert "API Error" in result["error"]


class TestTTSAdapter:
    def test_not_configured_without_token(self):
        from novora.voxia.adapters.tts import TTSAdapter
        with patch.dict("os.environ", {}, clear=True):
            adapter = TTSAdapter(token=None)
            assert not adapter.is_configured()

    def test_synthesize_returns_error_when_not_configured(self):
        from novora.voxia.adapters.tts import TTSAdapter
        with patch.dict("os.environ", {}, clear=True):
            adapter = TTSAdapter(token=None)
            result = adapter.synthesize("Hello")
            assert result["error"] is not None
            assert result["audio_bytes"] is None

    def test_synthesize_empty_text(self):
        from novora.voxia.adapters.tts import TTSAdapter
        adapter = TTSAdapter(token="hf_test")
        result = adapter.synthesize("")
        assert result["error"] is not None

    def test_synthesize_success_with_mock(self):
        from novora.voxia.adapters.tts import TTSAdapter
        adapter = TTSAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_client.text_to_speech.return_value = b"fake_audio_data"
        adapter._client = mock_client
        result = adapter.synthesize("Hello, how can I help?")
        assert result["audio_bytes"] == b"fake_audio_data"
        assert result["error"] is None
        assert result["content_type"] == "audio/flac"

    def test_synthesize_truncates_long_text(self):
        from novora.voxia.adapters.tts import TTSAdapter, MAX_TEXT_LENGTH
        adapter = TTSAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_client.text_to_speech.return_value = b"audio"
        adapter._client = mock_client
        long_text = "x" * (MAX_TEXT_LENGTH + 100)
        result = adapter.synthesize(long_text)
        called_with = mock_client.text_to_speech.call_args[1]["text"]
        assert len(called_with) == MAX_TEXT_LENGTH

    def test_synthesize_handles_exception(self):
        from novora.voxia.adapters.tts import TTSAdapter
        adapter = TTSAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_client.text_to_speech.side_effect = RuntimeError("TTS failed")
        adapter._client = mock_client
        result = adapter.synthesize("Hello")
        assert result["error"] is not None
        assert "TTS failed" in result["error"]


class TestLLMAdapter:
    def test_not_configured_without_token(self):
        from novora.voxia.adapters.llm import LLMAdapter
        with patch.dict("os.environ", {}, clear=True):
            adapter = LLMAdapter(token=None)
            assert not adapter.is_configured()

    def test_chat_returns_fallback_when_not_configured(self):
        from novora.voxia.adapters.llm import LLMAdapter
        with patch.dict("os.environ", {}, clear=True):
            adapter = LLMAdapter(token=None)
            result = adapter.chat([])
            assert result["error"] is not None
            assert result["content"] is not None  # fallback message

    def test_chat_success_with_mock(self):
        from novora.voxia.adapters.llm import LLMAdapter
        adapter = LLMAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Hello! How can I help?"
        mock_client.chat.completions.create.return_value = mock_resp
        adapter._client = mock_client
        result = adapter.chat([{"role": "user", "content": "Hi"}])
        assert result["content"] == "Hello! How can I help?"
        assert result["error"] is None
        assert result["tool_call"] is None

    def test_extract_tool_call_valid(self):
        from novora.voxia.adapters.llm import LLMAdapter
        content = '{"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-1001"}}'
        result = LLMAdapter._extract_tool_call(content)
        assert result is not None
        assert result["tool"] == "lookup_order"
        assert result["arguments"]["order_id"] == "ORD-1001"

    def test_extract_tool_call_no_match(self):
        from novora.voxia.adapters.llm import LLMAdapter
        result = LLMAdapter._extract_tool_call("Hello, how can I help?")
        assert result is None

    def test_extract_tool_call_invalid_json(self):
        from novora.voxia.adapters.llm import LLMAdapter
        result = LLMAdapter._extract_tool_call('{"action": "tool_call" invalid}')
        assert result is None

    def test_chat_with_tool_result(self):
        from novora.voxia.adapters.llm import LLMAdapter
        adapter = LLMAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "Your order is shipped."
        mock_client.chat.completions.create.return_value = mock_resp
        adapter._client = mock_client
        result = adapter.chat(
            [{"role": "user", "content": "Order ORD-1001?"}],
            tool_result='{"found": true, "order": {"status": "shipped"}}',
        )
        assert "shipped" in result["content"]

    def test_chat_strips_think_tags(self):
        from novora.voxia.adapters.llm import LLMAdapter
        adapter = LLMAdapter(token="hf_test")
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.choices = [MagicMock()]
        mock_resp.choices[0].message.content = "<think>thinking...</think>Hello!"
        mock_client.chat.completions.create.return_value = mock_resp
        adapter._client = mock_client
        result = adapter.chat([{"role": "user", "content": "Hi"}])
        assert "<think>" not in result["content"]
        assert result["content"] == "Hello!"
