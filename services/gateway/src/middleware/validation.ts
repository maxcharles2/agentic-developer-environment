import type { FastifyRequest, FastifyReply, preHandlerHookHandler } from "fastify";
import {
  CreateTaskRequestSchema,
  CreateProjectRequestSchema,
} from "@ade/shared-types";

// ---------------------------------------------------------------------------
// Minimal structural type compatible with both Zod v3 and v4
// ---------------------------------------------------------------------------

interface SafeParseableSchema<T> {
  safeParse(
    data: unknown,
  ):
    | { success: true; data: T }
    | { success: false; error: { issues: unknown[] } };
}

// ---------------------------------------------------------------------------
// Generic factory
// ---------------------------------------------------------------------------

export function createValidator<T>(
  zodSchema: SafeParseableSchema<T>,
): preHandlerHookHandler {
  return async function validate(
    request: FastifyRequest,
    reply: FastifyReply,
  ): Promise<void> {
    const result = zodSchema.safeParse(request.body);

    if (!result.success) {
      return reply.code(400).send({
        error: "Validation error",
        details: result.error.issues,
      });
    }

    // Replace body with the parsed (coerced + stripped) value.
    (request as FastifyRequest & { body: T }).body = result.data;
  };
}

// ---------------------------------------------------------------------------
// Pre-built validators
// ---------------------------------------------------------------------------

export const validateCreateTask = createValidator(CreateTaskRequestSchema);

export const validateCreateProject = createValidator(CreateProjectRequestSchema);
