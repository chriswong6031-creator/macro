# Mastermind Security Master — entity, security, listing and identifier spec (2026-08-12)

Status: specification. Implements Data OS **§D2 (Identity)**; nothing here relitigates D2.
Authority: `context_only` — this is universe/reference infrastructure. It never originates a
signal, a score or a promotion.
Reference implementation in the working tree: `lib/dataos/identity.py` — **UNTRACKED** as of this
writing (`git status --porcelain` → `?? lib/dataos/`), so every claim below that cites it describes
code that CI has never run. Commit before depending on it. It is ~700 lines and still moving under a
concurrent lane (`wc -l` → 726 at the last reading, 2026-08-12), so it is cited **by symbol, never
by line** — see the conventions below.
Prior art this extends rather than replaces: `collectors/china_tushare_spine.py`,
`engine/ledger_identity.py`, `config/theme_graph_identity_breaks.yml`,
`scripts/audit_reused_tickers.py`, `lib/delisted_symbols.py`.

Conventions in this document:

- **VERIFIED** = a command was run in this session and its output is quoted or reproducible from
  the appendix. **INFERRED** = reasoned from cited code, not executed.
- Every factual claim carries `path:LINE` or a command. An uncited claim is a defect; a citation
  that points at the wrong code is worse, because it reads as checked.
- **Untracked, concurrently-edited files are cited by SYMBOL, not by line:** `path::symbol`, e.g.
  `lib/dataos/identity.py::normalize_hk_symbol`, `::VendorAliasTable._assert_unambiguous`,
  `::_CODE_RE`. A leading `::` continues the file most recently named in the paragraph. Line
  numbers into `lib/dataos/*.py` were removed in this revision: they had drifted 30–50 lines as the
  file grew from 676 to 726 lines under a lane this document does not own, so every one of them
  resolved to different content than claimed. Resolve a symbol citation with
  `grep -n "def normalize_hk_symbol\|^_CODE_RE" lib/dataos/identity.py`.
- Standing adjudications are cited as `DNR:<KEY>`, never by row number.
- `data/` paths are read from `/Users/chriswong/Documents/Cluade/Macro Dashboard` (the materialized
  checkout). That checkout is in a broken git state (detached HEAD, unresolved conflict in
  `config/dag.yml`, ~1,119 commits behind), so **no claim here rests on its git log or file
  mtimes** — only on file presence and parquet contents, which are unaffected by the checkout's
  branch state.

---

## 0. Why this document exists

The repo does not lack identity discipline. It contains **at least thirteen independently-governed
identity surfaces**, several of them individually excellent, that share no vocabulary, no registry
and no arbitration rule. Correctness is therefore per-module and globally unverifiable: two of the
thirteen demonstrably disagree about whether SATS and ECHO are the same company, and neither is wrong
by its own contract.

This is D0's thesis applied to identity. The remedy is convergence and enforcement over patterns the
house already proved — specifically over `collectors/china_tushare_spine.py:1830
compile_security_master`, which is already an effective-dated, venue-qualified, alias-carrying
security master with a runtime consistency guard. It has zero rows on disk. The correct move is to
**generalize it to US/HK and turn it on**, not to design a second one.

---

## 1. The evidence: identity is broken today

### 1.1 Thirteen independently-governed identity surfaces

Each row is a real, live mechanism with its own scope, its own storage and its own governance.

Reconciliation with the census's adversarial verifier, which enumerated **ten**: eight of its ten are
rows 1, 5, 6, 7, 8, 9, 10 and 12 below; its other two (`config/biocatalyst_sponsor_ticker_map.yml`,
`config/us_search_aliases_zh.json`) are demoted to the narrower list beneath the table because they
are single-domain name→ticker lookups, not identity definitions. Five are added here that the
verifier's grep did not surface — rows 2, 3, 4 and 11 are config blocks or a function rather than
files whose names match `*alias*`, and row 13 is keyed on CUSIP rather than on a ticker.

**They are almost entirely mutually unaware.** VERIFIED by grepping top-level imports of all eight
module-shaped surfaces against each other: exactly **two** cross-references exist —
`collectors/edgar_deadnames.py:59` imports `lib.ticker_aliases`, and `engine/entity_resolver.py:291`
does a function-local `from engine import name_resolver`. Rows 5, 6, 7, 11 and 12 import none of the
others.

| # | Surface | What it maps | Governance |
|---|---|---|---|
| 1 | `lib/ticker_aliases.py:37-40` | membership ticker → Yahoo **fetch** symbol. 2 rows: `FI→FISV`, `MMC→MRSH` | hand-edited dict; explicitly "NOT a display map" (`:28-29`) |
| 2 | `config.yml:2043-2049` `breadth.ticker_fixups` | scraped index symbol → **stored key**. `MRSH→MMC`, `FISV→FI` — the **inverse direction** of #1 | config; consumed at `collectors/breadth.py:330` |
| 3 | `config.yml:3611-3617` `quality.ticker_key_migrations` | superseded **ledger key** → current key. 1 row: `SATS: ECHO` | config; read by `engine/ledger_identity.py:124 load_migrations` |
| 4 | `config.yml:3578-3581` `quality.reused_ticker_acks` | prose ratifications of ticker **reuse** (ECHO, SPWR, RPT) | curated prose; detector `scripts/audit_reused_tickers.py` |
| 5 | `lib/delisted_symbols.py` (108 lines) + `config/delisted_symbols.yml` (95 lines) | symbols whose **security stopped existing**; `successor_ticker` deliberately null (`config/delisted_symbols.yml:38-43`) | curated; three consumers act differently on one row (`lib/delisted_symbols.py:6-15`) |
| 6 | `config/theme_graph_identity_breaks.yml` (53 lines) | company-node **identity breaks**; a **third** id convention `co:<market>:<SYMBOL>` retired and re-minted as `...#2` (`:11-13`) | curated ratification; detectors propose (`:19-26`) |
| 7 | `engine/ledger_identity.py` (372 lines) | ticker-rename **continuations** for append-only ledgers | config map + duplicate detector (`:101 MIN_IDENTICAL_KEYS = 5`) |
| 8 | `engine/entity_resolver.py` (318 lines) | free text → ticker, five layers incl. CN code-adjacency, ~280 中文 basket names, and a CUSIP map (`:194 resolve_cusip`) | code; `@lru_cache`, never raises (`:3-5`) |
| 9 | `engine/name_resolver.py` (152 lines) | company **name** → ticker, SEC `company_tickers` + digest_db, own legal-form stripper (`:21-27`) | code |
| 10 | `collectors/edgar_deadnames.py` (807 lines) | **dead** ticker → CIK; exists because the fundamentals panel drops delisted filers (`:5-11`) | code + cached `data/edgar/dead_name_cik.json` |
| 11 | `collectors/china_tushare_spine.py:491 canonical_identity` | TuShare `ts_code` → repo ticker + `CN-<MIC>-<code>`; BSE old-code aliasing | code, with a hard `SpineError` on vendor/code-range disagreement (`:1873-1877`) |
| 12 | `lib/symbol_directory_receipts.py` (833 lines) | prospective completion receipts for symbol-directory artifacts; forbids synthesizing a receipt from filenames/mtimes/git (`:5-7`) | code + JSON schema |
| 13 | `collectors/openfigi.py` (`:39` → `data/openfigi/cusip_ticker.parquet`) | **CUSIP → US-composite ticker**, keyless OpenFIGI `/v3/mapping`, carrying `name`, `exch` and `sec_type` | code + committed cache; consumed at `engine/smart_money.py:213-225` |

Row 13 was missed by the census's verifier and is the most under-used asset in the list. VERIFIED:
610 rows, columns `[cusip, ticker, name, exch, sec_type, _mapped_at]`, with `sec_type` values
including `Common Stock` and `Depositary Receipt` — i.e. a working, live, 610-row partial security
master that nothing outside 13F resolution reads. Its docstring states the gap it closes:
"Foreign/ADR/renamed/non-index lines that miss both fall through and are silently HIDDEN"
(`collectors/openfigi.py:5-7`).

Six more narrower maps exist and are not counted above:
`config/biocatalyst_sponsor_ticker_map.yml` (1,057 lines, sponsor name → ticker),
`config/us_search_aliases_zh.json` (776 lines, zh search aliases),
`engine/hk_adr_bridge.py:75` (ADR ↔ HK ordinary twins),
`config.yml:6278-6290` (`ah_pairs`, H-share → A-share twin),
`collectors/tushare_client.py:94-101` (`norm_ticker`, `.SH`→`.SS` only),
and the four CN converters listed in §1.5.

VERIFIED — surface count and line numbers read directly from the files listed.

### 1.2 Three incompatible id schemes, and a fourth naming collision

| Scheme | Example | Where | Collision suffix |
|---|---|---|---|
| bare venue-qualified key | `CN-XSHG-600519` | `collectors/china_tushare_spine.py:520` | none defined |
| prefixed company node | `co:<market>:<SYMBOL>` | `config/theme_graph_identity_breaks.yml:6,13` | `#2`, `#3`, … |
| D2 / prototype | `SEC:US-XNYS-MMC`, `US-XNYS-MMC.2` | `lib/dataos/identity.py::security_id`, `::ListingKey` | `.2` |

The fourth problem is not a scheme, it is a **word**. `collectors/china_tushare_spine.py:520` emits
`security_id = f"CN-{mic}-{code}"` — under D2 that string is the **listing** id, and the security id
is `SEC:CN-XSHG-600519`. Two concepts, one field name, in the most rigorous identity module in the
repo. §11.2 specifies the rename.

### 1.3 The disagreement is demonstrable, not theoretical

`engine/ledger_identity.py:13` records `SATS→ECHO` effective 2026-06-24 and `config.yml:3612` carries
it as a machine-readable key migration. `lib/ticker_aliases.py:37-40` does not contain SATS, ECHO,
or any concept of a rename date. Both files are correct by their own docstrings — #1 is a *vendor
fetch* map (`:28-29`), #7 is a *ledger key* map (`:60-62`) — and the result is that the stack holds
two mutually-unaware answers to "is SATS ECHO".

VERIFIED, and the split is physical:

```
$ python3 -c "..."   # see Appendix A2
data/stocks/SATS.parquet: rows=4645 first=2008-01-02 last=2026-06-18
data/stocks/ECHO.parquet: rows=4657 first=2008-01-02 last=2026-07-08
```

Both files exist, both start 2008-01-02, and both carry EchoStar's history. This also **corrects**
`engine/ledger_identity.py:28`, which states "`data/stocks/SATS.parquet` no longer exists" — it does
exist in the materialized checkout, with 4,645 rows. Either the docstring's measurement was taken
against a different store root, or the file returned after the measurement. Flagged for the owner of
that module; the double-count conclusion is unaffected, since the double-count is caused by the two
files existing, not by one of them being gone.

### 1.4 Incident A — Marsh McLennan `MMC → MRSH`, a 7-month silent production loss

The rename: NYSE symbol change 2026-01-14, **same listing, same CUSIP, legal name unchanged**
(`lib/ticker_aliases.py:9-12`). Yahoo migrated the whole history onto MRSH, so the membership's MMC
began returning "possibly delisted, no price data found".

The loss: `scripts/fetch_basket_extras` carried the `MMC→MRSH` entry while its sibling
`scripts/fetch_basket_ohlcv` carried only `FI→FISV`, so `data/baskets/ohlcv/MMC.parquet` **came to
never exist**; the `insurance` basket rendered on **18/19** members and `us_sector_financials` on
**75/76** for the seven months after the rename (`lib/ticker_aliases.py:18-26`). Nothing went red.
The site drew one fewer line.

VERIFIED today, and it is still visible in the stores — this is the sharpest single artifact in the
whole census:

