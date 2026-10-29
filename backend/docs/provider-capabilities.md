# Novora Provider Capabilities & Integration Matrix

Novora evaluates AI voice agents by ingesting interaction data from specialized infrastructure providers. Providers play distinct, non-interchangeable roles in the voice ecosystem.

---

## 1. Provider Role Taxonomy

| Role Category | Responsibility in Voice Ecosystem | Novora Integration Point | Providers Supported |
| :--- | :--- | :--- | :--- |
| **Voice-Agent Platform** | Orchestrates turn-taking, LLM dialog, tools, audio streaming, and conversation logic. | Ingests post-call conversation webhook, turn transcript, latency metrics, and tool execution logs. | **ElevenLabs** (Conversational AI), Retell, Vapi |
| **Telephony & Carrier** | Manages PSTN/SIP trunks, call routing, audio recording, duration, and status callbacks. | Ingests call events (`completed`, `busy`, `no-answer`) and secure recording callbacks. Kept separate from evaluation transcript. | **Twilio** |
| **Speech-to-Text & Audio Analysis** | Transcribes audio recordings with speaker diarization, word timestamps, and acoustic confidence. | Ingests asynchronous transcription results or triggers transcription of authorized telephony audio. | **AssemblyAI**, Deepgram (future) |
| **Model-Based Evaluator** | Optional external LLM judge for nuanced sentiment or multi-turn conversational ambiguity. | Isolated behind provider-neutral judge interface. Never treated as ground truth over deterministic checks. | **OpenAI** (future) |

---

## 2. Ingestion & Security Protocols

### 2.1 ElevenLabs Conversational AI Webhook
- **Event Type**: `post_call_transcription` / `conversation_completed`
- **Security**:
  - HMAC-SHA256 signature verification via `elevenlabs-signature` header.
  - Timestamp anti-replay check (reject requests with timestamp drift > 300 seconds).
- **Idempotency**:
  - Deduplication via `event_id` and `conversation_id`.
  - Stored in `processed_webhook_events` table. Duplicate events return `200 OK` with `status: "already_processed"`.
- **Normalization**:
  - Turns mapped to `ConversationMessage(role=agent|customer, content, sequence, timestamp)`.

### 2.2 Twilio Telephony Callbacks
- **Event Types**: Call Status Callback (`completed`, `in-progress`), Recording Callback.
- **Security**:
  - Signature validation using Twilio Auth Token and request parameters (`X-Twilio-Signature`).
- **Data Boundary**:
  - Call metadata (`CallSid`, `Duration`, `Caller`, `RecordingUrl`) stored in `TelephonyCallRecord`.
  - Telephony metadata is linked to conversations by `call_sid` or customer phone, but never conflated with evaluation dialogue.

### 2.3 AssemblyAI Audio Transcription
- **Event Type**: Transcription completion webhook.
- **Data Handling**:
  - Maps diarized utterances (`speaker A`, `speaker B`) to customer/agent roles using greeting heuristic or metadata role tags.
  - Produces standard `Conversation` with word-level or utterance-level confidence in `metadata`.

---

## 3. Provider Manifests & Category Classification

Novora classifies providers into:
- **`voice_provider`**: Directly models, generates, or transcribes voice audio/turns (ElevenLabs, AssemblyAI).
- **`infrastructure`**: End-to-end voice orchestrators and telephony middleware (Vapi, Retell, Twilio).

Each provider implements `ProviderAdapterContract` (`backend/novora/providers/base.py`):
- `get_declared_capabilities()`: Returns typed `ProviderManifest` containing:
  - `category`: `voice_provider` or `infrastructure`
  - `configuration_requirements`: Required API keys and credential keys
  - `supported_execution_modes`: e.g. `mock`, `replay`, `simulated`, `direct_api`
  - `supported_input_modes`: e.g. `audio`, `text`, `webhook_payload`
  - `supported_event_types`: e.g. `turn`, `tool_call`, `tool_result`, `transcript`
  - `ghost_caller_implemented`: Boolean indicating native ghost-caller support
  - `real_calls_or_paid_operations`: Boolean indicating whether live runs incur cost
- `validate_agent_id(agent_id)`: Enforces mandatory, non-empty, formatted external agent identifiers.
- `get_supported_execution_modes()`: Declares execution capabilities.

---

## 4. Hugging Face Inference Evaluation Client

Novora integrates directly with Hugging Face Inference API via `huggingface_hub.InferenceClient`:
- **Judge Model**: `deepseek-ai/DeepSeek-R1-Distill-Qwen-32B` (configurable via `HF_JUDGE_MODEL`)
- **Generator Model**: `meta-llama/Llama-3.1-8B-Instruct` (configurable via `HF_GENERATOR_MODEL`)
- **Evaluator Model**: `meta-llama/Llama-3.1-8B-Instruct` (configurable via `HF_EVALUATOR_MODEL`)
- **Features**:
  - Automated `<think>...</think>` tag stripping for reasoning models.
  - JSON schema enforcement and robust fallback extraction.
  - Graceful degradation when `HF_TOKEN` is unset or test isolation is active.

