-- Seed data for local development / CI
-- Uses fixed UUIDs so foreign-key references are stable across re-seeds.

-- ---------------------------------------------------------------------------
-- Project
-- ---------------------------------------------------------------------------
INSERT INTO projects (id, name, repo_path, settings)
VALUES (
  'a0000000-0000-0000-0000-000000000001',
  'Demo Project',
  '/tmp/demo',
  '{}'
);

-- ---------------------------------------------------------------------------
-- Task
-- ---------------------------------------------------------------------------
INSERT INTO tasks (id, project_id, prompt, status)
VALUES (
  'b0000000-0000-0000-0000-000000000001',
  'a0000000-0000-0000-0000-000000000001',
  'Build a hello world endpoint',
  'pending'
);

-- ---------------------------------------------------------------------------
-- Task steps  (ordinals 1-3)
-- ---------------------------------------------------------------------------
INSERT INTO task_steps (task_id, ordinal, title, agent_type)
VALUES
  (
    'b0000000-0000-0000-0000-000000000001',
    1,
    'Plan the endpoint',
    'planner'
  ),
  (
    'b0000000-0000-0000-0000-000000000001',
    2,
    'Generate code',
    'codegen'
  ),
  (
    'b0000000-0000-0000-0000-000000000001',
    3,
    'Run tests',
    'executor'
  );
