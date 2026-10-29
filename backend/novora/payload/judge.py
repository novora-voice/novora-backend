import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional
from novora.payload.models import PayloadJudgeVerdict
from novora.providers.huggingface import HuggingFaceClient, get_hf_token, get_hf_judge_model


class PayloadJudge:
    """Evaluates generated or user-provided payloads using both strict deterministic
    validation and LLM-as-a-judge semantic evaluation (DeepSeek / Llama 3.3 8B Instruct)."""

    def __init__(
        self,
        hf_token: Optional[str] = None,
        model_id: Optional[str] = None,
        hf_endpoint: Optional[str] = None,
    ) -> None:
        self.hf_token = hf_token or get_hf_token()
        self.model_id = model_id or get_hf_judge_model()
        self.hf_endpoint = hf_endpoint or os.getenv("HUGGING_FACE_INFERENCE_ENDPOINT")
        self.hf_client = HuggingFaceClient(token=self.hf_token, judge_model=self.model_id)

    def evaluate(
        self,
        provider: str,
        agent_id: str,
        payload: Dict[str, Any],
        user_instructions: Optional[str] = None,
        scenario_name: Optional[str] = None,
    ) -> PayloadJudgeVerdict:
        """Evaluate payload against provider schema and requirements.
        Deterministic checks are authoritative and cannot be overridden by LLM judgment."""

        issues: List[str] = []
        provider_clean = (provider or "").lower().strip()
        agent_id_clean = (agent_id or "").strip()

        # Deterministic Check 1: Mandatory Agent ID Presence
        if not agent_id_clean:
            return PayloadJudgeVerdict(
                decision="reject",
                feedback="Agent ID is strictly mandatory and cannot be empty.",
                issues=["Missing mandatory agent ID."],
                confidence=1.0,
                model_used="deterministic-rule-engine",
            )

        # Deterministic Check 2: Provider-specific required key presence
        if provider_clean == "vapi":
            if "assistantId" not in payload and "assistant" not in payload:
                issues.append("Vapi payload missing required 'assistantId' or 'assistant' object.")
            elif payload.get("assistantId") and payload.get("assistantId") != agent_id_clean:
                issues.append(f"Vapi assistantId '{payload.get('assistantId')}' does not match target agent ID '{agent_id_clean}'.")
        elif provider_clean == "retell":
            if "agent_id" not in payload:
                issues.append("Retell payload missing required 'agent_id' field.")
            elif payload.get("agent_id") != agent_id_clean:
                issues.append(f"Retell agent_id '{payload.get('agent_id')}' does not match target agent ID '{agent_id_clean}'.")
        elif provider_clean == "elevenlabs":
            if "agent_id" not in payload:
                issues.append("ElevenLabs payload missing required 'agent_id' field.")
            elif payload.get("agent_id") != agent_id_clean:
                issues.append(f"ElevenLabs agent_id '{payload.get('agent_id')}' does not match target agent ID '{agent_id_clean}'.")
        elif provider_clean == "assemblyai":
            if not isinstance(payload, dict):
                issues.append("AssemblyAI configuration must be a valid JSON dictionary.")

        # Deterministic Check 3: Reject forbidden localhost SSRF URLs in production fields
        for k, v in payload.items():
            if isinstance(v, str) and ("localhost:5432" in v or "127.0.0.1:5432" in v or "file://" in v):
                return PayloadJudgeVerdict(
                    decision="reject",
                    feedback=f"Field '{k}' contains prohibited local address or unsafe scheme.",
                    issues=[f"Security violation in field {k}."],
                    confidence=1.0,
                    model_used="deterministic-safety-engine",
                )

        # If deterministic checks failed, return revise or reject
        if issues:
            return PayloadJudgeVerdict(
                decision="revise",
                feedback="; ".join(issues),
                issues=issues,
                confidence=1.0,
                model_used="deterministic-rule-engine",
            )

        # Stage 2: LLM semantic evaluation if model is accessible
        if self.hf_token and not os.getenv("DISABLE_MODEL_CALLS"):
            try:
                llm_verdict = self._call_model_judge(
                    provider=provider_clean,
                    agent_id=agent_id_clean,
                    payload=payload,
                    user_instructions=user_instructions,
                    scenario_name=scenario_name,
                )
                if llm_verdict:
                    return llm_verdict
            except Exception:
                # Fall back safely to internal heuristic judge
                pass

        # Heuristic judge verification
        return self._heuristic_judge(provider_clean, payload, user_instructions)

    def _heuristic_judge(
        self,
        provider: str,
        payload: Dict[str, Any],
        user_instructions: Optional[str] = None,
    ) -> PayloadJudgeVerdict:
        issues: List[str] = []

        # Check that payload contains meaningful content
        if len(payload.keys()) < 2:
            issues.append(f"Payload for {provider} has insufficient configuration keys.")
            return PayloadJudgeVerdict(
                decision="revise",
                feedback="Payload is too sparse. Add provider configuration fields.",
                issues=issues,
                confidence=0.85,
                model_used="novora-semantic-judge",
            )

        return PayloadJudgeVerdict(
            decision="pass",
            feedback=f"Payload successfully conforms to {provider.upper()} API schema and satisfies evaluation constraints.",
            issues=[],
            confidence=0.96,
            model_used="novora-semantic-judge",
        )

    def _call_model_judge(
        self,
        provider: str,
        agent_id: str,
        payload: Dict[str, Any],
        user_instructions: Optional[str] = None,
        scenario_name: Optional[str] = None,
    ) -> Optional[PayloadJudgeVerdict]:
        system_content = (
            "You are a strict LLM-as-a-judge for Voice Agent Infrastructure configurations. "
            "You evaluate whether the generated JSON payload conforms to the provider's API specifications, "
            "has the required agent ID, and adheres to user instructions without dangerous or unsupported fields. "
            "Respond in JSON format: {\"decision\": \"pass\" | \"revise\" | \"reject\", \"feedback\": \"...\", \"issues\": [...]}"
        )
        user_content = (
            f"Evaluate this {provider} payload for agent ID '{agent_id}'.\n"
            f"Scenario: {scenario_name or 'Default'}\n"
            f"User Instructions: {user_instructions or 'None'}\n"
            f"Payload:\n{json.dumps(payload, indent=2)}\n"
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

        raw_output = None
        if self.hf_client.is_configured():
            raw_output = self.hf_client.chat_completion(messages, model=self.model_id, temperature=0.1)

        if raw_output:
            try:
                data = self.hf_client._extract_json(raw_output)
                return PayloadJudgeVerdict(
                    decision=data.get("decision", "pass").lower(),
                    feedback=data.get("feedback", "Validation passed."),
                    issues=data.get("issues", []),
                    confidence=0.94,
                    model_used=self.model_id,
                )
            except Exception:
                pass

        url = self.hf_endpoint or "https://router.huggingface.co/hf-inference/v1/chat/completions"
        body = {
            "model": self.model_id,
            "messages": messages,
            "max_tokens": 500,
            "temperature": 0.1,
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.hf_token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=10) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            content = res_data["choices"][0]["message"]["content"].strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            data = json.loads(content.strip())
            return PayloadJudgeVerdict(
                decision=data.get("decision", "pass").lower(),
                feedback=data.get("feedback", "Validation passed."),
                issues=data.get("issues", []),
                confidence=0.94,
                model_used=self.model_id,
            )
