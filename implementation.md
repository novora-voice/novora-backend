# Novora Implementation: Production Knowledge Base, Hybrid RAG, Graph RAG, and Organization-Level RBAC

## Role

Act as a senior backend and AI infrastructure engineer specializing in RAG systems, hybrid retrieval, Graph RAG, vector databases, graph databases, multi-tenant SaaS architecture, FastAPI, PostgreSQL, and secure integrations.

Your task is to implement the production Knowledge Base functionality and organization-level access controls in my existing Novora platform.

This is an implementation task. Inspect the existing repositories, understand the existing architecture and connector prototypes, and implement the features without breaking the current platform.

## 1. Product objective

Novora must allow organizations to connect their own knowledge infrastructure, ingest and manage documents, retrieve relevant knowledge, connect that knowledge to agents, and evaluate whether agents use that knowledge correctly.

**Important architectural decision: Customers own their knowledge databases. Novora provides the integration and retrieval infrastructure.**

Do not force customers to use a Novora-owned vector database.

Support both:

- Customer-managed vector databases.
- Customer-managed graph databases.

Novora should provide a provider-neutral integration layer so customers can change database providers without rewriting agent workflows.

Implement organization-level access control as part of this work so knowledge bases, documents, connections, and agents are isolated and accessible only to authorized organization members.

## 2. Repository audit and safety

Before implementation:

1. Inspect the existing backend and frontend repositories.
2. Inspect current Git branches and working-tree changes.
3. Locate the existing Knowledge Base page, connector prototypes, database models, authentication, agent configuration, scenario/evaluation engine, and API contracts.
4. Identify existing organization, user, workspace, and membership models.
5. Identify existing document storage and file-upload mechanisms, if any.
6. Inspect existing migrations and testing conventions.
7. Document what already works and what is missing.

Preserve existing user changes.

Do not reset, discard, overwrite, or replace existing code unnecessarily.

Do not redesign unrelated frontend pages. Preserve the existing Novora branding, design system, navigation, components, and layouts. Extend the existing Knowledge Base UI.

Use the existing feature branch if appropriate. Otherwise, create a safe feature branch without losing uncommitted work.

Do not merge or deploy automatically.

After the audit, implement the functionality instead of stopping at a proposal.

## 3. Customer-owned knowledge infrastructure

Support the following vector database providers:

- Chroma
- Pinecone
- Weaviate
- Qdrant

Support graph database connectivity:

- Neo4j
- An extensible provider interface for additional graph databases.

Do not assume every provider has identical capabilities.

Create separate provider-neutral interfaces for vector and graph operations.

Suggested interfaces:

Vector database:
- connect()
- validate_connection()
- create_or_validate_collection()
- upsert_documents()
- delete_documents()
- search()
- get_collection_metadata()
- health_check()

Graph database:
- connect()
- validate_connection()
- create_or_validate_schema()
- query()
- retrieve_related_entities()
- health_check()

Adapt these interfaces to the actual capabilities of each provider.

Implement individual adapters rather than placing provider-specific conditionals throughout the application.

The runtime should use the same retrieval interface regardless of which provider the customer selects.

### Customer connection configuration

Customers must be able to configure:

- Provider.
- Connection endpoint or approved connection mechanism.
- Authentication credentials.
- Collection or index name.
- Namespace where supported.
- Relevant provider-specific settings.
- Organization ownership.
- Knowledge base association.

Do not expose credentials to the frontend after initial submission.

Encrypt stored credentials using the existing Novora encryption architecture. Never store plaintext secrets.

Use secure secret handling, connection validation, endpoint restrictions, and appropriate network access controls.

Do not accept arbitrary unrestricted URLs or implement unsafe server-side fetching.

External database connections should use read-only credentials by default unless a particular operation genuinely requires write access.

For customer-owned vector databases, document the minimum permissions needed for document indexing and retrieval.

## 4. Knowledge Base management

Implement complete Knowledge Base CRUD functionality.

An organization should be able to:

