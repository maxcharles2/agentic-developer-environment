-- Migration 002: tasks + task_steps tables, triggers, RLS

-- ---------------------------------------------------------------------------
-- tasks
-- ---------------------------------------------------------------------------
CREATE TABLE tasks (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  prompt      TEXT        NOT NULL,
  status      TEXT        NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending','planning','executing','reviewing','completed','failed')),
  metadata    JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER tasks_updated_at
  BEFORE UPDATE ON tasks
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------------
-- task_steps
-- ---------------------------------------------------------------------------
CREATE TABLE task_steps (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id      UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  ordinal      INT         NOT NULL,
  title        TEXT        NOT NULL,
  description  TEXT,
  status       TEXT        NOT NULL DEFAULT 'pending'
                 CHECK (status IN ('pending','in_progress','completed','failed','skipped')),
  agent_type   TEXT        NOT NULL
                 CHECK (agent_type IN ('planner','codegen','executor','context')),
  input_data   JSONB       NOT NULL DEFAULT '{}',
  output_data  JSONB       NOT NULL DEFAULT '{}',
  started_at   TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (task_id, ordinal)
);

CREATE TRIGGER task_steps_updated_at
  BEFORE UPDATE ON task_steps
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE tasks ENABLE ROW LEVEL SECURITY;

-- tasks owns project_id directly — compare it to the session variable.
CREATE POLICY "project_isolation" ON tasks
  USING (project_id = current_setting('app.current_project_id')::uuid);

ALTER TABLE task_steps ENABLE ROW LEVEL SECURITY;

-- task_steps does not have a project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON task_steps
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = task_steps.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );
