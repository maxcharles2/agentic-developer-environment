import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fp from "fastify-plugin";
import type { FastifyInstance, FastifyPluginAsync } from "fastify";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PROTO_DIR = path.resolve(__dirname, "../../../../packages/proto");

const LOADER_OPTIONS: protoLoader.Options = {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
};

// ---------------------------------------------------------------------------
// Error mapping
// ---------------------------------------------------------------------------

export interface GrpcErrorInfo {
  code: number;
  httpStatus: number;
  message: string;
}

const GRPC_TO_HTTP: Partial<Record<grpc.status, number>> = {
  [grpc.status.NOT_FOUND]: 404,
  [grpc.status.ALREADY_EXISTS]: 409,
  [grpc.status.INVALID_ARGUMENT]: 400,
  [grpc.status.PERMISSION_DENIED]: 403,
  [grpc.status.UNAUTHENTICATED]: 401,
  [grpc.status.RESOURCE_EXHAUSTED]: 429,
  [grpc.status.DEADLINE_EXCEEDED]: 504,
  [grpc.status.UNAVAILABLE]: 503,
  [grpc.status.UNIMPLEMENTED]: 501,
};

export function mapGrpcError(err: grpc.ServiceError): GrpcErrorInfo {
  const httpStatus =
    err.code !== undefined ? (GRPC_TO_HTTP[err.code] ?? 500) : 500;
  return { code: err.code ?? grpc.status.UNKNOWN, httpStatus, message: err.message };
}

// ---------------------------------------------------------------------------
// Shared call helpers
// ---------------------------------------------------------------------------

function callUnary<Req, Res>(
  stub: grpc.Client,
  method: string,
  request: Req,
  deadlineMs = 30_000,
  retriesLeft = 2,
): Promise<Res> {
  return new Promise<Res>((resolve, reject) => {
    const deadline = new Date(Date.now() + deadlineMs);
    ((stub as Record<string, unknown> & grpc.Client)[method] as (
      req: Req,
      metadata: grpc.Metadata,
      options: { deadline: Date },
      callback: (err: grpc.ServiceError | null, response: Res) => void,
    ) => void)(
      request,
      new grpc.Metadata(),
      { deadline },
      (err: grpc.ServiceError | null, response: Res) => {
        if (!err) return resolve(response);
        if (err.code === grpc.status.UNAVAILABLE && retriesLeft > 0) {
          const backoffMs = (3 - retriesLeft) * 500;
          setTimeout(() => {
            callUnary<Req, Res>(stub, method, request, deadlineMs, retriesLeft - 1)
              .then(resolve)
              .catch(reject);
          }, backoffMs);
        } else {
          reject(mapGrpcError(err));
        }
      },
    );
  });
}

async function* callServerStream<Req, Res>(
  stub: grpc.Client,
  method: string,
  request: Req,
  deadlineMs = 30_000,
): AsyncIterable<Res> {
  const deadline = new Date(Date.now() + deadlineMs);
  const call = ((stub as Record<string, unknown> & grpc.Client)[method] as (
    req: Req,
    metadata: grpc.Metadata,
    options: { deadline: Date },
  ) => grpc.ClientReadableStream<Res>)(
    request,
    new grpc.Metadata(),
    { deadline },
  );

  try {
    for await (const chunk of call) {
      yield chunk as Res;
    }
  } catch (err) {
    throw mapGrpcError(err as grpc.ServiceError);
  }
}

// ---------------------------------------------------------------------------
// Proto message types
// ---------------------------------------------------------------------------

export interface WorkflowRequest {
  task_id: string;
  project_id: string;
  prompt: string;
  metadata?: Record<string, string>;
}
export interface WorkflowEvent {
  event_type: string;
  step_id: string;
  payload: string;
  timestamp: string;
}
export interface WorkflowStatus {
  task_id: string;
  status: string;
  current_step: number;
  total_steps: number;
  current_agent: string;
}
export interface WorkflowId { id: string }
export interface OrchestratorAck { success: boolean; message: string }

export interface SandboxConfig {
  runtime: string;
  cpu_cores?: number;
  memory_mb?: number;
  timeout_s?: number;
}
export interface SandboxInfo { sandbox_id: string; status: string }
export interface SandboxId { id: string }
export interface ExecutionRequest {
  sandbox_id: string;
  command: string;
  code_path: string;
  env?: Record<string, string>;
}
export interface ExecutionResult {
  stdout: string;
  stderr: string;
  exit_code: number;
  duration_ms: string;
}
export interface SandboxAck { success: boolean; message: string }

export interface IndexRequest { project_id: string; repo_path: string; force_reindex?: boolean }
export interface IndexResult { chunks_indexed: number; files_processed: number; duration_s: number }
export interface ContextQuery { project_id: string; query: string; top_k?: number; threshold?: number }
export interface ContextChunk { id: string; file_path: string; content: string; score: number; metadata_json: string }
export interface ContextChunks { chunks: ContextChunk[] }
export interface WatchRequest { project_id: string; repo_path: string }
export interface ChangeEvent { file_path: string; change_type: string; timestamp: string }

// ---------------------------------------------------------------------------
// Client wrappers
// ---------------------------------------------------------------------------

