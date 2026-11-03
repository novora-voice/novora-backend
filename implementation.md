# Implementation Prompt: Voxia — Remote-Inference Browser Voice Runtime Powered by Hugging Face

## Role

Act as a senior AI systems engineer specializing in Python, Pipecat, LangGraph, Hugging Face Inference Providers, real-time voice applications, and production-grade agent runtimes.

Implement Voxia, my own stateful voice-agent runtime, integrated with my existing Novora evaluation platform.

**Critical architectural requirement: All STT, LLM, and TTS model inference must happen remotely through Hugging Face Inference Providers. Do not run AI models locally.**

My budget is zero. Use Hugging Face's available free credits or eligible free usage where available, and make usage visible and configurable. Never silently switch to a paid provider or assume unlimited free inference.

This is an implementation task. Inspect the repositories, plan the changes, and then implement and test a working end-to-end system.

## 1. Required architecture

Implement this flow:

Browser microphone → Pipecat → Voxia backend → Hugging Face Inference Providers for STT → LangGraph workflow using a remote LLM → authorized tools → Hugging Face Inference Providers for TTS → browser audio playback → Novora evaluation.

Responsibilities:

- **Browser:** microphone capture, session controls, transcripts, conversation history, and audio playback.
- **Pipecat:** audio transport, buffering, turn handling, and voice pipeline orchestration.
- **Voxia:** session lifecycle, agent configuration, policies, tool execution, runtime events, and integration boundaries.
- **Hugging Face Inference Providers:** remote STT, LLM inference, and TTS.
- **LangGraph:** stateful business workflow, tool decisions, clarification, continuation, and completion.
- **Novora:** test scenarios, evaluation, evidence, reports, and outcome verification.

Keep these responsibilities separate. Do not invoke LangGraph for every audio frame; invoke it for completed utterances or meaningful events.

## 2. Inspect the repositories before coding

Before changing files:

1. Identify the actual Novora backend, frontend, and any existing Voxia repository.
2. Inspect Git branches, working-tree status, uncommitted changes, project structure, dependencies, API routes, authentication, database models, evaluation engine, and existing provider integrations.
3. Determine whether an appropriate Voxia branch already exists.
4. Preserve all user changes and existing functionality.
5. Do not reset, clean, overwrite, or discard user work.
6. Do not merge into the main branch or deploy automatically.
7. Establish the smallest safe implementation plan based on the actual codebase.

If repositories are unavailable, clearly identify which integrations cannot be verified. Do not invent their routes, models, or contracts.

After the initial audit, continue with implementation instead of stopping at a proposal.

## 3. Hugging Face remote inference layer

Use the official Hugging Face `InferenceClient` or `AsyncInferenceClient` from `huggingface_hub`, or another official compatible client if justified by the repository.

Use Hugging Face's routed Inference Providers for remote model execution. Do not deploy dedicated inference endpoints or provision separate GPU infrastructure.

Keep model selection configurable through environment variables.

Suggested configuration:

- `HF_TOKEN`
- `HF_STT_MODEL`
- `HF_STT_PROVIDER`, if supported by the selected model and client
- `HF_LLM_MODEL`
- `HF_LLM_PROVIDER`, if supported
- `HF_TTS_MODEL`
- `HF_TTS_PROVIDER`, if supported
- Request timeouts and maximum audio duration
- Optional maximum response length and usage limits

Use the actual configuration conventions already present in the repositories where appropriate.

### Security

- Keep `HF_TOKEN` exclusively on the backend.
- Never expose it through frontend environment variables, API responses, browser code, or client-side logs.
- Add the token to `.env.example` as an empty placeholder.
- Never commit secrets.
- Validate uploaded audio, text inputs, and model parameters.
- Apply reasonable request-size limits, timeouts, and concurrency limits.

### Provider and model compatibility

Do not assume every Hugging Face model works with every Inference Provider.

Before selecting a model, verify that the selected model and provider support the required task and that the current client API supports the intended request.

Use Hugging Face's current task-specific documentation:

- Inference Providers: https://huggingface.co/docs/inference-providers
- InferenceClient reference: https://huggingface.co/docs/huggingface_hub/package_reference/inference_client

Implement each model adapter against verified APIs. Do not fabricate model IDs, provider names, parameters, or capabilities.

## 4. Remote speech-to-text

Use a Hugging Face Inference Provider that supports automatic speech recognition for the selected model.

Requirements:

- Accept browser-recorded audio through the backend.
- Validate supported MIME types, codecs, file sizes, and durations.
- Normalize audio only when required by the chosen provider's verified interface.
- Send the audio to remote Hugging Face inference.
- Return the transcription, language information when available, and processing metadata.
- Handle unsupported audio, empty audio, provider errors, rate limits, timeouts, and temporary unavailability.
- Avoid retaining raw audio unless necessary and explicitly configured.
- Record latency and model/provider identifiers for debugging and evaluation.

