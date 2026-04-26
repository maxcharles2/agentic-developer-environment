-- Migration 003: agent_runs + conversations tables, index, RLS

-- ---------------------------------------------------------------------------
-- agent_runs
-- ---------------------------------------------------------------------------
CREATE TABLE agent_runs (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id      UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  step_id      UUID        NOT NULL REFERENCES task_steps(id) ON DELETE CASCADE,
  agent_type   TEXT        NOT NULL,
  model        TEXT        NOT NULL,
  status       TEXT        NOT NULL DEFAULT 'running'
                 CHECK (status IN ('running','completed','failed','timeout')),
  input_state  JSONB       NOT NULL DEFAULT '{}',
  output_state JSONB       NOT NULL DEFAULT '{}',
  tokens_in    INT         NOT NULL DEFAULT 0,
  tokens_out   INT         NOT NULL DEFAULT 0,
  latency_ms   INT         NOT NULL DEFAULT 0,
  retry_count  INT         NOT NULL DEFAULT 0,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX ON agent_runs (task_id, created_at);

-- ---------------------------------------------------------------------------
-- conversations
-- ---------------------------------------------------------------------------
CREATE TABLE conversations (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id    UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  role       TEXT        NOT NULL
               CHECK (role IN ('user','assistant','system','tool')),
  content    TEXT        NOT NULL,
  metadata   JSONB       NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE agent_runs ENABLE ROW LEVEL SECURITY;

-- agent_runs has no project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON agent_runs
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = agent_runs.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );

ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;

-- conversations has no project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON conversations
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = conversations.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );
