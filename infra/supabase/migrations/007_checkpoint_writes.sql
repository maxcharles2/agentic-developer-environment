-- Migration 007: add checkpoint_ns to workflow_checkpoints + create checkpoint_writes table

-- ---------------------------------------------------------------------------
-- workflow_checkpoints: add checkpoint_ns column + replace index
-- ---------------------------------------------------------------------------
ALTER TABLE workflow_checkpoints
  ADD COLUMN checkpoint_ns TEXT NOT NULL DEFAULT '';

DROP INDEX IF EXISTS workflow_checkpoints_task_id_thread_id_step_number_idx;

CREATE INDEX ON workflow_checkpoints (thread_id, checkpoint_ns, step_number DESC);

-- ---------------------------------------------------------------------------
-- checkpoint_writes
-- ---------------------------------------------------------------------------
CREATE TABLE checkpoint_writes (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  checkpoint_id UUID        NOT NULL REFERENCES workflow_checkpoints(id) ON DELETE CASCADE,
  task_id       TEXT        NOT NULL,
  task_path     TEXT        NOT NULL DEFAULT '',
  channel       TEXT        NOT NULL,
  value         JSONB       NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON checkpoint_writes (checkpoint_id);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE checkpoint_writes ENABLE ROW LEVEL SECURITY;

-- checkpoint_writes has no project_id column; join through workflow_checkpoints -> tasks instead.
CREATE POLICY "project_isolation" ON checkpoint_writes
  USING (
    EXISTS (
      SELECT 1 FROM workflow_checkpoints
        JOIN tasks ON tasks.id = workflow_checkpoints.task_id
       WHERE workflow_checkpoints.id = checkpoint_writes.checkpoint_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );
