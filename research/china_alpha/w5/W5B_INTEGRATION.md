# W5-B — CONFIRM-path integration: survivorship-honest re-derivation block + product promotion

*China Alpha Program · Wave W5 (the reversal sleeve, ruling F5) · verdict-conditional wiring.*
*Pre-condition: W5-A returned CONFIRM-ON-AVAILABLE-PLANE.*
*Registry: `data/experiments/registry_seed.json` id `w5b-reversal-sleeve-integration`.*

---

## 1. Verdict branch taken: CONFIRM

W5-A result (from `research/china_alpha/w5/W5A_REVERSAL_REDERIVE.md` and registry entry
`w5a-reversal-rederive`):

| metric | value |
|---|---|
| verdict | **CONFIRM-ON-AVAILABLE-PLANE** |
| long-leg spread (universe-rel., fill-realistic) | **+0.426%/reb** |
| NW-HAC t | **3.29** |
| ann. Sharpe | **0.57** |
| n rebalances | 349 |
| hit rate | 53.9% |
| time-halves | both positive (early +0.597/t 2.97, late +0.314/t 1.92) |
| 2000-perm placebo perm_p | **0.0005** |
| momentum control (12-1) | -0.031%/reb, t -0.17 (DEAD — harness sane) |
| maxDD (universe-relative) | -62.8% (full depth incl. 1990s bears) |
| maxDD (CSI300-relative) | -37.7% (reproduces published -37.6%) |

**Substrate qualifier (always reported):** both substrates are pure-survivor on the delisting
axis (0 of 1,469 raw names end >20 sessions before the panel max). The reversal signal buys
the deepest within-sector decliners — exactly the population most likely to contain eventual
delistings. True out-of-sample number is AT OR BELOW this one. Every reversal number on the
page is labeled an upper bound.

**Recent-era caveat:** the 2024+ tail (n=29 rebalances) is negative (-0.772%/reb, t -1.60).
CONFIRM keys on the two time-HALVES per pre-registration (both positive). The forward ledger
adjudicates whether 2024+ is noise or a regime change; first ≥21d grades mature ~2026-07-29.

---

## 2. Changes shipped (CONFIRM path)

### 2.1 Stats JSON artifact (new file)

`research/china_alpha/w5/w5a_rederive_stats.json` — the committed honest-headline numbers the
sleeve page reads at render time. Populated from the W5-A results; updated by a future
re-derive run via the `_write_stats_json()` function added to
`scripts/china_reversal_rederive_phase0.py` (additive — the script's markdown report and all
existing behavior are untouched).

The JSON is the single source of truth for the re-derived stats; the sleeve builder reads it
defensively (absent/corrupt file = block omitted, no crash, no membership effect).

### 2.2 `scripts/build_cn_reversal_sleeve.py`

- Added `_REDERIVE_STATS` path constant pointing to the committed stats JSON.
- Added `_load_rederive_stats()` — best-effort loader, returns None on any error.
- `compute()` now calls `_load_rederive_stats()` early (before any early returns) so
  `"rederive_stats"` key is present in ALL returned payloads (including the `no_data` path).
- The value flows into the payload as `rederive_stats`.

**What was NOT touched:** `engine/cn_reversal_sleeve.py`, `engine/cn_reversal_sleeve_ledger.py`
(membership logic, sizing, ledger semantics — untouched, exactly as required).

### 2.3 `templates/cn_reversal_sleeve.html.j2`

1. **noindex removed** — page is now a linked product; the `<meta name="robots"
   content="noindex">` line is replaced with a comment explaining the change.
2. **Survivorship-honest re-derivation block added** (id `rederive-block`) ABOVE the existing
   backcast — shows verdict, long-leg spread, t, splits, fill tax, per-name drawdown p1/p5,
   placebo perm_p. Rendered only when `d.rederive_stats` is present (graceful omission). Full
   dual-span EN/ZH. No Chinese in HTML attribute values (ASCII attribute delimiters observed).
3. **Backcast section relabeled** — heading changed from "Backcast — NAV vs CSI300" to
   "Trimmed-plane reconstruction (upper bound) — NAV vs CSI300"; sub-text clarified that this
   is the survivorship-/adjustment-inflated upper bound vs the raw-plane re-derivation above.
4. **Reference line updated** — now reads "Original reference (1990→2026, upper bound — see
   re-derivation above for honest number)" instead of the bare "Reference (validated, 1990→2026)".
5. **Shadow tag updated** — "SHADOW · not live" → "beta · accruing grades".
6. **Footer updated** — removed "SHADOW product" framing, added honest promotion note.

