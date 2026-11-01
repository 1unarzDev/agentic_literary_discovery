-- 0001 hard-coded CHECK (stage IN (...)) on pins and jobs with the original
-- five stages, so pins/jobs for 'workcheck' and 'alt_label' failed with a 500.
-- Stage names are validated by the API (src/util.ts STAGES); the tables no
-- longer restrict them, so new stages need no table rebuild.
PRAGMA defer_foreign_keys = true;

CREATE TABLE pins_new (
  pin_hash     TEXT PRIMARY KEY,
  stage        TEXT NOT NULL,
  model_ref    TEXT NOT NULL,
  model_digest TEXT NOT NULL,
  prompt_hash  TEXT NOT NULL,
  schema_hash  TEXT NOT NULL,
  options_json TEXT NOT NULL,
  active       INTEGER NOT NULL DEFAULT 1,
  created      TEXT NOT NULL
);
INSERT INTO pins_new SELECT pin_hash, stage, model_ref, model_digest, prompt_hash, schema_hash, options_json, active, created FROM pins;
DROP TABLE pins;
ALTER TABLE pins_new RENAME TO pins;

CREATE TABLE jobs_new (
  job_id        TEXT PRIMARY KEY,
  stage         TEXT NOT NULL,
  wave          TEXT NOT NULL,
  shard_key     TEXT NOT NULL,
  pin_hash      TEXT NOT NULL REFERENCES pins(pin_hash),
  n_passages    INTEGER NOT NULL,
  split         TEXT NOT NULL CHECK (split IN ('discovery','confirmation')),
  dup_group     TEXT,
  priority      INTEGER NOT NULL DEFAULT 100,
  cell          TEXT,
  status        TEXT NOT NULL DEFAULT 'queued'
                CHECK (status IN ('queued','leased','done','dead','closed')),
  attempt       INTEGER NOT NULL DEFAULT 0,
  lease_worker  TEXT,
  lease_expires INTEGER,
  leased_at_ms  INTEGER,
  done_at       TEXT,
  done_by       TEXT,
  created       TEXT NOT NULL
);
INSERT INTO jobs_new SELECT job_id, stage, wave, shard_key, pin_hash, n_passages, split, dup_group, priority, cell, status,
                            attempt, lease_worker, lease_expires, leased_at_ms, done_at, done_by, created FROM jobs;
DROP TABLE jobs;
ALTER TABLE jobs_new RENAME TO jobs;

CREATE INDEX jobs_lease_idx   ON jobs(status, stage, priority);
CREATE INDEX jobs_expiry_idx  ON jobs(status, lease_expires);
CREATE INDEX jobs_dup_idx     ON jobs(dup_group) WHERE dup_group IS NOT NULL;
CREATE INDEX jobs_holder_idx  ON jobs(lease_worker) WHERE lease_worker IS NOT NULL;
CREATE INDEX jobs_wave_idx    ON jobs(wave);

CREATE TRIGGER jobs_lease_log AFTER UPDATE OF status ON jobs
WHEN NEW.status = 'leased' AND NEW.lease_worker IS NOT NULL
BEGIN
  INSERT OR IGNORE INTO leases(job_id, worker_id, attempt, leased_at_ms)
  VALUES (NEW.job_id, NEW.lease_worker, NEW.attempt, NEW.leased_at_ms);
END;
