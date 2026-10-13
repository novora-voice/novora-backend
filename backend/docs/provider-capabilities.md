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
