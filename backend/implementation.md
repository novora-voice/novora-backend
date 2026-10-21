# NOVORA — COMPREHENSIVE BACKEND UPGRADE COMMAND

## Principal AI Engineer | Provider Evaluation Engine | Ghost Caller | Automated Voice-Agent Testing Sandbox

### 0. NON-NEGOTIABLE COMMANDS

**Work exclusively in the `feat/provider-evaluation-engine` branch.**

**DO NOT CHANGE THE EXISTING FRONTEND DESIGN.**

**ONLY ADD THE NEW FEATURES AND THE MINIMUM FUNCTIONAL WIRING REQUIRED TO SUPPORT THEM.**

## MAKE USE OF HUGGING FACE INFERENCE CLIENT PROVIDERS

The existing frontend design is approved and must remain unchanged.

Do not redesign, restyle, replace, or unnecessarily refactor the frontend.

Do not change the existing:

- Colors, typography, spacing, and visual hierarchy.
- Sidebar, navigation, or page structure.
- Cards, tables, buttons, modals, or existing components' visual styling.
- Layout, responsive behavior, or animations.
- Dashboard appearance or existing design system.

New functionality must use existing components and styles. Add only the controls, fields, steps, modal content, provider labels, and status indicators required for the new features.

The backend is the primary scope of this task.

Before making changes, run:

```bash
git status
git branch --show-current
```

Confirm the current branch is `feat/provider-evaluation-engine`. If it is not, stop rather than switching branches unsafely or modifying another branch.

Preserve uncommitted changes. Never reset, discard, or overwrite unrelated work. Do not merge into `main` or the frontend branch.

**Do not rebuild Novora from scratch. Audit the repository first and extend the existing implementation.**

---

## 1. PRODUCT VISION

Novora is an automated pre-flight testing, evaluation, and regression-testing sandbox for AI voice agents.

The product should let a developer describe what they want to test in plain English, configure an agent and scenario, execute a supported test, inspect the agent's actual behavior, and determine whether the behavior meets their requirements.

The developer should not need to manually place repeated phone calls just to discover whether a configuration, tool, prompt, or backend integration has broken.

The central promise is:

**Write what you want to test. Run the test. Observe the agent. Verify the outcome.**

Novora should support two distinct testing paths.

### Path A — Model and voice-agent testing

For ElevenLabs and AssemblyAI, Novora acts as a ghost caller where the provider's documented interface supports automated conversation testing.

Novora connects through the supported interface, supplies the test input, captures actual events and responses, and evaluates the interaction.

### Path B — Pipeline and orchestration testing

For Vapi and Retell, Novora tests supported agent execution, tool/webhook contracts, integrations, and business workflows.

Where the provider offers a suitable agent execution or simulation interface, use it to test the actual configured agent.

Where the user explicitly wants to test a webhook contract directly, generate a provider-specific test payload and submit it to the configured test endpoint.

**Never confuse direct webhook testing with testing a complete live voice conversation.** Label the execution mode accurately and report what was actually tested.

The two paths must reuse Novora's common scenario, evaluation, evidence, persistence, and reporting systems.

---

## 2. REPOSITORY AUDIT AND PRESERVATION

Before writing code:

1. Inspect the current branch, repository structure, README, dependencies, environment configuration, and Git status.
2. Identify the current backend framework, API routes, database, migrations, queue system, and authentication model.
3. Find existing ElevenLabs, AssemblyAI, Vapi, and Retell integrations.
4. Trace the existing evaluation execution path from request to report.
5. Inspect existing scenario storage, templates, evaluation criteria, provider configuration, WebSocket handling, and LLM integrations.
6. Identify the source of the error:

   `Scenario with id 'scen_refund_cap' not found. Cannot evaluate.`

7. Determine whether the issue comes from a missing database record, hardcoded identifier, stale frontend reference, incorrect ownership scope, or broken scenario persistence.
8. Preserve all working functionality and established conventions.
9. Identify existing components that can be reused rather than introducing duplicate abstractions.
10. Write a concise implementation plan before making major changes.

Create or update the following documentation as needed:

- `docs/architecture.md`
- `docs/provider-capabilities.md`
- `docs/evaluation-contracts.md`
- `docs/api.md`
- `docs/testing-strategy.md`

