# ADE MVP — Module Breakdown & Plan Prompts

> **How to use this document**
>
> - There are **7 phases** (0-6), containing **47 modules** total.
> - Each module = **one plan** = **one PR**.
> - Modules within a phase can often be built **in parallel** (see dependency graph at the bottom).
> - Every module has a **Plan Mode Prompt** block — copy-paste it directly into Cursor plan mode to generate the implementation.
> - No module exceeds **500-800 lines** of production code (excluding tests).
>
> **MVP fast-path** (21 modules for first end-to-end flow):
> M01 → M03 → M04 → M05 → M06 → M07 → M10 → M12 → M13 → M15 → M16 → M17 → M18 → M20 → M22 → M23 → M26 → M27 → M28 → M29 → M36

---

## Phase 0 — Foundation

### M01: Shared Python Types

| Field | Detail |
|-------|--------|
| **Files** | `packages/shared-types/python/ade_types/__init__.py`, `task.py`, `agent.py`, `artifact.py`, `project.py`, `pyproject.toml` |
| **Dependencies** | None |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- `from ade_types import Task, TaskStep, WorkflowEvent` works
- All models roundtrip through `model_validate_json` / `model_dump_json`
- Enums use `StrEnum` for JSON serialization

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the shared Python type definitions for the Agentic Developer Environment (ADE). These Pydantic v2 models are used by every Python service in the system.

## Context
Read `CLAUDE.md` and `docs/architecture.md` for full system context. The database schema in `docs/architecture.md` Section 3 defines the exact field names and types these models must match.

## Files to create

### `packages/shared-types/python/pyproject.toml`
- Package name: `ade-types`
- Python >=3.12
- Dependencies: `pydantic>=2.6`
- Package dir: `ade_types`

### `packages/shared-types/python/ade_types/__init__.py`
- Re-export all public models from the submodules below.

### `packages/shared-types/python/ade_types/task.py`
Define these Pydantic v2 `BaseModel` classes:
- `TaskStatus(StrEnum)`: pending, planning, executing, reviewing, completed, failed
- `StepStatus(StrEnum)`: pending, in_progress, completed, failed, skipped
- `AgentType(StrEnum)`: planner, codegen, executor, context
- `TaskStep(BaseModel)`: id (UUID), task_id (UUID), ordinal (int), title (str), description (str), status (StepStatus), agent_type (AgentType), input_data (dict | None), output_data (dict | None), started_at (datetime | None), completed_at (datetime | None)
- `Task(BaseModel)`: id (UUID), project_id (UUID), prompt (str), status (TaskStatus), metadata (dict), created_at (datetime), updated_at (datetime)

### `packages/shared-types/python/ade_types/agent.py`
- `AgentRunStatus(StrEnum)`: running, completed, failed, timeout
- `AgentRun(BaseModel)`: id (UUID), task_id (UUID), step_id (UUID | None), agent_type (AgentType), model (str), status (AgentRunStatus), input_state (dict | None), output_state (dict | None), tokens_in (int), tokens_out (int), latency_ms (int), retry_count (int), created_at (datetime)
- `AgentMetric(BaseModel)`: id (UUID), run_id (UUID), agent_type (AgentType), metric_name (str), metric_value (float), labels (dict), recorded_at (datetime)

### `packages/shared-types/python/ade_types/artifact.py`
- `CodeArtifact(BaseModel)`: id (UUID), run_id (UUID), task_id (UUID), file_path (str), content (str), diff (str | None), language (str), version (int), created_at (datetime)
- `ExecutionResult(BaseModel)`: id (UUID), run_id (UUID), task_id (UUID), command (str), stdout (str), stderr (str), exit_code (int), duration_ms (int), sandbox_id (str), created_at (datetime)

### `packages/shared-types/python/ade_types/project.py`
- `Project(BaseModel)`: id (UUID), name (str), repo_url (str | None), repo_path (str | None), settings (dict), created_at (datetime), updated_at (datetime)
- `ContextChunk(BaseModel)`: id (UUID), project_id (UUID), file_path (str), chunk_content (str), embedding (list[float] | None), metadata (dict), indexed_at (datetime)
- `WorkflowEvent(BaseModel)`: event_type (str), step_id (str | None), payload (dict), timestamp (int)
- `ConversationMessage(BaseModel)`: id (UUID), task_id (UUID), role (Literal["user","assistant","system","tool"]), content (str), metadata (dict), created_at (datetime)

## Constraints
- Use Pydantic v2 syntax (`model_config = ConfigDict(...)`) not v1 `class Config`.
- All UUID fields should use `uuid.UUID` type.
- All datetime fields should use `datetime` from `datetime` module with UTC timezone awareness.
- All models must support `model_validate_json()` roundtrip.
- Use `StrEnum` for all enum types so they serialize as strings in JSON.
- Do not add ORM or database logic — these are pure data models.
- Total code must stay under 300 lines across all files.
```

</details>

---

### M02: Shared TypeScript Types

| Field | Detail |
|-------|--------|
| **Files** | `packages/shared-types/typescript/src/index.ts`, `package.json`, `tsconfig.json` |
| **Dependencies** | M01 (mirrors its shapes) |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- `tsc --noEmit` passes
- Zod schemas validate example payloads
- Types match M01 Python models 1:1

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the shared TypeScript type definitions for the Agentic Developer Environment (ADE). These must mirror the Python Pydantic models in `packages/shared-types/python/ade_types/` exactly.

## Context
Read `CLAUDE.md` and `docs/architecture.md` for full system context. Read the Python models in `packages/shared-types/python/ade_types/` (task.py, agent.py, artifact.py, project.py) — the TypeScript types must match every field name, type, and enum value.

## Files to create

### `packages/shared-types/typescript/package.json`
- Name: `@ade/shared-types`
- Private: true
- Dependencies: `zod` (latest)
- devDependencies: `typescript` (latest)
- Main entry: `dist/index.js`, types: `dist/index.d.ts`
- Scripts: `build: tsc`, `typecheck: tsc --noEmit`

### `packages/shared-types/typescript/tsconfig.json`
- Target: ES2022, module: ESNext, moduleResolution: bundler
- Strict: true, declaration: true, outDir: dist
- Include: `src/**/*.ts`

### `packages/shared-types/typescript/src/index.ts`
Define and export all of the following, using Zod schemas with inferred TypeScript types:

**Enums (as Zod enums):**
- `TaskStatus`: "pending" | "planning" | "executing" | "reviewing" | "completed" | "failed"
- `StepStatus`: "pending" | "in_progress" | "completed" | "failed" | "skipped"
- `AgentType`: "planner" | "codegen" | "executor" | "context"
- `AgentRunStatus`: "running" | "completed" | "failed" | "timeout"
- `MessageRole`: "user" | "assistant" | "system" | "tool"

**Schemas (Zod objects) + inferred types:**
- `TaskSchema` / `Task`: id (uuid string), project_id (uuid string), prompt (string), status (TaskStatus), metadata (record), created_at (ISO string), updated_at (ISO string)
- `TaskStepSchema` / `TaskStep`: id, task_id, ordinal (number), title, description, status (StepStatus), agent_type (AgentType), input_data (record, default {}), output_data (record, default {}), started_at (string | null), completed_at (string | null)
- `AgentRunSchema` / `AgentRun`: id, task_id, step_id (string | null), agent_type, model (string), status (AgentRunStatus), input_state, output_state, tokens_in (number | null), tokens_out (number | null), latency_ms (number | null), retry_count (number), created_at
- `AgentMetricSchema` / `AgentMetric`: id, run_id, agent_type, metric_name, metric_value (number), labels (record), recorded_at
- `CodeArtifactSchema` / `CodeArtifact`: id, run_id, task_id, file_path, content, diff (string | null), language, version (number), created_at
- `ExecutionResultSchema` / `ExecutionResult`: id, run_id, task_id, command, stdout, stderr, exit_code (number), duration_ms (number), sandbox_id, created_at
- `ProjectSchema` / `Project`: id, name, repo_url (string | null), repo_path (string | null), settings (record), created_at, updated_at
- `ContextChunkSchema` / `ContextChunk`: id, project_id, file_path, chunk_content, embedding (number array | null), metadata (record), indexed_at
- `WorkflowEventSchema` / `WorkflowEvent`: event_type, step_id (string | null), payload (record), timestamp (number)
- `ConversationMessageSchema` / `ConversationMessage`: id, task_id, role (MessageRole), content, metadata (record), created_at

**Also export:**
- A `WebSocketEventType` union type: "workflow.started" | "step.started" | "step.progress" | "step.completed" | "step.failed" | "artifact.created" | "execution.result" | "workflow.completed" | "workflow.error"
- Request/response types: `CreateTaskRequest` (project_id, prompt), `CreateTaskResponse` (task_id, status, ws_url), `CreateProjectRequest` (name, repo_url?, repo_path?, settings?)

## Constraints
- Use Zod for runtime validation, infer static types with `z.infer<>`.
- Every Zod schema must use `.strict()` to reject unknown fields.
- UUID fields are `z.string().uuid()`.
- Datetime fields are `z.string().datetime()`.
- Export both the Zod schema and the inferred type for each model.
- Total code must stay under 250 lines.
```

</details>

---

### M03: gRPC Proto Definitions

| Field | Detail |
|-------|--------|
| **Files** | `packages/proto/orchestrator.proto`, `sandbox.proto`, `context.proto`, `buf.gen.yaml` |
| **Dependencies** | None |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- `make proto` generates Python and TypeScript stubs without errors
- All message types match the contracts in `docs/architecture.md` Section 4b

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the gRPC protobuf service definitions for the three internal ADE services: OrchestratorService, SandboxService, and ContextService.

## Context
Read `docs/architecture.md` Section 4b — it contains the exact protobuf definitions to implement. Also read `CLAUDE.md` for the full repo structure.

## Files to create

### `packages/proto/orchestrator.proto`
```protobuf
syntax = "proto3";
package ade.orchestrator;
option go_package = "ade/orchestrator";

service OrchestratorService {
  rpc RunWorkflow(WorkflowRequest) returns (stream WorkflowEvent);
  rpc GetWorkflowStatus(WorkflowId) returns (WorkflowStatus);
  rpc CancelWorkflow(WorkflowId) returns (Ack);
}

message WorkflowRequest {
  string task_id = 1;
  string project_id = 2;
  string prompt = 3;
  map<string, string> metadata = 4;
}

message WorkflowEvent {
  string event_type = 1;
  string step_id = 2;
  string payload = 3;  // JSON-encoded
  int64 timestamp = 4;
}

message WorkflowId { string id = 1; }
message WorkflowStatus {
  string task_id = 1;
  string status = 2;
  int32 current_step = 3;
  int32 total_steps = 4;
  string current_agent = 5;
}
message Ack { bool success = 1; string message = 2; }
```

### `packages/proto/sandbox.proto`
```protobuf
syntax = "proto3";
package ade.sandbox;

service SandboxService {
  rpc CreateSandbox(SandboxConfig) returns (SandboxInfo);
  rpc Execute(ExecutionRequest) returns (ExecutionResult);
  rpc DestroySandbox(SandboxId) returns (Ack);
}

message SandboxConfig {
  string runtime = 1;    // "python3.12" | "node22"
  int32 cpu_cores = 2;   // default: 1
  int32 memory_mb = 3;   // default: 512
  int32 timeout_s = 4;   // default: 60
}
message SandboxInfo { string sandbox_id = 1; string status = 2; }
message SandboxId { string id = 1; }
message ExecutionRequest {
  string sandbox_id = 1;
  string command = 2;
  string code_path = 3;
  map<string, string> env = 4;
}
message ExecutionResult {
  string stdout = 1;
  string stderr = 2;
  int32 exit_code = 3;
  int64 duration_ms = 4;
}
message Ack { bool success = 1; string message = 2; }
```

### `packages/proto/context.proto`
```protobuf
syntax = "proto3";
package ade.context;

service ContextService {
  rpc IndexRepository(IndexRequest) returns (IndexResult);
  rpc RetrieveContext(ContextQuery) returns (ContextChunks);
  rpc WatchChanges(WatchRequest) returns (stream ChangeEvent);
}

message IndexRequest {
  string project_id = 1;
  string repo_path = 2;
  bool force_reindex = 3;
}
message IndexResult {
  int32 chunks_indexed = 1;
  int32 files_processed = 2;
  float duration_s = 3;
}
message ContextQuery {
  string project_id = 1;
  string query = 2;
  int32 top_k = 3;
  float threshold = 4;
}
message ContextChunk {
  string id = 1;
  string file_path = 2;
  string content = 3;
  float score = 4;
  string metadata_json = 5;
}
message ContextChunks { repeated ContextChunk chunks = 1; }
message WatchRequest { string project_id = 1; string repo_path = 2; }
message ChangeEvent {
  string file_path = 1;
  string change_type = 2;  // "created" | "modified" | "deleted"
  int64 timestamp = 3;
}
```

### `packages/proto/buf.gen.yaml`
Configure buf to generate:
- Python stubs using `grpcio-tools` (output to `services/orchestrator/src/generated/`, `services/sandbox/src/generated/`, `services/context/src/generated/`)
- TypeScript stubs using `@grpc/proto-loader` or `ts-proto` (output to `services/gateway/src/generated/`)

