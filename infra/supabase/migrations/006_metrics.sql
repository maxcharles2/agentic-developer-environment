-- Migration 006: agent_metrics + workflow_checkpoints tables, indexes, RLS

-- ---------------------------------------------------------------------------
-- agent_metrics
-- ---------------------------------------------------------------------------
CREATE TABLE agent_metrics (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id       UUID        NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  metric_name  TEXT        NOT NULL,
  metric_value FLOAT       NOT NULL,
  labels       JSONB       NOT NULL DEFAULT '{}',
  recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON agent_metrics (run_id, metric_name);

-- ---------------------------------------------------------------------------
-- workflow_checkpoints
-- ---------------------------------------------------------------------------
CREATE TABLE workflow_checkpoints (
  id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id        UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  thread_id      TEXT        NOT NULL,
  step_number    INT         NOT NULL,
  state_snapshot JSONB       NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON workflow_checkpoints (task_id, thread_id, step_number);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE agent_metrics ENABLE ROW LEVEL SECURITY;

-- agent_metrics has no project_id column; join through agent_runs -> tasks instead.
CREATE POLICY "project_isolation" ON agent_metrics
  USING (
    EXISTS (
      SELECT 1 FROM agent_runs
        JOIN tasks ON tasks.id = agent_runs.task_id
       WHERE agent_runs.id = agent_metrics.run_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );

ALTER TABLE workflow_checkpoints ENABLE ROW LEVEL SECURITY;

-- workflow_checkpoints has no project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON workflow_checkpoints
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = workflow_checkpoints.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );
