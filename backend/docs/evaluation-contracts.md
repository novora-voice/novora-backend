# Novora Evaluation Contracts & Specification

## 1. Domain Entities & Evaluation Hierarchy

Novora evaluates AI voice agents using a unified, provider-agnostic representation.

### 1.1 Evaluation Hierarchy
```
Scenario (Business Context & Criteria)
  ├── Test Case (Scripted Conversation / Ghost Caller Dialogue)
  ├── Evaluation Criteria
  │     ├── Deterministic Rules (Phrase, Tool Call, Flow, Safety)
  │     └── LLM-as-Judge Rubrics (Semantic intent, Politeness, Process adherence)
  └── Execution Run
        ├── Normalized Events (Turns, Tool Invocations, Results)
        ├── Deterministic Check Results (PASS / FAIL / INCONCLUSIVE)
        ├── LLM Judge Results (PASS / FAIL / INCONCLUSIVE)
        └── Aggregated Evaluation Report
```

## 2. Rule Types & Severities

### Rule Types:
- `required_phrase`: Must contain specific phrase or regex concept.
- `prohibited_phrase`: Prohibited language, unauthorized guarantees, or policy violations.
- `required_information`: Information that must be captured from the user.
- `required_question`: Questions the agent must explicitly ask.
- `expected_tool_call`: Mandatory tool call execution with schema validation.
- `forbidden_tool_call`: Disallowed tool execution.
- `tool_argument_validation`: Argument verification against expected parameters.
- `tool_call_ordering`: Order-dependent tool call constraints.
- `tool_result_validation`: Agent response alignment with tool outputs.
- `required_escalation`: Escalation to human agent when criteria met.
- `required_confirmation`: Customer confirmation prior to irreversible action.
- `turn_constraints`: Minimum or maximum turn count.
- `policy_compliance`: Multi-turn structured business rule validation.
- `unsupported_completion`: Agent claiming action without trusted backend confirmation.

### Severities:
- `CRITICAL`: Immediate overall failure if violated. Never overridden by LLM judge.
- `HIGH`: Contributes to failure score.
- `MEDIUM`: Warning or quality degradation.
- `LOW`: Informational feedback.

## 3. Aggregation Policy

1. Any `CRITICAL` deterministic rule failure produces an overall `FAIL`.
2. A missing event or prematurely terminated provider session produces `INCONCLUSIVE`.
3. LLM judge provides semantic evaluation but cannot override a failed deterministic safety rule.
4. Final overall status is strictly one of `PASS`, `FAIL`, or `INCONCLUSIVE`.
