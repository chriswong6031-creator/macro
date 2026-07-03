# W5 VERIFICATION + ADVERSARIAL REVIEW — reversal sleeve (ruling F5, open item O4)

**VERDICT: SHIP** (with 2 non-blocking fix-recommended items).

The W5-A re-derivation and the W5-B CONFIRM-branch integration both pass every load-bearing
gate. The one validated edge survives the survivorship-cleaner raw-plane stress test; the
research report is byte-for-byte deterministic on re-run; the integration wires exactly the
CONFIRM branch the registry records; the sibling shadow sleeve build + ledger are untouched;
all touched tests + bounded smoke are green. Two defects found are confined to the display
stats JSON's provenance/rounding and do NOT alter any page-visible number or the verdict.

---

## 1. RESEARCH AUDIT (W5-A) — PASS

| requirement | status | evidence |
|---|---|---|
| pre-registration BEFORE results | PASS | W5A §5 thresholds (CONFIRM/WEAKEN/REFUTE) fixed before §7 results; registry `w5a-reversal-rederive` hypothesis states the gate |
| thresholds as specified | PASS | CONFIRM = long-leg univ-rel spread positive, NW-HAC t≥2 full AND same sign both halves. Met: +0.426%/reb, t 3.29, early +0.597 / late +0.314 |
| placebo 2000 perms | PASS | `PERM=2000`, seeded `default_rng(SEED)`; perm_p 0.0005 (script L122/375-407) |
| KNOWN-RESULT control (momentum ~0/neg) | PASS | 12-1 momentum long quintile: full −0.031%/reb, t −0.17 → DEAD, reproduces #5/#6 (script L290+) |
| substrate-honesty count (load-bearing) | PASS | Quantified, NOT hand-waved: **0 of 1469 raw names end >20 sessions before panel max** → plane is essentially pure-survivor on delisting axis. Computed by `substrate_honesty()` (script L412-453). Reported as the DECISIVE finding; verdict correctly qualified `-ON-AVAILABLE-PLANE` |
| universe kept as-of formation dates | PASS | `_read_universe` docstring L195-196 "kept for their whole realized life — no as-of trim"; delisting-retention logic grepped (script L44, 195) |
| both benchmarks reported | PASS | UNIVERSE-EW-rel (primary, 349 reb) + CSI300-rel (169 reb, 2012-05+) both in §7 |
| both fill bases reported | PASS | fill-realistic T+1 (H+L)/2 w/ locked-limit exclusion +0.426 vs close-to-close +0.510; tax 0.084pp |
| per-name drawdown re-derived | PASS | published −37.6% reproduces as CSI300-rel spread-NAV −37.7%; univ-rel full-depth −62.8%; per-name p1 −26.6/p5 −17.3/worst −62.1 |
| direct trimmed-vs-raw comparison table | PASS | W5A §7: trimmed +0.97%/mo vs raw −0.067%/reb matched window → GAP ≈1.04pp/mo |
| registry entry matches | PASS | `w5a-reversal-rederive`: verdict CONFIRM-ON-AVAILABLE-PLANE, program china_alpha, wave W5, channel W5-A, status confirmed |

## 2. REPRODUCE — PASS (determinism holds)

Re-ran `PYTHONPATH=$PWD python3 scripts/china_reversal_rederive_phase0.py` end-to-end (EXIT 0,
~40s). Machine verdict reproduced: **CONFIRM-ON-AVAILABLE-PLANE**. The markdown report
`reports/china-reversal-rederive.md` regenerated **byte-for-byte identical** to the committed
version (`diff` → IDENTICAL). Every headline number in the report reproduces exactly:
+0.426%/reb, t 3.29, Sharpe 0.57, n=349, halves early +0.597 / late +0.314, momentum control
−0.031/t −0.17, placebo perm_p 0.0005, drawdown −37.7 / −62.8.

## 3. INTEGRATION AUDIT (W5-B) — PASS

- **Verdict branch matches EXACTLY.** W5-A = CONFIRM → W5-B took the CONFIRM path: rederive
  block shown, noindex removed, baskets card added, china.html link added. Registry
  `w5b-reversal-sleeve-integration` verdict CONFIRM-INTEGRATION-COMPLETE, program china_alpha,
  wave W5, channel W5-B, status shipped. No CONFIRM-link-on-REFUTE (or vice-versa) mismatch.
- **Sibling build runs unbroken.** `build_cn_reversal_sleeve.py` EXIT 0 — wrote page (129 KB)
  + JSON (members=291, sleeve×0.9, ledger rows=884).
- **Ledger semantics untouched.** `git diff engine/cn_reversal_sleeve_ledger.py` EMPTY;
  `git diff engine/cn_reversal_sleeve.py` EMPTY. Sibling program's conventions respected.
- **Stats block renders from committed JSON.** Rendered `site/cn_reversal_sleeve.html` carries
  CONFIRM-ON-AVAILABLE-PLANE, +0.426%/reb, perm_p 0.0005.
