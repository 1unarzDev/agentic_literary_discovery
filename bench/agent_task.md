Analyze the supplied corpus for a historical shift in the construct defined in task.json.
Use works.parquet (or works.csv) and passages.parquet. Passage IDs are opaque evidence references. Full text is absent; do not invent quotations.
Report whether a shift exists, direction, late-minus-early effect in passage-rate
units, and a 95% confidence interval. The cutoff and estimand are in task.json.
Use equal weights across genres and equal weights across works within a genre.
Report uncertainty, methods, data coverage and alternative explanations.
The target is a robust historical change. Explain whether the available data
and evidence support your conclusion; abstain when they do not.
No outside facts are needed; do not infer trends from remembered literary history.

Fixed analysis tools: Python, pandas, numpy, statsmodels; standard library for I/O.
No web, network, external files, additional models, package installation or agents.
The runner records a fixed 8,000-token total reasoning/output budget by default.
Treat this as a strict instruction; CLI backends may not expose hard token metering.
Wall time is separately enforced. Do not use generated or interpolated passage text.

Return ONLY a JSON object to stdout (or answer.json), with all fields:
{
  "claim": "shift|no_shift|abstain",
  "direction": "increase|decrease|none|unknown",
  "effect": null,
  "ci": null,
  "confidence": 0.5,
  "named_confounds": [],
  "evidence_passage_ids": [],
  "rationale": "Methods, evidence, uncertainty and alternative explanations."
}
Here effect is a finite number or null; ci is [lower, upper] or null.
A shift requires a nonzero effect, CI, and matching direction.
confidence is P(a robust historical shift exists), NOT confidence in your chosen
answer; provide it even when abstaining. It is used for Brier scoring.
Describe any alternative explanations in your own words. Cite actual IDs that
support the target construct; passage evidence illustrates function and cannot
alone establish a historical trend. Do not access hidden answer keys.
