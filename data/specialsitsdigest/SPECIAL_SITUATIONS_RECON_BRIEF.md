# Recon Brief — Special Situations Digest (reverse-engineer the taxonomy & methodology)

**For:** a local MCP subagent with browser/read access to a 14-day trial of
`specialsitsdigest.com` (Live Feed + Situations Database + Digests).
**Purpose:** extract the *methodology, taxonomy, and data schema* of their product
so we can build our own US-first special-situations desk on the macro dashboard.
**Deliverable:** a single structured markdown file (see §7) handed back to the
orchestrating session, which turns it into a Phase-1 build spec.

---

## 0. Ground rules (read first)

1. **We are extracting structure, not content.** Capture taxonomy, thresholds,
   field schemas, counts, source types, and *characterizations* of their prose
   (length, structure, tone). Do **NOT** copy/redistribute their written summaries
   verbatim — quote at most one short illustrative sentence per category as a
   format sample. We will write our own summaries from primary filings.
2. **Be efficient.** You do **not** need to read all 4,471 situations word-for-word.
   Use the database's filter/sort UI to read **aggregate counts** exhaustively, and
   use **stratified sampling** for the deep-read tasks (§3–§5). Target totals are
   given per task — stop when you hit them.
3. **Cite where each number came from** (which page/filter/issue) so we can trust it.
4. If a field/filter doesn't exist, say "NOT PRESENT" — absence is signal too.

---

## 1. Pages to work from

- **Situations Database** — `https://specialsitsdigest.com/situations-database/`
  The census source. Look for filters/columns: category, country, market-cap band,
  sector, status/stage, date. This is where you read off **counts**.
- **Live Feed** — `https://specialsitsdigest.com/live-feed/`
  Shows raw cadence + how fresh items look before they're digested. Use to gauge
  filing-date → publish-date **lag** and the raw vs. curated funnel.
- **Digests index** — `https://specialsitsdigest.com/digests/` and the free issue
  `https://specialsitsdigest.com/special-situations-digest-9/`
  Use the free issue as the **prose-format anchor** (full structure is visible).
- Any per-situation **detail page** — the schema source for §4.

---

## 2. CENSUS — exhaustive counts (cheap, do this fully)

Read these off the database's filtered views. We already have the **by-category**
totals below (from the site) — confirm them and fill the rest.

**2a. Confirm/refresh category counts** (our current snapshot, verify against DB):
Activist 36 · Strategic Reviews 23 · Acquisitions 71 · Divestitures 22 · Tender
Offers 22 · Going-Private 12 · Issuer Tenders 8 · Rights Offerings 9 ·
Restructuring 15 · Liquidations 4 · Spin-Offs 14 · New SpinCos 3 · Capital Returns 1
· Delistings 3 · Relistings 4 · Other 8. **Note:** these look like *current/recent*
counts, not the lifetime 4,471 — clarify whether the DB total is 4,471 lifetime and
report **both** lifetime and trailing-issue counts per category if both are shown.

**2b. By COUNTRY** — count of situations per country (or per region if that's the
only grouping). **This is the most important table** — it tells us exactly how much
of their product is US (which we can replicate cheaply) vs. international (their
moat). Rank countries by count; give the US share of total as a %.

**2c. By MARKET-CAP band** — whatever buckets they expose (nano/micro/small/mid/
large). We need the **floor**: do they include sub-$50M / sub-$10M names? Report the
smallest market cap you can find in any situation.

**2d. By SECTOR** — if a sector/industry facet exists, counts per sector.

**2e. By STATUS/STAGE** — if situations carry a lifecycle state (e.g. Rumored →
Announced → Definitive → Completed → Terminated/Withdrawn), list the exact state
vocabulary and counts per state.

---

## 3. TAXONOMY — definitions & boundaries (stratified read)

For **each of the 17 categories**, determine the operational definition and — more
importantly — the **boundary rules** that separate adjacent categories. Read ~2
example situations per category to infer the rule (≈34 situations total).

Specifically resolve these ambiguous pairs (this is what we most need):
- **Acquisition vs. Tender Offer vs. Going-Private** — what triggers each label?
  (merger agreement vs. tender mechanics vs. sponsor/insider take-private?)
- **Issuer Tender vs. Capital Return vs. Rights Offering** — buyback mechanics.
- **Strategic Review vs. Other Situations** — what's the catch-all threshold?
- **Spin-Off vs. New SpinCo** — is "New SpinCo" the *child entity* once it starts
  trading, vs. "Spin-Off" the *parent action*? Confirm.
- **Divestiture vs. Acquisition** — same deal from buyer vs. seller side? Do they
  double-count one transaction under both?
