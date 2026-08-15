# SP-1 — Short-Pressure & Crowding: adjudication + frozen test

> **CORRECTION (2026-08-14) — the entry rule's publication lag was measured
> EARLY, not merely revised.** This file states `knowable_date` = settlement + 10
> CALENDAR days in three places (§2, §4 trap 4, §5A entry rule) and calls it a
> "conservative" floor. It was not conservative: measured against the exchange
> calendar it lands **before** the figure was public on every settlement the repo
> can check, and **before our own collector's capture date** on all three
> settlements the history store holds. That is look-ahead at the publication
> boundary — the one place a short-interest study is most likely to be misread as
> predictive. The convention is now the 8th NYSE session after settlement, one
> definition in `lib/finra_knowable.py` (PR #5705).
>
> **SP1-A's published NULL verdict stands** — the correction makes the test
> strictly harder, and it touches neither of the two reasons §7 gave for the
> verdict. **Its effect sizes are not re-quotable**, and the panel must be rebuilt
> before any re-run. See **§5B — AMENDMENT 2** for the measurement, the governance
> ruling, and the re-run condition. The original text below is left **intact and
> annotated, never rewritten**, so the rule SP1-A actually ran under stays legible.

**Written:** 2026-08-05. **Status:** data spine BUILT; numeric study FROZEN, NOT RUN.
**Lobe:** `research/SHORT_SIDE_MASTERPLAN_BY_FABLE.md` (avoid-not-short charter).
**Freeze authority:** this file. No outcome number below has been computed. The
only measurements taken before writing this were data-quality (coverage,
sentinels, dispersion, joins) — never a forward return.

---

## §0. Acceptance gates (read first)

This wave is **not done** unless:

1. The IBKR borrow accrual runs nightly and each capture lands as its own
   immutable per-date file. *(shipped — `collectors/ibkr_borrow.py`)*
2. The FINRA short-interest panel rebuilds 2018→now with a `knowable_date`
   column, and nothing downstream is permitted to join on `settlement_date`.
   *(shipped — `scripts/backfill_finra_short_interest.py`)*
3. Every measured trap in §4 has a test that goes RED when its guard is removed
   — verified by mutation, not by the test merely passing. *(shipped —
   `tests/test_short_pressure.py`, 5 mutations verified)*
4. No artifact in this wave produces a fused positioning score, a ranking, a
   size, a gate, or the word "squeeze". *(shipped — asserted in tests)*
5. The §5 study runs only AFTER this file is committed.

---

## §1. The method, and what the evidence actually says

The proposal: use short positioning for both direction and risk — days-to-cover
plus change in short interest, borrow fee, utilization, availability, short-sale
volume, DTC change, institutional and passive ownership, options call
concentration, cover-volume vs float, negative revisions, insider activity, flow
velocity — combined into two interaction branches (high short pressure with
improving fundamentals = squeeze continuation; high short pressure with
deteriorating fundamentals = informed bearish continuation).

**Three corrections the evidence forces, before any of it is built.**

**(a) The direction is bearish, and the proposal's own closing line is the
correct one.** Hong, Li, Ni, Scheinkman & Yan (NBER w21166) find high
days-to-cover predicts *low* forward returns — short high-DTC, long low-DTC earns
~1.2%/month — and that DTC beats the plain short ratio precisely because it
normalises by trading capacity, with the short ratio becoming statistically
insignificant post-2000 while DTC survives. So "days to cover contains more
information than simple short ratios" is correct and well-sourced. The
implication is that the *squeeze* branch is a conditional carve-out from an
unfavourable base rate, not a symmetric twin of the bearish branch. It must be
tested as such, and it must never be the default reading.

**(b) The tradeable version of this edge is already gone; the avoid version is
not.** Muravyev, Pearson & Pollet (*Journal of Finance*, 2025) run 162 anomalies:
average long/short return +0.14%/month gross, **−0.01%/month after borrow fees**,
with the returns concentrated in the short leg and in expensive-to-borrow names.
That is close to fatal for a short book and *irrelevant to an avoid lens* — you
pay no borrow fee to decline to buy something. This is the single strongest
argument that the house's existing constraint (`DO_NOT_REBUILD`: "Short-side lobe
as directional shorting | FORBIDDEN — AVOID-not-SHORT evidence only") and the
economics point the same way. The constraint is not a tax here; it is the form in
which the edge survives.

**(c) The options leg is not independent of the borrow leg.** Muravyev, Pearson &
Pollet (*JFE*, Oct 2025) find abnormal stock-return predictability from option
signals falls by **about two-thirds** once returns are adjusted for borrow fees —
option prices embed the borrow fee. So "bullish options information" and "borrow
fee" are substantially the *same* variable wearing two hats. Counting them as two
agreeing confluence votes double-counts one force. Any construction here must
either orthogonalise them or carry only one.

Add ordinary anomaly decay — McLean & Pontiff-class haircuts of ~26% out-of-sample
and ~58% post-publication, and the DTC result is eleven years published — and the
honest prior on the bearish branch is "real, known, and substantially arbitraged";
on the squeeze branch, "unproven and fighting its own base rate".

---

## §2. What was unblocked (and why the house believed otherwise)

Two blockers were treated as settled facts across many documents. Both were
artifacts of what we had asked for, not of what exists. Both are now removed.

**(1) "No PIT short interest — usable ~2027+."** Stated in the short-side
masterplan §6, in `engine/crowding.py`, in the SM2-R3 preamble, in
`scripts/fund_crowding_phase0.py`, and as the stated reason for the
`DO_NOT_REBUILD` deferral of the winner-autopsy squeeze legs ("no PIT
short-interest history (single FINRA settlement date)").

The claim describes `collectors/finra.py`, which probes only recent candidate
settlement dates and keeps the newest that answers. FINRA's API itself serves the
back-history: a single `symbolCode` query returns **206 settlement dates spanning
2017-12-29 → 2026-07-15**, each paging a full 15k–22k-row cross-section.
Rebuilt in ~20 minutes. The forward-accrual clock that was scheduled to make this
answerable in 2029 is replaced by 8.5 years of history available today.

Caveat kept in front, not buried: this is an **as-restated** panel, not a true
vintage matrix. FINRA marks restatements (`revisionFlag`) and they are rare —
1.2% of rows across the first three settlements, 0.004% at 2026-07-15 — and the
flag is preserved so a consumer can exclude or measure them. The *publication*
lag, which is the larger PIT risk, is handled by a conservative `knowable_date`
(settlement + 10 days against an actual ~7-day dissemination).

> **RETIRED 2026-08-14 (§5B).** Both numbers in that sentence are wrong. The
> dissemination lag is not ~7 days — FINRA's own cited schedule example is 12
> calendar days — and settlement + 10 days was therefore not conservative but
> **early**. Current rule: the 8th NYSE session after settlement,
> `lib/finra_knowable.py`.

**(2) "Borrow fee / utilization / availability: paid vendor only."** The signal
docket carries three entries — SLF-002 (borrow-fee anomaly), SLF-014 (utilization
shock), SLF-015 (locate scarcity) — all marked `data_contract_first`, blocked on
DataLend/S3/IHS/Ortex. `SIGNAL_COMMONS_W6_PAID_DATA_MEMO.md` evaluated Ortex and
recommended SKIP. The data census confirms: no borrow data anywhere in the repo,
for any market.

Interactive Brokers publishes it free over anonymous FTP
(`ftp2.interactivebrokers.com/usa.txt`): **19,475 US symbols with an indicative
borrow fee, a rebate rate, and lendable availability**, refreshed ~every 15
minutes. That closes SLF-002 and SLF-015 outright at zero cost. It does **not**
close SLF-014 — true utilization is on-loan ÷ lendable and the feed gives only
the lendable side. Availability change is a *proxy* for demand consuming supply
and must be labelled as one, never as utilization.

Unlike the FINRA panel this has **no history and no backfill** — it accrues only
forward from first capture, so every night not run is permanently lost. That is
why the collector shipped first.

---

## §3. The legal envelope — what may and may not be built

The proposal's headline construction is forbidden here, and this is the most
important thing to say plainly:

> "Positioning fusion (positioning keys fused into signal scores) | **ILLEGAL**"
> — `DO_NOT_REBUILD`, Signal Commons rulings 2026-07-05
>
> **SM2-R3**: "No composite across 13F/insider/short/options axes at any grain…
> No function may accept both a 13F metric and a short-derived metric
> (`days_to_cover`, `si_change_pct`) as combined inputs producing a single
> number." — `engine/ownership_crowding.py`

"High short pressure + positive revisions + bullish options + institutional
accumulation + breakout = squeeze continuation candidate" is exactly a single
number fused across the short, revisions, options and 13F axes. It cannot ship in
that shape, whatever it scores.

What *is* permitted:

- **Printed legs, not a composite.** Each axis stated separately with its own
  coverage, plus an unweighted COUNT of how many agree. A count of printed legs
  is not a score: unweighted, unfitted, no authority. This is the existing
  `engine/altdata.py` "confluence, not a buy" pattern.
- **Display tier ships freely.** House epistemics: context/detection/tagging
  infrastructure ships display-tier without a gauntlet; the gauntlet is a
  *promotion* gate. A null blocks authority, never building or accrual.
- **A display-tier composite is possible but expensive.** `DO_NOT_REBUILD`
  Amendment 2 (operator override, 2026-08-03) allows a user-facing display-tier
  composite under the PSI §3.1.2 construction law: transparent printed legs, v0
  equal weights, coverage abstention, day-one forward grading. That is the only
  door to anything resembling the proposal's single verdict, and §5 is the study
  that would have to pass first.
- **Avoid, never short.** No short-sale recommendation, no borrow mechanics as
  execution advice, no "squeeze" vocabulary anywhere user-facing.

Prior-art boundaries confirmed clear:

- The §7 "short-interest crowding" kill does **not** cover this. The study behind
  those numbers (`scripts/fund_crowding_phase0.py`) tested a price-only
  conjunction — crowded relative strength AND extended above the 50dma — and
  *excluded* the short-interest leg entirely because it could not be backtested.
  It killed a momentum-crowding flag, not a short-interest construction.
- The standalone SI **factor** is a different and genuine prior null: q_fdr 0.32,
  `survives_fdr=false`, flagged "size in disguise". That closes the standalone
  level factor, consistent with the decay literature — not a conditional one.
- **The live factor is ungradeable, and its stated reason is now false.**
  `engine/equity_factors.py:554` nulls `short_interest` whenever `asof` is set;
  the IC scorecard always sets `asof`; so the factor is absent from all 11 graded
  factors in `data/edgar/ic_scorecard.json` while still rendering on
  `factors.html` as "Low short interest". It has been live and structurally
  ungradeable since it shipped. The panel from §2 removes the obstacle. Grading it
  is a **separate gated change** — deliberately not made in this wave, because
  letting an ungraded leg into a scorecard-weighted path is how authority gets
  granted by accident.
- SLF-013 ("SI days-to-cover level + change, split into squeeze-risk vs
  informed-short baskets", `local_phase0_ready`, never run) is essentially this
  proposal, already registered. SLF-012 (short-volume × price × borrow proxies,
  `advance_to_fable`, score 10.4, never run) is its nearest neighbour. This
  prereg is the harness those docket rows were waiting for.
- PSS-AF1 owns one frozen FINRA short-*volume* construction. SP-1 must not reuse
  raw short ratio as a standalone directional signal (AF1's explicit ban) and
  must not collide with its challenge-window configuration.

---

## §4. Measured traps (each has a mutation-verified test)

| # | Trap | Measurement | Guard |
|---|---|---|---|
| 1 | `days_to_cover` capped at **999.99** when ADV≈0 | 3,983/22,375 rows (**17.8%**) at 2026-07-15 — the raw column's p90 *is* the sentinel | percentiles taken on uncapped rows only; `dtc_capped` emitted; deltas refuse to difference against it |
| 2 | Feed is ~42% **OTC**, carrying nearly all sentinels | 9,491/22,375 OTC; listed sentinel rate only 0.3% (0.50% across the full 205-settlement panel) | percentile basis restricted to exchange-listed |
| 3 | **Borrow fee is near-constant in our universe** | in-universe median 0.35%, p99 1.25%, 18/1,519 names ≥1%, **none ≥20%**; full file median 1.10%, 50.9% ≥1% | absolute thresholds, never a percentile or z; capture widened to universe ∪ HTB tail |
| 3b | **Thin-ADV days-to-cover is a division artifact** | of the 75 listed names with DTC ≥ 50, **all 75** have ADV < 100k and their **median ADV is 36 shares/day**. With ADV ≥ 100k: p50 2.94, p99 16.1, max 38.8 | `MIN_ADV_SHARES = 100_000` floor on the percentile basis; thin names flagged and reported `elevated=None`, never "elevated" |
| 4 | Publication lag ≈ 7 days *(**measurement RETIRED 2026-08-14** — §5B; FINRA's own cited schedule example is 12 calendar days)* | joining on `settlement_date` buys ~8 days of look-ahead | `knowable_date` = **8 NYSE sessions** after settlement (`lib/finra_knowable.py`); missing column raises rather than degrades. *Retired guard: settlement + 10d — measured EARLY, see §5B* |
| 5 | `>10000000` availability sentinel | 762 rows | boolean flag; never coerced to a number |
| 6 | Feed mutates intraday | 07:01:33 → 07:17:12 in 16 min | one capture per day, `snapshot_et` recorded |
| 7 | **Delisted tickers resurrect** across an 8.5-year panel | "newest settlement per ticker" returned **48,539** names at asof 2026-08-01 when the newest settlement carries ~23k — the excess is dead symbols wearing years-old readings | `MAX_STALE_DAYS = 45`: a name that stopped being reported is absent, not stale-but-live |

Trap 3b is the most dangerous of the set and was found only by reading the live
output. The 999.99 sentinel announces itself; a DTC of 527 on a SPAC unit trading
36 shares a day does not — it looks like the single most heavily shorted name in
the market and would top any ranking built on this data. It is also not merely
cosmetic: removing artifact names from the comparison basis moved *real* names'
percentiles materially (WEN 72nd → 59th), so leaving them in mis-states every
reading, not just their own.

Trap 3 is the one that most changes the proposal. Three of the thirteen proposed
inputs — borrow fee, utilization, availability — carry the strongest literature
support, and all three are close to degenerate in the universe this system
covers. Within our names, borrow fee is a **rare-event flag** (18 names today),
not a ranking variable. Treating it as a continuous factor would z-score noise
around a flat line — the same structural-constancy defect already filed against
single-name `gamma_regime` (audit #29).

---

## §5. The frozen test

**Not yet run.** Runs only after this file is committed.

**Data.** FINRA panel 2018-01-12 → 2026-07-15 (**205 settlements, 3,866,270 rows,
48,539 tickers, 106MB** — built 2026-08-05), joined on `knowable_date`;
exchange-listed only; sentinel-capped rows excluded; ADV ≥ 100k shares (trap 3b;
this leaves ~5,977 rankable names per settlement out of ~23,316). Forward
returns from the existing close panel. Options/revisions/insider/13F legs enter
only where their own PIT coverage supports the date (revisions history begins
2026-06-16; insider is `filing_date`-keyed to 2006; the options watchlist covers
~25% of the universe — coverage abstention is mandatory, not optional).

**Pre-registered horizons.** 21d and 63d only, per the backtest-horizon ladder.
No verdict at any other horizon.

**H1 — the bearish branch (primary).** Among high-DTC names (top listed quintile
by `dtc_pctile`), do those with *deteriorating* fundamentals (negative revision
breadth) underperform the high-DTC cohort as a whole? One-sided: the claim is
degradation, and the deliverable is an avoid lens.

**H2 — the squeeze branch (secondary, adversarial).** Among high-DTC names, do
those with *improving* revisions outperform the high-DTC cohort? Pre-declared
prior: **fights the base rate; expected null.** Registering it as a named
hypothesis with a stated expectation is the point — an unregistered version of
this is how "short squeeze" narratives enter a product.

**H3 — orthogonality (mandatory, gates H1/H2 interpretation).** Does the options
leg add anything over the borrow leg? Per MPP(2025) it should be ~2/3 redundant.
If the incremental contribution is indistinguishable from zero, the options leg
is dropped rather than carried as a second vote.

**Controls.** Size and momentum neutralisation (the SI factor's prior verdict was
"size in disguise" — that must be refuted, not assumed away). Matched controls
drawn from the same DTC quintile so the contrast is the *conditioner*, not the
short pressure.

**Falsifiers, pre-stated.** H1 fails if the conditioned cohort's disadvantage vs
the unconditioned high-DTC cohort straddles zero at both horizons, or if it does
not survive size/momentum neutralisation, or if the sign flips across the
2018–2021 / 2022–2026 halves. H2 is treated as null unless it clears the *same*
bar as H1 — no weaker standard for the more attractive story.

**Promotion bar (unchanged from the lobe ladder).** ≥5pp on the constitution
axes at the declared horizon, episode-clustered bootstrap, BH-FDR q ≤ 0.10 within
this family, both halves sign-stable, per-name majority, n ≥ 300 per side.
Clearing it promotes to *display-tier composite eligibility* under PSI §3.1.2 —
**not** to rank, size, or gate authority, which remain closed by §3.

**Statistics discipline.** Nulls printed, not hidden. Resolution-conditioned
denominators forbidden. A null on H1 does not retire the axes: they remain
display-tier context and confluence inputs, per house epistemics.

---

## §5A. AMENDMENT 1 — the runnable subset (pre-outcome, 2026-08-05)

Committed BEFORE any outcome was computed. §5 as written cannot run: its primary
conditioner does not exist historically. Coverage measured after §5 was frozen:

| Conditioner in §5 | Historical availability | Verdict |
|---|---|---|
| revision breadth | `data/revisions/history.parquet` starts **2026-06-16** (~7 weeks) | **NOT RUNNABLE** |
| options positioning | 2026 only, ~25% of universe | **NOT RUNNABLE** |
| borrow fee | accrual starts **2026-08-05** | **NOT RUNNABLE** |
| insider (Form 4) | `filing_date`-keyed, 2006q1→2026q1 | runnable, deferred to A2 |
| **price action** | `data/yahoo/` 738 tickers, deep | **RUNNABLE** |

So the branch conditioner becomes **price action** — which is the proposal's own
"price breakout" versus "failed bounce" leg, not a substitute invented to make
something run. The revisions/options/borrow versions of H1/H2 are deferred until
their own accrual matures (~2027); this amendment does not weaken their bar.

**SP1-A, exactly:**

- **Universe:** FINRA exchange-listed ∩ not sentinel-capped ∩ ADV ≥ 100k ∩ has a
  `data/yahoo/` close at the entry date. Overlap measured: 481 names (2018) rising
  to 660 (2026).
- **Entry:** the first trading day at/after `knowable_date` (settlement + 10d).
  Never the settlement date.
  *(**CORRECTED 2026-08-14, §5B.** The binding clause — "first trading day at/after
  `knowable_date`", never the settlement date — is unchanged. The parenthetical
  gloss was wrong: `knowable_date` is the 8th NYSE session after settlement,
  `lib/finra_knowable.py`. SP1-A ran under the retired gloss; 146 of the 205
  settlement entry dates move 1–3 sessions LATER on rebuild, none earlier.)*
- **Horizons:** 21d and 63d only.
- **Short-pressure axis:** within-date `dtc_pctile` over the eligible set.
- **Conditioner:** within-date trailing 63d return percentile — strong vs weak.
- **H0 (replication):** does high DTC underperform low DTC unconditionally? This
  is the Hong-Li-Ni-Scheinkman-Yan result; if it does not appear at all, the
  branch tests are uninterpretable and that is the finding.
- **H1 (bearish branch):** within the top-DTC quintile, do price-WEAK names
  underperform the quintile as a whole?
- **H2 (squeeze branch):** within the top-DTC quintile, do price-STRONG names
  outperform the quintile as a whole? **Pre-declared expectation: null.**
- **Statistics:** returns demeaned within date (removes market timing), date-level
  spread series, Newey-West t (lag = horizon), split-half sign stability
  2018–2021 vs 2022–2026, BH-FDR q ≤ 0.10 across the family of tests reported.

**SURVIVORSHIP — stated up front, not discovered later.** `data/yahoo/` is the
*current* 738-name universe, so a 2018-start study sees only names that survived
to 2026. For a short-pressure study this is the worst possible bias direction to
be careless about: heavily-shorted names that went to zero are exactly what is
missing. It biases **against** H1 (the worst outcomes are absent), so a positive
H1 is conservative and a null H1 is **not** decisive. No effect size from SP1-A
may be quoted as unbiased, and no result here may promote anything. A clean
version needs a delisting-inclusive panel (`collectors/edgar_delisting.py` +
`edgar_deadname_prices.py` exist and are the path).

## §5B. AMENDMENT 2 — the publication lag was measured EARLY (post-outcome, 2026-08-14)

Committed AFTER SP1-A ran. That is the whole governance question, so it is answered
first, in the open, rather than left to a reader to notice.

**Provenance and status, as of 2026-08-14.** The corrected convention is established
by **PR #5705** (`lib/finra_knowable.py`, `scripts/backfill_finra_short_interest.py`,
`engine/neuralweb/context_api.py`), which was open and armed when this amendment was
written. This amendment is the governance record of that correction and does not
depend on the merge landing first: the *measurement* is what retires the old rule,
and it holds regardless of merge order. Two states are therefore true together and
are kept distinct throughout this section — the **rule** is corrected, and the
**live panel** still carries the retired one until it is rebuilt.

### What was wrong

`knowable_date` = settlement + 10 CALENDAR days, called "the deliberately
conservative floor" in the code comment this prereg inherited. Three independent
measurements (PR #5705, receipts in `lib/finra_knowable.py`'s module docstring)
show it was not a floor at all:

1. **Its own cited FINRA schedule example refutes it.** The comment reads
   "settlement Jan 15 → due Jan 20 6pm ET → published Jan 27". That is **12
   calendar days** — already two past the constant the same sentence calls
   conservative. §2 and §4 of this file repeated the derived "~7-day
   dissemination" claim; both are retired above.
2. **It lands early against the exchange calendar** on every settlement the repo
   holds: 2026-06-30 (3 days early), 2026-07-15 (2), 2026-07-31 (2). The 3-day gap
   is the observed 2026-07-03 Independence Day closure — precisely what calendar
   arithmetic cannot see and session arithmetic cannot miss.
3. **It precedes our own collector's capture date** on all three settlements in
   `data/finra/short_interest_history.parquet`. On the 07-31 settlement the retired
   rule declared the row knowable on 08-10, **three days before our collector could
   have seen it.**

The correct reading is not "the constant was a bit tight". An under-waiting derived
lag **manufactures look-ahead at the publication boundary**, and it did so in the
one direction that flatters a short-interest study.

### The measured blast radius on SP1-A's entry dates

`scripts/research/sp1_short_pressure_study.py:78` reads the panel's **stored**
`knowable_date` column and does not derive it (`engine/short_pressure.py` likewise,
and `tests/test_short_pressure.py:113` pins that it raises rather than degrades if
the column is absent). So the study's behaviour does not change until
`data/finra/short_interest_panel.parquet` is rebuilt — **and then SP1-A's entry
dates move with no code change to the study at all.**

Entry is "the first trading day at/after `knowable_date`", which absorbs part of the
shift whenever the retired date already fell on a weekend or holiday. Measured over
the settlement schedule this panel spans, retired rule vs 8-session rule:

| entry shift | settlements | share |
|---|---|---|
| unchanged | 59 | 28.8% |
| +1 session later | 45 | 22.0% |
| +2 sessions later | 76 | 37.1% |
| +3 sessions later | 25 | 12.2% |
| **moves LATER** | **146** | **71.2%** |
| **moves EARLIER** | **0** | **0.0%** |

**The defect is strictly one-directional.** Not one entry in 205 moved earlier: the
retired rule never once waited longer than the corrected one. Every deviation was a
1–3 session head start the study did not have in reality.

*Method, stated so it can be checked.* The panel is gitignored build output
(`.gitignore:143`) and absent from a sparse worktree, so this was computed over a
**reconstruction** of the FINRA settlement schedule (the 15th and the last calendar
day of each month, rolled back to the prior session), not over the panel's own
`settlement_date` column. The reconstruction reproduces the panel's committed
coverage sidecar exactly on all three of its independent anchors — **205
settlements, first 2018-01-12, last 2026-07-15** — and reproduces PR #5705's 3/2/2
day deltas on the three committed settlements. SP1-A drew **120** entry dates from
this 205-settlement schedule, so ~71% of them move; the exact per-date count is only
recoverable from a rebuilt panel.

### RULING — amend in place; do not supersede; do not re-run yet

**Amended in place.** This is not a design change. No hypothesis, conditioner,
horizon, universe, control, statistic, or promotion bar moves. §5A's binding entry
clause — *"the first trading day at/after `knowable_date`… Never the settlement
date"* — is untouched, and its stated purpose is exactly "no look-ahead at the
publication boundary". The parenthetical `(settlement + 10d)` was a **factual gloss
on what `knowable_date` meant**, and the gloss was measured wrong. Correcting a
wrong factual gloss *toward the rule's own stated intent* is a correction, not a
post-hoc redesign.

**Why a prereg may be corrected here at all.** Prereg immutability exists to stop
goalposts moving *after* outcomes are seen. That hazard is absent in both
directions:

- The correction makes the test **strictly harder** — later entry, less
  information, an advantage removed. Nobody moves a goalpost toward themselves.
- It was **not authored by SP1**. PR #5705 came out of a FINRA-lag audit of two
  drifting constants in `context_api.py` and the backfill script; it had no
  knowledge of, and no contact with, SP1's outcomes.
- Immutability is preserved by **non-deletion, not by non-annotation**. All three
  retired-rule sites are left legible and marked, so a reader can always reconstruct
  the rule SP1-A actually ran under. Silently rewriting them would have destroyed
  exactly the audit trail immutability is for.

**Precedent followed.** `research/ORACLE_COMPOUND_GAUNTLET_R1.md` handles a
*stronger* case the same way: a post-outcome dated blockquote at the top of the
file that **withdrew a PASS** (A9) and **reversed a verdict** (A17), left the
original intact, named what still stands, and minted no new file. This case
withdraws no verdict and is strictly weaker, so it takes the same treatment. §5A
above establishes the numbered in-document amendment form (though it was
pre-outcome).

**Superseding was rejected.** A new prereg would misfile a corrected data
convention as a design change, and would orphan a null that nothing depends on.

**Re-running now was rejected — but the obligation is recorded, not waived.** A
re-run has zero governance delta today: SP1-A promoted nothing, ranked nothing,
gated nothing, and filed no `DO_NOT_REBUILD` row (§7). The panel is gitignored build
output and its rebuild is a real ~20-minute compute cost (§1), paid to change numbers
that no authority state reads.

**DISCHARGED 2026-08-15 — the rebuild and re-run happened; see §7.** The actor this
ruling was waiting for arrived the next day. `short_interest_panel.parquet` was
rebuilt with the corrected writer (206 settlements, 3,888,611 rows, 2018-01-12 →
2026-07-31) and its sidecar now reads `"knowable_lag_sessions": 8`, so the receipt
named below has flipped. **The verdict did not move: SP1-A is still a NULL.** The
entry-shift prediction in this section was made against a *reconstruction* and is
now confirmed against the panel itself — of the 115 settlements admitted under both
conventions, **81 (70.4%) move 1–4 sessions later and 0 move earlier**, against the
71.2% / 0 predicted. **The citation ban below is NOT lifted:** this section's PIT
reason is discharged, but §5A's survivorship reason is untouched and §7's
2026-08-15 entry adds a **third, independent** reason — the price index is not a
trading-day index. Numbers from the re-run are no more quotable than the ones they
replace.

**The trigger is an ACTOR, not an event — do not wait for one.**
`scripts/backfill_finra_short_interest.py` is referenced by **no workflow**: it is a
manual script, so nothing rebuilds this panel on a schedule and there is no passive
"next rebuild" to inherit the correction. Until somebody runs it, the panel keeps the
retired rule indefinitely. Whoever next needs an SP1 number owns the rebuild + re-run
as one step; the binding obligation until then is the citation ban below.

**No live surface is affected today — and that is a trap for whoever wires one.**
`engine/short_pressure.py` is imported by exactly two things:
`tests/test_short_pressure.py` and `scripts/research/sp1_short_pressure_study.py`
(verified: no render, app, worker, or template consumer). The module is
**built-but-unwired**, so nothing user-facing is currently serving early
`knowable_date`s, and this correction is not a live-data incident. The hazard is
ordering: the FIRST consumer to wire `asof_slice` into a surface inherits a panel
still built on the retired rule and ships look-ahead on day one. **Rebuild the panel
before wiring, not after.** (Do not confuse this module with
`sfc_short_pressure` in `engine/hk_stock_signals.py` / `engine/pick_lab/hk.py` —
that is the Hong Kong SFC signal, a different source, unaffected by any of this.)

### Effect on published SP1 results — stated explicitly

**Mechanically affected: YES.** `reports/sp1-short-pressure.md`,
`data/research/sp1_short_pressure.json`, and the §7 status-log numbers were all
computed under the retired rule. The live panel still is: its committed sidecar
`data/finra/short_interest_panel_coverage.json` records `"knowable_lag_days": 10`,
which is the receipt that the panel predates this fix. (The corrected writer emits
`"knowable_lag_sessions": 8` instead, so the sidecar self-documents on rebuild.)

**The published VERDICT stands: unaffected.** SP1-A is a NULL that §5A's own gate
already declared uninterpretable, because H0 did not replicate. §7 gave two reasons
for that verdict — survivorship (34.8% of the pre-2021 high-DTC quintile is absent)
and coverage (583 of 5,616 eligible names, concentrated in large/mid caps). **The
lag correction touches neither.** It changes the numbers, not the reasons the
verdict was reached. Nothing was promoted on those numbers and nothing was killed by
them, so no authority state moves.

**The effect sizes are NOT re-quotable.** §5A already forbade quoting any SP1-A
effect size as unbiased on survivorship grounds; this adds a **second, independent
PIT reason**. No number from the §7 log or the report table may be cited — in a
successor study, an adjudication, a masterplan, or any user-facing surface — until a
re-run on a rebuilt panel replaces it. (The re-run happened on 2026-08-15 and the
ban still stands: it discharged this PIT reason and immediately found a **third**,
described in §7. Replacement was necessary but not sufficient.)

**What is deliberately NOT claimed.** A shifted entry produces genuinely different
events, not a monotone transform of the same ones, so no claim is made that a re-run
reproduces these numbers or their signs. The honest statement is directional: the
correction removes an advantage the study *already failed to exploit*, so the null is
if anything reinforced. Should a re-run instead flip H0 to negative-and-significant,
that is a **new finding requiring its own adjudication** — it would not
retroactively validate anything here.

### Standing rule for this class of correction

A prereg whose *data-availability convention* is later measured wrong is
**corrected in place, dated, with the retired convention left legible** — the
original is never rewritten and never silently replaced. The correction must state
that the retired rule was **measured wrong and in which direction**, never merely
"revised", and must answer explicitly whether each published result is affected in
its numbers, in its verdict, or in both. Superseding is reserved for changes to the
*design* — hypotheses, conditioners, horizons, universe, controls, statistics, or
the promotion bar. Recorded as `DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE`.
The complementary case — a post-outcome change that *does* move a design surface,
including a calendar that redefines what a horizon label measures — is §5C /
`DEC:PREREG-DESIGN-CHANGE-SUPERSEDES`.

## §5C. SUPERSESSION 1 — the price index is not a trading-day index (pre-run of THIS fix, 2026-08-15)

Committed BEFORE the code fix is applied and BEFORE this design is re-run. That
order is load-bearing. A weekday-only counterfactual was already computed in the
2026-08-15 §7 entry (counterfactual D: H0 21-row **+0.702pp / t 1.92 / q 0.0551**).
That measurement is why this cannot be an in-place amendment: the outcome of the
proposed change is already known. Applying the filter as a correction of SP1-A,
having seen it halve the t, is the goalpost move prereg immutability exists to
forbid. This section locks the successor design so the official run cannot be
chosen after further fishing.

### RULING — supersede; do not amend in place

**Supersession.** This is a design change. §5B's standing rule
(`DEC:PREREG-DATA-CONVENTION-CORRECTED-IN-PLACE`) reserves supersession for
changes to the *design* — hypotheses, conditioners, **horizons**, **universe**,
controls, statistics, or the promotion bar. Two of those surfaces move:

- **Horizons.** SP1-A applied `HORIZONS = (21, 63)` as positional row offsets on
  a calendar-union index. A 21-row step spanned exactly 15 weekday sessions; a
  63-row step spanned exactly 45. After this fix, `HORIZONS` **keeps its numeric
  labels** and those labels become **true NYSE sessions**. That is a different
  estimand — a different forward-return window — not a gloss on the same one.
- **Sample.** Restricting the index to NYSE sessions changes which dates
  `searchsorted` returns and which settlements survive `MIN_NAMES_PER_DATE`.
  Counterfactual D used 188 entry dates against the contaminated run's 193.

What does **not** move: hypotheses H0/H1/H2; the price-action conditioner
(trailing 63-session return percentile); the universe *of names* (FINRA listed ∩
ADV ≥ 100k ∩ yahoo close — the 35 non-equity files are not study names);
within-date demeaning; Newey-West t / split-half / BH-FDR; the promotion bar
(≥5pp, q ≤ 0.10, both halves sign-stable, n ≥ 300 per side).

**Why this is not a data-availability convention.** A data-availability
convention answers "when is a fact knowable?" The lag correction was that. The
price-index calendar answers "what is a day?" and "what is a 21-day horizon?"
Those are design parameters of the experiment. The original prereg said "21d and
63d" and "first trading day" — the *intent* was trading days — but the study
that *ran* used a different estimand. Correcting the implementation changes the
measured window from 15/45 weekday sessions to 21/63. That is a new experiment,
not a corrected gloss on the same one.

**Why the lag-correction licenses do not apply.**

1. The lag correction made the test strictly harder and was not authored by
   looking at SP1 outcomes (PR #5705). This change was discovered by looking at
   SP1 outcomes and seeing t drop from 3.06 to 1.92. That is exactly the
   goalpost hazard.
2. "Nobody moves a goalpost toward themselves" does not license this: the
   direction the t moves is already known, and applying it as an amendment
   would let the official record absorb a seen result.
3. In-place amendment would rewrite what "21d" meant in the 2026-08-05 and
   2026-08-15 entries, destroying the audit trail of what those runs actually
   measured.

**SP1-A is not rewritten.** Its two published runs stay the record of the
contaminated-calendar design. Their numbers remain non-quotable. This section
pre-registers the successor **SP1-B**. Recorded as
`DEC:PREREG-DESIGN-CHANGE-SUPERSEDES`.

### SP1-B, exactly

- **Universe:** same as SP1-A — FINRA exchange-listed ∩ not sentinel-capped ∩
  ADV ≥ 100k ∩ has a `data/yahoo/` close at the entry date. Non-equity files in
  `data/yahoo/` are not study names. Expected name count is the 2026-08-15
  SP1-A count minus the handful of non-equities that overlapped (counterfactual
  D: 1,723 → 1,718 if only those files are dropped; NYSE intersection may move
  it slightly).
- **Price index:** the wide close panel is restricted to **weekday NYSE
  sessions**. Implementation: `load_prices()` intersects the unioned index with
  `lib/nyse_calendar` (house helper: `session_rows`). Weekend rows contributed
  by crypto / FX / futures must be **0**. Rows that are not NYSE sessions
  (weekends *and* full-day holidays) must be **0**.
- **Entry:** first NYSE session at/after `knowable_date` (8 NYSE sessions after
  settlement, stored column). The binding clause is unchanged; on a trading-day
  index, `searchsorted` now rolls forward off a weekend rather than landing on
  it.
- **Horizons:** 21 and 63, **true NYSE sessions**. `HORIZONS` keeps its numeric
  labels. A 21-row step on the filtered index is 21 sessions; a 63-row step is
  63. The trailing conditioner `pos - 63` is likewise 63 sessions. We do **not**
  relabel to (15, 45) to preserve the old window — that would preserve the bug.
- **H0 / H1 / H2:** unchanged from §5A, including H2's pre-declared expectation
  of null and the H0-must-replicate-negative-and-significant interpretability
  gate.
- **Statistics / promotion bar:** unchanged from §5 / §5A.

### Pre-declared expected outcome

This is **not a blind test**. Counterfactual D in the 2026-08-15 §7 entry
already measured a weekday-only index (drop the 35 non-equity files; no
NYSE-holiday intersection) at H0 21-row: **+0.702pp / t 1.92 / q 0.0551**,
216,488 events, 188 entry dates. SP1-B's official run is expected to land in
that neighborhood:

- H0 remains **POSITIVE** (wrong direction vs Hong-Li-Ni-Scheinkman-Yan).
- H0 does **not** clear the §5A replication gate (negative AND q ≤ 0.10).
- No test clears the promotion bar (≥5pp, q ≤ 0.10, both halves, n ≥ 300).
- `calendar_audit` reads **0 weekend rows** and **21/63 true sessions**.

A result in that neighborhood is **confirmation of a seen counterfactual, not a
discovery**, and remains non-quotable (survivorship, §5A). A material deviation
— H0 flipping negative-and-significant, or any |mean| ≥ 5pp — is a **new
finding requiring its own adjudication** and does not retroactively validate
SP1-A.

### Citation ban

**Not lifted.** The 2026-08-15 §7 entry listed three independent reasons. This
supersession, once run, discharges only the third (calendar). Survivorship
(§5A) is unfixed — the named fix is still a delisting-inclusive panel
(`collectors/edgar_delisting.py` + `edgar_deadname_prices.py`). The PIT lag is
already discharged. No effect size from SP1-B may be cited in a successor
study, an adjudication, a masterplan, or any user-facing surface.

### What this does not do

- Does not lift the citation ban.
- Does not file a `DO_NOT_REBUILD` row.
- Does not change sibling studies that glob `data/yahoo/` or treat a DataFrame
  row offset as a trading-day horizon. Those need their own prereg if they are
  the same class (wide-panel union of every yahoo file + positional horizons).
- Does not rebuild the FINRA panel (already on the 8-session rule).

## §6. Graveyard seeded at charter

- **Fused short-pressure score** — forbidden by §3 regardless of any result.
- **Any short-sale recommendation or borrow-cost-as-execution-advice** — outside
  the lobe charter; would need a new charter and its own constitution work.
- **"Squeeze" as user-facing vocabulary** — banned; `DO_NOT_REBUILD` already
  forbids shortening a flow reading to "short squeeze".
- **Borrow fee as a continuous in-universe ranking factor** — killed at build
  time by trap 3, before any outcome was measured.
- **Utilization** — not derivable from this feed. Availability change is a proxy
  and must be labelled as one.
- **Letting `short_interest` into the IC scorecard as a side effect** — the panel
  makes it possible; doing it silently would grant an ungraded leg authority.
  Separate, gated change.

## §7. Status log

- 2026-08-05: Data spine built (IBKR borrow collector; FINRA 2018→now panel
  backfill; display-tier axes module; 20 tests, all guards mutation-verified). Two
  believed-blocked data sources unblocked. Study frozen, not run.
- 2026-08-05: Amendment 1 committed pre-outcome (revisions/options/borrow
  conditioners not historically available; price-action substituted).
- 2026-08-05: **SP1-A RUN — NULL.** 47,807 events, 120 entry dates, 641 tickers,
  2018-01-22 → 2026-04-10, returns demeaned within date.
  `reports/sp1-short-pressure.md`, `data/research/sp1_short_pressure.json`.

  **H0 does not replicate.** High days-to-cover *out*performed low (+0.37pp 21d /
  +0.79pp 63d, t 1.22 / 1.09, q 0.45 / 0.82) — opposite sign to the published
  result and not significant. Per §5A's own gate, the branch tests are therefore
  **uninterpretable**, and that is the finding. H1 (bearish branch) came out
  positive — opposite to hypothesis — and null. H2 (squeeze branch) reached
  q=0.09 at 63d but its 21d sibling flips sign across halves, its halves differ
  ~8× (+0.28 / +2.19), and 1.28pp sits far below the ±5pp promotion bar. Its
  pre-declared expectation was null; it is null.

  **This does not overturn the published result — this universe cannot test it.**
  Three measured reasons, all pushing the same way: 34.8% of the pre-2021
  high-DTC quintile is gone from the panel by 2025 and the price panel is the
  CURRENT universe (so the names that went to zero are absent, biasing H0
  positive); coverage is 583 of 5,616 eligible names, concentrated in large/mid
  caps by quintile {3.2, 13.4, 19.2, 12.6, 7.2}%, while the documented effect
  lives in small and illiquid names; and the sample is entirely post-publication.
  The sort itself is alive (5.4× top/bottom spread vs 7.8× in the full universe),
  so this is a population problem, not a dead signal.

  **No DO_NOT_REBUILD row is filed.** Nothing was killed: the construction was
  not testable on this price panel. The named fix is a delisting-inclusive panel
  (`collectors/edgar_delisting.py` + `edgar_deadname_prices.py` already exist) and
  a wider universe. Until then short pressure stays display-tier context, which is
  where §3 already put it.

- 2026-08-14: **AMENDMENT 2 committed POST-outcome (§5B) — the entry rule's
  publication lag was measured EARLY, not merely revised.** `knowable_date` =
  settlement + 10 calendar days landed before the figure was public on every
  settlement checkable, and before our own collector's capture date on all three in
  the history store: it manufactured look-ahead at the publication boundary. Rule
  corrected to the 8th NYSE session after settlement, one definition in
  `lib/finra_knowable.py` (PR #5705). Measured blast radius: **146 of 205 settlement
  entry dates move 1–3 sessions LATER on rebuild, 0 move earlier** — the defect was
  strictly one-directional.

  **The SP1-A verdict above stands** — §7's two stated reasons for it (survivorship,
  coverage) are untouched by the lag, and the correction makes the test strictly
  harder. **Its effect sizes are now doubly non-quotable** (survivorship per §5A,
  plus this PIT defect) and no number in the entry above may be cited until a re-run
  on a rebuilt panel replaces it. The live panel still carries the retired rule —
  `data/finra/short_interest_panel_coverage.json` records `"knowable_lag_days": 10`.
  The study picks the correction up with no code change
  (`sp1_short_pressure_study.py:78` reads the stored column), so the trigger is a
  rebuild of `data/finra/short_interest_panel.parquet` — **which nothing does
  automatically**: `scripts/backfill_finra_short_interest.py` is in no workflow, so
  the panel keeps the retired rule until a person runs it. Whoever next needs an SP1
  number owns the rebuild + re-run as one step. **No live surface is affected:**
  `engine/short_pressure.py` is imported only by its own tests and the SP1 study
  script — built-but-unwired — so the hazard is ordering, not exposure. The first
  consumer to wire `asof_slice` into a surface must rebuild the panel FIRST or it
  ships look-ahead on day one. No `DO_NOT_REBUILD` row is filed: nothing was killed
  and no authority state moves.

- 2026-08-15: **SP1-A RE-RUN on the rebuilt panel — §5B's obligation is DISCHARGED.
  Verdict UNCHANGED: still a NULL.** Panel rebuilt with the corrected writer
  (`lib/finra_knowable.py`, PR #5705 — armed and still unmerged when this ran, so the
  writer was applied from its branch; the same provenance convention §5B used):
  206 settlements, 3,888,611 rows, 2018-01-12 → 2026-07-31, 48,679 tickers. The
  committed sidecar flips `"knowable_lag_days": 10` → `"knowable_lag_sessions": 8`.
  The study took the correction with **no entry-logic change**, exactly as §5B
  predicted — it reads the panel's stored `knowable_date`. Artifacts regenerated:
  `reports/sp1-short-pressure.md`, `data/research/sp1_short_pressure.json`.

  **§5B's blast-radius prediction is confirmed against the real panel** (it was
  computed over a reconstructed schedule and said so). Of the 115 settlements
  admitted under **both** conventions, 81 (**70.4%**) move later — +1 session ×4,
  +2 ×47, +3 ×29, +4 ×1 — 34 (29.6%) are unchanged, and **0 move earlier**. §5B
  predicted 71.2% / 0. The defect was strictly one-directional, as claimed.

  **H0 still does not replicate — it is POSITIVE.** 222,367 events, 193 entry dates,
  1,723 tickers, 2018-02-12 → 2026-06-10, median 1,186 names/date. H0 `+0.782pp`
  (NW t 3.06, q 0.0022) at the 21-row horizon and `+0.902pp` (t 1.29, q 0.2366) at
  63-row; H1 `+0.241` / `+0.663`; H2 `+0.039` / `+0.267`. §5A's gate requires H0
  **negative and significant**, so the branch tests stay uninterpretable and SP1-A
  remains a NULL. **No `DO_NOT_REBUILD` row is filed** — nothing promoted, nothing
  killed, no authority state moves.

  **H0 is now significant in the WRONG direction, and that is NOT a new finding.**
  §5B reserved adjudication for a flip to negative-and-significant; this is the
  opposite pole, and it is adjudicated here as **explained, not discovered**. Two
  confounds were isolated by changing one input at a time:

  | run | lag | price calendar | events | entry dates | H0 21-row |
  |---|---|---|---|---|---|
  | 2026-08-05 published | retired +10d | as-is | 47,807 | 120 | +0.372, t 1.22 |
  | counterfactual B | retired +10d | as-is | 139,349 | 121 | +0.556, t 1.49 |
  | **2026-08-15 re-run** | **corrected 8s** | as-is | 222,367 | 193 | **+0.782, t 3.06** |
  | counterfactual D | corrected 8s | weekday-only | 216,488 | 188 | +0.702, **t 1.92** |

  1. **Universe.** `data/yahoo/` grew **739 → 2,268 files** between the two runs
     (study tickers 641 → 1,723). Run B — retired lag, today's universe — recovers
     most of the effect-size move, and reproduces the published run's entry-date
     count (121 vs 120), which is what licenses it as a faithful counterfactual.
  2. **The price index is not a trading-day index — a THIRD defect, independent of
     the lag and of survivorship.** `load_prices()` unions every file in
     `data/yahoo/`, including 35 non-equities that trade on weekends (`BTC-USD`,
     `ETH-USD`, `SOL-USD`, 16 FX pairs, 13 futures). Measured on this run: **868 of
     3,041 index rows in the event window (28.5%) are weekend rows**, from 36 of
     2,112 columns. Removing only those files costs **zero** study names
     (1,723 → 1,718) and takes t from 3.06 to **1.92**.

  **That third defect has two consequences, both pre-existing, both undisclosed
  until now.** (a) Horizons are applied as **positional row offsets**
  (`px.iloc[pos + h]`), so a 21-row step spans exactly **15** weekday sessions and a
  63-row step exactly **45** — every horizon label in the 2026-08-05 entry above and
  in this one is off by 5/7. (b) When the retired **calendar**-day rule landed on a
  weekend, `searchsorted` returned that weekend row — it *is* in the index — leaving
  2–3 priced names, so `MIN_NAMES_PER_DATE` dropped the settlement silently. That is
  why the published run used **120 of 205** settlements and this one uses **193 of
  206**: the retired rule lost **41%** of its sample to this, evenly across all nine
  years. **The sample rescue is an incidental side-effect of the lag fix, not a
  property of the lag**, and `120 entry dates` sat in the published report the whole
  time reading as normal.

  **CITATION BAN NOT LIFTED — now three independent reasons.** §5B's PIT reason is
  discharged by this rebuild. Survivorship (§5A) is untouched: 34.6% of the pre-2021
  high-DTC quintile is still gone by 2025 and the named fix (a delisting-inclusive
  panel — `collectors/edgar_delisting.py` + `edgar_deadname_prices.py`) is still
  unbuilt. The calendar defect is the third. **No effect size from this run may be
  cited either** — successor study, adjudication, masterplan, or user-facing surface.

  **The calendar defect is deliberately NOT fixed here.** Applying it post-outcome,
  having seen that it moves t from 3.06 to 1.92, is precisely the goalpost move
  prereg immutability exists to forbid — and unlike the lag correction it is **not**
  a data-availability convention: it changes the sample and the horizon definitions,
  i.e. the design. Per §5B's own standing rule that is reserved for supersession,
  not in-place amendment, so it needs its own pre-registration. Recorded here so the
  next actor inherits it rather than rediscovering it.

  **DISCHARGED as a pre-registration obligation by §5C (same day).** The successor
  study is SP1-B. This entry is left intact so the contaminated-calendar numbers
  stay attributable to the design that produced them.

  **Report generator hardened (not entry logic).** The 2026-08-05 template hardcoded
  that run's effect sizes into its **prose** while the table was computed, and
  hardcoded a verdict reading "sign is positive, not significant" — so this re-run
  would have emitted a table and a narrative contradicting each other, under a
  verdict line that had just stopped being true. Every number in the prose is now
  derived from `results`; the report additionally prints the panel's lag convention
  (read from the sidecar, never assumed) and a measured calendar audit, so neither
  the convention nor the horizon distortion can go unstated again.

- 2026-08-15: **§5C SUPERSESSION 1 committed — SP1-B pre-registered; NOT YET RUN.**
  The trading-day price-index fix is locked in §5C before any code change and
  before any official re-run. Counterfactual D in the entry above is the
  *expected* neighborhood, not a result of this study. Official numbers follow
  in a later §7 line after the run. Citation ban still stands (survivorship
  unfixed).

  **DISCHARGED by the next entry — the official run happened in the same
  session, after this line and after the code change.** The commit order is
  the receipt: prereg → filter → results.

- 2026-08-15: **SP1-B RUN on the NYSE-session price index — §5C's official
  run. Verdict UNCHANGED: still a NULL. Confirmation of the seen
  counterfactual, not a discovery.** Artifacts regenerated:
  `reports/sp1-short-pressure.md`, `data/research/sp1_short_pressure.json`.
  Commit order on this change: (1) §5C + `DEC:PREREG-DESIGN-CHANGE-SUPERSEDES`
  with no code and no run, (2) `restrict_to_nyse_sessions` + tests, (3) this
  log and the artifacts.

  **`calendar_audit` after the fix:** `weekend_rows_in_event_window` = **0**
  of 2,085 index rows in the event window; a 21-row step spans **21** weekday
  sessions and a 63-row step spans **63**. The horizon labels are true NYSE
  sessions.

  **H0 still does not replicate — it is POSITIVE.** 229,486 events, 200
  entry dates, 1,715 tickers, 2018-01-25 → 2026-05-12, median 1,183
  names/date. H0 `+0.749pp` (NW t 2.09, q 0.0363) at 21 sessions and
  `+0.959pp` (t 1.01, q 0.4697) at 63 sessions. H1 `+0.281` / `+0.872`;
  H2 `+0.240` / `+0.735`. §5A's gate requires H0 **negative and
  significant**, so the branch tests stay uninterpretable and SP1-B is a
  NULL. No test is near the ±5pp promotion bar. **No `DO_NOT_REBUILD` row
  is filed** — nothing promoted, nothing killed, no authority state moves.

  **Against the pre-declared expected neighborhood (counterfactual D).**
  D measured H0 21-row `+0.702pp / t 1.92 / q 0.0551`, 216,488 events, 188
  entry dates, on a weekday-only index made by dropping the 35 non-equity
  files. Official SP1-B (NYSE-session intersection, holidays dropped too,
  `HORIZONS` as true sessions) landed at `+0.749 / t 2.09 / q 0.0363`,
  229,486 events, 200 entry dates. Same sign, same t-band, same failure of
  the replication gate and of the promotion bar. The window starts earlier
  (2018-01-25 vs the contaminated run's 2018-02-12) because `searchsorted`
  no longer lands on a thin weekend/holiday row, and ends earlier
  (2026-05-12 vs 2026-06-10) because a 21-session horizon needs more
  runway than a 15-session one. Entry-date count 200 vs D's 188 is a
  sample difference, not a material deviation: §5C reserved adjudication
  for H0 flipping negative-and-significant or any `|mean| ≥ 5pp`. Neither
  happened.

  **CITATION BAN NOT LIFTED.** This run discharges only the third of the
  three reasons (calendar). Survivorship (§5A) is untouched: 34.6% of the
  pre-2021 high-DTC quintile is still gone by 2025 and the named fix is
  still unbuilt. The PIT lag is already discharged. **No effect size from
  this run may be cited** — successor study, adjudication, masterplan, or
  user-facing surface. A result in the seen neighborhood is confirmation,
  not discovery.
