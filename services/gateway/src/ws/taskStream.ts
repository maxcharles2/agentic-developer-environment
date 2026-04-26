import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { WorkflowEventSchema } from "@ade/shared-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isUUID(value: string): boolean {
  return UUID_RE.test(value);
}

function redisChannel(taskId: string): string {
  return `workflow:events:${taskId}`;
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

async function plugin(fastify: FastifyInstance): Promise<void> {
  fastify.get<{ Params: { id: string }; Querystring: { token?: string } }>(
    "/:id",
    { websocket: true },
    async (socket, request) => {
      const { id: taskId } = request.params;

      // -- UUID validation ---------------------------------------------------
      if (!isUUID(taskId)) {
        socket.close(4000, "Invalid task ID");
        return;
      }

      // -- Token-based auth (WS clients cannot set custom headers) -----------
      const token = request.query.token;
      if (!token) {
        socket.close(4001, "Unauthorized");
        return;
      }

      const { data: authData, error: authError } =
        await fastify.supabase.auth.getUser(token);

      if (authError || !authData.user) {
        request.log.warn({ taskId }, "WS auth failed — invalid token");
        socket.close(4001, "Unauthorized");
        return;
      }

      // -- Task existence check ----------------------------------------------
      const { error: taskError } = await fastify.supabase
        .from("tasks")
        .select("id")
        .eq("id", taskId)
        .single();

      if (taskError) {
        if (taskError.code === "PGRST116") {
          socket.close(4004, "Task not found");
        } else {
          request.log.error({ taskId, err: taskError }, "Task lookup error");
          socket.close(4000, "Internal error");
        }
        return;
      }

      request.log.info({ taskId, userId: authData.user.id }, "WS client connected");

      // -- Dedicated Redis subscriber ----------------------------------------
      // ioredis enters subscriber mode on subscribe(); a duplicate connection
      // is required so the main fastify.redis instance stays usable.
      const sub = fastify.redis.duplicate();
      const channel = redisChannel(taskId);
      let cleanedUp = false;

      function cleanup(): void {
        if (cleanedUp) return;
        cleanedUp = true;
        clearInterval(heartbeat);
        sub.unsubscribe(channel).catch(() => undefined);
        sub.quit().catch(() => undefined);
        request.log.info({ taskId }, "WS client disconnected — subscriber released");
      }

      // -- Heartbeat ---------------------------------------------------------
      const heartbeat = setInterval(() => {
        if (socket.readyState === socket.OPEN) {
          socket.send(JSON.stringify({ event_type: "heartbeat" }));
        }
      }, 30_000);

      // -- Subscribe to Redis channel ----------------------------------------
      await sub.subscribe(channel);

      // Notify client that the subscription is live
      socket.send(
        JSON.stringify({ event_type: "connection.established", task_id: taskId }),
      );

      sub.on("message", (_chan: string, message: string) => {
        if (socket.readyState !== socket.OPEN) return;

        let parsed: unknown;
        try {
          parsed = JSON.parse(message);
        } catch {
          request.log.debug({ taskId, message }, "WS: malformed Redis message — skipping");
          return;
        }

        const result = WorkflowEventSchema.safeParse(parsed);
        if (!result.success) {
          request.log.debug(
            { taskId, issues: result.error.issues },
            "WS: Redis message failed schema validation — skipping",
          );
          return;
        }

        socket.send(JSON.stringify({ ...result.data, received_at: Date.now() }));
      });

      sub.on("error", (err: Error) => {
        request.log.error({ taskId, err }, "WS: Redis subscriber error");
        if (socket.readyState === socket.OPEN) {
          socket.send(
            JSON.stringify({ event_type: "error", message: "Redis connection lost" }),
          );
          // Attempt resubscription after a transient error
          sub.subscribe(channel).catch((resubErr: unknown) => {
            request.log.error({ taskId, err: resubErr }, "WS: Redis resubscription failed");
          });
        }
      });

      // -- Incoming client messages ------------------------------------------
      socket.on("message", (raw: Buffer | string) => {
        let msg: unknown;
        try {
          msg = JSON.parse(raw.toString());
        } catch {
          request.log.debug({ taskId }, "WS: non-JSON client message — ignoring");
          return;
        }

        if (
          msg !== null &&
          typeof msg === "object" &&
          (msg as Record<string, unknown>).type === "ping"
        ) {
          socket.send(JSON.stringify({ type: "pong" }));
        } else {
          request.log.debug({ taskId, msg }, "WS: unrecognised client message — ignoring");
        }
      });

      // -- Socket lifecycle --------------------------------------------------
      socket.on("close", cleanup);
      socket.on("error", (err: Error) => {
        request.log.warn({ taskId, err }, "WS socket error");
        cleanup();
      });
    },
  );
}

export default fp(plugin, {
  name: "ws-task-stream",
  fastify: "5.x",
  dependencies: ["@fastify/websocket"],
});
