"""Pipecat audio pipeline for Voxia voice sessions.

Pipecat is the audio transport and processing layer that sits between raw
browser audio and the LangGraph workflow. It handles:
  - Audio frame buffering
  - Voice Activity Detection (VAD) / frame accumulation
  - Turn completion handling
  - Routing the completed transcript to the LangGraph StateGraph

Architecture
------------
Browser audio bytes (HTTP base64)
  → VoxiaAudioPipeline.process_audio_turn()
      → Pipecat Pipeline:
          [InputAudioRawFrame source]
          → VoxiaHFSTTProcessor     (wraps STTAdapter.transcribe → TranscriptionFrame)
          → VoxiaLangGraphProcessor (calls invoke_turn → produces AgentResponseFrame)
          → VoxiaResultCollector   (captures agent output)
      → returns {transcript, agent_text, tool_calls, events, audio_bytes, content_type}
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

from pipecat.frames.frames import (
    EndFrame,
    Frame,
    InputAudioRawFrame,
    TextFrame,
    TranscriptionFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineParams, PipelineTask
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor

from novora.voxia.adapters.llm import LLMAdapter
from novora.voxia.adapters.stt import STTAdapter
from novora.voxia.adapters.tts import TTSAdapter
from novora.voxia.langgraph_workflow import invoke_turn

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Pipecat frame type for agent output
# ---------------------------------------------------------------------------

class AgentResponseFrame(Frame):
    """Carries the agent's text response and metadata from LangGraph."""

    def __init__(
        self,
        agent_text: str,
        tool_calls: list,
        events: list,
        audio_bytes: Optional[bytes],
        content_type: str,
        tts_error: Optional[str],
        user_text: str = "",
    ) -> None:
        super().__init__()
        self.agent_text = agent_text
        self.tool_calls = tool_calls
        self.events = events
        self.audio_bytes = audio_bytes
        self.content_type = content_type
        self.tts_error = tts_error
        self.user_text = user_text


# ---------------------------------------------------------------------------
# STT processor — wraps STTAdapter, converts InputAudioRawFrame → TranscriptionFrame
# ---------------------------------------------------------------------------

class VoxiaHFSTTProcessor(FrameProcessor):
    """Pipecat FrameProcessor that transcribes audio via the HF STT adapter."""

    def __init__(self, stt: Optional[STTAdapter] = None, mime_type: str = "audio/webm") -> None:
        super().__init__()
        self._stt = stt or STTAdapter()
        self._mime_type = mime_type
        self._audio_buffer: bytearray = bytearray()

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, InputAudioRawFrame):
            self._audio_buffer.extend(frame.audio)
            await self.push_frame(frame, direction)

        elif isinstance(frame, EndFrame):
            if self._audio_buffer:
                audio_bytes = bytes(self._audio_buffer)
                self._audio_buffer.clear()
                try:
                    loop = asyncio.get_running_loop()
                    result = await loop.run_in_executor(
                        None, lambda: self._stt.transcribe(audio_bytes, self._mime_type)
                    )
                    transcript = result.get("text", "")
                    if transcript:
                        logger.debug("STT transcript: %s", transcript)
                        await self.push_frame(
                            TranscriptionFrame(text=transcript, user_id="user", timestamp=""),
                            direction,
                        )
                except Exception as exc:
                    logger.warning("STT transcription failed: %s", exc)
            await self.push_frame(frame, direction)
        else:
            await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# LangGraph processor — routes transcripts into the LangGraph StateGraph
# ---------------------------------------------------------------------------

class VoxiaLangGraphProcessor(FrameProcessor):
    """
    Pipecat FrameProcessor that:
      1. Receives a TranscriptionFrame (or TextFrame) from upstream
      2. Calls invoke_turn() on the compiled LangGraph StateGraph
      3. Pushes an AgentResponseFrame downstream
    """

    def __init__(
        self,
        session_id: str,
        test_mode: bool = False,
        llm: Optional[LLMAdapter] = None,
        tts: Optional[TTSAdapter] = None,
    ) -> None:
        super().__init__()
        self._session_id = session_id
        self._test_mode = test_mode
        self._llm = llm
        self._tts = tts
        self.last_result: Optional[Dict[str, Any]] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)

        if isinstance(frame, (TranscriptionFrame, TextFrame)):
            user_text = frame.text
            audio_provided = isinstance(frame, TranscriptionFrame)

            logger.debug(
                "LangGraph processor: session=%s text=%r audio_provided=%s",
                self._session_id,
                user_text,
                audio_provided,
            )

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                lambda: invoke_turn(
                    session_id=self._session_id,
                    user_text=user_text,
                    audio_provided=audio_provided,
                    test_mode=self._test_mode,
                    llm=self._llm,
                    tts=self._tts,
                ),
            )
            result["user_text"] = user_text
            self.last_result = result

            agent_frame = AgentResponseFrame(
                agent_text=result["agent_text"],
                tool_calls=result["tool_calls"],
                events=result["events"],
                audio_bytes=result.get("audio_bytes"),
                content_type=result.get("content_type", "audio/flac"),
                tts_error=result.get("tts_error"),
                user_text=user_text,
            )
            await self.push_frame(agent_frame, direction)
        else:
            await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# Result collector — captures AgentResponseFrame at the end of the pipeline