## Constraints
- Use proto3 syntax.
- Every service must have a health-check-compatible structure (or add an explicit `HealthCheck` rpc).
- Field numbering must be sequential and stable.
- Total proto code should be ~200 lines across all files.
```

</details>

---

### M04: Database Migrations & RLS

| Field | Detail |
|-------|--------|
| **Files** | `infra/supabase/migrations/001_projects.sql` through `006_metrics.sql`, `seed.sql` |
| **Dependencies** | None |
| **Est. lines** | ~400 |

**Acceptance criteria:**
- `make migrate` applies cleanly to fresh Supabase
- `seed.sql` inserts a sample project and task
- RLS blocks cross-project reads when tested with different JWTs

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create all Supabase SQL migration files and a seed file for the Agentic Developer Environment database.

## Context
Read `docs/architecture.md` Section 3 for the full ERD and DDL. All 10 tables must be created with proper foreign keys, indexes, constraints, and Row-Level Security (RLS) policies.

## Files to create

### `infra/supabase/migrations/001_projects.sql`
- Enable pgvector extension: `CREATE EXTENSION IF NOT EXISTS vector;`
- Create `projects` table: id (UUID PK, gen_random_uuid()), name (TEXT NOT NULL), repo_url (TEXT), repo_path (TEXT), settings (JSONB NOT NULL DEFAULT '{}'), created_at (TIMESTAMPTZ DEFAULT now()), updated_at (TIMESTAMPTZ DEFAULT now())
- Create `updated_at` trigger function (reusable): `CREATE OR REPLACE FUNCTION update_updated_at() RETURNS TRIGGER AS $$ BEGIN NEW.updated_at = now(); RETURN NEW; END; $$ LANGUAGE plpgsql;`
- Attach trigger to projects table.
- Enable RLS: `ALTER TABLE projects ENABLE ROW LEVEL SECURITY;`
- RLS policy: users can only access rows where `id = current_setting('app.current_project_id')::uuid` or via a broader auth claim. For MVP, create a permissive policy that checks `project_id` via a JWT claim or session variable.

### `infra/supabase/migrations/002_tasks.sql`
- Create `tasks` table: id (UUID PK), project_id (UUID FK -> projects ON DELETE CASCADE), prompt (TEXT NOT NULL), status (TEXT NOT NULL DEFAULT 'pending' CHECK IN ('pending','planning','executing','reviewing','completed','failed')), metadata (JSONB DEFAULT '{}'), created_at, updated_at
- Create `task_steps` table: id (UUID PK), task_id (UUID FK -> tasks ON DELETE CASCADE), ordinal (INT NOT NULL), title (TEXT NOT NULL), description (TEXT NOT NULL), status (TEXT DEFAULT 'pending' CHECK IN ('pending','in_progress','completed','failed','skipped')), agent_type (TEXT NOT NULL CHECK IN ('planner','codegen','executor','context')), input_data (JSONB), output_data (JSONB), started_at (TIMESTAMPTZ), completed_at (TIMESTAMPTZ)
- Unique constraint: (task_id, ordinal)
- updated_at trigger on tasks
- RLS on both tables scoped via project_id (tasks.project_id directly; task_steps via JOIN to tasks)

### `infra/supabase/migrations/003_agent_runs.sql`
- Create `agent_runs` table: id (UUID PK), task_id (UUID FK -> tasks), step_id (UUID FK -> task_steps), agent_type (TEXT NOT NULL), model (TEXT NOT NULL), status (TEXT DEFAULT 'running' CHECK IN ('running','completed','failed','timeout')), input_state (JSONB), output_state (JSONB), tokens_in (INT DEFAULT 0), tokens_out (INT DEFAULT 0), latency_ms (INT DEFAULT 0), retry_count (INT DEFAULT 0), created_at
- Index on (task_id, created_at)
- RLS via project_id through tasks join
- Create `conversations` table: id (UUID PK), task_id (UUID FK -> tasks), role (TEXT CHECK IN ('user','assistant','system','tool')), content (TEXT NOT NULL), metadata (JSONB DEFAULT '{}'), created_at
- RLS on conversations via tasks join

### `infra/supabase/migrations/004_artifacts.sql`
- Create `code_artifacts` table: id (UUID PK), run_id (UUID FK -> agent_runs), task_id (UUID FK -> tasks), file_path (TEXT NOT NULL), content (TEXT NOT NULL), diff (TEXT), language (TEXT NOT NULL), version (INT NOT NULL DEFAULT 1), created_at
- Index on (task_id, file_path)
- Create `execution_results` table: id (UUID PK), run_id (UUID FK -> agent_runs), task_id (UUID FK -> tasks), command (TEXT NOT NULL), stdout (TEXT DEFAULT ''), stderr (TEXT DEFAULT ''), exit_code (INT NOT NULL), duration_ms (INT DEFAULT 0), sandbox_id (TEXT), created_at
- RLS on both via task_id -> project_id

### `infra/supabase/migrations/005_context.sql`
- Create `context_chunks` table: id (UUID PK), project_id (UUID FK -> projects ON DELETE CASCADE), file_path (TEXT NOT NULL), chunk_content (TEXT NOT NULL), embedding (vector(1536)), metadata (JSONB DEFAULT '{}'), indexed_at (TIMESTAMPTZ DEFAULT now())
- IVFFlat index: `CREATE INDEX ON context_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);`
- Index on (project_id, file_path)
- RLS scoped to project_id

### `infra/supabase/migrations/006_metrics.sql`
- Create `agent_metrics` table: id (UUID PK), run_id (UUID FK -> agent_runs), agent_type (TEXT NOT NULL), metric_name (TEXT NOT NULL), metric_value (FLOAT NOT NULL), labels (JSONB DEFAULT '{}'), recorded_at (TIMESTAMPTZ DEFAULT now())
- Create `workflow_checkpoints` table: id (UUID PK), task_id (UUID FK -> tasks ON DELETE CASCADE), thread_id (TEXT NOT NULL), node_name (TEXT NOT NULL), state_snapshot (JSONB NOT NULL), step_number (INT NOT NULL), created_at
- Index on workflow_checkpoints (task_id, thread_id, step_number)
- RLS on both via task_id -> project_id

### `infra/supabase/seed.sql`
- Insert a sample project: name "Demo Project", repo_url null, repo_path "/tmp/demo"
- Insert a sample task under that project: prompt "Build a hello world endpoint", status "pending"
- Insert 2-3 sample task_steps for that task

## Constraints
- Use `gen_random_uuid()` for all PKs.
- All timestamps should be `TIMESTAMPTZ NOT NULL DEFAULT now()`.
- All FK constraints must use `ON DELETE CASCADE`.
- Every table must have RLS enabled and at least one policy.
- Total SQL should be ~400 lines across all files.
```

</details>

---

### M05: Docker Compose & Makefile

| Field | Detail |
|-------|--------|
| **Files** | `docker-compose.yml`, `Makefile`, `.env.example`, `infra/docker/nginx.conf` |
| **Dependencies** | M03, M04 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- `make dev` boots all services; `docker ps` shows all containers healthy
- `curl localhost:3000/health` returns 200
- `.env.example` documents every required env var

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the Docker Compose configuration, Makefile, environment template, and nginx reverse proxy config for the Agentic Developer Environment.

## Context
Read `CLAUDE.md` for the repo map and key commands. Read `docs/architecture.md` Section 1 for the component list and Section 7 for the sandbox Docker design.

## Files to create

### `docker-compose.yml`
Define these services:

1. **supabase-db**: image `supabase/postgres:15`, port 5432, volume for data persistence, healthcheck via pg_isready
2. **redis**: image `redis:7-alpine`, port 6379, healthcheck via redis-cli ping
3. **gateway**: build from `services/gateway/Dockerfile`, port 3000, depends_on supabase-db + redis, env vars for SUPABASE_URL, REDIS_URL, ORCHESTRATOR_GRPC_URL
4. **orchestrator**: build from `services/orchestrator/Dockerfile`, port 50051 (gRPC), depends_on supabase-db + redis, env vars for SUPABASE_URL, REDIS_URL, SANDBOX_GRPC_URL, CONTEXT_GRPC_URL, OPENAI_API_KEY, ANTHROPIC_API_KEY
5. **sandbox**: build from `services/sandbox/Dockerfile`, port 50052 (gRPC), volumes: mount /var/run/docker.sock (for container management), env vars for DOCKER_SOCKET
6. **context**: build from `services/context/Dockerfile`, port 50053 (gRPC), depends_on supabase-db, env vars for SUPABASE_URL, OPENAI_API_KEY
7. **nginx**: image `nginx:alpine`, port 80, volumes: mount `infra/docker/nginx.conf`, depends_on gateway

Networks: `ade-network` (bridge)
Volumes: `supabase-data`, `redis-data`

All services should have restart: unless-stopped and appropriate healthchecks.