```
data/massive_stock_day/MMC.parquet   rows=1137  2021-07-06 .. 2026-01-13
data/massive_stock_day/MRSH.parquet  rows= 117  2026-01-14 .. 2026-07-02
data/baskets/ohlcv/MMC.parquet       ABSENT
data/baskets/ohlcv/MRSH.parquet      ABSENT
data/stocks/{MMC,MRSH}.parquet       ABSENT
data/yahoo/{MMC,MRSH}.parquet        ABSENT
data/baskets/extras.parquet          column "MMC" present, "MRSH" absent
```

One security. One listing. One CUSIP. The raw store splits it into two files **whose spans meet
exactly at the rename date** and records nowhere that they are the same thing; the deep store has
neither; the extras store has only the pre-rename name. A reader joining `massive_stock_day` on
`MMC` sees a tape that ends 2026-01-13 and reads as a delisting.

### 1.5 Incident B — six CN suffix converters, at least two disagreeing on Beijing

| Converter | BSE rule | Result for `920163` |
|---|---|---|
| `collectors/china_universe.py:113-135 _code_to_ticker` | `6`/`900`→`.SS`, `0`/`3`→`.SZ`, **everything else → `None`** (`:135`) | **dropped** |
| `collectors/china_ths_concepts.py:97-110 to_suffixed` | `8`/`4` prefix **or `startswith("92")`** → `.BJ` (`:108`) | `920163.BJ` |
| `collectors/china_tushare_spine.py:465-480 _board_for` | BSE from the **vendor exchange tag**, never guessed from the code | `bse` |
| `collectors/tushare_client.py:94-101 norm_ticker` | `.SH`→`.SS`; `.SZ`/`.BJ`/`.DC` pass through | unchanged |
| `collectors/china_universe.py:98-110 _to_ticker` | `sh`/`sz` prefixes only; `bj` → `None` (`:110`) | **dropped** |
| `scripts/d4_cn_supply_absorption_phase0.py:132-136` and `scripts/build_china_microstructure.py:234` | inline `.replace(".SH", ".SS")`, re-derived not imported | unchanged |

`collectors/china_universe.py:120-126` is worth quoting because it documents the failure mode
precisely: a bad code "fails QUIETLY, not loudly — yfinance returns an all-NaN column and
`dropna(axis=1, how='all')` deletes it, so a bad code shrinks the universe with no error."

VERIFIED consequence — the Beijing Stock Exchange is **entirely absent from the live CN store**:

```
$ ls data/china_stocks_raw | wc -l          → 1592
$ ls data/china_stocks_raw | grep -c '\.BJ' →    0
```

A third, latent disagreement: the spine contract pins "Every canonical BSE mapping target must be
`920xxx`" (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:89`), and
`lib/dataos/identity.py::cn_board` implements `startswith("920")`, while
`collectors/china_ths_concepts.py:108` implements `startswith("92")`. The two agree on every code
issued to date and diverge the day `921xxx`–`929xxx` is allocated — at which point one converter
routes to Beijing and the other to Shanghai. INFERRED (no such code exists yet:
`ls data/china_stocks_raw | grep -cE '^92'` → 0).

### 1.6 Incident C — Fiserv `FISV → FI`, one security stored twice (new, this pass)

`lib/ticker_aliases.py:38` handles the vendor **lagging** the rename: fetch under `FISV`, store under
`FI`. VERIFIED that both keys are materialized in `data/yahoo`, and that they are the same tape:

```
data/yahoo/FISV.parquet  rows=10020  1986-09-25 .. 2026-07-08
data/yahoo/FI.parquet    rows= 3901  2011-01-03 .. 2026-07-10
overlap rows = 3899 ; close ratio min = max = 1.0
2024-06-03  FI.close = FISV.close = 148.47000122070312
```

Byte-identical over the whole overlap, and `FISV` carries **6,121 rows that `FI` does not**
(10,020 − 3,899; the series are contiguous and `FI` starts 2011-01-03, so those rows are the 1986–2010
history). A consumer keyed on `FI` silently loses 1986–2010; a consumer keyed on `FISV` gets
the full series under a symbol that no longer trades. `data/baskets/ohlcv/FI.parquet` exists,
`data/baskets/ohlcv/FISV.parquet` does not — a third answer in a third store.

`scripts/check_symbol_rename_drift.py:83-87` explicitly guards "vendor symbol leaked into universe …
that mints two stores for one company" — but it only inspects the sp500/sp400/sp600 **membership
lists**, not the stores. `FISV` is not an index member, so the leak it warns about is exactly what
happened, in the one place it cannot see.

### 1.7 What is already right, and must not be rebuilt

- **`collectors/china_tushare_spine.py:1830 compile_security_master`** — an effective-dated,
  venue-qualified security master (19 fields, `:1889-1910`), a conflict-refusing alias table
  (`:1924-1949`), and an instrument-scope classification (`:1951-1988`), all compiled inside one
  immutable generation and exposed by a single atomic pointer promotion (`:1989-1994`;
  `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:102-108`). This is the pattern. It just
  has no rows: its declared store root does not exist on disk, and its own docstring states "every
  collection path remains disabled in this foundation commit" (`collectors/china_tushare_spine.py:40`).
- **`engine/ledger_identity.py`** — the correct doctrine for renames in append-only stores, including
  "detectors propose, curation ratifies" (`:72-74`) and a deliberately short `PROVENANCE_COLS` tuple
  (`:117`) so that a measurement column can always veto a merge.
- **`config/theme_graph_identity_breaks.yml:11-13`** — the correct doctrine for the opposite
  relation: retire, never re-point, and mint the new holder at the next epoch.
- **`lib/delisted_symbols.py:17-19`** — "The exit is disclosed, never disappeared." A delisting
  strips scoring authority; it never deletes a store or a deep link.
- **`scripts/audit_reused_tickers.py`** — a working reuse detector with a correlation-based
  different-instrument test (`:24-28`) and three ratified acks (`config.yml:3578-3581`).

Three correct doctrines, one correct implementation and one working detector already exist. What is
missing is a **shared vocabulary and one arbitration surface** so they stop being five islands.

---

## 2. The five concepts

D2 fixes these. Restated with the discriminating question for each, because concept confusion is the
defect this spec exists to make hard.

| Concept | The question it answers | Changes when |
|---|---|---|
| **Issuer** | *Who is the economic entity?* | never, short of a merger that extinguishes it |
| **Security** | *Which legal instrument / share class?* | a new class is created; the instrument is extinguished |
| **Listing** | *Which security, on which venue?* | the security is admitted to, or removed from, a venue |
| **Symbol** | *What string does this venue use for this listing, on this date?* | freely — MMC→MRSH changed nothing else |
| **Vendor id** | *What string does this vendor use, on this date?* | freely, and **independently of the exchange** — Yahoo led the MMC rename and lags the FISV one (`lib/ticker_aliases.py:7-12`) |

The law, unchanged from D2: **a symbol is never an identity.** Both incidents in §1.4 and §1.6 are
one violation of that sentence.

Three consequences that the field list in §8 must satisfy:

1. **BRK.A and BRK.B are one issuer and two securities.** A field that is per-class (shares
   outstanding, voting rights, the price tape) belongs to the security; a field that is per-entity
   (CIK, sector, fundamentals) belongs to the issuer.
2. **ICBC's A-share and H-share are one issuer, two securities, two listings, two currencies.**
   `config.yml:6280` already pairs them (`"1398.HK": "601398.SS"`) but as a bare 1:1 ticker map with
   an explicitly stated share-equivalence assumption (`engine/hk_ah.py:11`).
3. **An ADR and its ordinary are one issuer and two securities** — the ADR is a distinct legal
   instrument with a deposit ratio. `engine/hk_adr_bridge.py:20-24` already lists four such pairs
   (`BABA↔9988.HK`, `BIDU↔9888.HK`, `JD↔9618.HK`, `TCOM↔9961.HK`) as "direct twins (same underlying
   company)" — the right relation, expressed as a ticker pair with no ratio field.

---

## 3. The three id forms — exact grammars

All three grammars are implemented in `lib/dataos/identity.py`; each regex is cited by its module-level
name so a reader can check the spec against the code rather than trusting either.

### 3.1 Listing key (bare) — the base of the other two

```abnf
listing-key    = country "-" mic "-" code [ "." disambiguator ]
country        = 2ALPHA-UPPER              ; ISO 3166-1 alpha-2
mic            = 4(ALPHA-UPPER / DIGIT)    ; ISO 10383, from the CLOSED list below
code           = (ALPHA-UPPER / DIGIT) *( ALPHA-UPPER / DIGIT / "." / "-" )
disambiguator  = ("2"/"3"/"4"/"5"/"6"/"7"/"8"/"9")   ; 2..9
               / (("1"-"9") 1*DIGIT)                  ; 10, 11, ...  — ".1" is ILLEGAL
```

As regexes, matching the implementation:

| Element | Regex | Source |
|---|---|---|
| country | `^[A-Z]{2}$` | `lib/dataos/identity.py::_COUNTRY_RE` |
| code | `^[A-Z0-9][A-Z0-9.\-]*$` | `lib/dataos/identity.py::_CODE_RE` |
| disambiguator tail | `^(?P<code>.+)\.(?P<n>[0-9]+)$` | `lib/dataos/identity.py::_DISAMBIGUATOR_RE` |
| whole key (validating) | `^[A-Z]{2}-(?:XNYS\|XNAS\|XASE\|XSHG\|XSHE\|XBSE\|XHKG\|XTSE\|XTSX)-[A-Z0-9][A-Z0-9.\-]*(?:\.(?:[2-9]\|[1-9][0-9]+))?$` | derived from `::KNOWN_MICS` + `::_CODE_RE` + `::_DISAMBIGUATOR_RE` |

The disambiguator alternation is `[2-9]|[1-9][0-9]+`, **not** `[2-9][0-9]*` — the latter silently
rejects `.10` through `.19`. The implementation does not have this bug because it parses the tail as
an integer and range-checks it (`lib/dataos/identity.py::parse_listing_key`,
`::ListingKey.__post_init__`); a regex written from the prose instead of from the code would.

Parsing rule, and it is not optional: **split on the first two hyphens only**, because a code may
contain one (`US-XNYS-BRK-B`). A trailing `.<digits>` is the disambiguator; any other dotted tail
(`BRK.B`) stays part of the code (`lib/dataos/identity.py::parse_listing_key`).

The MIC list is **closed**: `XNYS XNAS XASE XSHG XSHE XBSE XHKG XTSE XTSX`
(`lib/dataos/identity.py::KNOWN_MICS`). Minting on an unknown venue is a decision a human makes once
in a diff, not something a normalizer guesses at 03:00 during a nightly. Adding a MIC requires a
comment naming the estate that needs it (`::ListingKey.__post_init__`, the unknown-MIC raise).

Per-market code normalization:

| Market | Canonical `<CODE>` | Accepted inputs | Source |
|---|---|---|---|
| US | the exchange ticker at inception, class suffix preserved as printed | `MMC`, `BRK.B`, `BRK-B` | `lib/dataos/identity.py::_CODE_RE` |
| CN | 6 digits, no suffix | `600519.SH`, `600519.SS`, `600519`, `sh600519` | `lib/dataos/identity.py::normalize_cn_symbol` |
| HK | **5 digits, zero-padded** | `700`, `0700`, `00700`, `0700.HK` | `lib/dataos/identity.py::normalize_hk_symbol` |

CN normalization **cross-checks a declared venue suffix against the code range and RAISES on
conflict** (`lib/dataos/identity.py::normalize_cn_symbol`, the `declared != inferred` raise):
`600519.SZ` is not a Shenzhen listing with a typo, it
is two facts that cannot both be true, and picking one silently is how a Shanghai tape ends up under
a Shenzhen key.

