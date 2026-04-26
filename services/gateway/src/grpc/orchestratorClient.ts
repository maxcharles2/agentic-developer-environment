import * as grpc from "@grpc/grpc-js";
import * as protoLoader from "@grpc/proto-loader";
import { fileURLToPath } from "node:url";
import path from "node:path";

// ---------------------------------------------------------------------------
// Proto loading — resolved relative to this file so it works regardless of
// the process CWD (dev server, compiled dist, Docker, etc.)
// ---------------------------------------------------------------------------

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const PROTO_PATH = path.resolve(
  __dirname,
  "../../../../packages/proto/orchestrator.proto",
);

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface WorkflowRequest {
  task_id: string;
  project_id: string;
  prompt: string;
  metadata?: Record<string, string>;
}

/** Thin interface over the dynamically-loaded gRPC stub. */
interface OrchestratorStub {
  RunWorkflow(
    request: WorkflowRequest,
    metadata?: grpc.Metadata,
  ): grpc.ClientReadableStream<unknown>;
}

export interface OrchestratorClient {
  /**
   * Fire-and-forget call to RunWorkflow.
   *
   * Returns the server-streaming call object so callers can optionally
   * attach listeners, but callers are not required to await or consume it.
   * Returns `null` if the initial gRPC call throws (e.g. orchestrator down);
   * the task row is already persisted so the work is not lost.
   */
  runWorkflow(req: WorkflowRequest): grpc.ClientReadableStream<unknown> | null;

  /** Close the underlying gRPC channel. */
  close(): void;
}

// ---------------------------------------------------------------------------
// Factory
// ---------------------------------------------------------------------------

export function createOrchestratorClient(address: string): OrchestratorClient {
  const descriptor = grpc.loadPackageDefinition(packageDefinition);

  // Navigate the nested proto namespace: ade.orchestrator.OrchestratorService
  const OrchestratorServiceCtor = (
    (descriptor["ade"] as grpc.GrpcObject)[
      "orchestrator"
    ] as grpc.GrpcObject
  )["OrchestratorService"] as grpc.ServiceClientConstructor;

  const stub = new OrchestratorServiceCtor(
    address,
    grpc.credentials.createInsecure(),
  ) as unknown as OrchestratorStub;

  return {
    runWorkflow(req: WorkflowRequest): grpc.ClientReadableStream<unknown> | null {
      try {
        return stub.RunWorkflow(req);
      } catch {
        return null;
      }
    },

    close(): void {
      (stub as unknown as grpc.Client).close();
    },
  };
}
