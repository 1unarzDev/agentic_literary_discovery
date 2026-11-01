"""Free CLI fixture: verify staging and always abstain."""
import json
from pathlib import Path

assert Path('task.json').exists()
assert not Path('private').exists()
print(json.dumps({'claim': 'abstain', 'direction': 'unknown', 'effect': None,
                  'ci': None, 'confidence': .5, 'named_confounds': [],
                  'evidence_passage_ids': [], 'rationale': 'Dummy agent; no analysis.'}))
