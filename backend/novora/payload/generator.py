import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, Optional
from novora.payload.models import PayloadGenerationRequest


class PayloadGenerator:
    """Generates provider-specific payloads using configured models (DeepSeek / Llama 3.3 8B Instruct)
    or schema-compliant fallback heuristics."""

    def __init__(
        self,
        hf_token: Optional[str] = None,
        model_id: str = "deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        hf_endpoint: Optional[str] = None,
    ) -> None:
        self.hf_token = hf_token or os.getenv("HUGGING_FACE_API_KEY")
        self.model_id = os.getenv("PAYLOAD_GENERATOR_MODEL", model_id)
        self.hf_endpoint = hf_endpoint or os.getenv("HUGGING_FACE_INFERENCE_ENDPOINT")

    def generate(
        self,
        request: PayloadGenerationRequest,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate provider-specific payload, incorporating any feedback from previous revision cycles."""
        # If user supplied custom JSON and no feedback revision is requested, start from custom JSON
        if request.custom_json and not feedback:
            payload = dict(request.custom_json)
            # Ensure provider agent ID is correctly set
            if request.provider == "vapi":
                payload["assistantId"] = request.agent_id
            elif request.provider == "retell" and "agent_id" not in payload:
                payload["agent_id"] = request.agent_id
            elif request.provider == "elevenlabs" and "agent_id" not in payload:
                payload["agent_id"] = request.agent_id
            return payload

        # Attempt model-based generation if HF token is present
        if self.hf_token and not os.getenv("DISABLE_MODEL_CALLS"):
            try:
                model_result = self._call_model_generator(request, feedback)
                if model_result and isinstance(model_result, dict):
                    return model_result
            except Exception:
                # Fall back safely to structured template generator
                pass

        # Robust schema-compliant generator based on target provider
        return self._generate_structured_payload(request, feedback)

    def _generate_structured_payload(
        self,
        request: PayloadGenerationRequest,
        feedback: Optional[str] = None,
    ) -> Dict[str, Any]:
        provider = (request.provider or "").lower().strip()
        agent_id = request.agent_id.strip()
        scenario_name = request.scenario.name if request.scenario else (request.scenario_id or "Voice Agent Evaluation")
        scenario_goal = request.scenario.business_goal if request.scenario else (request.user_instructions or "Evaluate agent behavior")
        user_prompt = request.user_instructions or scenario_goal

        if provider == "vapi":
            return {
                "assistantId": agent_id,
                "name": f"Vapi Eval — {scenario_name}",
                "transcriber": {
                    "provider": "deepgram",
                    "model": "nova-2",
                    "language": "en",
                },
                "model": {
                    "provider": "openai",
                    "model": "gpt-4o",
                    "messages": [
                        {
                            "role": "system",
                            "content": f"You are an evaluated assistant for {scenario_name}. Objective: {scenario_goal}. Instructions: {user_prompt}",
                        }
                    ],
                },
                "voice": {
                    "provider": "11labs",
                    "voiceId": "paula",
                },
                "firstMessage": f"Hello, thank you for calling. How can I assist you today with {scenario_name}?",
                "endCallMessage": "Thank you for contacting us. Have a wonderful day.",
                "serverUrl": "https://api.novora.internal/api/v1/webhooks/vapi",
                "analysisPlan": {
                    "summaryPlan": {"enabled": True},
                    "structuredDataPlan": {"enabled": True},
                    "successEvaluationPlan": {"enabled": True},
                },
                "metadata": {
                    "novora_evaluation": True,
                    "target_agent_id": agent_id,
                    "scenario": scenario_name,
                    "revision_note": feedback or "initial",
                },
            }

        elif provider == "retell":
            return {
                "agent_id": agent_id,
                "agent_name": f"Retell Eval — {scenario_name}",
                "voice_id": "11labs-Adrian",
                "llm_websocket_url": "wss://api.novora.internal/api/v1/webhooks/retell",
                "begin_message": f"Hello! Welcome to our support line regarding {scenario_name}.",
                "general_prompt": f"Goal: {scenario_goal}. User test instructions: {user_prompt}",
                "dynamic_variables": {
                    "customer_name": "Valued Customer",
                    "scenario_target": scenario_name,
                    "test_agent_id": agent_id,
                },
                "post_call_analysis_data": [
                    {"type": "string", "name": "resolution_status", "description": "Whether the caller issue was resolved"},
                    {"type": "boolean", "name": "verification_completed", "description": "Whether authentication occurred"},
                ],
                "metadata": {
                    "novora_evaluation": True,
                    "revision_note": feedback or "initial",
                },
            }

        elif provider == "elevenlabs":
            return {
                "agent_id": agent_id,
                "name": f"ElevenLabs Eval — {scenario_name}",
                "conversation_config": {
                    "agent": {
                        "prompt": {
                            "prompt": f"System goal: {scenario_goal}. Target test instructions: {user_prompt}",
                        },
                        "first_message": f"Hello, how can I help you today regarding {scenario_name}?",
                        "language": "en",
                    },
                    "tts": {
                        "voice_id": "21m00Tcm4TlvDq8ikWAM",
                    },
                },
                "metadata": {
                    "novora_evaluation": True,
                    "agent_id": agent_id,
                },
            }

        elif provider == "assemblyai":
            return {
                "sample_rate": 16000,
                "word_boost": ["verification", "refund", "support", scenario_name.lower()],
                "format_text": True,
                "speaker_labels": True,
                "speech_model": "best",
                "metadata": {
                    "agent_id": agent_id,
                    "scenario": scenario_name,
                },
            }

        else:
            return {
                "provider": provider,
                "agent_id": agent_id,
                "scenario": scenario_name,
                "instructions": user_prompt,
                "metadata": {"novora_evaluation": True},
            }

    def _call_model_generator(
        self,
        request: PayloadGenerationRequest,
        feedback: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Call Hugging Face Router API for DeepSeek / Llama model generation."""
        url = self.hf_endpoint or "https://router.huggingface.co/hf-inference/v1/chat/completions"
        system_content = (
            f"You are an expert AI Voice Infrastructure Engineer generating exact API payloads for {request.provider}. "
            "Return ONLY valid JSON matching the provider's exact API schema with no surrounding markdown or explanation."
        )
        user_content = (
            f"Generate a valid JSON payload for provider '{request.provider}' with agent ID '{request.agent_id}'.\n"
            f"Scenario: {request.scenario.name if request.scenario else request.scenario_id}\n"
            f"Objective: {request.scenario.business_goal if request.scenario else ''}\n"
            f"User Instructions: {request.user_instructions or ''}\n"
        )
        if feedback:
            user_content += f"\nPrevious review feedback to fix: {feedback}\n"

        body = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "max_tokens": 1000,
            "temperature": 0.2,
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
            # Clean markdown code blocks if present
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
