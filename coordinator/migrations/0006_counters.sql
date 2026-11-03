-- D1 read budget: /v1/status and /v1/fleet aggregated over every jobs row (~10k rows per call, ~4M rows read/day).
-- Counters maintained by triggers make those aggregates a few hundred rows; a cache row bounds recomputation.

-- (wave, stage, cell, status) -> jobs, passages. cell '' = none.
CREATE TABLE job_counts (
  wave     TEXT NOT NULL,
  stage    TEXT NOT NULL,
  cell     TEXT NOT NULL,
  status   TEXT NOT NULL,
  n        INTEGER NOT NULL DEFAULT 0,
  p        INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (wave, stage, cell, status)
);
INSERT INTO job_counts(wave, stage, cell, status, n, p)
  SELECT wave, stage, COALESCE(cell, ''), status, COUNT(*), COALESCE(SUM(n_passages), 0) FROM jobs GROUP BY 1, 2, 3, 4;

CREATE TRIGGER job_counts_ins AFTER INSERT ON jobs BEGIN
  INSERT INTO job_counts(wave, stage, cell, status, n, p) VALUES (NEW.wave, NEW.stage, COALESCE(NEW.cell, ''), NEW.status, 1, NEW.n_passages)
    ON CONFLICT(wave, stage, cell, status) DO UPDATE SET n = n + 1, p = p + excluded.p;
END;
CREATE TRIGGER job_counts_upd AFTER UPDATE OF status ON jobs WHEN OLD.status <> NEW.status BEGIN
  UPDATE job_counts SET n = n - 1, p = p - OLD.n_passages
   WHERE wave = OLD.wave AND stage = OLD.stage AND cell = COALESCE(OLD.cell, '') AND status = OLD.status;
  INSERT INTO job_counts(wave, stage, cell, status, n, p) VALUES (NEW.wave, NEW.stage, COALESCE(NEW.cell, ''), NEW.status, 1, NEW.n_passages)
    ON CONFLICT(wave, stage, cell, status) DO UPDATE SET n = n + 1, p = p + excluded.p;
END;
CREATE TRIGGER job_counts_del AFTER DELETE ON jobs BEGIN
  UPDATE job_counts SET n = n - 1, p = p - OLD.n_passages
   WHERE wave = OLD.wave AND stage = OLD.stage AND cell = COALESCE(OLD.cell, '') AND status = OLD.status;
END;

-- Full results per (UTC hour, worker, stage): throughput, ETA and quality without scanning results.
CREATE TABLE hourly (
  hour                   TEXT NOT NULL,     -- 'YYYY-MM-DDTHH'
  worker_id              TEXT NOT NULL,
  stage                  TEXT NOT NULL,
  results                INTEGER NOT NULL DEFAULT 0,
  passages               INTEGER NOT NULL DEFAULT 0,
  n_ok                   INTEGER NOT NULL DEFAULT 0,
  n_flagged              INTEGER NOT NULL DEFAULT 0,
  n_schema_invalid       INTEGER NOT NULL DEFAULT 0,
  n_evidence_unverified  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (hour, worker_id, stage)
);
INSERT INTO hourly(hour, worker_id, stage, results, passages, n_ok, n_flagged, n_schema_invalid, n_evidence_unverified)
  SELECT substr(created, 1, 13), worker_id, stage, COUNT(*), SUM(n_passages),
         COALESCE(SUM(json_extract(stats_json, '$.n_ok')), 0), COALESCE(SUM(json_extract(stats_json, '$.n_flagged')), 0),
         COALESCE(SUM(json_extract(stats_json, '$.n_schema_invalid')), 0), COALESCE(SUM(json_extract(stats_json, '$.n_evidence_unverified')), 0)
    FROM results GROUP BY 1, 2, 3;
CREATE TRIGGER hourly_ins AFTER INSERT ON results BEGIN
  INSERT INTO hourly(hour, worker_id, stage, results, passages, n_ok, n_flagged, n_schema_invalid, n_evidence_unverified)
  VALUES (substr(NEW.created, 1, 13), NEW.worker_id, NEW.stage, 1, NEW.n_passages,
          COALESCE(json_extract(NEW.stats_json, '$.n_ok'), 0), COALESCE(json_extract(NEW.stats_json, '$.n_flagged'), 0),
          COALESCE(json_extract(NEW.stats_json, '$.n_schema_invalid'), 0), COALESCE(json_extract(NEW.stats_json, '$.n_evidence_unverified'), 0))
  ON CONFLICT(hour, worker_id, stage) DO UPDATE SET results = results + 1, passages = passages + excluded.passages,
     n_ok = n_ok + excluded.n_ok, n_flagged = n_flagged + excluded.n_flagged,
     n_schema_invalid = n_schema_invalid + excluded.n_schema_invalid,
     n_evidence_unverified = n_evidence_unverified + excluded.n_evidence_unverified;
END;

-- Small JSON cache (fleet / status responses).
CREATE TABLE kv_cache (
  key        TEXT PRIMARY KEY,
  value      TEXT NOT NULL,
  updated_ms INTEGER NOT NULL
);

-- Lease: per (status, stage, pin) ordered by priority, so a lease reads ~LIMIT rows instead of every queued job.
CREATE INDEX jobs_lease2_idx ON jobs(status, stage, pin_hash, priority);
