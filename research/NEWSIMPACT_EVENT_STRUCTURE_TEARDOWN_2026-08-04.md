# NewsImpact Teardown — Event-Impact Structure for the Stock Dossier and Company Intelligence

**Date:** 2026-08-04 · **Subject:** `nimpact.tech/newsimpact/news/f45a46c79809f96f` ($MCD, "McDonald's
earnings beat estimates, chain announces new U.S. head")
**Relationship to existing dockets:** extends
[`EARNINGSCALL_AI_TEARDOWN_AND_MASTERMIND_INTEGRATION_2026-08-01.md`](EARNINGSCALL_AI_TEARDOWN_AND_MASTERMIND_INTEGRATION_2026-08-01.md)
(that one tears down a *transcript corpus* competitor; this one tears down an *event-impact
presentation* competitor) and consumes the shipped W0 of
[`EARNINGS_WIRE_PROGRAM.md`](EARNINGS_WIRE_PROGRAM.md). It proposes no new corpus, no new
ingestion lane, and no second product shell.

---

## §0 ACCEPTANCE GATES

A surface built from this docket is **not done** unless:

1. **Every displayed number resolves to a stored figure with a basis label.** No EPS, revenue,
   or surprise renders without `basis ∈ {gaap, adjusted}` and the matching consensus basis.
   Cross-basis comparison declines the verdict — it never prints one
   (`EARNINGS_WIRE_PROGRAM` §2.4).
2. **No model-originated score reaches the page.** Direction, confidence, and magnitude are
   either measured base rates from stored history or they are absent. An LLM may de-escalate
   or phrase; it may never originate (Neural Web A7).
3. **No front-facing refutation vocabulary.** The register is "Changes this read: `<condition>`" /
   "改判条件：`<条件>`" — never "falsified / refuted / 证伪" (operator ruling 2026-07-27, #3821;
   fenced by `tests/test_front_facing_register.py`).
4. **Nulls print.** A quarter with no consensus, no adjusted row, or no reaction history renders
   the reason in plain words, not an empty panel and not a silent omission.
5. **Display tier only.** Nothing here ranks, sizes, gates, or vetoes. Promotion to authority
   requires the pre-registered gauntlet, separately.
6. **Bilingual EN/ZH at parity**, no translated text in `title=` attributes.
7. Per-surface visual crops (light + dark, EN + ZH) posted in the PR body.

---

## §1 What the page actually is

Transcribed section order, headings verbatim:

| # | Block | Content |
|---|---|---|
| 1 | Chip row | `$MCD` · `Positive` · `74% confidence` · `Direct company news` |
| 2 | Headline + provenance | publisher (CNBC), timestamp, "Analysis by NewsImpact Research", trust chips: `Source checked` / `Editorial standards` / `Methodology` |
| 3 | `IMPACT ON $MCD` | direction + one paragraph: catalyst → materiality → *self-limiting magnitude claim* |
| 4 | `WHY THIS MATTERS` | transmission mechanism, conditional ("If stronger sales… drove the beat, analysts can raise…") |
| 5 | `MARKET OUTLOOK` triad | `HORIZON: Days` · `EXPECTED IMPACT: Moderate` · `EVIDENCE: Medium` |
| 6 | Three paths | `MOST LIKELY PATH` / `STRONGER POSITIVE CASE` / `STRONGER NEGATIVE CASE` |
| 7 | `SIGNALS THAT CONFIRM THE OUTLOOK` | 4 bullets, each a checkable observable |
| 8 | `SIGNALS THAT MAKE THE OUTLOOK WRONG` | 4 bullets |
| 9 | `EVIDENCE CHECK` | source quality prose; explicitly separates *reported fact* from *inference* |
| 10 | `PRICE SINCE THIS NEWS` | news-time price, latest, since-news %, observed move at `1h / 1d / 5d` with `Pending`, and **`Prediction matched — Predicted Positive; observed Positive`** |
| 11 | `MCD PRICE CONTEXT` | `LATEST` / `1D MOVE` / `20D TREND` / `VOLUME 1.4x 20D avg` + 30-day chart with prior news markers colored by read |
| 12 | `SOURCE` + `Why this news matched $MCD` | publisher link, share, match-path narrative |
| 13 | Tail | gated report teaser, comments, feedback chips (`Useful` / `Too broad` / `Wrong direction` / `Need more detail`), disclaimer |

The information architecture is genuinely good. Blocks 5–10 are the interesting part: a
pre-committed horizon, three conditioned paths, a list of observables that would move the read,
and **a self-grading price ledger that publishes its own hit/miss with `Pending` states for
unresolved horizons.** That last one is a real accountability primitive, and most competitors
do not ship it.

---

## §2 Verdict — an excellent container with no substrate

The page is an **earnings** story. It contains **no earnings numbers**: no EPS actual, no
consensus, no revenue, no margin, no segment detail, no guidance, no historical reaction
distribution. Not a summarization choice — the page says so itself, twice:

> "The likely impact is moderate because no figures, guidance, margin details, or independent
> corroboration are supplied."

> "…its extracted title was blank and its description only referenced MCD's year-to-date
> decline and market capitalization, so the fetched metadata does not corroborate the
> headline's central claims."

So the pipeline is: fetch a headline → the fetch degrades → generate ~700 words of correctly
hedged prose about a beat it never read. The `74% confidence` is attached to a claim the system
explicitly could not verify. The hedging is honest and the scaffolding is disciplined, but the
analysis is **structurally about the headline, not about the quarter.**

**The asymmetry is the whole opportunity: they have the container, we have the contents.**

---

## §3 The MCD collision — concrete, same company, same morning

Our EDGAR wire read the primary document for this exact filing on this exact morning. From
`engine/marketing/edgar_earnings_wire.py`, measured 2026-08-04:

```
MCD  7,099 / 3.32   correct
PFE 15,034 / -0.04  correct
TDG  2,741 / 9.39   correct
CAT  ——             DECLINED (segment tables only)
MRK  ——             DECLINED (same)
```

Three right, two declined, **zero wrong** — from the 8-K Item 2.02 accepted at 07:01:40 ET,
ahead of the wire accounts that reported the same numbers. And `EARNINGS_WIRE_PROGRAM` §2.4
already carries the basis trap for this very name:

| | GAAP vs adj. estimate | adjusted vs estimate |
|---|---|---|
| MCD | 3.32 vs 3.32 → "in line" | 3.38 vs 3.32 → **beat** |

We hold the structural extraction rule (accept figures only from the table carrying *both* a
revenue row and a per-share row), the basis check, the units-caption fix, and the
decline-rather-than-guess floor. NewsImpact wrote the paragraph. We read the filing.

That is the entire thesis of this docket: **wrap our substrate in their scaffolding.**

---

## §4 Copy / Upgrade / Reject

Same format as the EarningsCall.ai docket §"What to copy and what to reject".

### Copy
- The **pre-committed horizon** (`HORIZON: Days`) — stated before the outcome, not after.
- The **evidence grade as a first-class chip**, adjacent to the read, not in a footnote.
- **Three conditioned paths** instead of one point forecast.
- **Observables that would move the read**, written as things a reader can actually check.
- **`Pending` as a rendered state** for an unresolved horizon — an unfinished row is shown, not hidden.
- **Self-graded outcome publishing** (`Prediction matched`) on the same page as the call.
- **News markers on the price chart**, colored by the prior read.
- The **match-path block** ("Why this news matched $MCD") — entity linkage shown, not assumed.
- **Feedback chips naming failure modes** (`Too broad` / `Wrong direction`) rather than a thumbs-up.

### Upgrade
- Confidence → **measured base rate**, not a model number (§6.1).
- Paths → **conditioned on this issuer's own reaction history**, not plausible prose (§7).
- Evidence check → **our receipt spine**: sha256 body hash, byte-coordinate spans, `fact_pack`
  vs `claim_graph` separation, governed source tier. Their "Evidence: Medium" is a word; ours
  is a hash you can recompute.
- Beat/miss → **basis-labelled**, with the verdict declined on cross-basis comparison.
- Self-grading → **lane-gated and claim-keyed** under the existing ledger discipline, so the
  grade cannot be recomputed favourably after the fact.

### Reject
- **The confidence percentage as shipped.** A model-invented 74% on an unverified claim is
  exactly the fluent-prose-outrunning-evidence failure the EarningsCall.ai docket flagged.
- **"SIGNALS THAT MAKE THE OUTLOOK WRONG" as a heading.** Banned register (#3821).
- **Publishing an impact read when the source fetch degraded.** Our equivalent is to decline —
  the wire's `figures_from_tables → None` is a success of the design, not a gap in it.
- **A separate news-report product shell.** The ticker dossier is already the right home
  (EarningsCall.ai docket §2). This is a section, not a site.
- **Analysis keyed to a headline** rather than to an event identity.

---

## §5 Where it lands — three surfaces, one object

One `event_impact` projection, three consumers. No new corpus.

**5.1 Earnings call record page** (`site/stocks/earnings/<t>-<q>-call-record.html`)
Today this page is deliberately transcript-only and says so: *"No release, filing, slides,
consensus, or price-reaction join is implied here."* That boundary is correct for the
*verbatim record* and should stay. The impact structure attaches **below** it as a clearly
separated derived section, with its own provenance line — record above, read below, never
interleaved.

**5.2 Stock dossier** (`templates/stock.html.j2` → `#panel_earn`)
The existing Earnings panel already renders the countdown, `eps_forecast`, and the beat/miss
sparkline from `surprises_json`. It becomes the impact block: reported-vs-consensus with basis,
the measured reaction distribution, the three paths, the watch conditions. This is the primary
surface — it is where a reader already goes with a ticker in mind.

**5.3 Company Intelligence** (`engine/company_intelligence/`)
`CONTEXT_SCHEMA = company_intelligence_context.v1` is `authority: context_only` with a closed
`PUBLIC_METRICS` set, explicitly because the object is eventually handed to a language model —
unknown fields are an input-boundary violation. The impact projection therefore lands as
**named additions to that closed set**, never as a free-form blob. This gives the Brain and the
Terminal a grounded event read without giving them a generation surface.

---

## §6 The three house constraints that change the design

### 6.1 A7 — the model never originates a score
Their `74% confidence` cannot be ported. Two compliant replacements:

- **Measured base rate.** We hold up to 8 quarters of `{qtr, eps, consensus, surprise_pct}` per
  name in `surprises_json`, plus `post_earnings_move.day0_move_pct` from
  `engine/earnings_catalyst.py`. "Beat in 6 of the last 8; median day-0 move +1.4%, range
  −2.1% to +5.3%" is a *computed* statement with a printable denominator.
- **Or no number.** When n is too small, print the n and say so. `endpoint-null ≠ 0.5`.

The LLM's remaining job is phrasing and de-escalation — never the number.

### 6.2 #3821 — no front-facing refutation vocabulary
Direct rename of their block 8, semantics preserved:

| Theirs | Ours |
|---|---|
| `SIGNALS THAT CONFIRM THE OUTLOOK` | **What would confirm this** / 佐证条件 |
| `SIGNALS THAT MAKE THE OUTLOOK WRONG` | **Changes this read** / 改判条件 |
| `STRONGER NEGATIVE CASE` | **If it goes the other way** / 反向情形 |

The tripwire machinery keeps evaluating in the background; the schema keys
(`falsifier_text`, `falsifier.check`) stay. Full verdicts remain on the Calibration Lab
(`measurement.html`), below the fold. This is a display-register change only.

### 6.3 Gauntlet is a promotion gate, not a build gate
Every field here ships display-tier immediately. None of it may rank, size, gate, or veto.
`engine/earnings_blackout.assess` remains the one earnings authority in the pick chain and is
untouched — the same boundary `engine/earnings_catalyst.py` already documents at its §0.

---

## §7 Substrate inventory

| Their block | Our source | State |
|---|---|---|
| Direction chip | `earnings_qual` sentiment/performance (`is_context_only`) | **have** |
| Confidence % | — | **reject as-is** → base rate (§6.1) |
| Evidence grade | `earnings_narrative` governed source tier (A–D), transcript-present, `article_receipt_floor` | **have, stronger** |
| Beat/miss numbers | `edgar_earnings_wire.figures_from_tables` + basis check | **have, shipped (W0)** |
| Consensus | `earnings.parquet.eps_forecast` (1,604 names) | **have** |
| Reaction history | `surprises_json` (8q) + `earnings_catalyst.post_earnings_move` | **have**, coverage accruing (§9) |
| Guidance direction | `engine/guidance_gap.py` — 8-K raise/cut language | **have** (coarse band, not numeric) |
| Analyst revisions | `engine/analyst_revisions.py` | **have** |
| Price-since-news + self-grade | `cycle_forward_log.py`, `ledger_lane.py`, entry_status disclosure law | **machinery exists, not wired to earnings** |
| News markers on chart | `news_event_ledger` → `data/news/event_log.parquet` (PIT, keep-first) | **have** |
| Match path | `news_events.classify_event` + `theme_centrality`, `company_theme_exposure` | **have** |
| Segment detail | — | **missing** (CAT/MRK-shaped adjacent-table pairing is W5 of the wire program) |
| "Why this matters" transmission | — | **missing** — the one genuinely new writing surface |

Almost everything is already built. The work is **projection and presentation**, not ingestion.

---

## §8 Build queue

| | item | depends on |
|---|---|---|
| **W1** | `engine/earnings_impact.py` — pure projection: joins wire figures + consensus + basis → `{verdict, basis, surprise_pct, declined_reason}`. Declines on cross-basis. No I/O. | shipped W0 |
| **W2** | Reaction distribution from `surprises_json` + `post_earnings_move`: beat rate with printed denominator, median/range day-0 move, explicit small-n null. | W1 |
| **W3** | `#panel_earn` becomes the impact block on the stock dossier (§5.2) — the primary surface. Ships EN/ZH, light/dark. | W1, W2 |
| **W4** | Watch-conditions block in the #3821 register (§6.2), sourced from `guidance_gap` + `analyst_revisions` + `earnings_qual` tags. Conditions are *derived from stored fields*, not written. | W2 |
| **W5** | Named field additions to `company_intelligence` `PUBLIC_METRICS` (§5.3) + contract test pinning the closed set. | W1, W2 |
| **W6** | Derived-read section on the call-record page, below the verbatim boundary (§5.1). | W3 |
| **W7** | Wire the earnings event into the forward ledger — pre-committed horizon, `Pending` states, published grade under the claim-keyed first-wins boundary. **The accountability primitive; the one worth the most.** | W3, ledger lane |
| **W8** | News markers on the dossier chart from `event_log.parquet`. | W3 |

W1–W3 is the minimum shippable slice and covers most of the visible gap versus their page.
W7 is the piece that would put us ahead of them rather than level.

---

## §9 Coverage reality — name it, do not hide it

Measured in this worktree, `data/earnings/earnings.parquet`:

| commit | date | rows | names with surprise history |
|---|---|---|---|
| `ba368abe905` | 2026-07-27 | 1,364 | **4** |
| `66345aeeab8` | 2026-08-04 | 1,954 | **122** |

All 120 dated stamps read `2026-08-04`. The W4 rotation fix (`drip_order`, oldest-stamp-first)
is working and the store is accruing at roughly the nightly drip cap. At that rate the universe
completes in **~16 nights, around 2026-08-20**.

Two consequences, both load-bearing:

1. **W2 must render the coverage state, not an empty panel.** A name with no surprise history
   says so with its date; it does not silently omit the block. Per the entry_status disclosure
   law, a coverage cliff dates the *feature*, not the data — and any cross-name comparison of
   reaction stats before ~08-20 is reading the drip order, not the market.
2. **Do not gate W3 on full coverage.** 122 names with history plus 1,604 with a forecast is
   already a shippable surface, and shipping it early is what surfaces the extraction gaps
   (CAT/MRK-shaped declines) while the drip fills.

---

## §10 Recommendation

Proceed with W1–W3, then W7.

Do not build a news-impact product. Build the **event-impact projection** that makes their best
structure native to the dossier we already have: pre-committed horizon, evidence grade bound to
a recomputable hash, three paths conditioned on the issuer's own measured reaction history,
watch conditions in the sanctioned register, and a published self-grade.

Their page proves that scaffolding sells the analysis. Our filing read proves the analysis.
The two have never been in the same place.
