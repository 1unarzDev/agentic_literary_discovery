# Results to fill in after the Nov 9–11 unseal (NAACL SRW long paper)

**Rule:** every number comes from the registered run (`uv run python -m analysis.stats.battery …` at the registered
commit) and is copied, not retyped by memory. Report every registered row, including nulls. Do not change wording to
fit the result; pick the pre-written template sentence that matches the verdict.

## Before unsealing (gate, all required)
- [ ] OSF registration hash in `docs/prereg.md` line 3 (replaces `OSF-HASH-PLACEHOLDER`), plus the registration date.
- [ ] Blindness attestation signed and deposited. If it is missing, every TF mention gets the flag "expert not blind".
- [ ] Human sign-off on the verified early dates (`human_signoff`), as prereg §2 requires.
- [ ] `canon.parquet` and the registration commit hash frozen and recorded in §Code of the prereg.
- [ ] Seal-integrity log §8.1 re-checked: any new entries copied into paper §9.
- [ ] Early-era top-up (13 works, 144 passages) labeled, or its absence recorded.

## Measurement (from the audit, Nov 6–8, can be filled before the unseal)
- [ ] Peer certification: n certified / n attempted; κ on 20-item pre-test (§4.5).
- [ ] Peer exclusions under the κ < 0.40 rule; π recomputed (yes/no).
- [ ] Peer–expert locus κ, overall and per era (≈150 expert items/era). Construct gate: ≥ 0.6?
- [ ] Model–expert κ (has_obstacle, locus) per era. Gate: ≥ 0.4 in every era? If not, add the "weak model
      information" flag.
- [ ] Model yes-precision/recall against the expert, per era and canonical × non-canonical (replaces the QA-pass
      numbers in §4.3 as the headline accuracy).
- [ ] Teacher–expert agreement on ≈8 items (descriptive).
- [ ] Skip rates per cell; flag any cell above 10%.
- [ ] Quote verification rate on Confirmation (exact + normalized; gate 0.97).

## Confirmatory (Table 2, §6.1, abstract, intro last paragraph)
- [ ] **TF**: Δ_material, Δ_internal (pp) with Bonferroni-adjusted 95% CIs; 2-df Wald p; class; verdict.
- [ ] TF battery: pass / applicable / needed; list any failed check by name.
- [ ] **H1** (L − E), H1|canonical, H1|non-canonical: estimates, CIs, raw and Holm-adjusted p, classes, verdicts.
- [ ] Registered MDEs reported next to any null (TF 9 pp; H1 ≈15 pp).
- [ ] TF genre-adjusted (descriptive): estimate and CI.
- [ ] Composition: share of the E→L material change due to canon composition (shift-share with CI).
- [ ] H1-ML (M vs L, descriptive).
- [ ] Sensitivities: peers-only and expert-only estimators; cross-half canonical authors dropped; early-era
      standardization; K ∈ {20, 25, 40, 50}; downloads-based canon flag.
- [ ] Replication (ELTeC-eng), if available; otherwise state "not available, excluded from denominator".
- [ ] H2a–c, H3 effects and CIs (Appendix C; no verdicts).

## Coverage (§4.4, §9)
- [ ] Final labeled passages per split × era × canonical (Confirmation primary set, `rand_a` k < 12).
- [ ] Works / authors per era in the analysed primary set (expect E ≈87, M ≈538, L ≈3,423 works).

## Multiverse (§7.2, Figure 3)
- [ ] Claude reference vs Gemma vs Qwen: κ and naive TF/H1 under each (`docs/claude_reference_analysis.md`).
- [ ] Specification curve rendered; DSL Confirmation band added.

## Text to update once numbers exist
- [ ] Abstract last sentence; Intro final paragraph (one-line answer); §6.1 template sentence; §8.1 if results
      change the story; Limitations "Compute" bullet; figure 4.
- [ ] Deviations table (Appendix D): add any post-registration deviation, with whether Confirmation data had been seen.
- [ ] Strip `[src: …]` and `TODO` tags; check that every citation resolves to a verified `refs.bib` entry.
- [ ] Anonymity pass: no repo URL, worker names, domain names or teacher/school identifiers.
