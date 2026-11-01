"""Structural checks only; historical interpretation still requires source review."""
import csv, hashlib, json, re
from pathlib import Path
from urllib.parse import urlparse
import yaml
root=Path(__file__).resolve().parent
rows=list(csv.DictReader((root/'timeline.csv').open()))
assert len(rows)==len({r['event_id'] for r in rows})
assert list(rows[0])==['event_id','domain','country','year','month','event','significance_for_fiction','source1_url','source1_title','source2_url','source2_title','confidence']
for r in rows:
 assert r['domain'] in {'communication','mobility','lighting'}
 assert r['country'] in {'UK','US','both'}
 assert 1796<=int(r['year'])<=1925
 assert not r['month'] or 1<=int(r['month'])<=12
 for n in [1,2]:
  assert urlparse(r[f'source{n}_url']).scheme=='https'
  assert r[f'source{n}_title']
 assert r['source1_url']!=r['source2_url']
doc=yaml.safe_load((root/'lexicon.yaml').read_text())
patterns=[]
for d in doc['domains'].values():
 for g in d['groups']:
  p=re.compile(g['pattern'],re.I)
  assert all(p.search(s) for s in g['forms']),g['id']
  patterns.append(p)
subset=root/'data/chat_uk_us_selected.csv'
assert len(list(csv.DictReader(subset.open())))==252
report={'timeline_rows':len(rows),'regex_patterns_compiled':len(patterns),'listed_forms_with_a_match':sum(len(g['forms']) for d in doc['domains'].values() for g in d['groups']),'chat_rows':252,'chat_sha256':hashlib.sha256(subset.read_bytes()).hexdigest(),'checks':'schema, identifiers, dates, HTTPS URL syntax, source-pair distinctness, YAML parse, regex compilation and seed-form matches; not a historical accuracy or corpus precision test'}
(root/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
