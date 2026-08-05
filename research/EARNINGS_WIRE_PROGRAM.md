# Earnings Wire — why the lane never posted, and what makes it fast

**Opened** 2026-08-04 · **Trigger:** McDonald's reported Q2 pre-market; @DeItaone,
@financialjuice and @AIStockSavvy all posted inside ~3 minutes. We posted nothing.
Not late — *nothing*. The outbox has never held a single `kind="earnings"` item.

## §0 ACCEPTANCE GATES

A change in this program is not done unless:

1. **No figure is published that the filing does not state.** Every number in a post
   traces to a row of a table in the 8-K exhibit it came from, and the provenance
   names that row. A figure we cannot prove is dropped, never guessed.
2. **No beat/miss is claimed across measures.** A GAAP per-share figure is never
   compared to an adjusted consensus (§2.4). If the basis cannot be matched, the
   post states the figures and no verdict.
3. **Every decline is loud.** A give-up path prints a `::warning`/`::notice` and
   increments a counter the run reports. A quiet wire and a broken one must never
   look the same (§1.2 is what happens when they do).
4. **Latency is measured end-to-end**, filing-acceptance → live post, and reported
   as a number, not an intention.
5. **Volume is capped by editorial judgement, not by budget** (§3.3).

---

## §1 Diagnosis — four independent failures, each fatal alone

### 1.1 The data feed is a dead URL

`earnings_feed.FreePollProvider` polls `finviz.com/rss.ashx?v=3&auth=0`. That
endpoint 301s to `/rss?v=3&auth=0`, which returns a **404 HTML page**. Measured
2026-08-04. Zero events, ever.

### 1.2 The failure was invisible — the reason it survived

The fetch exception is swallowed at `logger.debug`. A dead feed and a quiet
calendar produce byte-identical output:

```
[fastlane] tick | emitted=0 skipped=0 quarantined=0
marketing-earnings-wire: nothing queued this pass
```

`skipped=0` is the tell — nothing was filtered, nothing *arrived*. Every run since
the lane was armed reported success. **The bug was not that a URL rotted. URLs rot.
The bug was that nothing could tell the difference.**

### 1.3 GitHub drops ~85% of the polls

Cron `*/10 11-13,20-22 * * 1-5` = 36 slots/weekday. Actual: 5 on 07-31, 6 on 08-03,
**0 on 08-04 — the day MCD reported**. Only 2 days in a fortnight ran at all. Runs
that land arrive 2–60+ min late.

Cause: this repo carries **54 scheduled workflows / 68 cron expressions** and 200+
runs in 6 hours. GitHub sheds scheduled runs under load. *Adding cron expressions to
this repo makes the problem worse, not better.*

### 1.4 The publish path floors at ~25 minutes

Poll (avg 5 min) → publish sweep every 30 min → Buffer's hard `dueAt = now + 3 min`
→ Buffer's own send. And `marketing-publish` drops slots too: on 08-04 it ran at
04:31 then not again until 10:04 — a six-hour hole. MCD reported at 11:01.

---

## §2 The source, and the four traps in reading it

### 2.1 SEC EDGAR is free, primary, and sub-minute

An issuer announces by filing an 8-K with **Item 2.02** and the release as Exhibit
99.1. EDGAR's `getcurrent` Atom feed carries it within seconds: measured entries at
07:10:23 ET while the clock read 07:11. MCD's 8-K was accepted **07:01:40 ET —
ahead of the wire accounts that posted the same numbers.**

We already hold the other half: `data/earnings/earnings.parquet` had MCD at
`2026-08-04, pre-market, eps_forecast=3.32` — the exact consensus the competitors
printed. Nothing in an 8-K states the estimate; this is where it comes from.

### 2.2 Trap — prose matching is ~50% wrong

Flattening the release and regexing sentences read Pfizer's revenue as "500 million"
(~$15B actual) and Merck's as "161 million" (~$16.6B). A release says "revenue" in a
dozen sentences; one of them is the consolidated number.

### 2.3 Trap — first-matching-table reads a segment

Caterpillar's revenue came back **7,037** from a segment table. CAT bills ~$16B a
quarter.

**The rule that fixes it is structural, not a magnitude heuristic:** the consolidated
statement of operations is the one table carrying BOTH a revenue row and a per-share
row. A segment table has sales and no EPS. Accept figures only from a table yielding
both. On the 08-04 filings: MCD/PFE/TDG correct, CAT/MRK **declined**, zero wrong.

