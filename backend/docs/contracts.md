# Novora Public Contracts & Interface Specification

## 1. Ownership Matrix

| Area | Primary Owner | Module Path | Contract Stability |
| :--- | :--- | :--- | :--- |
| Core Domain Models | Claude A | `novora.core.models` | Stable Public Contract |
| Deterministic Evaluators | Claude A | `novora.evaluation` | Internal to Core Engine |
| Scenario & Evaluation API | Claude A | `novora.api` | Stable Public Contract |
| Persistence Repositories | Claude A | `novora.adapters.repositories` | Core Storage Protocol |
| Voice Provider Adapters | Claude B | `novora.providers.voice` | Consumes `novora.core.models.Conversation` |
| LLM Judge Adapters | Claude B | `novora.providers.llm` | Consumes `novora.core.models.EvaluationScenario` |

---

## 2. Core Domain Data Contracts

External adapters written by Claude B must emit or conform to these data types.

### 2.1 ConversationMessage
Represents a single utterance in an interaction.

```python
class MessageRole(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"

class ConversationMessage(BaseModel):
    id: str = Field(description="Unique message identifier, e.g. msg_001")
    role: MessageRole
    content: str
    sequence: int = Field(ge=0, description="0-indexed order of utterance")
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
```

### 2.2 Conversation
Normalized conversation container produced by ingestion adapters or client requests.

```python
class ConversationSource(str, Enum):
    TRANSCRIPT_UPLOAD = "transcript_upload"
    VAPI_WEBHOOK = "vapi_webhook"
    RETELL_WEBHOOK = "retell_webhook"
    SYNTHETIC_FIXTURE = "synthetic_fixture"

class Conversation(BaseModel):
    id: str = Field(description="Unique conversation identifier, e.g. conv_100")
    scenario_id: Optional[str] = None
    source: ConversationSource = ConversationSource.TRANSCRIPT_UPLOAD
    messages: List[ConversationMessage]
    trusted_action_records: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Verified actions confirmed by backend systems (e.g. refund_receipt_id, booking_id)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

### 2.3 EvidenceReference
Traceable citation pointing back to the conversation.

```python
class EvidenceReference(BaseModel):
    message_id: str
    speaker: MessageRole
    sequence: int
    char_start: Optional[int] = None
    char_end: Optional[int] = None
    snippet: str
    note: Optional[str] = None
```

### 2.4 RuleResult & EvaluationStatus
Result of a discrete rule execution.

```python
class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

class RuleResult(BaseModel):
    rule_id: str
    rule_name: str
    rule_version: str = "1.0.0"
    status: RuleStatus
    explanation: str
    evidence: List[EvidenceReference] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)
```

### 2.5 EvaluationReport
The final output of an evaluation session.

```python
class OverallStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

class EvaluationReport(BaseModel):
    id: str = Field(description="Unique report identifier, e.g. eval_999")
    scenario_id: str
    conversation_id: str
    overall_status: OverallStatus
    summary: str
    rule_results: List[RuleResult]
    total_rules: int
    passed_rules: int
    failed_rules: int
    inconclusive_rules: int
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

---

## 3. Public REST API Endpoints

### `POST /api/v1/scenarios`
Register a repeatable evaluation scenario.

**Request:**
```json
{
  "name": "Delayed Refund Inquiries",
  "business_goal": "Authenticate customer, verify order eligibility, enforce refund processing rules",
  "success_criteria": [
    "Customer order ID collected",
    "Agent verified delay reason",
    "Agent does not claim refund is executed without backend verification"
  ],
  "rules_config": [
    {
      "rule_type": "required_information",
      "required_fields": ["order_id", "email_or_phone"]
    },
    {
      "rule_type": "prohibited_claims",
      "prohibited_patterns": [
        "guarantee an instant refund within 1 hour",
        "waive all bank processing fees"
      ]
    },
    {
      "rule_type": "unsupported_completion",
      "action_verbs": ["refunded", "processed your refund", "credited your account"],
      "requires_trusted_record": "refund_confirmation"
    }
  ]
}
```

**Response (201 Created):**
Returns `EvaluationScenario` entity with assigned `id` and `created_at`.

### `GET /api/v1/scenarios/{scenario_id}`
Returns the stored scenario or 404.

### `POST /api/v1/evaluations`
Submit a conversation against a scenario to execute evaluation.

**Request:**
```json
{
  "scenario_id": "scen_123",
  "conversation": {
    "id": "conv_456",
    "messages": [
      {
        "id": "msg_001",
        "role": "customer",
        "sequence": 0,
        "content": "Hi, where is my refund for order #9821?"
      },
      {
        "id": "msg_002",
        "role": "agent",
        "sequence": 1,
        "content": "Let me check that. Can you confirm your email address?"
      }
    ],
    "trusted_action_records": []
  }
}
```

**Response (200 OK):**
Returns `EvaluationReport`.

### `GET /api/v1/evaluations/{evaluation_id}`
Retrieves a previously computed evaluation report.