Documentation must describe implemented behavior accurately. Never document a provider feature as working merely because an adapter class or UI entry exists.

---

## 3. PROVIDER CATEGORIES

On the existing Agents page, separate the providers into two groups without redesigning the page.

### Voice Providers

- ElevenLabs
- AssemblyAI

### Infrastructure Providers

- Vapi
- Retell

Use the existing visual design to add the two group labels. Preserve the current provider cards and their behavior.

Expose provider metadata from the backend, including:

- Provider identifier.
- Display name.
- Category.
- Configuration requirements.
- Actual connection status.
- Supported execution modes.
- Supported input modes.
- Supported event types.
- Whether the relevant ghost-caller workflow is implemented and tested.
- Whether direct webhook contract testing is supported.
- Whether real calls or paid operations may occur.

Do not assume the categories mean the providers have identical execution protocols. The categories organize the product; the adapters handle technical differences.

---

## 4. SHARED ARCHITECTURE

Implement or refine a provider-neutral testing engine using the repository's existing architecture.

The execution pipeline should follow this pattern:

```text
User configuration
        ↓
Scenario and test instructions
        ↓
Agent configuration validation
        ↓
Execution-mode selection
        ↓
Provider-specific adapter
        ↓
Actual provider events or HTTP response
        ↓
Normalized evidence
        ↓
Deterministic evaluation
        ↓
LLM-as-a-judge evaluation
        ↓
Result aggregation
        ↓
Persisted report and evaluation history
```

For Vapi and Retell payload generation, add the separate preparation pipeline described below before the relevant execution stage.

### Shared responsibilities

Reuse the same core for:

- Scenario and test-case management.
- Test instructions and configuration validation.
- Provider-neutral execution orchestration.
- Event normalization.
- Deterministic rules.
- User-defined LLM evaluation rubrics.
- LLM-as-a-judge orchestration.
- Evidence references.
- Evaluation aggregation.
- Run history and reporting.
- Batch execution and partial-failure handling.
- Error classification and audit logging.

### Provider-specific responsibilities

Keep these isolated in adapters:

- Authentication.
- Agent identification and configuration.
- Connection and session initialization.
- Supported input delivery.
- Audio encoding where required.
- WebSocket event handling.
- Tool-call and tool-result extraction.
- Webhook request construction.
- Provider-specific payload schemas.
- Final artifact retrieval.
- Provider-specific errors, limits, and retries.

Reuse existing working adapters wherever possible. Do not copy the evaluation engine four times.

---

## 5. DEFINE A STRICT PROVIDER CONTRACT

Define a typed, documented contract that all provider adapters must implement where applicable.

The contract should cover:

- Provider identity and declared capabilities.
- Configuration validation.
- Agent identification.
- Supported execution modes.
- Session creation and lifecycle.
- Supported input submission.
- Event collection.
- Transcript retrieval.
- Tool-call and tool-result observation.
- Completion and error handling.
- Final artifact retrieval.
- Cancellation and timeouts where supported.
- Explicit unsupported-capability reporting.

Normalize actual provider events into a common internal model with fields such as:

- `event_id`
- `run_id`
- `provider`
- `event_type`
- `sequence_number`
- `occurred_at`
- `speaker`
- `text`
- `tool_name`
- `tool_arguments`
- `tool_result`
- `status`
- `raw_payload_reference`

Optional fields must remain optional. Do not invent missing information.

Retain useful raw evidence securely, redact secrets, and distinguish actual observations from derived interpretations.

Every provider adapter must pass the shared contract tests applicable to its declared capabilities.

---

## 6. STEP-BY-STEP EVALUATION WORKFLOW

The user's workflow must be sequential, explicit, and enforced by the backend.

The expected sequence is:

1. Choose an evaluation type and provider.
2. Configure the agent.
3. Create a scenario or choose an existing scenario.
4. Define what to test.
5. Add deterministic rules.
6. Add LLM evaluation criteria.
7. Generate and validate any required provider payload.
8. Execute the selected test mode.
9. Evaluate the captured evidence.
10. Review the results.

The backend must validate prerequisites before advancing.

If a required field is missing, return a structured validation error and preserve the user's existing configuration.

The existing frontend should expose these steps using its current design. Do not redesign the entire workflow or introduce an unrelated UI framework.

---

## 7. AGENT CONFIGURATION

