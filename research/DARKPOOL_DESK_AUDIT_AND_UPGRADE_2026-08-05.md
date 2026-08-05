# Dark Pool Desk — audit, upgrade plan, and what shipped (2026-08-05)

Scope: `site/darkpool.html` and everything under it — `scripts/build_darkpool_desk.py`,
`engine/darkpool_context.py`, `collectors/finra_short_volume.py`,
`collectors/finra_ats_transparency.py`, `data/finra_short_volume/panel.parquet`,
`data/finra_ats/`.

Every number below was measured on the live store on 2026-08-05, not asserted.

---

## §0 Headline

The desk was reporting a **direction** it had no basis for and that house law forbids,
while ranking its board on a **structural constant**, off a panel holding **47 days** of
history, with **no price data at all**, and calling **all** off-exchange volume "dark
pool" when only ~a quarter of it reaches a dark pool.

All five are fixed. The desk now describes what was observed, ranks by deviation from
each name's own norm, runs on **755 days** of history, joins price, separates
institutional venues from retail internalisation, and writes a forward ledger so its
reads become gradeable instead of assumed.

---

## §1 Findings

### F1 — The headline verdict was a construction house law forbids (SEVERITY: highest)

`research/DO_NOT_REBUILD.md`, PSS-AF1 row, and the PSS-AF1 charter §14:

> "FINRA short volume is not short interest, net selling, or institutional buying.
> **Raw short ratio/off-exchange share remains forbidden as a standalone direction
> signal.**"

`darkpool_context.classify()` derived `accumulation` / `distribution` from exactly raw
off-exchange share + raw short ratio, standalone, and the page rendered it as
**"leaning up" / "leaning down"** in the hero, the rail, and every name card.

### F2 — And measurement gave it nothing to stand on

Walk-forward over the panel as it then stood (47 dates; n=86 accumulation / 61
distribution), forward returns of tagged names minus universe:

| horizon | acc − dist | t | p |
|---|---|---|---|
| 1d | +0.22% | 0.33 | 0.74 |
| 5d | −0.87% | −0.63 | 0.53 |
| 10d | −0.10% | −0.05 | 0.96 |

The sign **flips** between 1d and 5d and nothing approaches significance. This is not a
refutation — 47 dates cannot refute anything — it is the *absence of any basis* for copy
that was asserting a direction anyway. Nothing was ever recorded at tag time, so this
null had to be reconstructed after the fact.

### F3 — Most of what the page called "dark pool" is not dark pool

Off-exchange volume = registered ATS (true dark pools) **+** non-ATS OTC (wholesaler
internalisation, predominantly retail marketable flow). Measured per name, week
2026-06-22 — ATS share of each name's off-exchange total:

| AAPL | NVDA | TSLA | GME | F |
|---|---|---|---|---|
| 31.4% | 23.5% | 26.0% | 24.5% | 16.5% |

The headline `oe_share` counted **both**; the venue table showed **only ATS**. The table
could never account for the number printed above it, and a page titled *"where the big
money trades off the public tape"* was mostly measuring retail order flow being
internalised by Citadel/Virtu/Jane Street.

### F4 — The board ranked a structural constant

`_sort_ticker_stats` sorted by raw `oe_share` descending. Over the panel:

- **42.7%** of participation variance is a **fixed per-name effect**
- top-20 day-over-day overlap **45%**
- cross-sectional rank autocorrelation **0.58** (lag 1), **0.45** (lag 20)

Retail-heavy and thin names print more off-exchange *every day*. Ranking by level spent
the front of the board on structure rather than news.

### F5 — History was 47 days, and the documented backfill would have broken the repo

`panel.parquet` held 2026-05-26 → 2026-07-31. `backfill_finra_short_volume.py` targets
2018-08-01 and had **never been run**; FINRA's CDN serves the full history (verified
2018/2020/2022/2024/2025/2026, all HTTP 200).

Worse, the script's universe was `gex_symbols() ∪ every ticker already in the panel`.
That was safe when the panel was young, but the nightly collector had accrued 1,533
tickers, so at the script's **own documented invocation** (`--start 2018-08-01`) it
projected to **86 MB** — ~3× the 30 MB git ceiling its docstring claimed to respect.
`build_darkpool_desk.py:434` prints that exact command as the operator remedy.

