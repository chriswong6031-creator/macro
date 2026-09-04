# F09-1 — evidence-bound cash-deal premium/spread: precision and coverage report

Operation `marketontology-f09-premium-math-v1-20260902-sol-001` · carrier
[macro#6785](https://github.com/mastermindx-market-intelligence/macro/issues/6785) ·
branch `claude/f09-premium-math-v1-20260903` · base `origin/main@5af021ba`.

Context-only throughout. Nothing here scores, ranks as a signal, sizes, or feeds Prophet.

## 1. The defect, measured before any change

`data/special_situations/context/latest.json` (`special_sits_context.v1`, `asof=2026-09-01`) on
`origin/main` led `risk_arb_top` with:

```json
{"ticker": "LGMK", "company": "LogicMark, Inc.",
 "gross_spread_pct": 64.57, "annualized_pct": 42790.2, "days_to_close": 30}
```

Five keys. No deal price, no close price, no exchange session, no accession, no source URL, no
formula revision, no quality state. **The absence is the defect — not the magnitude.**

Reproduced directly against the `origin/main` module (receipt below is verbatim output):

```
1. month-end substitution:
   days_to_close('2026-11', 2026-09-01) = 90   <- an unobserved day, invented
2. ungrounded publication:
   {'deal_price': 25.0, 'live_price': 15.19, 'gross_spread_pct': 64.58,
    'days_to_close': 90, 'annualized_pct': 654.3, 'consideration': 'cash'}
   provenance keys present: []
3. consumer divergence — special_sits_intel sorted `annualized_pct or 0`
```

Three independent causes, each now closed:

| # | Cause (origin/main) | Site | Closed by |
|---|---|---|---|
| 1 | `YYYY-MM` silently resolved to **month end**, then annualized off the invented day | `special_arb.py:185-187` | month-end resolution deleted; a window keeps `days_to_close=None`, `annualized_pct=None` |
| 2 | live price was `panel[col].dropna().iloc[-1]` — a bare last-non-null row, no session, no as-of, no freshness | `special_situations.py:622-624` | typed `price_input` carrying session, `sessions_behind`, basis, source artifact, calendar |
| 3 | "unaffected" price was a fixed **30-row** lookback (rows are not sessions) | `special_situations.py:625` | filing-reference price = last session **strictly before** first verified SEC availability, or `REFERENCE_SESSION_UNRESOLVED` |
| 4 | `mastermind_emit` filtered `consideration == "cash"`; `special_sits_intel` did not, and sorted `annualized_pct or 0` | `special_situations.py:966` vs `special_sits_intel.py:1088` | one `select_ordered_context()` owner consumed by both |
| 5 | a `0.6–1.8` plausibility band already guarded this path and **admitted** LGMK (ratio 1.6457) | `special_arb.py:130` | band and `_DAYS_CAP` removed — a clamp that lets the defect through is not a gate |

**Test coverage before this wave: one assertion** — `assert "risk_arb_top" in result`. That is
how 42,790.2% reached every Neural Web consumer without anything failing.

## 2. Precision gate — zero false precise publications

22-case corpus, `tests/fixtures/special_situations/f09/corpus.json`, run through the real
extractor and current-term compiler:

| verdict | n |
|---|---|
| correct publication (price matched the expected value exactly) | 9 |
| **correct decline** (no price published where none may be) | 10 |
| recall miss (should have published, declined) | 0 |
| **FALSE PUBLICATION** | **0** |

Three cases were added by the critical repair, all previously absent and all reproduced as
false publications first (§8): a rejected historical **cash** proposal under *Background of the
Merger* beside a current **all-stock** merger (measured at head `a88c12f2` as `VERIFIED`, offer
48.00, spread +20%, consideration `cash`); a *Prior Proposals* price that is the document's only
per-share number; and a **fairness-opinion** DCF value quoted beside a correctly-scoped offer,
which must NOT suppress the real price. Out-of-scope prices are not discarded — all three are
retained as `deferred` observations noted `outside_current_transaction_scope`, so the evidence
stays visible while never becoming a live term.

Hostile negatives that must never yield an offer price, and all declined: special **dividend**
per share, preferred **redemption** price, option **exercise** price, **aggregate/enterprise**
value expressed per fully diluted share, two **conflicting** cash prices in one filing, and
**per-ADS vs per-ordinary-share** wording for different amounts.

Cases that legitimately observe a price but are refused downstream by the reducer rather than by
the extractor: `cash_and_stock_merger` ($12.00 cash leg → `NOT_FIXED_CASH`),
`contingent_value_right` ($9.00 + CVR → `NOT_FIXED_CASH`), `cross_currency_bare_dollar` ($32.00
on a CAD listing → currency never established, `AMBIGUOUS`).

### Honest limits of this number

- **The corpus is authored, not sampled.** The excerpts are written in canonical SEC
  merger/tender phrasing; they are not verbatim filing bodies, because committing production
  filing bodies is forbidden by the operation. So **100% recall here is a statement about the
  corpus, not about EDGAR.** Real-world recall is unmeasured and is expected to be materially
  lower — the extractor is deliberately tuned to decline.
- Precision is the load-bearing claim, and it is the one the design optimises: every candidate
  span must survive an explicit per-share anchor plus a ±160-character negative lexicon.
- Recall against live filings can only be measured on the natural production run, which is
  gated behind #6783 (Mac Studio daily-runner recovery). Until then this capability is
  `BUILT_NOT_PROVEN / PRODUCTION_INERT`.
- A bare `$` is admitted as USD **only** where it cannot be anything else (no other dollar
  qualifier anywhere in the document AND a USD listing). Every observation records which of the
  four `currency_basis` values applied, so an inference can never be mistaken for an observation.

## 3. What a published number now carries

```
term      → accession, CIK, form type, filing date, source URL, body sha256,
            document id, character offsets, excerpt sha256, extraction revision
price     → exchange session, sessions behind expected, price basis, source artifact, currency
clocks    → source filing date · system availability (acquired_at) · market session ·
            calculation as-of (calc_asof) · build time — five distinct clocks, never merged
formula   → formula_revision, and four SEPARATELY named numbers:
            stated_premium_pct · filing_reference_premium_pct · live_gross_spread_pct ·
            annualized_pct (exact observed close DATE only)
state     → VERIFIED · STALE_PRICE · AMBIGUOUS · NOT_FIXED_CASH · TERMINAL ·
            SOURCE_UNAVAILABLE · INELIGIBLE_CATEGORY · CALCULATION_UNAVAILABLE
```

## 4. LGMK disposition

The mandated regression canary is **excluded from the ordered context with a typed reason**,
not clamped and not deleted:

- with the same offer and close price but **no observed exact close date**, the row computes a
  real `live_gross_spread_pct` (visible), `annualized_pct = None`, `orderable = False`, reason
  `DATE_PRECISION_INSUFFICIENT`, and is counted in the visible degraded census;
- with a genuinely observed exact date it publishes with full receipts — pinned by
  `test_an_extreme_but_fully_grounded_value_is_disclosed_not_hidden`, where a grounded extreme
  value is published and flagged `extreme_value: true` rather than banded away;
- `test_no_clamp_no_band_no_ticker_exception_in_the_owner` fails the build if the string `LGMK`,
  `_PLAUS_LO`, `_PLAUS_HI` or `_DAYS_CAP` ever reappears in the owner.

Whether the *real* LGMK row is grounded or excluded on live data is answerable only by the
natural production run — see §5.

## 5. What is NOT proven

- No production proof. The daily route is under the #6783 disk-admission floor, and this
  capability may not claim `PROVEN_LIVE` until one natural authoritative cycle emits the
  artifact and the real Neural Web consumers read it. No dispatch was made to manufacture proof.
- The observation ledger (`data/special_situations/observations/observations.jsonl`) has never
  been written by a production build; it is exercised only by tests in tmp dirs.
- Real-world extraction recall is unmeasured (§2).
- The five Neural Web consumers (`mastermind_context`, `world_state`, `ask_brain`,
  `brief_context`, `cortex`) were censused and pass through `risk_arb_top` rows unchanged, so
  the richer rows propagate without edits. That is a read of their code, not a live observation.

## 6. Market Ontology disposition (MO-PAID-064 / MO-DELTA-023)

Recorded here rather than by editing
`MARKET_ONTOLOGY_F00C_GRANULAR_CLOSURE_LEDGER_2026-09-02.csv`: that file is F00C's dated
closure artifact and belongs to a different operation. Rewriting another lane's dated ledger
would destroy its record; final ledger reconciliation belongs to acceptance, not to this wave.

F00C row `MO-PAID-064` (paired `MO-DELTA-023`) carries:

- `granular_disposition: NEW_BOUNDED_BUILD`, `capability_state_c2: PARTIAL`
- `next_bounded_child: SPLIT — premium-math slice BUILDABLE-NOW from EDGAR tender filings;
  financing-path/break-fee stays RIGHTS-GATE`
- `acceptance_test: one classified M&A event gets computed premium math`
- `authority_ceiling: research_only`

**Disposition after this wave.** The premium-math slice is **source-complete and unproven**:

| ledger field | state after F09-1 |
|---|---|
| premium-math slice | implemented under the existing owner — no new store, scheduler or plane |
| acceptance test ("one classified M&A event gets computed premium math") | **not yet satisfiable in production** — the collector lane that writes the observation ledger has no caller, and the natural daily route is under the #6783 floor |
| financing-path / break-fee / antitrust | untouched, still RIGHTS-GATE — explicit F09-1 non-goals |
| authority ceiling | unchanged `research_only`; `is_signal=False` is structural in the reducer's output |
| capability state | `BUILT_NOT_PROVEN / PRODUCTION_INERT` — **not** `PROVEN_LIVE` |

The honest reading of the acceptance test is that it is **not** met: computed premium math now
exists and is grounded, but no classified M&A event has passed through it in production. Two
things must land first — the `enrich_deal_terms()` caller (awaiting a path-boundary ruling) and
the #6783 host recovery. Both are recorded as `next_actions` in
`agentos/handoffs/MARKET-ONTOLOGY-F09-PREMIUM-MATH-2026-09-03.md`.

## 7. Repair after Sol's exact-head review (review 5099936758)

The independent review rejected the first head and named eight defects. Six were real
false-precision holes; three of those my own records had half-named without my drawing the
conclusion. All are repaired at this head.

| # | Defect on `5db9634a31a3` | Repair |
|---|---|---|
| 1 | `enrich_deal_terms()` never called by `build(refresh=True)` — a natural run leaves the ledger empty and every deal reports `SOURCE_UNAVAILABLE` | wired into the refresh sequence **before** `desk_payload()`, under the granted one-path expansion; `--no-refresh` stays source-inert, pinned by a build-path test |
| 2 | observations grouped by issuer **CIK**, so two unrelated deals shared terms | accession-isolated; multiple accessions merge only through an explicit `link_supersession()` chain. `/A` or a shared filer proves nothing |
| 3 | digest taken over `_strip_markup(raw)[:40000]` while the span claimed `full_submission_text` | complete response bytes retained (`raw_sha256`/`raw_bytes`) beside a **versioned** normalized projection; `completeness ∈ complete/truncated/unknown`, and anything but `complete` can never be VERIFIED |
| 4 | ledger checked a `schema` label; malformed JSON skipped silently | every row re-validated against a **closed** digest; malformed/invalid rows counted and surfaced as `INTEGRITY_FAILED` + `PARTIAL_GENERATION`, never a healthy subset |
| 5 | `_calendar_index` derived the expected session from the panel being graded | `lib/nyse_calendar.py` **unchanged** as the owner; every price carries `calendar_owner`, `calendar_revision`, `expected_session`, `sessions_behind` and an immutable `artifact_sha256` |
| 6 | `market_currency("") → "USD"`; date-only `date_filed` as availability; `date.today()` as market clock | unresolved listing returns `None`; reference sessions need the exact SEC acceptance moment parsed from source bytes; `now_utc` is a **required** argument — omitting it raises |
| 7 | consideration matched document-wide, so a background CVR could classify the live deal | every field resolves inside one `transaction_scope()` anchored on the price span and cut at section boundaries |
| 8 | `stated_premium_pct` published with no comparator | publishable only with a captured basis; no comparator, or two disagreeing ones, publishes nothing — and never substitutes for the computed filing-reference premium |

### Evidence

- **RED first**: 16 new mutants failed against the reviewed head before any fix; all green now.
- **Required REDs, all present**: same CIK/two deals · forged observation · tampered offset ·
  malformed trailing JSONL line · truncated body · unresolved foreign listing + bare `$` ·
  whole-panel stale · missing calendar receipt · premarket vs after-close acceptance · real
  `build(refresh=True)` path · background-only CVR · cash financing beside a stock deal ·
  two premium comparators · bare `35% premium`.
- **143 passed** across `test_special_arb` / `test_special_situations` / `test_special_sits_intel`.
- **No regressions**: 40 failures across the full dependent surface, all in unrelated suites
  (`china_heatmap_gate`, `us_board_gate`, `seo_meta_rollout`, …) that need `site/`/`data/`;
  **zero** in any `special_*` suite.

### One repair that changed a rule rather than a line

The premarket/after-close mutant exposed a second bug behind the first. `_reference_price`
compared the session index's **midnight** against the acceptance moment, so a filing accepted at
07:45 ET selected that same day's *unclosed* session as its reference. Keying the comparison to
the session's 16:00 ET close fixed it — and made the previously-passing
`test_filing_day_close_is_not_a_reference_price` wrong on its own premise, since an after-close
filing genuinely may use that day's close. That test was replaced rather than patched.

`DSC:A-DIGEST-OF-A-DERIVED-PROJECTION-IS-NOT-BYTE-BINDING` records the transferable half: no
single layer lied — the falsehood lived at the seam between "the bytes I hashed" and "the
document I claimed", which is precisely what per-layer review does not inspect.

## 8. Critical repair after the independent NOT PASS

The head that §7 describes, `a88c12f2`, was then reviewed independently and **failed**. The
reviewer reproduced Sol's seven blocking repairs and added four defects neither Sol's review nor
this lane had named — three of which reached `VERIFIED` on a wrong or unproven number. Sol folded
them into one addendum (carrier `1788441394.459699`) and required a single return covering the
complete set. This section is the record of that repair; §7 remains the record of the round
before it, and the sections are deliberately not merged, because the useful fact about this wave
is that a green suite, a passing exact-head review by the *author's* own lane, and a full CI pack
sweep all held simultaneously with three `VERIFIED`-reaching defects still live.

| # | Defect at `a88c12f2` | Repair |
|---|---|---|
| NEW-1 | `observation_id()` excluded `prior/supersedes_observation_id` and `correction_reason`, so `link_supersession()` recomputing the id returned the **same string** — a no-op. A hand-forged relation validated `True`, and `compile_current_terms` then admitted an entire multi-accession bucket whenever *any* `supersedes` matched *any* id in it | the correction relation moved **inside** the closed digest, so a changed relation cannot keep its identity; `validate_lineage()` additionally proves predecessor existence, same-field lineage, direction and acyclicity; and the compile now walks the connected lineage **out from the requested accession** instead of admitting the bucket |
| NEW-2 | `_price_inputs` graded Canada/intl/HK panels against `lib/nyse_calendar` and stamped `calendar_id=XNYS`. On 2026-07-03 NYSE was closed while HKEX traded, so a genuinely one-session-stale `.HK` column reported `sessions_behind=0` and reached `VERIFIED` | V1 admits only an exact resolved **U.S.** listing: `resolve_us_listing()` plus a closed `calendar_id`/`listing` check. No suffix-root fallback, no foreign panel, no syntax-derived currency |
| NEW-3 | the pure reducer never cross-validated its own receipt: `_has_calendar_receipt()` checked field *presence*, `sessions_behind` was taken from the caller, `session` was never compared to `expected_session`, any string passed as a `basis`, and `price_input()`'s own default was `close_raw` | `validate_price_receipt()` re-derives every recomputable field through the calendar owner and checks the rest against closed vocabularies; the reducer publishes **its own** recomputation, so a published freshness number cannot disagree with the calendar even when the producer is wrong |
| NEW-4 | `_fetch_filing_text()` returned the legacy `.txt` **before** `_retain_source()` ever ran, so every already-cached accession could never obtain a receipt; `enrich_deal_terms()` skipped it and the natural build passes `fetch_missing=False`. Coverage over the pre-existing corpus was structurally zero, permanently, with no backfill path | a legacy candidate cache with no verified receipt now goes back through the same fetch owner to reacquire the exact complete bytes; `--no-refresh` stays network- and source-inert |
| CONFIRMED | a rejected historical `$48.00` cash proposal under *Background of the Merger*, beside a current all-stock merger, published `VERIFIED` / offer 48.00 / spread +20% / consideration `cash` — the scope anchored on the first price candidate and cut *into* the background section | one deterministic current-transaction scope; background, prior-proposal, fairness-opinion, financing and employee-award spans cannot originate a current term. Out-of-scope prices are retained as `deferred`, not discarded (§2) |
| CONFIRMED | SEC acceptance timestamps hard-coded to `-04:00`, wrong for every winter filing | `ZoneInfo("America/New_York")`, byte-equivalent to the proven `sec_capital_structure` parser and pinned by a test that runs both over the same bytes |
| CONFIRMED | the ledger appended with `open(..., "a")` after silently skipping malformed lines; the JSON Schema accepted any `observation_id` of 8+ characters and required none of the source receipt | validate-the-whole-ledger-before-append, atomic publish + readback, `INTEGRITY_FAILED` / `PARTIAL_GENERATION` with a census; schema hardened to a closed 32-hex id and a conditional `allOf` that requires `raw_sha256`, `raw_bytes`, `acquired_at` and `completeness=complete` for any observed exact term |

### The mutation gate, and the one guard it caught

The suites passing is not the evidence — Sol required discriminating mutants, and the reason is
visible in the result. Ten mutants were applied one at a time to the repaired sources, each
re-introducing exactly one defect above, with the file restored from the index between runs:

| mutant | verdict |
|---|---|
| M1 correction lineage removed from the `observation_id` digest | killed |
| M2 caller's `sessions_behind` trusted again | killed |
| M3 `basis` vocabulary opened | killed |
| M4 receipt's declared `expected_session` no longer compared | **SURVIVED 197/197** |
| M5 non-US listing/calendar admitted | killed |
| M6 `rebind_observation()` neutered | killed |
| M7 SEC acceptance clock hard-coded to `-04:00` | killed |
| M8 legacy `.txt` returned before reacquisition | killed |
| M9 malformed ledger line silently skipped | killed |
| M10 schema `observation_id` loosened to `minLength: 8` | killed |

M4 is the finding. The `expected_session` comparison is *correct code*, shipped in the repair,
reviewed, and pinned by **nothing**: deleting it left every test green. The four sibling
freshness tests each move `session` or `sessions_behind` as well, so recomputed staleness
arithmetic reddens them first and the finer check never decides anything. The killing test has to
do the opposite of what feels thorough — hold `session` and `sessions_behind` genuinely honest for
`now_utc`, so the price really is current and nothing downstream disagrees, and corrupt only the
receipt's own claim about which session the market last completed. It matters because that field
is **published**: a `VERIFIED` row would have carried a calendar fact no calendar owner produced.
Closed by `test_a_false_expected_session_field_is_invalid_even_when_the_price_is_current`; the
matrix is then 10/10 at 198 passing. Recorded as
`DSC:A-GREEN-SUITE-CANNOT-TELL-YOU-WHICH-GUARDS-IT-PINS`.

### Regression evidence, controlled

The four owned suites are **198 passed**. For the rest, the sparse worktree makes a raw failure
count meaningless — unrelated suites need `data/` and `site/`, which are not checked out — so the
comparison is run as a true A/B on the *same* tree, same data, same sparseness: the 33 other test
files that reference these modules are run once against the repaired sources, then again with
`origin/main`'s versions of all six F09 paths swapped in and nothing else changed.

| side | result |
|---|---|
| repaired branch | 40 failed, 1547 passed, 19 skipped |
| `origin/main` F09 sources swapped in | 40 failed, 1547 passed, 19 skipped |

The failing sets are **identical, test for test**: 40 failures present on both sides, 0 present
only on the branch, 0 present only on main. Zero regressions attributable to this repair, and the
40 are pre-existing sparse-worktree artifacts in unrelated suites. Every F09 source file was
restored from the index afterwards and re-verified by blob digest.
