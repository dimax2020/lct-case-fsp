ALTER TABLE interview_questions ADD COLUMN shown_at timestamptz;
ALTER TABLE interview_answers ADD COLUMN duration_ms integer;
