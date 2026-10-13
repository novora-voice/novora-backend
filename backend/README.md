# Novora — AI Voice-Agent Evaluation & Observability Platform

Novora is a modular AI voice-agent infrastructure platform that tests and verifies whether AI voice agents accomplish real business outcomes, follow company policy, and resolve customer issues with traceable evidence.

Built with Python and FastAPI using a clean modular monolith architecture.

---

## 1. Modular Architecture

```
novora/
├── core/                  # Domain models, enums, protocols
│   ├── enums.py           # MessageRole, RuleStatus, OverallStatus, RuleType, ConversationSource
│   ├── models.py          # EvaluationScenario, Conversation, RuleResult, EvaluationReport, RegressionReport
│   └── interfaces.py      # Abstract protocols for evaluators, repositories, telephony, webhooks
├── evaluation/            # Deterministic rule engine & regression diff comparator
│   ├── engine.py          # EvaluationEngine orchestrator
│   ├── comparator.py      # EvaluationComparator for baseline vs candidate diffs
│   └── rules/             # 6 deterministic rule engines
│       ├── required_info.py           # Rule 1: Required Information
│       ├── required_steps.py          # Rule 2: Sequential Workflow Steps
│       ├── prohibited_claims.py       # Rule 3: Prohibited Claims & Promises
│       ├── unsupported_completion.py  # Rule 4: Flag claims without backend verification
│       ├── unresolved_work.py         # Rule 5: Unresolved Work Detection
│       └── policy_compliance.py       # Rule 6: Quantitative Policy Limits
├── providers/             # Capability protocols for third-party systems
│   └── base.py            # VoiceAgentProvider, TelephonyProvider, TranscriptionProvider protocols
├── adapters/              # Persistence repositories and provider normalizers
│   ├── database.py        # SQLAlchemy models and SQLite/PostgreSQL repositories
│   ├── repositories.py    # Thread-safe in-memory stores for dev/test
│   └── providers/         # Provider payload adapters
│       ├── transcript_importer.py     # Parses raw text or JSON dialogue transcripts
│       ├── elevenlabs.py              # ElevenLabs webhook HMAC-SHA256 & idempotency
│       ├── twilio.py                  # Twilio call/recording status & X-Twilio-Signature
│       └── assemblyai.py              # AssemblyAI diarization & utterance mapping
└── api/                   # REST API Layer
    ├── main.py            # FastAPI Application & dependency injection
    └── schemas.py         # Pydantic request & response schemas
```

---

## 2. Running Automated Tests

Run the full pytest suite (36 automated unit, API, integration, and regression tests):

```bash
cd backend
python -m pytest -v
```

All 36 tests execute and pass cleanly.

---

## 3. Running the REST API

Launch the local development server:

```bash
cd backend
python -m uvicorn novora.api.main:app --app-dir . --reload --port 8000
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### API Endpoints

- `POST /api/v1/scenarios` — Register a business evaluation scenario with rules.
- `GET /api/v1/scenarios/{scenario_id}` — Retrieve a scenario.
- `GET /api/v1/scenarios` — List registered scenarios.
- `POST /api/v1/evaluations` — Evaluate a conversation against a scenario and persist the report.
- `GET /api/v1/evaluations/{evaluation_id}` — Retrieve an evaluation report with message-level evidence.
- `GET /api/v1/evaluations?scenario_id=...` — Filter reports for a given scenario.
- `GET /api/v1/scenarios/{scenario_id}/history` — Evaluation history for repeated scenario runs.
- `POST /api/v1/evaluations/compare` — Compare baseline vs candidate runs to detect regressions.
- `POST /api/v1/conversations/import-transcript` — Import dialogue text or JSON records.
- `POST /api/v1/webhooks/elevenlabs` — Ingest ElevenLabs webhook with HMAC validation and deduplication.
- `POST /api/v1/webhooks/twilio` — Ingest Twilio telephony call status & recording callbacks.
- `POST /api/v1/webhooks/assemblyai` — Ingest completed transcription results.
- `GET /api/v1/telephony/calls` — Query isolated telephony call records.
- `GET /health` — Health check endpoint.

---

## 4. Key Capabilities & Invariants

1. **Deterministic Traceability**:
   Every `RuleResult` contains `EvidenceReference` elements citing the exact `message_id`, `speaker`, character spans (`char_start`, `char_end`), and snippet.
2. **Missing Evidence Invariance**:
   Missing data never defaults to `PASS`. It yields `FAIL` or `INCONCLUSIVE`.
3. **Unsupported Completion Protection**:
   If an agent verbally claims an action was executed (e.g. *"I have processed your refund"*), Novora checks `conversation.trusted_action_records`. If no backend system confirms the action, the call is flagged with `UNSUPPORTED_COMPLETION` failure.
4. **Idempotent Webhooks & Anti-Replay**:
   Incoming webhooks are deduplicated using provider event IDs and verified against timestamp drift.
5. **Telephony Data Isolation**:
   Twilio call metadata (`CallSid`, `Duration`, `RecordingUrl`) is kept in separate telephony records and never conflated with evaluation dialogue.