> **SPEC NOTE (extends D2, does not contradict it).** HK width. D2's own example is `HK-XHKG-00700`
> — five digits — and the implementation agrees (`lib/dataos/identity.py::normalize_hk_symbol`, which
> returns `ListingKey("HK", XHKG, raw.zfill(5))`). The repo
> currently runs **both** widths: `zfill(5)` at `collectors/hk_fundamentals.py:69`,
> `collectors/hk_valuation.py:75`, `collectors/hk_ah_official.py:120`, `collectors/hk_names_zh.py:86`;
> `zfill(4)` at `collectors/hk_universe.py:138`, `scripts/collect_hk_connect_roster.py:146`,
> `engine/neuralweb/brain_gateway.py:1123`, `collectors/hk_names_zh.py:88` — the last file doing both
> two lines apart. The store is 4-digit (`data/hk_stocks/0700.HK.parquet`, 159 files). Canonical is
> **5**, matching the exchange; the 4-digit spellings become alias rows (§6), not a second key.

### 3.2 Issuer and security

```abnf
security-id = "SEC:" listing-key
issuer-id   = "ISS:" listing-key
```

`lib/dataos/identity.py::security_id`, `::issuer_id`. The prefix is visible on purpose: a grep, a
parquet dump or a log line tells you which concept you are holding (module docstring, the
"VISIBLE type prefix" bullet under "THE SHAPES").