# ---------------------------------------------------------------------------

class VoxiaResultCollector(FrameProcessor):
    """Collects AgentResponseFrame output from the pipeline."""

    def __init__(self) -> None:
        super().__init__()
        self.result: Optional[Dict[str, Any]] = None

    async def process_frame(self, frame: Frame, direction: FrameDirection) -> None:
        await super().process_frame(frame, direction)
        if isinstance(frame, AgentResponseFrame):
            self.result = {
                "agent_text": frame.agent_text,
                "tool_calls": frame.tool_calls,
                "events": frame.events,
                "audio_bytes": frame.audio_bytes,
                "content_type": frame.content_type,
                "tts_error": frame.tts_error,
                "user_text": frame.user_text,
            }
        await self.push_frame(frame, direction)


# ---------------------------------------------------------------------------
# Public pipeline class
# ---------------------------------------------------------------------------

class VoxiaAudioPipeline:
    """
    High-level interface for running one Voxia turn through a Pipecat pipeline.
    """

    def __init__(
        self,
        session_id: str,
        test_mode: bool = False,
        stt: Optional[STTAdapter] = None,
        llm: Optional[LLMAdapter] = None,
        tts: Optional[TTSAdapter] = None,
    ) -> None:
        self._session_id = session_id
        self._test_mode = test_mode
        self._stt = stt or STTAdapter()
        self._llm = llm
        self._tts = tts

    async def process_audio_turn(
        self, audio_bytes: bytes, mime_type: str = "audio/webm"
    ) -> Dict[str, Any]:
        """
        Run audio through the full Pipecat pipeline:
          InputAudioRawFrame → STT → LangGraph → collect result
        """
        stt_processor = VoxiaHFSTTProcessor(stt=self._stt, mime_type=mime_type)
        lg_processor = VoxiaLangGraphProcessor(
            session_id=self._session_id,
            test_mode=self._test_mode,
            llm=self._llm,
            tts=self._tts,
        )
        collector = VoxiaResultCollector()

        pipeline = Pipeline([stt_processor, lg_processor, collector])
        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=False))

        audio_frame = InputAudioRawFrame(audio=audio_bytes, sample_rate=16000, num_channels=1)

        runner = PipelineRunner(handle_sigint=False)
        asyncio.ensure_future(runner.run(task))

        await task.queue_frame(audio_frame)
        await task.queue_frame(EndFrame())

        # Yield and poll until result is available
        await asyncio.sleep(0)
        for _ in range(100):  # up to 5 seconds
            if collector.result is not None:
                break
            await asyncio.sleep(0.05)

        if collector.result is None:
            logger.warning(
                "Pipecat pipeline timed out for session %s; falling back to direct STT",
                self._session_id,
            )
            return await self._fallback_turn(audio_bytes, mime_type, audio_provided=True)

        return collector.result

    async def process_text_turn(self, user_text: str) -> Dict[str, Any]:
        """
        Run a plain-text turn through the LangGraph portion of the pipeline.
        """
        lg_processor = VoxiaLangGraphProcessor(
            session_id=self._session_id,
            test_mode=self._test_mode,
            llm=self._llm,
            tts=self._tts,
        )
        collector = VoxiaResultCollector()

        pipeline = Pipeline([lg_processor, collector])
        task = PipelineTask(pipeline, params=PipelineParams(allow_interruptions=False))

        text_frame = TextFrame(text=user_text)

        runner = PipelineRunner(handle_sigint=False)
        asyncio.ensure_future(runner.run(task))

        await task.queue_frame(text_frame)
        await task.queue_frame(EndFrame())

        await asyncio.sleep(0)
        for _ in range(100):
            if collector.result is not None:
                break
            await asyncio.sleep(0.05)

        if collector.result is None:
            logger.warning("Pipecat text pipeline timed out; falling back to direct invoke_turn")
            return await self._fallback_turn_text(user_text)

        return collector.result

    async def _fallback_turn(
        self, audio_bytes: bytes, mime_type: str, audio_provided: bool
    ) -> Dict[str, Any]:
        """Fallback: STT then direct LangGraph invoke."""
        loop = asyncio.get_running_loop()
        stt_result = await loop.run_in_executor(
            None, lambda: self._stt.transcribe(audio_bytes, mime_type)
        )
        user_text = stt_result.get("text", "")
        res = await self._fallback_turn_text(user_text, audio_provided=True)
        res["user_text"] = user_text
        return res

    async def _fallback_turn_text(
        self, user_text: str, audio_provided: bool = False
    ) -> Dict[str, Any]:
        """Fallback: direct LangGraph invoke."""
        loop = asyncio.get_running_loop()
        res = await loop.run_in_executor(
            None,
            lambda: invoke_turn(
                session_id=self._session_id,
                user_text=user_text,
                audio_provided=audio_provided,
                test_mode=self._test_mode,
                llm=self._llm,
                tts=self._tts,
            ),
        )
        res["user_text"] = user_text
        return res
