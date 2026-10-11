ALTER TABLE practices ADD COLUMN IF NOT EXISTS vacancy_id text;
ALTER TABLE practices ADD COLUMN IF NOT EXISTS source_practice_id text;
CREATE INDEX IF NOT EXISTS practices_vacancy ON practices (vacancy_id) WHERE vacancy_id IS NOT NULL AND source_practice_id IS NULL;
CREATE INDEX IF NOT EXISTS practices_source ON practices (source_practice_id) WHERE source_practice_id IS NOT NULL;
