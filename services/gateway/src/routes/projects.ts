import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { validateCreateProject, validateUpdateProject } from "../middleware/validation.js";
import type { CreateProjectRequest, UpdateProjectRequest } from "@ade/shared-types";

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
  // -- POST / — Create project -----------------------------------------------

  fastify.post<{ Body: CreateProjectRequest }>(
    "/",
    { preHandler: [validateCreateProject] },
    async (request, reply) => {
      const { name, repo_url, repo_path, settings } = request.body;

      const { data, error } = await fastify.supabase
        .from("projects")
        .insert({
          name,
          repo_url: repo_url ?? null,
          repo_path: repo_path ?? null,
          settings: settings ?? {},
        })
        .select()
        .single();

      if (error) {
        request.log.error({ error }, "Failed to create project");
        return reply.code(500).send({ error: "Failed to create project" });
      }

      return reply.code(201).send(data);
    },
  );

  // -- GET /:id — Get project by ID ------------------------------------------

  fastify.get<{ Params: { id: string } }>(
    "/:id",
    async (request, reply) => {
      const { id } = request.params;

      if (!isUUID(id)) {
        return reply.code(400).send({ error: "Invalid project ID — must be a UUID" });
      }

      const { data, error } = await fastify.supabase
        .from("projects")
        .select("*")
        .eq("id", id)
        .single();

      if (error) {
        if (error.code === "PGRST116") {
          return reply.code(404).send({ error: "Project not found" });
        }
        request.log.error({ error }, "Failed to fetch project");
        return reply.code(500).send({ error: "Failed to fetch project" });
      }

      return reply.code(200).send(data);
    },
  );

  // -- PATCH /:id — Update project -------------------------------------------

  fastify.patch<{ Params: { id: string }; Body: UpdateProjectRequest }>(
    "/:id",
    { preHandler: [validateUpdateProject] },
    async (request, reply) => {
      const { id } = request.params;

      if (!isUUID(id)) {
        return reply.code(400).send({ error: "Invalid project ID — must be a UUID" });
      }

      const { data, error } = await fastify.supabase
        .from("projects")
        .update(request.body)
        .eq("id", id)
        .select()
        .single();

      if (error) {
        if (error.code === "PGRST116") {
          return reply.code(404).send({ error: "Project not found" });
        }
        request.log.error({ error }, "Failed to update project");
        return reply.code(500).send({ error: "Failed to update project" });
      }

      return reply.code(200).send(data);
    },
  );

  // -- DELETE /:id — Delete project ------------------------------------------

  fastify.delete<{ Params: { id: string } }>(
    "/:id",
    async (request, reply) => {
      const { id } = request.params;

      if (!isUUID(id)) {
        return reply.code(400).send({ error: "Invalid project ID — must be a UUID" });
      }

      const { error } = await fastify.supabase
        .from("projects")
        .delete()
        .eq("id", id)
        .select("id")
        .single();

      if (error) {
        if (error.code === "PGRST116") {
          return reply.code(404).send({ error: "Project not found" });
        }
        request.log.error({ error }, "Failed to delete project");
        return reply.code(500).send({ error: "Failed to delete project" });
      }

      return reply.code(204).send();
    },
  );

  // -- GET / — List projects --------------------------------------------------

  fastify.get<{ Querystring: { limit?: string; offset?: string } }>(
    "/",
    async (request, reply) => {
      const rawLimit = parseInt(request.query.limit ?? "20", 10);
      const rawOffset = parseInt(request.query.offset ?? "0", 10);

      const limit = isNaN(rawLimit) || rawLimit < 1 ? 20 : Math.min(rawLimit, 100);
      const offset = isNaN(rawOffset) || rawOffset < 0 ? 0 : rawOffset;

      const { data, error, count } = await fastify.supabase
        .from("projects")
        .select("*", { count: "exact" })
        .range(offset, offset + limit - 1);

      if (error) {
        request.log.error({ error }, "Failed to list projects");
        return reply.code(500).send({ error: "Failed to list projects" });
      }

      return reply.code(200).send({ projects: data, total: count ?? 0 });
    },
  );
}

export default fp(plugin, {
  name: "projects-routes",
  fastify: "5.x",
});