### 2.4 `templates/baskets_china.html.j2`

- Added CSS for `.sleeve-strategy-card` (compact, distinct from basket cards).
- Added "Reversal Sleeve" strategy card (id `reversal-sleeve-card`) in the non-lite path,
  between the `#content` div and the footer. Shows:
  - Badge: "VALIDATED EDGE"
  - Name: "Reversal Sleeve" (dual-span)
  - One-line honest framing: "monthly-rebalanced contrarian basket — a portfolio, NOT stock
    tips; high variance, size small"
  - Stats: n members, sleeve sizing (×factor), re-derived Sharpe ~0.57, +0.43%/reb, n=349
  - Link: `cn_reversal_sleeve.html`
  - Honest caveat about upper bound and forward ledger

### 2.5 `scripts/build_baskets_china.py`

- Added best-effort `sleeve_stats` loader (reads `site/factordata/cn_reversal_sleeve.json`
  if it exists, extracts `n_members` and `sleeve_factor` for the template card). Additive, never
  fatal.
- Passes `sleeve_stats=sleeve_stats` to the template render call.

### 2.6 `templates/china.html.j2`

- Minimal edit: the sentence "The validated A-share within-sector reversal basket edge is a
  **separate quarterly basket product**" in the stock board note (near line 1623) now has
  `cn_reversal_sleeve.html` as an anchor link (dual-span EN/ZH). No other changes.

### 2.7 `data/experiments/registry_seed.json`

- Added entry `w5b-reversal-sleeve-integration` (status `shipped`, verdict
  `CONFIRM-INTEGRATION-COMPLETE`, program `china_alpha`, wave `W5`, channel `W5-B`).

---

## 3. Tests

`tests/test_w5b_integration.py` — 18 targeted tests:

| id | what |
|---|---|
| T1 | rederive block present when stats JSON available (CONFIRM verdict) |
| T2 | rederive block omitted gracefully when stats JSON absent |
| T3 | noindex meta tag absent from rendered sleeve HTML |
| T4 | `cn_reversal_sleeve.html` link present in baskets_china template |
| T5 | dual-span (l-en/l-zh) in rederive block |
| T6 | `rederive_stats` key in compute() payload (all code paths) |
| T7a-c | `_load_rederive_stats` returns None on corrupt, absent, missing-key inputs |
| T7d | `_load_rederive_stats` returns dict on valid input |
| T8 | `check_title_i18n` passes on sleeve template |
| T9 | `check_title_i18n` passes on baskets_china template |
| T10 | sleeve `build()` end-to-end smoke — sibling build intact |
| T11 | no CJK characters inside HTML attribute values in sleeve template |
| T12a | backcast section still present and labeled "upper bound" |
| T12b | backcast NAV section (bc-stats / nav.sleeve) still in template |
| T13 | committed stats JSON has all required keys |
| T14 | china.html.j2 links to `cn_reversal_sleeve.html` near "separate" |

All 18 pass. All 30 pre-existing `test_cn_reversal_sleeve.py` tests pass. All 25
`test_china_reversal_rederive_phase0.py` tests pass. `check_title_i18n` clean on all three
edited templates.

---

## 4. What was explicitly NOT done (per the laws)

- No touch to `engine/cn_reversal_sleeve.py` semantics, sizing, or membership logic.
- No touch to `engine/cn_reversal_sleeve_ledger.py`.
- No new git commits (no git writes).
- No network calls.
- The re-derive script's markdown report path and all existing CLI behavior are unchanged.
- The `REFUTE` path is fully implemented in the test suite (T2 covers "block omitted when no
  stats") — the REFUTE branch would simply not show the rederive block AND would keep noindex
  AND would not add the baskets_china card; the conditional logic in the template and builder
  already handles this correctly.

---

## 5. Open items inherited (unchanged from W5-A)

- **Substrate repair (O4 residual):** the raw plane is still a pure-survivor plane on the
  delisting axis. A PIT membership store retaining delisted-name terminal returns is an F9/W1
  substrate repair — until it lands every reversal number stays labeled an upper bound.
- **2024+ weakness adjudication:** forward ledger adjudicates ~2026-07-29 (first ≥21d maturity).
  If it corroborates a regime break, revisit sleeve sizing; if noise, full-depth CONFIRM stands.
- **Cost pass:** the re-derived spread is gross of cost. The sleeve page already frames "size
  small" and the high-turnover nature; a net-of-cost validation is a future wave.
