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

class RuleType(str, Enum):
    REQUIRED_INFORMATION = "required_information"
    REQUIRED_STEPS = "required_steps"
    PROHIBITED_CLAIMS = "prohibited_claims"
    UNSUPPORTED_COMPLETION = "unsupported_completion"
    UNRESOLVED_WORK = "unresolved_work"
    POLICY_COMPLIANCE = "policy_compliance"
