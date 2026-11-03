"""Remote LLM adapter using Hugging Face InferenceClient."""
from __future__ import annotations
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

DEFAULT_LLM_MODEL = "meta-llama/Llama-3.1-8B-Instruct"

SYSTEM_PROMPT = """You are Voxia, a helpful customer support AI voice agent. 
You help customers with their orders and inquiries.

Available tools:
- lookup_order(order_id: str): Look up order details by order ID

Rules:
1. Greet the customer warmly on first turn.
2. Ask for their order reference if they mention an order.
3. Use lookup_order when you have an order ID to check.
4. Always verify what the tool actually returned before reporting results.
5. If you need to call a tool, respond with JSON in this exact format:
   {"action": "tool_call", "tool": "lookup_order", "arguments": {"order_id": "ORD-XXXX"}}
6. Otherwise respond with plain conversational text.
7. Keep responses concise for voice — under 80 words.
8. End the conversation politely when the customer is satisfied.
"""


class LLMAdapter:
    """Remote LLM inference via HF. Never loads models locally."""

    def __init__(
        self,
        token: Optional[str] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        timeout: float = 45.0,
        max_tokens: int = 256,
    ) -> None:
        self.token = token or os.getenv("HF_TOKEN") or os.getenv("HUGGING_FACE_API_KEY")
        self.model = model or os.getenv("HF_LLM_MODEL", DEFAULT_LLM_MODEL)
        self.provider = provider or os.getenv("HF_LLM_PROVIDER")
        self.timeout = timeout
        self.max_tokens = max_tokens
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
                logger.error("Could not initialize HF InferenceClient for LLM: %s", exc)
        return self._client

    def chat(
        self,
        conversation_history: List[Dict[str, str]],
        tool_result: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Run a chat completion. Returns dict with 'content', 'model', 'latency_ms',
        and optionally 'tool_call' if the model wants to invoke a tool.
        """
        if not self.is_configured():
            return {
                "content": "I'm sorry, I'm having technical difficulties. Please try again later.",
                "model": self.model,
                "latency_ms": 0,
                "error": "LLM not configured: HF_TOKEN missing.",
            }

        client = self._get_client()
        if client is None:
            return {
                "content": "I'm sorry, I'm unavailable right now.",
                "model": self.model,
                "latency_ms": 0,
                "error": "HF client initialization failed.",
            }

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(conversation_history)
        if tool_result:
            messages.append({"role": "user", "content": f"[Tool result]: {tool_result}"})

        start_ms = time.monotonic() * 1000
        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.7,
            )
            latency_ms = time.monotonic() * 1000 - start_ms
            content = ""
            if response.choices:
                content = response.choices[0].message.content or ""
            # Strip think tags
            content = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()

            logger.info("LLM responded in %.0f ms via %s", latency_ms, self.model)

            # Check if model wants to call a tool
            tool_call = self._extract_tool_call(content)
            return {
                "content": content,
                "model": self.model,
                "latency_ms": round(latency_ms, 1),
                "error": None,
                "tool_call": tool_call,
            }
        except Exception as exc:
            latency_ms = time.monotonic() * 1000 - start_ms
            logger.error("LLM inference failed: %s", exc)
            return {
                "content": "I'm sorry, I encountered a technical issue.",
                "model": self.model,
                "latency_ms": round(latency_ms, 1),
                "error": str(exc),
                "tool_call": None,
            }

    @staticmethod
    def _extract_tool_call(content: str) -> Optional[Dict[str, Any]]:
        """Extract a tool call JSON from the model's response, if present."""
        if not content:
            return None
        # Try raw JSON first
        trimmed = content.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                parsed = json.loads(trimmed)
                if isinstance(parsed, dict) and parsed.get("action") == "tool_call" and "tool" in parsed:
                    return parsed
            except Exception:
                pass

        # Try finding JSON objects using bracket balance
        start_idx = 0
        while True:
            pos = content.find("{", start_idx)
            if pos == -1:
                break
            depth = 0
            for i in range(pos, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = content[pos : i + 1]
                        try:
                            parsed = json.loads(candidate)
                            if isinstance(parsed, dict) and parsed.get("action") == "tool_call" and "tool" in parsed:
                                return parsed
                        except Exception:
                            pass
                        break
            start_idx = pos + 1

        return None