The user controls their agent configuration.

**An agent ID is mandatory before an evaluation can execute.**

Depending on the provider and execution mode, the configuration may include:

- Provider.
- Agent ID.
- Assistant ID, if distinct and required.
- Credential reference.
- Test endpoint URL for direct webhook tests.
- Environment.
- Provider-specific settings.
- Optional test constraints.

Do not require fields that are irrelevant to a particular provider or execution mode.

Never expose provider secrets to the browser.

Validate configuration on the backend before running the evaluation.

If the agent ID is missing, return an error such as:

```json
{
  "code": "AGENT_ID_REQUIRED",
  "message": "An agent ID is required before running an evaluation."
}
```

A configured agent ID must not automatically be treated as proof that the provider connection works. Validate the connection or execution configuration where the provider supports verification.

---

## 8. SCENARIO CREATION AND SELECTION

Every evaluation must reference a valid, persisted scenario.

Fix the existing failure:

`Scenario with id 'scen_refund_cap' not found. Cannot evaluate.`

Investigate the actual root cause. Remove any invalid hardcoded assumptions, stale identifiers, or fake scenario references.

Do not silently create an evaluation scenario from a missing ID.

Do not fabricate successful scenario retrieval.

### If the user has no scenarios

Return a clear, actionable state:

`Create a scenario before running an evaluation, or choose an existing scenario if one is available.`

Expose the appropriate create/select workflow through the existing frontend.

### If the user already has scenarios

Allow the user to choose a previously created scenario.

The selection modal should communicate:

**Choose an existing scenario to test, or create a new scenario first.**

Validate scenario existence and ownership on the backend when the user submits the evaluation request.

If the scenario does not exist or the user lacks permission to access it, return an appropriate error and prevent execution.

### Scenario fields

Support the appropriate equivalent of:

- ID.
- Name.
- Description.
- Business goal.
- User instructions.
- Test inputs.
- Expected behaviors.
- Prohibited behaviors.
- Deterministic rules.
- LLM evaluation criteria.
- Provider constraints.
- Creator/workspace ownership.
- Created and updated timestamps.
- Version.

Use the existing data model where possible.

Snapshot the scenario, test inputs, rules, and LLM rubric at run time so historical reports remain reproducible.

---

## 9. TEMPLATE OR CUSTOM JSON

When creating a scenario, the user must be able to choose either a template or custom JSON instructions.

### Option A — Existing template

Support the existing or newly implemented templates:

**Customer Support and Receptionist**

Test intent understanding, information gathering, policy adherence, tool usage, issue resolution, routing, and closing behavior.

**Incident Response**

Test incident recognition, information collection, severity handling, permitted tool use, escalation, and next-step confirmation.

**Language Practitioner**

Test configured language use, proficiency level, corrections, exercise adherence, and response to misunderstandings.

Templates are editable starting points. They must not prevent users from defining their own scenarios.

### Option B — Custom JSON

Allow users to supply a valid JSON configuration containing their instructions, business goal, test inputs, expected behavior, and relevant criteria.

Example:

```json
{
  "goal": "Determine whether the customer qualifies for a refund.",
  "instructions": [
    "Ask for the customer's order number.",
    "Verify the refund policy.",
    "Do not promise a refund before eligibility is confirmed."
  ]
}
```

Validate the JSON schema, required fields, data types, size limits, and provider-specific restrictions where applicable.

Return actionable validation errors. Do not silently rewrite malformed JSON or discard user instructions.

Store the user's original configuration and any normalized representation separately when needed.

Treat custom JSON and instructions as untrusted input. They must never override system-level security rules.

---

## 10. USER-DEFINED TEST INSTRUCTIONS

The user must be able to describe exactly what they want to test in plain English.

Examples:

- "Ask the agent for a refund after explaining that the product arrived damaged."
- "Ask the receptionist to reschedule an appointment and verify whether it collects all required information."
- "Report a failed payment and check whether the agent follows the configured escalation policy."
- "Tell the agent that a support ticket was never received and verify that it does not falsely claim the issue is resolved."

Persist the original user instructions with the evaluation run.

Do not replace them with generic template instructions unless the user chooses to use those instructions.

If a template is selected, combine it with the user's modifications according to an explicit, documented precedence rule. Never silently discard the user's requirements.

