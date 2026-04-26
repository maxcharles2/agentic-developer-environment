import fp from "fastify-plugin";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const RATE_LIMIT_KEY_PREFIX = "ratelimit:";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function rateLimitKey(projectId: string, windowMinute: number): string {
  return `${RATE_LIMIT_KEY_PREFIX}${projectId}:${windowMinute}`;
}

/** Seconds remaining until the start of the next one-minute window. */
function secondsUntilNextMinute(): number {
  const now = Date.now();
  return Math.ceil((60_000 - (now % 60_000)) / 1000);
}

// ---------------------------------------------------------------------------
// Rate-limit plugin
// ---------------------------------------------------------------------------

async function plugin(fastify: FastifyInstance): Promise<void> {
  const limit =
    Number(process.env.RATE_LIMIT_PER_MINUTE) || 100;

  fastify.addHook(
    "onRequest",
    async (request: FastifyRequest, reply: FastifyReply) => {
      if (request.url === "/health") {
        return;
      }

      const projectId = request.user?.project_id;

      if (!projectId) {
        // Auth middleware will have already rejected the request; skip here.
        return;
      }

      const windowMinute = Math.floor(Date.now() / 60_000);
      const key = rateLimitKey(projectId, windowMinute);

      const count = await fastify.redis.incr(key);

      // Set TTL only on the first request of the window to avoid resetting it.
      if (count === 1) {
        await fastify.redis.expire(key, 60);
      }

      const remaining = Math.max(0, limit - count);
      const resetAt = windowMinute + 1; // Unix minute of the next window

      reply.header("X-RateLimit-Limit", String(limit));
      reply.header("X-RateLimit-Remaining", String(remaining));
      reply.header("X-RateLimit-Reset", String(resetAt * 60)); // Unix seconds

      if (count > limit) {
        const retryAfter = secondsUntilNextMinute();
        reply.header("Retry-After", String(retryAfter));
        return reply.code(429).send({
          error: "Rate limit exceeded",
          retry_after: retryAfter,
        });
      }
    },
  );
}

export const rateLimitPlugin = fp(plugin, {
  name: "rate-limit",
  fastify: "5.x",
  dependencies: ["auth"],
});

export default rateLimitPlugin;
