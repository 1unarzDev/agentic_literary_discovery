-- Annotation: a 'review' set. The expert reader sees the reference answer + rationale of a
-- practice/cert/retake passage and agrees or corrects it; their answers become the key.
-- Rebuild ann_items to extend the set_name CHECK (ref_json required for review too).
PRAGMA defer_foreign_keys = true;

CREATE TABLE ann_items_v3 (
  item_id    TEXT PRIMARY KEY,
  passage_id TEXT NOT NULL,
  text       TEXT NOT NULL,
  ctx_before TEXT NOT NULL DEFAULT '',
  ctx_after  TEXT NOT NULL DEFAULT '',
  set_name   TEXT NOT NULL CHECK (set_name IN ('review','practice','cert','retake','teaching','audit')),
  ref_json   TEXT,
  created    TEXT NOT NULL,
  CHECK ((set_name IN ('review','practice','cert','retake')) = (ref_json IS NOT NULL))
);
INSERT INTO ann_items_v3(item_id, passage_id, text, ctx_before, ctx_after, set_name, ref_json, created)
  SELECT item_id, passage_id, text, ctx_before, ctx_after, set_name, ref_json, created FROM ann_items;
DROP TABLE ann_items;
ALTER TABLE ann_items_v3 RENAME TO ann_items;
CREATE INDEX ann_items_set_idx ON ann_items(set_name);