`<CODE>` is **the code the listing carried at inception, never the current one**
(`lib/dataos/identity.py` module docstring, the "``<CODE>`` is the code the listing carried **at
inception**" bullet). That single rule is what makes the id survive the events in §1.4
and §1.6: Marsh stays `US-XNYS-MMC` after MMC→MRSH; Fiserv stays `US-XNAS-FISV` after FISV→FI.

`parse_id` returns `("issuer" | "security" | "listing", ListingKey)` and **raises** on `OPT:`/`FUT:`/
`IDX:`/`FX:` rather than returning a half-truth (`lib/dataos/identity.py::parse_id`) — returning a
partial parse for an instrument-class id is how a concept confusion gets written to a store.

**Issuer inception tie-break (new; D2 does not specify it).** The issuer id is derived from the
issuer's *inception listing*. When two listings share an inception date — the A+H simultaneous-IPO
pattern — resolve deterministically, in order:

1. earliest `list_date`;
2. the venue in the issuer's country of incorporation;
3. lexicographically lowest MIC.

Deterministic, no allocator, stable under re-derivation, and it never consults a clock outside the
listing facts themselves.

The worked results below (`ISS:CN-XSHG-601398` for ICBC, `ISS:US-XNYS-BABA` for Alibaba) depend on
listing dates that **have no in-repo source** — see §13 item 1. They are shown to exercise the rule,
not asserted as established facts, and the master must not mint either issuer id until the listing
dates are resolved from the exchange. This is the same discipline `config/delisted_symbols.yml:28-36`
already applies to exits: resolved, never inferred.

> **D2B1 AMENDMENT (2026-08-19, `research/prophet_v4/d2/D2B1_FROZEN_CONTRACT_2026-08-19.md`).**
> Rules 1–2 above have no in-repo data source at all (no per-security `list_date` table, no
> country-of-incorporation table) and per this section's own discipline are SKIPPED when
> unsourced, never guessed — so in practice, today, only rule 3 is ever reached. That left ties
> UNRESOLVED for same-venue, unsourced-date dual share classes — the exact shape of a US CIK
> group with two listings on the same MIC (GOOG/GOOGL, both `XNAS`, one CIK `1652044`). A fourth
> rule closes it:
>
> 4. **lexicographically lowest full listing key** (`<CC>-<MIC>-<CODE>[.N]`).
>
> `US-XNAS-GOOG` < `US-XNAS-GOOGL` picks GOOG as Alphabet's canonical issuer member; GOOGL's
> issuer_id is repointed from its own prior mint (`ISS:US-XNAS-GOOGL`) to `ISS:US-XNAS-GOOG` via
> the one authorized correction era (`scripts/build_security_master.py`, era constant
> `issuer_semantic_correction_v1`), recorded in `data/reference/issuer_migrations.parquet`.
> `security_id`/`listing_key` are never touched — this is an issuer-axis correction only. See
> `data/reference/security_master.parquet`'s new `issuer_state`/`issuer_cik`/
> `issuer_evidence_snapshot` columns and `lib/dataos/identity.IssuerMaster` for the reader.

### 3.3 Instrument classes

| Class | Grammar | Regex | Source |
|---|---|---|---|
| Option | `OPT:<listing key>:<YYYYMMDD>:<C\|P>:<strike×1000, 8 digits>` | `^OPT:(?P<listing>[^:]+):(?P<expiry>[0-9]{8}):(?P<right>[CP]):(?P<strike>[0-9]{8})$` | `lib/dataos/identity.py::_OPTION_RE` |
| Future | `FUT:<MIC>:<root>:<YYYYMM>` | `^FUT:(?P<mic>[A-Z0-9]{4}):(?P<root>[A-Z0-9]+):(?P<month>[0-9]{6})$` | `::_FUTURE_RE` |
| Index | `IDX:<provider>-<code>` | `^IDX:(?P<provider>[A-Z0-9]+)-(?P<code>[A-Z0-9.]+)$` | `::_INDEX_RE` |
| FX | `FX:<BASE><QUOTE>` | `^FX:(?P<base>[A-Z]{3})(?P<quote>[A-Z]{3})$` | `::_FX_RE` |

Two implementation rules that are part of the spec, not incidental:

- **A float strike is refused, not converted** (`lib/dataos/identity.py::_strike_decimal`).
  `Decimal(250.10) * 1000` is `250099.99999999997`, so a binary float silently mints a *different
  contract*. Callers pass `Decimal("250.10")` or `"250.10"`.
- **The index provider is part of the identity** (`::index_id`). Two providers publish
  differently-constructed indices under colliding short codes; dropping the provider is how "the S&P
  500" silently becomes whichever vendor answered.
- The futures MIC is deliberately **not** validated against the closed equity MIC list (`::future_id`) —
  the futures estate touches venues no equity listing here does.

### 3.4 Symbol and vendor id are not identifiers

They are **columns**, always accompanied by their scope. A symbol is `(venue, string, valid_from,
valid_to)`; a vendor id is `(vendor, string, valid_from, valid_to)`. Neither may be a primary key,
a filename stem, or a join key in any L2+ store. §6 is where they live.

---

## 4. Minting: deterministic derivation, no allocator

**Rule.** The id is *derived* from inception facts — country, MIC, inception code — by pure function.
There is no counter, no allocator service, no hash, and no central registry that must be consulted
before a session may name a security.

**Why, concretely.** VERIFIED: this repo currently has **275 registered worktrees**
(`git worktree list | wc -l`) and **163 directories** under `.claude/worktrees/`. A sequential
counter, or any allocator whose state is a tracked file, would be a permanent merge-conflict surface
across those trees, and two sessions minting the same new security in parallel would produce two
different ids for one thing. Derivation makes that impossible: both sessions produce the *same*
string, and the merge is a no-op. (`lib/dataos/identity.py` module docstring, the "**No allocator, no
counter, no hash.**" bullet.)

**Mint once and store.** The derivation is the *allocator*; the value written into the master is the
*authority*. A later correction to inception facts **never re-mints** — it appends an alias row. This
mirrors the CN spine's generation-atomic pointer promotion
(`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:102-108`) and satisfies
`DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY`: no run clock, no build time, no ingestion timestamp ever
enters an identity string. An idempotent mint is the whole point — re-running the nightly must not
create a second identity for an unchanged security.

**What inception means per market.**

| Market | Inception fact | Source available today |
|---|---|---|
| CN | `list_date` from `stock_basic`, floored at `BSE_LAUNCH = 2021-11-15` for BSE (`collectors/china_tushare_spine.py:126,1885-1887`) | in code, **no rows on disk** (`:40`) |
| US | first listing date | **no in-repo source** — nearest is the symbol-directory snapshot (`scripts/check_symbol_rename_drift.py:36-42`), which is a *current* listing set, not a history |
| HK | first listing date | **no in-repo source** |

PROPOSED, and the honest consequence: for US/HK the initial master must be seeded with
`inception_date = null` and `code_provenance = "first-observed"` rather than `"exchange-listing"`.
A null inception date is a **disclosed** weakness; back-dating one from a store's earliest bar would
be a fabricated fact, and `lib/symbol_directory_receipts.py:5-7` already forbids exactly that class
of synthesis ("readers must never synthesize a receipt from filenames, mtimes, Git, or the current
contents of an old file"). Same rule here.

---

## 5. Collisions

A collision is one case only: **the same venue reissues a code that a different, earlier security
carried.** Everything else — renames, migrations, class creation — is handled in §7 and is *not* a
collision.

**Resolution: an explicit integer disambiguator, starting at 2.** `US-XNYS-MMC.2`.
`.1` is rejected rather than accepted-as-first, because two spellings of one identity is exactly the
ambiguity the type removes (`lib/dataos/identity.py::ListingKey.__post_init__`, the
`disambiguator < 2` raise).

**Detectors propose, curation ratifies.** This is not a new doctrine; it is the one already ratified
in `config/theme_graph_identity_breaks.yml:19-26` and `engine/ledger_identity.py:72-74`. The
detector is `scripts/audit_reused_tickers.py`, which classifies a `zombie` as a key that (a) is in
the dead registry, (b) advances past `reused_grace_days`, (c) spans the death date, and (d) fails a
correlation test — "min of full-overlap and last-60 daily-return correlation < 0.35, or overlap too
thin to verify" (`:24-28`). A candidate is never an identity until an operator writes the row.

The three ratified cases become the first three disambiguated ids (PROPOSED — the master does not
exist yet):

| Ack (`config.yml`) | Prior holder | New holder | Ids |
|---|---|---|---|
| `:3579` ECHO | Echo Global Logistics, CUSIP 27875T101, take-private 2021-12 @ $48.25 | EchoStar, CIK 1415404, FIGI BBG000TGLV00, renamed from SATS 2026-06-24 | prior `SEC:US-XNAS-ECHO`; EchoStar keeps `SEC:US-XNAS-SATS` (its own inception code) — **not** `ECHO.2` |
| `:3580` SPWR | SunPower Corp, Ch.11 2024-08 | new SunPower (ex-Complete Solaria), adopted SPWR 2024-09, overlap corr ~0.05 | prior `SEC:US-XNAS-SPWR`; new holder `SEC:US-XNAS-SPWR.2` |
| `:3581` RPT | RPT Realty, merged into Kimco 2024-01 | Rithm Property Trust, overlap corr ~0.22 | prior `SEC:US-XNYS-RPT`; new holder `SEC:US-XNYS-RPT.2` |

All facts in the first three columns are quoted from `config.yml:3579-3581`; `scripts/audit_reused_tickers.py:4`
supplies "Echo Global Logistics (NASDAQ ECHO, CUSIP 27875T101)". The **MICs in the fourth column are
placeholders** — no in-repo artifact records which venue SPWR, RPT or SATS listed on, so each must be
resolved from the symbol directory before the id is minted. Getting a MIC wrong mints a different id,
which is the one mistake this scheme cannot self-heal.

The ECHO row is the instructive one and it is **not** a `.2` case: EchoStar already had an identity
under its own inception code (SATS), so the correct action is an *alias* on the existing security,
not a new mint. `.2` is only for a genuinely new security that has no prior identity of its own. Two
of the three ratified reuse cases resolve without a disambiguator ever being minted — which is the
expected ratio, and the reason `.2` is rare, greppable, and never silent.

**Relation to `co:<market>:<SYMBOL>#2`.** The theme graph's `#N` and this `.N` express the same
relation. They do not need to merge on day one; §11 specifies the crosswalk. What must not happen is
a third convention.

---

## 6. The alias table

**Grain:** one row per `(vendor, vendor_symbol, security_id, valid_from, valid_to)`
(`lib/dataos/identity.py::AliasRow`).

**Interval convention: `valid_from` INCLUSIVE, `valid_to` EXCLUSIVE.** An inclusive end would make
the changeover day ambiguous — two rows valid at once on 2026-01-14, which is exactly the day the
MMC/MRSH answer has to be unambiguous (`lib/dataos/identity.py::AliasRow` docstring; enforced in
`::AliasRow.covers`). `None` on either side is an open bound.

**Ambiguity is refused at construction, not at read.** Building a table where two rows for one
`(vendor, vendor_symbol)` — *or* one `(vendor, security_id)` — overlap raises `IdentityError`
(`lib/dataos/identity.py::VendorAliasTable._assert_unambiguous`, called from `::VendorAliasTable.__init__`).
Both directions, because a translation layer that can return either of two answers is not a
translation layer.

**Two required directions:**

- `resolve(vendor, vendor_symbol, on) -> security_id | None` — what did this vendor *mean* by this
  string on this date (`::VendorAliasTable.resolve`);
- `vendor_symbol_for(vendor, security_id, on) -> str | None` — what did this vendor *call* this
  security on this date (`::VendorAliasTable.vendor_symbol_for`).

The second direction is the one `lib/ticker_aliases.py` cannot express at all, and its absence is
what makes a backfill dangerous: a timeless map re-labels the past.
`lib/dataos/identity.py::VendorAliasTable`'s class docstring states it exactly — a two-entry timeless
dict "can say 'MMC means MRSH' but cannot say 'MMC meant MMC before 2026-01-14'."

**Storage.** `reference/identity_aliases.parquet` inside the generation, following
`collectors/china_tushare_spine.py:1990`. `VendorAliasTable` does **no I/O** by design
(`lib/dataos/identity.py::VendorAliasTable`, which loads only from plain mappings via
`::VendorAliasTable.from_records`) so it stays importable in a thin CI lane with no filesystem.

**Columns:**

| Column | Type | Notes |
|---|---|---|
| `vendor` | str | `yahoo`, `tushare`, `polygon`, `massive`, `cboe`, `akshare`, `edgar`, `nasdaq_symdir`, `exchange` |
| `vendor_symbol` | str | the literal string the vendor uses |
| `security_id` | str | `SEC:` form, never bare |
| `valid_from` / `valid_to` | date / null | half-open; null = open bound |
| `alias_kind` | enum | `canonical` · `vendor_symbol` · `exchange_symbol` · `former_symbol` · `bse_old_code` · `zero_pad_variant` · `class_notation` · `occ_root` · `cusip` · `cik` · `figi` — extends `collectors/china_tushare_spine.py:1930,1940` |
| `source` | str | e.g. `tushare.bse_mapping` (`:1941`), `config.yml:ticker_key_migrations` |
| `evidence` | str | the ratification receipt; prose is legal here and only here |

`alias_kind` is the field that lets the thirteen seams collapse without losing what each one *meant*.
`lib/ticker_aliases.py` rows become `vendor_symbol`; `breadth.ticker_fixups` rows become
`exchange_symbol`; the HK 4-digit spellings become `zero_pad_variant`; `BRK-B`/`BRK.B` become
`class_notation`; the CN old-BJ codes become `bse_old_code`, which already exists.

---

## 7. Identity events

The event table is the mechanism that makes §5's "rename is not a collision" enforceable. Each row
states what changes and — more importantly — what must **not**.

| Event | Issuer | Security | Listing | Symbol | Price series |
|---|---|---|---|---|---|
| **Rename** (MMC→MRSH) | unchanged | unchanged | unchanged | new row, old row closed at the effective date | **one continuous series** |
| **Vendor rename lag** (Yahoo still serves FISV) | unchanged | unchanged | unchanged | exchange symbol changed; **vendor symbol did not** | one series; the alias table carries both |
| **Exchange migration** (NYSE American → NYSE) | unchanged | unchanged | **new listing** on the new MIC; old listing closed | new | one series, spliceable; the *listing* key changes and the *security* key does not |
| **Share-class creation** (a new B class) | unchanged | **new security**, new id | new listing | new | separate series; never spliced |
| **Spinoff** | **new issuer** for the spun entity; parent unchanged | new security | new listing | new | new series; parent's `_tradj` basis is re-scaled from the ex-date — see §10 |
| **Merger (stock-for-stock)** | acquired issuer **extinguished** | acquired security extinguished at the effective date | listing closed | retired | series **ends**; the acquirer is a different, pre-existing security on its own line and **may not be spliced** (`config/delisted_symbols.yml:38-43`) |
| **Merger (cash)** | extinguished | extinguished | closed | retired | series ends; **no successor** |
| **Delisting** | may survive (OTC) | survives | listing closed | may survive off-exchange | series ends at the last trading session; scoring authority stripped, history retained (`lib/delisted_symbols.py:10-19`) |
| **Relisting / uplisting** (TCNNF → NYSE:TRLV) | unchanged | unchanged | **new listing** | new | one economic history, two listing intervals; treat as a key migration, never as a delisting (`config/delisted_symbols.yml:33-36`) |
| **Ticker reuse by a different issuer** | **different issuer** | **new security**, `.2` | new listing | reused string | **two series that must never touch** (§5) |

Two governing rules:

1. **`successor_ticker` is null by default and is load-bearing.** `config/delisted_symbols.yml:38-43`
   already states the discipline: "an all-stock acquirer (Devon) is a DIFFERENT, pre-existing security
   on its own price line, and a cash acquirer (Sumitomo Forestry) leaves no US-listed line at all.
   Neither continues this series, so neither may be spliced onto it." Fill it only when the same tape
   genuinely continues under a new symbol — and then it is a rename, not a delisting.
2. **Every row is resolved, never inferred.** The required evidence standard already exists
   (`config/delisted_symbols.yml:28-36`): absence from the NASDAQ symbol directory *and* the issuer's
   SEC filing history showing the exit (Form 25/25-NSE, usually Form 15 and a merger 8-K with Item
   2.01/3.01). "A vendor probe saying 'possibly delisted' is a HINT, never the evidence" — Yahoo says
   exactly that about a live security whose symbol merely changed.

**Corporate actions are events the Security Master REFERENCES, not events it stores.** There is no
corporate-action event store anywhere in the repo, and the absence is *declared*: VERIFIED,
`contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:232,246` makes
`point_in_time_corporate_actions` a **required** property pinned to `{"const": false}`. On the CN side
the spine stores unadjusted nominal (`collectors/china_tushare_spine.py:47`) and lists "pro_bar
adjusted price construction" under `not_tested`
(`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:294`). This spec therefore defines the
*identity-bearing* subset of corporate actions (the rows above) and declares splits/dividends/ex-dates
**out of scope** — they belong to the price-basis spec (D4), which needs the factor table this repo
does not have. The vocabulary to hang it on already exists:
`contracts/capital_structure_event.schema.json:65` carries `"corporate_action"` in its `family` enum,
and `collectors/china_tushare_spine.py:4684` documents `daily` as "unadjusted nominal OHLC; pre_close
is ex-rights adjusted vendor field" — the one derivable CN corporate-action detector in the repo.

---

## 8. Security Master field list

Derived from consumers that exist in this repo. Each field names the caller that needs it; a field
with no caller is not in the list. Fields marked **†** have no source in this repo today and ship
null with a disclosed reason (§D6 vocabulary: `NO_COVERAGE`).

### 8.1 Issuer table — grain: one row per `issuer_id`

| Field | Type | Needed by |
|---|---|---|
| `issuer_id` | str `ISS:…` | every join below |
| `legal_name` | str | `engine/name_resolver.py:21-27` (legal-form stripper), `collectors/edgar_deadnames.py` |
| `name_zh` | str | `collectors/hk_names_zh.py:86`, `engine/entity_resolver.py:14-16` (~280 basket names ∪ ~2.3k analyst pairs) |
| `cik` | str | `collectors/edgar_deadnames.py:14-21`; the dead-ticker→CIK bridge is the survivorship de-bias. The drop it repairs is `collectors/edgar.py:702-704` — `t = cik_t.get(cik); if t is None: continue  # delisted / unmapped — can't join to prices` (note: `edgar_deadnames.py:6` cites this as `edgar.py:423`, which is now `fy = cand` — the line reference has drifted and should be corrected in that docstring) |
| `country_of_incorporation` | ISO-2 | §3.2 tie-break rule 2 |
| `figi` | str | **a source exists and no lane cited it**: SEC 13F `INFOTABLE.tsv` carries `FIGI` (`engine/institutional_census/sec_sources.py:145,324`) and it is a declared string column in the census catalog (`engine/institutional_census/catalog.py:100`). Scope caveat — that is a *holdings-line* FIGI, per security per filing, not an issuer master, so it seeds rather than defines. `config.yml:3579` separately cites `BBG000TGLV00` for EchoStar in prose |
| `status` | enum `active·extinguished` | `lib/delisted_symbols.py`, `config/theme_graph_identity_breaks.yml:11` |
| `extinguished_at` / `extinguished_reason` | date / enum | §7 merger rows |

### 8.2 Security table — grain: one row per `security_id`

| Field | Type | Needed by |
|---|---|---|
| `security_id` | str `SEC:…` | everything |
| `issuer_id` | str | class/ADR/A+H rollups (§9.7, §9.9) |
| `security_class` | enum `common·adr·gdr·preferred·etf·fund·warrant·unit` | three partial sources already agree in shape: `data/openfigi/cusip_ticker.parquet.sec_type` carries live `Common Stock` / `Depositary Receipt` values (610 rows, VERIFIED); `config/institutional_13f.yml:59` enumerates `[Common Stock, Depositary Receipt, REIT, Partnership Shares]`; `collectors/china_tushare_spine.py:1955,1973` uses `A_share` / `exchange_fund` |
| `share_class` | str, nullable | `BRK.B`; distinguishes GOOG/GOOGL, which `engine/ledger_identity.py:98-100` explicitly protects from being merged (Jaccard 0.769 and "genuinely two instruments") |
| `currency` | ISO-4217 | `collectors/china_tushare_spine.py:1868` hard-refuses a non-CNY A-share; `engine/hk_ah.py:73` needs CNY vs HKD |
| `cusip` | str, partial coverage | `engine/entity_resolver.py:194 resolve_cusip`; `data/sec_ftd/panel.parquet` keyed `(date, symbol, cusip)`; **`data/openfigi/cusip_ticker.parquet`, 610 CUSIP→ticker rows** (`collectors/openfigi.py:39`), plus the ~60-CUSIP ARK seed it layers over (`engine/smart_money.py:213-225`) |
| `isin` | str, **bonds only** | `collectors/corp_bond_holdings.py:46` `OUT_COLS = ["isin", "cusip6", …]` — a real, ISIN-keyed corporate-bond holdings parser. No equity ISIN source exists |
| `sedol` | str **†** | genuinely absent: `SEDOL` appears once, as a column name in a docstring describing an iShares workbook layout (`collectors/corp_bond_holdings.py:227`), and is **not** in that parser's `OUT_COLS` (`:46`) |
| `underlying_security_id` | str, nullable | ADR → ordinary (`engine/hk_adr_bridge.py:20-24`) |
| `deposit_ratio` | Decimal, nullable **†** | required for ADR↔ordinary price math; **no in-repo source** (`grep -rniE "adr_ratio\|deposit_ratio\|depositary"` returns only 13F security-type strings and unrelated 8-K vocabulary) |
| `occ_root` | str, nullable **†** | `engine/options_focused_quote.py:641-646` builds a 21-char OCC symbol from a `root` that is assumed equal to the equity ticker; the census found **zero** matches for `root_symbol\|occ_root\|underlying_root\|option_root_map` across `engine/options_*.py` and `collectors/*.py` |
| `st_flag` / `st_provenance` | bool / enum | `collectors/china_tushare_spine.py:2642-2649` (exact `stock_st` endpoint, 2016+) vs `:529-532` (name-regex inference, pre-2016). Two confidences; never collapse to one boolean |
| `inception_date` / `code_provenance` | date **†** US/HK / enum | §4 |
| `status` | enum `active·delisted·extinguished·reused_retired` | `lib/delisted_symbols.py`, §5 |

### 8.3 Listing table — grain: one row per `listing_id` × validity interval

| Field | Type | Needed by |
|---|---|---|
| `listing_id` | str bare key | `collectors/china_tushare_spine.py:520` (already emits it) |
| `security_id` | str | the A+H and cross-listing joins (§9.7) |
| `mic` | str | `collectors/china_tushare_spine.py:177` already maps SSE/SZSE/BSE → XSHG/XSHE/XBSE |
| `exchange_symbol` | str | the symbol *the exchange* prints, time-scoped in §6 |
| `board` | enum `main·star·chinext·bse` | `collectors/china_tushare_spine.py:465-480`, with the vendor-disagreement guard at `:1873-1877` |
| `repo_suffix` | str | `.SS` / `.SZ` / `.BJ` / `.HK` — the store filename convention (`collectors/china_tushare_spine.py:178`) |
| `list_date` / `delist_date` | date | `collectors/china_tushare_spine.py:1902-1903`; `list_date` inclusive, `delist_date` **inclusive** effective end (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:93`) |
| `effective_from` / `effective_to` | date | `collectors/china_tushare_spine.py:1904-1905`; BSE floored at 2021-11-15 (`:1885-1887`) |
| `list_status` | enum `L·D·P·G` | `collectors/china_tushare_spine.py:175,1901` |
| `primary` | bool | a consolidated-tape last print is not the primary closing auction (D4); needed to say which listing owns the official close |
| `lot_size` | int **†** | **no source anywhere** — census `grep -rln "lot_size\|board_lot\|round_lot\|每手"` over `collectors lib engine` returned zero, reconfirmed this pass. Blocks any HK per-name board-lot or STAR 200-share minimum work |
| `timezone` / `session_calendar_id` | str | `lib/cn_calendar.py:76` (`HOLIDAY_COVERAGE_END = 2027-12-31`), `lib/hk_calendar.py:100-111` (LNY table ends 2030) — both degrade silently past their window; the master must carry a *monitored expiry*, not a comment |

Note the shape: **8.3 is nearly a rename away from `collectors/china_tushare_spine.py:1889-1910`.**
That is the finding — the schema exists, it is CN-scoped and dormant, and the work is generalization
plus turning it on, not design.

---

## 9. Worked examples

Each traced from the vendor string to the canonical id and back. `→` means "resolves to".

### 9.1 Marsh McLennan — MMC → MRSH (2026-01-14, same listing, same CUSIP)

| | |
|---|---|
| Issuer | `ISS:US-XNYS-MMC` |
| Security | `SEC:US-XNYS-MMC` |
| Listing | `US-XNYS-MMC`, MIC XNYS, `primary=true` |
| Exchange symbol | `MMC` [.., 2026-01-14) · `MRSH` [2026-01-14, ..) |

Alias rows:

| vendor | vendor_symbol | security_id | valid_from | valid_to | alias_kind |
|---|---|---|---|---|---|
| `exchange` | `MMC` | `SEC:US-XNYS-MMC` | null | 2026-01-14 | `exchange_symbol` |
| `exchange` | `MRSH` | `SEC:US-XNYS-MMC` | 2026-01-14 | null | `exchange_symbol` |
| `yahoo` | `MMC` | `SEC:US-XNYS-MMC` | null | 2026-01-14 | `vendor_symbol` |
| `yahoo` | `MRSH` | `SEC:US-XNYS-MMC` | 2026-01-14 | null | `vendor_symbol` |
| `massive` | `MMC` | `SEC:US-XNYS-MMC` | null | 2026-01-14 | `vendor_symbol` |
| `massive` | `MRSH` | `SEC:US-XNYS-MMC` | 2026-01-14 | null | `vendor_symbol` |

What this fixes, checkably. Today `data/massive_stock_day/MMC.parquet` (1,137 rows, ends 2026-01-13)
and `data/massive_stock_day/MRSH.parquet` (117 rows, starts 2026-01-14) are two unrelated files
(VERIFIED, Appendix A2). Under the alias table both resolve to `SEC:US-XNYS-MMC`, so
`resolve("massive", "MMC", 2025-06-01)` and `resolve("massive", "MRSH", 2026-06-01)` return the same
security and the two files concatenate into one continuous tape. The `insurance` basket's 19th member
returns. `data/baskets/extras.parquet` keeps its `MMC` column — no store is renamed (§10).

Note the direction trap this removes: `lib/ticker_aliases.py:39` says `MMC → MRSH` while
`config.yml:2044` says `MRSH → MMC`. Both are correct for their own purpose. Neither is an identity.

### 9.2 Fiserv — FISV → FI (2023), the vendor LAGS the rename

| | |
|---|---|
| Issuer / Security | `ISS:US-XNAS-FISV` / `SEC:US-XNAS-FISV` — the **inception** code, not today's |
| Exchange symbol | `FISV` [.., 2023) · `FI` [2023, ..) |
| Yahoo symbol | `FISV` [.., ..) — **never moved** (`lib/ticker_aliases.py:38`) |

| vendor | vendor_symbol | valid_from | valid_to | alias_kind |
|---|---|---|---|---|
| `exchange` | `FISV` | null | 2023-XX-XX | `exchange_symbol` |
| `exchange` | `FI` | 2023-XX-XX | null | `exchange_symbol` |
| `yahoo` | `FISV` | null | null | `vendor_symbol` |

(The exact 2023 effective date is not recorded anywhere in the repo — `lib/ticker_aliases.py:7-8` and
`config.yml:2048` both say only "2023". It must be resolved from the exchange before the row is
written; a guessed date is a fabricated fact.)

VERIFIED consequence today: `data/yahoo/FISV.parquet` has 10,020 rows from 1986-09-25 and
`data/yahoo/FI.parquet` has 3,901 rows from 2011-01-03, **byte-identical over all 3,899 overlapping
rows** (close ratio min = max = 1.0). One security, two keys, one of which is missing the entire
1986–2010 history. Under this spec both are alias rows on `SEC:US-XNAS-FISV`, the duplicate is
detectable mechanically (§12 check 3b), and the reader that wants the full tape gets it.

### 9.3 Kweichow Moutai — 600519 across `.SH` / `.SS` / bare

| Spelling | Origin | Resolves to |
|---|---|---|
| `600519.SH` | TuShare `ts_code` (`collectors/china_tushare_spine.py:179`) | `CN-XSHG-600519` |
| `600519.SS` | repo ticker + Yahoo (`data/china_stocks_raw/600519.SS.parquet`, VERIFIED present) | `CN-XSHG-600519` |
| `600519` | bare code, e.g. CSIndex constituent tables | `CN-XSHG-600519` |
| `sh600519` | Sina/EastMoney prefix form (`collectors/china_universe.py:99`) | `CN-XSHG-600519` |
| `600519.SZ` | — | **RAISES** (`lib/dataos/identity.py::normalize_cn_symbol`, the `declared != inferred` raise) |

| | |
|---|---|
| Issuer / Security | `ISS:CN-XSHG-600519` / `SEC:CN-XSHG-600519` |
| Listing | `CN-XSHG-600519`, board `main`, currency CNY, repo suffix `.SS` |

Reconciling the vendor: `collectors/tushare_client.py:94-101 norm_ticker` converts `.SH → .SS` and
passes everything else through — a *store-key* normalizer, not an identity. It stays, and becomes one
alias-producing function instead of six (§1.5). The `.SH`/`.SS` split is the exact pair the spine
contract names: "Repository tickers are `600519.SS`… stable IDs are `CN-XSHG-600519`"
(`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:86-88`). `.SS` is also a legitimate
US-vendor suffix, which is why the ambiguity must die at the boundary rather than inside a join
(`lib/dataos/identity.py`, the "China A-share normalization (§D2)" section comment; the `.SS` entry
in `::_CN_SUFFIX_MICS` carries the same note).

### 9.4 Beijing Stock Exchange — 920163

| | |
|---|---|
| Listing | `CN-XBSE-920163` |
| Board | `bse` |
| `effective_from` | `max(list_date, 2021-11-15)` — **BSE eligibility cannot precede 2021-11-15** (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:94`; enforced at `collectors/china_tushare_spine.py:1885-1887` with `BSE_LAUNCH` at `:126`, and again in the daily path at `:4171`) |
| Old BJ code (e.g. `83xxxx`) | alias row, `alias_kind = bse_old_code`, source `tushare.bse_mapping` (`collectors/china_tushare_spine.py:1936-1942`) — "Every canonical BSE mapping target must be `920xxx`"
(`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:89`) |

Today, VERIFIED: `920163` **cannot enter the live CN pipeline at all**.
`collectors/china_universe.py:135` returns `None` for it, and the store has zero `.BJ` files out of
1,592. `collectors/china_ths_concepts.py:108` *would* map it to `920163.BJ`, so the name exists in
concept-board data and not in the price store — a name that is simultaneously known and unfetchable.
Under this spec the code-range table is `collectors/china_tushare_spine.py:465-480` (the most rigorous
one, and the only one with a runtime disagreement guard at `:1873-1877`), everyone imports it, and a
BSE code either resolves or raises. It never silently evaporates.

### 9.5 STAR 688xxx and ChiNext 300xxx (including the 309800–309999 CDR range)

| Code | Board | MIC | Listing id | Rule |
|---|---|---|---|---|
| `688001` | `star` | XSHG | `CN-XSHG-688001` | SSE + `688`/`689` prefix (`collectors/china_tushare_spine.py:468`; `lib/dataos/identity.py::cn_board` → `CNBoard.STAR`, routed to `XSHG` by `::_cn_mic_from_code`) |
| `300001` | `chinext` | XSHE | `CN-XSHE-300001` | SZSE + `300000 ≤ code ≤ 309999` (`collectors/china_tushare_spine.py:470-479`) |
| `309900` | `chinext` | XSHE | `CN-XSHE-309900` | same range — the **309800–309999 CDR** sub-range, called out by name at `collectors/china_tushare_spine.py:475-477`: "Do not misclassify future 303-309 families as main-board securities" |

VERIFIED: `data/china_stocks_raw` holds `688001.SS`, `688002.SS`, `688003.SS` and `300001.SZ`… but
**zero `309xxx` names** (`ls data/china_stocks_raw | grep -cE '^309'` → 0). The CDR range is therefore
a *prospective* correctness requirement, not a current defect — which is exactly why it must be pinned
in the code-range table now: the first 309xxx name to appear will be classified by whichever converter
sees it first. `collectors/china_ths_concepts.py:110` gets the *venue* right by falling through to
`.SZ`, but it carries no board concept at all — so a 309xxx CDR arrives downstream indistinguishable
from a 000xxx main-board name, and the price-limit band that depends on the board is then wrong.

Board is a **listing** attribute, not a security attribute: it determines the price-limit band and the
lot minimum, both of which are venue rules.

### 9.6 Tencent — 700 / 0700 / 0700.HK

| Spelling | Where it appears | Resolves to |
|---|---|---|
| `700` | bare code | `HK-XHKG-00700` |
| `0700` | `collectors/hk_universe.py:138` `zfill(4)`, `scripts/collect_hk_connect_roster.py:146` | `HK-XHKG-00700` |
| `0700.HK` | yfinance native; the store filename `data/hk_stocks/0700.HK.parquet` (VERIFIED present) | `HK-XHKG-00700` |
| `00700` | `collectors/hk_fundamentals.py:69`, `collectors/hk_valuation.py:75`, `collectors/hk_names_zh.py:86` `zfill(5)` | `HK-XHKG-00700` |

| | |
|---|---|
| Issuer / Security | `ISS:HK-XHKG-00700` / `SEC:HK-XHKG-00700` |
| Currency | HKD |
| `underlying_security_id` | null (Tencent's US line is the thin OTC `TCEHY`, explicitly excluded as a twin at `engine/hk_adr_bridge.py:27`: "thin/illiquid → group ETF proxy only") |

`normalize_hk_symbol('700') == normalize_hk_symbol('0700.HK')` by construction
(`lib/dataos/identity.py::normalize_hk_symbol`). The four spellings above become `zero_pad_variant` alias rows;
`data/hk_stocks/0700.HK.parquet` keeps its filename (§10).

### 9.7 A dual-listed A+H pair — ICBC (one issuer, two securities, two listings, two currencies)

| | A-share | H-share |
|---|---|---|
| Security | `SEC:CN-XSHG-601398` | `SEC:HK-XHKG-01398` |
| Listing | `CN-XSHG-601398` | `HK-XHKG-01398` |
| Currency | CNY | HKD |
| Board / venue | `main`, XSHG | XHKG |
| Issuer | `ISS:CN-XSHG-601398` — **both** (§3.2 tie-break rule 2, incorporated CN; listing dates unsourced in-repo — see the §3.2 caveat) | ← same |

Today this pair is a bare ticker map: `config.yml:6280` `"1398.HK": "601398.SS"`, one of twelve
(`:6278-6290`). `engine/hk_ah.py:11` states the two assumptions it rests on — "We assume 1:1 A/H
share-equivalence" — and `:73` shows the FX leg is a *cross-rate through USD*
(`cny_per_hkd = usdcny / usdhkd`), not a quoted CNYHKD pair. The docstring is honest that "the
ABSOLUTE level differs slightly from the official Hang Seng AH Premium index" (`:1-16`).

What the Security Master changes: the pair stops being a hand-maintained dict and becomes a **derived
query** — `SELECT security_id FROM security WHERE issuer_id = 'ISS:CN-XSHG-601398'` returns both
legs, and the 1:1 share-equivalence assumption becomes an explicit per-security field
(`shares_per_unit`, default 1) rather than a sentence in a docstring. Note the ordering constraint:
the twelve config pairs remain the *ratified* seed. The master must reproduce all twelve before the
config map is retired (§12 check 4).

### 9.8 An option contract on a US underlying — OCC/OSI and Polygon `O:` as aliases of one id

Canonical:

```
OPT:US-XNAS-AAPL:20260918:C:00250000
```

`lib/dataos/identity.py::option_contract_id`. Strike is carried as strike × 1000 zero-padded to 8 digits, so a
tenth-of-a-cent strike is exact and lexical order is numeric order.

The four encodings in active use today, all of which become aliases:

| # | Encoding | Example | Source |
|---|---|---|---|
| 1 | OCC/OSI 21-char, root left-padded to 6 | `AAPL  260918C00250000` | `engine/options_focused_quote.py:641-646` — `f"{root:<6}{expiration:%y%m%d}{right}{strike_millis:08d}"`; parser asserts `len == 21` at `:650` |
| 2 | Polygon/OPRA `O:` prefix, **variable-length root, no padding** | `O:SPY260710C00525000` | `collectors/polygon_options.py:77` persists `det.get("ticker")` verbatim as `strike_ticker`; VERIFIED on disk — `data/polygon_gex/chains/2026-07-09.parquet` (22 chain files), `strike_ticker.head(3)` = `O:SPY260710C00525000`, `…C00530000`, `…C00565000` |
| 3 | synthetic sha256 | `contract:uchain:<64 hex>` over `root\|expiration\|right\|strike` | `engine/options_focused_quote.py:636-638` |
| 4 | bare tuple, no symbol at all | `(root, strike, exp, right)` | `engine/options_structure.py:249-261` |

Encodings 1 and 2 differ only in root padding and prefix, so the crosswalk is mechanical *once the
root is known*. Encoding 3 is a one-way hash: it can be **verified** against a canonical id
(recompute and compare) but never inverted, so it must be stored **alongside** the canonical id, never
instead of it. Encoding 4 is not an identifier and becomes a projection of the canonical id.

The unsolved half, stated plainly: `OPT:` is defined over the **underlying's listing key**, and
nothing in the repo maps an OCC root to an equity listing. The census found zero matches for
`root_symbol|occ_root|underlying_root|option_root_map` across `engine/options_*.py` and
`collectors/*.py`, and `collectors/polygon_options.py:76` passes `underlying` straight through from
its input argument. For the overwhelming majority of names root == ticker; the exceptions (class
shares, post-merger adjusted series) are precisely the ones that break, and they break silently. Hence
`occ_root` in §8.2, and hence the §12 check that every distinct root observed in
`data/polygon_gex/chains/*.parquet` resolves.

Two related facts a consumer of this id must know, both already documented: the contract multiplier is
a single hardcoded `100.0` (`engine/gex_engine.py:28`) with no adjusted-multiplier path, so
post-merger 1-for-N special OCC series are silently mispriced; and the right is encoded four ways
(`C`/`P`, `CALL`/`PUT`, `is_call` bool, `option_type` str) with the OPRA field name `cp_flag` appearing
nowhere. The canonical id form fixes the *identity*; it does not fix either of those, and this spec
does not claim to.

### 9.9 An ADR and its ordinary — Alibaba

| | ADR (NYSE) | Ordinary (HKEX) |
|---|---|---|
| Security | `SEC:US-XNYS-BABA` | `SEC:HK-XHKG-09988` |
| `security_class` | `adr` | `common` |
| Listing | `US-XNYS-BABA` | `HK-XHKG-09988` |
| Currency | USD | HKD |
| `underlying_security_id` | `SEC:HK-XHKG-09988` | null |
| `deposit_ratio` | **†** null, `NO_COVERAGE` | n/a |
| Issuer | `ISS:US-XNYS-BABA` (§3.2 rule 1; listing dates unsourced in-repo — see §3.2 caveat) | ← same |

`security_class = adr` is **derivable today, not proposed**: `data/openfigi/cusip_ticker.parquet`
carries `sec_type` per CUSIP and its live values include `Depositary Receipt` — VERIFIED on the second
row of that file, `00138L108 / RERE / ATRENEW INC / Depositary Receipt` (`collectors/openfigi.py:39`).
So the master can *classify* an ADR from an existing store on day one. What it cannot do is price one
against its ordinary, because the ratio is absent.

`engine/hk_adr_bridge.py:20-24` already asserts the relation for four pairs, and its own words are the
right ones: "Direct twins (same underlying company)". What it cannot express, and what the Security
Master adds, is that this is an **issuer**-level twinning of two **different securities** — which is
why `adr_pct` (`:16`) is a legitimate cross-security comparison while a naive splice of the two price
series would not be.

The deposit ratio is the honest gap. Without it, an ADR price and an ordinary price cannot be compared
in levels, only in returns — which is exactly what `hk_adr_bridge` does (percentage moves only). That
constraint is currently implicit in the module's arithmetic; under this spec it becomes an explicit
null with a reason, and any consumer attempting a level comparison hits it instead of silently getting
a number. `engine/hk_adr_bridge.py:25-32` records the complementary case — five HK names with no clean
US twin, routed to `KWEB`/`FXI` group ETF proxies and labelled "proxy, no direct ADR". A proxy is not
an alias and must never become one; it is a modelling choice with a different id
(`SEC:US-XNYS-KWEB`) and no issuer relation to the name it proxies.

---

## 10. What the Security Master does NOT do

1. **It does not rename any store, file or page slug.** `data/hk_stocks/0700.HK.parquet` keeps its
   name. `data/baskets/extras.parquet` keeps its `MMC` column. `site/signals/ECHO.json` keeps its
   URL. The master is a *resolution* layer; renaming stores is a separate, later, opt-in migration
   with its own blast radius. `lib/delisted_symbols.py:17-19` already sets the precedent — "the page
   keeps its deep links (CSP-R1)."
2. **It does not splice price series.** Deciding that two tapes concatenate is a data decision made by
   a store's reader using the master's answer, not by the master. Cf. `config/delisted_symbols.yml:38-43`.
3. **It does not adjust prices, and it does not store splits, dividends or ex-dates.** Corporate
   actions enter here only where they change *identity* (§7). Basis and adjustment vintage are D4's.
4. **It does not classify sectors or themes.** GICS, theme-graph membership and basket membership are
   time-scoped *attributes* that join to `security_id`; they are not identity.
5. **It does not resolve free text.** `engine/entity_resolver.py` and `engine/name_resolver.py` remain
   the text→ticker ladder. They gain a canonical target to resolve *to*; their layers, their
   precision-over-recall rule (`engine/name_resolver.py:9-11`) and their never-raise contract
   (`engine/entity_resolver.py:3-5`) are unchanged.
6. **It does not originate signals or scores.** `authority_tier = context_only`, per the house
   epistemics law.
7. **It is not a live-listing directory.** Whether a symbol trades *today* is answered by the NASDAQ
   symbol-directory snapshot (`scripts/check_symbol_rename_drift.py:36-42`), which stays.

**The thing being superseded, named.** `scripts/check_symbol_rename_drift.py:11-12` declares its own
boundary: *"This is deliberately not a company-identity mapper. Historical filings and point-in-time
membership keep the symbols they actually carried."* That scoping was correct for a guard whose only
tool was a two-entry dict. This spec supplies the company-identity mapper that sentence was written to
disclaim the absence of, and the guard's *checks* survive intact inside §12 — `check_alias_contract`
(`:64-88`) and `check_universe_coverage` (`:91-108`) become two of the five, re-expressed over the
alias table instead of over `YAHOO_FETCH_ALIASES`. The second half of that sentence — historical
membership keeps the symbols it carried — is **retained as law**, and is precisely why §6's alias rows
are time-scoped rather than a rewrite of history.

---

## 11. Migration: thirteen seams to one, without a flag day

The rule throughout: **no seam is deleted until its rows are provably reproduced by the master.** Each
phase is independently shippable and independently revertible.

Nine of the thirteen surfaces in §1.1 are absorbed (the §11.4 table folds them into eleven ordered
steps, because the CN converters and the HK zero-pad sites are each one step covering several call
sites). The other four — `engine/entity_resolver.py`, `engine/name_resolver.py`,
`collectors/edgar_deadnames.py`, `lib/symbol_directory_receipts.py` — are deliberately kept, for the
reason given at the end of §11.4.

### 11.1 Phase M0 — commit the prototype, and stop the bleeding

`lib/dataos/identity.py` and its tests are untracked (`git status --porcelain` → `?? lib/dataos/`,
`?? tests/test_dataos_identity.py`). Until they are committed, nothing here is enforceable and one
`git clean` or one `scripts/worktree_gc.py` sweep deletes the implementation. **This is the first
work item and it blocks every other phase.**

### 11.2 Phase M1 — vocabulary, no behaviour change

- Rename `collectors/china_tushare_spine.py:520`'s `security_id` field. It emits a **listing** key.
  Either (a) rename the column to `listing_id` and add `security_id = "SEC:" + listing_id`, or
  (b) keep the column name and change the value to the `SEC:` form. (a) is preferred: the bare key is
  genuinely useful and already threaded through `research/cn_limit_alpha_sol/W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md:30`.
  Zero rows exist on disk (`collectors/china_tushare_spine.py:40`), so this rename has **no data
  migration cost today** — and it will have one the moment the spine is switched on. Do it first.
- Publish the closed MIC list and the CN board table as the single importable source. Every converter
  in §1.5 becomes a thin wrapper over it. `collectors/china_tushare_spine.py:465-480` wins on merit:
  it is the only one with a runtime guard that raises when the vendor's declared market disagrees with
  the code range (`:1873-1877`).

### 11.3 Phase M2 — the master exists and is empty of authority

Generalize `compile_security_master` (`collectors/china_tushare_spine.py:1830`) to accept a per-market
adapter, and seed three markets:

| Market | Seed source | Expected rows |
|---|---|---|
| US | symbol-directory snapshots (`scripts/check_symbol_rename_drift.py:36-42`) ∪ store filename stems from `data/stocks`, `data/yahoo`, `data/baskets/ohlcv`, `data/massive_stock_day` | thousands; `data/massive_stock_day` alone is the widest (20,476 per the census) |
| CN | `data/china_stocks_raw` stems (1,592, VERIFIED) — and `.BJ` is **structurally absent**, so BSE seeds empty until the spine is on | 1,592 |
| HK | `data/hk_stocks` stems (159, VERIFIED) | 159 |

Everything is **display-tier and advisory** in this phase. No reader changes. The output is a catalog
and a disagreement report — which is already useful on its own: it is the first artifact in the repo
that can answer "how many securities do we actually have".

### 11.4 Phase M3 — absorb the seams, one alias_kind at a time

Each step is: import the seam's rows as alias rows with the right `alias_kind`, prove round-trip
equality against the original map, then make the original map a **thin shim that reads the master**.
Delete nothing yet.

| Order | Seam | `alias_kind` | Round-trip proof |
|---|---|---|---|
| 1 | `lib/ticker_aliases.py:37-40` (2 rows) | `vendor_symbol` | `fetch_symbol(t)` and `store_key(s)` return identical results for every universe member |
| 2 | `config.yml:2043-2049` `ticker_fixups` (2 rows) | `exchange_symbol` | `collectors/breadth.py:330`'s map is reproduced exactly |
| 3 | `config.yml:3611` `ticker_key_migrations` (1 row) | `former_symbol` | `engine/ledger_identity.py:124 load_migrations` returns the same dict, chains resolved (`:156-169`) |
| 4 | `config/delisted_symbols.yml` (95 lines) | status field, not an alias | `lib/delisted_symbols.py:is_delisted` unchanged for every row |
| 5 | HK zero-pad variants (8 call sites, §3.1 note) | `zero_pad_variant` | every 4-digit and 5-digit spelling resolves to the same listing |
| 6 | CN converters (6, §1.5) | none — they become one function | every code in `data/china_stocks_raw` resolves identically through the old and new paths |
| 7 | `config.yml:6278-6290` `ah_pairs` (12 rows) | issuer relation | the issuer query in §9.7 returns all twelve pairs |
| 8 | `engine/hk_adr_bridge.py:75` (4 twins) | issuer relation + `underlying_security_id` | all four pairs reproduced |
| 9 | `config/theme_graph_identity_breaks.yml` | crosswalk `co:<market>:<SYM>#N` ↔ `.N` | every ratified break maps to exactly one disambiguated id |
| 10 | `config.yml:3578-3581` `reused_ticker_acks` | `.2` mints per §5 | ECHO resolves without a `.2`; SPWR and RPT mint one |
| 11 | `data/openfigi/cusip_ticker.parquet` (610 rows) | `cusip` + seeds `security_class` from `sec_type` | `engine/smart_money.py:213 load_cusip_ticker()` returns the same dict; every `sec_type` value maps into the §8.2 enum without a residual bucket |

Order 11 is placed last because it is the only seam that *adds* rows rather than restating existing
ones, and because `collectors/openfigi.py:125` refuses to run when smart_money has no CUSIPs — so its
coverage is a function of 13F ingestion, not of the universe. It is a seed, not an authority.

`engine/entity_resolver.py`, `engine/name_resolver.py`, `collectors/edgar_deadnames.py` and
`lib/symbol_directory_receipts.py` are **not** absorbed. They are producers and consumers of identity,
not competing definitions of it; they gain a canonical target and keep their own logic.

### 11.5 Phase M4 — the master becomes authority

Flip the shims: the original maps become derived views over the master, or are deleted with their
consumers re-pointed. Only now may a seam's file be removed, and only for seams whose round-trip proof
has been green in CI for a full nightly cycle.

**What has no flag day, by construction.** Every phase leaves every existing map working. A reader
that never learns about the master keeps behaving exactly as it does today, because in phases M2–M3
the master is either advisory or a shim behind an unchanged function signature. That is the property
that makes this shippable across 275 worktrees without a coordinated cutover.

---

## 12. The guard: proving that a vendor symbol resolves

PROPOSED — `scripts/check_security_identity.py` (VERIFIED not to exist: `ls scripts/check_security_identity.py`
→ No such file), in the guard-registry style of `scripts/check_symbol_rename_drift.py`. It absorbs that
guard's two existing checks (rows 1 and 2 below) and adds four that would have caught the incidents in §1.

GitHub annotations must be emitted as a bare `print("::error title=<slug>::<msg>", flush=True)` at line
start, never through a logger — the house law, and `scripts/check_symbol_rename_drift.py:72-73,104-106`
already does it correctly.

| # | Check | Severity | Would have caught |
|---|---|---|---|
| 1 | **Alias-table well-formedness.** No two rows for one `(vendor, vendor_symbol)` or one `(vendor, security_id)` overlap in time. Directly `lib/dataos/identity.py::VendorAliasTable._assert_unambiguous` | BLOCK | — (structural) |
| 2 | **Every universe key resolves.** Every member of every declared universe (sp500/400/600, CN search members, HK breadth, basket memberships) resolves to exactly one `security_id` on the run date. Generalizes `check_universe_coverage` (`scripts/check_symbol_rename_drift.py:91-108`) from 3 US universes to all of them | BLOCK | §1.5 — a BSE code that resolves to `None` |
| 3 | **Resolution implies materialization** — the check that does not exist today. For every `(universe member, store)` pair that the store is declared to cover, the resolved security has **a file in that store** whose date span covers the member's active interval. | BLOCK | §1.4 — `data/baskets/ohlcv/MMC.parquet` never existing |
| 3b | **No two store files resolve to one security** without a declared alias relationship | BLOCK | §1.6 — `FI` and `FISV` both live in `data/yahoo`; §1.4 — `MMC` and `MRSH` both in `data/massive_stock_day` |
| 4 | **Ratified maps are reproduced.** Every row of every seam in §11.4's table resolves through the master to the same answer the seam gives | BLOCK | a migration that silently drops a curated row |
| 5 | **Every observed vendor symbol resolves or is quarantined.** Sweep the distinct symbols actually present in the stores — parquet stems in `data/{stocks,yahoo,baskets/ohlcv,massive_stock_day,china_stocks_raw,hk_stocks}`, `underlying` and `strike_ticker` in `data/polygon_gex/chains/*.parquet` — and require each to resolve. An unresolved symbol is reported by name with its store, never dropped | WARN → BLOCK once the backlog is zero | §9.8 — an OCC root that is not the equity ticker |

Check 3 is the one that matters most, and it is the precise gap in the guard being superseded.
`scripts/check_symbol_rename_drift.py` proves that a **name resolves**; it never asks whether a
**series exists**. MMC resolved correctly the entire time — `lib/ticker_aliases.py:39` has carried the
row — while `data/baskets/ohlcv/MMC.parquet` did not exist for seven months. Resolution without
materialization is exactly the shape of a silent loss.

Check 5 starts at WARN deliberately. `lib/delisted_symbols.py:6-9` states the reason better than a
rewrite would: a warning that is always on "trains the reader to ignore the one tripwire that would
catch the NEXT real outage". A guard whose first run reports thousands of unresolved symbols is a
guard nobody reads. It escalates to BLOCK only when the backlog reaches zero.

---

## 13. Open questions and known weaknesses

1. **US and HK inception dates have no in-repo source** (§4). The initial master ships them null with
   `code_provenance = "first-observed"`. Anyone who back-dates one from a store's earliest bar has
   fabricated a fact.
2. **`deposit_ratio`, `lot_size` and `sedol` have no source at all** — verified absent by grep this
   pass (Appendix A6). Each blocks a specific capability: ADR↔ordinary level comparison; HK per-name
   board lots and the STAR 200-share first-order minimum; one leg of cross-vendor reconciliation.
   `figi` and `isin` **do** have sources, contrary to an earlier draft of this document and to the
   census: FIGI from SEC 13F info tables (`engine/institutional_census/sec_sources.py:145,324`), ISIN
   from the corporate-bond holdings parser (`collectors/corp_bond_holdings.py:46`). Both are
   scope-limited (a holdings line, and bonds) and neither is an equity issuer master, but "we have
   none" was wrong and the seed should be used.
3. **The CN spine has no rows.** Everything in §9.3–§9.5 that cites `collectors/china_tushare_spine.py`
   cites *code*, not data. Its own docstring says every collection path is disabled (`:40`), and it is
   additionally gated on a vendor-entitlement receipt (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:16-24`).
   The master's CN leg is only as real as that gate.
4. **`engine/ledger_identity.py:28` disagrees with the store** about whether `data/stocks/SATS.parquet`
   exists (§1.3). Needs the module owner's resolution; it does not change the double-count conclusion.
5. **The `92` vs `920` BSE prefix divergence is latent, not live** (§1.5). It becomes a real defect the
   day `921xxx`–`929xxx` is allocated. Cheap to fix now, expensive to detect later.
6. **Option root ↔ equity ticker has no crosswalk** (§9.8) and no known divergent example was tested
   against actual data. The check exists (§12 check 5); the backlog size is unknown until it runs.
7. **`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` interacts with §9.4.** Once BSE names become resolvable,
   they become fetchable — and the only live CN tape is the Yahoo-plane adjusted one that adjudication
   forbids for limit-band work. Making a name resolvable must not be read as making it *usable* for
   legal-limit math. Identity resolution and basis authority are independent gates.
8. **Cross-repo user data carries no identity.** `charting-app/supabase/migrations/0001_init.sql`
   (`watchlist_symbols.symbol text`, `alerts.symbol text`, `favorites.value text`) and the bot's
   per-symbol parquet filenames all key on a bare string with no market qualifier, and no repo outside
   Macro imports `lib/ticker_aliases.py` (census cross-repo lane, which ran the grep over Mastermind's
   `brain/`, `portfolio/`, `data_layer/` and `bridge/` and found zero hits; not re-run in this pass).
   This spec deliberately does **not** propose changing them:
   the cross-repo boundary is governed elsewhere and `duplicate_control_planes` is a standing
   prohibition. It only makes a stable id *available* to them.

---

## Appendix A — verification commands

Every VERIFIED claim above reproduces from these. Run from
`/Users/chriswong/Documents/Cluade/Macro Dashboard` unless noted.

**A1 — worktree count** (`git worktree list` run from this worktree; the `ls` uses the absolute path
because the count is of the *primary* checkout's worktree root):

```
git worktree list | wc -l                                                       → 275
ls -d "/Users/chriswong/Documents/Cluade/Macro Dashboard/.claude/worktrees"/*/ | wc -l   → 163
```

**A2 — the MMC / SATS / FI stores:**

```python
import pandas as pd, os
for p in ["data/massive_stock_day/MMC.parquet", "data/massive_stock_day/MRSH.parquet",
          "data/stocks/SATS.parquet", "data/stocks/ECHO.parquet",
          "data/yahoo/FI.parquet", "data/yahoo/FISV.parquet",
          "data/baskets/ohlcv/MMC.parquet", "data/baskets/ohlcv/MRSH.parquet",
          "data/stocks/MMC.parquet", "data/yahoo/MMC.parquet"]:
    if not os.path.exists(p):
        print(f"{p}: ABSENT"); continue
    d = pd.read_parquet(p)
    print(f"{p}: rows={len(d)} {d.index.min()} .. {d.index.max()}")
```

**A3 — FI/FISV are the same tape:**

```python
import pandas as pd
a = pd.read_parquet("data/yahoo/FI.parquet"); b = pd.read_parquet("data/yahoo/FISV.parquet")
i = a.index.intersection(b.index); r = (a.loc[i, "close"] / b.loc[i, "close"]).dropna()
print(len(i), float(r.min()), float(r.max()))            → 3899 1.0 1.0
```

**A4 — CN store composition:**

```
ls data/china_stocks_raw | wc -l                             → 1592
ls data/china_stocks_raw | grep -c '\.BJ'                    → 0
ls data/china_stocks_raw | grep -cE '^309'                   → 0
ls data/china_stocks_raw | grep -cE '^900'                   → 0
ls data/hk_stocks | wc -l                                    → 159
ls data/china_stocks_raw/600519.SS.parquet                   → present
ls data/china_stocks_raw | grep '^688' | head -3             → 688001.SS 688002.SS 688003.SS
```

**A5 — extras keying:**

```python
import pandas as pd
e = pd.read_parquet("data/baskets/extras.parquet")
print(e.shape, "MMC" in e.columns, "MRSH" in e.columns)      → (880, 666) True False
```

**A6 — absence greps** (run from the worktree; zero output = absent):

```
grep -rniE "adr_ratio|deposit_ratio|adr_shares" --include="*.py" --include="*.yml" engine lib collectors scripts config
grep -rniE "lot_size|board_lot|round_lot"       --include="*.py" engine lib collectors scripts
grep -rniE "\bsedol\b"                          --include="*.py" --include="*.yml" engine lib collectors scripts config
```

Use `\b` word boundaries. A bare `grep -rln ISIN` returns dozens of false positives — pandas
`.isin(...)` calls and the substring inside `RAISING` — and reading that output as evidence of an
ISIN column is how an earlier draft of this document got §8.2 wrong. Counter-check the positives:

```
grep -rniE "openfigi" --include="*.py" engine lib collectors scripts
    → collectors/openfigi.py, engine/smart_money.py:201-225, engine/entity_resolver.py:24,184
grep -rniE "\bfigi\b" --include="*.py" engine lib collectors scripts
    → engine/institutional_census/catalog.py:100, engine/institutional_census/sec_sources.py:145,324,
      engine/smart_money.py:214-225
```

Note that `engine/biocatalyst/operational_store.py:125-156` lists `figi`, `isin`, `sedol`, `cusip` in
`NEVER_ALLOWED_PAYLOAD_KEY_TOKENS` — a **fence forbidding** those identifiers in that store, not a
source providing them. A grep hit is not a source.

**A6b — the OpenFIGI store:**

```python
import pandas as pd
d = pd.read_parquet("data/openfigi/cusip_ticker.parquet")
print(d.shape, list(d.columns))
    (610, 6) ['cusip', 'ticker', 'name', 'exch', 'sec_type', '_mapped_at']
print(sorted(set(d["sec_type"]))[:4])      # includes 'Common Stock', 'Depositary Receipt'
```

**A7 — untracked prototype:**

```
git status --porcelain | grep dataos
    ?? config/dataset_registry.yml
    ?? lib/dataos/
    ?? tests/test_dataos_identity.py   (+ nulls, price, quality, registry, temporal)
git ls-files lib/dataos/                                     → (empty)
```

---

## Appendix B — citation index

Distinct `file:line` citations in this document: **143**, across **46** distinct files. `lib/dataos/identity.py`
is **not** in either count — it is cited by symbol (`path::symbol`) throughout, for the reason given
in the conventions at the top of this document. Recount:

```python
import re
t = open("research/MASTERMIND_SECURITY_MASTER_SPEC.md").read()
body = t.split("## Appendix B")[0]
c = set()
for m in re.finditer(r'([A-Za-z0-9_./\-]+\.(?:py|yml|yaml|json|md|sql))\`?\:\s*'
                     r'(\d+(?:-\d+)?(?:\s*,\s*\d+(?:-\d+)?)*)', body):
    for part in m.group(2).split(","):
        c.add((m.group(1), part.strip()))
print(len(c), len({f for f, _ in c}))
```

The recount runs over the body only (it excludes this appendix, which restates the same citations) and
it **under-reports**, because it cannot see bare `:NNN` back-references written after a paragraph has
already named the file — e.g. `scripts/audit_reused_tickers.py`'s `:24-28` in §5, or the bare `:NNN`
refs to `collectors/china_tushare_spine.py`. It also does not see the ~30 `lib/dataos/identity.py::symbol`
citations, which carry no line number by design. Two entries below (`collectors/edgar.py:423`,
`collectors/edgar_deadnames.py:6`) appear in the body unqualified because they are quoted from another
module's docstring; they are folded into their real paths here, which is why the file count is 46
rather than the raw 48.

Three further sources are cited by constant or column name rather than by line, and are not in the
count: `charting-app/supabase/migrations/0001_init.sql` (`watchlist_symbols.symbol`, `alerts.symbol`,
`favorites.value`), `data/openfigi/cusip_ticker.parquet` (column `sec_type`), and
`data/polygon_gex/chains/*.parquet` (column `strike_ticker`).

Sources by weight:

| File | Cited lines |
|---|---|
| `collectors/china_tushare_spine.py` | 40, 47, 126, 175, 177, 178, 179, 465-480, 468, 475-477, 491, 520, 1830, 1868, 1885-1887, 1889-1910, 1901, 1902-1903, 1904-1905, 1930, 1936-1942, 1940, 1955, 1973, 1990, 2642-2649, 4684 |
| `config.yml` | 2043-2049, 2044, 2048, 3578-3581, 3579, 3579-3581, 3611, 3611-3617, 3612, 6278-6290, 6280 |
| `lib/ticker_aliases.py` | 7-12, 7-8, 9-12, 18-26, 37-40, 38, 39 |
| `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` | 16-24, 86-88, 89, 93, 94, 102-108, 294 |
| `engine/entity_resolver.py` | 3-5, 14-16, 24, 184, 194, 291 |
| `scripts/check_symbol_rename_drift.py` | 11-12, 36-42, 72-73, 83-87, 91-108, 104-106 |
| `collectors/china_universe.py` | 98-110, 99, 113-135, 120-126, 135 |
| `config/theme_graph_identity_breaks.yml` | 6, 11-13, 11, 13, 19-26 |
| `engine/ledger_identity.py` | 13, 28, 72-74, 98-100, 124 |
| `engine/hk_adr_bridge.py` | 20-24, 25-32, 27, 75 |
| `engine/smart_money.py` | 201-225, 213-225, 213, 214-225 |
| `lib/delisted_symbols.py` | 6-15, 6-9, 10-19, 17-19 |
| `collectors/china_ths_concepts.py` | 97-110, 108, 110 |
| `collectors/openfigi.py` | 5-7, 39, 125 |
| `config/delisted_symbols.yml` | 28-36, 33-36, 38-43 |
| `collectors/corp_bond_holdings.py` | 46, 227 |
| `collectors/edgar_deadnames.py` | 6, 14-21, 59 |
| `collectors/hk_names_zh.py` | 86, 88 |
| `collectors/polygon_options.py` | 76, 77 |
| `contracts/market_memory/spy_daily_price_source_observation.v1.schema.json` | 232, 246 |
| `engine/hk_ah.py` | 11, 73 |
| `engine/institutional_census/sec_sources.py` | 145, 324 |
| `engine/name_resolver.py` | 9-11, 21-27 |
| `engine/options_focused_quote.py` | 636-638, 641-646 |
| `collectors/breadth.py` | 330 |
| `collectors/edgar.py` | 423 (stale ref quoted from a docstring), 702-704 |
| `collectors/hk_ah_official.py` | 120 |
| `collectors/hk_fundamentals.py` | 69 |
| `collectors/hk_universe.py` | 138 |
| `collectors/hk_valuation.py` | 75 |
| `collectors/tushare_client.py` | 94-101 |
| `config/institutional_13f.yml` | 59 |
| `contracts/capital_structure_event.schema.json` | 65 |
| `engine/biocatalyst/operational_store.py` | 125-156 |
| `engine/gex_engine.py` | 28 |
| `engine/institutional_census/catalog.py` | 100 |
| `engine/neuralweb/brain_gateway.py` | 1123 |
| `engine/options_structure.py` | 249-261 |
| `lib/cn_calendar.py` | 76 |
| `lib/hk_calendar.py` | 100-111 |
| `lib/symbol_directory_receipts.py` | 5-7 |
| `research/cn_limit_alpha_sol/W2_BAND_PROGRESS_SUBSTRATE_RECEIPT_2026-08-08.md` | 30 |
| `scripts/audit_reused_tickers.py` | 4 |
| `scripts/build_china_microstructure.py` | 234 |
| `scripts/collect_hk_connect_roster.py` | 146 |
| `scripts/d4_cn_supply_absorption_phase0.py` | 132-136 |

**`lib/dataos/identity.py` — cited by symbol.** Line numbers are deliberately absent: the file is
untracked and being edited by a concurrent lane, and an earlier revision of this document pinned
line numbers that had drifted 30–50 lines by the time anyone opened them, so every one resolved to
different content than claimed. The 31 symbols cited in the body, in file order:

| Section of the module | Symbols cited |
|---|---|
| module docstring | "THE SHAPES" table; the `<CODE>`-at-inception bullet; the "No allocator, no counter, no hash" bullet; the VISIBLE-type-prefix bullet |
| venue authority | `KNOWN_MICS` |
| listing-key grammar | `_COUNTRY_RE`, `_CODE_RE`, `_DISAMBIGUATOR_RE` |
| listing key | `ListingKey`, `ListingKey.__post_init__`, `parse_listing_key` |
| issuer / security | `security_id`, `issuer_id`, `parse_id` |
| instrument classes | `_OPTION_RE`, `_FUTURE_RE`, `_INDEX_RE`, `_FX_RE`, `_strike_decimal`, `option_contract_id`, `future_id`, `index_id` |
| China A-share | "China A-share normalization (§D2)" section comment, `_CN_SUFFIX_MICS`, `cn_board`, `_cn_mic_from_code`, `normalize_cn_symbol` |
| Hong Kong | `normalize_hk_symbol` |
| alias table | `AliasRow`, `AliasRow.covers`, `VendorAliasTable`, `VendorAliasTable.__init__`, `VendorAliasTable.from_records`, `VendorAliasTable._assert_unambiguous`, `VendorAliasTable.resolve`, `VendorAliasTable.vendor_symbol_for` |

VERIFIED 2026-08-12: every symbol above resolves in the working-tree copy of the file
(`for s in _COUNTRY_RE _CODE_RE … vendor_symbol_for; do grep -c "$s" lib/dataos/identity.py; done` →
non-zero for all 31). The file was **726 lines** at that reading (`wc -l lib/dataos/identity.py` →
726), not the 676 an earlier revision of this document asserted. Expect that number to move again;
that is the point of citing by symbol.
