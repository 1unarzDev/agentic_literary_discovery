-- Fleet view: latest worker self-report (heartbeat stats, whitelisted) and read-only viewer tokens.
ALTER TABLE workers ADD COLUMN stats_json TEXT;
CREATE TABLE viewer_tokens (
  token_sha256 TEXT PRIMARY KEY,
  name         TEXT NOT NULL,
  created      TEXT NOT NULL
);
