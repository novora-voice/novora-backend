from enum import Enum

class MessageRole(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"
    TOOL = "tool"

class RuleStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

class OverallStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"

class ConversationSource(str, Enum):
    TRANSCRIPT_UPLOAD = "transcript_upload"
    ELEVENLABS_WEBHOOK = "elevenlabs_webhook"
    TWILIO_WEBHOOK = "twilio_webhook"
    ASSEMBLYAI_WEBHOOK = "assemblyai_webhook"
    VAPI_WEBHOOK = "vapi_webhook"
    RETELL_WEBHOOK = "retell_webhook"
    SYNTHETIC_FIXTURE = "synthetic_fixture"

class RuleSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"

class TestRunStatus(str, Enum):
    __test__ = False
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RuleType(str, Enum):
    REQUIRED_INFORMATION = "required_information"
    REQUIRED_STEPS = "required_steps"
    PROHIBITED_CLAIMS = "prohibited_claims"
    UNSUPPORTED_COMPLETION = "unsupported_completion"
    UNRESOLVED_WORK = "unresolved_work"
    POLICY_COMPLIANCE = "policy_compliance"
    REQUIRED_PHRASE = "required_phrase"
    PROHIBITED_PHRASE = "prohibited_phrase"
    REQUIRED_QUESTION = "required_question"
    EXPECTED_TOOL_CALL = "expected_tool_call"
    FORBIDDEN_TOOL_CALL = "forbidden_tool_call"
    TOOL_ARGUMENT_VALIDATION = "tool_argument_validation"
    TOOL_CALL_ORDERING = "tool_call_ordering"
    TOOL_RESULT_VALIDATION = "tool_result_validation"
    REQUIRED_ESCALATION = "required_escalation"
    REQUIRED_CONFIRMATION = "required_confirmation"
    REQUIRED_CLOSING = "required_closing"
    TURN_CONSTRAINTS = "turn_constraints"
    CONVERSATION_COMPLETION = "conversation_completion"
    EVIDENCE_AVAILABILITY = "evidence_availability"
    TIMEOUT_EXECUTION_FAILURE = "timeout_execution_failure"
    LLM_SEMANTIC_RUBRIC = "llm_semantic_rubric"

