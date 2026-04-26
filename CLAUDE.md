# CLAUDE.md — Agentic Developer Environment

## Project Purpose

The **Agentic Developer Environment (ADE)** is a multi-agent system that autonomously executes software engineering tasks. A developer submits a natural-language task (e.g. "build an auth module with JWT") via CLI or React UI; the system decomposes it into steps, generates code, runs tests in an isolated sandbox, and streams results back in real time.

The system is built on a **Supervisor + Pipeline** multi-agent pattern orchestrated by [LangGraph](https://github.com/langchain-ai/langgraph), with a TypeScript Gateway API, Python backend services, Supabase for persistence, and Redis for caching and pub/sub.

---

## Repo Map

```
agentic-developer-environment/
├── CLAUDE.md                          ← you are here
├── ROADMAP.md                         ← module breakdown + plan prompts (47 modules)
├── README.md
├── docker-compose.yml                 ← all services + infra
├── .env.example
├── Makefile                           ← build / test / lint / dev commands
│
├── docs/
│   ├── architecture.md                ← full system design (start here)
│   ├── api-contracts.md               ← REST + gRPC + WebSocket specs
│   ├── database-schema.md             ← ERD + table definitions + DDL
│   └── decisions/                     ← Architecture Decision Records (ADRs)
│
├── packages/
│   ├── shared-types/                  ← Pydantic models (Python) + mirrored TS types
│   └── proto/                         ← gRPC .proto definitions (orchestrator, sandbox, context)
│
├── services/
│   ├── gateway/                       ← TypeScript — REST API + WebSocket server (Fastify)
│   ├── orchestrator/                  ← Python — LangGraph supervisor + agent subgraphs
│   ├── sandbox/                       ← Python — Docker container execution isolation
│   └── context/                       ← Python — RAG indexer + vector search (pgvector)
│
├── cli/                               ← Python CLI (Typer + Rich)
├── ui/                                ← React + TypeScript frontend (Vite)
│
├── infra/
│   ├── supabase/migrations/           ← numbered SQL migrations (001–006)
│   └── docker/nginx.conf              ← reverse proxy config
│
└── tests/
    ├── integration/                   ← end-to-end workflow + sandbox tests
    └── fixtures/sample_project/       ← test project for integration runs
```

---

## Key Commands

```bash
# Start all services (Gateway, Orchestrator, Sandbox, Context, Supabase, Redis)
make dev

# Build all Docker images
make build

# Run all tests (unit + integration)
make test

# Run linters across all services
make lint

# Apply Supabase database migrations
make migrate

# Generate gRPC stubs from .proto files
make proto

# Tear down all containers and volumes
make clean
```

---

## Architectural Constraints

1. **Supervisor routes, never executes.** The supervisor LLM call only decides which subgraph to invoke next — it never directly modifies state or calls tools.

2. **Strict tool isolation per agent.**
   - Planner: no file-write tools
   - Codegen: file-write only, no execution
   - Executor: sandbox-only execution
   - Context: read-only codebase access

3. **All state persists to Supabase.** LangGraph checkpoints are saved after every node via `SupabaseCheckpointer`. Workflows survive restarts and can be replayed or forked from any checkpoint.

4. **Quality gates before returning to supervisor.** Codegen output is syntax-checked and linted before the supervisor sees it; failures trigger a local retry loop (max 3 iterations) inside the codegen subgraph.

5. **Sandbox execution is fully ephemeral.** Each execution request creates a fresh Docker container with: 1 CPU core, 512 MB RAM, 60 s timeout, no outbound network, read-only root filesystem (except `/tmp`), non-root user, dropped Linux capabilities.

6. **Model routing by task complexity.** Supervisor uses a strong model (Claude Opus / GPT-4o) for routing accuracy; worker agents use faster models (Claude Sonnet / GPT-4o-mini) for cost efficiency.

7. **Redis as the event bus.** The orchestrator publishes `WorkflowEvent` messages to Redis pub/sub channels; the Gateway subscribes and fans out to connected WebSocket clients. Never couple Gateway ↔ Orchestrator over HTTP polling.

8. **Row-Level Security everywhere.** All Supabase tables have RLS policies scoped to `project_id` for multi-tenant isolation. Never bypass RLS in application code.

---

## Further Reading

| Topic | File |
|---|---|
| Full system design + diagrams | [`docs/architecture.md`](docs/architecture.md) |
| MVP module breakdown + plan prompts | [`ROADMAP.md`](ROADMAP.md) |
| REST, gRPC, and WebSocket contracts | [`docs/api-contracts.md`](docs/api-contracts.md) |
| Database ERD + table DDL | [`docs/database-schema.md`](docs/database-schema.md) |
| Architecture decisions (ADRs) | [`docs/decisions/`](docs/decisions/) |
| LangGraph graph definitions | [`services/orchestrator/src/graphs/`](services/orchestrator/src/graphs/) |
| Agent implementations | [`services/orchestrator/src/agents/`](services/orchestrator/src/agents/) |
| Agent prompt templates | [`services/orchestrator/src/prompts/`](services/orchestrator/src/prompts/) |
| Event publisher (Redis pub/sub) | [`services/orchestrator/src/events/`](services/orchestrator/src/events/) |
| gRPC service definitions | [`packages/proto/`](packages/proto/) |
| Shared Pydantic + TS types | [`packages/shared-types/`](packages/shared-types/) |
