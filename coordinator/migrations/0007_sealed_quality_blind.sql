-- SEALED split: quality metrics are outcome-revealing (no-obstacle rows carry no evidence quote, so the
-- flagged / quote-failure rate tracks obstacle prevalence; gen_tokens per passage too). Keep them for
-- discovery only.

-- 1. Stored stats of confirmation results/partials: keep counts and timing only.
UPDATE results SET stats_json = json_object('n_lines', n_passages,
                                            'wall_s', COALESCE(json_extract(stats_json, '$.wall_s'), 0))
 WHERE split = 'confirmation';
UPDATE job_partials SET stats_json = json_object('n_lines', n_ids,
                                                 'wall_s', COALESCE(json_extract(stats_json, '$.wall_s'), 0))
 WHERE split = 'confirmation';

-- 2. Hourly counters: passages for every split, quality for discovery only.
DROP TRIGGER hourly_ins;
DELETE FROM hourly;
INSERT INTO hourly(hour, worker_id, stage, results, passages, n_ok, n_flagged, n_schema_invalid, n_evidence_unverified)
  SELECT substr(created, 1, 13), worker_id, stage, COUNT(*), SUM(n_passages),
         COALESCE(SUM(CASE WHEN split = 'discovery' THEN json_extract(stats_json, '$.n_ok') END), 0),
         COALESCE(SUM(CASE WHEN split = 'discovery' THEN json_extract(stats_json, '$.n_flagged') END), 0),
         COALESCE(SUM(CASE WHEN split = 'discovery' THEN json_extract(stats_json, '$.n_schema_invalid') END), 0),
         COALESCE(SUM(CASE WHEN split = 'discovery' THEN json_extract(stats_json, '$.n_evidence_unverified') END), 0)
    FROM results GROUP BY 1, 2, 3;
CREATE TRIGGER hourly_ins AFTER INSERT ON results BEGIN
  INSERT INTO hourly(hour, worker_id, stage, results, passages, n_ok, n_flagged, n_schema_invalid, n_evidence_unverified)
  VALUES (substr(NEW.created, 1, 13), NEW.worker_id, NEW.stage, 1, NEW.n_passages,
          CASE WHEN NEW.split = 'discovery' THEN COALESCE(json_extract(NEW.stats_json, '$.n_ok'), 0) ELSE 0 END,
          CASE WHEN NEW.split = 'discovery' THEN COALESCE(json_extract(NEW.stats_json, '$.n_flagged'), 0) ELSE 0 END,
          CASE WHEN NEW.split = 'discovery' THEN COALESCE(json_extract(NEW.stats_json, '$.n_schema_invalid'), 0) ELSE 0 END,
          CASE WHEN NEW.split = 'discovery' THEN COALESCE(json_extract(NEW.stats_json, '$.n_evidence_unverified'), 0) ELSE 0 END)
  ON CONFLICT(hour, worker_id, stage) DO UPDATE SET results = results + 1, passages = passages + excluded.passages,
     n_ok = n_ok + excluded.n_ok, n_flagged = n_flagged + excluded.n_flagged,
     n_schema_invalid = n_schema_invalid + excluded.n_schema_invalid,
     n_evidence_unverified = n_evidence_unverified + excluded.n_evidence_unverified;
END;

-- 3. Worker self-reports may carry the last job's quality rates (possibly a confirmation job): drop them.
UPDATE workers SET stats_json = json_remove(stats_json, '$.schema_fail_rate', '$.evidence_fail_rate', '$.quality_stage')
 WHERE stats_json IS NOT NULL;

-- 4. Cached fleet/status responses computed from the old counters.
DELETE FROM kv_cache;
