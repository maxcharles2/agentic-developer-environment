-- Migration 005: context_chunks table, IVFFlat + B-tree indexes, RLS
-- Requires: 001_projects.sql (vector extension + projects table)

-- ---------------------------------------------------------------------------
-- context_chunks
-- ---------------------------------------------------------------------------
CREATE TABLE context_chunks (
  id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id  UUID        NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  file_path   TEXT        NOT NULL,
  chunk_index INT         NOT NULL,
  content     TEXT        NOT NULL,
  embedding   vector(1536),
  metadata    JSONB       NOT NULL DEFAULT '{}',
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- IVFFlat index for approximate nearest-neighbour cosine similarity searches.
-- lists = 100 is a reasonable default for collections up to ~1 M rows;
-- tune upward (e.g. sqrt(n_rows)) as the dataset grows.
CREATE INDEX context_chunks_embedding_idx
  ON context_chunks
  USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

-- B-tree index to efficiently filter/sort chunks within a project by file path.
CREATE INDEX context_chunks_project_file_idx
  ON context_chunks (project_id, file_path);

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
ALTER TABLE context_chunks ENABLE ROW LEVEL SECURITY;

-- context_chunks owns project_id directly, so use the same direct-check
-- pattern as the projects and tasks tables.
CREATE POLICY "project_isolation" ON context_chunks
  USING (project_id = current_setting('app.current_project_id')::uuid);
