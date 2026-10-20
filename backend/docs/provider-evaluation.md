# Live provider evaluations

`POST /api/v1/test-runs/jobs` runs scripted user messages against provider services and then evaluates the returned transcript. The frontend must send `scenario`, `agent.provider_name`, `agent.external_agent_id`, and `user_instructions`; API credentials are resolved by the backend and are never read from the request body or put in the Redis job record.

Each completed run persists its evaluation report together with the configured agent ID and name. The report history exposes `agent_id` and `agent_name`, allowing the dashboard to show the latest verdict for the matching agent after a reload.

Set the provider key in `backend/.env` and restart the API and evaluation worker:

```dotenv
ELEVENLABS_API_KEY=...
ASSEMBLYAI_API_KEY=...
VAPI_API_KEY=...
RETELL_API_KEY=...
```

The selected provider must have a key, and the agent ID must identify a real configured agent. ElevenLabs uses its Conversational AI WebSocket and waits for `agent_response_complete`. AssemblyAI uses the configured stored `agent_id`, injects each scripted caller message with `conversation.message`, requests an agent response with `reply.create`, and waits for `reply.done` before ending the session. This text-based path requires only `ASSEMBLYAI_API_KEY`; it does not use ElevenLabs TTS or synthesize caller audio. Vapi creates a WebSocket transport call. Retell currently exposes simulation testing through its REST API; it does not expose a direct client-to-agent WebSocket for this test flow, so the Retell adapter uses its batch simulation API and returns the provider transcript. No provider response is fabricated if connection, authentication, or transcript retrieval fails.

Evaluation jobs require Redis and a running ARQ worker. Jobs can take several minutes depending on provider response time and retry delays.

## Testing your own CRM/database tool endpoint

The Integrations page also supports a developer-configured HTTP endpoint. The
developer's application remains responsible for database and CRM access; Novora
replays a sample provider contract against that application and records its
actual response, HTTP status, and latency. The Vapi view shows webhook
round-trip metrics and validates the `toolCallId` response contract. The Retell
view shows the custom-function request and observed HTTP result as an event log;
it is not a simulated WebSocket connection.

Use HTTPS and a bearer token where required. The backend encrypts that token,
authenticates endpoint-management requests, scopes endpoint configurations and
history to the signed-in user, and blocks private-network destinations by
default. To reach a local development service, explicitly set
`NOVORA_ALLOW_PRIVATE_TOOL_ENDPOINTS=true` in the backend environment. GET is
the default read-only method; other methods require a per-run write confirmation.
