-- ALD coordinator schema v1.
-- Timestamps: *_at / created columns are ISO-8601 UTC strings produced by
-- Date.prototype.toISOString() (lexicographically sortable); lease_expires and
-- leased_at_ms are epoch milliseconds (integers) because the lease logic does
-- arithmetic on them.

-- Key/value configuration (client release, registry version/etag, ...).
CREATE TABLE config (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE workers (
  id             TEXT PRIMARY KEY,
  token_sha256   TEXT NOT NULL UNIQUE,
  name           TEXT NOT NULL,
  os             TEXT,
  arch           TEXT,
  gpu            TEXT,
  vram_gb        REAL,
  ram_gb         REAL,
  tier           TEXT,
  client_version TEXT,
  created        TEXT NOT NULL,
  last_seen      TEXT,
  tok_s          REAL,
  passages_done  INTEGER,
  disabled       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE invites (
  code_sha256 TEXT PRIMARY KEY,
  created     TEXT NOT NULL,
  used_by     TEXT REFERENCES workers(id),
  used_at     TEXT
);

CREATE TABLE pins (
  pin_hash     TEXT PRIMARY KEY,
  stage        TEXT NOT NULL CHECK (stage IN ('screen','label','adjudicate','cloze','embed')),
  model_ref    TEXT NOT NULL,
  model_digest TEXT NOT NULL,
  prompt_hash  TEXT NOT NULL,
  schema_hash  TEXT NOT NULL,
  options_json TEXT NOT NULL,
  active       INTEGER NOT NULL DEFAULT 1,
  created      TEXT NOT NULL
);

CREATE TABLE shards (
  shard_key      TEXT PRIMARY KEY,           -- R2 key: shards/<wave>/<shard_id>.jsonl.gz
  wave           TEXT NOT NULL,
  shard_id       TEXT NOT NULL,
  split          TEXT NOT NULL CHECK (split IN ('discovery','confirmation')),
  n_passages     INTEGER NOT NULL,
  decades        TEXT,                       -- CSV as uploaded
  content_sha256 TEXT NOT NULL,
  size           INTEGER NOT NULL,
  created        TEXT NOT NULL
);

-- One row per (shard, pin). Lease state lives on the row (current holder);
-- the full lease history is in `leases`.
CREATE TABLE jobs (
  job_id        TEXT PRIMARY KEY,
  stage         TEXT NOT NULL CHECK (stage IN ('screen','label','adjudicate','cloze','embed')),
  wave          TEXT NOT NULL,
  shard_key     TEXT NOT NULL,
  pin_hash      TEXT NOT NULL REFERENCES pins(pin_hash),
  n_passages    INTEGER NOT NULL,
  split         TEXT NOT NULL CHECK (split IN ('discovery','confirmation')),
  dup_group     TEXT,
  priority      INTEGER NOT NULL DEFAULT 100,   -- lower = served first
  cell          TEXT,                           -- optional sampling cell label (for /v1/status)
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','leased','done','dead','closed')),
  attempt       INTEGER NOT NULL DEFAULT 0,
  lease_worker  TEXT,
  lease_expires INTEGER,                        -- epoch ms
  leased_at_ms  INTEGER,
  done_at       TEXT,
  done_by       TEXT,                           -- worker id, or 'partials'
  created       TEXT NOT NULL
);
-- The lease query: status + stage filter, priority order.
CREATE INDEX jobs_lease_idx   ON jobs(status, stage, priority);
-- The reclaim query.
CREATE INDEX jobs_expiry_idx  ON jobs(status, lease_expires);
CREATE INDEX jobs_dup_idx     ON jobs(dup_group) WHERE dup_group IS NOT NULL;
CREATE INDEX jobs_holder_idx  ON jobs(lease_worker) WHERE lease_worker IS NOT NULL;

-- Lease history: one row per (job, worker, attempt). Written by trigger so it
-- is atomic with the lease UPDATE.
CREATE TABLE leases (
  job_id       TEXT NOT NULL,
  worker_id    TEXT NOT NULL,
  attempt      INTEGER NOT NULL,
  leased_at_ms INTEGER NOT NULL,
  PRIMARY KEY (job_id, worker_id, attempt)
);
CREATE INDEX leases_worker_idx ON leases(worker_id, job_id);

CREATE TRIGGER jobs_lease_log AFTER UPDATE OF status ON jobs
WHEN NEW.status = 'leased' AND NEW.lease_worker IS NOT NULL
BEGIN
  INSERT OR IGNORE INTO leases(job_id, worker_id, attempt, leased_at_ms)
  VALUES (NEW.job_id, NEW.lease_worker, NEW.attempt, NEW.leased_at_ms);
END;

-- Result index: one row per uploaded shard result (NOT per passage).
CREATE TABLE results (
  job_id          TEXT NOT NULL,
  worker_id       TEXT NOT NULL,
  r2_key          TEXT NOT NULL,
  content_sha256  TEXT NOT NULL,
  pin_hash        TEXT NOT NULL,
  model_digest    TEXT NOT NULL,
  backend_version TEXT,
  stats_json      TEXT NOT NULL,
  n_passages      INTEGER NOT NULL,   -- passages covered (for throughput/ETA)
  stage           TEXT NOT NULL,
  split           TEXT NOT NULL,
  late            INTEGER NOT NULL DEFAULT 0,  -- 1 = another worker had already completed the job
  created         TEXT NOT NULL,
  PRIMARY KEY (job_id, worker_id)
);
CREATE INDEX results_created_idx ON results(created);
CREATE INDEX results_worker_idx  ON results(worker_id, created);

-- Partial (checkpoint) uploads; one row per uploaded part.
CREATE TABLE job_partials (
  job_id            TEXT NOT NULL,
  worker_id         TEXT NOT NULL,
  part_n            INTEGER NOT NULL,
  r2_key            TEXT NOT NULL,
  content_sha256    TEXT NOT NULL,
  passage_ids_json  TEXT NOT NULL,    -- JSON array of passage ids in this part
  n_ids             INTEGER NOT NULL,
  pin_hash          TEXT NOT NULL,
  model_digest      TEXT NOT NULL,
  backend_version   TEXT,
  stats_json        TEXT NOT NULL,
  stage             TEXT NOT NULL,
  split             TEXT NOT NULL,
  created           TEXT NOT NULL,
  PRIMARY KEY (job_id, worker_id, part_n),
  UNIQUE (job_id, worker_id, content_sha256)
);
CREATE INDEX job_partials_created_idx ON job_partials(created);
CREATE INDEX job_partials_worker_idx  ON job_partials(worker_id, created);

-- Confirmation seal. Sealed while this table is empty. A single row, which
-- cannot be updated or deleted: unsealing is irreversible.
CREATE TABLE seal (
  id          INTEGER PRIMARY KEY CHECK (id = 1),
  prereg_hash TEXT NOT NULL,
  unsealed_at TEXT NOT NULL
);
CREATE TRIGGER seal_no_update BEFORE UPDATE ON seal
BEGIN SELECT RAISE(ABORT, 'seal is irreversible'); END;
CREATE TRIGGER seal_no_delete BEFORE DELETE ON seal
BEGIN SELECT RAISE(ABORT, 'seal is irreversible'); END;

-- Human annotation.
CREATE TABLE annotators (
  id           TEXT PRIMARY KEY,
  name         TEXT NOT NULL UNIQUE,
  token_sha256 TEXT NOT NULL UNIQUE,
  seed         TEXT NOT NULL,       -- per-annotator order seed
  created      TEXT NOT NULL
);

-- Items carry NO model labels, title, author or date (enforced by the API's
-- field whitelist). passage_id is admin-only and never sent to annotators.
CREATE TABLE ann_items (
  item_id    TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL,
  text       TEXT NOT NULL,
  ctx_before TEXT NOT NULL DEFAULT '',
  ctx_after  TEXT NOT NULL DEFAULT '',
  set_name   TEXT NOT NULL CHECK (set_name IN ('teaching','audit')),
  created    TEXT NOT NULL
);

CREATE TABLE ann_assignments (
  annotator_id TEXT NOT NULL REFERENCES annotators(id),
  item_id      TEXT NOT NULL REFERENCES ann_items(item_id),
  ord          INTEGER NOT NULL,     -- seeded per-annotator order key
  PRIMARY KEY (annotator_id, item_id)
);
CREATE INDEX ann_assignments_ord_idx ON ann_assignments(annotator_id, ord);

CREATE TABLE ann_labels (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  annotator_id  TEXT NOT NULL REFERENCES annotators(id),
  item_id       TEXT NOT NULL REFERENCES ann_items(item_id),
  label_json    TEXT NOT NULL,
  evidence_text TEXT NOT NULL DEFAULT '',
  seconds_spent REAL,
  created       TEXT NOT NULL,
  undone        INTEGER NOT NULL DEFAULT 0,
  undone_at     TEXT
);
CREATE UNIQUE INDEX ann_labels_active_idx ON ann_labels(annotator_id, item_id) WHERE undone = 0;
CREATE INDEX ann_labels_recent_idx ON ann_labels(annotator_id, undone, id);
