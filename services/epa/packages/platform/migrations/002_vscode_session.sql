-- Existing databases created before the VS Code client need the new session client
-- and a presence timestamp. Fresh installs already have both from 001; these statements are idempotent.
ALTER TABLE dev_sessions DROP CONSTRAINT IF EXISTS dev_sessions_client_check;
ALTER TABLE dev_sessions ADD CONSTRAINT dev_sessions_client_check CHECK (client IN ('gateway', 'sidecar', 'platform', 'vscode'));
ALTER TABLE dev_sessions ADD COLUMN IF NOT EXISTS last_seen_at timestamptz;
