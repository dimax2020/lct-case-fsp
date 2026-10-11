ALTER TABLE candidates ADD COLUMN IF NOT EXISTS username text;
CREATE UNIQUE INDEX IF NOT EXISTS candidates_username_lower ON candidates (lower(username)) WHERE username IS NOT NULL;
