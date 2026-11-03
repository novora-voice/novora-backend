import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Configurable Hugging Face model IDs with verified defaults
DEFAULT_HF_JUDGE_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
DEFAULT_HF_GENERATOR_MODEL = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B"
DEFAULT_HF_EVALUATOR_MODEL = "meta-llama/Llama-3.1-8B-Instruct"


def get_hf_token() -> Optional[str]:
    """Retrieve Hugging Face token from environment, never exposing to client."""
    return (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGING_FACE_API_KEY")
        or os.getenv("HUGGINGFACE_API_KEY")
    )


def get_hf_judge_model() -> str:
    return os.getenv("HF_JUDGE_MODEL") or os.getenv("PAYLOAD_JUDGE_MODEL") or DEFAULT_HF_JUDGE_MODEL


def get_hf_generator_model() -> str:
    return os.getenv("HF_GENERATOR_MODEL") or os.getenv("PAYLOAD_GENERATOR_MODEL") or DEFAULT_HF_GENERATOR_MODEL


def get_hf_evaluator_model() -> str:
    return os.getenv("HF_EVALUATOR_MODEL") or DEFAULT_HF_EVALUATOR_MODEL


class HFJudgeVerdict(BaseModel):
    criterion_id: str
    status: str  # "PASS", "FAIL", "INCONCLUSIVE"
    confidence: float = 0.8
    rationale: str
    evidence_references: List[str] = Field(default_factory=list)
    model_identifier: str = ""
    evaluation_status: str = "completed"


class HuggingFaceClient:
    """Hugging Face Inference Client integration for LLM-as-a-judge and payload generation."""

    def __init__(
        self,
        token: Optional[str] = None,
        judge_model: Optional[str] = None,
        generator_model: Optional[str] = None,
        evaluator_model: Optional[str] = None,
        timeout: float = 30.0,
    ) -> None:
        self.token = token or get_hf_token()
        self.judge_model = judge_model or get_hf_judge_model()
        self.generator_model = generator_model or get_hf_generator_model()
        self.evaluator_model = evaluator_model or get_hf_evaluator_model()
        self.timeout = timeout
        self._inference_client = None

    def is_configured(self) -> bool:
        return bool(self.token)

    def _get_client(self):
        if self._inference_client is None and self.token:
            try:
                from huggingface_hub import InferenceClient
                self._inference_client = InferenceClient(token=self.token, timeout=self.timeout)
            except Exception as exc:
                logger.warning("Could not initialize huggingface_hub.InferenceClient: %s", exc)
        return self._inference_client

    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.1,
        max_tokens: int = 1024,
    ) -> Optional[str]:
        target_model = model or self.judge_model
        client = self._get_client()
        if client is None:
            return None

        try:
            response = client.chat.completions.create(
                model=target_model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            if response.choices and len(response.choices) > 0:
                content = response.choices[0].message.content
                # Strip out any DeepSeek <think>...</think> chain-of-thought
                cleaned = re.sub(r"<think>[\s\S]*?</think>", "", content).strip()
                return cleaned
        except Exception as exc:
            logger.error("Hugging Face chat completion failed for model %s: %s", target_model, exc)
            return None
        return None

    def evaluate_criterion(
        self,
        criterion_id: str,
        criterion_name: str,
        rubric_description: str,
        dialogue_transcript: str,
        scenario_goal: str,
        model_override: Optional[str] = None,
    ) -> HFJudgeVerdict:
        """Run independent LLM-as-a-judge evaluation for a specific rubric criterion."""
        used_model = model_override or self.evaluator_model
        if not self.is_configured():
            return HFJudgeVerdict(
                criterion_id=criterion_id,
                status="NOT_EVALUATED",
                confidence=0.0,
                rationale="Hugging Face LLM judge not configured (HF_TOKEN missing).",
                model_identifier=used_model,
                evaluation_status="skipped",
            )

        system_prompt = (
            "You are an impartial, strict LLM-as-a-Judge for AI voice agents. "
            "Evaluate whether the dialogue transcript satisfies the specific criterion. "
            "Output ONLY valid JSON in this exact structure with no extra text or markdown formatting:\n"
            "{\n"
            '  "verdict": "PASS" | "FAIL" | "INCONCLUSIVE",\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "rationale": "Concise factual reason citing observed quotes from dialogue",\n'
            '  "evidence_references": ["relevant quote 1", "relevant quote 2"]\n'
            "}"
        )

        user_content = (
            f"Scenario Business Goal: {scenario_goal}\n"
            f"Criterion [{criterion_id}]: {criterion_name}\n"
            f"Rubric: {rubric_description}\n\n"
            f"--- OBSERVED DIALOGUE EVIDENCE ---\n"
            f"{dialogue_transcript}\n"
            f"--- END DIALOGUE EVIDENCE ---\n\n"
            "Evaluate the evidence against the rubric. Output JSON."
        )

        raw_output = self.chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            model=used_model,
            temperature=0.0,
        )

        if not raw_output:
            return HFJudgeVerdict(
                criterion_id=criterion_id,
                status="INCONCLUSIVE",
                confidence=0.5,
                rationale="Hugging Face model response was empty or timed out.",
                model_identifier=used_model,
                evaluation_status="failed",
            )

        try:
            parsed = self._extract_json(raw_output)
            verdict_str = str(parsed.get("verdict", "INCONCLUSIVE")).upper()
            if verdict_str not in ("PASS", "FAIL", "INCONCLUSIVE"):
                verdict_str = "INCONCLUSIVE"
            return HFJudgeVerdict(
                criterion_id=criterion_id,
                status=verdict_str,
                confidence=float(parsed.get("confidence", 0.8)),
                rationale=str(parsed.get("rationale", "Evaluated by Hugging Face judge.")),
                evidence_references=list(parsed.get("evidence_references", [])),
                model_identifier=used_model,
                evaluation_status="completed",
            )
        except Exception as exc:
            logger.warning("Failed to parse Hugging Face judge output: %s. Raw: %s", exc, raw_output[:200])
            return HFJudgeVerdict(
                criterion_id=criterion_id,
                status="INCONCLUSIVE",
                confidence=0.4,
                rationale=f"Failed to parse model verdict JSON: {exc}",
                model_identifier=used_model,
                evaluation_status="parse_error",
            )

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        text = text.strip()
        # Remove markdown code fences if present
        if "```" in text:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
            if match:
                text = match.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        return json.loads(text)