- Create a knowledge base.
- Give it a name and description.
- Select a vector database connection.
- Optionally connect a graph database.
- Configure the collection or namespace.
- View connection status.
- Test database connectivity.
- Edit configuration.
- Associate the knowledge base with agents.
- View its documents and ingestion history.
- Delete or archive it safely.

A knowledge base belongs to an organization.

An agent must not be able to access a knowledge base belonging to another organization.

Support multiple knowledge bases per organization and the ability to associate an agent with one or more authorized knowledge bases.

Do not assume every agent needs graph retrieval.

Allow customers to configure vector-only, graph-only where supported, or hybrid retrieval.

## 5. Document ingestion pipeline

Implement production-oriented document ingestion.

Support practical document formats such as:

- PDF.
- DOCX.
- TXT.
- Markdown.
- CSV, where a suitable ingestion strategy exists.

Inspect existing dependencies before adding new document-processing libraries.

### Ingestion workflow

Implement the following pipeline:

1. User uploads a document.
2. Validate organization permissions.
3. Validate file type, size, and content.
4. Persist the document metadata.
5. Extract text.
6. Normalize extracted text.
7. Extract useful metadata.
8. Split the content into configurable chunks.
9. Generate embeddings.
10. Upsert chunks into the customer's selected vector database.
11. Optionally process structured entities and relationships for graph indexing.
12. Update ingestion status.
13. Record errors and ingestion history.

Use background jobs for long-running ingestion tasks where the existing ARQ infrastructure is suitable.

Do not perform long document ingestion inside an ordinary synchronous HTTP request.

### Document metadata

Persist relevant information:

- Document ID.
- Organization ID.
- Knowledge base ID.
- Original filename.
- MIME type.
- File size.
- Content hash.
- Storage reference.
- Ingestion status.
- Chunk count.
- Embedding model identifier.
- Vector provider and collection.
- Uploading user.
- Created and updated timestamps.
- Error details where applicable.

Support duplicate detection through content hashes.

Implement safe document replacement, re-indexing, and deletion.

When deleting or replacing a document, ensure its corresponding indexed chunks are also handled correctly.

Use idempotent job handling where possible.

### Storage

Inspect existing storage infrastructure.

If there is an existing file-storage mechanism, reuse it.

Otherwise, implement a storage abstraction that supports local development and can later use compatible object storage.

Do not assume a paid cloud storage service is available.

Do not store large documents or binary files directly in PostgreSQL unless the existing architecture has a deliberate reason to do so.

## 6. Embedding infrastructure

Implement an embedding abstraction independent of vector database providers.

The embedding generation process must support remote inference through an appropriate configurable provider.

If Hugging Face Inference Providers are used, verify that the chosen model and provider support the required embedding task.

Do not run local embedding models or silently switch to a paid service.

Make embedding configuration explicit.

Persist the embedding model identifier and relevant indexing configuration with the knowledge base or index metadata.

**Important:** Documents indexed with one embedding model cannot safely be queried with an incompatible embedding model.

Implement validation that prevents incompatible query embeddings from being used against an existing index.

If the customer supplies a pre-indexed external knowledge base, support retrieval from it where compatible without requiring Novora to re-ingest all its documents.

Do not assume that every external database contains embeddings generated by the same model.

## 7. Retrieval engine

Implement a provider-neutral retrieval service.

A query should include:

- Organization ID.
- Agent ID.
- Knowledge base IDs.
- User question.
- Retrieval configuration.
- Optional metadata filters.
- Optional graph retrieval configuration.

### Vector retrieval

Support:

- Similarity search.
- Configurable top-k.
- Metadata filtering.
- Namespace or collection selection.
- Relevance scores where supported.
- Source document and chunk identifiers.
- Retrieval latency.

### Graph retrieval

Where a graph database is configured, support:

- Entity retrieval.
- Related entity lookup.
- Relationship traversal.
- Relevant context retrieval.
- Safe, parameterized queries.
- Query restrictions.

Never execute arbitrary graph queries supplied directly by an end user or untrusted LLM without validation and authorization.

### Hybrid retrieval