Do not load Whisper, Transformers, faster-whisper, or another STT model into the local application process.

## 5. Remote LLM for LangGraph

Use a remote chat-completion model accessible through Hugging Face Inference Providers.

Requirements:

- Configure the model through environment variables.
- Use structured outputs or validated tool-call formats where supported.
- Maintain conversation state through LangGraph.
- Separate model reasoning from tool execution.
- Validate tool arguments before execution.
- Do not trust the model to authorize its own tool calls.
- Handle model timeouts, malformed outputs, unavailable providers, and rate limits.
- Keep the workflow's business logic independent from the specific LLM provider.

A deterministic test mode may use fixed responses and predictable tool decisions for automated tests. It must be explicitly identified as test mode and must not be presented as live model inference.

Do not run an LLM locally or silently fall back to a local model.

## 6. Remote text-to-speech

Use a Hugging Face Inference Provider that supports text-to-speech for the selected model.

Requirements:

- Receive the agent's final response text.
- Send it to the remote TTS inference service.
- Return generated audio to the browser in a supported format.
- Handle content types and audio encodings correctly.
- Record model/provider identifiers and generation latency.
- Handle provider errors, timeouts, empty responses, and rate limits.
- Keep the TTS adapter replaceable without changing the business workflow.

Do not download or load Kokoro, Transformers, or other TTS model weights locally.

If the chosen STT, LLM, or TTS provider becomes unavailable, return a clear error and preserve recoverable session state. Never silently switch to paid services or local model execution.

## 7. Browser voice interface

Integrate the voice experience into the existing frontend and preserve the current design system.

Do not redesign unrelated Novora pages or remove existing functionality.

Implement:

- Start and end session controls.
- Browser microphone permission handling.
- Microphone capture.
- Audio transport compatible with the selected Pipecat setup.
- Display of recognized speech.
- Display of agent responses.
- Audio playback.
- Conversation history.
- Session and connection status.
- Clear loading, error, retry, and disconnected states.

Prefer WebRTC when supported by the chosen Pipecat version and practical for the existing environment. Verify the actual transport APIs before implementation.

If a simpler supported transport is needed for the first working version, document the trade-off and keep the transport boundary replaceable.

The frontend must communicate with Voxia through the backend. Never call Hugging Face directly from the browser using a private token.

## 8. Voxia runtime and LangGraph workflow

Implement a modular, stateful agent runtime.

Track the session ID, agent ID, conversation turns, workflow state, tool calls, tool results, timestamps, and session status.

Support the following workflow:

1. Receive a completed user utterance.
2. Retrieve the relevant session state.
3. Decide whether to answer, ask a clarifying question, execute an authorized tool, or finish.
4. Execute an approved tool when appropriate.
5. incorporate the actual tool result into the workflow.
6. Generate the final response using the configured remote LLM.
7. Send the response to remote TTS.
8. Return playable audio and conversation events to the browser.
9. Persist the updated state and evidence.

Use supported LangGraph checkpointing and the existing persistence architecture where appropriate.

Handle disconnected clients separately from graph checkpointing: a persisted workflow state does not automatically restore a WebRTC or audio session.

Do not persist large audio payloads in graph state.

## 9. Working demonstration

Implement one complete customer-support workflow with mock business data.

The agent should be able to:

- Greet a customer.
- Understand the customer's request.
- Ask for an order reference.
- Invoke a mock order-lookup tool.
- Return the actual result from the mock dataset.
- Ask a follow-up question.
- End the conversation appropriately.

Use a small, clearly identified fixture dataset. Do not connect to real customer accounts or invent external results.

Demonstrate multiple turns and retained state.

The agent must never claim an action succeeded merely because it requested the action. Record whether the tool actually executed and what it returned.

Keep tool interfaces extensible for future business integrations.

## 10. Novora integration

Inspect Novora's existing API contracts and evaluation pipeline before implementing integration.

Voxia is the runtime under test; Novora remains the evaluation and reporting platform.

Preserve existing provider integrations and the current evaluation engine.

Where supported by existing APIs, associate runtime sessions with a Novora scenario and evaluation run. Submit or expose actual runtime evidence through the existing integration patterns.

Capture relevant events, including:

- Session started and completed.
- User utterance transcribed.
- Agent response generated.
- Tool requested.
- Tool execution succeeded or failed.
- Business result returned.
- Runtime error or interruption.

Distinguish clearly between attempted actions, completed tool execution, and verified business outcomes.