| window | universe | projected panel |
|---|---|---|
| 3y | gex only | 7.4 MB |
| 3y | union (as coded) | 32.3 MB — over |
| 8y | gex only | 19.8 MB |
| 8y | union (as coded) | 86.1 MB — ~3× over |

### F6 — The split trap (found only once real history landed)

Participation = FINRA off-exchange shares ÷ vendor consolidated shares. FINRA reports
raw as-of-day counts; the price vendor **retroactively split-adjusts** its volume
history. After an N:1 split every pre-split day therefore reads participation ÷ N.

7 of 225 names carried a corrupted baseline, and they are exactly the known splitters:

`BKNG 30.9× · ORLY 21.4× · LRCX 11.4× · KLAC 10.5× · AVGO 10.1× · SMCI 8.8× · MSTR 7.8×`

BKNG read **1.0%** participation in 2023 against 31.7% now, and the bimodal baseline
produced **z = +53.7** for a day whose participation was actually *below* its own norm.

This is invisible on a 47-day panel (no split falls in-window) and any future split
silently recreates it. Note the vendor's price columns are *both* split-adjusted (they
differ only by dividends), so the split factor is **not recoverable** from the store —
detection and baseline restart is the honest remedy, not correction.

### F7 — Statistical construction

`oe_z` used mean and population σ of the **entire** series **including the current
observation**, over an expanding window. A genuine spike inflates its own σ and drags
the mean toward itself, suppressing the score meant to flag it. Participation is
fat-tailed, so mean/σ is the wrong scale estimator regardless.

### F8 — Collected-but-unused, and available-but-uncollected

| field | status before |
|---|---|
| `short_exempt` | in the panel since day one, **never read** by the desk |
| `totalNotionalSum` | dropped in `_parse_rows` — no dollar weighting possible |
| `OTC_W_SMBL_FIRM` | never fetched — the non-ATS half (F3) |
| avg print size (`shares/trades`) | computable from stored data, never computed |
| price | **never loaded** — builder read only the `volume` column |

### F9 — The lag chip understated reality

Copy said *"2–4 wk publication lag"*, hardcoded. The stored latest week was 2026-06-22
against a panel date of 2026-08-04 — **44 days (6.3 weeks)**. A staleness chip that is
itself stale is worse than none.

### F9b — The backfill collided with a frozen research family's tamper seal

Caught by CI on the first push, not by local tests.

`engine/personality_flow_absorption.py` (PSS-AF1 — a **frozen prospective family**, see
`research/DO_NOT_REBUILD.md`) seals every `panel.parquet` row dated `<= 2026-07-21` with
a row count (`51,960`) and a `SHA256`. Backfilling history straight into that file
changed both, so `load_registration()` began failing inert and two gates went red.

The write was verified **purely additive** — 0 pre-existing rows missing, 0 modified,
258,198 added — so this was not tampering. But the seal is *tamper-evidence*: it is
deliberately brittle and **cannot distinguish** "rows legitimately backfilled from the
authoritative source" from "rows edited to manufacture a result". That is the property
that makes it worth having.

**Resolution: do not re-cut the seal.** Re-freezing a frozen family's attestation is an
operator decision, and doing it here would teach the seal to yield whenever it is
inconvenient. Instead the stores are separated:

- `panel.parquet` — the collector's, **byte-identical to what PSS-AF1 attested**
- `panel_deep.parquet` — pre-collector history, written only by the backfill
- `build_darkpool_desk._load_panel()` unions them; the collector wins on any overlapping
  `(date, ticker)` because it carries FINRA's latest restatement

The desk still sees all 755 dates. `_assert_not_the_sealed_panel` fails the backfill
closed if anyone points it back at `panel.parquet`.

### F10 — Freshness

Panel stopped at 2026-07-31 while FINRA had 08-03 and 08-04 posted; last commit touching
it was 2026-08-01. (Cured incidentally by the backfill, which runs to `today`.)

---

## §2 What shipped

**Data foundation**
- Backfill universe capped to `gex_symbols()` (`--universe union` retained for
  deliberate off-git work), plus a `MAX_PANEL_MB` hard stop that refuses to grow the
  tracked panel past 25 MB **before** a commit rather than after. Corrected size table
  in the docstring. **[F5]**
