# W2 (narrative confluence) — VERIFICATION + ADVERSARIAL REVIEW

*Gate: verification subagent · 2026-07-03 · worktree `lucid-knuth-523979` · model Opus 4.8.*

## VERDICT: **SHIP** (one non-blocking hygiene finding — registry diff churn)

Spec implemented faithfully. No F3 (rank/admission) violation, no honesty-law violation, no
non-ASCII attribute delimiters, dual-span present, Jinja `.get()`-safe, degradation-safe. All
touched tests pass; live fixtures resolve as the spec requires. The phase-0 (W2-C) research is a
well-powered pre-registered true-negative, correctly registered, and wired to nothing.

One non-blocking blemish: the W2-C executor re-serialized `data/experiments/registry_seed.json`
with `ensure_ascii=False`, producing 158 lines of cosmetic unicode-escape churn on ~30 unrelated
experiment entries. Verified semantically inert (only the new `w2c-hc-readthrough` entry changes;
all other entries byte-differ in escaping only, load identically via `json.loads`). Not a shipper —
noted for a follow-up minimal-diff re-serialize.

---

## 1. HOSTILE DIFF REVIEW

Files changed (5 tracked + 4 new): `engine/china_narrative_tags.py` (new), `tests/test_china_alpha_w2a.py`
(new), `tests/test_china_alpha_w2b.py` (new), `scripts/c_hc_readthrough_phase0.py` (new),
`reports/c-hc-readthrough-phase0.md` (new, untracked), `research/china_alpha/w2/*` (new),
`scripts/build_china_library.py`, `engine/china_standout_track.py`, `templates/china.html.j2`,
`data/experiments/registry_seed.json`, `research/china_alpha/phase1/phase0-verdicts.md`.

**F3 (narrative never creates admission/rank) — UPHELD.**
- Builder `scripts/build_china_library.py:1696-1719` (buy) and `:1586-1600` (ripening) attach
  narrative by in-place dict mutation only (`r["narrative"]=...`, `r["ab_tier"]=...`). No append,
  removal, or sort of any ranked list. `_cn_bonus`, `blend_sorted`, admission gates untouched
  (grep confirms no edit).
- Order-invariance assert exists at `build_china_library.py:1715-1719` AND PASSES on live data
  (fixture d, below). CAVEAT: the assert compares `eligible_rows[:110]` against `wide["buy"]`
  (a list built from that same slice) — since narrative code never reorders either list, the
  assert is structurally weak (would not catch a narrative-introduced reorder because narrative
  cannot introduce one). The real F3 guarantee is structural (mutation-only) and is independently
  confirmed by the live pre/post order check in fixture (d). Not a blocker; the assert is
  belt-and-suspenders, and the substantive invariant holds.

**Honesty-law — UPHELD.**
- Every `nb-narr` chip (2 in template, ENTRY + RIPENING loops) carries "descriptive positioning
  lens, NOT validated alpha" verbatim in its `title` (regex-verified). No BUY-family word in any
  chip title.
- Global-AI honesty tags pass through VERBATIM: engine `china_narrative_tags.py:317` stores the
  whole `global_ai` dict by reference (no mutation); `ab_tier` reads `validated_tag` only for a
  set-membership test (`:436`), never rewrites it; template renders `.get('validated_tag','')`
  directly. A `2024+-only` / `weak` tag flows unaltered and correctly fails the A-tier gate
  (only `validated`/`partial` qualify). Live radar carries e.g. `ths_storage_chip
  validated_tag='2024+-only'` — verified unaltered.
- Help text extension (+2 sentences EN + ZH) frames narrative as "display-only … not a buy
  trigger"; A-tier tooltip is the spec copy ("display-only, forward grades accruing").

**Jinja missing-key — SAFE.** All narrative access is `.get()`-guarded (`n.get('narrative')`,
`(_nr.get('radar') or {}).get(...)`, `_nr.get('rel20') or 0`). Chip renders only when
`n.get('narrative') and n.get('narrative').get('theme')` — a radar-only tag (theme=None) yields
no chip. Ledger writes use `(r.get("narrative") or {}).get(...)`.

**Dual-span — PRESENT.** Every user-visible narrative string has `l-en`/`l-zh` spans; `t()` is not
used inside any attribute (tooltips are plain `title="EN · ZH"` strings, per the standing rule).

**Non-ASCII attribute delimiters — NONE.** Regex scan of the W2 chip/badge lines finds no
smart-quote / full-width quote used as an attribute delimiter; executor's own
`test_no_non_ascii_attribute_delimiters` passes.

**Orphan hunks — ONE (non-blocking).** `registry_seed.json`: 175+/158− lines, of which 158 removed
are pure `\uXXXX`→literal churn on ~30 unrelated entries (ensure_ascii toggle). Semantic diff:
only `w2c-hc-readthrough` added; all shared entries + top-level keys identical. Cosmetic, inert at
runtime. Flag for minimal-diff cleanup, not a shipper. No other orphan hunks.

**A/B badge scoping — CORRECT.** Depth-parsed loop scan: `nb-atier` and `nb-narr` appear ONLY in
the ENTRY (`_entry_rows`) and RIPENING (`_rip`) loops. Both RAN loops (`_ran_late_rows`, `_ran`)
carry NEITHER — stricter than the W2B report's claim (which said the chip *could* appear on
RAN_LATE). Belt-and-suspenders: builder sets `ab_tier=None` for non-ENTRY/RIPENING stages.

## 2. PHASE-0 AUDIT (W2-C global-HC → CN-pharma read-through)

