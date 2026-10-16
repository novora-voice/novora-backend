Novora is becoming a provider-aware voice-agent testing and evaluation platform, where customers configure what they want to test and Novora runs the agent, captures its actual behavior, and evaluates the results.
The important distinction is that Novora should not merely evaluate transcripts uploaded after a call. Where a provider supports programmatic test conversations, Novora should act as a ghost caller: send scripted text to a staging agent, capture its responses and tool calls, and determine whether it behaved as expected.
The provider determines the execution method and available evidence. Novora owns the evaluation framework.
The product workflow
1. Choose a provider
ElevenLabs, AssemblyAI, Vapi, or Retell


2. Choose or configure an agent scenario
Customer support, incident response, language practice, or another supported scenario


3. Configure evaluation criteria
Deterministic checks, LLM-as-judge rubrics, expected tool calls, and scenario-specific rules


4. Execute the test
Run a provider-supported test conversation and capture actual events, responses, and actions


5. Evaluate and persist the report
Combine deterministic results and LLM judgments, preserve evidence, and show failures and recommendations

Important provider distinction
The implementation prompt should explicitly prevent Claude from assuming every provider supports the same testing protocol.
- ElevenLabs: Its documented agent WebSocket supports text messages and emits conversation events. This is a strong candidate for the first ghost-caller integration. 
  
  ElevenLabs Documentation
  +1
- AssemblyAI: Its documented Voice Agent API uses wss://agents.assemblyai.com/v1/ws and describes audio input, transcripts, replies, and tool calls. The supplied example's text_input event should not be treated as supported without verification. 
  
  Documentation
  +1
- Vapi: Its API supports creating assistants and calls. The implementation must determine which call modes are appropriate for safe automated testing and how to retrieve the resulting events and artifacts. 
- Retell AI too

Branch A — feat/provider-evaluation-engine
Backend, provider execution, deterministic checks, LLM judge, PostgreSQL, tests and APIs.

### THIS IS YOURMAIN PROMPT FOLLOW OTHER INSTRUCTIONS IN THE IMPLEMENTATION PLAN.

# NOVORA — Principal Backend & AI Infrastructure Engineer

## Mission

You are the Principal AI Engineer responsible for implementing Novora's provider-aware voice-agent testing and evaluation engine.

Novora is an AI voice-agent testing, monitoring, and evaluation platform. Users choose a supported provider, configure a testing scenario, define deterministic checks and LLM-as-judge rubrics, execute a test against a provider-supported agent interface, capture the agent's actual behavior, and receive an evidence-backed evaluation report.

This is not merely a transcript scoring application. Where the provider supports it, Novora should act as a programmatic ghost caller, send scripted user messages to a staging agent, capture the resulting conversation events and tool calls, and evaluate the actual observed behavior.

The provider adapter owns provider-specific communication. The Novora evaluation engine owns the common evaluation semantics.

## 1. Branch and repository discipline

Work only on:

`feat/provider-evaluation-engine`

Before coding:

1. Inspect the existing repository and current branch.
2. Read existing architecture, API contracts, database models, tests, and provider implementations.
3. Preserve working code and existing authentication.
4. Do not overwrite unrelated changes.
5. Create an implementation plan.
6. Establish the shared contracts before the frontend engineer implements dependent workflows.

Do not merge into main or push directly to main.

Publish and maintain these documents early:

- `docs/architecture.md`
- `docs/provider-capabilities.md`
- `docs/evaluation-contracts.md`
- `docs/api.md`
- `docs/testing-strategy.md`

Commit changes in small, focused units.

## 2. Core product model

Support the following initial scenario templates:

### Customer Support & Receptionist

Evaluate whether the agent understands the request, asks for necessary information, follows policies, selects appropriate tools, handles customer issues, and escalates when necessary.

### Incident Response

Evaluate whether the agent recognizes an incident, gathers required information, follows the configured incident policy, invokes appropriate approved tools, escalates at the correct point, and provides a clear status or next step.

