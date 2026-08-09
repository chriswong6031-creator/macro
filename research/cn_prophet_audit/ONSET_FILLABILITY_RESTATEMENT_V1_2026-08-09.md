# CN ONSET FILLABILITY RE-STATEMENT v1 — the onset book at prices you could get

**Program** CN LIMIT-MOVE ALPHA, Wave 3 / lane W3-C (masterplan §8 W2 item 3).
**Tier** Display / audit. MEASUREMENT ONLY. Nothing here promotes, ranks for size, gates,
admits, or reaches a live surface. No LLM is involved at any point.
**Instrument** `research/cn_prophet_audit/onset_fillability_restatement_v1.py`
**Frozen JSON** `research/cn_prophet_audit/ONSET_FILLABILITY_RESTATEMENT_V1_2026-08-09.json`
(this document mirrors it; every number below is read from it).

**Honest prior, written before the first number.** This is a measurement COMPLETION, not an
edge hunt. Wave 1 shipped two halves of one arithmetic and never joined them: lane L3 proved
the onset probabilities are real and ordered, lane L1 proved that a close is not a fill, and
nobody applied the second to the first. The expected outcome was that the edge concentrates
in the picks you cannot buy — that the model's best names are exactly the 一字 opens the
auction already took. **That is what was found, and that null cleanly measured IS the
deliverable**: it is the honest "what could you actually buy" curve the product needs in
place of a paper hit rate. Nothing here was reframed when it came back negative.

---

## DECISION SUMMARY

1. **The main-board onset book's paper edge does not survive the open. Not partially — not at
   all.** Across 90 cells (5 selection objects × 6 book sizes × 3 exit families), **every
   single implementable cell is net-negative in BOTH the fit and the holdout window.** In the
   fit window 52 of those 90 paper cells print a POSITIVE number; **all 52 flip negative** the
   moment unfillable opens are refused. The holdout had 8 positive paper cells; all 8 flip.
2. **The tax is concentrated exactly at the head of the book — where the model is most
   confident.** Main holdout entry availability by book size: **82.6% at K=1** rising
   monotonically to **97.9% at K=50**, against a market-wide baseline of **99.79%**. The
   single most confident pick of the day is unbuyable roughly one day in six; a random name
   is unbuyable one day in 480.
3. **The 连板 ladder states it most bluntly of all.** B0's four rungs, main holdout: fillable
   share **99.91% → 93.00% → 83.44% → 71.21%** as N goes 0 → 3+, with strict 一字 rising
   **0.022% → 13.53%**. Top-versus-bottom rung: **−28.7 pp of buyability.** The rung that
   predicts a board best is the rung you can least buy.
4. **What survives on the rate axis is about two thirds to three quarters.** Main board,
   P(limit-up close at T+1): paper → implementable survival ratio runs **0.556–0.768 (median
   0.649)** in the fit window and **0.698–0.819 (median 0.748)** in the holdout. Capture share
   survives worse — fit median **0.605**, holdout **0.704** — because the boards you miss are
   disproportionately the ones that happened.
5. **No implementable onset book is net-positive with any inferential support.** Of 180
   (board × cell × exit) combinations, 8 are positive in both windows — **all ChiNext, all
   with a fit-window date-clustered t of essentially zero** — and **0 clear a date-clustered
   t ≥ 2.0 in both windows.** The largest holdout date-clustered t over EVERY implementable
   cell in the study is **1.54**.
6. **ChiNext is barely taxed, and that is not good news.** Its book's entry availability runs
   **99.08–100.0%** across every ranker and K because its book does not select boards in the
   first place: 2.36% realized at K=10 against a 0.357% base. A censor cannot tax a selection
   that is not selecting.
7. **The censor is doing the work, and it is proved rather than asserted.** Permuting
   fillability within each session collapses the mean absolute paper-versus-implementable
   rate gap from **2.787 pp to 0.031 pp** (1.1% of the real gap) and the E1 return gap from
   0.374 pp to 0.007 pp. On the exemplar cell (main holdout, B1, K=10) the real gap is
   **−3.997 pp** and the corrupted gap is **−0.027 pp**, with availability reverting to the
   market-wide 99.79%.

**What this changes.** L3's top-K table is not wrong; it answers a question about closes. It
must never again be read as a book. The pairing below is the version that can face a desk,
and the honest headline is that **the implementable onset book is a losing book at every size
tested** — which is the same verdict L1 reached on the continuation side, now reproduced on
the selection side, on 90 cells per board instead of one family.

---

## COVERAGE RECEIPT (read before any number)

