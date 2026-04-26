import fp from "fastify-plugin";
import type { FastifyInstance, FastifyRequest, FastifyReply } from "fastify";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  project_id: string;
}

declare module "fastify" {
  interface FastifyRequest {
    user?: AuthUser;
  }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const SESSION_KEY_PREFIX = "session:";
const SESSION_TTL_SECONDS = 86_400; // 24 h

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function sessionKey(apiKey: string): string {
  return `${SESSION_KEY_PREFIX}${apiKey}`;
}

// ---------------------------------------------------------------------------
// Auth plugin
// ---------------------------------------------------------------------------

async function plugin(fastify: FastifyInstance): Promise<void> {
  fastify.decorateRequest<AuthUser | undefined>("user", undefined);

  fastify.addHook(
    "onRequest",
    async (request: FastifyRequest, reply: FastifyReply) => {
      if (request.url === "/health") {
        return;
      }

      const authHeader = request.headers["authorization"];
      const apiKey = request.headers["x-api-key"];

      if (!authHeader && !apiKey) {
        return reply.code(401).send({ error: "Unauthorized" });
      }

      if (authHeader) {
        await handleBearer(fastify, request, reply, authHeader);
      } else {
        await handleApiKey(
          fastify,
          request,
          reply,
          apiKey as string,
        );
      }
    },
  );
}

async function handleBearer(
  fastify: FastifyInstance,
  request: FastifyRequest,
  reply: FastifyReply,
  authHeader: string,
): Promise<void> {
  const parts = authHeader.split(" ");
  if (parts.length !== 2 || parts[0].toLowerCase() !== "bearer") {
    return reply.code(401).send({ error: "Unauthorized" });
  }

  const token = parts[1];

  try {
    const { data, error } = await fastify.supabase.auth.getUser(token);

    if (error || !data.user) {
      request.log.warn({ userId: null }, "Bearer token verification failed");
      return reply.code(401).send({ error: "Unauthorized" });
    }

    const userId = data.user.id;
    const projectId = (data.user.app_metadata as Record<string, unknown>)
      ?.project_id as string | undefined;

    if (!projectId) {
      request.log.warn({ userId }, "Bearer token missing project_id in app_metadata");
      return reply.code(401).send({ error: "Unauthorized" });
    }

    request.user = { id: userId, project_id: projectId };
  } catch (err) {
    request.log.warn({ err }, "Unexpected error during bearer token verification");
    return reply.code(401).send({ error: "Unauthorized" });
  }
}

async function handleApiKey(
  fastify: FastifyInstance,
  request: FastifyRequest,
  reply: FastifyReply,
  apiKey: string,
): Promise<void> {
  try {
    // Check Redis cache first
    const cached = await fastify.redis.get(sessionKey(apiKey));

    if (cached) {
      const parsed = JSON.parse(cached) as AuthUser;
      request.user = parsed;
      return;
    }

    // Cache miss — query the projects table
    const { data, error } = await fastify.supabase
      .from("projects")
      .select("id, settings")
      .filter("settings->>api_key", "eq", apiKey)
      .single();

    if (error || !data) {
      request.log.warn({ projectId: null }, "API key lookup failed — not found");
      return reply.code(401).send({ error: "Unauthorized" });
    }

    const user: AuthUser = {
      id: (data.settings as Record<string, unknown>)?.owner_id as string ?? "",
      project_id: data.id as string,
    };

    // Write back to Redis with 24h TTL
    await fastify.redis.set(
      sessionKey(apiKey),
      JSON.stringify(user),
      "EX",
      SESSION_TTL_SECONDS,
    );

    request.user = user;
  } catch (err) {
    request.log.warn({ err }, "Unexpected error during API key verification");
    return reply.code(401).send({ error: "Unauthorized" });
  }
}

export const authPlugin = fp(plugin, {
  name: "auth",
  fastify: "5.x",
});

export default authPlugin;

// ---------------------------------------------------------------------------
// requireProject preHandler
// ---------------------------------------------------------------------------

export async function requireProject(
  request: FastifyRequest,
  reply: FastifyReply,
): Promise<void> {
  if (!request.user?.project_id) {
    return reply.code(403).send({ error: "Forbidden" });
  }
}