### 2.4 Trap — GAAP vs adjusted manufactures results

**The subtlest and worst.** Consensus is quoted on *adjusted* earnings; the income
statement reports *GAAP*. Comparing them does not add noise — it invents results:

| | GAAP vs adj. estimate | adjusted vs estimate |
|---|---|---|
| FIS | 0.45 vs 1.47 → −69% "miss" | 1.48 vs 1.47 → **+0.7% beat** |
| TKR | 0.42 vs 1.63 → −74% "miss" | 1.83 vs 1.63 → **+12.3% beat** |
| PFE | −0.04 vs 0.68 → "miss" | 0.77 vs 0.68 → **+13.2% beat** |
| MCD | 3.32 vs 3.32 → "in line" | 3.38 vs 3.32 → **beat** |

Every one of those "misses" is an artifact. The adjusted figure is stated in the
non-GAAP reconciliation and it is *labelled*, so it can be looked up rather than
inferred. When no adjusted row exists, we **decline the verdict** rather than
compare across measures.

### 2.5 Trap — a units caption outside the scanned window

Trex states "($ in thousands)" ~11.5k chars in. A head-only scan defaulted to
millions and turned $418M into **$418B**. The caption that governs is the nearest
one *preceding the table we actually read* — filings carry several.

*(Also: EDGAR's 8-K `reportDate` is the TRIGGERING EVENT date, not the fiscal period.
Trex's Q2 release carries 2026-08-04. Deriving a quarter from it labelled every Q2
print "Q3 2026". Read the period from the release text.)*

---

## §3 Build queue

| | item | state |
|---|---|---|
| **W0** | EDGAR wire: feed → Item 2.02 → same-table extraction → basis check → `earnings_feed` schema. Replaces the dead provider. | **SHIPPED** |
| **W1** | Competitor-grade composer (§3.2) | next |
| **W2** | X API direct posting — removes Buffer's 3-min floor | next |
| **W3** | VPS systemd daemon (§3.1) — removes the cron drop | next |
| **W4** | Priority tier (§3.3) — the volume cap | next |
| **W5** | Coverage: pair adjacent tables so CAT/MRK-shaped filings stop declining | later |

### 3.1 Where it runs

The VPS, as a systemd unit beside `marketing-press-feeds.service` — same shape, same
`/opt/macro` venv, `--lane earnings`. That removes GitHub's scheduler from the path
entirely, which is §1.3's only real fix.

**No LLM in the hot path.** The VPS has no Ollama (`app/deploy/` carries no
`OLLAMA_BASE_URL`), the local Qwen 3.5:9b took 22s on one exhibit and returned empty
content — `finish_reason: length`, the whole budget spent on reasoning — and an
earnings post is a table of numbers, which is the one case where deterministic
composition is not a compromise but the correct tool.

### 3.2 What the post should look like

From the three competitor posts: **cashtag first; verdict in the headline and it can
be split** ("EPS BEATS, SALES COME IN SLIGHTLY LIGHT"); **every line is actual-vs-
estimate**; **bullets, not prose**; the story is often in the *comps*, not EPS.

Honest gap: our calendar carries **EPS consensus only**. Revenue consensus is
obtainable (Finnhub); comparable-sales consensus is Bloomberg-tier and out of reach.
Lines we have no estimate for are stated as levels, never as an implied surprise.

### 3.3 Volume is an editorial cap, not a budget one

**295 companies reported on 2026-08-04**; 286 the next day. At $0.015/post the cost
of posting all of them is trivial (~$4.50/day) — the constraint is that ~300 posts in
one session would collapse per-post reach and read as spam. Target the tier that
earns attention (~40–60/day at peak), which also puts spend near ~$70–90/year.

---

## §4 Standing laws

- **L1 — Decline beats guess.** A post we never make is recoverable; a wrong number
  under our name is not. `figures_from_tables` returning `None` is the design
  working.
- **L2 — A silent decline is the failure, not the decline.** Every give-up path
  annotates and counts.
- **L3 — Never compare across measures.** GAAP is not adjusted, basic is not
  diluted, and both errors run *in our favour*, which is the direction a publishing
  error must never be allowed to drift.
- **L4 — Structure over heuristics.** "The table with both rows" beats any magnitude
  band, needs no per-company tuning, and fails safe.
- **L5 — Cron is not a scheduler here.** With 68 cron expressions in one repo,
  anything latency-critical belongs on a daemon we own.
