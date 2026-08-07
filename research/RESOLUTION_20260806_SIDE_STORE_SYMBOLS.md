# Resolution 2026-08-06 — CTRA / TPH / TCNNF symbol status

Status: RESOLVED. Closes chip (2) of
`research/ADJUDICATION_20260803_UNIVERSE_SIDE_STORE_FRESHNESS.md` §4, which
deferred symbol-level resolution for the refused `stock_search.extra_tickers`
names and kept them honest in the meantime with the #4643 freshness demotion and
deliberately cause-neutral page copy. Executed under the #4622 protocol (resolve
against the NASDAQ symbol directory + OpenFIGI/SEC, never by inference; a rename
is a KEY MIGRATION) and the #4616 law (delisted is not stale).

## §0. Verdict

**The brief's hypothesis is half right and inverted on every name.** The two names
suspected of being retired-symbol renames are delistings; the one name a vendor
probe called "possibly delisted" is the only live security of the three, and it
is the rename.

| Name | Suspected | RESOLVED | Store tip | What the tip actually is |
|---|---|---|---|---|
| CTRA | rename | **DELISTED 2026-05-07** — Coterra Energy acquired by Devon Energy | 2026-05-07 | last trading session |
| TPH | rename | **DELISTED 2026-05-14** — Tri Pointe Homes acquired by Sumitomo Forestry | 2026-05-13 | last trading session (deal closed before the open on 05-14) |
| TCNNF | "possibly delisted" | **RENAME → NYSE:TRLV** — Trulieve uplisted from the OTC quote 2026-06-09 | 2026-07-17 | last day Yahoo served the retired OTC symbol |

Two consequences follow, and they point in opposite directions:

1. CTRA and TPH must **stop being fetched** and must **stop being described as
   "no new data"** — but they must **not** be removed from the library. There is
   no successor symbol to re-point at, and deleting the ticker from
   `stock_search.extra_tickers` drops it out of `build_stock_library.universe()`
   and 404s pages that are still linked (CSP-R1).
2. TCNNF must be **migrated**, not retired. It is a live company whose feed was
   recoverable the whole time.

## §1. Receipts (all fetched 2026-08-06 in this worktree)

### CTRA — Coterra Energy Inc., SEC CIK 0000858470

- Absent from the NASDAQ symbol directory (`nasdaqtraded.txt`, 13,106 rows,
  2,937 of them NYSE-listed — the file covers NYSE, and `TPR`/`TPL`/`TPB` are all
  present, so absence here is a real absence and not a coverage hole). No
  security named "Coterra" appears in the file at all.
- Absent from SEC `company_tickers.json` (10,398 rows); the per-CIK submissions
  header carries `tickers: []`, `exchanges: []`.
- 8-K 2026-05-07, items 1.02/2.01/3.01/3.03/5.01/5.02 (accession
  0001104659-26-057278): merger with Cubs Merger Sub, Inc. completed on the
  Closing Date 2026-05-07; the Company survives as a wholly-owned subsidiary of
  **Devon Energy Corporation**. Each share converted into the right to receive
  **0.70 shares of Devon common stock** plus cash in lieu of fractions. Item 3.01
  states the NYSE was notified that the merger closed.
- 25-NSE 2026-05-07 (accession 0000876661-26-000399) — exchange delisting
  notification.
- 15-12G 2026-05-19 (accession 0001193125-26-231109) — registration termination.
- DEFM14A 2026-03-30 (accession 0001104659-26-036887).
- yfinance `period=3mo`: 0 rows, "possibly delisted; no price data found".

### TPH — Tri Pointe Homes, Inc., SEC CIK 0001561680

- Absent from `nasdaqtraded.txt`; **also absent from OpenFIGI** under
  `exchCode: US` ("No identifier found") — CTRA, by contrast, still resolves at
  OpenFIGI to a composite record, which is why OpenFIGI presence is not on its
  own evidence of a live listing.
- **The SEC submissions header is STALE and says the opposite**: `tickers: ['TPH']`,
  `exchanges: ['NYSE']`. The filings are the discriminator, not the header — this
  is the same shape as the BLD misdiagnosis in #4616, where EDGAR's header also
  outlived the delisting.