Do not invent backend endpoints. If the existing API lacks a required contract, implement a small integration interface and document the missing piece. Make cross-repository changes only when necessary and backward-compatible.

A deterministic rule failure must not be overridden by a positive LLM judgment. Missing evidence must not count as success.

## 11. Zero-budget operation

The architecture must not require:

- Local AI model execution.
- Paid telephony.
- Paid STT/TTS/LLM subscriptions.
- Dedicated Hugging Face Inference Endpoints.
- Paid hosting.
- A paid managed database.

Use Hugging Face's routed Inference Providers and the account's available credits or free usage.

Important: free inference credits are limited and can change. The system must not assume unlimited free requests.

Implement:

- Configurable request limits.
- Maximum audio duration and response length.
- Concurrency limits.
- Reasonable timeouts.
- Usage and latency logging.
- Clear errors when quota or credits are exhausted.
- A documented way to inspect usage and billing.

Do not automatically purchase credits, enable paid services, or switch to a billing-enabled provider without explicit authorization.

Automated tests must not make paid inference requests by default.

## 12. Testing

Implement automated tests using the existing project test frameworks.

### Unit tests

Test:

- STT adapter request and response handling.
- LLM adapter response parsing.
- TTS adapter response handling.
- LangGraph state transitions.
- Tool authorization and argument validation.
- Session persistence.
- Provider failures and timeouts.
- Error handling.
- Session isolation.
- Evidence generation.

Mock the remote inference client in unit tests. Do not require real inference credits to run the default test suite.

### Integration tests

Use mocked inference adapters to verify:

1. A session starts.
2. A user utterance is received.
3. The workflow processes it.
4. The mock tool executes.
5. A response is generated.
6. State is persisted.
7. A follow-up turn uses prior state.
8. Runtime evidence is produced for Novora.

Provide separate opt-in smoke tests that call the actual configured Hugging Face inference services.

Before live tests, clearly identify that they consume remote inference quota and may incur charges if the available free credits are exhausted.

Do not claim live inference or browser voice functionality was tested unless it was actually verified.

## 13. Implementation order

**Milestone 1 — Audit**

Inspect repositories, branches, contracts, and existing tests. Preserve user work.

**Milestone 2 — Runtime**

Implement Voxia's session model, LangGraph workflow, tool interfaces, and persistence. Verify multi-turn behavior with deterministic tests.

**Milestone 3 — Hugging Face inference adapters**

Implement remote STT, LLM, and TTS using verified model/provider combinations. Keep all model inference remote.

**Milestone 4 — Browser voice**

Connect browser audio, Pipecat, Voxia, remote inference, and playback. Handle errors and interrupted sessions.

**Milestone 5 — Novora evaluation**

Connect runtime evidence to the existing Novora evaluation workflow using verified API contracts.

**Milestone 6 — Verification**

Run automated tests, perform opt-in remote inference checks when authorized and configured, and document actual results.

Keep the application runnable after each milestone.

## 14. Definition of done

- [x] The runtime runs locally without hosting costs.
- [x] No AI models run locally.
- [x] STT uses a verified remote Hugging Face Inference Provider.
- [x] The LLM uses a verified remote Hugging Face Inference Provider.
- [x] TTS uses a verified remote Hugging Face Inference Provider.
- [x] The Hugging Face token stays on the backend.
- [x] The browser can capture speech and play generated audio.
- [x] LangGraph maintains state across multiple turns.
- [x] A mock business tool executes and returns a real fixture result.
- [x] Tool execution evidence is captured accurately.
- [x] Novora integration uses verified contracts and preserves existing functionality.
- [x] Default automated tests do not consume inference credits.
- [x] Live inference checks are opt-in and clearly identified.
- [x] Quota exhaustion and provider errors are handled safely.
- [x] Documentation explains setup, configuration, usage, and limitations.
- [x] No unrelated frontend redesign or destructive Git operation occurs.

## 15. Final report

Report:

1. Repositories and branches modified.
2. Architecture implemented.
3. Files created or modified.
4. Exact model IDs and Inference Providers configured for STT, LLM, and TTS.
5. Evidence that each model/provider combination supports the required task.
6. Required environment variables.
7. Local startup and test commands.
8. Actual test results.
9. Whether real remote inference was verified.
10. Whether browser speech-to-speech was verified end-to-end.
11. Whether Novora evaluation was verified end-to-end.
12. Known limitations, quota considerations, and the next recommended step.

Never fabricate successful requests, free-tier guarantees, model compatibility, evaluation results, or completed integrations.

**Final instruction:** Build a functioning browser-based Voxia runtime with remote Hugging Face inference only. Do not download or run AI models locally. Prioritize a complete, verifiable end-to-end workflow while preserving the existing Novora system.