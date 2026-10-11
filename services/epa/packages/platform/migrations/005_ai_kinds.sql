ALTER TABLE ai_analyses ALTER COLUMN submission_id DROP NOT NULL;
ALTER TABLE ai_analyses ADD COLUMN IF NOT EXISTS kind text NOT NULL DEFAULT 'submission';