Combine vector and graph retrieval when both are configured.

The system should:

1. Retrieve semantically relevant chunks.
2. Identify useful entities and relationships.
3. Retrieve related graph context.
4. Merge and deduplicate evidence.
5. Rank or rerank results where supported.
6. Return a structured evidence package.

Keep vector-only retrieval fully functional when graph infrastructure is absent.

Do not force graph database setup on customers who only want vector RAG.

### Retrieval result

Return a structured result containing:

- Query.
- Knowledge base IDs.
- Source document IDs.
- Chunk IDs.
- Retrieved text.
- Provider and collection.
- Similarity/relevance scores where available.
- Graph entities and relationships where applicable.
- Retrieval latency.
- Retrieval errors or partial-result indicators.

Do not fabricate sources, similarity scores, or graph relationships.

## 8. Agent integration

Knowledge bases must be configurable on existing Novora agents.

Extend the existing agent configuration rather than introducing a completely separate agent system.

Allow authorized users to:

- Attach one or more knowledge bases to an agent.
- Select retrieval mode.
- Configure top-k.
- Configure metadata filters.
- Enable or disable graph retrieval.
- Configure retrieval thresholds where supported.
- Inspect the knowledge bases available to an agent.

At runtime:

1. Agent receives a user request.
2. Runtime identifies the agent's authorized knowledge bases.
3. Retrieval executes with organization and permission filters.
4. Retrieved evidence is added to the agent's context.
5. The LLM generates an answer grounded in that evidence.
6. Sources are retained in the execution trace.

The agent should distinguish between:

- Information supported by retrieved evidence.
- Information not found in the knowledge base.
- Conflicting sources.
- Retrieval failures.

If relevant information is unavailable, the agent must be able to say it does not have sufficient information rather than inventing an answer.

Avoid injecting an entire knowledge base into the LLM context. Retrieve only relevant evidence.

Preserve the existing Novora provider agent workflows.

For external agents, support knowledge retrieval through the existing integration mechanisms where possible. For Novora's own runtime, provide a native retrieval tool/interface.

## 9. Knowledge-grounded evaluations

This is a critical Novora differentiator.

Extend the existing evaluation engine to support knowledge-grounded evaluation.

Do not create an unrelated second evaluation engine.

Capture retrieval evidence alongside conversation and tool execution evidence.

Add evaluation capabilities such as:

### Retrieval evaluation

- Was relevant information retrieved?
- Were the correct source documents retrieved?
- Were relevant chunks missing?
- Was the retrieval context sufficient?
- Did retrieval return irrelevant information?

### Groundedness evaluation

- Is the response supported by retrieved evidence?
- Did the agent invent information?
- Did the agent contradict the source material?
- Did it ignore relevant evidence?
- Did it acknowledge missing information?

### Source evaluation

- Can the answer be traced to its source documents?
- Are the cited sources associated with the correct organization?
- Were source permissions respected?
- Was the correct knowledge base used?

### Deterministic checks

Where appropriate, implement deterministic rules for:

- Required source presence.
- Required metadata.
- Allowed knowledge base IDs.
- Prohibited source usage.
- Missing retrieval evidence.
- Unauthorized knowledge access.

LLM-based judges may evaluate semantic groundedness, but deterministic security and evidence failures must not be overridden by positive LLM judgments.

A missing retrieval trace must not be interpreted as a successful grounded answer.

Store the evaluation evidence so users can inspect why an agent passed or failed.

## 10. Organization-level RBAC

Implement proper organization-level access control.

First inspect whether the existing database already supports organizations, workspaces, memberships, or roles.

Reuse existing structures where possible. Avoid introducing duplicate tenant models.

At minimum, support these roles:

- Owner.
- Admin.
- Member.
- Viewer.

Define and enforce permissions for:

**Owner**
- Full organization access.
- Manage organization settings.
- Invite and remove members.
- Assign roles.
- Manage integrations, knowledge bases, and agents.
- Access organization resources.

**Admin**
- Manage organization members according to the defined policy.
- Manage agents, integrations, and knowledge bases.
- Manage scenarios and evaluations.
- Cannot transfer ownership or perform owner-only actions.

