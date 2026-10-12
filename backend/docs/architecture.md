# Novora Platform Architecture — Claude A

## 1. System Vision & Context

Novora is a modular AI voice-agent infrastructure platform. Its core purpose is to verify whether voice agents satisfy business outcomes, comply with operational policies, and complete required workflows with traceable, auditable evidence.

This document describes the modular architecture established by **Claude A (Core & Evaluation Engine)**.

```
                    ┌───────────────────────────────┐
                    │  Caller / Client (Web / API)  │
                    └───────────────┬───────────────┘
                                    │ HTTP / JSON
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                          NOVORA CORE PLATFORM                          │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                        api module                              │   │
│   │  - FastAPI Routes (/scenarios, /evaluations)                   │   │
│   │  - Request Validation & Response Serialization (Pydantic)      │   │
│   │  - Auth & Error Handlers                                       │   │
│   └───────────────────────┬────────────────────────┬───────────────┘   │
│                           │                        │                   │
│                           ▼                        ▼                   │
│   ┌───────────────────────────────┐        ┌───────────────────────┐   │
│   │       evaluation module       │        │     core (domain)     │   │
│   │  - EvaluationOrchestrator     │        │  - EvaluationScenario │   │
│   │  - Rule Registry & Evaluators │◄───────┤  - Conversation       │   │
│   │  - Evidence Extractors        │        │  - RuleResult         │   │
│   │  - Report Generator           │        │  - EvaluationReport   │   │
│   └───────────────┬───────────────┘        └───────────┬───────────┘   │
│                   │                                    │               │
│                   ▼                                    ▼               │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                       adapters module                          │   │
│   │  - Storage Repository (InMemory / Postgres Interface)          │   │
│   │  - Persistence Entities & Serialization                        │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   ┌──────────────────────────────┐         ┌───────────────────────┐   │
│   │      providers (future)      │         │    runtime (future)   │   │
│   │  - Voice Provider Adapters   │         │  - Stateful agent     │   │
│   │  - LLM Judge Adapter         │         │  - Tool calling       │   │
│   └──────────────────────────────┘         └───────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Modular Boundaries

Novora follows a **modular monolith** design pattern with strict package separation:

| Module | Responsibility | Ownership |
| :--- | :--- | :--- |
| `novora.core` | Domain entities, enums, value objects, domain interfaces, business rules. | Claude A |
| `novora.evaluation` | Deterministic rule engine, evidence collectors, rule scorers, regression diff comparator. | Claude A |
| `novora.providers` | Capability protocols for voice-agent platforms, telephony, and transcription providers. | Claude A |
| `novora.adapters` | Provider payload normalizers (ElevenLabs, Twilio, AssemblyAI, transcript import), storage repositories. | Claude A |
| `novora.api` | FastAPI application, route controllers, schemas, webhooks, dependency injection. | Claude A |
| `novora.runtime` | Stateful runtime, live audio streaming, handoffs (Voxia — deferred to later milestone). | Future Phase |

---

## 3. Core Architectural Decisions

1. **Deterministic Rules First**:
   - Evaluation rules run deterministically.
   - Every rule result produces an explicit status (`PASS`, `FAIL`, `INCONCLUSIVE`) accompanied by exact character/message evidence spans.
   - Subjective or stochastic LLM judging is isolated behind a secondary provider interface and never treated as ground truth.
2. **Provider-Agnostic Core**:
   - The core domain model (`Conversation`, `ConversationMessage`) is normalized and strictly detached from provider-specific webhook formats.
   - Upstream providers must normalize their conversation events into Novora's standard format before triggering an evaluation.
3. **Traceability & Evidence Invariance**:
   - Every check must cite the exact message IDs, speaker, and snippet spans.
   - Missing evidence can **never** result in a `PASS` status.
   - External claims (e.g. "I have refunded $50") without trusted backend confirmation are flagged as `UNSUPPORTED_CLAIM`.
4. **Clean Persistence Abstraction**:
   - Repositories are defined as abstract protocols (`ScenarioRepository`, `EvaluationRepository`).
   - Development and testing run against an in-memory repository; production connects to PostgreSQL via identical contracts.