- **noindex handling consistent.** `noindex` count in rendered page = 0 (removed); page is a
  linked product; china.html + baskets_china both link `cn_reversal_sleeve.html`.
- **i18n guard passes** on all 3 edited templates (`check_title_i18n` OK).
- **Hostile diff — no orphan hunks.** Both builder diffs are additive, defensive
  (best-effort/None-safe), every hunk maps to a W5-B deliverable.

## 4. TESTS — PASS

- Touched files: `tests/test_w5b_integration.py` (18) + `tests/test_cn_reversal_sleeve.py` (30)
  + `tests/test_china_reversal_rederive_phase0.py` (25) → **73 passed**.
- Bounded smoke `pytest tests -q -k "china or reversal or sleeve"` → **725 passed, 1 skipped**.

## 5. COHERENCE FIXTURES — PASS

- **(a) No page over-claims the verdict.** "VALIDATED EDGE" / "validated A-share edge" language
  refers to phase0-verdict #1, which W5-A re-CONFIRMED; every surface carries the honest
  upper-bound caveat (sleeve `rd-ub` block; baskets card caveat; china.html "separate product"
  note). No surface claims survivorship-free or drops the `-ON-AVAILABLE-PLANE` qualifier.
- **(b) Headline number = re-derived number; upper-bound line relabeled.** Sleeve page rederive
  block = +0.426%/reb, Sharpe 0.57, n=349 (matches report). The old 0.58 line is relabeled
  "Original reference (1990→2026, upper bound — see re-derivation above for honest number)";
  backcast section relabeled "Trimmed-plane reconstruction (upper bound)". Baskets card
  = ~0.57 / +0.43%/reb / n=349 (matches).
- **(c) Link resolves.** `site/cn_reversal_sleeve.html` exists (regenerates from the sibling
  build); china.html + baskets_china anchors point to it.

## 6. HYGIENE — PASS

- `data/vector/regime_calibration.json` stays **untracked/uncommitted** (correct).
- No test-dirtied tracked data. The re-derive re-run overwrites `reports/china-reversal-rederive.md`
  and the stats JSON — both are **untracked** (`??`), so no tracked data was dirtied; report
  regen was byte-identical anyway. My verification build dirtied `site/cn_reversal_sleeve.html`
  + `site/factordata/cn_reversal_sleeve.json`; I reverted both with `git checkout` — tree clean.
- Note (not a defect): committed HEAD `site/cn_reversal_sleeve.html` is STALE (no rederive
  block, noindex still present) — expected, since `site/` regenerates from templates at
  render/deploy time; W5-B correctly ships the template/builder change, not the render.

---

## FINDINGS (non-blocking — fix recommended, do NOT block ship)

**F1 — committed stats JSON is hand-authored, not script-emitted (provenance mismatch).**
`research/china_alpha/w5/w5a_rederive_stats.json` does NOT match what
`scripts/china_reversal_rederive_phase0.py::_write_stats_json()` (L759-819) actually emits:
- committed is pretty-printed (`"key": value`); the script writes compact (`"key":value`,
  `separators=(",",":")`, L818);
- committed rounds per-name drawdown (`-26.6`) where the script emits full precision (`-26.641`);
- committed has `csi300_reference.hit: null` where the script emits `0.556`; committed omits
  `ls_spread.n / hit / maxdd_pct` that the script emits.
Both the template comment (`cn_reversal_sleeve.html.j2` L139-140) and the builder comment
(`build_cn_reversal_sleeve.py` L50-52) assert the JSON is "emitted by
china_reversal_rederive_phase0.py" — which is currently false. **Every page-visible number in
the committed JSON is nonetheless correct and matches the report**, so this is a
documentation/provenance defect, not a wrong-number defect. Fix: regenerate the JSON from the
script (or drop the "emitted by" claim). Impact if unfixed: a future re-run will silently
change the committed file's formatting + the keys below.

**F2 — script `_write_stats_json` mangles perm_p via 3dp rounding.** `_p()` (L768-770) rounds
to 3dp, so the true `perm_p 0.0005` (report uses 4dp, `round(perm_p,4)`, L612) is written to
the JSON as **0.001**. The committed JSON (hand-authored) has the correct `0.0005`, and the
page renders `0.0005` via `'%.4f'` (template L161) — so the LIVE page is correct today. But if
anyone regenerates the JSON per F1's fix, the page perm_p would flip to `0.0010`. Both values
are "deep in the tail" (does not change the CONFIRM verdict), but the writer should use ≥4dp
for perm_p to stay consistent with the report. `data/china_stocks_raw` file count 1568 vs
"1469 names with data" vs "1278 post-hygiene" are all consistent (store / loadable / post-filter),
not a discrepancy.

Neither F1 nor F2 changes any verdict, any page-visible number, or the determinism of the
research report. They are recommended cleanups for the sibling program's next touch.
