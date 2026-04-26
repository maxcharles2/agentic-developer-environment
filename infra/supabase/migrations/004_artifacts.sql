-- Migration 004: code_artifacts + execution_results tables, indexes, RLS

-- ---------------------------------------------------------------------------
-- code_artifacts
-- ---------------------------------------------------------------------------
CREATE TABLE code_artifacts (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  run_id      UUID        NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  file_path   TEXT        NOT NULL,
  content     TEXT        NOT NULL,
  language    TEXT        NOT NULL,
  version     INT         NOT NULL DEFAULT 1,
  metadata    JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER code_artifacts_updated_at
  BEFORE UPDATE ON code_artifacts
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

CREATE INDEX ON code_artifacts (task_id, file_path);

-- ---------------------------------------------------------------------------
-- execution_results
-- ---------------------------------------------------------------------------
CREATE TABLE execution_results (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id     UUID        NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
  run_id      UUID        NOT NULL REFERENCES agent_runs(id) ON DELETE CASCADE,
  exit_code   INT         NOT NULL,
  stdout      TEXT        NOT NULL DEFAULT '',
  stderr      TEXT        NOT NULL DEFAULT '',
  duration_ms INT         NOT NULL DEFAULT 0,
  metadata    JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE code_artifacts ENABLE ROW LEVEL SECURITY;

-- code_artifacts has no project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON code_artifacts
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = code_artifacts.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );

ALTER TABLE execution_results ENABLE ROW LEVEL SECURITY;

-- execution_results has no project_id column; join through tasks instead.
CREATE POLICY "project_isolation" ON execution_results
  USING (
    EXISTS (
      SELECT 1 FROM tasks
       WHERE tasks.id = execution_results.task_id
         AND tasks.project_id = current_setting('app.current_project_id')::uuid
    )
  );