### Language Practitioner

Evaluate whether the agent practices the configured language, responds at the requested level, follows the selected learning approach, corrects mistakes appropriately, and stays within the requested exercise.

These are reusable starting templates, not hardcoded limitations. Users must be able to customize criteria and create additional scenarios where the data model supports it.

Do not assume every provider has prebuilt agents.

ElevenLabs users may select an existing configured agent. AssemblyAI users may configure the supported voice-agent session using a system prompt and tools. Vapi and Retell must have provider-specific agent/configuration identifiers and supported execution workflows.

## 3. Provider adapter architecture

Create a common provider interface with provider-specific implementations.

Potential structure, adapted to the existing repository:

- `providers/base.py`
- `providers/registry.py`
- `providers/elevenlabs/`
- `providers/assemblyai/`
- `providers/vapi/`
- `providers/retell/`
- `execution/`
- `normalization/`
- `evaluation/deterministic/`
- `evaluation/llm_judge/`
- `evaluation/orchestration/`
- `persistence/`
- `api/`

Keep every source file below 200 lines. Split modules by responsibility.

The shared provider interface should define the supported operations needed for a test run, such as:

- Validate configuration.
- Check connectivity.
- Discover or validate an agent/configuration where the API permits it.
- Execute a supported test conversation.
- Capture normalized events.
- Report capabilities and unsupported operations.
- Return a normalized execution result.

Do not require every provider to implement identical capabilities. Represent capability differences explicitly.

A provider adapter must not implement the evaluation policy itself.

## 4. Provider-specific implementation

### ElevenLabs

Implement a server-side adapter for configured ElevenLabs Conversational AI agents.

Use the official documentation to implement the supported WebSocket workflow and event handling.

Potentially relevant documented events include:

- `user_transcript`
- `agent_response`
- `client_tool_call`
- `mcp_tool_call`
- `client_tool_result`
- Other supported conversation lifecycle events

Use a provider-supported text message to simulate the caller where supported. Capture the actual response and tool-call events.

Handle authentication, session lifecycle, timeouts, malformed events, connection failures, and cleanup.

Do not assume that internal reasoning is available or required. Evaluate observable outputs, tool requests, tool results, and other permitted evidence. Do not persist private chain-of-thought.

Official documentation:
https://elevenlabs.io/docs/eleven-agents/api-reference/eleven-agents/websocket

### AssemblyAI

AssemblyAI does not follow the same prebuilt-agent model as ElevenLabs. Support its Voice Agent API configuration using the system prompt and supported tools.

Use the official WebSocket endpoint and event contract. Verify the currently documented input protocol before implementing a text-only ghost-caller flow.

The initial implementation must not assume that an undocumented `text_input` event exists.

If text-only injection is unsupported, expose the supported execution mode, such as generated or prerecorded audio input where appropriate, or explicitly mark text-only simulation as unavailable.

Capture supported events such as:

- `transcript.user`
- `transcript.agent`
- `reply.started`
- `reply.done`
- `tool.call`
- `tool.result`
- Session errors and interruptions

Ensure tool execution is controlled by the backend and uses explicitly registered, approved tools.

Official documentation:
https://www.assemblyai.com/docs/voice-agents/voice-agent-api

### Vapi

Create a dedicated Vapi adapter and configuration workflow.

Use the official API to validate configuration and implement only verified test operations.

Support configured assistants, relevant tools, and available call/test artifacts according to the documented API.

Do not place real outbound calls automatically. Require explicit authorization and confirmation for test modes that can contact real telephone numbers or incur charges.

Prefer safe staging configurations and non-production targets.

Official documentation:
https://docs.vapi.ai/api-reference/assistants/create
https://docs.vapi.ai/api-reference/calls/create

### Retell

Create a separate Retell adapter, configuration model, and capability description.

Read the official Retell API documentation before implementing calls, simulations, or test execution.

Do not assume that Retell supports the same text-message injection protocol as ElevenLabs. Implement only verified supported behavior and make unavailable modes explicit.