---

## 11. GHOST CALLER EXECUTION

Novora must act as an automated caller/customer simulator.

Where the provider supports the necessary interface, Novora should:

1. Establish a supported connection or session.
2. Send the user's test inputs.
3. Receive actual agent responses and events.
4. Observe tool calls and results when available.
5. Stop according to explicit completion, turn limits, cancellation, or timeout.
6. Persist the interaction evidence.
7. Run the configured evaluations.

The user chooses what the ghost caller says.

Novora should not invent the agent's responses or report an unexecuted test as completed.

If a provider requires audio, use the supported audio-input workflow. If it supports text injection, use the documented text-input mechanism. If neither method is supported for the selected configuration, report the limitation and offer a supported execution mode where available.

### Execution-mode distinctions

Represent execution modes explicitly, for example:

- Provider-supported conversation test.
- Direct webhook contract test.
- Offline/mock test.

The UI and report must state which mode was used.

A direct webhook test may validate payload shape, endpoint behavior, latency, and returned results. It does not prove that the full voice agent correctly interpreted a conversation unless the actual agent execution path was exercised.

---

## 12. ELEVENLABS ADAPTER

Audit and reuse the existing ElevenLabs implementation.

Use official documentation:

- https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket
- https://elevenlabs.io/docs/eleven-agents/customization/events/client-to-server-events
- https://elevenlabs.io/docs/eleven-agents/libraries/web-sockets

Where supported, use the documented WebSocket interface and `user_message` event for text input.

Implement or repair:

- Agent identification and configuration.
- Credential validation.
- Session initialization.
- Supported test input submission.
- Transcript and response collection.
- Tool-call and tool-result collection where available.
- Session completion.
- Error and disconnect handling.
- Event normalization.
- Evaluation and report persistence.

Do not duplicate a working WebSocket client.

Do not assume a tool invocation succeeded merely because the model requested it.

### Acceptance test

With mocked provider events, verify the entire workflow without live credentials.

With approved test credentials, run an opt-in live test that:

1. Connects to a configured test agent.
2. Submits the user-defined test input.
3. Receives actual events.
4. Captures available evidence.
5. Runs deterministic and LLM evaluation.
6. Persists the report.
7. Retrieves the report through the API.

Record whether the workflow was mock-tested or live-verified.

---

## 13. ASSEMBLYAI ADAPTER

Reuse the shared ghost-caller runtime, event model, evaluator, and reporting system.

Official documentation:

- https://www.assemblyai.com/docs/voice-agents/voice-agent-api
- https://www.assemblyai.com/docs/voice-agents/voice-agent-api/events-reference

Implement the documented Voice Agent API protocol.

Do not assume it uses the same input events as ElevenLabs.

In particular, do not introduce an undocumented `text_input` event merely to make the adapters look identical.

Where audio is required:

1. Accept the user's text-based test instructions.
2. Convert them to audio using an appropriate supported method or configured audio fixtures.
3. Apply the provider's documented audio encoding and session requirements.
4. Submit input only after the required session handshake.
5. Capture transcripts, agent responses, tool calls/results, interruptions, completion, and errors where available.
6. Normalize the evidence.
7. Reuse the same evaluation engine and reporting pipeline.

Keep audio-specific behavior inside the AssemblyAI adapter.

If the existing application already has an audio generation or fixture pipeline, reuse it.

Do not claim that a text-only simulation ran if the provider required audio and no valid audio input was submitted.

---

## 14. VAPI AND RETELL: PAYLOAD GENERATION AND VALIDATION

For Vapi and Retell, implement the requested payload-generation workflow for supported execution modes.

The user may supply:

- Agent ID.
- Provider selection.
- Scenario.
- Plain-English test instructions.
- Custom JSON configuration.
- Expected tool behavior.
- Provider-specific settings.
- An approved test endpoint for direct webhook testing, if applicable.

The payload must be generated according to the selected provider's actual API or webhook contract.

Do not use one generic payload structure for both providers.

Verify the current provider documentation before implementing or updating payload schemas:

- Vapi: https://docs.vapi.ai/
- Retell: https://docs.retellai.com/llms.txt

### Payload pipeline

Implement the following controlled process:

