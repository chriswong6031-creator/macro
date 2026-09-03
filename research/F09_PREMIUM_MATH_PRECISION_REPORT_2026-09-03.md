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

19-case corpus, `tests/fixtures/special_situations/f09/corpus.json`, run through the real
extractor and current-term compiler:

| verdict | n |
|---|---|
| correct publication (price matched the expected value exactly) | 8 |
| **correct decline** (no price published where none may be) | 8 |
| recall miss (should have published, declined) | 0 |
| **FALSE PUBLICATION** | **0** |

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
