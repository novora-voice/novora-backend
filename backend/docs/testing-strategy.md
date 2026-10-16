# Novora Testing Strategy & Verification Plan

## 1. Testing Pyramid

Novora employs a three-tier testing strategy:

1. **Unit Tests (Fast, Isolated)**:
   - Deterministic rule evaluators (100% offline, deterministic).
   - Event normalizers for ElevenLabs, AssemblyAI, Vapi, Retell.
   - Pydantic models, schema validation, and SQL persistence entities.
   - Security checks: SSRF URL validation, signature verification, prompt injection sanitizer.

2. **Integration Tests (Mocked Providers & Local SQLite/Memory)**:
   - Ghost caller simulated conversations against mock provider WebSockets and HTTP APIs.
   - Tool execution sandbox: mock external databases and authorized tools.
   - LLM Judge offline evaluator: mock structured response parser and confidence aggregator.
   - End-to-end evaluation pipeline: Scenario -> Ghost Caller -> Normalization -> Evaluation -> DB Report.

3. **Opt-in Live Integration Tests**:
   - Gated behind environment variables (`LIVE_TEST_ELEVENLABS_API_KEY`, `LIVE_TEST_VAPI_KEY`, etc.).
   - Execute against isolated staging agents without contacting production telephone lines.

## 2. Test Execution
Run test suite:
```powershell
.venv\Scripts\pytest.exe -v
```
Run live provider tests (when keys configured):
```powershell
$env:ENABLE_LIVE_PROVIDER_TESTS="1"; .venv\Scripts\pytest.exe -v -m live
```