- **Pre-registration before results — YES.** §1 of `W2C_HC_READTHROUGH.md` fixes driver (XLV primary
  + XLV/IBB/XBI robustness), target (survivorship-clean Shenwan-Pharma 801150 + 3 THS baskets),
  controls (SPY + CN-universe horse race), placebos, era splits, and GO/ACCRUE/NO-GO bars, with an
  explicit honest prior (ACCRUE-at-best, likely NO-GO). Methodology mirrors #773 precedent verbatim
  (W-FRI weekly, ported `nw_ols` HAC lags=4, 4w log-momentum, horse race, full/pre-2024/2024+).
- **Thresholds are the pre-registered ones — YES.** GO: full|t|≥3 AND pre-2024|t|≥2 AND HAC|t|≥2;
  observed 0.48/0.59/0.49 → NO-GO. Machine report gate line matches doc.
- **Placebo run — YES.** 2000-permutation shuffled-driver null (seed 773): mean 0.015, sd 0.993,
  P(|t|≥2)=0.041, real perm_p 0.085. Cross-slice placebos (baijiu/gold/cpo) flat. Positive control
  FIRES: same harness reproduces semis→cpo t=3.08/3.12 (vs published #773 3.27/3.03) — proving the
  null is a true negative, not a dead instrument. The doc §2.3 honestly discloses and corrects an
  earlier single-shuffle t≈2.5 artifact.
- **Registered in repo idiom — YES.** `data/experiments/registry_seed.json` → `w2c-hc-readthrough`
  (kind phase0_verdict, verdict NO-GO, program china_alpha, wave W2, channel W2-C);
  `phase0-verdicts.md` row 41 (single-line add).
- **Nothing wired — CONFIRMED.** `grep` across engine/ + builder + templates finds zero imports of
  `c_hc_readthrough`. Script is read-only research, `__main__`-gated, deterministic.
- **Reproducible — YES.** Re-ran `python3 -m scripts.c_hc_readthrough_phase0`: exit 0, verdict NO-GO,
  `reports/c-hc-readthrough-phase0.md` regenerated BYTE-IDENTICAL.

## 3. TESTS (honest counts)

- `tests/test_china_alpha_w2a.py` — **39 passed** (4 pandas deprecation warnings).
- `tests/test_china_alpha_w2b.py` — **38 passed**.
- Bounded smoke `pytest tests -q -k "china or narrative or setup_tier"` — **740 passed, 1 skipped**,
  6021 deselected (115s). No failures.
- Template hygiene subset (delimiter/parse/balanced/dual_span/buy_family/ran_late) — **11 passed**.

## 4. LIVE FIXTURES (as_of 2026-07-03; 259 baskets, 812 tickers tagged)

| # | Fixture | Result |
|---|---------|--------|
| a | 300725.SZ | theme=Synthetic Biology, level=HOT, rel20=+17.8pp, breadth=87.5%, src=THS. ab_tier(ENTRY/RIPENING)=A (HOT), ab_tier(RAN_LATE)=None. Spec-consistent. |
| b | 688306.SS | theme=Solid-State Battery, level=HOT, rel20=+31.84pp, breadth=81.8%, src=THS. ab_tier(ENTRY/RIPENING)=A, RAN_LATE=None. |
| c | 603129.SS | NO qualifying theme (theme=None) → narrative chip ABSENT (template guards on `.get('theme')`); has radar-only join with global_ai=None → ab_tier(RAN_LATE)=None, ab_tier(ENTRY)=B. Honest absence confirmed. |
| d | buy-array order | pre==post IDENTICAL after live narrative attach (110 rows); 70/110 buy rows tagged. F3 upheld empirically. |
| e | render scoping | A/B badge + narrative chip render ONLY in ENTRY + RIPENING loops (depth-parsed); every chip title carries "NOT validated alpha" + "descriptive positioning lens"; A-badge tooltip carries "display-only … forward grades accruing"; zero BUY-family words. |
| f | degradation | closes=None → empty heat, no crash; missing membership → empty; build_narrative_tags() with missing closes → n_baskets=0, no raise (radar-only tags still emit, theme=None so no chip); builder's degraded stub returns ab_tier=None. Graceful. |

**Caveat on (a)/(c) stage-dependence:** the committed live artifact
`site/factordata/china_standouts.json` is STALE (pre-W1: all `stage=None`; pre-W2: no
narrative/ab_tier keys) because no render has run since these edits (task forbids full render).
So "603129 is RAN_LATE" and "given its stage, ab_tier consistent" cannot be checked against a live
artifact — the stage field does not yet exist there. Instead I verified `ab_tier` produces the
spec-correct value under EACH possible stage (A on ENTRY/RIPENING when HOT/confirmed, B otherwise,
None on RAN_LATE). Stage assignment is W1 machinery, out of W2 scope. This is a data-freshness
limitation of the verification, not a defect in the W2 code.

## 5. HYGIENE

- `git status`: 5 tracked modified (the expected code/doc files) + expected new files. No tracked
  data/parquet dirtied by my test or script runs.
- `data/vector/regime_calibration.json` remains UNTRACKED (pre-existing) — correctly not committed.
- Phase-0 rerun regenerated `reports/c-hc-readthrough-phase0.md` byte-identically (untracked). No
  restore needed.
- No git writes performed.

## Non-blocking follow-ups
1. Re-serialize `data/experiments/registry_seed.json` with `ensure_ascii=True` to drop the 158 lines
   of cosmetic escape churn and leave only the `w2c-hc-readthrough` addition in the diff.
2. (Optional) Strengthen the builder order-invariance assert to snapshot buy-ticker order BEFORE the
   narrative loop and compare AFTER, so it has real power against a future reorder regression.
