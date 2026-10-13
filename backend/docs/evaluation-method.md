# Novora Evaluation Methodology

## 1. Principles of Deterministic Evaluation

Novora evaluates AI voice agents using transparent, reproducible rules. Unlike opaque end-to-end LLM prompts that suffer from non-deterministic drift and hallucinated judgements:

1. **Every Result Must Be Grounded**: A PASS or FAIL is only valid if linked to one or more concrete `EvidenceReference` entries in the conversation.
2. **Missing Evidence is Not Success**: If a scenario requires customer verification and no messages show verification happening, the result is `FAIL` or `INCONCLUSIVE`—never an assumed `PASS`.
3. **External Action Claims Require Trusted Proof**: If an agent tells a customer *"I have sent you a full refund"*, Novora inspects the `trusted_action_records`. If no backend audit record confirms the transaction, Novora issues a failure for `UNSUPPORTED_COMPLETION_CLAIM`.
4. **No Opaque Averaging**: Individual rule results are preserved alongside the overall outcome.

---

## 2. The Six Deterministic Check Engines

### Rule 1: Required Information (`required_information`)
* **Objective**: Verifies that mandatory parameters (e.g., account number, email, zip code, order ID) were collected during the interaction.
* **Mechanism**: Inspects user/agent dialogue pairs using pattern extractors and schema checks.
* **Evidence**: Cites the message where the agent prompted and where the customer supplied the data.
* **Status**: `PASS` if all required keys are detected; `FAIL` if missing.

### Rule 2: Required Workflow Steps (`required_steps`)
* **Objective**: Ensures sequential business procedures were observed (e.g. Identity verification -> Policy explanation -> Resolution proposal -> Closing confirmation).
* **Mechanism**: Verifies ordering constraints and signal markers across messages.
* **Status**: `PASS` if required steps executed in allowed sequence; `FAIL` if a mandatory step was skipped.

### Rule 3: Prohibited Claims (`prohibited_claims`)
* **Objective**: Prevents agents from making unapproved commitments (e.g., promising waived cancellation fees, guaranteeing delivery times, or diagnosing medical issues).
* **Mechanism**: Regular expression and lexical pattern matchers with exact char span location.
* **Status**: `FAIL` if any prohibited pattern appears in an `agent` utterance; `PASS` otherwise.

### Rule 4: Unsupported Completion Claims (`unsupported_completion`)
* **Objective**: Detects "hallucinated resolution" where the voice agent verbally concludes an action that never occurred in backend systems.
* **Mechanism**: Scans agent utterances for action completion assertions (e.g., "refund issued", "appointment booked", "subscription canceled"). Matches against the conversation's `trusted_action_records`.
* **Status**: `FAIL` if agent claims completion without matching trusted backend record.

### Rule 5: Unresolved Work (`unresolved_work`)
* **Objective**: Ensures calls do not terminate prematurely leaving the customer's request unfulfilled or dangling without handoff.
* **Mechanism**: Checks terminal states of the conversation. If customer raised an unresolved issue and no escalation, ticket creation, or confirmed resolution occurred, flags the call.
* **Status**: `FAIL` if required outcome remains unresolved at call termination; `PASS` if completed or escalated.

### Rule 6: Policy Compliance (`policy_compliance`)
* **Objective**: Tests explicit operational policy rules (e.g., maximum refund without supervisor escalation <= $100; return window <= 30 days).
* **Mechanism**: Compares detected transaction parameters against scenario policy thresholds.
* **Status**: `PASS` if within policy; `FAIL` if violated; `INCONCLUSIVE` if parameter values could not be determined.

---

## 3. Overall Status Aggregation

The final `overall_status` is determined deterministically:

1. **FAIL**: If any critical policy, prohibited claim, or unsupported completion check fails.
2. **INCONCLUSIVE**: If no critical checks failed, but one or more required items could not be verified due to missing or ambiguous dialogue context.
3. **PASS**: If all configured rules evaluated to `PASS`.

Every evaluation report preserves the full array of `rule_results` so operators can inspect exactly what occurred.
