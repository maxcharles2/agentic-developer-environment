import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { validateCreateTask, validateApproveStep } from "../middleware/validation.js";
import { createOrchestratorClient } from "../grpc/orchestratorClient.js";
import type { CreateTaskRequest, ApproveStepRequest } from "@ade/shared-types";

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
  const orchestrator = createOrchestratorClient(
    process.env.ORCHESTRATOR_GRPC_URL ?? "localhost:50051",
  );

  // -- POST / — Submit task --------------------------------------------------

  fastify.post<{ Body: CreateTaskRequest }>(
    "/",
    { preHandler: [validateCreateTask] },
    async (request, reply) => {
      const { project_id, prompt } = request.body;

      const { data, error } = await fastify.supabase
        .from("tasks")
        .insert({ project_id, prompt, status: "pending" })
        .select()
        .single();

      if (error) {
        request.log.error({ error }, "Failed to create task");
        return reply.code(500).send({ error: "Failed to create task" });
      }

      const task_id: string = data.id as string;

      const stream = orchestrator.runWorkflow({ task_id, project_id, prompt });
      const response: {
        task_id: string;
        status: string;
        ws_url: string;
        warning?: string;
      } = {
        task_id,
        status: "pending",
        ws_url: `/ws/tasks/${task_id}`,
      };

      if (stream === null) {
        request.log.warn({ task_id }, "Orchestrator unavailable — task queued");
        response.warning = "Orchestrator unavailable — task queued";
      }

      return reply.code(202).send(response);
    },
  );

  // -- GET / — List tasks ----------------------------------------------------

  fastify.get<{
    Querystring: {
      project_id: string;
      status?: string;
      limit?: string;
      offset?: string;
    };
  }>("/", async (request, reply) => {
    const { project_id, status } = request.query;

    if (!project_id) {
      return reply.code(400).send({ error: "Missing required query param: project_id" });
    }

    if (!isUUID(project_id)) {
      return reply.code(400).send({ error: "Invalid project_id — must be a UUID" });
    }

    const rawLimit = parseInt(request.query.limit ?? "20", 10);
    const rawOffset = parseInt(request.query.offset ?? "0", 10);
    const limit = isNaN(rawLimit) || rawLimit < 1 ? 20 : Math.min(rawLimit, 100);
    const offset = isNaN(rawOffset) || rawOffset < 0 ? 0 : rawOffset;

    let query = fastify.supabase
      .from("tasks")
      .select("*", { count: "exact" })
      .eq("project_id", project_id)
      .order("created_at", { ascending: false })
      .range(offset, offset + limit - 1);

    if (status) {
      query = query.eq("status", status);
    }

    const { data, error, count } = await query;

    if (error) {
      request.log.error({ error }, "Failed to list tasks");
      return reply.code(500).send({ error: "Failed to list tasks" });
    }

    return reply.code(200).send({ tasks: data, total: count ?? 0 });
  });

  // -- GET /:id — Get task by ID ---------------------------------------------

  fastify.get<{ Params: { id: string } }>("/:id", async (request, reply) => {
    const { id } = request.params;

    if (!isUUID(id)) {
      return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
    }

    const { data, error } = await fastify.supabase
      .from("tasks")
      .select("*")
      .eq("id", id)
      .single();

    if (error) {
      if (error.code === "PGRST116") {
        return reply.code(404).send({ error: "Task not found" });
      }
      request.log.error({ error }, "Failed to fetch task");
      return reply.code(500).send({ error: "Failed to fetch task" });
    }

    return reply.code(200).send(data);
  });

  // -- GET /:id/steps — List task steps --------------------------------------

  fastify.get<{ Params: { id: string } }>(
    "/:id/steps",
    async (request, reply) => {
      const { id } = request.params;

      if (!isUUID(id)) {
        return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
      }

      const { data, error } = await fastify.supabase
        .from("task_steps")
        .select("*")
        .eq("task_id", id)
        .order("ordinal", { ascending: true });

      if (error) {
        request.log.error({ error }, "Failed to fetch task steps");
        return reply.code(500).send({ error: "Failed to fetch task steps" });
      }

      return reply.code(200).send({ steps: data });
    },
  );

  // -- POST /:id/steps/:stepId/approve — Approve or reject a step ------------

  fastify.post<{
    Params: { id: string; stepId: string };
    Body: ApproveStepRequest;
  }>(
    "/:id/steps/:stepId/approve",
    { preHandler: [validateApproveStep] },
    async (request, reply) => {
      const { id, stepId } = request.params;

      if (!isUUID(id)) {
        return reply.code(400).send({ error: "Invalid task ID — must be a UUID" });
      }

      if (!isUUID(stepId)) {
        return reply.code(400).send({ error: "Invalid step ID — must be a UUID" });
      }

      const { data: step, error: fetchError } = await fastify.supabase
        .from("task_steps")
        .select("*")
        .eq("id", stepId)
        .eq("task_id", id)
        .single();

      if (fetchError) {
        if (fetchError.code === "PGRST116") {
          return reply.code(404).send({ error: "Step not found" });
        }
        request.log.error({ fetchError }, "Failed to fetch step");
        return reply.code(500).send({ error: "Failed to fetch step" });
      }

      const currentStatus = step.status as string;
      if (currentStatus !== "pending" && currentStatus !== "in_progress") {
        return reply.code(409).send({
          error: `Step cannot be approved — current status is "${currentStatus}"`,
        });
      }

      const { approved, feedback } = request.body;
      const newStatus = approved ? "completed" : "skipped";

      const { data: updated, error: updateError } = await fastify.supabase
        .from("task_steps")
        .update({ status: newStatus })
        .eq("id", stepId)
        .select()
        .single();

      if (updateError) {
        request.log.error({ updateError }, "Failed to update step");
        return reply.code(500).send({ error: "Failed to update step" });
      }

      const eventType = approved ? "step.approved" : "step.rejected";
      const channel = `workflow:events:${id}`;
      const event = JSON.stringify({
        event_type: eventType,
        step_id: stepId,
        payload: { approved, ...(feedback !== undefined && { feedback }) },
        timestamp: Date.now(),
      });

      try {
        await fastify.redis.publish(channel, event);
      } catch (redisErr) {
        request.log.warn({ redisErr, channel }, "Failed to publish step event to Redis");
      }

      return reply.code(200).send(updated);
    },
  );
}

export default fp(plugin, {
  name: "tasks-routes",
  fastify: "5.x",
});
