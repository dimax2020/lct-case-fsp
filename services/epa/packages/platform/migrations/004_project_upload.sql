ALTER TABLE practices ADD COLUMN IF NOT EXISTS brief text;
ALTER TABLE practices ADD COLUMN IF NOT EXISTS project_source text NOT NULL DEFAULT 'template';