- Ran it: panel **47 → 755 dates** (2023-08-01 → 2026-08-04), 6.1 MB. Also cured **F10**.
- New `FinraOtcNonAtsAdapter` (same endpoint, `OTC_W_SMBL_FIRM` → `data/finra_otc_nonats/`),
  registered in `scripts/collect.py`. ~38k rows/week vs ATS's 191k. **[F3]**
- `notional` captured in both stores; readers `fillna` for weeks stored earlier. **[F8]**

**New `engine/darkpool_signals.py`**
- `trailing_z` — fixed lookback, current observation **excluded**, median/MAD. **[F7]**
- `share_break_index` / `usable_history` — split detection and baseline restart.
  Catches 7/7 known splitters; does **not** fire on the market's genuine 1.2×/3y drift.
  Max |z| across the universe fell **53.7 → 3.48**. **[F6]**
- `streak_above_norm` — campaign vs spike, strict `>` so a flat series scores 0.
- `venue_split` — `ats_frac`, per-leg block sizes, avg print price. Keys non-ATS on
  `venue_name` because FINRA publishes **no MPID** for non-ATS firms. **[F3]**
- `market_gauge` — dollar-weighted market participation. **[F8]**
- `unusualness` — ranks deviation, deliberately excluding the raw level. **[F4]**
- Price, dollar participation, and `short_exempt` rate all wired. **[F8]**

**`engine/darkpool_context.py` → v2**
- Direction call **removed**. Names group by the observed conjunction:
  `heavy_into_weakness` / `heavy_into_strength` / `heavy_price_flat`. `classify()`
  returns `None` without price, so the forbidden standalone construction is
  unreachable. **[F1]**
- `append_ledger` → `data/darkpool/ledger/forward.jsonl`, same-day idempotent, records
  observed inputs only (no outcome, no score, no direction). **[F2]**
- Copy follows the operator's 2026-07-27 rule: "what we're watching" conditions, no
  verdict or refutation vocabulary.

**Page**
- Market gauge; per-name venue character ("34% through dark pools — mixed"); streak;
  5-day price; measured lag chip **[F9]**; a printed-nulls coverage block; methodology
  rewritten to describe what the desk now does; three new desk columns.

**Migration** — `darkpool_context.v1 → v2`, `darkpool_eod.v1 → v2`, NW lobe keys, and
the synapse registry entry all moved together, because a consumer reading v1 keys off a
v2 artifact gets silent nulls rather than an error.

**Tests** — `tests/test_darkpool_signals.py` (18 new) + rewritten context section.
Mutation-checked: disabling split-trimming, reverting the streak comparison, and folding
the current observation back into the baseline each fail the suite. One test
(`trailing_z` exclusion) was **found vacuous** under mutation — median/MAD is too robust
for a 200-point fixture to see the difference — and was rewritten to pin the mean/σ path
where the original defect actually lived.

---

## §3 Not done — deliberately

| item | why |
|---|---|
| Deeper than 3y history | 8y is size-lawful (19.8 MB) but a much longer crawl; 755 dates already supports a 252-session baseline. One command away: `--start 2018-08-01`. |
| Grading the ledger | It needs forward time to accrue. The reader is the next piece of work, and until it exists the honest statement is the null in §1/F2. |
| Wholesaler classification (retail internaliser vs institutional broker) | The data supports it — AAPL's largest non-ATS counterparty is Goldman at $15.5B, which is not retail flow. But the retail/institutional labelling of firms is a judgment call that should ship as an explicitly labelled heuristic, reviewed, not slipped in. |
| Intraday / per-print data | Genuinely needs an equity tick feed. Still `null` under `pending`, never faked. |
| Re-fetching stored ATS weeks for `notional` | Would cost ~39 API pages/week for cosmetic completeness; new weeks acquire it naturally, and `avg_print_price_partial` flags the interim. |

---

## §4 Standing constraints honoured

- PSS-AF1 kill (§1/F1) — no standalone directional signal from off-exchange share.
- The PSS-AF1 frozen family (`engine/personality_flow_absorption.py`,
  `data/personality_timing/flow_absorption_manifest_v1.json`) is **untouched**; its
  "do not add Quiver/ATS" clause is scoped to that research family, not to this desk.
- Display tier throughout: `is_context_only=True`, `display_only=True`, no rank/size/gate
  authority, "validated" never emitted (CI-enforced).
- Nulls printed, not hidden — the coverage block names what could not be seen.
- Bilingual EN/ZH; 红涨绿跌 swap verified in computed styles for the price-direction hues.