```text
User instructions and configuration
                ↓
Provider-specific payload generator
                ↓
Generated payload
                ↓
Schema and contract validator
                ↓
Independent LLM payload reviewer
                ↓
          Is it valid?
           /       \
         YES        NO
          ↓          ↓
    Execution     Correction
                     ↓
              Revalidate payload
```

The payload must be generated based on the selected provider, agent ID, supported operation, scenario, and user's instructions.

### Important distinction

Use a deterministic schema/contract validator as the authoritative check for structural validity, required fields, allowed values, and types.

Use the LLM reviewer as a semantic quality gate to check whether the generated payload accurately represents the user's intent and selected provider operation.

**The LLM reviewer must not override a deterministic schema failure.**

A payload that is syntactically valid but semantically inconsistent with the user's instructions must not be executed without correction.

### Payload generation requirements

The generator should receive:

- Selected provider.
- Relevant official or repository-maintained provider schema.
- Provider capabilities.
- Agent ID.
- Execution mode.
- Scenario snapshot.
- User instructions.
- Custom JSON, when supplied.
- Expected behavior.
- Allowed operations and constraints.

Return structured output containing the proposed payload and a concise explanation of how it maps to the user's request.

Validate generated JSON before attempting to use it.

Do not let the model invent unsupported fields or fabricate an agent ID.

### Correction loop

If validation or semantic review fails:

1. Return the specific validation errors to the generator.
2. Ask it to revise the payload while preserving the user's original intent.
3. Validate the revised payload again.
4. Repeat only up to a configurable maximum number of revisions.
5. If the maximum is reached, mark the payload preparation as failed and return actionable errors.

Never create an infinite generation loop.

Never execute a payload that fails required validation.

Persist the revision count and final validation result. Store revision artifacts only as needed for debugging and auditing.

### Execution safety

Before dispatching a generated payload:

- Verify the target and execution mode.
- Confirm required credentials and agent configuration.
- Validate the endpoint or provider operation.
- Enforce timeouts and response-size limits.
- Prevent server-side request forgery by restricting endpoint destinations and blocking private or otherwise prohibited targets unless explicitly supported and safely authorized.
- Prevent unauthorized calls, destructive operations, and unintended production side effects.
- Require explicit confirmation where the selected operation can incur charges or contact real users.

Do not execute a webhook payload against an arbitrary URL supplied by the user without appropriate validation and authorization.

### Evidence after execution

Capture the actual response, HTTP status, latency, relevant headers, structured errors, and provider artifacts where available.

Do not treat HTTP 200 alone as proof that the business objective succeeded.

The evaluator must assess the actual result against the expected outcome.

---

## 15. HUGGING FACE LLM-AS-A-JUDGE

Use Hugging Face-hosted models as the supported model source for LLM-as-a-judge evaluation, using the repository's existing LLM integration patterns where possible.

The requested models are:

- DeepSeek model.
- Llama 3.3 8B model.

Do not assume a particular model identifier or provider endpoint without verifying availability and compatibility. Configure the exact model IDs through environment variables or backend settings, and document the verified defaults.

For example, define configurable settings such as:

- `HF_TOKEN`
- `HF_JUDGE_MODEL`
- `HF_GENERATOR_MODEL`
- `HF_EVALUATOR_MODEL`

Use separate generator and judge configuration where the architecture requires different models or roles.

The application must not expose Hugging Face tokens to the frontend.

### Model roles

Use the configured DeepSeek and Llama 3.3 8B models for the generator and evaluator roles according to the supported deployment configuration.

Prefer separating generation from judging so the judge independently assesses the generator's output.

The system must support model configuration without requiring code changes.

If a model is unavailable, rate-limited, incompatible with the selected endpoint, or unconfigured, report that condition explicitly. Do not silently substitute an unrelated model while claiming the requested model was used.

### LLM judge responsibilities

Evaluate:

- Whether the agent understood the user's intent.
- Whether the agent followed the scenario instructions.
- Whether required information was collected.
- Whether the response was relevant and clear.
- Whether the agent followed configured policies.
- Whether the agent resolved or appropriately escalated the issue.
- Whether the required tool behavior occurred.
- Whether the returned business result matches the expected outcome.
- Whether the generated provider payload represents the user's intended test.

Use structured JSON output validated against a schema.

Each result should include:

- Criterion ID.
- Verdict.
- Concise rationale.
- Evidence references.
- Confidence, if supported by the selected model and output schema.
- Model identifier.
- Evaluation status.

