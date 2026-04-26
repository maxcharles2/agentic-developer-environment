import fp from "fastify-plugin";
import type { FastifyInstance } from "fastify";
import { z } from "zod";
import { createHash } from "crypto";

// ---------------------------------------------------------------------------
// Model pricing constants (USD per 1M tokens)
// ---------------------------------------------------------------------------

const MODEL_PRICING: Record<string, { input_per_1m: number; output_per_1m: number }> = {
  "gpt-4o":        { input_per_1m: 2.50,  output_per_1m: 10.00 },
  "gpt-4o-mini":   { input_per_1m: 0.15,  output_per_1m: 0.60  },
  "claude-sonnet": { input_per_1m: 3.00,  output_per_1m: 15.00 },
  "claude-opus":   { input_per_1m: 15.00, output_per_1m: 75.00 },
};

const DEFAULT_PRICING = { input_per_1m: 2.50, output_per_1m: 10.00 };

// ---------------------------------------------------------------------------
// Query param schema
// ---------------------------------------------------------------------------

const QuerySchema = z.object({
  project_id:  z.string().uuid({ message: "project_id must be a valid UUID" }),
  agent_type:  z.enum(["planner", "codegen", "executor", "context"]).optional(),
  from:        z.string().datetime({ offset: true }).optional(),
  to:          z.string().datetime({ offset: true }).optional(),
  granularity: z.enum(["hour", "day"]).default("day"),
});

type QueryParams = z.infer<typeof QuerySchema>;

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

type AgentRun = {
  task_id:    string;
  agent_type: string;
  model:      string;
  status:     string;
  tokens_in:  number;
  tokens_out: number;
  latency_ms: number;
  created_at: string;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function p95(values: number[]): number {
  if (values.length === 0) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.floor(0.95 * (sorted.length - 1))] ?? 0;
}

function estimateCost(model: string, tokensIn: number, tokensOut: number): number {
  const pricing = MODEL_PRICING[model] ?? DEFAULT_PRICING;
  return (tokensIn / 1_000_000) * pricing.input_per_1m + (tokensOut / 1_000_000) * pricing.output_per_1m;
}

function bucketKey(createdAt: string, granularity: "hour" | "day"): string {
  const iso = new Date(createdAt).toISOString();
  return granularity === "hour" ? iso.slice(0, 13) + ":00:00Z" : iso.slice(0, 10);
}

function buildCacheKey(projectId: string, params: QueryParams): string {
  const payload = JSON.stringify({
    agent_type:  params.agent_type ?? null,
    from:        params.from ?? null,
    to:          params.to ?? null,
    granularity: params.granularity,
  });
  const hash = createHash("sha256").update(payload).digest("hex").slice(0, 16);
  return `metrics:${projectId}:${hash}`;
}

// ---------------------------------------------------------------------------
// Plugin
// ---------------------------------------------------------------------------