### `.env.example`
Document every environment variable with comments:
- SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_KEY
- REDIS_URL (default: redis://redis:6379)
- OPENAI_API_KEY, ANTHROPIC_API_KEY
- ORCHESTRATOR_GRPC_URL (default: orchestrator:50051)
- SANDBOX_GRPC_URL (default: sandbox:50052)
- CONTEXT_GRPC_URL (default: context:50053)
- GATEWAY_PORT (default: 3000)
- LOG_LEVEL (default: info)
- NODE_ENV (default: development)

### `Makefile`
Targets:
- `dev`: docker compose up --build
- `build`: docker compose build
- `test`: run tests across all services (pytest for Python, vitest for TS)
- `lint`: run linters (ruff for Python, eslint for TS)
- `migrate`: apply Supabase migrations using psql or supabase CLI
- `proto`: generate gRPC stubs from `packages/proto/*.proto`
- `clean`: docker compose down -v --remove-orphans
- `logs`: docker compose logs -f
- `restart`: docker compose restart

Include a `.PHONY` declaration for all targets.

### `infra/docker/nginx.conf`
- Reverse proxy: route `/api/*` and `/ws/*` to gateway:3000
- Route `/` to ui:5173 (for dev, or static files in prod)
- WebSocket upgrade support for `/ws/*` paths
- Basic security headers (X-Frame-Options, X-Content-Type-Options)
- Gzip compression

## Constraints
- Use Docker Compose v3.8+ syntax.
- All services must use the `ade-network` Docker network.
- Healthchecks must have reasonable intervals (10s) and retries (3).
- Total code ~300 lines across all files.
```

</details>

---

## Phase 1 — Gateway Service

### M06: Gateway Server Bootstrap

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/index.ts`, `services/gateway/package.json`, `services/gateway/tsconfig.json`, `services/gateway/Dockerfile` |
| **Dependencies** | M02, M05 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- Server starts on port 3000
- `GET /health` returns `{ status: "ok" }`
- Graceful shutdown on SIGTERM

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the Gateway API server bootstrap for the ADE system. This is a TypeScript Fastify server that serves as the public API surface.

## Context
Read `CLAUDE.md` and `docs/architecture.md` Section 1 + Section 4a. The Gateway is a TypeScript Fastify app that exposes REST endpoints and WebSocket connections, bridging clients to the Python orchestrator via gRPC.

## Files to create

### `services/gateway/package.json`
- Name: `@ade/gateway`
- Dependencies: `fastify` (latest), `@fastify/cors`, `@fastify/helmet`, `@fastify/websocket`, `@fastify/rate-limit`, `ioredis` (latest), `@supabase/supabase-js` (latest), `@grpc/grpc-js`, `@grpc/proto-loader`, `pino` (logger, built into Fastify), `zod`
- DevDependencies: `typescript`, `tsx`, `@types/node`, `vitest`
- Scripts: `dev: tsx watch src/index.ts`, `build: tsc`, `start: node dist/index.js`, `test: vitest`, `typecheck: tsc --noEmit`

### `services/gateway/tsconfig.json`
- Target: ES2022, module: ESNext, moduleResolution: bundler
- Strict: true, outDir: dist, rootDir: src
- Include: `src/**/*.ts`

### `services/gateway/src/index.ts`
Implement the Fastify server:
1. Load environment variables: PORT (default 3000), REDIS_URL, SUPABASE_URL, SUPABASE_SERVICE_KEY, ORCHESTRATOR_GRPC_URL, LOG_LEVEL
2. Create Fastify instance with pino logger
3. Register plugins: @fastify/cors (allow all origins in dev), @fastify/helmet, @fastify/websocket
4. Create and export Redis client (ioredis) as a shared instance — attach to `fastify.decorate('redis', redisClient)`
5. Create and export Supabase client — attach to `fastify.decorate('supabase', supabaseClient)`
6. Register a health endpoint: `GET /health` returns `{ status: "ok", timestamp: new Date().toISOString() }`
7. Placeholder plugin registration points (comments) for: auth middleware, rate limit middleware, route plugins (projects, tasks, artifacts, metrics), WebSocket handler, gRPC clients
8. Graceful shutdown: on SIGTERM/SIGINT, close Redis connection, close Fastify server
9. Start listening on PORT

### `services/gateway/Dockerfile`
- Multi-stage build: builder stage (node:22-slim, npm ci, tsc) + runtime stage (node:22-slim, copy dist + node_modules, USER node, CMD ["node", "dist/index.js"])
- Expose port 3000

## Constraints
- Use Fastify's plugin system for all registrations (no global state).
- Use `fastify.decorate()` to share Redis and Supabase clients across plugins.
- All config must come from environment variables, no hardcoded values.
- Do NOT implement routes, middleware, or gRPC clients yet — just leave plugin registration points with TODO comments.
- Total code ~200 lines.
```

</details>

---

### M07: Auth Middleware

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/middleware/auth.ts` |
| **Dependencies** | M04, M06 |
| **Est. lines** | ~150 |

**Acceptance criteria:**
- Valid Supabase JWT passes through; `request.user` contains project_id
- Expired/missing token returns 401
- `/health` endpoint is excluded from auth

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the authentication middleware for the ADE Gateway API.

## Context
Read `CLAUDE.md` (architectural constraint #8: RLS everywhere). Read `docs/architecture.md` Section 6 for Redis session strategy. The Gateway uses Fastify. The Supabase client is available via `fastify.supabase` (decorated in M06). Redis is available via `fastify.redis`.

## Files to create

### `services/gateway/src/middleware/auth.ts`
Export a Fastify plugin that registers a `preHandler` hook on all routes except `/health`.

Implementation:
1. Extract the `Authorization` header (Bearer token) or `x-api-key` header.
2. If Bearer token: verify it as a Supabase JWT using `supabase.auth.getUser(token)`. Extract `user.id` and any `project_id` from the JWT metadata/claims.
3. If x-api-key: look up the API key in Redis at `session:{key}` to get the associated project_id. If not in Redis, query the `projects` table for a matching key in the `settings` JSONB column.
4. If neither header is present or verification fails, return 401 `{ error: "Unauthorized", message: "Missing or invalid authentication" }`.
5. Attach a `user` object to the Fastify request via `request.user = { id, project_id }`. Use Fastify's `decorateRequest` to type this properly.
6. Define a TypeScript interface `AuthUser { id: string; project_id: string }` and augment the Fastify request type.

Also export:
- A `requireProject` preHandler that checks `request.user.project_id` exists (some endpoints require it, others don't).

## Constraints
- Use Fastify's plugin system (`fp` from `fastify-plugin` for encapsulation).
- Skip auth for routes matching `/health`.
- Never log tokens or API keys.
- Handle edge cases: malformed JWT, expired token, Supabase service unavailable.
- Total code ~150 lines.
```

</details>

---

### M08: Rate Limit & Validation Middleware

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/middleware/rateLimit.ts`, `services/gateway/src/middleware/validation.ts` |
| **Dependencies** | M02, M06 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- 100+ requests in 1 minute from the same project returns 429
- Malformed request body returns 400 with Zod error details

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement rate limiting and request validation middleware for the ADE Gateway API.

## Context
Read `docs/architecture.md` Section 6 for the Redis rate limiting strategy. Redis keys use the pattern `ratelimit:{project_id}:{minute}`. The shared TypeScript types from `@ade/shared-types` (M02) provide Zod schemas for request validation.

## Files to create

### `services/gateway/src/middleware/rateLimit.ts`
Export a Fastify plugin that implements sliding-window rate limiting per project:
1. On each request (after auth middleware), extract `project_id` from `request.user`.
2. Compute the Redis key: `ratelimit:{project_id}:{currentMinute}` where currentMinute is `Math.floor(Date.now() / 60000)`.
3. Use `INCR` + `EXPIRE 60` on that key.
4. If count exceeds the limit (configurable, default 100/min), return 429 `{ error: "Rate limit exceeded", retry_after: secondsUntilNextMinute }`.
5. Add `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` headers to all responses.
6. Skip rate limiting for `/health`.

### `services/gateway/src/middleware/validation.ts`
Export a Fastify plugin that provides a `validateBody` utility:
1. A factory function `createValidator(zodSchema)` that returns a Fastify `preHandler` hook.
2. The hook calls `zodSchema.safeParse(request.body)`.
3. On failure, returns 400 with `{ error: "Validation error", details: zodError.issues }`.
4. On success, replaces `request.body` with the parsed (typed) value.

Also export pre-built validators for the known request types:
- `validateCreateTask`: validates against `CreateTaskRequest` schema (project_id: uuid, prompt: non-empty string)
- `validateCreateProject`: validates against `CreateProjectRequest` schema (name: non-empty, repo_url?: url, repo_path?: string)

## Constraints
- Rate limiter must use Redis (via `fastify.redis`) for distributed counting.
- Rate limit config (requests per minute) should come from env var `RATE_LIMIT_PER_MINUTE`.
- Validation errors must include field-level detail from Zod.
- Total code ~200 lines combined.
```

</details>

---

### M09: Project Routes

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/routes/projects.ts` |
| **Dependencies** | M04, M06, M07, M08 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- Full CRUD lifecycle: create, read, update, delete
- RLS enforces project isolation

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the project CRUD routes for the ADE Gateway API.

## Context
Read `docs/architecture.md` Section 4a for the endpoint spec. The `projects` table schema is in Section 3. Supabase client is available via `fastify.supabase`. Auth middleware from M07 is registered globally. Validation middleware from M08 provides `validateCreateProject`.

## Files to create

### `services/gateway/src/routes/projects.ts`
Export a Fastify plugin that registers these routes under `/api/v1/projects`:

1. **`POST /api/v1/projects`** — Create a new project
   - Validate body with `validateCreateProject` (name required, repo_url optional, repo_path optional, settings optional)
   - Insert into `projects` table via Supabase client
   - Return 201 with the created project object

2. **`GET /api/v1/projects/:id`** — Get project by ID
   - Validate `:id` is a UUID
   - Select from `projects` where id = :id
   - Return 200 with project, or 404 if not found

3. **`PATCH /api/v1/projects/:id`** — Update project settings
   - Validate `:id` is UUID, body contains optional fields: name, repo_url, repo_path, settings
   - Update the `projects` row
   - Return 200 with updated project, or 404

4. **`DELETE /api/v1/projects/:id`** — Delete project (cascades to all related data)
   - Delete from `projects` where id = :id
   - Return 204 on success, 404 if not found

5. **`GET /api/v1/projects`** — List all projects (for the authenticated user)
   - Optional query params: `limit` (default 20), `offset` (default 0)
   - Return 200 with `{ projects: Project[], total: number }`

## Constraints
- All Supabase queries should use the service-role client but set `project_id` context for RLS.
- Use the Project type from `@ade/shared-types`.
- Return appropriate error responses: 400 (bad request), 404 (not found), 500 (server error).
- Include `Content-Type: application/json` on all responses.
- Total code ~200 lines.
```

</details>

---

### M10: Task Routes

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/routes/tasks.ts` |
| **Dependencies** | M04, M06, M07, M08, M13 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- POST returns 202 with task_id and ws_url
- GET returns task with current status
- Step approval updates step status

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the task submission and management routes for the ADE Gateway API.

## Context
Read `docs/architecture.md` Section 4a for the endpoint spec and example request/response. The Gateway calls the Orchestrator via gRPC (M13 provides the client). When a task is submitted, the Gateway inserts a `tasks` row, then calls `OrchestratorService.RunWorkflow` to start the agent pipeline.

## Files to create

### `services/gateway/src/routes/tasks.ts`
Export a Fastify plugin that registers these routes under `/api/v1/tasks`:

1. **`POST /api/v1/tasks`** — Submit a new developer task
   - Validate body: `{ project_id: uuid, prompt: string }` using `validateCreateTask`
   - Insert into `tasks` table with status "pending"
   - Call `orchestratorClient.runWorkflow({ task_id, project_id, prompt })` (non-blocking — don't await the stream here, the WebSocket handles events)
   - Return 202 `{ task_id, status: "pending", ws_url: "/ws/tasks/{task_id}" }`

2. **`GET /api/v1/tasks/:id`** — Get task details
   - Select from `tasks` where id = :id
   - Return 200 with full task object, or 404

3. **`GET /api/v1/tasks`** — List tasks for a project
   - Required query param: `project_id` (UUID)
   - Optional: `status` filter, `limit` (default 20), `offset` (default 0)
   - Order by created_at DESC
   - Return 200 with `{ tasks: Task[], total: number }`

4. **`GET /api/v1/tasks/:id/steps`** — List planner-generated steps
   - Select from `task_steps` where task_id = :id, order by ordinal ASC
   - Return 200 with `{ steps: TaskStep[] }`

5. **`POST /api/v1/tasks/:id/steps/:stepId/approve`** — Human-in-the-loop approval
   - Validate step exists and has status "pending" or "in_progress"
   - Accept body `{ approved: boolean, feedback?: string }`
   - Update step status to "completed" (if approved) or "skipped" (if rejected)
   - Publish a `step.approved` or `step.rejected` event to Redis pub/sub for the orchestrator to pick up
   - Return 200 with updated step

## Constraints
- The gRPC call to RunWorkflow should be fire-and-forget from the route handler's perspective. The stream is consumed by the event publisher (M26), not by this route.
- If the orchestrator is unavailable, still insert the task row but return status "pending" with a warning field.
- Use types from `@ade/shared-types`.
- Total code ~300 lines.
```

</details>

---

### M11: Artifact & Results Routes

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/routes/artifacts.ts` |
| **Dependencies** | M04, M06, M07 |
| **Est. lines** | ~150 |

**Acceptance criteria:**
- Returns artifacts with diff, language, version
- Returns execution results with stdout/stderr/exit_code
- Pagination works

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the read-only routes for code artifacts and execution results in the ADE Gateway API.

## Context
Read `docs/architecture.md` Section 4a. These are read-only endpoints that retrieve data written by the orchestrator's agents. The `code_artifacts` and `execution_results` tables are defined in Section 3.

## Files to create

### `services/gateway/src/routes/artifacts.ts`
Export a Fastify plugin that registers these routes:

1. **`GET /api/v1/tasks/:id/artifacts`** — Get generated code artifacts for a task
   - Select from `code_artifacts` where task_id = :id
   - Optional query params: `file_path` (filter), `version` (filter), `limit`, `offset`
   - Order by created_at DESC
   - Return 200 with `{ artifacts: CodeArtifact[], total: number }`

2. **`GET /api/v1/tasks/:id/artifacts/:artifactId`** — Get a single artifact
   - Select from `code_artifacts` where id = :artifactId and task_id = :id
   - Return 200 with full artifact (including content and diff), or 404

3. **`GET /api/v1/tasks/:id/results`** — Get sandbox execution results
   - Select from `execution_results` where task_id = :id
   - Optional query params: `step_id` (filter by originating step), `limit`, `offset`
   - Order by created_at DESC
   - Return 200 with `{ results: ExecutionResult[], total: number }`

4. **`GET /api/v1/tasks/:id/results/:resultId`** — Get a single execution result
   - Return 200 with full result (stdout, stderr, exit_code, duration_ms), or 404

## Constraints
- These are read-only endpoints. No INSERT/UPDATE/DELETE operations.
- Use types from `@ade/shared-types`.
- Validate that :id and :artifactId/:resultId are UUIDs.
- Total code ~150 lines.
```

</details>

---

### M12: WebSocket Task Stream

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/ws/taskStream.ts` |
| **Dependencies** | M06, M07 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- Client connects and receives `workflow.started` event
- Disconnection unsubscribes from Redis cleanly
- Invalid task_id returns a close frame with reason

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the WebSocket handler for real-time task event streaming in the ADE Gateway.

## Context
Read `docs/architecture.md` Section 4c for the WebSocket event schema, and Section 6 for the Redis pub/sub event bus design. The orchestrator publishes WorkflowEvent JSON to Redis channel `workflow:events:{task_id}`. The Gateway subscribes on WebSocket connection and forwards events to the client.

## Files to create

### `services/gateway/src/ws/taskStream.ts`
Export a Fastify plugin that registers the WebSocket handler:

**Route:** `GET /ws/tasks/:id` (WebSocket upgrade)

**On connection:**
1. Extract `task_id` from URL params. Validate it's a UUID.
2. Authenticate: extract token from `?token=` query parameter. Verify via the same auth logic as M07. If invalid, send close frame with code 4001 and reason "Unauthorized", then close.
3. Verify the task exists in the `tasks` table. If not, close with 4004 "Task not found".
4. Create a dedicated Redis subscriber connection (ioredis `duplicate()` for pub/sub).
5. Subscribe to Redis channel `workflow:events:{task_id}`.
6. On Redis message: parse the JSON `WorkflowEvent`, add a `received_at` timestamp, and send it to the WebSocket client as JSON text.
7. Send an initial synthetic event: `{ event_type: "connection.established", task_id, timestamp: Date.now() }`.

**On client message:**
- Accept `{ type: "ping" }` messages and respond with `{ type: "pong" }` for keepalive.

**On close/error:**
1. Unsubscribe from the Redis channel.
2. Close the duplicate Redis connection.
3. Log the disconnection.

**Heartbeat:**
- Send a `{ event_type: "heartbeat" }` message every 30 seconds to prevent timeouts.

## Constraints
- Use `@fastify/websocket` for WebSocket support.
- Each WebSocket connection gets its own Redis subscriber (ioredis requires dedicated connections for pub/sub).
- Handle Redis reconnection gracefully — if Redis drops, send error event to client and attempt reconnect.
- Log connection/disconnection with task_id for observability.
- Total code ~200 lines.
```

</details>

---

### M13: gRPC Client Layer

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/grpc/clients.ts` |
| **Dependencies** | M03 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- `orchestratorClient.runWorkflow()` sends a valid gRPC request
- Connection failure returns structured error
- Deadline propagation works

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the gRPC client layer for the ADE Gateway, providing typed wrappers to call the Orchestrator, Sandbox, and Context services.

## Context
Read `docs/architecture.md` Section 4b for the gRPC service definitions. The proto files are in `packages/proto/`. Generated TypeScript stubs should be at `services/gateway/src/generated/` (from M03). The Gateway uses these clients to call internal Python services.

## Files to create

### `services/gateway/src/grpc/clients.ts`
Export a Fastify plugin that decorates the app with gRPC clients:

1. **OrchestratorClient** — wraps `OrchestratorService`:
   - `runWorkflow(request: WorkflowRequest): AsyncIterable<WorkflowEvent>` — calls `RunWorkflow` server-streaming RPC. Returns an async iterator of events.
   - `getWorkflowStatus(taskId: string): Promise<WorkflowStatus>` — calls `GetWorkflowStatus`.
   - `cancelWorkflow(taskId: string): Promise<Ack>` — calls `CancelWorkflow`.

2. **SandboxClient** — wraps `SandboxService`:
   - `createSandbox(config: SandboxConfig): Promise<SandboxInfo>`
   - `execute(request: ExecutionRequest): Promise<ExecutionResult>`
   - `destroySandbox(sandboxId: string): Promise<Ack>`

3. **ContextClient** — wraps `ContextService`:
   - `indexRepository(projectId: string, repoPath: string): Promise<IndexResult>`
   - `retrieveContext(query: ContextQuery): Promise<ContextChunks>`
   - `watchChanges(request: WatchRequest): AsyncIterable<ChangeEvent>`

**Shared behavior for all clients:**
- Load proto definitions using `@grpc/proto-loader` with `keepCase: true, longs: String, enums: String, defaults: true, oneofs: true`.
- Create channels to service addresses from env vars: `ORCHESTRATOR_GRPC_URL`, `SANDBOX_GRPC_URL`, `CONTEXT_GRPC_URL`.
- Wrap every call with: deadline propagation (default 30s timeout), retry logic (max 2 retries on UNAVAILABLE), and error mapping (gRPC status codes -> HTTP-friendly error objects).
- Decorate Fastify: `fastify.decorate('orchestratorClient', ...)`, etc.

## Constraints
- Use `@grpc/grpc-js` (not the deprecated `grpc` package).
- Use `grpc.credentials.createInsecure()` for dev (services are on the same Docker network).
- Handle connection errors gracefully — if a service is unavailable, return a typed error, don't crash.
- Total code ~200 lines.
```

</details>

---

### M14: Metrics Route

| Field | Detail |
|-------|--------|
| **Files** | `services/gateway/src/routes/metrics.ts` |
| **Dependencies** | M04, M06, M07 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- Returns aggregated metrics with filtering
- Includes token counts, latency percentiles, costs

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the metrics aggregation endpoint for the ADE Gateway API.

## Context
Read `docs/architecture.md` Section 3 for the `agent_metrics` and `agent_runs` tables. This endpoint aggregates agent performance data for the dashboard.

## Files to create

### `services/gateway/src/routes/metrics.ts`
Export a Fastify plugin that registers:

**`GET /api/v1/metrics`** — Aggregated agent metrics
- Query params: `project_id` (required UUID), `agent_type` (optional filter), `from` (ISO date), `to` (ISO date), `granularity` ("hour" | "day", default "day")

Response shape:
```json
{
  "summary": {
    "total_tasks": 42,
    "completed_tasks": 38,
    "failed_tasks": 4,
    "total_tokens_in": 150000,
    "total_tokens_out": 80000,
    "estimated_cost_usd": 12.50,
    "avg_latency_ms": 2300,
    "p95_latency_ms": 5400
  },
  "by_agent": [
    {
      "agent_type": "planner",
      "total_runs": 42,
      "success_rate": 0.95,
      "avg_latency_ms": 1200,
      "total_tokens": 30000
    }
  ],
  "timeline": [
    { "date": "2026-04-25", "tasks": 5, "tokens": 12000, "cost_usd": 1.20 }
  ]
}
```

Implementation:
1. Query `agent_runs` for summary stats: COUNT, SUM(tokens_in), SUM(tokens_out), AVG(latency_ms), percentile_cont(0.95) for latency.
2. Query `agent_runs` grouped by agent_type for per-agent stats.
3. Query `agent_runs` grouped by date (or hour) for timeline data.
4. Compute estimated cost using model pricing constants (GPT-4o: $2.50/$10 per 1M tokens in/out, Claude Sonnet: $3/$15, etc.).
5. Return the aggregated result.

## Constraints
- Use Supabase's `.rpc()` for complex aggregations, or build the query with the query builder.
- Cache results in Redis for 60 seconds at key `metrics:{project_id}:{hash_of_params}` to avoid expensive aggregation on every request.
- Total code ~200 lines.
```

</details>

---

## Phase 2 — Orchestrator Service

### M15: Orchestrator Server Bootstrap

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/server.py`, `config.py`, `pyproject.toml`, `Dockerfile` |
| **Dependencies** | M01, M03, M04, M05 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- gRPC server starts on port 50051
- `RunWorkflow` RPC accepts a request and returns an event stream
- Config loaded from environment

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the Orchestrator service bootstrap — a Python gRPC server that hosts the LangGraph-based agent orchestration engine.

## Context
Read `CLAUDE.md` and `docs/architecture.md` Section 5. The orchestrator is a Python gRPC server implementing `OrchestratorService` from `packages/proto/orchestrator.proto`. It uses LangGraph for the agent graph and Supabase for persistence.

## Files to create

### `services/orchestrator/pyproject.toml`
- Name: `ade-orchestrator`
- Python: >=3.12
- Dependencies: `grpcio`, `grpcio-tools`, `langgraph>=0.2`, `langchain-core`, `langchain-openai`, `langchain-anthropic`, `supabase` (Python client), `redis`, `pydantic>=2.6`, `ade-types` (path dependency to `../../packages/shared-types/python`)
- Dev dependencies: `pytest`, `pytest-asyncio`, `ruff`
- Scripts: `serve: python -m src.server`

### `services/orchestrator/src/config.py`
Load from environment using pydantic-settings or plain os.environ:
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`
- `REDIS_URL` (default: redis://localhost:6379)
- `GRPC_PORT` (default: 50051)
- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- `SUPERVISOR_MODEL` (default: "claude-sonnet-4-20250514")
- `WORKER_MODEL` (default: "claude-sonnet-4-20250514")
- `SANDBOX_GRPC_URL` (default: localhost:50052)
- `CONTEXT_GRPC_URL` (default: localhost:50053)
- `LOG_LEVEL` (default: "info")

Export as a singleton `Settings` instance.

### `services/orchestrator/src/server.py`
Implement the gRPC server:
1. Initialize: load config, create Supabase client, create Redis client, import the supervisor graph (from M17, placeholder for now).
2. Implement `OrchestratorService`:
   - `RunWorkflow(request, context)`: Create a new workflow, run the LangGraph supervisor graph in a background asyncio task, yield `WorkflowEvent` messages as the graph executes. Also publish each event to Redis channel `workflow:events:{task_id}`.
   - `GetWorkflowStatus(request, context)`: Query the latest `workflow_checkpoints` entry for the task to determine current status.
   - `CancelWorkflow(request, context)`: Set a cancellation flag in Redis at `workflow:cancel:{task_id}`. The graph checks this flag at each node.
3. Start the gRPC server on the configured port with asyncio.
4. Graceful shutdown on SIGTERM.

### `services/orchestrator/Dockerfile`
- Base: python:3.12-slim
- Copy pyproject.toml, install dependencies
- Copy src/
- USER nobody
- CMD ["python", "-m", "src.server"]
- Expose 50051

## Constraints
- Use `grpc.aio` for async gRPC server.
- The supervisor graph import should be behind a lazy import or factory function so the server can start even if the graph module isn't implemented yet (for incremental development).
- Publish events to Redis AND yield them on the gRPC stream (dual delivery).
- Total code ~300 lines.
```

</details>

---

### M16: Workflow State & Checkpointer

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/state/workflow.py`, `services/orchestrator/src/state/checkpointer.py` |
| **Dependencies** | M01, M04, M15 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- State persists after each graph node
- Service restart resumes from last checkpoint
- Can list all checkpoints for a task

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the LangGraph workflow state definition and Supabase checkpoint persistence for the ADE Orchestrator.

## Context
Read `docs/architecture.md` Section 5 for the `WorkflowState` schema and checkpointing design. The `workflow_checkpoints` table is in Section 3. LangGraph uses a `BaseCheckpointSaver` interface to persist state between graph nodes.

## Files to create

### `services/orchestrator/src/state/workflow.py`
Define the `WorkflowState` as a LangGraph-compatible `TypedDict` with annotation-based reducers:

```python
from typing import TypedDict, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage
from ade_types import TaskStep, CodeArtifact, ExecutionResult

class WorkflowState(TypedDict):
    task_id: str
    project_id: str
    prompt: str
    steps: Annotated[list[TaskStep], operator.add]  # planner appends
    current_step_index: int
    context_chunks: Annotated[list[str], operator.add]  # context agent appends
    artifacts: Annotated[list[CodeArtifact], operator.add]  # codegen appends
    execution_results: Annotated[list[ExecutionResult], operator.add]
    messages: Annotated[list[BaseMessage], add_messages]
    next_agent: str  # supervisor routing decision
    retry_count: int
    requires_approval: bool
    error: str | None
```

Also define helper functions:
- `create_initial_state(task_id, project_id, prompt) -> WorkflowState` — factory for new workflow
- `get_current_step(state) -> TaskStep | None` — returns step at current_step_index
- `advance_step(state) -> WorkflowState` — increments current_step_index
- `set_error(state, error_msg) -> WorkflowState` — sets error field

### `services/orchestrator/src/state/checkpointer.py`
Implement `SupabaseCheckpointer(BaseCheckpointSaver)`:

This is a LangGraph checkpoint saver that uses the `workflow_checkpoints` table in Supabase.

Methods to implement:
1. `put(config, checkpoint, metadata)` — INSERT a new row into `workflow_checkpoints` with: task_id (from config), thread_id (from config), node_name (from metadata), state_snapshot (JSON serialized checkpoint), step_number (auto-incrementing per thread)
2. `get_tuple(config)` — SELECT the latest checkpoint for a given thread_id, return as a `CheckpointTuple`
3. `list(config, *, before, limit)` — SELECT checkpoints for a thread_id, ordered by step_number DESC, with optional filtering/pagination
4. `put_writes(config, writes, task_id)` — store pending writes for a checkpoint (INSERT into a jsonb column or separate table)

Constructor takes a Supabase client instance.

Use the `supabase-py` client for all database operations. Serialize/deserialize checkpoint state using `json.dumps`/`json.loads` with a custom encoder for non-JSON-native types (datetime, UUID, Pydantic models).

## Constraints
- Follow the LangGraph `BaseCheckpointSaver` interface exactly — check LangGraph docs/source for the current method signatures.
- Use `Annotated` reducers on WorkflowState so LangGraph handles state merging correctly (e.g., `operator.add` for list fields means agents can append without overwriting).
- The `messages` field must use `add_messages` from langgraph to handle LangChain message deduplication.
- JSON serialization must handle UUID, datetime, and Pydantic model instances.
- Total code ~350 lines.
```

</details>

---

### M17: Supervisor Graph

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/graphs/supervisor.py` |
| **Dependencies** | M01, M16, M18-M21 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- Routes to planner on first call when no steps exist
- Routes to codegen after plan exists
- Routes to END after all steps complete

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the top-level LangGraph supervisor graph for the ADE Orchestrator.

## Context
Read `docs/architecture.md` Section 5 for the full supervisor graph design and Mermaid diagram. Read `CLAUDE.md` constraint #1: "Supervisor routes, never executes." The supervisor is a LangGraph StateGraph that uses an LLM to decide which agent subgraph to invoke next.

## Files to create

### `services/orchestrator/src/graphs/supervisor.py`
Build the supervisor `StateGraph` using LangGraph:

**Nodes:**
1. `supervisor_node` — The routing brain. Makes an LLM call (strong model from config) with the current WorkflowState summary. The LLM returns a structured decision: `{ next: "planner" | "context" | "codegen" | "executor" | "human_review" | "done", reasoning: str }`. Store the `next` value in `state["next_agent"]`.

2. `planner_node` — Invokes the planner subgraph (M18). Placeholder: import from `graphs.planning`.
3. `context_node` — Invokes the context agent (M19). Placeholder: import from `agents.context`.
4. `codegen_node` — Invokes the codegen subgraph (M20). Placeholder: import from `graphs.codegen`.
5. `executor_node` — Invokes the execution subgraph (M21). Placeholder: import from `graphs.execution`.
6. `human_review_node` — Sets `state["requires_approval"] = True` and pauses execution. When approval arrives (via Redis pub/sub), resumes.

**Edges:**
- START -> supervisor_node
- supervisor_node -> conditional edge based on `state["next_agent"]`:
  - "planner" -> planner_node
  - "context" -> context_node
  - "codegen" -> codegen_node
  - "executor" -> executor_node
  - "human_review" -> human_review_node
  - "done" -> END
- planner_node -> supervisor_node
- context_node -> supervisor_node
- codegen_node -> supervisor_node (quality gate is internal to codegen subgraph)
- executor_node -> supervisor_node
- human_review_node -> supervisor_node

**Supervisor LLM Prompt:**
The supervisor node should format a system message explaining its role and the available agents, then include the current state summary (task prompt, completed steps, pending steps, recent artifacts, recent errors). The LLM should respond with a JSON object selecting the next agent.

**Safety guards:**
- Max iterations: 20 (prevent infinite loops). After 20 supervisor calls, force route to END with error.
- Check for cancellation flag in Redis (`workflow:cancel:{task_id}`) at each supervisor invocation.
- If `state["error"]` is set and retry_count > 3, route to END.

**Compile the graph:**
Export a factory function `create_supervisor_graph(checkpointer) -> CompiledGraph` that:
1. Builds the StateGraph with all nodes and edges
2. Compiles it with the SupabaseCheckpointer
3. Returns the compiled graph

## Constraints
- The supervisor node ONLY makes routing decisions — it never calls tools or modifies state beyond setting `next_agent`.
- Use `ChatAnthropic` or `ChatOpenAI` based on the configured SUPERVISOR_MODEL.
- The LLM call should use structured output (tool calling or JSON mode) for reliable parsing.
- Subgraph imports should use lazy imports so the supervisor can be tested independently.
- Total code ~300 lines.
```

</details>

---

### M18: Planner Agent & Subgraph

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/graphs/planning.py`, `services/orchestrator/src/agents/planner.py`, `services/orchestrator/src/prompts/planner.md` |
| **Dependencies** | M01, M16 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- Given "Build JWT auth", returns 3-6 ordered TaskSteps
- Steps have correct agent_type assignments
- Steps are persisted to `task_steps` table

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the Planner agent and its LangGraph subgraph for the ADE Orchestrator. The planner decomposes a natural-language developer prompt into an ordered list of TaskStep objects.

## Context
Read `docs/architecture.md` Section 5 for agent design. Read `CLAUDE.md` constraint #2: the planner has NO tools — it's pure LLM reasoning. The planner receives a prompt and produces structured steps.

## Files to create

### `services/orchestrator/src/prompts/planner.md`
System prompt for the planner agent:
- Role: You are a senior software architect. Given a developer's task description, break it down into a clear, ordered sequence of implementation steps.
- Each step must specify: title (short name), description (detailed instructions), and agent_type ("codegen" for code writing, "executor" for testing, "context" for codebase research).
- Steps should follow a logical order: context research first, then implementation, then testing.
- Aim for 3-8 steps per task. Each step should be completable in a single agent session.
- Output format: JSON array of step objects.

### `services/orchestrator/src/agents/planner.py`
Implement the planner agent:
1. Load the system prompt from `prompts/planner.md`.
2. Create an LLM instance (worker model from config) with structured output binding.
3. Define a Pydantic model for the LLM output: `PlannerOutput(BaseModel)` with `steps: list[PlannedStep]` where `PlannedStep` has `title`, `description`, `agent_type`.
4. The agent function takes `WorkflowState` and returns a state update:
   - Format the user prompt and any existing context_chunks into the LLM message.
   - Call the LLM with structured output to get the plan.
   - Convert `PlannedStep` objects into `TaskStep` objects with ordinals, status "pending", and UUIDs.
   - Persist the steps to the `task_steps` table via Supabase.
   - Return `{ "steps": task_steps }` as the state update.

### `services/orchestrator/src/graphs/planning.py`
Define the planner subgraph:
1. Create a `StateGraph` with WorkflowState.
2. Single node: `plan` that calls the planner agent function.
3. Edge: START -> plan -> END.
4. Export `create_planning_subgraph() -> CompiledGraph`.

This is intentionally simple — the planner is a single-shot LLM call wrapped in a subgraph for consistency with the supervisor's routing pattern.

## Constraints
- The planner has NO tools. It only makes LLM calls.
- Use structured output (LLM tool calling with Pydantic schema) for reliable step extraction.
- Each generated TaskStep must have a UUID id, sequential ordinal starting at 1, and status "pending".
- The Supabase insert should batch-insert all steps in a single call.
- Total code ~300 lines across all 3 files.
```

</details>

---

### M19: Context Agent

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/agents/context.py` |
| **Dependencies** | M01, M03, M16 |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- Retrieves relevant chunks for a given query
- Appends chunks to `WorkflowState.context_chunks`

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the Context agent for the ADE Orchestrator. This agent retrieves relevant codebase context using the Context Service (gRPC) and provides it to other agents.

## Context
Read `docs/architecture.md` Section 5 for agent tool permissions. The Context agent has: read_file (✓), vector_search (✓), no write or execute. It communicates with the Context Service via gRPC (M03 proto: ContextService.RetrieveContext).

## Files to create

### `services/orchestrator/src/agents/context.py`
Implement the Context agent as a LangGraph tool-calling agent:

**Tools:**
1. `search_codebase(query: str, top_k: int = 10) -> list[dict]` — Calls `ContextService.RetrieveContext` via gRPC. Returns a list of `{ file_path, content, score }` objects. Uses the search tool module (M23, provide a placeholder interface for now).

2. `read_file(file_path: str) -> str` — Reads a specific file from the project repo. Uses the file_ops tool module (M22, provide a placeholder interface for now).

**Agent function:** `context_agent(state: WorkflowState) -> dict`
1. Determine what context is needed based on `state["prompt"]` and `state["steps"]` (current step's description).
2. Create an LLM instance (worker model) bound to the two tools above.
3. Run a ReAct loop: the LLM decides whether to search or read files, calls tools, and decides when it has enough context.
4. Collect all retrieved chunks.
5. Return `{ "context_chunks": [chunk_contents] }` to append to state.

**LLM system message:**
- You are a codebase analyst. Your job is to find relevant code context that will help other agents complete their tasks.
- Use search_codebase to find relevant files, then read_file to get full contents of the most relevant ones.
- Focus on: existing patterns, related code, imports, type definitions, and test examples.
- Return when you have sufficient context (typically 3-8 relevant chunks).

## Constraints
- The context agent is READ-ONLY — it cannot write files or execute code.
- Use LangGraph's `create_react_agent` or manual tool-calling loop.
- Limit to 5 tool calls per invocation to control costs.
- gRPC calls should have a 10s timeout.
- Total code ~250 lines.
```

</details>

---

### M20: Codegen Agent & Quality Gate

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/graphs/codegen.py`, `services/orchestrator/src/agents/codegen.py`, `services/orchestrator/src/prompts/codegen.md` |
| **Dependencies** | M01, M16, M22, M23 |
| **Est. lines** | ~400 |

**Acceptance criteria:**
- Generates syntactically valid code
- Quality gate catches syntax errors and retries (up to 3x)
- After 3 failures, reports error to supervisor

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the Codegen agent and its quality-gated subgraph for the ADE Orchestrator.

## Context
Read `docs/architecture.md` Section 5. Read `CLAUDE.md` constraints #2 (codegen: file-write only, no execution) and #4 (quality gates before returning to supervisor, max 3 retries). The codegen subgraph has an internal retry loop: codegen -> quality gate -> pass/fail -> retry or return.

## Files to create

### `services/orchestrator/src/prompts/codegen.md`
System prompt for the codegen agent:
- Role: You are an expert software engineer. Generate or modify code files to implement the given task step.
- You have access to: write_file (create/update files), read_file (read existing files), search_codebase (find relevant code).
- Follow existing code patterns and conventions visible in the context chunks.
- Generate complete, working code — not pseudocode or snippets.
- Include necessary imports, type annotations, and error handling.
- Do NOT include tests (the executor handles that).

### `services/orchestrator/src/agents/codegen.py`
Implement the codegen agent:

**Tools (from M22 and M23):**
- `write_file(file_path: str, content: str) -> str` — writes a file to the project
- `read_file(file_path: str) -> str` — reads a file
- `search_codebase(query: str) -> list[dict]` — semantic search

**Agent function:** `codegen_agent(state: WorkflowState) -> dict`
1. Get the current step from `state["steps"][state["current_step_index"]]`.
2. Build context: include `state["context_chunks"]`, the step description, and the task prompt.
3. Create LLM (worker model) bound to the three tools.
4. Run a ReAct loop where the LLM reads relevant files, then writes new/modified files.
5. Collect all written files as `CodeArtifact` objects.
6. Return `{ "artifacts": [artifacts] }`.

### `services/orchestrator/src/graphs/codegen.py`
Define the codegen subgraph with quality gate:

**Nodes:**
1. `codegen` — calls `codegen_agent`, produces artifacts
2. `quality_gate` — for each artifact, run syntax validation:
   - Python: `ast.parse(content)` + ruff check (if available)
   - TypeScript/JavaScript: basic syntax check (regex for obvious errors, or call a linter in sandbox)
   - Other: skip
   - If all pass: return `{ "quality_passed": True }`
   - If any fail: return `{ "quality_passed": False, "errors": [...] }`

**Edges:**
- START -> codegen
- codegen -> quality_gate
- quality_gate -> conditional:
  - If quality_passed: END (return to supervisor)
  - If NOT quality_passed AND retry_count < 3: back to codegen (increment retry_count, add error messages to state for the LLM to fix)
  - If NOT quality_passed AND retry_count >= 3: END with error

Export `create_codegen_subgraph() -> CompiledGraph`.

## Constraints
- Codegen can write files but CANNOT execute code (constraint #2).
- Quality gate is a deterministic check, not an LLM call.
- Max 3 retry iterations inside the subgraph (constraint #4).
- Persist each artifact to `code_artifacts` table via Supabase.
- Total code ~400 lines across 3 files.
```

</details>

---

### M21: Executor Agent & Execution Subgraph

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/graphs/execution.py`, `services/orchestrator/src/agents/executor.py`, `services/orchestrator/src/prompts/executor.md` |
| **Dependencies** | M01, M03, M16, M24 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Runs pytest in sandbox and captures results
- Handles timeout (60s kill)
- Results persisted to `execution_results` table

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the Executor agent and its LangGraph subgraph for the ADE Orchestrator. The executor runs tests and commands inside ephemeral Docker sandboxes.

## Context
Read `docs/architecture.md` Section 5 and Section 7. Read `CLAUDE.md` constraint #2: executor has sandbox-only execution, no file writes. The executor calls SandboxService via gRPC.

## Files to create

### `services/orchestrator/src/prompts/executor.md`
System prompt:
- Role: You are a test execution specialist. Run tests and commands to verify that generated code works correctly.
- You have access to: run_command (execute in isolated sandbox), read_file (check generated code).
- Decide what commands to run based on the step description and generated artifacts.
- Common commands: `python -m pytest`, `python -m pytest -v`, `node --check file.js`, `npx vitest run`.
- After running tests, summarize the results: what passed, what failed, and why.

### `services/orchestrator/src/agents/executor.py`
**Tools:**
- `run_command(command: str, runtime: str = "python3.12") -> dict` — calls sandbox tool (M24). Returns `{ stdout, stderr, exit_code, duration_ms }`.
- `read_file(file_path: str) -> str` — reads a file (M22).

**Agent function:** `executor_agent(state: WorkflowState) -> dict`
1. Determine runtime from context (Python or Node based on file extensions in artifacts).
2. LLM decides what commands to run.
3. Execute commands via sandbox tool.
4. Collect `ExecutionResult` objects.
5. Return `{ "execution_results": [results] }`.

### `services/orchestrator/src/graphs/execution.py`
**Nodes:**
1. `setup_sandbox` — creates sandbox via gRPC (SandboxService.CreateSandbox)
2. `execute` — runs the executor agent
3. `teardown_sandbox` — destroys sandbox via gRPC (SandboxService.DestroySandbox)

**Edges:** START -> setup_sandbox -> execute -> teardown_sandbox -> END

Export `create_execution_subgraph() -> CompiledGraph`.

## Constraints
- Executor can read files and execute commands, but CANNOT write files.
- All execution happens in the sandbox — never on the host.
- Persist results to `execution_results` table.
- Handle sandbox timeout (60s) gracefully.
- Total code ~350 lines across 3 files.
```

</details>

---

### M22: Tool — File Operations

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/tools/file_ops.py` |
| **Dependencies** | M01 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- `read_file` returns file content
- `write_file` creates/overwrites files safely
- Paths sandboxed to project repo_path

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the file operation tools for ADE orchestrator agents. These are LangGraph tool definitions for reading and writing files in the project repository.

## Context
Read `docs/architecture.md` Section 5 agent tool permissions table. Codegen has read+write. Executor and Context have read-only. Tool binding controls who gets which tools.

## Files to create

### `services/orchestrator/src/tools/file_ops.py`
Define LangGraph tools using the `@tool` decorator from `langchain_core.tools`:

1. **`read_file(file_path: str) -> str`**
   - Resolves `file_path` relative to the project's `repo_path`.
   - Validates the resolved path is within repo_path (prevent directory traversal).
   - Returns file content as string.
   - Raises ToolException if file doesn't exist or path escapes repo.

2. **`write_file(file_path: str, content: str) -> str`**
   - Resolves relative to repo_path.
   - Creates parent directories if needed.
   - Writes content to file.
   - Returns confirmation message with the file path.
   - Validates path is within repo (no traversal).

3. **`list_directory(dir_path: str = ".") -> str`**
   - Lists files and directories at the given path within the project repo.
   - Returns formatted listing with file types and sizes.
   - Max depth: 2 levels to prevent huge outputs.

4. **`delete_file(file_path: str) -> str`**
   - Deletes a file within the project repo.
   - Returns confirmation message.
   - Validates path is within repo.

**Shared utilities:**
- `resolve_safe_path(repo_path: str, relative_path: str) -> Path` — resolves and validates that the path stays within repo_path. Uses `Path.resolve()` and checks `.is_relative_to()`.
- `get_repo_path(state: dict) -> str` — extracts repo_path from the workflow state or project config.

## Constraints
- ALL path operations must be sandboxed to the project's repo_path. Use resolve_safe_path for every operation.
- Raise clear errors on directory traversal attempts.
- read_file should handle encoding (UTF-8 with fallback to latin-1).
- write_file should generate a diff string (unified diff format) comparing old vs new content for the CodeArtifact.
- Total code ~200 lines.
```

</details>

---

### M23: Tool — Semantic Search

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/tools/search.py` |
| **Dependencies** | M03 |
| **Est. lines** | ~120 |

**Acceptance criteria:**
- Returns top-k chunks with file_path and score
- gRPC timeout of 10s enforced

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the semantic search tool for ADE orchestrator agents. This tool calls the Context Service via gRPC to perform vector similarity search over the indexed codebase.

## Context
Read `docs/architecture.md` Section 4b (ContextService proto). The ContextService.RetrieveContext RPC takes a query string, project_id, top_k, and threshold, and returns ranked code chunks.

## Files to create

### `services/orchestrator/src/tools/search.py`
Define a LangGraph tool using `@tool`:

**`search_codebase(query: str, top_k: int = 10, threshold: float = 0.7) -> str`**
1. Create a gRPC channel to the Context Service at `CONTEXT_GRPC_URL` from config.
2. Build a `ContextQuery` message: project_id (from workflow state), query, top_k, threshold.
3. Call `ContextService.RetrieveContext` with a 10-second deadline.
4. Parse the `ContextChunks` response.
5. Format results as a readable string: for each chunk, show `[{score:.2f}] {file_path}\n{content}\n---`.
6. Return the formatted string (this is what the LLM sees).

**Helper:**
- `_get_context_stub()` — lazy singleton for the gRPC stub. Reuse across calls within the same process.

**Error handling:**
- If the Context Service is unavailable, return a message like "Context service unavailable — proceeding without codebase search."
- If no results found, return "No relevant code found for query: {query}"

## Constraints
- 10-second gRPC deadline on every call.
- Return human-readable formatted text (LLM will read this).
- Cache the gRPC channel/stub as a module-level singleton.
- Total code ~120 lines.
```

</details>

---

### M24: Tool — Sandbox Bridge

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/tools/sandbox.py` |
| **Dependencies** | M03 |
| **Est. lines** | ~150 |

**Acceptance criteria:**
- `run_command("python -m pytest")` returns stdout/stderr/exit_code
- Timeout at 60s kills the sandbox

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the sandbox execution tool for ADE orchestrator agents. This tool calls the Sandbox Service via gRPC to run commands inside ephemeral Docker containers.

## Context
Read `docs/architecture.md` Section 4b (SandboxService proto) and Section 7 (Docker sandbox design). The sandbox lifecycle: CreateSandbox -> Execute -> DestroySandbox. Resource limits: 1 CPU, 512MB RAM, 60s timeout, no network.

## Files to create

### `services/orchestrator/src/tools/sandbox.py`
Define a LangGraph tool:

**`run_command(command: str, runtime: str = "python3.12", timeout_s: int = 60) -> str`**
1. Get the gRPC stub for SandboxService.
2. Call `CreateSandbox(SandboxConfig(runtime=runtime, cpu_cores=1, memory_mb=512, timeout_s=timeout_s))`.
3. Call `Execute(ExecutionRequest(sandbox_id=sandbox.sandbox_id, command=command, code_path="/workspace"))`.
4. Call `DestroySandbox(SandboxId(id=sandbox.sandbox_id))` in a finally block.
5. Format result: `"Exit code: {exit_code}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}\nDuration: {duration_ms}ms"`
6. Return formatted string.

**Helper:**
- `_get_sandbox_stub()` — lazy singleton for gRPC stub.

**Error handling:**
- gRPC DEADLINE_EXCEEDED: return "Command timed out after {timeout_s} seconds"
- gRPC UNAVAILABLE: return "Sandbox service unavailable"
- Always call DestroySandbox in finally block to prevent container leaks.

## Constraints
- Every sandbox is created and destroyed within a single tool call (fully ephemeral).
- 60-second default timeout on execution.
- Always clean up (DestroySandbox) even on errors.
- Total code ~150 lines.
```

</details>

---

### M25: Tool — Git Operations

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/tools/git_ops.py` |
| **Dependencies** | M01 |
| **Est. lines** | ~150 |

**Acceptance criteria:**
- `git_diff` returns uncommitted changes
- `git_commit` creates a commit
- Operations sandboxed to project repo

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement git operation tools for ADE orchestrator agents. These tools execute git commands against the project repository.

## Context
Read `docs/architecture.md` Section 5 agent tool permissions. Git ops are available post-codegen for committing generated code. All git commands run against the project's repo_path.

## Files to create

### `services/orchestrator/src/tools/git_ops.py`
Define LangGraph tools:

1. **`git_status() -> str`** — runs `git status --porcelain` in repo_path, returns output
2. **`git_diff(staged: bool = False) -> str`** — runs `git diff` (or `git diff --staged`), returns output
3. **`git_add(file_paths: list[str] | str = ".") -> str`** — runs `git add` on specified paths
4. **`git_commit(message: str) -> str`** — runs `git commit -m "{message}"`, returns commit hash
5. **`git_branch(name: str | None = None) -> str`** — if name provided, creates branch; otherwise lists branches

All tools use `subprocess.run()` with:
- `cwd` set to the project repo_path
- `capture_output=True`, `text=True`, `timeout=30`
- Path validation to stay within repo_path

**Shared utility:**
- `_run_git(args: list[str], repo_path: str) -> tuple[str, str, int]` — runs git command, returns (stdout, stderr, returncode)

## Constraints
- All git commands must run with cwd set to repo_path.
- Timeout of 30 seconds for any git operation.
- Never run destructive commands (force push, hard reset) — restrict to safe operations.
- Total code ~150 lines.
```

</details>

---

### M26: Event Publisher

| Field | Detail |
|-------|--------|
| **Files** | `services/orchestrator/src/events/publisher.py` |
| **Dependencies** | M01, M04, M15 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- Events appear on Redis channel within 100ms of node completion
- Agent metrics are written to `agent_metrics` table

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the event publishing system for the ADE Orchestrator. This module publishes WorkflowEvent messages to Redis pub/sub and persists agent metrics to Supabase.

## Context
Read `docs/architecture.md` Section 6 for Redis pub/sub design. Events are published to `workflow:events:{task_id}`. Read Section 4c for the WebSocket event schema — the publisher produces these exact events. The Gateway subscribes and forwards to WebSocket clients.

## Files to create

### `services/orchestrator/src/events/publisher.py`
Implement `EventPublisher` class:

**Constructor:** takes Redis client and Supabase client.

**Methods:**

1. `publish_event(task_id: str, event_type: str, step_id: str | None, payload: dict) -> None`
   - Build a `WorkflowEvent` object: event_type, step_id, payload (JSON-encoded), timestamp (epoch ms).
   - Publish to Redis channel `workflow:events:{task_id}`.
   - Log the event at INFO level.

2. `workflow_started(task_id: str) -> None` — publishes `workflow.started`
3. `step_started(task_id: str, step_id: str, agent_type: str, title: str) -> None` — publishes `step.started`
4. `step_progress(task_id: str, step_id: str, message: str) -> None` — publishes `step.progress`
5. `step_completed(task_id: str, step_id: str, output: dict) -> None` — publishes `step.completed`
6. `step_failed(task_id: str, step_id: str, error: str) -> None` — publishes `step.failed`
7. `artifact_created(task_id: str, artifact_id: str, file_path: str, diff: str) -> None` — publishes `artifact.created`
8. `execution_result(task_id: str, result_id: str, exit_code: int, stdout: str, stderr: str) -> None`
9. `workflow_completed(task_id: str, summary: str, artifact_ids: list[str]) -> None`
10. `workflow_error(task_id: str, error: str, step_id: str | None) -> None`

11. `record_agent_metrics(run_id: str, agent_type: str, tokens_in: int, tokens_out: int, latency_ms: int) -> None`
    - Insert into `agent_metrics` table: metric entries for tokens_in, tokens_out, latency_ms.
    - Update the `agent_runs` row with tokens and latency.

**Factory:**
Export `create_publisher(redis_client, supabase_client) -> EventPublisher`.

## Constraints
- Redis publish is fire-and-forget (don't await confirmation).
- JSON encode all payloads — must handle UUIDs and datetimes.
- Supabase writes for metrics should be non-blocking (fire-and-forget or batched).
- Total code ~200 lines.
```

</details>

---

## Phase 3 — Sandbox Service

### M27: Sandbox Server Bootstrap

| Field | Detail |
|-------|--------|
| **Files** | `services/sandbox/src/server.py`, `config.py`, `pyproject.toml`, `Dockerfile` |
| **Dependencies** | M03 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- gRPC server starts on port 50052
- Health check responds

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the Sandbox service bootstrap — a Python gRPC server that manages ephemeral Docker containers for isolated code execution.

## Context
Read `docs/architecture.md` Section 7 for sandbox design. The Sandbox service implements `SandboxService` from `packages/proto/sandbox.proto`. It uses the Docker SDK to create, execute in, and destroy containers.

## Files to create

### `services/sandbox/pyproject.toml`
- Name: `ade-sandbox`
- Python: >=3.12
- Dependencies: `grpcio`, `grpcio-tools`, `docker` (Docker SDK for Python), `pydantic>=2.6`
- Dev: `pytest`, `ruff`

### `services/sandbox/src/config.py`
Config from env:
- `GRPC_PORT` (default: 50052)
- `DOCKER_SOCKET` (default: /var/run/docker.sock)
- `PYTHON_IMAGE` (default: ade-sandbox-python:latest)
- `NODE_IMAGE` (default: ade-sandbox-node:latest)
- `DEFAULT_CPU_CORES` (default: 1)
- `DEFAULT_MEMORY_MB` (default: 512)
- `DEFAULT_TIMEOUT_S` (default: 60)
- `LOG_LEVEL` (default: info)

### `services/sandbox/src/server.py`
gRPC server implementing SandboxService:
1. `CreateSandbox(config)` — delegates to container module (M28). Returns SandboxInfo.
2. `Execute(request)` — delegates to appropriate runner (M29). Returns ExecutionResult.
3. `DestroySandbox(sandbox_id)` — delegates to container module. Returns Ack.
4. Track active sandboxes in a dict: `{sandbox_id: container_info}`.
5. Periodic cleanup: destroy any sandbox that's been alive > 5 minutes (safety net).
6. Graceful shutdown: destroy all active sandboxes.

### `services/sandbox/Dockerfile`
- Base: python:3.12-slim
- Install docker CLI + SDK
- Copy and install pyproject.toml deps, then copy src
- USER nobody (but needs Docker socket access — document this)
- CMD, expose 50052

## Constraints
- Use `grpc.aio` for async server.
- The server itself runs on the host (or in a container with Docker socket mounted) — it manages OTHER containers.
- Total code ~200 lines.
```

</details>

---

### M28: Container Lifecycle & Network Isolation

| Field | Detail |
|-------|--------|
| **Files** | `services/sandbox/src/isolation/container.py`, `services/sandbox/src/isolation/network.py` |
| **Dependencies** | M27 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Container enforces 512MB memory limit
- No outbound network from sandbox
- Container auto-destroyed after execution

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement Docker container lifecycle management and network isolation for the ADE Sandbox service.

## Context
Read `docs/architecture.md` Section 7 for the full sandbox design. Resource limits: 1 CPU, 512MB RAM, 60s timeout, no network, read-only root (except /tmp), non-root user, dropped Linux capabilities.

## Files to create

### `services/sandbox/src/isolation/container.py`
Implement `ContainerManager` class using the Docker SDK for Python:

**Constructor:** takes Docker client, config.

**Methods:**

1. `create(runtime: str, cpu_cores: int, memory_mb: int, timeout_s: int, code_path: str) -> SandboxContainer`
   - Select image based on runtime: "python3.12" -> config.PYTHON_IMAGE, "node22" -> config.NODE_IMAGE
   - Create container with:
     - `--cpus={cpu_cores}`, `--memory={memory_mb}m`
     - `--read-only` (read-only root filesystem)
     - `--tmpfs /tmp:rw,noexec,nosuid,size=100m` (writable /tmp)
     - `--network={isolated_network}` (from network module)
     - `--user=1000:1000` (non-root)
     - `--cap-drop=ALL` (drop all capabilities)
     - `--security-opt=no-new-privileges`
     - Volume mount: code_path -> /workspace:ro
   - Start the container.
   - Return `SandboxContainer(id, container_ref, created_at, timeout_s)`.

2. `execute(sandbox: SandboxContainer, command: str, env: dict) -> ExecutionOutput`
   - Run `exec_run(command, environment=env, workdir="/workspace")` with timeout.
   - Capture stdout and stderr.
   - If execution exceeds timeout_s, kill the container and return timeout error.
   - Return `ExecutionOutput(stdout, stderr, exit_code, duration_ms)`.

3. `destroy(sandbox_id: str) -> None`
   - Force remove the container: `container.remove(force=True)`.
   - Clean up any temporary volumes.

**Data classes:**
- `SandboxContainer`: id, container (docker Container obj), created_at, timeout_s
- `ExecutionOutput`: stdout (str), stderr (str), exit_code (int), duration_ms (int)

### `services/sandbox/src/isolation/network.py`
Implement `NetworkManager`:

1. `ensure_isolated_network() -> str` — creates (or finds existing) Docker network named `ade-sandbox-isolated` with `--internal` flag (no external routing). Returns network name.
2. `cleanup_network() -> None` — removes the isolated network (called on shutdown).

## Constraints
- Use `docker` Python SDK (not subprocess calls to docker CLI).
- Timeout enforcement: use threading.Timer or asyncio.wait_for to kill container on timeout.
- ALWAYS clean up containers in finally blocks — leaked containers are a serious resource issue.
- Test the memory limit by documenting how: a Python script that allocates >512MB should be OOM-killed.
- Total code ~350 lines combined.
```

</details>

---

### M29: Language Runners

| Field | Detail |
|-------|--------|
| **Files** | `services/sandbox/src/runners/python_runner.py`, `node_runner.py`, `generic_runner.py` |
| **Dependencies** | M27, M28 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- Python runner executes `pytest` and parses results
- Node runner executes `vitest`
- Generic runner passes through raw output

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement language-specific runners for the ADE Sandbox service. Each runner knows how to set up, execute, and parse results for its language runtime.

## Context
Read `docs/architecture.md` Section 7 for image variants. Python image includes pytest, coverage, black, ruff, mypy. Node image includes jest, vitest, eslint, typescript, tsx.

## Files to create

### `services/sandbox/src/runners/python_runner.py`
`PythonRunner` class:
- `prepare(code_path: str) -> list[str]`: returns setup commands (e.g., `pip install -r requirements.txt` if requirements.txt exists)
- `get_test_command(test_path: str | None) -> str`: returns `python -m pytest {test_path} -v --tb=short` or default
- `get_lint_command() -> str`: returns `ruff check .`
- `parse_test_output(stdout: str, stderr: str) -> dict`: extract passed/failed/error counts from pytest output using regex

### `services/sandbox/src/runners/node_runner.py`
`NodeRunner` class:
- `prepare(code_path: str) -> list[str]`: returns `npm ci` if package.json exists
- `get_test_command(test_path: str | None) -> str`: returns `npx vitest run {test_path}` or default
- `get_lint_command() -> str`: returns `npx eslint .`
- `parse_test_output(stdout: str, stderr: str) -> dict`: extract test results from vitest output

### `services/sandbox/src/runners/generic_runner.py`
`GenericRunner` class:
- Fallback runner for arbitrary commands.
- `prepare()` -> empty list
- `execute(command: str) -> dict`: just passes command through, returns raw stdout/stderr
- No parsing — returns output as-is.

**Runner interface (base class or protocol):**
```python
class BaseRunner(Protocol):
    def prepare(self, code_path: str) -> list[str]: ...
    def get_test_command(self, test_path: str | None) -> str: ...
    def parse_test_output(self, stdout: str, stderr: str) -> dict: ...
```

**Runner factory:**
`get_runner(runtime: str) -> BaseRunner` — returns PythonRunner for "python*", NodeRunner for "node*", GenericRunner for anything else.

## Constraints
- Runners do NOT create containers — they provide commands and parse output. Container management is in M28.
- Test output parsing should be best-effort — don't crash on unexpected output format.
- Total code ~300 lines across 3 files.
```

</details>

---

### M30: Sandbox Docker Images

| Field | Detail |
|-------|--------|
| **Files** | `services/sandbox/images/python.Dockerfile`, `services/sandbox/images/node.Dockerfile` |
| **Dependencies** | None |
| **Est. lines** | ~80 |

**Acceptance criteria:**
- `docker build` succeeds for both images
- `pytest --version` works in Python image
- `npx vitest --version` works in Node image

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the pre-built Docker images used by the ADE Sandbox service for isolated code execution.

## Context
Read `docs/architecture.md` Section 7 "Image Variants" for exact specifications.

## Files to create

### `services/sandbox/images/python.Dockerfile`
- FROM python:3.12-slim
- RUN pip install --no-cache-dir pytest coverage black ruff mypy
- Create non-root user: useradd -m -u 1000 sandbox
- USER sandbox
- WORKDIR /workspace

### `services/sandbox/images/node.Dockerfile`
- FROM node:22-slim
- RUN npm install -g jest vitest eslint typescript tsx
- Create non-root user: useradd -m -u 1000 sandbox (or use existing node user with UID 1000)
- USER sandbox
- WORKDIR /workspace

## Constraints
- Images should be as small as possible (use slim bases, no-cache installs).
- Non-root user with UID 1000 to match the --user=1000:1000 flag in container creation.
- No ENTRYPOINT or CMD — commands are passed by the container manager.
- Total ~80 lines.
```

</details>

---

## Phase 4 — Context Service

### M31: Context Server Bootstrap

| Field | Detail |
|-------|--------|
| **Files** | `services/context/src/server.py`, `config.py`, `pyproject.toml`, `Dockerfile` |
| **Dependencies** | M03, M04 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- gRPC server starts on port 50053
- Handles `IndexRepository` and `RetrieveContext` RPCs

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the Context service bootstrap — a Python gRPC server for codebase indexing and RAG retrieval.

## Context
Read `docs/architecture.md` Sections 1 and 4b. The Context service implements `ContextService` from `packages/proto/context.proto`. It uses pgvector in Supabase for vector storage and OpenAI embeddings.

## Files to create

### `services/context/pyproject.toml`
- Name: `ade-context`
- Python: >=3.12
- Dependencies: `grpcio`, `grpcio-tools`, `openai` (for embeddings), `supabase`, `watchdog` (file watcher), `tree-sitter` + `tree-sitter-python` + `tree-sitter-javascript` (AST parsing), `redis`, `pydantic>=2.6`, `ade-types`
- Dev: `pytest`, `ruff`

### `services/context/src/config.py`
- `GRPC_PORT` (default: 50053), `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `REDIS_URL`, `OPENAI_API_KEY`
- `EMBEDDING_MODEL` (default: "text-embedding-3-small"), `EMBEDDING_DIMENSIONS` (default: 1536)
- `CHUNK_MAX_TOKENS` (default: 500), `LOG_LEVEL`

### `services/context/src/server.py`
gRPC server implementing ContextService:
1. `IndexRepository(request)` — delegates to chunker (M32) and embedder (M33). Returns IndexResult.
2. `RetrieveContext(query)` — delegates to search (M35). Returns ContextChunks.
3. `WatchChanges(request)` — delegates to watcher (M34). Streams ChangeEvent.

### `services/context/Dockerfile`
- python:3.12-slim, install deps, copy src, expose 50053

## Constraints
- Use `grpc.aio` for async.
- Lazy-import indexer/retriever modules for incremental development.
- Total code ~200 lines.
```

</details>

---

### M32: AST Chunker

| Field | Detail |
|-------|--------|
| **Files** | `services/context/src/indexer/chunker.py` |
| **Dependencies** | M01 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Python files chunked into function/class-level blocks
- Each chunk < 500 tokens
- Fallback to sliding-window for non-parseable files

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the AST-aware code chunker for the ADE Context service. This module parses source code files into semantically meaningful chunks for embedding and retrieval.

## Context
Read `docs/architecture.md` Section 1 (Context Agent role). Code chunks are stored in the `context_chunks` table and used for RAG retrieval. Good chunks should be function-level or class-level, including necessary context like imports.

## Files to create

### `services/context/src/indexer/chunker.py`
Implement `CodeChunker` class:

**Public method:** `chunk_file(file_path: str, content: str) -> list[CodeChunk]`

Where `CodeChunk` is a dataclass: `file_path`, `chunk_content`, `metadata` (dict with keys: chunk_type, name, start_line, end_line, language).

**Strategy by language:**

1. **Python** (`.py` files): Use Python's built-in `ast` module.
   - Parse with `ast.parse(content)`.
   - Extract top-level: functions (`ast.FunctionDef`), classes (`ast.ClassDef`), and module-level code.
   - For each class, also extract individual methods as sub-chunks.
   - Prepend file-level imports to each chunk for context.
   - If a chunk exceeds max_tokens, split it with sliding window.

2. **TypeScript/JavaScript** (`.ts`, `.js`, `.tsx`, `.jsx`): Use regex-based splitting.
   - Split on function/class/interface declarations using regex patterns.
   - Capture: `export function`, `export class`, `export interface`, `export const ... = () =>`, etc.
   - Include preceding comments/JSDoc as part of the chunk.

3. **Other files** (`.md`, `.sql`, `.yaml`, `.json`, etc.): Sliding-window chunking.
   - Window size: max_tokens (default 500 tokens, estimate ~4 chars per token).
   - Overlap: 50 tokens.
   - Split on paragraph/section boundaries when possible.

**Token estimation:** `_estimate_tokens(text: str) -> int` — approximate as `len(text) // 4`.

**Ignored files:** Skip binary files, node_modules, .git, __pycache__, dist, build directories.

## Constraints
- Use Python's built-in `ast` module for Python parsing (not tree-sitter, to avoid the dependency for MVP).
- Each chunk should be self-contained enough to be useful without reading the full file.
- Max chunk size: 500 tokens (~2000 chars). Split larger chunks.
- Include file_path and line numbers in metadata for every chunk.
- Total code ~350 lines.
```

</details>

---

### M33: Embedding Generator

| Field | Detail |
|-------|--------|
| **Files** | `services/context/src/indexer/embedder.py` |
| **Dependencies** | M01, M04, M32 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- 100 chunks embedded and stored in < 10s
- Embeddings are 1536-dimensional
- Batch processing works

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the embedding generator for the ADE Context service. This module generates vector embeddings for code chunks and stores them in Supabase.

## Context
Read `docs/architecture.md` Section 3 for `context_chunks` table schema. Uses OpenAI text-embedding-3-small (1536 dimensions). Chunks come from the chunker module (M32).

## Files to create

### `services/context/src/indexer/embedder.py`
Implement `Embedder` class:

**Constructor:** takes OpenAI client and Supabase client.

**Methods:**

1. `embed_chunks(project_id: str, chunks: list[CodeChunk]) -> int`
   - Batch the chunks into groups of 100 (OpenAI API limit).
   - For each batch, call `openai.embeddings.create(model="text-embedding-3-small", input=[chunk.chunk_content for chunk in batch])`.
   - Build rows for Supabase: `{ project_id, file_path, chunk_content, embedding, metadata, indexed_at }`.
   - Upsert into `context_chunks` table (upsert on project_id + file_path + chunk content hash to avoid duplicates).
   - Return total count of embedded chunks.

2. `embed_query(query: str) -> list[float]`
   - Generate a single embedding for a search query.
   - Return the 1536-dimensional vector.

3. `delete_file_chunks(project_id: str, file_path: str) -> int`
   - Delete all chunks for a specific file (used when file is modified or deleted).
   - Return count of deleted chunks.

**Caching:**
- Cache embeddings in Redis at `ctx:{project_id}:{chunk_hash}` with 15-min TTL to avoid re-embedding unchanged chunks.

## Constraints
- Batch API calls (max 100 chunks per request).
- Handle OpenAI rate limits with exponential backoff.
- Use SHA256 hash of chunk_content for deduplication.
- Total code ~200 lines.
```

</details>

---

### M34: File Watcher

| Field | Detail |
|-------|--------|
| **Files** | `services/context/src/indexer/watcher.py` |
| **Dependencies** | M32, M33 |
| **Est. lines** | ~200 |

**Acceptance criteria:**
- File modification triggers re-indexing within 5s
- Deleted files have their chunks removed
- Debounces rapid changes

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the file watcher for the ADE Context service. This module monitors project repositories for file changes and triggers re-indexing.

## Context
Read `docs/architecture.md` Section 6 for cache invalidation on file change. The watcher uses the `watchdog` library to monitor the filesystem and triggers the chunker + embedder pipeline on changes.

## Files to create

### `services/context/src/indexer/watcher.py`
Implement `FileWatcher` class:

**Constructor:** takes project_id, repo_path, chunker (M32), embedder (M33), Redis client.

**Methods:**

1. `start() -> None` — starts the watchdog Observer on repo_path.
2. `stop() -> None` — stops the Observer.

**Watchdog event handler (inner class or function):**
- On `FileCreatedEvent` or `FileModifiedEvent`:
  - Debounce: wait 2 seconds after last event for same file (use a dict of timers).
  - Skip ignored files/directories (.git, node_modules, __pycache__, etc.).
  - Read file content.
  - Re-chunk the file using chunker.
  - Delete old chunks for that file_path.
  - Embed and store new chunks.
  - Invalidate Redis cache: delete keys matching `ctx:{project_id}:*` for the affected file.
  - Publish a ChangeEvent to any active WatchChanges stream.

- On `FileDeletedEvent`:
  - Delete all chunks for that file_path from Supabase.
  - Invalidate Redis cache.

**Full index method:**
- `index_repository(project_id: str, repo_path: str, force: bool = False) -> IndexResult`
  - Walk the repo directory.
  - If not force, skip files whose mtime hasn't changed since last index (store mtime in chunk metadata).
  - Chunk and embed all eligible files.
  - Return IndexResult with counts.

## Constraints
- Use `watchdog` library for cross-platform file watching.
- Debounce rapid saves (2-second window per file).
- Skip binary files and ignored directories.
- Total code ~200 lines.
```

</details>

---

### M35: Vector Search & Reranker

| Field | Detail |
|-------|--------|
| **Files** | `services/context/src/retriever/search.py`, `services/context/src/retriever/reranker.py` |
| **Dependencies** | M04, M31, M33 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- Query returns relevant chunks ranked by cosine similarity
- Cached results returned on repeat query
- Reranker improves precision

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement vector search and result reranking for the ADE Context service.

## Context
Read `docs/architecture.md` Section 3 for the `context_chunks` table with pgvector. Section 6 for Redis caching of context chunks. The search uses cosine similarity via pgvector's `<=>` operator.

## Files to create

### `services/context/src/retriever/search.py`
Implement `VectorSearch` class:

**Constructor:** takes Supabase client, Redis client, Embedder instance (M33).

**Methods:**

1. `search(project_id: str, query: str, top_k: int = 10, threshold: float = 0.7) -> list[SearchResult]`
   - Generate query embedding using `embedder.embed_query(query)`.
   - Check Redis cache: `ctx:search:{project_id}:{hash(query+top_k+threshold)}` with 5-min TTL.
   - If not cached, query Supabase using pgvector:
     ```sql
     SELECT id, file_path, chunk_content, metadata,
            1 - (embedding <=> $1) AS similarity
     FROM context_chunks
     WHERE project_id = $2
       AND 1 - (embedding <=> $1) > $3
     ORDER BY embedding <=> $1
     LIMIT $4
     ```
   - Filter results above threshold.
   - Cache results in Redis.
   - Return list of `SearchResult(id, file_path, content, score, metadata)`.

### `services/context/src/retriever/reranker.py`
Implement `Reranker` class:

**Methods:**

1. `rerank(query: str, results: list[SearchResult], top_n: int = 5) -> list[SearchResult]`
   - For MVP, use a simple keyword-overlap reranker:
     - Tokenize query into keywords.
     - Score each result by: (cosine_similarity * 0.7) + (keyword_overlap_ratio * 0.3).
     - Re-sort by combined score.
   - Return top_n results.
   - (Future: replace with cross-encoder model for better precision.)

## Constraints
- Use Supabase's `.rpc()` for the vector similarity query (create a Supabase function or use raw SQL).
- Cache search results in Redis with 5-min TTL.
- The reranker is a lightweight scoring adjustment for MVP — not an LLM call.
- Total code ~300 lines combined.
```

</details>

---

## Phase 5 — CLI

### M36: CLI Bootstrap & Task Command

| Field | Detail |
|-------|--------|
| **Files** | `cli/src/main.py`, `cli/src/commands/task.py`, `cli/pyproject.toml`, `cli/README.md` |
| **Dependencies** | M06, M10, M12 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- `ade task "build auth"` submits task and streams events
- Rich progress display in terminal
- Auth token stored in config file

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the CLI bootstrap and task submission command for the ADE system.

## Context
Read `CLAUDE.md` for the CLI structure at `cli/`. The CLI is built with Typer + Rich. It communicates with the Gateway API via REST and WebSocket.

## Files to create

### `cli/pyproject.toml`
- Name: `ade-cli`
- Python: >=3.12
- Dependencies: `typer[all]>=0.9`, `rich>=13`, `httpx` (HTTP client), `websockets` (WS client), `pydantic>=2.6`
- Scripts: `ade = "src.main:app"`

### `cli/src/main.py`
Typer app entrypoint:
- Create Typer app with `name="ade"`, help="Agentic Developer Environment CLI"
- Register command groups: `task`, `project`, `status`, `logs` (import from commands/)
- Global options: `--api-url` (default: http://localhost:3000), `--token` (auth token)
- Config file: `~/.ade/config.json` with saved api_url and token.
- Load config on startup, override with CLI flags.

### `cli/src/commands/task.py`
Implement `ade task "prompt"` command:

1. **`task` command** (default/main):
   - Argument: `prompt` (str) — the task description
   - Option: `--project-id` (UUID, required or from config)
   - Option: `--no-stream` (bool, skip WebSocket streaming)
   - Flow:
     a. POST to `/api/v1/tasks` with `{ project_id, prompt }`.
     b. Print task_id and ws_url.
     c. Unless `--no-stream`: open WebSocket to ws_url, stream events.
     d. Use Rich Live display to show a progress panel:
        - Current step name and agent type
        - Progress bar for steps (N of M completed)
        - Live-updating log of events
     e. On `workflow.completed`: print summary and exit 0.
     f. On `workflow.error`: print error and exit 1.

### `cli/README.md`
Brief usage instructions for the CLI tool.

## Constraints
- Use `httpx` for HTTP (async-capable).
- Use `websockets` library for WebSocket client.
- Rich Live display for real-time updates.
- Store auth token in `~/.ade/config.json` after first auth.
- Total code ~300 lines.
```

</details>

---

### M37: CLI Project & Status Commands

| Field | Detail |
|-------|--------|
| **Files** | `cli/src/commands/project.py`, `cli/src/commands/status.py` |
| **Dependencies** | M09, M10 |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- `ade project init` registers project
- `ade status <id>` shows step-by-step progress table

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the project and status CLI commands for the ADE system.

## Context
Read `CLAUDE.md` CLI structure. These commands interact with the Gateway REST API to manage projects and check task status.

## Files to create

### `cli/src/commands/project.py`
Typer command group `project`:

1. **`ade project init`** — Initialize a new project
   - Option: `--name` (str, default: current directory name)
   - Option: `--repo-url` (str, optional)
   - Option: `--repo-path` (str, default: current directory)
   - POST to `/api/v1/projects` with the project details.
   - Save project_id to `~/.ade/config.json` as the default project.
   - Print project details in a Rich table.

2. **`ade project link <project-id>`** — Link to an existing project
   - Save project_id to config.
   - GET the project details and display.

3. **`ade project list`** — List all projects
   - GET `/api/v1/projects` and display as Rich table.

4. **`ade project info`** — Show current project details
   - GET the project from saved project_id in config.

### `cli/src/commands/status.py`
1. **`ade status <task-id>`** — Show task status
   - GET `/api/v1/tasks/{task_id}` for task details.
   - GET `/api/v1/tasks/{task_id}/steps` for step breakdown.
   - Display as Rich table:
     - Task: prompt, status, created_at
     - Steps table: ordinal, title, agent_type, status, duration
   - Color-code statuses: green=completed, yellow=in_progress, red=failed, gray=pending.

## Constraints
- All HTTP calls use httpx with the auth token from config.
- Rich tables for all output.
- Handle errors gracefully: 404 (not found), 401 (unauthorized), connection errors.
- Total code ~250 lines.
```

</details>

---

### M38: CLI Logs & Rich Display

| Field | Detail |
|-------|--------|
| **Files** | `cli/src/commands/logs.py`, `cli/src/display/rich_output.py` |
| **Dependencies** | M11, M14 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- `ade logs <id>` shows syntax-highlighted diffs and test output
- Rich tables render cleanly for all display types

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the logs command and shared Rich display utilities for the ADE CLI.

## Context
The logs command retrieves artifacts and execution results for a completed task and displays them with Rich formatting.

## Files to create

### `cli/src/commands/logs.py`
1. **`ade logs <task-id>`** — Display task artifacts and results
   - Option: `--artifacts` (show only code artifacts)
   - Option: `--results` (show only execution results)
   - Option: `--metrics` (show agent metrics)
   - Default: show everything.
   - GET `/api/v1/tasks/{task_id}/artifacts` — display each artifact with syntax-highlighted diff.
   - GET `/api/v1/tasks/{task_id}/results` — display each result with stdout/stderr.
   - GET `/api/v1/metrics?project_id=...` — display summary metrics.

### `cli/src/display/rich_output.py`
Shared Rich rendering utilities:

1. `render_task_status(task: dict) -> Panel` — Rich panel showing task prompt, status badge, timestamps.
2. `render_steps_table(steps: list[dict]) -> Table` — Rich table of task steps with colored statuses.
3. `render_diff(file_path: str, diff: str, language: str) -> Syntax` — Syntax-highlighted unified diff.
4. `render_execution_result(result: dict) -> Panel` — Panel with command, exit code (green/red), stdout, stderr.
5. `render_metrics_summary(metrics: dict) -> Table` — Table of token usage, costs, latencies.
6. `render_streaming_event(event: dict) -> Text` — Format a WebSocket event for live display.
7. `status_style(status: str) -> str` — Map status strings to Rich styles (green, yellow, red, etc.).

## Constraints
- Use Rich Syntax for code highlighting (auto-detect language from file extension).
- Use Rich Panel, Table, Text, and Live for output.
- Diffs should use "diff" syntax highlighting.
- Handle large outputs gracefully (truncate stdout >1000 lines with "... truncated" message).
- Total code ~350 lines combined.
```

</details>

---

## Phase 6 — UI

### M39: App Shell & Routing

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/App.tsx`, `ui/src/main.tsx`, `ui/index.html`, `ui/package.json`, `ui/tsconfig.json`, `ui/vite.config.ts`, `ui/Dockerfile`, `ui/tailwind.config.ts`, `ui/postcss.config.js` |
| **Dependencies** | M02 |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- `npm run dev` starts on port 5173
- Navigation between Dashboard, TaskDetail, Settings works
- Responsive layout with sidebar

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Create the React UI app shell with routing and layout for the ADE system.

## Context
Read `CLAUDE.md` and `docs/architecture.md` Section 2 for the UI structure. The UI is a React + TypeScript app built with Vite, using Tailwind CSS and shadcn/ui components.

## Files to create

### `ui/package.json`
- Name: `@ade/ui`
- Dependencies: `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `zustand`, `tailwindcss`, `@radix-ui/react-*` (via shadcn), `lucide-react` (icons), `clsx`, `tailwind-merge`
- DevDependencies: `typescript`, `@types/react`, `@types/react-dom`, `vite`, `@vitejs/plugin-react`, `autoprefixer`, `postcss`
- Scripts: `dev`, `build`, `preview`, `typecheck`

### `ui/vite.config.ts`
- React plugin, resolve alias `@` -> `src/`, proxy `/api` and `/ws` to `http://localhost:3000` in dev.

### `ui/tailwind.config.ts` + `ui/postcss.config.js`
- Standard Tailwind + shadcn configuration with dark mode support.

### `ui/index.html`
- Standard Vite HTML entry point.

### `ui/src/main.tsx`
- React 18 createRoot, render App.

### `ui/src/App.tsx`
- React Router with routes: `/` (Dashboard), `/tasks/:id` (TaskDetail), `/settings` (ProjectSettings).
- Layout component with:
  - Left sidebar (collapsible): logo, nav links (Dashboard, Settings), active project indicator.
  - Main content area where routes render.
  - Header bar with project selector dropdown.
- Wrap with TanStack Query Provider and a Zustand-compatible context.
- Responsive: sidebar collapses to icons on mobile.

### `ui/Dockerfile`
- Multi-stage: node:22-slim, npm ci, vite build, then nginx:alpine serving dist/.

## Constraints
- Use shadcn/ui design system (or Radix primitives with Tailwind styling).
- Dark mode support via Tailwind's `dark:` prefix.
- Clean, modern, minimal UI — no unnecessary decoration.
- Total code ~250 lines (excluding generated shadcn components).
```

</details>

---

### M40: Zustand Store & API Client

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/store/index.ts`, `ui/src/api/client.ts` |
| **Dependencies** | M02, M06 |
| **Est. lines** | ~300 |

**Acceptance criteria:**
- `apiClient.getTasks()` returns typed `Task[]`
- Store updates trigger re-renders
- Auth token managed in store

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the Zustand state store and typed API client for the ADE UI.

## Context
Read `docs/architecture.md` Section 4a for all REST endpoints. The TypeScript types from `@ade/shared-types` (M02) provide Zod schemas for response validation.

## Files to create

### `ui/src/api/client.ts`
Typed API client class:

**Constructor:** takes `baseUrl` (from env), auth token.

**Methods** (all return typed data using Zod schemas for validation):
- `createProject(data: CreateProjectRequest): Promise<Project>`
- `getProject(id: string): Promise<Project>`
- `listProjects(): Promise<{ projects: Project[], total: number }>`
- `createTask(data: CreateTaskRequest): Promise<CreateTaskResponse>`
- `getTask(id: string): Promise<Task>`
- `listTasks(projectId: string, opts?): Promise<{ tasks: Task[], total: number }>`
- `getTaskSteps(taskId: string): Promise<{ steps: TaskStep[] }>`
- `approveStep(taskId: string, stepId: string, approved: boolean): Promise<TaskStep>`
- `getArtifacts(taskId: string): Promise<{ artifacts: CodeArtifact[], total: number }>`
- `getResults(taskId: string): Promise<{ results: ExecutionResult[], total: number }>`
- `getMetrics(projectId: string, opts?): Promise<MetricsResponse>`

**Shared fetch wrapper:** handles auth header, JSON parsing, Zod validation, error mapping (401 -> redirect to auth, 404 -> null, 429 -> retry-after).

### `ui/src/store/index.ts`
Zustand store with slices:

- `auth`: { token, setToken, clearToken, isAuthenticated }
- `projects`: { projects, activeProjectId, setActiveProject, fetchProjects }
- `tasks`: { tasks, activeTaskId, fetchTasks, addTask }
- `activeTask`: { task, steps, artifacts, results, wsEvents, setTask, addEvent }
- `ui`: { sidebarOpen, theme, toggleSidebar, setTheme }

Use Zustand's `persist` middleware for token and activeProjectId (localStorage).

## Constraints
- API client is a plain class (not React-specific) — can be used in hooks or directly.
- Zod-validate all API responses at runtime (catch backend bugs early).
- Store uses immer middleware for convenient immutable updates.
- Total code ~300 lines combined.
```

</details>

---

### M41: WebSocket Hook

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/hooks/useWebSocket.ts` |
| **Dependencies** | M12, M40 |
| **Est. lines** | ~150 |

**Acceptance criteria:**
- Connects on mount, events flow into store
- Reconnects with exponential backoff
- Cleans up on unmount

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the WebSocket React hook for real-time task event streaming in the ADE UI.

## Context
Read `docs/architecture.md` Section 4c for the WebSocket event schema. The Gateway serves WebSocket at `/ws/tasks/:id`. Events are JSON-encoded WorkflowEvent objects.

## Files to create

### `ui/src/hooks/useWebSocket.ts`
Export `useTaskWebSocket(taskId: string | null)` hook:

1. **Connection:** When taskId is non-null, open WebSocket to `ws://localhost:3000/ws/tasks/{taskId}?token={authToken}`.
2. **Message handling:** Parse each message as JSON WorkflowEvent. Dispatch to Zustand store via `addEvent(event)`. Also update task/step state based on event_type:
   - `step.started` -> update step status to "in_progress"
   - `step.completed` -> update step status to "completed"
   - `step.failed` -> update step status to "failed"
   - `artifact.created` -> add to artifacts list
   - `execution.result` -> add to results list
   - `workflow.completed` -> update task status to "completed"
   - `workflow.error` -> update task status to "failed"
3. **Reconnection:** On close or error, reconnect with exponential backoff: 1s, 2s, 4s, 8s, max 30s. Reset on successful connection.
4. **Heartbeat:** Respond to server `heartbeat` events. Send `{ type: "ping" }` every 25s.
5. **Cleanup:** On unmount or taskId change, close the WebSocket.
6. **Return:** `{ isConnected: boolean, lastEvent: WorkflowEvent | null, error: string | null }`

## Constraints
- Use native WebSocket API (no library needed).
- Handle all WebSocket lifecycle events: open, message, close, error.
- Don't reconnect if the task is in a terminal state (completed/failed).
- Total code ~150 lines.
```

</details>

---

### M42: Task Submission Flow

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/components/TaskSubmit.tsx`, `ui/src/pages/Dashboard.tsx` |
| **Dependencies** | M39, M40 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Submit a task from UI
- Task appears in dashboard with status
- Click navigates to detail page

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the task submission component and dashboard page for the ADE UI.

## Context
Read `docs/architecture.md` Section 4a for the task submission API. The dashboard is the main landing page showing recent tasks and a submit form.

## Files to create

### `ui/src/components/TaskSubmit.tsx`
A modal or inline form for submitting new tasks:
- Project selector dropdown (populated from store).
- Large textarea for the task prompt with placeholder: "Describe what you want to build..."
- Submit button with loading state.
- On submit: call `apiClient.createTask(...)`, add task to store, navigate to `/tasks/{task_id}`.
- Keyboard shortcut: Cmd+Enter to submit.
- Validation: prompt must be non-empty, project must be selected.

### `ui/src/pages/Dashboard.tsx`
Main dashboard page:
- Header: "Dashboard" title + "New Task" button (opens TaskSubmit).
- Task list: fetched via `apiClient.listTasks(activeProjectId)` using TanStack Query.
- Each task card shows: prompt (truncated), status badge (colored), created_at (relative time), step progress (e.g., "3/5 steps complete").
- Click on a task card navigates to `/tasks/{task_id}`.
- Empty state: illustration + "Submit your first task" CTA.
- Auto-refresh every 10 seconds for active tasks.

## Constraints
- Use TanStack Query for data fetching (with automatic refetch).
- Status badges should use colored pills: blue=pending, yellow=planning/executing, green=completed, red=failed.
- Responsive: cards stack vertically on mobile.
- Total code ~350 lines combined.
```

</details>

---

### M43: Task Detail & Timeline

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/pages/TaskDetail.tsx`, `ui/src/components/TaskTimeline.tsx`, `ui/src/hooks/useTask.ts` |
| **Dependencies** | M39, M40, M41 |
| **Est. lines** | ~500 |

**Acceptance criteria:**
- Live timeline updates as agents work
- Completed steps show green; failed show red
- Expandable step details show output

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the task detail page with live timeline for the ADE UI.

## Context
Read `docs/architecture.md` Section 4c for WebSocket events. This is the core user experience — watching agents work in real time.

## Files to create

### `ui/src/hooks/useTask.ts`
Composable hook combining REST data fetching + WebSocket streaming:
- Fetch task, steps, artifacts, results via REST on mount.
- Open WebSocket for live updates (via useTaskWebSocket).
- Merge REST data with WS events for a consistent view.
- Return: `{ task, steps, artifacts, results, isLoading, isConnected }`

### `ui/src/components/TaskTimeline.tsx`
Vertical timeline visualization:
- Each step is a timeline node with:
  - Status icon (spinner=in_progress, check=completed, x=failed, clock=pending)
  - Step title and agent type badge
  - Expandable content area showing:
    - Step description
    - Agent output (from step.completed event payload)
    - Duration (if completed)
    - Error message (if failed)
  - Subtle animation when status changes (transition from pending to in_progress)
- Steps are ordered by ordinal.
- Auto-scroll to the currently active step.
- Responsive: full-width on mobile.

### `ui/src/pages/TaskDetail.tsx`
Task detail page layout:
- Header: task prompt, status badge, timestamps, cancel button (if active).
- Two-column layout (desktop):
  - Left (60%): TaskTimeline component.
  - Right (40%): Tabbed panel with "Artifacts", "Results", "Chat" tabs.
- Mobile: single column, tabs below timeline.
- "Artifacts" tab: list of code artifacts with file path, click to expand diff (M44).
- "Results" tab: list of execution results with exit codes.
- "Chat" tab: agent conversation (M46).
- Human-in-the-loop: if a step has `requires_approval`, show approve/reject buttons inline.

## Constraints
- Use the `useTask` hook for all data.
- Smooth animations for status transitions (CSS transitions or framer-motion).
- Auto-scroll behavior should be cancellable (if user scrolls up manually, stop auto-scrolling).
- Total code ~500 lines across 3 files.
```

</details>

---

### M44: Code Diff Viewer

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/components/CodeDiff.tsx` |
| **Dependencies** | M40 |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- Unified diffs render with syntax highlighting
- File sections are collapsible
- Large diffs are virtualized

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the code diff viewer component for the ADE UI.

## Context
Code artifacts from the orchestrator include a `diff` field (unified diff format) and a `content` field (full file content). This component renders them in a developer-friendly way.

## Files to create

### `ui/src/components/CodeDiff.tsx`
Props: `{ artifacts: CodeArtifact[] }` or `{ artifact: CodeArtifact }`.

**Features:**
1. **File list view:** When showing multiple artifacts, render a collapsible list. Each item shows file_path, language badge, and change summary (+N/-M lines).
2. **Diff rendering:** For each artifact with a `diff` field:
   - Parse the unified diff format.
   - Render with line numbers, green backgrounds for additions, red for deletions.
   - Syntax highlighting based on the `language` field (use a lightweight highlighter like Prism or highlight.js).
3. **Full content view:** Toggle to show the full file content (for new files without a diff).
4. **Copy button:** Copy file content or diff to clipboard.
5. **Virtualization:** For large diffs (>500 lines), use virtual scrolling to maintain performance.
6. **Collapsible sections:** Each file section can be expanded/collapsed. Default: first 3 expanded, rest collapsed.

**Styling:**
- Monospace font (JetBrains Mono or system monospace).
- Line numbers in gray gutter.
- Additions: green-50 background, green-700 text.
- Deletions: red-50 background, red-700 text.
- Dark mode compatible.

## Constraints
- Use a lightweight diff library (e.g., `diff2html` or manual parsing of unified diffs).
- Syntax highlighting library should be code-split / lazy-loaded.
- Total code ~250 lines.
```

</details>

---

### M45: Metrics Dashboard

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/components/MetricsDashboard.tsx`, `ui/src/hooks/useMetrics.ts` |
| **Dependencies** | M39, M40 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Charts render with sample data
- Auto-refresh every 30s
- Time range filter works

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the metrics dashboard component for the ADE UI.

## Context
Read `docs/architecture.md` Section 3 for metrics tables. The `/api/v1/metrics` endpoint (M14) returns aggregated data including token usage, costs, latencies, and success rates.

## Files to create

### `ui/src/hooks/useMetrics.ts`
- Fetch metrics via `apiClient.getMetrics(projectId, { from, to, granularity })`.
- Use TanStack Query with 30-second refetch interval.
- Return: `{ metrics, isLoading, timeRange, setTimeRange }`

### `ui/src/components/MetricsDashboard.tsx`
Dashboard with cards and charts:

**Summary Cards (top row):**
- Total Tasks (completed/total)
- Token Usage (in/out with cost estimate)
- Avg Latency (with p95)
- Success Rate (percentage with trend)

**Charts:**
1. **Tasks over time** — bar chart showing tasks per day/hour.
2. **Token usage over time** — area chart with tokens_in and tokens_out.
3. **Latency by agent type** — horizontal bar chart comparing planner, codegen, executor, context.
4. **Success/failure rate** — donut chart.

**Controls:**
- Time range selector: Last 24h, Last 7d, Last 30d, Custom.
- Agent type filter: All, Planner, Codegen, Executor, Context.

Use `recharts` library for charts.

## Constraints
- Use `recharts` (lightweight, React-native charts).
- Cards should show trend indicators (up/down arrow with percentage vs previous period).
- Handle empty state gracefully (no data yet).
- Total code ~350 lines combined.
```

</details>

---

### M46: Agent Chat

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/components/AgentChat.tsx` |
| **Dependencies** | M40, M41 |
| **Est. lines** | ~350 |

**Acceptance criteria:**
- Agent messages stream in real time
- Approval buttons appear for flagged steps
- Tool calls displayed with collapsible output

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the agent chat/conversation component for the ADE UI.

## Context
Read `docs/architecture.md` Section 3 for the `conversations` table and Section 5 for the human-in-the-loop design. This component shows the real-time conversation between agents and the system, including tool calls and their outputs.

## Files to create

### `ui/src/components/AgentChat.tsx`
Props: `{ taskId: string }`

**Features:**
1. **Message list:** Display conversation messages with role-based styling:
   - System messages: gray background, italic
   - Agent (assistant) messages: left-aligned, agent type badge
   - Tool messages: collapsible panel showing tool name, input, output
   - User messages (approvals/feedback): right-aligned, blue background

2. **Live updates:** Subscribe to WebSocket events:
   - `step.started` -> show "Agent started: {title}" message
   - `step.progress` -> streaming text update (LLM tokens)
   - `step.completed` -> show completion message with output
   - `artifact.created` -> show inline mini diff preview
   - `execution.result` -> show inline result with exit code

3. **Human-in-the-loop:**
   - When a step has `requires_approval`, render an approval card:
     - Step title and description
     - "Approve" (green) and "Reject" (red) buttons
     - Optional feedback textarea
   - On click: call `apiClient.approveStep(taskId, stepId, approved)`.

4. **Auto-scroll:** Scroll to bottom on new messages. Stop auto-scroll if user scrolls up. "Jump to latest" button when not at bottom.

5. **Timestamp:** Show relative timestamps (e.g., "2m ago") on hover.

## Constraints
- Messages should use a chat-bubble UI pattern.
- Tool call outputs should be in collapsible code blocks (collapsed by default).
- Approval card should be visually prominent (yellow border or background).
- Total code ~350 lines.
```

</details>

---

### M47: Project Settings Page

| Field | Detail |
|-------|--------|
| **Files** | `ui/src/pages/ProjectSettings.tsx` |
| **Dependencies** | M39, M40 |
| **Est. lines** | ~250 |

**Acceptance criteria:**
- Settings load and save correctly
- Re-index triggers context service
- Form validation works

<details>
<summary><strong>Plan Mode Prompt</strong></summary>

```
## Task
Implement the project settings page for the ADE UI.

## Context
Read `docs/architecture.md` Section 3 for the `projects` table. The settings JSONB column stores project-specific configuration.

## Files to create

### `ui/src/pages/ProjectSettings.tsx`
Settings form page:

**Sections:**

1. **General:**
   - Project name (text input)
   - Repository URL (text input, validated as URL)
   - Repository path (text input)

2. **Model Preferences:**
   - Supervisor model (dropdown: Claude Opus, GPT-4o)
   - Worker model (dropdown: Claude Sonnet, GPT-4o-mini)
   - Temperature slider (0.0 - 1.0)

3. **Rate Limits:**
   - Max requests per minute (number input)
   - Max tokens per task (number input)

4. **Codebase Index:**
   - Last indexed timestamp
   - "Re-index Now" button (calls context service via Gateway)
   - Indexed file count and chunk count

5. **Danger Zone:**
   - "Delete Project" button with confirmation modal (cascades all data)

**Behavior:**
- Load current settings via `apiClient.getProject(activeProjectId)`.
- Form state managed locally. "Save" button PATCHes the project.
- "Cancel" resets form to saved values.
- Toast notifications on save success/failure.

## Constraints
- Use controlled form inputs.
- Validate all fields before save (URL format, number ranges, etc.).
- The delete confirmation should require typing the project name.
- Total code ~250 lines.
```

</details>

---

## Dependency Graph

```
Phase 0 (Foundation) — all parallel, no inter-deps except M02→M01
  M01 ──→ M02
  M03 (parallel with M01)
  M04 (parallel with M01)
  M05 depends on M03 + M04

Phase 1 (Gateway) — starts after M02 + M05
  M06 ──→ M07 ──→ M09, M10
  M06 ──→ M08
  M06 ──→ M13 (after M03)
  M06 ──→ M12
  M09-M14 all parallel after M06+M07+M08

Phase 2 (Orchestrator) — starts after M01 + M03 + M04
  M15 ──→ M16 ──→ M17
  M16 ──→ M18, M19, M20, M21 (all parallel)
  M22, M23, M24, M25 (all parallel, after M01/M03)
  M26 (after M15)

Phase 3 (Sandbox) — starts after M03
  M27 ──→ M28 ──→ M29
  M30 (parallel, no deps)

Phase 4 (Context) — starts after M03 + M04
  M31 ──→ M32 ──→ M33 ──→ M34
  M31 ──→ M35 (after M33)

Phase 5 (CLI) — starts after Phase 1 Gateway endpoints
  M36 (after M06, M10, M12)
  M37 (after M09, M10)
  M38 (after M11, M14)

Phase 6 (UI) — starts after M02
  M39 ──→ M40 ──→ M41
  M42-M47 all parallel after M40+M41
```

## Module Summary

| Phase | Modules | Total Est. Lines | Notes |
|-------|---------|-----------------|-------|
| 0 — Foundation | M01-M05 | ~1,450 | No runtime code; types, schemas, infra |
| 1 — Gateway | M06-M14 | ~1,800 | TypeScript Fastify; 9 focused modules |
| 2 — Orchestrator | M15-M26 | ~3,070 | Python LangGraph; the largest phase |
| 3 — Sandbox | M27-M30 | ~930 | Docker isolation; 4 modules |
| 4 — Context | M31-M35 | ~1,250 | RAG pipeline; 5 modules |
| 5 — CLI | M36-M38 | ~900 | Typer + Rich; 3 modules |
| 6 — UI | M39-M47 | ~2,750 | React + Vite; 9 modules |
| **Total** | **47** | **~12,150** | **47 plans → 47 PRs** |