-- Annotation v2: training and certification sets with reference answers.
--   practice : 20 items, the reference + rationale is shown right after each answer;
--   cert     : 20 items, no feedback; passing (locus kappa >= 0.60 and obstacle agreement
--              >= 0.75 vs the reference) unlocks the main (audit) and teaching sets;
--   retake   : 20 fresh items, offered once if cert is failed.
-- SQLite cannot alter a CHECK, so ann_items is rebuilt. ref_json is admin-written and is only
-- ever returned to the annotator for practice items after they answer, and for missed
-- cert/retake items after the round is complete.
PRAGMA defer_foreign_keys = true;

CREATE TABLE ann_items_v2 (
  item_id    TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL,
  text       TEXT NOT NULL,
  ctx_before TEXT NOT NULL DEFAULT '',
  ctx_after  TEXT NOT NULL DEFAULT '',
  set_name   TEXT NOT NULL CHECK (set_name IN ('practice','cert','retake','teaching','audit')),
  ref_json   TEXT,
  created    TEXT NOT NULL,
  CHECK ((set_name IN ('practice','cert','retake')) = (ref_json IS NOT NULL))
);
INSERT INTO ann_items_v2(item_id, passage_id, text, ctx_before, ctx_after, set_name, ref_json, created)
  SELECT item_id, passage_id, text, ctx_before, ctx_after, set_name, NULL, created FROM ann_items;
DROP TABLE ann_items;
ALTER TABLE ann_items_v2 RENAME TO ann_items;
CREATE INDEX ann_items_set_idx ON ann_items(set_name);

-- Admin decision that overrides the computed certification result (e.g. pass after review,
-- or revoke). One row per annotator; deleting the row returns to the computed result.
CREATE TABLE ann_cert_override (
  annotator_id TEXT PRIMARY KEY REFERENCES annotators(id),
  decision     TEXT NOT NULL CHECK (decision IN ('pass','revoke')),
  note         TEXT NOT NULL DEFAULT '',
  created      TEXT NOT NULL
);