- **Restructuring vs. Liquidation vs. Delisting** — distress ladder.
- **Delisting vs. Relisting** — direction + what counts.

For each category return: `name`, `1-line definition`, `trigger (what filing/event
creates it)`, `boundary note (what it is NOT)`.

---

## 4. PER-SITUATION SCHEMA — the field set (sample ~20–30 detail pages)

Open ~20–30 situation detail pages spread across categories and countries. Record
the **union of all fields** they populate. Expected candidates (confirm presence,
add any we missed):

- Identity: company name, ticker, exchange, country, CIK/ISIN, sector
- Situation: category, sub-type, status/stage, headline, date(s) (announced /
  filed / effective / closing)
- Parties: activist / acquirer / target / sponsor / advisor names
- Deal economics: deal value, price/share, **premium %**, consideration
  (cash/stock/mixed), implied EV
- **Fundamentals shown** — list the EXACT metrics displayed (e.g. market cap, EV,
  EV/EBITDA, P/B, P/E, net cash, net debt, FCF yield, revenue, insider %). We need
  this list precisely — it defines what we must join from our own data.
- Provenance: link/citation to the underlying source (see §5)
- Narrative: the summary paragraph (characterize only, per §0)
- Tracking: do they show an update history / changelog per situation across issues?

Return the schema as a field table: `field | always present? | example value (anonymized if sensitive)`.

---

## 5. SOURCE ATTRIBUTION — "are they just reading EDGAR?" (sample ~50–80)

For ~50–80 situations spanning **US and non-US**, record the **underlying source
type** they cite or link. Bucket each into:

- US SEC EDGAR filing — and which **form** (SC 13D / 13D-A, SC TO-T, SC TO-I,
  SC 14D9, DEFM14A / PREM14A, 8-K, S-1, Form 10, SC 13E3, Form 25/15)
- UK LSE **RNS** announcement
- Canada **SEDAR+**
- Australia **ASX** / other APAC regulator (EDINET, TDnet, HKEXnews)
- EU national regulator / OAM
- Press release / newswire (Business Wire, PR Newswire, GlobeNewswire)
- Secondary news media
- No source cited

**Output:** a count/% per source bucket, split US vs non-US. This is the definitive
answer to whether EDGAR alone suffices (it won't — quantify how much it misses) and
which secondary feeds we'd need for international parity. Also note, per US
situation, the **EDGAR form-type → their-category** mapping you observe — this is
gold for our deterministic classifier.

---

## 6. PROSE & CADENCE characterization (use free issue #9 + sample)

- **Summary length**: median words per situation summary (eyeball ~15 samples).
- **Structure**: what does a summary contain, in order? (e.g. what happened → who's
  involved → terms/premium → why it matters / valuation angle → what to watch).
  Give the recurring skeleton, not the text.
- **Tone**: neutral-reportorial vs. opinionated/recommending? Do they take a view?
- **Cadence/lag**: from the Live Feed, estimate typical days between the underlying
  filing/announcement date and when it appears. (Tells us our real-time edge.)
- **Digest structure**: how is an issue organized (by category? by country? by cap?),
  and roughly how many situations per weekly issue.

---

## 7. OUTPUT FORMAT (return exactly this)

Return one markdown doc with these sections:

```
# Special Situations Digest — Recon Findings
## A. Census
   - A1 category counts (lifetime + trailing) [table]
   - A2 by country [ranked table + US %]
   - A3 by market-cap band [table + smallest cap found]
   - A4 by sector [table]
   - A5 by status/stage [vocabulary + counts]
## B. Taxonomy (17 categories: definition / trigger / boundary)  [table]
   - B1 resolved ambiguous-pair rules [bullets]
## C. Per-situation schema [field table]  + exact fundamentals-metric list
## D. Source attribution [bucket %s, US vs non-US] + EDGAR-form→category map
## E. Prose & cadence [length / skeleton / tone / lag / issue structure]
## F. Open questions / anything surprising
```

Keep it tight and structured. Tables over prose. Cite the page/filter for each
number. Flag low-confidence items. **Do not paste full summaries.**

---

## Why each section matters (context for the subagent)

- **§2b (country)** decides scope: US-first if US is the bulk; otherwise we plan for
  RNS/SEDAR+ early.
- **§3 + §5 (taxonomy + form mapping)** *is* our deterministic classifier — EDGAR
  form-type → one of 17 categories, no LLM needed.
- **§4 (schema + fundamentals)** is our data model and tells us which fields we
  already have (we have EDGAR fundamentals, 13F, insider, prices) vs. must add.
- **§5 (sources)** answers the user's core question and sizes the international moat.
- **§6 (prose)** calibrates our single LLM summary touchpoint (Haiku/DeepSeek).