async function plugin(fastify: FastifyInstance): Promise<void> {
  fastify.get<{ Querystring: Record<string, string> }>("/", async (request, reply) => {
    // 1. Validate query params
    const parsed = QuerySchema.safeParse(request.query);
    if (!parsed.success) {
      const message = parsed.error.issues.map((e) => e.message).join("; ");
      return reply.code(400).send({ error: message });
    }

    const params = parsed.data;
    const { project_id, agent_type, from, to, granularity } = params;

    // 2. Check Redis cache
    const cacheKey = buildCacheKey(project_id, params);
    try {
      const cached = await fastify.redis.get(cacheKey);
      if (cached) {
        return reply.code(200).send(JSON.parse(cached) as unknown);
      }
    } catch (redisErr) {
      request.log.warn({ redisErr }, "Redis cache read failed — proceeding to DB");
    }

    // 3. Fetch agent_runs joined through tasks for project scoping
    let query = fastify.supabase
      .from("agent_runs")
      .select(
        "task_id, agent_type, model, status, tokens_in, tokens_out, latency_ms, created_at, tasks!inner(project_id)",
      )
      .eq("tasks.project_id", project_id);

    if (agent_type) query = query.eq("agent_type", agent_type);
    if (from)       query = query.gte("created_at", from);
    if (to)         query = query.lte("created_at", to);

    const { data, error } = await query;

    if (error) {
      request.log.error({ error }, "Failed to fetch agent_runs for metrics");
      return reply.code(500).send({ error: "Failed to fetch metrics" });
    }

    const rows = (data ?? []) as AgentRun[];

    // 4. Aggregate — summary
    const total     = rows.length;
    const completed = rows.filter((r) => r.status === "completed").length;
    const failed    = rows.filter((r) => r.status === "failed").length;
    const sumIn     = rows.reduce((s, r) => s + r.tokens_in, 0);
    const sumOut    = rows.reduce((s, r) => s + r.tokens_out, 0);
    const latencies = rows.map((r) => r.latency_ms);
    const avgLatency = total > 0 ? latencies.reduce((s, v) => s + v, 0) / total : 0;
    const totalCost  = rows.reduce((s, r) => s + estimateCost(r.model, r.tokens_in, r.tokens_out), 0);

    // 4b. Aggregate — by agent type
    const agentMap = new Map<string, AgentRun[]>();
    for (const row of rows) {
      const bucket = agentMap.get(row.agent_type) ?? [];
      bucket.push(row);
      agentMap.set(row.agent_type, bucket);
    }

    const by_agent = Array.from(agentMap.entries()).map(([type, agentRows]) => {
      const agentLatencies = agentRows.map((r) => r.latency_ms);
      const agentTotal     = agentRows.length;
      const agentSumLat    = agentLatencies.reduce((s, v) => s + v, 0);
      return {
        agent_type:          type,
        total_runs:          agentTotal,
        completed:           agentRows.filter((r) => r.status === "completed").length,
        failed:              agentRows.filter((r) => r.status === "failed").length,
        tokens_in:           agentRows.reduce((s, r) => s + r.tokens_in, 0),
        tokens_out:          agentRows.reduce((s, r) => s + r.tokens_out, 0),
        avg_latency_ms:      parseFloat((agentTotal > 0 ? agentSumLat / agentTotal : 0).toFixed(2)),
        p95_latency_ms:      p95(agentLatencies),
        estimated_cost_usd:  parseFloat(
          agentRows.reduce((s, r) => s + estimateCost(r.model, r.tokens_in, r.tokens_out), 0).toFixed(6),
        ),
      };
    });

    // 4c. Aggregate — timeline
    const timelineMap = new Map<
      string,
      { runs: number; tokens_in: number; tokens_out: number; cost: number; latencies: number[] }
    >();

    for (const row of rows) {
      const bucket = bucketKey(row.created_at, granularity);
      const entry  = timelineMap.get(bucket) ?? { runs: 0, tokens_in: 0, tokens_out: 0, cost: 0, latencies: [] };
      entry.runs++;
      entry.tokens_in  += row.tokens_in;
      entry.tokens_out += row.tokens_out;
      entry.cost       += estimateCost(row.model, row.tokens_in, row.tokens_out);
      entry.latencies.push(row.latency_ms);
      timelineMap.set(bucket, entry);
    }

    const timeline = Array.from(timelineMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([period, entry]) => ({
        period,
        runs:               entry.runs,
        tokens_in:          entry.tokens_in,
        tokens_out:         entry.tokens_out,
        estimated_cost_usd: parseFloat(entry.cost.toFixed(6)),
        avg_latency_ms:     parseFloat(
          (entry.latencies.reduce((s, v) => s + v, 0) / entry.latencies.length).toFixed(2),
        ),
      }));

    // 5. Build response
    const result = {
      project_id,
      summary: {
        total_runs:         total,
        completed,
        failed,
        tokens_in:          sumIn,
        tokens_out:         sumOut,
        avg_latency_ms:     parseFloat(avgLatency.toFixed(2)),
        p95_latency_ms:     p95(latencies),
        estimated_cost_usd: parseFloat(totalCost.toFixed(6)),
      },
      by_agent,
      timeline,
    };

    // 6. Cache result with 60 s TTL
    try {
      await fastify.redis.set(cacheKey, JSON.stringify(result), "EX", 60);
    } catch (redisErr) {
      request.log.warn({ redisErr }, "Redis cache write failed");
    }

    return reply.code(200).send(result);
  });
}

export default fp(plugin, {
  name: "metrics-routes",
  fastify: "5.x",
});