Do not store hidden chain-of-thought. Persist concise explanations and evidence-backed conclusions.

Treat user instructions, transcripts, tool results, provider responses, and generated payloads as untrusted data. Prompt injection inside those inputs must never override judge instructions or authorize tool execution.

---

## 16. USER-DEFINED DETERMINISTIC RULES

Users must be able to add their own deterministic evaluation rules.

Add the minimum necessary control to the existing UI, such as an **Add Deterministic Rule** button, using existing styling.

The backend must support creating, validating, storing, editing, and executing user-defined rules.

Supported rule types should include, where appropriate:

- Required phrase or keyword.
- Prohibited phrase or keyword.
- Required information collected.
- Required question asked.
- Expected tool call.
- Forbidden tool call.
- Tool argument matches a specified value or schema.
- Required tool result.
- Required escalation.
- Required confirmation.
- Maximum turns or duration.
- Required final response or next step.
- Latency threshold.
- HTTP status or response-field expectation for direct webhook tests.

Use a typed rule schema rather than accepting arbitrary executable Python or JavaScript.

For each rule, persist:

- Rule ID.
- Name.
- Description.
- Rule type.
- Configuration.
- Severity.
- Whether it is required.
- Applicable execution modes.
- Creation and update timestamps.

Validate rules before running an evaluation.

Return `PASS`, `FAIL`, or `INCONCLUSIVE` with evidence references.

Critical failures must remain visible even when the LLM judge produces a favorable result.

---

## 17. USER-DEFINED LLM EVALUATIONS

Users must also be able to define custom LLM evaluation criteria.

Add the minimum necessary **Add LLM Evaluation** control using the existing frontend design.

Users should be able to define criteria in natural language, such as:

- "Check whether the agent apologized before offering a resolution."
- "Check whether the agent gathered all required customer details."
- "Check whether the agent clearly explained why the refund was denied."
- "Check whether the agent followed the escalation policy."
- "Check whether the agent avoided claiming that an action succeeded without evidence."

Persist these criteria with the scenario and snapshot them for each evaluation run.

The judge must evaluate each criterion independently using the available conversation and tool evidence.

Each result must include a verdict, concise explanation, evidence references, and an explicit inconclusive state when the evidence is insufficient.

Do not permit custom evaluation instructions to override security rules, alter the provider configuration, or execute arbitrary tools.

---

## 18. EVALUATION EXECUTION AND RESULT AGGREGATION

When a run starts:

1. Validate user/workspace access.
2. Validate the provider and agent configuration.
3. Confirm that the scenario exists and is accessible.
4. Snapshot the scenario and evaluation criteria.
5. Validate the execution mode.
6. Generate and validate any required payload.
7. Execute the supported provider or webhook test.
8. Persist actual events and response evidence.
9. Run all configured deterministic rules.
10. Run all configured LLM evaluation criteria.
11. Aggregate the outcomes.
12. Persist and expose the final report.

Keep these results separate:

- Execution status.
- Payload preparation status.
- Deterministic results.
- LLM judge results.
- Aggregate evaluation outcome.
- Warnings and errors.

Use a documented, conservative aggregation policy.

A critical deterministic failure cannot be overturned by a favorable LLM verdict.

If the run failed before sufficient evidence was captured, report an execution failure or inconclusive result as appropriate.

If the LLM judge fails, retain the deterministic results and report the judge failure separately. Never invent a successful LLM evaluation.

A successful transport connection or HTTP response is not sufficient to declare the business objective achieved.

---

## 19. DATABASE, VERSIONING, AND HISTORY

Inspect the current database schema and migrations before making changes.

Extend existing models where possible.

Ensure the existing schema or its minimal extension can persist:

- Provider integrations.
- Agent configurations.
- Scenarios and versions.
- Test instructions.
- Deterministic rules.
- LLM evaluation criteria.
- Evaluation runs.
- Payload-generation attempts.
- Payload-validation results.
- Normalized events.
- Tool calls and results.
- Deterministic evaluation results.
- LLM judge results.
- Aggregate reports.
- Batch runs and per-run outcomes.
- Execution errors and relevant metadata.

Enforce ownership and workspace isolation at the API and data-access layers.