**Member**
- Access authorized organization resources.
- Create and manage permitted agents, knowledge bases, scenarios, and evaluations.
- Cannot change organization-level security settings or assign privileged roles.

**Viewer**
- Read-only access to permitted resources.
- Cannot create, edit, delete, or execute privileged operations.

Implement a centralized permission-checking mechanism.

Do not rely on frontend visibility as authorization.

Every protected backend operation must verify:

1. Authenticated user.
2. Organization membership.
3. Role permissions.
4. Resource ownership.
5. Resource-to-organization relationship.

Apply tenant isolation to:

- Knowledge bases.
- Documents.
- Database connections.
- Agents.
- Scenarios.
- Evaluation runs.
- Reports.
- Retrieval requests.
- Session evidence.

Prevent IDOR vulnerabilities and cross-organization resource access.

Ensure background jobs preserve organization context and revalidate resource ownership before processing.

Implement migrations using the existing migration system.

If the current schema lacks organizations and memberships, add them safely with a migration strategy that preserves existing user data and handles existing resources.

## 11. Frontend implementation

Extend the existing Knowledge Base page.

Preserve Novora's existing design, branding, navigation, components, and overall layout.

Do not redesign the application.

Implement the following views and workflows:

### Knowledge Base overview

Display:

- Knowledge base name.
- Description.
- Organization.
- Vector provider.
- Graph provider, if configured.
- Connection status.
- Number of documents.
- Ingestion status.
- Last updated.

### Create Knowledge Base

Allow a user to:

1. Enter the name and description.
2. Select a vector provider.
3. Configure its connection.
4. Validate the connection.
5. Optionally configure a graph provider.
6. Validate the graph connection.
7. Create the knowledge base.

Clearly explain that customers provide and own their database infrastructure.

Do not display fake successful connections.

### Document management

Allow authorized users to:

- Upload supported files.
- View documents.
- View processing status.
- View ingestion errors.
- Re-index documents.
- Delete documents.
- Inspect ingestion history.

Provide meaningful loading, empty, error, and success states.

### Agent configuration

Allow users to attach knowledge bases to agents and configure retrieval behavior.

Show which knowledge sources an agent can access.

### Organization settings

Provide member management and role assignment based on permissions.

Do not show administrative actions to users who do not have permission, but always enforce permissions in the backend.

Use the existing component library and patterns.

Do not introduce mock data as if it were real production state.

## 12. API design

Inspect existing routes before defining new ones.

Implement consistent API contracts for:

- Organization membership and roles.
- Knowledge base creation, update, deletion, and listing.
- Vector and graph connection validation.
- Document upload and management.
- Ingestion status and history.
- Agent-to-knowledge-base associations.
- Retrieval testing.
- Retrieval evidence.
- Knowledge-grounded evaluation.

Use the existing FastAPI conventions, authentication, response models, and error handling.

Document all newly introduced endpoints.

Do not invent endpoint names in the frontend without implementing the corresponding backend contracts.

## 13. Security requirements

Treat customer knowledge and database credentials as sensitive.

Implement:

- Encrypted credential storage.
- Organization-level isolation.
- Permission-aware retrieval.
- Safe file validation.
- Upload size restrictions.
- SSRF protection.
- Connection timeouts.
- Safe database query execution.
- Read-only database credentials by default.
- Secret redaction in logs.
- Safe deletion and re-indexing.
- Background-job authorization.
- Audit logging for sensitive operations.

Do not allow one organization to query, retrieve, modify, or inspect another organization's documents or database connections.

## 14. Testing

Add tests using the existing test framework.

### Unit tests

Test:

- Each vector adapter.
- Graph adapter interfaces.
- Connection validation.
- Document parsing.
- Chunking.
- Embedding interface.
- Retrieval.
- Hybrid retrieval.
- Permission checking.
- Role authorization.
- Tenant isolation.
- Document deletion and re-indexing.
- Groundedness evaluation.
- Error handling.

