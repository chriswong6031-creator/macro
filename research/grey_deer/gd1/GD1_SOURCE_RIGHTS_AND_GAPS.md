# GD-1 source rights and gaps

**Prereg:** `663fb02b500c` · **Replay HEAD at writing:** see `GD1_REPRO_MANIFEST.json`
**Law:** a source with unknown `available_at` may not support an anticipatory claim.

## Rights that are sufficient for this dossier

| Source | Rights basis | Lawful use here |
|---|---|---|
| TreasuryDirect auction results | Public official results | EOD descriptive; enter no earlier than auction-day close |
| PBOC OMO HTML bulletins | Public pbc.gov.cn; store carries `first_seen` | First-seen classification of tool/tenor/amount |
| Yahoo EOD bars (US ETFs, KOSPI via `_KS11`) | Vendor EOD already in repo | Descriptive close-to-close; not intraday |
| Prophet candidate parquets | Internal intelligence already committed | Sidecar only; do not rebuild boards |
| Leadership Crack / Market State / Risk Radar forward logs | Internal emission logs | Observation-at-`asof`; not intra-session |

## Gaps that block a claim (do not guess)

1. **When-issued auction tail.** `engine/treasury_supply.py` states the true tail is omitted because WI quotes are not in the free store. Search of this checkout found no WI series. **GD-H3 tail leg = UNAVAILABLE.** Proxy `auction_concession_proxy_v1` (TLT t−3..t0) is a different construction and is not renamed tail.
2. **SK Hynix issuer tape (`000660.KS`).** No parquet in `data/yahoo/` or Korea stores. Issuer-only repair path cannot be priced. **GD-H7 issuer leg = BLOCKED** on prices; secondary press may label the impulse only.
3. **Official SK Hynix filing clock.** 2026-08-19 BOD buyback is known here from BusinessKorea 16:59 KST, not from DART/KIND in-repo. **CLOCK_PARTIAL.** Do not treat article time as the event if a filing timestamp later appears.
4. **Intraday Prophet quotes.** Not retained. Screenshots are not a quantitative dataset. **GD-H5 intraday = UNAVAILABLE.**
5. **China Prophet 2026-08-17 board.** Absent from `candidates.parquet`. Cannot compute a 08-17→08-18 board-health delta from emissions.
6. **China Prophet session returns.** No session-return column. Featured/more_actionable counts exist; median session return does not.
7. **Leadership Crack emission history.** Forward log begins 2026-07-17 already `BROKEN` (n=15). **GD-H1/H2 historical predictive tests from the emission log = UNDERPOWERED.** A truncate-and-recompute of the current definition is a separate counterfactual, not done in this wave.
8. **Anticipation and Velocity artifacts.** No `data/anticipation` or `data/velocity` stores. Those organs are **BLOCKED** for replay.
9. **CN Risk Radar August emissions.** Last row 2026-07-16. August CN radar **STALE / missing**.
10. **FRED DGS*/VIXCLS.** Latest-revised daily files, no `published_at`. Descriptive only in this dossier. Scored historical frames that used them as first-available would leak (TDS §0).
11. **MOVE / VVIX / short-dated VIX.** Not in `data/fred/`. Rate-vol confirmation for GD-H3 used 30y yield change, not MOVE.
12. **Mastermind Portfolio shadow.** Filename walk of `Mastermind/portfolio` found no `derisk` / `macro_risk` / `market_view` / `posture` artifacts. **NOT_LOCATED.**
13. **Yahoo coverage of Prophet buyable names.** Only 39 of 241 Aug-17 buyable names had a 08-17 and 08-18 close in `data/yahoo/`. Sidecar utility is **coverage-blocked** for the full board.
14. **Grey Deer architecture freeze (Sol).** Absent on `origin/main` and from GitHub PR/issue/code search on 2026-08-19. Hypotheses frozen from the Fable packet, not from a Sol freeze document.
15. **KOSPI 2026-08-19 bar.** Volume ~half of recent sessions. May be incomplete. Do not treat as a settled terminal close until the vendor bar is final.

## Minimum lawful substitutes

| Blocked thing | Substitute | What it may support |
|---|---|---|
| WI tail | `auction_concession_proxy_v1` (named separately) | Descriptive GD-H3 proxy only |
| 000660.KS | KOSPI `_KS11` + EWY (US-hours proxy) | Regional, not issuer |
| Official buyback filing | Secondary press receipt | Impulse timestamp with CLOCK_PARTIAL |
| Intraday board quotes | EOD candidate parquet | EOD lane/disposition only |
| LC prehistory | Truncate-recompute at current SHA (not done) | Counterfactual, labeled `def_current_cf` |
| Anticipation/Velocity | Omit from timeline | Do not invent states |
| MOVE | DGS30 1d/3d change | Yield confirmation, not rate-vol |
| Full-board sidecar | Priced subset n=39 | Illustration; not a policy number |

## Rights that do **not** authorize live action

Nothing in this file, and nothing in GD-1, grants Prophet, Portfolio, or on-page alert authority.