Store scenario and criteria snapshots for historical reproducibility.

Do not create duplicate tables for existing concepts.

Do not introduce a new database or queue unless the audit demonstrates a concrete need.

Use migrations and indexes appropriate to the query patterns.

---

## 20. API CONTRACTS

Audit the existing API and preserve current route conventions.

Ensure the backend exposes the equivalent functionality for:

- Listing providers and actual capabilities.
- Configuring and validating provider integrations.
- Configuring an agent.
- Listing, creating, updating, and retrieving scenarios.
- Selecting a scenario for evaluation.
- Managing templates and custom JSON.
- Managing deterministic rules.
- Managing LLM evaluation criteria.
- Generating and validating a provider payload.
- Starting an evaluation run.
- Retrieving run status and progress.
- Retrieving transcripts and event evidence.
- Retrieving deterministic and LLM results.
- Retrieving reports and history.
- Starting and retrieving batch evaluations.

Use the existing FastAPI request and response patterns.

Validate inputs with typed schemas.

Return consistent, actionable error responses.

Do not break existing API contracts without documenting the change and checking compatibility with the current frontend.

---

## 21. SECURITY AND SAFETY

Implement or preserve:

- Server-side secret storage.
- Credential masking.
- Authentication and authorization.
- Workspace isolation.
- Provider payload validation.
- Strict schema validation.
- SSRF protections for user-supplied test endpoints.
- Request timeouts and response-size limits.
- Safe logging and redaction.
- Webhook signature verification where supported.
- Idempotency for retried requests and duplicate events.
- Read-only or sandboxed defaults for tool execution.
- Explicit confirmation for potentially expensive or destructive live operations.
- Protection against prompt injection in transcripts and JSON.
- Bounded retries and bounded LLM correction loops.

Never execute arbitrary code supplied in custom JSON or evaluation criteria.

Never let the LLM judge or payload generator bypass deterministic validation or authorization.

Never log private credentials or expose them to the browser.

---

## 22. TESTING REQUIREMENTS

Testing is mandatory.

### A. Provider contract tests

Create reusable tests for each adapter covering:

- Configuration validation.
- Connection and initialization.
- Supported input delivery.
- Event normalization.
- Transcript and artifact handling.
- Tool calls and results.
- Unknown and malformed events.
- Duplicate events.
- Timeouts and disconnections.
- Unsupported capability reporting.
- Consistent lifecycle and error behavior.

### B. Scenario tests

Verify:

- Scenario creation and retrieval.
- Template-based scenarios.
- Custom JSON validation.
- Missing scenario handling.
- Invalid scenario IDs.
- Ownership and authorization.
- Snapshot persistence.
- Historical results remaining unchanged after edits.

### C. Deterministic evaluation tests

Verify:

- Passing rules.
- Failing rules.
- Inconclusive rules.
- User-defined rules.
- Tool argument validation.
- Missing evidence.
- Critical failure handling.
- Webhook status, latency, and response validation where applicable.

### D. Payload generation tests

Verify:

- Provider-specific schemas.
- Correct agent ID use.
- Correct mapping of user intent.
- Invalid JSON handling.
- Schema rejection.
- LLM reviewer rejection.
- Bounded revision loops.
- Failure after maximum revisions.
- No execution of invalid payloads.
- Prevention of unauthorized endpoint requests.

### E. LLM judge tests

Use mocked model responses to verify:

- Valid structured verdicts.
- Invalid output.
- Missing evidence.
- Unsupported claims.
- Prompt-injection resistance.
- Model timeout and rate-limit handling.
- Unavailable-model behavior.
- Separation between deterministic and LLM outcomes.

### F. Integration and end-to-end tests

Test the entire workflow:

1. Select provider.
2. Configure an agent.
3. Create or select a scenario.
4. Add custom instructions.
5. Add deterministic rules.
6. Add LLM evaluation criteria.
7. Generate and validate any required payload.
8. Execute a mocked or approved live provider test.
9. Capture and persist evidence.
10. Evaluate the evidence.
11. Retrieve the report.

Ordinary CI must use mocked provider interactions and mocked LLM responses where appropriate.

Live tests must be opt-in and require explicitly configured test credentials and safe test targets.

Never claim that a live provider was tested when only mocks were used.

---

## 23. IMPLEMENTATION CONSTRAINTS

