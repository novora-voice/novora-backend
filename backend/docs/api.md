# Novora REST API Reference — v0.1

This document specifies the HTTP endpoints exposed by the Novora Backend API for evaluation orchestration, provider webhook ingestion, transcript import, and regression comparisons.

All requests accept and return `application/json` unless otherwise specified.

---

## 1. Scenarios

### `POST /api/v1/scenarios`
Create a new evaluation scenario with business goals and deterministic rule definitions.

**Request Body:**
```json
{
  "name": "Delayed Refund Policy Check",
  "business_goal": "Authenticate customer, verify order eligibility, enforce $50 credit limit",
  "success_criteria": [
    "Order ID collected",
    "No false completion claims",
    "Credit <= $50"
  ],
  "rules": [
    {
      "rule_type": "required_information",
      "name": "Collect Order ID",
      "parameters": {
        "required_fields": ["order_id"]
      }
    },
    {
      "rule_type": "policy_compliance",
      "name": "Enforce $50 Credit Cap",
      "parameters": {
        "max_refund_amount": 50.0
      }
    }
  ]
}
```

**Response (201 Created):**
`EvaluationScenario` object with assigned `id` and `created_at`.

### `GET /api/v1/scenarios/{scenario_id}`
Retrieve a scenario definition by ID.

### `GET /api/v1/scenarios`
List registered scenarios with pagination (`limit`, `offset`).

---

## 2. Evaluations & Regression Comparisons

### `POST /api/v1/evaluations`
Evaluate a normalized conversation against a scenario and persist the report.

**Request Body:**
```json
{
  "scenario_id": "scen_abc123",
  "conversation": {
    "id": "conv_xyz789",
    "messages": [
      {
        "id": "msg_001",
        "role": "customer",
        "content": "Hi, where is my order #9821?",
        "sequence": 0
      },
      {
        "id": "msg_002",
        "role": "agent",
        "content": "I am checking order #9821 now.",
        "sequence": 1
      }
    ],
    "trusted_action_records": []
  }
}
```

**Response (201 Created):**
`EvaluationReport` object containing `overall_status`, `summary`, `rule_results`, and message citations.

### `GET /api/v1/evaluations/{evaluation_id}`
Retrieve a persisted evaluation report.

### `GET /api/v1/evaluations?scenario_id={scenario_id}`
List all evaluation reports for a given scenario to inspect historical runs.

### `POST /api/v1/evaluations/compare`
Compare two evaluation runs (e.g. baseline vs candidate) to detect regressions or improvements.

**Request Body:**
```json
{
  "baseline_evaluation_id": "eval_base_001",
  "candidate_evaluation_id": "eval_cand_002"
}
```

**Response (200 OK):**
```json
{
  "scenario_id": "scen_abc123",
  "baseline_id": "eval_base_001",
  "candidate_id": "eval_cand_002",
  "baseline_status": "PASS",
  "candidate_status": "FAIL",
  "regression_detected": true,
  "net_status_change": "regressed",
  "rule_comparisons": [
    {
      "rule_name": "Enforce $50 Credit Cap",
      "rule_type": "policy_compliance",
      "baseline_status": "PASS",
      "candidate_status": "FAIL",
      "change": "regressed",
      "explanation_diff": "Offered amount ($120.00) violates policy limit of $50.00."
    }
  ]
}
```

---

## 3. Ingestion & Provider Webhooks

### `POST /api/v1/conversations/import-transcript`
Import a raw text or dialogue transcript and normalize it into a Novora `Conversation`.

**Request Body:**
```json
{
  "source": "transcript_upload",
  "scenario_id": "scen_abc123",
  "text": "Customer: Hi, I need help with order #9821.\nAgent: Hello! I can look that up for you.",
  "format": "dialogue_text"
}
```

**Response (200 OK):**
Normalized `Conversation` object ready for evaluation.

### `POST /api/v1/webhooks/elevenlabs`
Ingest ElevenLabs Conversational AI post-call webhook.
- **Headers**:
  - `elevenlabs-signature`: HMAC-SHA256 signature
  - `x-timestamp`: Unix timestamp of the request
- **Idempotency**: Automatic deduplication on `conversation_id`.
- **Response**: `{ "status": "processed", "conversation_id": "..." }` or `{ "status": "already_processed" }`.

### `POST /api/v1/webhooks/twilio`
Ingest Twilio telephony status or recording callbacks.
- **Headers**: `X-Twilio-Signature`
- **Body**: Form or JSON with `CallSid`, `CallStatus`, `RecordingUrl`, etc.
- **Response**: `{ "status": "recorded", "call_sid": "..." }`.

### `POST /api/v1/webhooks/assemblyai`
Ingest completed transcription webhook from AssemblyAI.
- **Body**: AssemblyAI transcript object with `id`, `text`, `utterances`.
- **Response**: `{ "status": "normalized", "conversation_id": "..." }`.

---

## 4. Providers & Integration Management

### `GET /api/v1/providers`
List supported providers (ElevenLabs, AssemblyAI, Vapi, Retell, Twilio) with manifests and supported capabilities.

### `POST /api/v1/integrations`
Create or update an API integration with masked server-side credential persistence.

### `POST /api/v1/integrations/{integration_id}/test-connectivity`
Verify live or simulated API connectivity and authentication for a configured provider.

### `GET /api/v1/agents?provider={provider_name}`
Discover or validate configured agents and assistant IDs for the provider.

---

## 5. Scenario Templates, Ghost-Caller Execution & Batches

### `GET /api/v1/scenarios/templates`
Retrieve built-in scenario templates:
- Customer Support & Receptionist
- Incident Response
- Language Practitioner

### `POST /api/v1/test-runs`
Execute a programmatic ghost-caller test conversation against a configured provider agent, capture observable events and tool calls, and run deterministic + LLM evaluations.

### `GET /api/v1/test-runs/{test_run_id}`
Retrieve execution status, normalized conversation events, tool calls, and final evaluation report.

### `POST /api/v1/batches`
Trigger a batch evaluation across multiple test cases and scenarios.

### `GET /api/v1/batches/{batch_id}`
Inspect overall batch progress, pass/fail counts, and partial failures.

