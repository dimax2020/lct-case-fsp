ALTER TABLE employers ADD COLUMN IF NOT EXISTS password_hash text;
ALTER TABLE candidates ADD COLUMN IF NOT EXISTS password_hash text;
