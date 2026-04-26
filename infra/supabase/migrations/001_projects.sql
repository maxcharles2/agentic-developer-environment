-- Migration 001: projects table, updated_at trigger, RLS
-- pgvector is needed by 005_context.sql but is safe to enable here

CREATE EXTENSION IF NOT EXISTS vector;

-- Reusable trigger function: keeps updated_at current on any row change.
-- Defined once here so all subsequent migrations can attach it without
-- redefining it (CREATE OR REPLACE is idempotent).
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ---------------------------------------------------------------------------
-- projects
-- ---------------------------------------------------------------------------
CREATE TABLE projects (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT        NOT NULL,
  repo_url    TEXT,
  repo_path   TEXT,
  settings    JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TRIGGER projects_updated_at
  BEFORE UPDATE ON projects
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at();

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE projects ENABLE ROW LEVEL SECURITY;

-- Rows are visible / mutable only when the session variable matches the row id.
-- Application code must call:  SET LOCAL app.current_project_id = '<uuid>';
-- before any query against this table.
CREATE POLICY "project_isolation" ON projects
  USING (id = current_setting('app.current_project_id')::uuid);