| Item | Value |
|---|---|
| Curated universe | **1,836 names modelled** of 1,842 store files, against a listed A-share market of ~5,400 |
| Store vintage | `data/china_stocks_raw`, **back-adjusted** (L1's price-basis correction), healed-events vintage **71,463 events** (branch `claude/cn-limit-w1-dataheal`) |
| zt_pool cross-check | 1,770 vendor-pool names, **29.0%** present in the raw store |
| ST cohort | 100 tickers excluded wholesale (`asof 2026-07-06`) — 1 present in the store |
| Panel | 4,981,168 bars, 4,843,577 live; limit-up closes main 50,421 / ChiNext 8,999 / STAR 878 |
| Complete-case coverage | **91.4%** of usable rows carry all six features (dominated by `f4_sector_heat`); sector coverage 93.68% |
| Survivorship | current listed universe only; a name that ran, collapsed and delisted contributes neither its run-ups nor its failures |

**The binding caveat, sharpened for this lane.** 一字 lives disproportionately in the
small-cap and ST names this store omits. **The censoring rates below are therefore the
OPTIMISTIC end of the market's true tax**, and falsifier F3 (the full ~5,400-name re-run)
hangs over this receipt as it does over every Wave-1/2 artifact.

---

## WHAT WAS INHERITED, AND WHAT THIS FILE ADDED

Everything about the panel, the exclusions, the PRIMARY limit-up definition, the 0.2%
cushion, the no-pooling rule, the ChiNext 2020-08-24 era restriction, the fit/calib/holdout
boundaries, the THIN gates, the five selection objects and the top-K tie rule comes from
`onset_calibration_v1.py` **by import**. The fillability censor, the strict 一字 test, the
three exit families, the locked-exit roll and the 15 bp round trip come from
`continuation_rider_v1.py` **by import**. This file adds exactly four things: the join, a
second (ex-ante) pick universe, the censoring taxonomy, and the corruption control.

**Boards.** Main and ChiNext are modelled because L3 models them. **STAR is THIN-SKIPPED** —
40 fit-core positives against the pre-registered floor of 150 (its 612 holdout positives do
not rescue it; the floor is on the fitting side). L3 built no STAR book, so there is no STAR
book to re-state. STAR is unmeasured here, not null.

**Splits (L3's, frozen).** Main: era from 2011-01-04, split 2021-11-26. ChiNext: era from
**2020-08-24** (never pooled across the band change), split 2024-10-25.

---

## PRE-REGISTRATION (frozen before the first number)

- **Two pick universes.** `U1_y_ok` = L3's own rows (live, complete-case, usable next bar) —
  the PRIMARY, and the one whose paper column must reproduce L3's published table.
  `U2_ex_ante` = the same rows WITHOUT the next-bar-usability filter — the set a desk can
  actually rank at T's close, and the only universe in which suspension censoring exists at
  all. Picks with no usable next bar are reported as censored, **never scored 0 and never
  scored 1**.
- **Books.** Per feature-date, rank by P̂ descending, ties by ticker ascending (L3's rule),
  take the top K. Rankers **B0, B1, B2, P1, P2**; K ∈ **{1, 3, 5, 10, 20, 50}** (10/20/50 are
  L3's published set so the paper column is checkable; 1/3/5 are desk-realistic sizes, and
  the fillability question bites hardest at the head of a book); windows **fit and holdout**.
- **Fillable** iff the T+1 bar is usable and `open[T+1] < limit_price[T+1] × (1 − 0.002)`.
  Unfillable opens are REFUSED, never modelled as fills.
- **Exits** E1 board-fail / E2 first-down-close / E3 time-stop-T+4, with L1's locked-exit
  roll (a scheduled exit open at or below limit-down cannot be sold; it rolls up to 10
  sessions, then closes at the last available close and is flagged).
- **One disclosed change to the STEP rule.** The exit walk is **closure-tolerant**: it steps
  to the immediately following LIVE bar with no calendar cap. W3-A measured that reusing
  v0's 10-calendar-day pair rule as a forward-chain step rule truncates every open window
  market-wide at a CNY / National-Day closure and force-closes it at a mark-to-market close.
  **The ENTRY pair rule stays v0's 10 days**, because it defines the population L3 and L1
  both measured. Both step rules are run and printed.
- **Complete-window books only** in every headline; still-forced trades are counted in their
  own block. **Censoring is two-sided:** a pick with no usable T+1 bar is excluded from the
  return book on the PAPER side as well as the implementable side. A paper book that priced a
  suspension placeholder's stale open would be the same class of fiction as buying a 一字.
- **Survival is a RATIO only where the paper number is positive.** Where the paper number is
  negative or straddles zero the pp difference is the statement. Paper and implementable are
  never blended.
- Wilson 95% on every rate; **date-clustered t beside per-trade stats on every return cell**;
  yearly era tables; THIN at n < 20; boards never pooled.
- **The corruption control and its expected outcome were written before it was run.**

---

## VERIFICATION GATES — all 11 PASS (the run exits non-zero if any does not)

| Gate | What it pins | Result |
|---|---|---|
| **L3 top-K parity** | the paper column against L3's published holdout top-K table, cell for cell | **PASS** — main 12/12 cells, ChiNext 4/4, zero mismatches (e.g. B1·K=10 main: published 11,350 rows / 1,882 hits / 16.581%, re-derived 11,350 / 1,882 / 16.5815%) |
| **Prefix-order pin** (internal) | that K=1/3/5 are prefixes of the K=10 book under L3's exact ordering | **PASS** — **26,105** (ranker, feature-date) groups across all four U1 scopes; zero non-monotone P̂ sequences, zero mis-ordered ties, zero non-contiguous rank runs |
| **L1 trade parity** | the restated exit walker against `continuation_rider_v1.process_ticker`, trade for trade, under L1's strict step rule | **PASS** — 230 tickers (deterministic 1-in-8), **18,777 trades compared, 0 mismatched, 0 missing, max abs return diff 0.0** |
| **y_ok agreement** | L3's panel pair rule against L1's **second code path** for the same rule | **PASS** — agreement on all 4,981,168 rows |
| **Exclusion-cause pin** | the re-derived exclusion cascade against `_ticker_arrays`' own counts | **PASS** — IPO 2,793 / ex-div 620 / zero-volume 133,781, both ways; **0 blocked bars left unclassified** |
| **Corruption control** | that the censor, not a coding artifact, produces the gap | **PASS** — collapse ratio 0.0112 against a pre-registered ceiling of 0.10 |

**What the external pin does NOT cover, stated plainly.** L3 published 16 of this file's 180
(board × cell × exit) combinations — main {B0,B1,B2,P1} × K{10,20,50} plus ChiNext K=10 only.
**No K < 10** (the head of the book, which is exactly where the tax-on-confidence claim
lives), no P2, no fit window, no ChiNext K ∈ {20,50}. The prefix-order pin closes the K < 10
hole **internally**: if within each (ranker, feature-date) the picks are ordered by P̂
descending with ties by ticker ascending and ranks are contiguous, then top-1 ⊂ top-3 ⊂
top-5 ⊂ top-10 by construction and the head rows are a prefix of externally pinned
membership. That is a weaker claim than an external check — it **inherits** L3's ordering, it
does not re-verify it — and it is labelled as such in the JSON.

**Two further limits of the pins.** The L1 trade-parity gate runs `closure_tolerant=False`
because that is the rule L1 published, so the tolerant walker used in every headline is
pinned only on the branch the two rules share; `step_rule_effect` prints the divergence
(895 / 2,023 / 2,616 windows on E1 / E2 / E3). And the y_ok gate is a **transcription check**,
not independent corroboration: both paths derive `pair_ok & nxt_live` from identical
exclusion masks. It is still worth having, because this file joins the two lanes row-wise and
a silent disagreement would misalign every pairing above.

The L1 parity gate is what makes the restated walker safe to use: L1 defines its entry book
inside a closure and cannot be imported, so the alternative to a gate is a silent divergence
in the one arithmetic this lane exists to apply.

**The exit code carries the gates.** `main()` walks every `pass` field in the gate tree — 11
of them — and returns non-zero if any is not exactly `True` (a `None`, meaning the gate did
not run, counts as a failure). A receipt whose gates fail is still written, so the failure is
inspectable, but the process reports it. Without this a future re-run against a drifted
dependency would write a same-named artifact with `pass: false` buried inside and exit green.

**Determinism.** Two consecutive `TZ=UTC` runs produce byte-identical JSON with
`generated_utc` and `runtime_sec` excluded. SHA-256 of the canonicalised payload, both runs:
`3195ff530f585d5690b4127601478cdd5c2e5221ddd21894e42cf1a55d528c57`. Runtime ~75–90 s.

---

## THE PAIRING — main board, HOLDOUT (U1, L3's own rows)

1,135 dates, 1,283,378 rows, base rate 1.204%, 15,455 positives available. `avail` = share of
picks offering a fillable open. **paper** is L3's published number; **impl** refuses the
unfillable opens.

| Ranker | K | **avail** | paper P | **impl P** | surv | paper capture | **impl capture** | surv |
|---|---|---|---|---|---|---|---|---|
| B0 | 1 | **82.64%** | 34.714% | **25.373%** | 0.731 | 2.549% | 1.540% | 0.604 |
| B0 | 10 | 92.73% | 16.846% | **12.028%** | 0.714 | 12.371% | 8.192% | 0.662 |
| B0 | 50 | 97.90% | 5.494% | 3.920% | 0.714 | 20.175% | 14.093% | 0.699 |
| **B1** | 1 | 91.98% | 25.727% | **21.073%** | 0.819 | 1.889% | 1.423% | 0.753 |
| **B1** | 10 | 93.96% | **16.581%** | **12.584%** | **0.759** | **12.177%** | **8.683%** | **0.713** |
| **B1** | 50 | 97.89% | 7.403% | 5.872% | 0.793 | 27.182% | 21.106% | 0.776 |
| B2 | 1 | **82.38%** | 34.361% | **24.599%** | 0.716 | 2.523% | 1.488% | 0.590 |
| B2 | 10 | 92.41% | 17.841% | **12.842%** | 0.720 | 13.103% | 8.716% | 0.665 |
| B2 | 50 | 97.81% | 7.121% | 5.509% | 0.774 | 26.147% | 19.786% | 0.757 |

Full 30-cell grid per (board, window, universe) is in the JSON under
`by_board.<board>.universes.<universe>.<window>.cells`.

**Rate-survival spread over all 30 holdout cells:** main **0.698 – 0.819** (median 0.748);
capture-survival **0.590 – 0.796** (median 0.704). Fit window is harsher: rate survival
**0.556 – 0.768** (median 0.649), capture **0.453 – 0.757** (median 0.605).

### ChiNext — HOLDOUT, 433 dates, base 0.357%

| Ranker | K | avail | paper P | impl P | surv |
|---|---|---|---|---|---|
| B1 | 1 | 99.31% | 4.157% | 3.488% | 0.839 |
| B1 | 10 | 99.75% | 2.356% | 2.246% | 0.953 |
| B2 | 1 | 99.08% | 6.236% | 5.594% | 0.897 |
| B0 | 10 | 99.77% | 1.062% | 0.903% | 0.850 |

Rate survival 0.831–1.000 (median 0.929). **ChiNext's book is nearly untaxed because it is
nearly not selecting** — 2.36% realized at K=10 is a 6.6× lift on a 0.357% base, but it is
not a board book in the sense the main board's is, and the 一字 population it would have to
pay for barely appears in its picks (0.028% of them).

**THIN on SUCCESSES, not only on trials.** A survival ratio is a ratio of two rates and
inherits the noise of the thinner numerator, which a trials-based flag cannot see: a ChiNext
K=1 cell carries 433 trials and can still rest on single-digit hits. Every survival block
therefore also carries a successes count against a pre-registered floor of 30. **Six of
ChiNext's 30 holdout cells are THIN on successes — B0·K1, B1·K1, B2·K1, P1·K1, P1·K3,
P2·K1 — and none of main's 60.** In particular **ChiNext P1·K=1 prints "survival 1.000" off
9 hits versus 9 hits**; that is not a measured survival and is now labelled as such in the
JSON. An interval on the ratio itself (bootstrap over feature-dates; the arms are nested and
positively dependent, so an independent-samples delta method would be conservative in an
un-quantified direction) is untested — it is in the ore ledger, not in this pass.

---

## THE RETURN AXIS — every paper number beside its implementable twin

Net of a 15 bp round trip, complete windows only. `dc-t` is the date-clustered t (each
feature-date collapsed to its own mean first, so the t counts sessions). For K=1 the
per-trade t and the date-clustered t coincide by construction — at most one trade per date —
and they do: −2.72 / −2.72 on the fit E1 cell below.

### Main board, B1, FIT window (in-sample — labelled as such)

| K | exit | **paper net** | **impl net** | Δpp | impl dc-t | impl n |
|---|---|---|---|---|---|---|
| 1 | E1 | **+0.528%** | **−0.405%** | −0.933 | −2.72 | 2,275 |
| 1 | E2 | +0.140% | −0.759% | −0.899 | −4.54 | 2,255 |
| 1 | E3 | **+0.621%** | **−0.492%** | −1.113 | −2.44 | 2,251 |
| 5 | E1 | +0.229% | −0.586% | −0.815 | −8.16 | 12,096 |
| 10 | E1 | +0.108% | −0.463% | −0.571 | −8.31 | 24,790 |
| 50 | E1 | −0.069% | −0.215% | −0.146 | −4.92 | 129,140 |

### Main board, B1, HOLDOUT

| K | exit | paper net | **impl net** | Δpp | impl dc-t | impl n |
|---|---|---|---|---|---|---|
| 1 | E1 | −0.523% | **−1.000%** | −0.477 | −3.59 | 1,036 |
| 1 | E3 | −0.499% | −0.882% | −0.383 | −2.33 | 1,035 |
| 5 | E1 | −0.487% | −0.762% | −0.275 | −6.23 | 5,231 |
| 10 | E1 | −0.414% | **−0.622%** | −0.208 | −6.84 | 10,628 |
| 10 | E3 | −0.301% | −0.517% | −0.216 | −3.84 | 10,605 |
| 50 | E1 | −0.248% | −0.315% | −0.067 | −5.02 | 55,412 |

**Read the Δpp column down the K axis.** The gap is **−0.93 pp at K=1 and −0.15 pp at K=50**
in the fit window, −0.48 pp and −0.07 pp in the holdout. The fillability tax is not a level
shift applied to the whole book; it is a tax on confidence, and it is largest exactly where
the operator's spreading math wants to concentrate.

**Census, not curation.** Main board, all 90 cells (5 rankers × 6 K × 3 exits):

| Window | cells | paper > 0 | impl ≤ 0 | **paper > 0 AND impl ≤ 0** |
|---|---|---|---|---|
| fit | 90 | 52 | **90** | **52** |
| holdout | 90 | 8 | **90** | **8** |

ChiNext: fit 64 positive-paper cells → 49 flip; holdout 46 → 5 flip.

**Risk texture of the implementable book** (main holdout, B1·K=10): win rate 41.13%, median
net −1.071%, worst trade **−35.35%**, 287 locked-exit rolls on E1. The roll is not decoration:
L1's worked example marked a naive −17.3% trade that actually cost −32.3%.

---

## ERA TABLE — main board, B1, K=10, E1 (yearly; the §0 gate)

| year | picks | fill% | paper P | impl P | **paper net** | **impl net** | impl dc-t |
|---|---|---|---|---|---|---|---|
| 2011 | 2,440 | 98.81 | 3.61% | 2.61% | −0.518% | −0.592% | −4.74 |
| 2012 | 2,430 | 97.65 | 5.88% | 4.13% | −0.495% | −0.512% | −3.65 |
| 2013 | 2,380 | 94.75 | 11.01% | 6.96% | **+0.164%** | −0.190% | −1.36 |
| 2014 | 2,450 | 92.82 | 13.06% | 7.30% | **+0.915%** | −0.210% | −1.29 |
| **2015** | 2,440 | **84.18** | **26.56%** | **15.38%** | **+2.995%** | **−0.542%** | −2.18 |
| 2016 | 2,440 | 96.84 | 9.34% | 6.94% | −0.410% | −0.528% | −2.92 |
| 2017 | 2,440 | 96.35 | 6.84% | 4.17% | −0.333% | −0.340% | −2.48 |
| 2018 | 2,430 | 97.65 | 5.35% | 3.71% | −1.002% | −1.015% | −6.69 |
| 2019 | 2,420 | 95.37 | 11.94% | 9.06% | −0.894% | −1.029% | −5.57 |
| 2020 | 2,420 | 92.52 | 18.93% | 14.07% | **+0.578%** | −0.106% | −0.44 |
| 2021 (fit) | 2,170 | 94.75 | 18.20% | 14.54% | **+0.242%** | **+0.057%** | 0.17 |
| 2021 (hold) | 260 | 90.77 | 19.23% | 12.71% | −0.482% | −0.543% | −1.07 |
| 2022 | 2,420 | 94.01 | 16.36% | 12.31% | −0.883% | −0.946% | −5.09 |
| 2023 | 2,410 | 96.85 | 10.75% | 8.65% | −0.515% | −0.761% | −5.49 |
| 2024 | 2,410 | 90.91 | 19.17% | 12.96% | −0.383% | −0.912% | −4.08 |
| 2025 | 2,430 | 93.46 | 19.05% | 15.15% | −0.012% | −0.107% | −0.59 |
| 2026 | 1,420 | 95.56 | 17.75% | 14.89% | −0.167% | −0.247% | −0.85 |

**2015 is the whole receipt in one row.** The hottest era in the sample prints the biggest
paper number in the study (+2.995%, a 26.56% hit rate) and has **the lowest fillability of
any year-row (84.18%)** — and it lands at **−0.542% implementable**. The two largest paper
years, 2015 and 2014, are also the two least fillable years among the positive-paper years
(84.18% and 92.82% against a 94.31% all-row mean). That co-movement is not universal — 2013
and 2021-fit are positive-paper at 94.75% fillability, slightly above the mean — so the
statement is about the big numbers, not about every sign. The implementable book is negative
in **16 of 17 year-rows**; the one exception (2021 fit, +0.057%) carries a date-clustered t
of **0.17**.

### ERA TABLE — the flip exemplar, main · B1 · K=1 · E1 (§0 gate 2)

The K=1 head of the book is where the paper-positive-to-implementable-negative claim is made,
so it gets its own yearly table rather than borrowing K=10's.

| year | picks | fill% | **paper net** | **impl net** | impl dc-t |
|---|---|---|---|---|---|
| 2011 | 244 | 92.62 | +0.007% | −0.659% | −2.33 |
| 2012 | 243 | 93.00 | −0.240% | −0.128% | −0.31 |
| 2013 | 238 | 83.19 | **+1.625%** | **+0.074%** | 0.18 |
| **2014** | 245 | **75.10** | **+3.476%** | **−0.190%** | −0.41 |
| **2015** | 244 | **77.46** | **+3.017%** | **−0.455%** | −0.85 |
| 2016 | 244 | 89.34 | −0.643% | −0.927% | −2.12 |
| 2017 | 244 | 86.48 | −0.355% | −0.166% | −0.49 |
| 2018 | 243 | 91.77 | −1.124% | −1.199% | −2.80 |
| 2019 | 242 | 91.32 | −1.080% | −1.183% | −2.20 |
| 2020 | 242 | 92.98 | +0.568% | −0.103% | −0.15 |
| 2021 (fit) | 217 | 93.09 | +0.710% | +0.626% | 0.91 |
| 2021 (hold) | 26 | 84.62 | −2.268% | −2.176% | −1.39 |
| 2022 | 242 | 91.32 | −2.410% | −2.301% | −3.57 |
| 2023 | 241 | 93.78 | +0.616% | −0.517% | −1.04 |
| 2024 | 241 | 88.80 | −0.754% | −2.315% | −3.74 |
| 2025 | 243 | 91.36 | −0.501% | −0.294% | −0.49 |
| 2026 | 142 | 97.89 | +1.441% | +1.384% | 1.61 |

Implementable is negative in **14 of 17 year-rows**. **2014 is the sharpest cell in the
study:** the single most confident pick of the day earns a paper **+3.476%** while a quarter
of those picks (24.9%) could not be bought at all, and what remained earned **−0.190%**. 2015
repeats it (+3.017% → −0.455% at 77.46% fillability). The three positive implementable years
— 2013 (+0.074%, t 0.18), 2021 fit (+0.626%, t 0.91) and 2026 (+1.384%, t 1.61, a partial
year of 142 picks) — none reaches |t| = 2.

---

## SECONDARY (a) — does model confidence correlate with unfillability? YES, near-monotonically

### By top-K bucket (main, holdout; market-wide baseline 99.79% fillable, 0.21% 一字)

| Ranker | K=1 | K=3 | K=5 | K=10 | K=20 | K=50 |
|---|---|---|---|---|---|---|
| B0 fillable | **82.64%** | 86.99% | 89.57% | 92.73% | 95.42% | 97.90% |
| B0 一字 | **8.02%** | 6.14% | 4.97% | 3.44% | 2.04% | 0.93% |
| B1 fillable | 91.98% | 91.63% | 92.62% | 93.96% | 95.76% | 97.89% |
| B2 fillable | **82.38%** | 86.29% | 88.88% | 92.41% | 95.25% | 97.81% |
| B2 一字 | **8.19%** | 6.46% | 5.36% | 3.57% | 2.14% | 0.97% |

Wilson 95% on the B0·K=1 cell: [80.33%, 84.74%], n = 1,135 — the deviation from the 99.79%
baseline is **−17.15 pp** and nowhere near its interval. **Every ranker, at every K, is below
the market baseline, and the deficit shrinks NEAR-monotonically as the book widens — B1
reverses once, at K=1 → K=3 (91.982% → 91.630%), which the row above shows directly.** B0 and
B2 are strictly monotone across all six sizes. The reversal is 0.35 pp inside a
17-pp-scale effect; it changes nothing about the direction or the magnitude, and it is named
here rather than smoothed over.

### By P̂ decile (main, holdout)

| Model | bins | top-vs-bottom fillable | shape | monotone? |
|---|---|---|---|---|
| B1 | 9 | **−1.63 pp** | 99.978% (P̂ 0.30%) → 98.344% (P̂ 4.56%); 一字 0.009% → 0.470% (**52×**) | strictly |
| B2 | 10 | **−1.73 pp** | 99.978% → 98.253%; 一字 0.012% → 0.487% | **two reversals** |
| **B0** | 4 | **−28.70 pp** | **99.91% → 93.00% → 83.44% → 71.21%** across N = 0/1/2/3+; 一字 **0.022% → 2.007% → 7.205% → 13.527%** | strictly |

**Near-monotone, stated precisely.** B1's nine deciles and B0's four rungs fall strictly. B2
reverses twice — decile 3 → 4 (99.9582% → 99.9616%) and decile 7 → 8 (99.9133% → 99.9297%),
using the JSON's own 0-based decile ids — both inside the fourth decimal place of a
percentage, on a −1.73 pp effect. No trend test was run (see the ore ledger); the direction
is read off the printed sequence and the reversals are named rather than smoothed over.

The decile view is diluted — 99.8% of the panel is ordinary N=0 rows — and the direction is
the signal, not the magnitude. **B0 states it undiluted** because its four distinct values
ARE the 连板 ladder: L3's own reliability rule (distinct values as bins when a model has fewer
values than requested bins) is reused here, and without it `qcut` collapses the ladder to a
single bucket and reports the benchmark as structureless. **The hypothesis is confirmed for
the constructions tested: the model's most confident rows are the least buyable, and the
mechanism is the ladder, not the six features.**

---

## SECONDARY (b) — the survivor book: is ANY implementable onset book net-positive in both windows?

**No cell clears the bar.**

| | |
|---|---|
| (board × cell × exit) combinations evaluated | **180** |
| positive net in BOTH fit and holdout | **8** (all ChiNext) |
| **clearing date-clustered t ≥ 2.0 in both windows** | **0** |
| largest holdout date-clustered t over EVERY implementable cell | **1.54** |

The 8 two-window positives, in holdout-t order, top three:

| board | cell | exit | fit net / dc-t | holdout net / dc-t |
|---|---|---|---|---|
| chinext | B2·K=50 | E3 | +0.003% / **−0.07** | +0.229% / 1.29 |
| chinext | B2·K=3 | E2 | +0.010% / **−0.09** | +0.394% / 1.16 |
| chinext | B1·K=50 | E3 | +0.004% / **−0.06** | +0.215% / 1.10 |

Every one of them has a fit-window date-clustered t indistinguishable from zero. This is the
shape of a coin-flip census, not of a survivor: with 180 combinations, 8 sign-agreements at
|t| < 1.3 is what noise looks like. **Per the ore law this closes the constructions tested and
nothing else** — see the ledger.

**And the era tables finish them off.** §0 gate 2 requires a yearly sign table for every cell
a receipt names, so one is cut for each of the 8 (both windows) — ChiNext's era runs
2020-08-24 onward, giving 5 fit years and 3 holdout years:

| cell · exit | fit years positive | **holdout years positive (of 3)** |
|---|---|---|
| B0·K=20 E3 | 2021, 2023, 2024 | **2025 only** |
| B0·K=50 E3 | 2021, 2023, 2024 | **2025 only** |
| B1·K=50 E3 | 2020, 2021, 2024 | 2025, 2026 |
| B2·K=3 E2 | 2023, 2024 | **2025 only** |
| B2·K=50 E3 | 2021, 2023, 2024 | 2025, 2026 |
| P1·K=1 E2 | 2021, 2023, 2024 | 2024, 2025 |
| P2·K=3 E2 | 2021, 2023, 2024 | **2025 only** |
| P2·K=5 E3 | 2020, 2021, 2023 | **2025 only** |

**All 8 are positive in 2025, and 5 of the 8 are positive in NO other holdout year.** Not one
is a book that worked across the holdout; each is one good year inside three. Combined with
fit-window t-statistics of |t| ≤ 0.38, the two-window sign agreement is an artifact of a
single ChiNext year, and the census reads as a clean null rather than as eight near-misses.

---

## SECONDARY (c) — censoring composition: why a pick could not be bought

Denominator = all picks (main holdout, K ≤ 50, all rankers).

| Category | U1 (L3's rows) | U2 (ex-ante) |
|---|---|---|
| fillable | 277,839 (97.92%) | 277,523 (97.46%) |
| **unfillable — strict 一字** | 2,595 (0.915%) | 2,595 (0.911%) |
| **unfillable — limit at the open, not 一字** | 3,316 (1.169%) | 3,314 (1.164%) |
| **no entry — suspended (zero-volume bar)** | — (invisible by construction) | **316 (0.111%)** |
| no entry — exchange closure (CNY / National Day) | — | 750 (0.263%) |
| no entry — ex-div suspect | — | 2 |
| no entry — store edge (last bar) | — | 250 (0.088%) |

**"Suspended" needed care and nearly produced a false zero.** This store does not drop a 停牌
session — it carries a **zero-volume placeholder bar** (133,781 of them in window), which v0's
exclusion cascade then marks not-live. A taxonomy that only looked for MISSING bars would
have printed "suspensions: 0" while a hundred thousand suspension bars sat in the store under
another name. The cascade is unpicked here so every censored pick names its own cause, and
the unpicking is pinned against `_ticker_arrays`' own counts (gate above); **0 blocked bars
were left unclassified.**

Two further store facts worth carrying forward: only **23** short suspensions in 4.98 M rows
are silently *bridged* by v0's 10-calendar-day pair rule (so that rule is not quietly
stitching over halts), and closure tolerance in the exit walk recovers **895 / 2,023 / 2,616**
complete windows on E1 / E2 / E3 that the strict 10-day step rule would have force-closed at
a mark-to-market price. On the flagship cell the two step rules give −0.622% (tolerant, 44
excluded) versus −0.637% (strict, 88 excluded) — the direction W3-A predicted, at a tenth of
W3-A's magnitude because these exits are short.

### The ex-ante universe: L3's resolution-conditioned denominator is real but MINOR here

L3's own JSON flags that conditioning on next-bar usability is a filter a desk at T's close
cannot apply. Measured, at B1·K=10:

| board | window | universe | picks | ungraded | avail | paper P | impl P | impl E1 net |
|---|---|---|---|---|---|---|---|---|
| main | holdout | U1 | 11,350 | 0 | 93.96% | 16.581% | 12.584% | −0.622% |
| main | holdout | **U2** | 11,390 | **59** | 93.46% | 16.601% | 12.598% | −0.621% |
| main | fit | U1 | 26,460 | 0 | 94.70% | 11.822% | 7.874% | −0.463% |
| main | fit | **U2** | 26,470 | **357** | 93.37% | 11.910% | 7.922% | −0.463% |

**A printed null:** dropping the look-ahead moves entry availability by 0.5–1.3 pp and the
book's expectancy by ≤ 0.001 pp. For the ONSET question the resolution-conditioned
denominator is an honest caveat, not a material distortion. (It is not thereby closed for
other questions — a limit-DOWN or delisting study would look very different.)

### A defect this receipt fixed rather than footnoted: the U2 paper book priced 停牌 opens

The first cut of this instrument masked censored picks out of the **implementable** book and
not out of the **paper** book. `walk_trades` accepts any finite positive `open[T+1]`, and a
zero-volume suspension placeholder bar carries one — so the U2 paper return book was scoring
a small number of trades at **stale placeholder opens**, in direct violation of this file's
own pre-registration ("censored, never scored"). It could not touch U1, where every pick has
a usable next bar by construction.

Rather than disclose it, the mask was made two-sided and the instrument re-run; downstream
waves read the frozen JSON, and a contaminated artifact with a caveat is worse than a clean
one. **Every U2 number the mask touched now prints its own delta** in
`books.<rule>.paper_censored_excluded`. The scale:

| board | window | cell (full pick set) | trades removed | share | paper mean net |
|---|---|---|---|---|---|
| main | fit | B1·K=50 E1 | 568 of 130,520 | 0.435% | −0.069% → **−0.070%** |
| main | holdout | B1·K=50 E1 | 197 of 56,729 | 0.347% | −0.245% → **−0.249%** |
| chinext | fit | B1·K=50 E1 | 115 of 50,402 | 0.228% | −0.087% → **−0.085%** |
| chinext | holdout | B1·K=50 E1 | 54 of 21,635 | 0.250% | −0.014% → **−0.014%** |

**360 cell × rule combinations were touched, all of them U2; the largest absolute move on any
paper number anywhere in the study is 0.055 pp** (ChiNext·U2·fit·B2·K=1·E2). U1 removals: 0,
and every U1 number in this receipt is unchanged. The correction is immaterial to every
conclusion and is reported anyway, because "immaterial" is a finding, not an excuse.

---

## THE CORRUPTION CONTROL — the finding's own falsifier

**Design, written before it was run.** Fillability flags are permuted WITHIN each feature-date
across every candidate row (frozen seed 20260809). This preserves each session's market-wide
fillable share exactly — the 一字 intensity of a day is a real market fact and must survive —
and destroys only the association between P̂ rank and buyability. **Pre-registered
expectation:** the gap collapses toward zero and the survivor book degrades toward the
unconditional book. **A gap that survived the permutation would mean the censor is a coding
artifact and the whole finding is void.**

| Statistic (120 primary-universe cells) | real | **corrupted** | collapse |
|---|---|---|---|
| mean absolute paper→impl **rate** gap | 2.787 pp | **0.031 pp** | **1.1%** |
| mean absolute paper→impl **E1 net** gap | 0.374 pp | **0.007 pp** | 1.9% |

Exemplar, main holdout B1·K=10:

| | entry avail | paper P | impl P | rate gap | E1 net gap |
|---|---|---|---|---|---|
| real | 93.96% | 16.5815% | **12.5844%** | **−3.997 pp** | **−0.208 pp** |
| corrupted | **99.789%** | 16.5815% | 16.5548% | **−0.027 pp** | **+0.006 pp** |

Under permutation the book's entry availability reverts to the market-wide rate (99.789% vs
the panel's 99.792%) and the implementable book becomes the paper book. **PASS.**

---

## WHAT THIS DOES NOT ESTABLISH

- **It does not establish that no onset book can be traded.** It establishes that the five
  L3 objects, at six book sizes, with three daily-bar exit families, at the printed T+1 open,
  lose after the censor — on this universe, in both windows.
- **It does not price a limit order, a partial fill, or an auction queue.** Every fill here
  is all-or-nothing at the printed open. A desk that rests a bid below the 一字 price is
  playing a different, unmeasured game.
- **It does not measure intraday.** The foresight premium W3-A sized (+2.03% at H=10) lives
  inside windows that daily-scheduled exits cannot collect; nothing here can see it.
- **It does not close the ranking question.** A ranker trained on P(board AND fillable),
  rather than on P(board), has not been built. This lane measures the tax; it does not try to
  dodge it.
- **It does not speak for STAR** (THIN-SKIPPED at the fitting gate) or for the ~3,560 names
  outside the curated store.
- **The fit-window columns are in-sample** and are labelled as such everywhere; they are here
  because a survivor claim needs both windows, not because they are evidence on their own.

---

## ORE LEDGER — untested variants (19)

Under the ORE LAW a null on one construction never closes a hypothesis. Nothing below is
claimed dead; all of it is unmeasured.

**Entry constructions (7)** — limit-order-at-open fills (a resting bid below the 一字 price is
a different, sometimes-filled object); partial fills (needs 集合竞价成交, purchased
2026-08-09); auction-participation entries (queueing INTO the 9:25 call rather than reading
its result — no history exists anywhere, collector P5 must start first); intraday first-touch
entries (blocked on minute bars, purchased, not yet wired); seal-break (开板) re-entries on a
pick that opened locked and then unsealed — the fillable moment daily bars cannot see but
首次封板时间 partly can; VWAP / first-N-minutes entries as a fill proxy; next-day deferral of a
refused pick to T+2 rather than refusal.

**Exit constructions (3)** — trailing stops, limit-target exits, seal-stability and intraday
stops; roll caps other than L1's 10 sessions; H > 1 onset horizons (this lane grades the same
one-bar outcome L3 modelled).

**Selection constructions (4)** — regime conditioning of the BOOK (W2-A's R0/R2/R3 objects
may censor differently); **fillability-aware ranking** — a model of P(board AND fillable)
rather than P(board), which is the obvious next construction this receipt argues for;
size-weighted or P̂-weighted books (everything here is equal-weight within a date);
**replacement books** that spend a refused slot on the next-ranked fillable name rather than
leaving it empty.

**Inference (2)** — **a confidence interval on the survival ratio itself**: every survival
number here is a point ratio of two rates whose arms are NESTED (implementable ⊂ paper) and
therefore positively dependent, so an independent-samples delta method would be conservative
in an un-quantified direction; a bootstrap over feature-dates is the obvious construction and
was not run. This pass reports the point ratio, a Wilson interval on each arm, and a
successes-based THIN flag. Also untested: **a formal monotonicity test** in K or in P̂ decile
(Jonckheere–Terpstra, isotonic fit) — direction is read off the printed sequence and the two
observed reversals are named.

**Population (3)** — **F3**, the full ~5,400-name universe including ST and delisted names
(the censoring rate itself may be a curation artifact, since the omitted small-caps are where
一字 lives); STAR, THIN-SKIPPED and therefore unmeasured, not null; a full ex-ante (U2)
restatement of every L3 table.

---

## REPRODUCE

```
git fetch origin claude/cn-limit-w1-onset claude/cn-limit-w1-rider claude/cn-limit-w1-dataheal
git show origin/claude/cn-limit-w1-onset:research/cn_prophet_audit/onset_calibration_v1.py \
  > research/cn_prophet_audit/onset_calibration_v1.py
git show origin/claude/cn-limit-w1-rider:research/cn_prophet_audit/continuation_rider_v1.py \
  > research/cn_prophet_audit/continuation_rider_v1.py
git show origin/claude/cn-limit-w1-dataheal:data/china_zt_pool/pool.parquet \
  > data/china_zt_pool/pool.parquet

TZ=UTC python3 research/cn_prophet_audit/onset_fillability_restatement_v1.py
```

Runs from repo root in ~80 s. A missing dependency is a loud `SystemExit` carrying the exact
`git show` recovery line, never a silent fallback. Once PRs #5055 / #5061 / #5059 have merged
to main the extraction step is unnecessary.
