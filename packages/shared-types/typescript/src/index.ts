import { z } from "zod";

// ── Enums ────────────────────────────────────────────────────────────────────

export const TaskStatus = z.enum([
  "pending",
  "planning",
  "executing",
  "reviewing",
  "completed",
  "failed",
]);
export type TaskStatus = z.infer<typeof TaskStatus>;

export const StepStatus = z.enum([
  "pending",
  "in_progress",
  "completed",
  "failed",
  "skipped",
]);
export type StepStatus = z.infer<typeof StepStatus>;

export const AgentType = z.enum(["planner", "codegen", "executor", "context"]);
export type AgentType = z.infer<typeof AgentType>;

export const AgentRunStatus = z.enum([
  "running",
  "completed",
  "failed",
  "timeout",
]);
export type AgentRunStatus = z.infer<typeof AgentRunStatus>;

export const MessageRole = z.enum(["user", "assistant", "system", "tool"]);
export type MessageRole = z.infer<typeof MessageRole>;

export const WebSocketEventType = z.enum([
  "workflow.started",
  "step.started",
  "step.progress",
  "step.completed",
  "step.failed",
  "artifact.created",
  "execution.result",
  "workflow.completed",
  "workflow.error",
]);
export type WebSocketEventType = z.infer<typeof WebSocketEventType>;

// ── Object Schemas ────────────────────────────────────────────────────────────

export const TaskSchema = z
  .object({
    id: z.string().uuid(),
    project_id: z.string().uuid(),
    prompt: z.string(),
    status: TaskStatus,
    metadata: z.record(z.string(), z.unknown()).default({}),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
  })
  .strict();
export type Task = z.infer<typeof TaskSchema>;

export const TaskStepSchema = z
  .object({
    id: z.string().uuid(),
    task_id: z.string().uuid(),
    ordinal: z.number().int(),
    title: z.string(),
    description: z.string(),
    status: StepStatus,
    agent_type: AgentType,
    input_data: z.record(z.string(), z.unknown()).default({}),
    output_data: z.record(z.string(), z.unknown()).default({}),
    started_at: z.string().datetime().nullable().default(null),
    completed_at: z.string().datetime().nullable().default(null),
  })
  .strict();
export type TaskStep = z.infer<typeof TaskStepSchema>;

export const AgentRunSchema = z
  .object({
    id: z.string().uuid(),
    task_id: z.string().uuid(),
    step_id: z.string().uuid().nullable().default(null),
    agent_type: AgentType,
    model: z.string(),
    status: AgentRunStatus,
    input_state: z.record(z.string(), z.unknown()).default({}),
    output_state: z.record(z.string(), z.unknown()).default({}),
    tokens_in: z.number().int().nullable().default(null),
    tokens_out: z.number().int().nullable().default(null),
    latency_ms: z.number().int().nullable().default(null),
    retry_count: z.number().int().default(0),
    created_at: z.string().datetime(),
  })
  .strict();
export type AgentRun = z.infer<typeof AgentRunSchema>;

export const AgentMetricSchema = z
  .object({
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    agent_type: AgentType,
    metric_name: z.string(),
    metric_value: z.number(),
    labels: z.record(z.string(), z.unknown()).default({}),
    recorded_at: z.string().datetime(),
  })
  .strict();
export type AgentMetric = z.infer<typeof AgentMetricSchema>;

export const CodeArtifactSchema = z
  .object({
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    task_id: z.string().uuid(),
    file_path: z.string(),
    content: z.string(),
    diff: z.string().nullable().default(null),
    language: z.string(),
    version: z.number().int(),
    created_at: z.string().datetime(),
  })
  .strict();
export type CodeArtifact = z.infer<typeof CodeArtifactSchema>;

export const ExecutionResultSchema = z
  .object({
    id: z.string().uuid(),
    run_id: z.string().uuid(),
    task_id: z.string().uuid(),
    command: z.string(),
    stdout: z.string(),
    stderr: z.string(),
    exit_code: z.number().int(),
    duration_ms: z.number().int(),
    sandbox_id: z.string(),
    created_at: z.string().datetime(),
  })
  .strict();
export type ExecutionResult = z.infer<typeof ExecutionResultSchema>;

export const ProjectSchema = z
  .object({
    id: z.string().uuid(),
    name: z.string(),
    repo_url: z.string().nullable().default(null),
    repo_path: z.string().nullable().default(null),
    settings: z.record(z.string(), z.unknown()).default({}),
    created_at: z.string().datetime(),
    updated_at: z.string().datetime(),
  })
  .strict();
export type Project = z.infer<typeof ProjectSchema>;

export const ContextChunkSchema = z
  .object({
    id: z.string().uuid(),
    project_id: z.string().uuid(),
    file_path: z.string(),
    chunk_content: z.string(),
    embedding: z.array(z.number()).nullable().default(null),
    metadata: z.record(z.string(), z.unknown()).default({}),
    indexed_at: z.string().datetime(),
  })
  .strict();
export type ContextChunk = z.infer<typeof ContextChunkSchema>;

export const WorkflowEventSchema = z
  .object({
    event_type: z.string(),
    step_id: z.string().uuid().nullable().default(null),
    payload: z.record(z.string(), z.unknown()).default({}),
    timestamp: z.number().int(),
  })
  .strict();
export type WorkflowEvent = z.infer<typeof WorkflowEventSchema>;

export const ConversationMessageSchema = z
  .object({
    id: z.string().uuid(),
    task_id: z.string().uuid(),
    role: MessageRole,
    content: z.string(),
    metadata: z.record(z.string(), z.unknown()).default({}),
    created_at: z.string().datetime(),
  })
  .strict();
export type ConversationMessage = z.infer<typeof ConversationMessageSchema>;

// ── Request / Response Types ──────────────────────────────────────────────────

export const CreateTaskRequestSchema = z
  .object({
    project_id: z.string().uuid(),
    prompt: z.string(),
  })
  .strict();
export type CreateTaskRequest = z.infer<typeof CreateTaskRequestSchema>;

export const CreateTaskResponseSchema = z
  .object({
    task_id: z.string().uuid(),
    status: TaskStatus,
    ws_url: z.string(),
  })
  .strict();
export type CreateTaskResponse = z.infer<typeof CreateTaskResponseSchema>;

export const CreateProjectRequestSchema = z
  .object({
    name: z.string(),
    repo_url: z.string().nullable().optional(),
    repo_path: z.string().nullable().optional(),
    settings: z.record(z.string(), z.unknown()).optional(),
  })
  .strict();
export type CreateProjectRequest = z.infer<typeof CreateProjectRequestSchema>;