Mock external providers by default. Automated tests must not require paid database services or inference requests.

### Integration tests

Verify:

1. An organization creates a knowledge base.
2. It configures a vector database connection.
3. The connection is validated.
4. A document is uploaded.
5. The document is processed and indexed.
6. A retrieval query returns the correct evidence.
7. An agent uses the retrieved evidence.
8. The evaluation engine receives the retrieval trace.
9. A groundedness evaluation is produced.
10. Another organization cannot access the knowledge base.

Also verify graph retrieval and hybrid retrieval with mock graph/vector adapters.

Test all four roles and cross-tenant access attempts.

### Provider smoke tests

Provide opt-in tests for actual customer-configured databases.

Do not require provider credentials for the standard test suite.

Clearly distinguish mocked tests from live provider tests.

## 15. Implementation milestones

**Milestone 1 — Architecture and security audit**

Inspect existing models, connectors, authentication, and frontend. Establish the organization and tenant ownership strategy.

**Milestone 2 — RBAC foundation**

Implement organization membership, roles, centralized permission checks, tenant isolation, and migrations.

**Milestone 3 — Knowledge Base and connection management**

Implement knowledge base CRUD, customer-owned vector and graph connections, secure credential storage, and connection validation.

**Milestone 4 — Document ingestion**

Implement parsing, chunking, embeddings, indexing, job status, and document management.

**Milestone 5 — Retrieval**

Implement provider-neutral vector retrieval, graph retrieval, and hybrid retrieval.

**Milestone 6 — Agent integration**

Connect knowledge bases to existing agents and make retrieval available during agent execution.

**Milestone 7 — Knowledge-grounded evaluation**

Extend Novora's existing evaluation engine with retrieval evidence, groundedness checks, and source verification.

**Milestone 8 — Frontend**

Extend the existing Knowledge Base, agent configuration, and organization settings pages without redesigning unrelated UI.

**Milestone 9 — Testing and documentation**

Run tests, verify tenant isolation, validate integrations, and document the implementation.

Keep the application runnable throughout implementation.

## 16. Definition of done

- [ ] Organizations can manage their own knowledge bases.
- [ ] Customers can connect Chroma, Pinecone, Weaviate, and Qdrant through provider adapters.
- [ ] Customers can connect Neo4j through a graph adapter.
- [ ] Vector and graph providers are independent.
- [ ] Documents can be uploaded, parsed, chunked, embedded, and indexed.
- [ ] Customers can manage document ingestion and indexing.
- [ ] Agents can access authorized knowledge bases.
- [ ] Vector retrieval works.
- [ ] Graph retrieval works where configured.
- [ ] Hybrid retrieval works when both sources are available.
- [ ] Retrieved sources are preserved as execution evidence.
- [ ] Novora can evaluate retrieval quality and answer groundedness.
- [ ] Organization-level RBAC is enforced by the backend.
- [ ] Cross-organization access is prevented.
- [ ] Credentials are encrypted.
- [ ] Existing provider evaluation functionality remains intact.
- [ ] Existing frontend design is preserved.
- [ ] Automated tests pass.
- [ ] Documentation explains configuration, permissions, ingestion, retrieval, and provider requirements.

## 17. Final implementation report

Provide:

1. Repository and branch modified.
2. Existing architecture discovered.
3. Database migrations introduced.
4. Models and API routes implemented.
5. Vector and graph adapters implemented.
6. Document ingestion pipeline details.
7. Retrieval and hybrid RAG implementation.
8. Agent integration details.
9. Knowledge-grounded evaluation implementation.
10. RBAC roles and permissions.
11. Security controls.
12. Frontend changes.
13. Tests run and actual results.
14. Provider integrations verified against real services.
15. Remaining limitations and next steps.

Do not claim that an adapter is production-verified merely because its interface or mocked tests exist.

**Final instruction:** Implement a real multi-tenant Knowledge Base infrastructure for Novora, not just a document upload page. Customers own their databases, Novora connects to them, agents retrieve from them, and Novora evaluates whether those agents use the knowledge correctly.