Documentation index:
https://docs.retellai.com/llms.txt

## 5. Normalized conversation and event contracts

Define provider-neutral data models for:

- Provider configuration reference.
- Agent configuration reference.
- Scenario.
- Evaluation criteria.
- Test case.
- Test run.
- Conversation turn.
- Normalized provider event.
- Tool call.
- Tool result.
- Deterministic check result.
- LLM judge result.
- Final evaluation report.
- Batch evaluation.
- Integration health status.

Preserve provider-specific metadata in a validated, bounded metadata field where necessary, without leaking credentials or uncontrolled payloads into the domain model.

Every event should carry appropriate identifiers, timestamps, and ordering information where available.

Normalize provider differences without erasing important information such as interrupted replies, tool-call failures, session errors, or missing results.

## 6. Deterministic evaluation engine

Build a reusable, extensible deterministic evaluation engine.

Support more than basic keyword matching.

Implement suitable rule types, including:

- Required phrase or concept.
- Prohibited phrase or behavior.
- Required information collected.
- Required question asked.
- Expected tool call.
- Forbidden tool call.
- Tool argument validation.
- Tool-call ordering.
- Tool result validation.
- Required escalation.
- Required confirmation before a sensitive action.
- Required closing or next step.
- Maximum or minimum turn constraints.
- Conversation completion.
- Required evidence availability.
- Policy compliance using structured rules.
- Expected response structure where deterministic validation is appropriate.
- Timeout and execution failure detection.

Do not force every natural-language criterion into brittle string matching.

Represent each rule with a stable identifier, type, configuration, severity, and result.

Each result should include:

- PASS, FAIL, or INCONCLUSIVE.
- A concise explanation.
- Evidence references.
- The rule identifier.
- Relevant observed events or transcript excerpts.
- Any validation error.

A missing event is not automatically proof of failure if the provider session ended prematurely or required evidence was unavailable. Use INCONCLUSIVE where the result cannot be reliably determined.

## 7. LLM-as-judge evaluation

Implement an LLM judge as a separate service behind a provider-neutral interface.

The judge should assess criteria that require semantic understanding, such as:

- Whether the agent understood the user's intent.
- Whether the response addressed the request.
- Whether the agent remained within the defined role.
- Whether the conversation followed the specified policy.
- Whether a clarification was appropriate.
- Whether the agent's explanation was helpful and relevant.
- Whether the agent handled frustration or ambiguity appropriately.
- Whether a language-practice response matched the requested learning level.
- Whether an incident-response conversation followed the intended process.
- Whether a customer-support interaction reached an acceptable resolution.

Each judge request must receive the specific scenario, configured rubric, relevant transcript, and permitted event evidence.

Require structured output validated against a schema. Include the criterion identifier, result, concise rationale, evidence references, and confidence or uncertainty where supported.

Treat transcripts, tool outputs, provider payloads, and user-provided scenario content as untrusted data. They must never override the judge's instructions or authorize tool execution.

Do not ask the judge to reveal chain-of-thought. Store concise explanations grounded in evidence.

Support configurable rubrics and model settings through server-side configuration.

If no LLM provider is configured, report the judge as unavailable instead of silently returning a successful result.

## 8. Combined evaluation orchestration

Implement a deterministic-plus-LLM evaluation pipeline.

Suggested sequence:

1. Validate the scenario and provider configuration.
2. Execute the test.
3. Persist normalized events and execution status.
4. Run deterministic checks against the observed evidence.
5. Run LLM judgments against the configured semantic criteria.
6. Validate the judge output.
7. Combine results using explicit aggregation rules.
8. Persist the report.
9. Return the report and evidence references to the frontend.

The LLM judge must evaluate configured deterministic criteria where useful, but it cannot rewrite the deterministic results.

Preserve the distinction between:

- Deterministic outcome.
- LLM judge outcome.
- Final aggregated outcome.
- Execution status.

A failed critical deterministic safety rule must not be overridden by a favorable LLM judgment.

