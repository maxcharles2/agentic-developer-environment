import Fastify from "fastify";
import authPlugin from "./middleware/auth.js";
import cors from "@fastify/cors";
import helmet from "@fastify/helmet";
import websocket from "@fastify/websocket";
import rateLimit from "@fastify/rate-limit";
import Redis from "ioredis";
import { createClient, SupabaseClient } from "@supabase/supabase-js";
import { z } from "zod";

// ---------------------------------------------------------------------------
// Env config — validated at startup; process exits on invalid input
// ---------------------------------------------------------------------------

const envSchema = z.object({
  GATEWAY_PORT: z.coerce.number().default(3000),
  REDIS_URL: z.string().default("redis://localhost:6379"),
  SUPABASE_URL: z.string(),
  SUPABASE_SERVICE_KEY: z.string(),
  ORCHESTRATOR_GRPC_URL: z.string().default("localhost:50051"),
  LOG_LEVEL: z
    .enum(["fatal", "error", "warn", "info", "debug", "trace"])
    .default("info"),
});

const config = envSchema.parse(process.env);

// ---------------------------------------------------------------------------
// Fastify type augmentation — type-safe access to shared clients in plugins
// ---------------------------------------------------------------------------

declare module "fastify" {
  interface FastifyInstance {
    redis: Redis;
    supabase: SupabaseClient;
  }
}

// ---------------------------------------------------------------------------
// Server factory
// ---------------------------------------------------------------------------

function buildServer() {
  const app = Fastify({
    logger: {
      level: config.LOG_LEVEL,
      transport:
        process.env.NODE_ENV !== "production"
          ? { target: "pino-pretty", options: { colorize: true } }
          : undefined,
    },
  });

  // -- Plugins ---------------------------------------------------------------

  app.register(helmet);

  app.register(cors, {
    origin: true,
    credentials: true,
  });

  app.register(websocket);

  app.register(rateLimit, {
    max: 100,
    timeWindow: "1 minute",
  });

  // -- Shared clients (decorated onto the Fastify instance) ------------------

  app.decorate("redis", new Redis(config.REDIS_URL));

  app.decorate(
    "supabase",
    createClient(config.SUPABASE_URL, config.SUPABASE_SERVICE_KEY, {
      auth: { persistSession: false },
    }),
  );

  // -- Health endpoint -------------------------------------------------------

  app.get("/health", async (_req, _reply) => {
    return { status: "ok", timestamp: new Date().toISOString() };
  });

  // -- Auth middleware --------------------------------------------------------
  app.register(authPlugin);

  // -- TODO: Register rate-limit middleware plugin ---------------------------
  // app.register(import("./plugins/rateLimit.js"));

  // -- TODO: Register route plugins ------------------------------------------
  // app.register(import("./routes/projects.js"), { prefix: "/api/v1/projects" });
  // app.register(import("./routes/tasks.js"),    { prefix: "/api/v1/tasks" });
  // app.register(import("./routes/artifacts.js"),{ prefix: "/api/v1/artifacts" });
  // app.register(import("./routes/metrics.js"),  { prefix: "/api/v1/metrics" });

  // -- TODO: Register WebSocket handler plugin --------------------------------
  // app.register(import("./plugins/ws.js"));

  // -- TODO: Initialize gRPC client (orchestrator service) -------------------
  // const grpcClient = createOrchestratorClient(config.ORCHESTRATOR_GRPC_URL);

  return app;
}

// ---------------------------------------------------------------------------
// Graceful shutdown
// ---------------------------------------------------------------------------

async function shutdown(
  app: ReturnType<typeof buildServer>,
  signal: string,
): Promise<void> {
  app.log.info({ signal }, "Received shutdown signal — closing server");

  try {
    await app.close();
    app.log.info("Fastify closed");
  } catch (err) {
    app.log.error({ err }, "Error while closing Fastify");
  }

  try {
    await app.redis.quit();
    app.log.info("Redis connection closed");
  } catch (err) {
    app.log.error({ err }, "Error while closing Redis");
  }

  process.exit(0);
}

// ---------------------------------------------------------------------------
// Entry point
// ---------------------------------------------------------------------------

async function start(): Promise<void> {
  const app = buildServer();

  process.once("SIGTERM", () => void shutdown(app, "SIGTERM"));
  process.once("SIGINT", () => void shutdown(app, "SIGINT"));

  try {
    await app.listen({ port: config.GATEWAY_PORT, host: "0.0.0.0" });
  } catch (err) {
    app.log.error({ err }, "Failed to start server");
    process.exit(1);
  }
}

void start();
