import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import type { CodeArtifact, ExecutionResult } from "@ade/shared-types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function isUUID(value: string): boolean {
  return UUID_RE.test(value);
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

async function plugin(fastify: FastifyInstance): Promise<void> {
  // -- GET /:id/artifacts — List artifacts for a task ------------------------

  fastify.get<{
    Params: { id: string };
    Querystring: {
      file_path?: string;
      version?: string;
      limit?: string;
      offset?: string;
    };
  }>("/:id/artifacts", async (request, reply) => {
    const { id } = request.params;

    if (!isUUID(id)) {
      return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
    }

    const rawLimit = parseInt(request.query.limit ?? "20", 10);
    const rawOffset = parseInt(request.query.offset ?? "0", 10);
    const limit = isNaN(rawLimit) || rawLimit < 1 ? 20 : Math.min(rawLimit, 100);
    const offset = isNaN(rawOffset) || rawOffset < 0 ? 0 : rawOffset;

    let query = fastify.supabase
      .from("code_artifacts")
      .select("*", { count: "exact" })
      .eq("task_id", id)
      .order("created_at", { ascending: false })
      .range(offset, offset + limit - 1);

    if (request.query.file_path) {
      query = query.eq("file_path", request.query.file_path);
    }

    if (request.query.version !== undefined) {
      const version = parseInt(request.query.version, 10);
      if (!isNaN(version)) {
        query = query.eq("version", version);
      }
    }

    const { data, error, count } = await query;

    if (error) {
      request.log.error({ error }, "Failed to list artifacts");
      return reply.code(500).send({ error: "Failed to list artifacts" });
    }

    return reply.code(200).send({
      artifacts: data as CodeArtifact[],
      total: count ?? 0,
    });
  });

  // -- GET /:id/artifacts/:artifactId — Single artifact ----------------------

  fastify.get<{
    Params: { id: string; artifactId: string };
  }>("/:id/artifacts/:artifactId", async (request, reply) => {
    const { id, artifactId } = request.params;

    if (!isUUID(id)) {
      return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
    }

    if (!isUUID(artifactId)) {
      return reply
        .code(400)
        .send({ error: "Invalid artifact ID — must be a UUID" });
    }

    const { data, error } = await fastify.supabase
      .from("code_artifacts")
      .select("*")
      .eq("id", artifactId)
      .eq("task_id", id)
      .single();

    if (error) {
      if (error.code === "PGRST116") {
        return reply.code(404).send({ error: "Artifact not found" });
      }
      request.log.error({ error }, "Failed to fetch artifact");
      return reply.code(500).send({ error: "Failed to fetch artifact" });
    }

    return reply.code(200).send(data as CodeArtifact);
  });

  // -- GET /:id/results — List execution results for a task ------------------

  fastify.get<{
    Params: { id: string };
    Querystring: {
      step_id?: string;
      limit?: string;
      offset?: string;
    };
  }>("/:id/results", async (request, reply) => {
    const { id } = request.params;

    if (!isUUID(id)) {
      return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
    }

    const rawLimit = parseInt(request.query.limit ?? "20", 10);
    const rawOffset = parseInt(request.query.offset ?? "0", 10);
    const limit = isNaN(rawLimit) || rawLimit < 1 ? 20 : Math.min(rawLimit, 100);
    const offset = isNaN(rawOffset) || rawOffset < 0 ? 0 : rawOffset;

    const { step_id } = request.query;

    // execution_results links to agent_runs via run_id; agent_runs has step_id.
    // If a step_id filter is requested, resolve the matching run_ids first.
    let runIdFilter: string[] | null = null;

    if (step_id !== undefined) {
      if (!isUUID(step_id)) {
        return reply
          .code(400)
          .send({ error: "Invalid step_id — must be a UUID" });
      }

      const { data: runs, error: runsError } = await fastify.supabase
        .from("agent_runs")
        .select("id")
        .eq("task_id", id)
        .eq("step_id", step_id);

      if (runsError) {
        request.log.error({ runsError }, "Failed to resolve agent runs for step");
        return reply.code(500).send({ error: "Failed to list results" });
      }

      runIdFilter = (runs ?? []).map((r: { id: string }) => r.id);

      // If no runs matched, return an empty result set immediately.
      if (runIdFilter.length === 0) {
        return reply.code(200).send({ results: [], total: 0 });
      }
    }

    let query = fastify.supabase
      .from("execution_results")
      .select("*", { count: "exact" })
      .eq("task_id", id)
      .order("created_at", { ascending: false })
      .range(offset, offset + limit - 1);

    if (runIdFilter !== null) {
      query = query.in("run_id", runIdFilter);
    }

    const { data, error, count } = await query;

    if (error) {
      request.log.error({ error }, "Failed to list results");
      return reply.code(500).send({ error: "Failed to list results" });
    }

    return reply.code(200).send({
      results: data as ExecutionResult[],
      total: count ?? 0,
    });
  });

  // -- GET /:id/results/:resultId — Single execution result ------------------

  fastify.get<{
    Params: { id: string; resultId: string };
  }>("/:id/results/:resultId", async (request, reply) => {
    const { id, resultId } = request.params;

    if (!isUUID(id)) {
      return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
    }

    if (!isUUID(resultId)) {
      return reply
        .code(400)
        .send({ error: "Invalid result ID — must be a UUID" });
    }

    const { data, error } = await fastify.supabase
      .from("execution_results")
      .select("*")
      .eq("id", resultId)
      .eq("task_id", id)
      .single();

    if (error) {
      if (error.code === "PGRST116") {
        return reply.code(404).send({ error: "Result not found" });
      }
      request.log.error({ error }, "Failed to fetch result");
      return reply.code(500).send({ error: "Failed to fetch result" });
    }

    return reply.code(200).send(data as ExecutionResult);
  });
}

export default fp(plugin, {
  name: "artifacts-routes",
  fastify: "5.x",
});