- 8-K 2026-05-14, items 1.01/2.01/3.01/3.03/5.01/5.02/5.03/8.01/9.01 (accession
  0001193125-26-222960): merger with Teton NewCo, Inc. completed 2026-05-14
  under the 2026-02-13 Merger Agreement with **Sumitomo Forestry Co., Ltd.**;
  each share converted into the right to receive **US$47.00 in cash**.
- 25-NSE 2026-05-14 (accession 0000876661-26-000432).
- 15-12G 2026-05-26 (accession 0001561680-26-000029).
- DEFM14A 2026-03-17 (accession 0001193125-26-110678).
- yfinance `period=3mo`: 0 rows, "possibly delisted".

### TCNNF → TRLV — Trulieve Cannabis Corp., SEC CIK 0001754195

- `TRLV` is present in `nasdaqtraded.txt` as "Trulieve Cannabis Corp.
  Subordinate Voting Shares", listing exchange **N** (NYSE); `TCNNF` is absent.
- SEC `company_tickers.json`: `{cik 1754195, ticker TRLV, Trulieve Cannabis Corp.}`.
  Submissions header `tickers: ['TRLV']`, `exchanges: ['NYSE']`.
- **8-A12B and a NYSE listing certification (form CERT), both 2026-06-09** — the
  registration of a class of securities on a national exchange. **No Form 25 and
  no Form 15 anywhere in the filing history.** The company is alive; it changed
  venue, not existence.
- OpenFIGI: `TRLV | TRULIEVE CANNABIS CORP | Common Stock | US`; `TCNNF` returns
  no identifier.
- **Basis proof for the re-key**: Yahoo serves TRLV back to 2018-09-27 (1,973
  rows). Over the 19 sessions where the stored TCNNF stub and TRLV both print
  (2026-06-15 … 2026-07-17), the closes are **identical on every session**
  (TRLV/TCNNF ratio min = max = 1.000000). Same security, same basis, no
  consolidation — so `data/yahoo/TCNNF.parquet` is re-keyed, never re-based.
  The nightly lane's `auto_adjust=False` basis is unchanged by this move; depth
  beyond the 19-row stub comes from the `backfill.yml --full-history` dispatch,
  not from a hand-written parquet (adjudication R4).

### What the vendor probe was worth

yfinance said "possibly delisted; no price data found" for TCNNF, CTRA and TPH
alike. It was right twice and wrong once, and nothing in the message
distinguishes the cases. A vendor's silence is the QUESTION, never the answer —
the same lesson #4616 recorded when a live-looking `get_info()` quote (actually a
frozen last close, with `marketCap / sharesOutstanding` reproducing it exactly)
was used to *exclude* the rename hypothesis for BLD.

### No stranded state

No open forward claim, ledger row or basket membership is keyed on CTRA, TPH or
TCNNF: `data/qledger/**` and `data/name_score/**` contain zero rows for any of
the three, and `data/baskets/membership.json` never listed them. The #4622
disclosure-and-strand machinery is therefore not needed here — this migration
strands nothing.

## §2. What shipped

**A delisting is now a first-class, disclosed state — not an unexplained silence.**

- **`config/delisted_symbols.yml`** (new) — the exit ledger. Per row: company,
  exchange, CIK, last session, delisting date, reason, acquirer (EN + ZH),
  consideration, `successor_ticker`, and the SEC accession numbers behind every
  claim. `successor_ticker` is null on both rows and that is load-bearing: an
  all-stock acquirer (Devon) is a different pre-existing security and an all-cash
  acquirer (Sumitomo Forestry) leaves no US line at all, so neither continues this
  price series and neither may be spliced onto it.
- **`lib/delisted_symbols.py`** (new) — loader, in `lib/` because `collectors/`
  may not import `engine/`. Fails **open**: an unreadable or malformed ledger
  reads as empty and every consumer degrades to its pre-ledger behaviour. A row
  missing a required field is dropped whole rather than half-applied — a
  half-read row would strip a name's score while leaving the page unable to say
  why, which is strictly worse than the cause-neutral note it replaces.