export interface OrchestratorClient {
  runWorkflow(request: WorkflowRequest): AsyncIterable<WorkflowEvent>;
  getWorkflowStatus(taskId: string): Promise<WorkflowStatus>;
  cancelWorkflow(taskId: string): Promise<OrchestratorAck>;
  close(): void;
}

export interface SandboxClient {
  createSandbox(config: SandboxConfig): Promise<SandboxInfo>;
  execute(request: ExecutionRequest): Promise<ExecutionResult>;
  destroySandbox(sandboxId: string): Promise<SandboxAck>;
  close(): void;
}

export interface ContextClient {
  indexRepository(projectId: string, repoPath: string, forceReindex?: boolean): Promise<IndexResult>;
  retrieveContext(query: ContextQuery): Promise<ContextChunks>;
  watchChanges(request: WatchRequest): AsyncIterable<ChangeEvent>;
  close(): void;
}

function resolveServiceCtor(
  packageDef: protoLoader.PackageDefinition,
  ...namePath: string[]
): grpc.ServiceClientConstructor {
  const descriptor = grpc.loadPackageDefinition(packageDef);
  return namePath.reduce(
    (obj, key) => (obj as grpc.GrpcObject)[key] as grpc.GrpcObject,
    descriptor as grpc.GrpcObject,
  ) as unknown as grpc.ServiceClientConstructor;
}

function makeOrchestratorClient(address: string): OrchestratorClient {
  const def = protoLoader.loadSync(path.join(PROTO_DIR, "orchestrator.proto"), LOADER_OPTIONS);
  const Ctor = resolveServiceCtor(def, "ade", "orchestrator", "OrchestratorService");
  const stub = new Ctor(address, grpc.credentials.createInsecure()) as grpc.Client;

  return {
    runWorkflow(request) {
      return callServerStream<WorkflowRequest, WorkflowEvent>(stub, "RunWorkflow", request);
    },
    getWorkflowStatus(taskId) {
      return callUnary<WorkflowId, WorkflowStatus>(stub, "GetWorkflowStatus", { id: taskId });
    },
    cancelWorkflow(taskId) {
      return callUnary<WorkflowId, OrchestratorAck>(stub, "CancelWorkflow", { id: taskId });
    },
    close() { stub.close(); },
  };
}

function makeSandboxClient(address: string): SandboxClient {
  const def = protoLoader.loadSync(path.join(PROTO_DIR, "sandbox.proto"), LOADER_OPTIONS);
  const Ctor = resolveServiceCtor(def, "ade", "sandbox", "SandboxService");
  const stub = new Ctor(address, grpc.credentials.createInsecure()) as grpc.Client;

  return {
    createSandbox(config) {
      return callUnary<SandboxConfig, SandboxInfo>(stub, "CreateSandbox", config);
    },
    execute(request) {
      return callUnary<ExecutionRequest, ExecutionResult>(stub, "Execute", request);
    },
    destroySandbox(sandboxId) {
      return callUnary<SandboxId, SandboxAck>(stub, "DestroySandbox", { id: sandboxId });
    },
    close() { stub.close(); },
  };
}

function makeContextClient(address: string): ContextClient {
  const def = protoLoader.loadSync(path.join(PROTO_DIR, "context.proto"), LOADER_OPTIONS);
  const Ctor = resolveServiceCtor(def, "ade", "context", "ContextService");
  const stub = new Ctor(address, grpc.credentials.createInsecure()) as grpc.Client;

  return {
    indexRepository(projectId, repoPath, forceReindex = false) {
      return callUnary<IndexRequest, IndexResult>(stub, "IndexRepository", {
        project_id: projectId,
        repo_path: repoPath,
        force_reindex: forceReindex,
      });
    },
    retrieveContext(query) {
      return callUnary<ContextQuery, ContextChunks>(stub, "RetrieveContext", query);
    },
    watchChanges(request) {
      return callServerStream<WatchRequest, ChangeEvent>(stub, "WatchChanges", request);
    },
    close() { stub.close(); },
  };
}

// ---------------------------------------------------------------------------
// Fastify plugin
// ---------------------------------------------------------------------------

declare module "fastify" {
  interface FastifyInstance {
    orchestratorClient: OrchestratorClient;
    sandboxClient: SandboxClient;
    contextClient: ContextClient;
  }
}

interface GrpcClientPluginOptions {
  orchestratorUrl: string;
  sandboxUrl: string;
  contextUrl: string;
}

const grpcClientsPlugin: FastifyPluginAsync<GrpcClientPluginOptions> = async (
  fastify: FastifyInstance,
  opts: GrpcClientPluginOptions,
) => {
  const orchestratorClient = makeOrchestratorClient(opts.orchestratorUrl);
  const sandboxClient = makeSandboxClient(opts.sandboxUrl);
  const contextClient = makeContextClient(opts.contextUrl);

  fastify.decorate("orchestratorClient", orchestratorClient);
  fastify.decorate("sandboxClient", sandboxClient);
  fastify.decorate("contextClient", contextClient);

  fastify.addHook("onClose", (_instance, done) => {
    orchestratorClient.close();
    sandboxClient.close();
    contextClient.close();
    done();
  });
};

export default fp(grpcClientsPlugin, {
  name: "grpc-clients",
  fastify: "5.x",
});