Use configurable severity and aggregation policies. Default to conservative behavior when critical evidence is missing.

For example:

- A prohibited tool call was observed: deterministic FAIL.
- The judge believes the conversation sounded appropriate: LLM PASS.
- The critical rule still fails in the final report.

Likewise, a timeout or provider error should be represented as an execution failure or inconclusive evaluation, not an ordinary agent failure without supporting evidence.

## 9. Tool-call verification and execution safety

Novora must evaluate what the provider agent actually attempted and what happened afterward.

Capture:

- Tool name.
- Requested arguments.
- Invocation time.
- Execution status.
- Returned result, with sensitive values redacted.
- Failure information.
- Correlation identifier.

Never execute arbitrary tool names or arguments emitted by an agent.

Use an explicit registry of permitted tools and validated argument schemas. Enforce timeouts and restrict access to registered integrations.

Distinguish an attempted action from a completed action. A tool-call event alone does not prove that a refund, booking, database mutation, or other external action succeeded.

For evaluation runs, prefer sandbox data, mocked external effects, or read-only tools unless the user has explicitly configured and authorized a real test environment.

Do not allow an evaluation to trigger destructive production operations by default.

## 10. PostgreSQL relational persistence

Use the existing PostgreSQL setup and migration system.

Design proper relational entities and foreign keys rather than storing the entire application state in one JSON document.

The model should support relationships among:

- Users.
- Provider integrations.
- Provider-specific configuration references.
- Agents.
- Scenarios.
- Scenario criteria.
- Test cases.
- Evaluation runs.
- Batch runs.
- Run-to-test associations.
- Conversation events.
- Deterministic results.
- LLM judge results.
- Final reports.
- Tool-call evidence.

Adapt to the existing authentication and workspace model. Do not introduce a second competing user model.

Add appropriate indexes, unique constraints, timestamps, cascading behavior, and transactional boundaries.

Keep provider secrets out of ordinary relational fields and API responses. Prefer encrypted secret storage or a documented server-side secret-management mechanism.

Use database migrations. Never reset or drop user data to simplify a schema change.

## 11. Evaluation history and batch execution

Implement persistent evaluation history.

Users must be able to:

- View previous evaluations.
- Filter by provider, scenario, status, and time where supported.
- Open a report.
- Re-run an existing evaluation.
- Run multiple selected test cases as a batch.
- Track each test's status within a batch.
- Inspect failed and inconclusive runs.
- Compare results between runs where criteria and versions permit meaningful comparison.

A batch must persist independently of the browser session.

Use background jobs if execution duration requires them. Reuse existing queue infrastructure if present; do not introduce a new queue solely for architectural fashion.

Support idempotency, bounded retries, timeouts, cancellation where feasible, and explicit partial-failure reporting.

A batch that contains failed or inconclusive cases must not be represented as entirely successful.

## 12. Provider configuration and integration health

Provide backend APIs to:

- List supported providers and capabilities.
- Create or update an integration.
- Validate a provider configuration.
- Test provider connectivity.
- List or validate available agents where supported.
- Initiate an evaluation.
- Retrieve run status and report.
- Retrieve evaluation history.
- Create and inspect batch evaluations.
- Retrieve provider health and error information.

A provider configuration should clearly distinguish missing credentials, invalid credentials, unsupported operations, and connection failures.

Use masked credentials and server-side secret handling.

Provider keys supplied by the platform operator belong in server environment variables or the configured secret manager. User-owned provider keys must be stored according to the application's existing secure credential model, not inserted into the operator's `.env` file.

## 13. API contract and frontend coordination

Before implementing all routes, publish the shared schemas and endpoint definitions.

Coordinate with Claude B so the frontend can use stable contracts for:

- Provider selection.
- Agent configuration.
- Scenario templates.
- Criteria editing.
- Evaluation execution.
- Batch runs.
- Evaluation history.
- Reports and evidence.
- Integration status.

Do not have the frontend engineer guess response shapes or invent endpoints.