- Preserve the existing stack and established architecture.
- Do not redesign the frontend.
- Do not rewrite unrelated modules.
- Reuse working provider integrations.
- Avoid unnecessary dependencies.
- Avoid giant files; keep source files under 200 lines where reasonably achievable, excluding generated files and unavoidable configuration/migration artifacts.
- Split large modules into focused components.
- Use typed interfaces and schemas.
- Do not create microservices or Kubernetes infrastructure for this task.
- Do not introduce fake data into production paths.
- Do not return fake successful evaluations.
- Do not claim unsupported provider capabilities.
- Do not silently swallow exceptions.
- Do not overwrite `.env` or commit secrets.
- Do not mark tests as passed unless they were actually executed.

---

## 24. EXECUTION PLAN

Complete the work in reviewable stages.

### Stage 1 — Audit

Inspect the existing repository, identify the scenario lookup bug, trace the current provider execution paths, and document the gaps.

### Stage 2 — Contracts and shared core

Implement or repair the shared provider contract, normalized events, scenario validation, deterministic evaluation, LLM evaluation interface, and persistence.

### Stage 3 — Hugging Face judge

Configure the requested DeepSeek and Llama 3.3 8B models through verified Hugging Face-compatible endpoints. Implement structured output validation, timeout handling, and mocked tests.

### Stage 4 — ElevenLabs

Repair or complete the existing ghost-caller workflow and verify the full evaluation pipeline.

### Stage 5 — AssemblyAI

Implement its documented input and event protocol using the shared core.

### Stage 6 — Vapi and Retell

Implement provider-specific payload generation and validation, supported agent execution, direct webhook contract testing where requested, and evidence-backed evaluation.

### Stage 7 — Custom rules and workflow

Complete user-defined deterministic rules, user-defined LLM criteria, scenario selection, template/custom JSON validation, and run prerequisites.

### Stage 8 — Testing and hardening

Run unit, contract, integration, migration, API, and end-to-end tests. Fix failures and document limitations.

Do not make unrelated frontend changes at any stage.

---

## 25. DEFINITION OF DONE

The work is complete only when:

- The correct backend branch is used.
- Existing frontend designs remain unchanged.
- The missing-scenario error is fixed at its root cause.
- Users cannot start an evaluation without a valid scenario and required agent ID.
- Users can create a scenario or select an existing one.
- Users can select a template or supply validated custom JSON.
- Users can write their own test instructions.
- Users can add their own deterministic rules.
- Users can add their own LLM evaluation criteria.
- ElevenLabs uses its documented execution protocol.
- AssemblyAI uses its documented execution protocol.
- Vapi and Retell have provider-specific, schema-validated payload generation where applicable.
- Generated payloads are reviewed, corrected within a bounded loop, and validated before execution.
- Hugging Face model configuration supports the requested DeepSeek and Llama 3.3 8B models using verified model IDs and endpoints.
- Actual events and responses are captured and persisted.
- Deterministic and LLM evaluation results remain separately visible.
- Critical deterministic failures cannot be hidden by the LLM judge.
- Reports are reproducible and evidence-backed.
- Provider contract tests and failure-path tests pass.
- Unsupported capabilities are reported honestly.
- Documentation matches the actual implementation.

---

## 26. FINAL ENGINEERING REPORT

At completion, report:

1. Initial repository findings.
2. Root cause of the scenario lookup error.
3. Files created and modified.
4. Shared architecture changes.
5. Provider-specific implementation status.
6. ElevenLabs and AssemblyAI execution results.
7. Vapi and Retell payload and execution results.
8. Hugging Face model IDs and endpoints actually configured.
9. Deterministic and LLM evaluation behavior.
10. Database migrations and API changes.
11. Contract, unit, integration, and end-to-end tests run.
12. Commands executed and their actual outcomes.
13. Security and reliability changes.
14. Known limitations and remaining work.

Clearly distinguish:

- Implemented.
- Unit-tested.
- Contract-tested.
- Mocked end-to-end tested.
- Live-verified.
- Not yet implemented.

**Begin with the repository audit. Preserve the existing frontend design. Work only on `feat/provider-evaluation-engine`. Fix the existing scenario bug, build the shared evaluation core, prove the ElevenLabs workflow, and extend it to the remaining providers without duplicating the platform.**