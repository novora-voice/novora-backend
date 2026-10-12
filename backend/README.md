# Novora — AI Voice-Agent Evaluation Platform

Novora is a modular AI voice-agent infrastructure platform that tests and verifies whether AI voice agents accomplish real business outcomes, follow company policy, and resolve customer issues with traceable evidence.

Built with Python and FastAPI using a clean modular monolith architecture.

---

## 1. Modular Architecture

```
novora/
├── core/                  # Domain models, enums, protocols
│   ├── enums.py           # MessageRole, RuleStatus, OverallStatus, RuleType
│   ├── models.py          # EvaluationScenario, Conversation, RuleResult, EvaluationReport
│   └── interfaces.py      # Abstract protocols for evaluators & repositories
├── evaluation/            # Deterministic rule engine & orchestrator
│   ├── engine.py          # EvaluationEngine orchestrator
│   └── rules/             # 6 deterministic rule engines
│       ├── required_info.py           # Rule 1: Required Information
│       ├── required_steps.py          # Rule 2: Sequential Workflow Steps
│       ├── prohibited_claims.py       # Rule 3: Prohibited Claims & Promises
│       ├── unsupported_completion.py  # Rule 4: Flag claims without backend verification
│       ├── unresolved_work.py         # Rule 5: Unresolved Work Detection
│       └── policy_compliance.py       # Rule 6: Quantitative Policy Limits
├── adapters/              # Persistence repositories 
│   └── repositories.py    # Thread-safe in-memory stores (Postgres-ready)
└── api/                   # REST API Layer 
    ├── main.py            # FastAPI Application & dependency injection
    └── schemas.py         # Pydantic request & response schemas
```

---

## 2. Running Automated Tests

Run the full pytest suite (19 automated unit, API, and regression tests):

```bash
python -m pytest -v
```

All tests execute in < 1 second.

---

## 3. Running the REST API

Launch the local development server:

```bash
uvicorn novora.api.main:app --reload --port 8000
```

Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### API Endpoints

- `POST /api/v1/scenarios` — Register a business evaluation scenario with rules.
- `GET /api/v1/scenarios/{scenario_id}` — Retrieve a scenario.
- `GET /api/v1/scenarios` — List registered scenarios.
- `POST /api/v1/evaluations` — Evaluate a conversation against a scenario and persist the report.
- `GET /api/v1/evaluations/{evaluation_id}` — Retrieve an evaluation report with message-level evidence.
- `GET /api/v1/evaluations?scenario_id=...` — Filter reports for a given scenario.
- `GET /health` — Health check endpoint.

---

## 4. Key Capabilities & Invariants

1. **Deterministic Traceability**:
   Every `RuleResult` contains `EvidenceReference` elements citing the exact `message_id`, `speaker`, character spans (`char_start`, `char_end`), and snippet.
2. **Missing Evidence Invariance**:
   Missing data never defaults to `PASS`. It yields `FAIL` or `INCONCLUSIVE`.
3. **Unsupported Completion Protection**:
   If an agent verbally claims an action was executed (e.g. *"I have processed your refund"*), Novora checks `conversation.trusted_action_records`. If no backend system confirms the action, the call is flagged with `UNSUPPORTED_COMPLETION` failure.
4. **Isolated Integration Contracts**:
   Upstream voice providers (Vapi, Retell, Twilio) convert payloads into the normalized `Conversation` contract, keeping core domain logic clean and decoupled.