- **`collectors/yahoo.py`** — delisted symbols leave the FETCH list
  (`all_tickers()`), and leave the Stooq fallback's probe list too. A new
  `maintained_tickers()` is the un-filtered view the store audit runs on, so a
  store the fetch no longer touches is still read every night. The exclusion is
  announced once per run as a `::notice` naming each symbol, its last session and
  its reason. `audit_store_freshness` gains a `delisted` bucket and drops those
  names from `stale`/`stub` — a finished tape is not a defect, and a permanently
  unclearable warning costs the audit the attention the next real freeze needs.
  A delisted store whose tip advances PAST its recorded last session raises a
  `::warning`: either the row is wrong, or the ticker was reused by another
  issuer (the ECHO/EchoStar class, where a reused key refills with the new
  holder's history and looks born-clean).
- **`scripts/build_stock_library.py`** — `_apply_delisting` writes a `delisted`
  block and **removes** `feed_stale`; the two are mutually exclusive claims about
  the same silence, and shipping both would have the page say "no new data for 91
  days" beside "stopped trading 7 May". Authority is stripped exactly as the
  freshness demotion strips it (no board, no standout, no percentile cohort, no
  potential call, `conviction.score = None`), but **unconditionally**:
  `_authority_admits` now refuses a delisted ticker independently of
  `demote_map`, because R2's circuit breaker empties that map wholesale on a
  mass-freeze run — precisely the run where a dead name regaining a score would
  be least visible. `_feed_freshness` skips delisted recs entirely so they
  neither earn a lag-based demotion nor pad the breaker's denominator.
- **`templates/stock.html.j2`** — the as-of line now carries at most one honesty
  note. Delisted: `· stopped trading 7 May 2026 — bought by Devon Energy; no
  longer scored` / `· 2026年5月7日停止交易 — 被 Devon Energy 收购；不再评分`
  (`住友林业` for TPH). Plain words, active voice, no apology, no jargon: what
  happened and what it means for the score. The accession numbers stay in the
  YAML, where the next engineer will look — not on a stock page. Dates are parsed
  by hand rather than through `new Date()`, which reads an ISO date as UTC
  midnight and renders the previous day for every viewer west of Greenwich.
- **`config.yml`** — `TCNNF` → `TRLV` in `extra_tickers` with an `extra_names`
  label (Health Care, per SEC SIC 2833); `data/yahoo/TCNNF.parquet` re-keyed to
  `TRLV.parquet` in the same commit. Ticker, store filename and label move
  together or the library mints two companies out of one. CTRA and TPH **keep**
  their membership and gain `extra_names` labels, with a comment on each line
  saying why deleting it would 404 a live page.

## §3. Boundaries

- **No store rewrites.** CTRA's and TPH's parquets are untouched — what the
  vendor served is what is stored, and the exit row makes it inert for scoring.
  TRLV's file is the TCNNF bytes under a new name; its depth heal is the existing
  `backfill.yml --full-history --only yahoo` dispatch, never a hand-written
  parquet (adjudication R4, price-basis law).
- **No ledger changes** (#4441/#4463 own that layer), no membership edits, no
  breadth-cache pruning, no re-sourcing.
- **CWEN-A is untouched.** It is a distinct listed security whose Yahoo symbol
  went quiet; R3 already rules how it heals and retires, and nothing here
  reopens that.
- **The rename half of the lifecycle is #4622's** (`lib/symbol_aliases.py`,
  `scripts/heal_retired_symbol_keys.py`, `scripts/check_symbol_rename_drift.py`,
  still open at time of writing). This PR deliberately does not depend on those
  modules and does not touch `breadth.ticker_fixups`: TCNNF's migration is a
  three-line config + store re-key with no downstream key to strand, and coupling
  it to an open PR would block a resolved fact behind an unresolved one.

## §4. Follow-ups

- **Depth heal for TRLV** — the store carries 19 rows; Yahoo serves 1,973 back to
  2018-09-27. Dispatch `backfill.yml --full-history --only yahoo` after this
  merges. Until then TRLV renders as a LIMITED record, which is honest.
- **The delisting sweep is not done.** `K` (Kellanova, named by the #4643 §5
  census as requested nightly with no store file ever) and `RGI` (frozen
  2026-07-17) are the same class and were out of scope here. Resolve each on its
  own receipts before adding a row — the whole point of this file is that no row
  enters it by inference.