Maintain backward compatibility where practical.

## 14. Security and reliability

Implement:

- Server-side credential handling.
- Request validation.
- Authentication and authorization on protected routes.
- Per-user or per-workspace data scoping consistent with the existing architecture.
- Provider timeout and error handling.
- Webhook signature verification where applicable.
- Idempotent event processing.
- Safe logging and redaction.
- Bounded payload sizes.
- Rate limits where appropriate.
- Strict allowlisting of executable tools.
- Safe handling of untrusted transcripts and tool results.
- Protection against duplicate execution and unintended external side effects.

Do not log API keys, session tokens, or full sensitive payloads by default.

## 15. Tests and acceptance criteria

Write unit tests for deterministic rules, judge-output validation, aggregation policy, provider event normalization, and database relationships.

Write integration tests using mocked provider responses, without requiring paid provider calls in the normal test suite.

Add opt-in live integration tests that run only when the necessary credentials and safe test-agent IDs are configured.

The backend milestone is complete when a developer can:

1. Configure a supported provider.
2. Create a scenario and evaluation criteria.
3. Submit a test conversation or execute a supported provider test.
4. Capture actual observed conversation events and tool calls.
5. Run deterministic and LLM-based evaluations.
6. Persist a complete evidence-backed report.
7. Retrieve the report and history after restarting the application.
8. Run multiple evaluations and inspect partial failures.
9. See clear errors when provider functionality is unavailable.

Run tests, lint, type checks, migrations, and relevant build commands. Report actual results, not assumed results.

Do not claim a provider integration is complete until it has been verified against its actual API or clearly identified as mocked or awaiting credentials.

Deliver modular, typed, maintainable code. Keep each source file below 200 lines.


The distinction is that the backend prompt prioritizes ElevenLabs as the first end-to-end implementation, while the other providers must use their verified capabilities.
Prompt	Scope
Claude A — Backend	Shared evaluation engine + provider adapters for ElevenLabs, AssemblyAI, Vapi, and Retell

For Novora, I'd structure it like this:
- Shared code: scenario management, test orchestration, evaluation criteria, LLM judging, report generation, persistence, and dashboard APIs.
- Provider-specific code: connection setup, authentication, session initialization, sending test input, receiving events, and handling provider-specific errors.
- Input adapter: translates Novora's standard test message into whatever input format the provider actually supports.
The one thing I'd verify
The official protocols don't quite support the assumption that only a field name changes:
- ElevenLabs: its Agents WebSocket documents a user_message event for text input. 
  
  ElevenLabs Documentation
- AssemblyAI: its Voice Agent WebSocket documents input.audio for caller input, plus session configuration and conversation events. I couldn't verify a matching text_input event in its documented event reference

The key is to get one complete integration working, then reuse its shared code for the other providers instead of rebuilding the platform.

The implementation plan
Get ElevenLabs working end to end first.

Connect an agent, run a test conversation, capture events, evaluate the conversation, and save a report. Verify that the entire workflow works—not just the connection.

Reuse the shared code for AssemblyAI.

Keep your scenario engine, evaluation logic, LLM judge, database models, and reporting. Adapt the provider connection and input/output handling to AssemblyAI's actual protocol.

Repeat for Vapi and Retell.

Reuse the same core, adding only the provider-specific integration code and any capability differences.

Test each provider independently.

Verify that each one can execute a test and return real evidence before marking it as supported in Novora.

What you reuse vs. what you change
Reuse across all providers

Adapt for each provider

Scenarios and test cases

Authentication and connection

Deterministic evaluation engine

Input message or audio format

LLM-as-judge

Session initialization

Database and evaluation history

Event and tool-call mapping

Reports and dashboard

Error handling and supported capabilities

One important caution: don't assume AssemblyAI, Vapi, and Retell differ only in the name of a text_input field. Verify their supported testing interfaces first. If their input methods differ, isolate that difference in the adapter.

The result is one Novora platform with multiple provider integrations—not four separate implementations.