# D2 — Defense Identity Atlas pilot

**Wave:** D2  
**Depends on:** D1 merged and proven live.  
**Status:** written, unauthorized until D1 returns.  
**Graph law:** consume whichever **reviewed** recipient graph is on `origin/main` when D2 starts. Today that is `defense19-v1` digest `0733a966…`. `#5424` (`defense20-v1`) must not be treated as live and must not be merged from this wave.

## Observable mission

A user opens **five** golden issuers and sees reviewed point-in-time legal-entity, identifier, ownership, and public-security paths. Ambiguous joins stay in mapping backlog and **cannot** create ticker evidence. GE and BWXT remain `mapping_needed` until a reviewed UEI→legal→`central:*` path exists.

## Why it matters

Filmstrip extras and mapping-backlog 21 already show names that are not issuer proof (`DSC` Radar lock aside). D2 is the identity vertical, not a BOM graph and not a second Stock Identity.

## Authority precedence

Identity owner = Stock Identity (`central:TICKER`). Recipient graph owner = reviewed GovRev graph. D2 may add reviewed edges under the existing contract (`government_recipient_resolution.v1`). Display/context_only. No rank/gate/size.

## Verified current state

- IRDM path proven (L1).
- HII path proven on some events; deobligation on N0002415C2114 has **empty** `listed_company_impacts` (L2) — Atlas must not invent a ticker on that row.
- GE, BWXT: `mapping_needed` / `exact_identifier_mapping_required` (L5).
- SPR: **not** in SI universe; Boeing close 2025-12-08 (G1b). Historical only.
- CACI, SAIC: not in SI snapshot — resolve listing before any candidate.
- International names: not on US SI plane.

## Pilot cases (frozen)

| # | Issuer | Job | Adversarial |
|---|---|---|---|
| 1 | **IRDM** | Strong path; keep partial_identifier_coverage from minting extra names | Late discovery clocks |
| 2 | **HII** | Ship identity; attach ticker only where reviewed | Deobligation sibling without impacts |
| 3 | **LMT** | Mega prime; many UEIs | Do not collapse JVs |
| 4 | **GE** | `mapping_needed` today | GE vs GEV listing; do not use filmstrip |
| 5 | **BWXT** | `mapping_needed` today | Nuclear supplier vs prime |

Do not swap these five to make the wave pass.

## Exact contracts / files

- `engine/government_revenue/` recipient graph proposal + review (existing `propose_government_revenue_recipient_graph` tests)
- Stock Identity read-only: `data/stock_identity/partition/universe_snapshot_v1.parquet` (after sparse `add data` or `git show`)
- Mapping backlog projector: `scripts/build_government_revenue_candidates.py`
- Product: company filmstrip + dossier identity panel on `government_revenue.html.j2` / `government-revenue-dossiers.js`
- Reviewer UX: existing graph review receipts, not a new admin app if one already exists

## Explicit non-goals

- No Govini/Janes BOM.
- No SPR live ticker.
- No defense ticker table.
- No Prophet members.
- No “fix all 21 backlog rows” unless they fall out of the five pilots.

## User journey

1. Open IRDM dossier: legal path + SI live flags + last reviewed award.
2. Open HII: see which events are ticker-linked vs impacts-empty.
3. Open LMT: multiple UEIs listed, not flattened.
4. Open GE: **mapping queue**, not a fake candidate.
5. Open BWXT: same.
6. Mapping backlog still says `issuer_attribution: not_asserted` for unresolved names.

## Data / time / correction

Ownership edges need `valid_from`/`valid_to`. GE split and SPR close are PIT tests. Corrections invalidate with predecessor graph id (`DNR:LAW-REVIEWED-MANIFEST-CENSUS` — a reviewed graph cannot re-time itself).

## Failure states

`identity unresolved`, `conflicting graph`, `listing terminated` (SPR), `not in SI universe` (CACI/SAIC/internationals). Print them.

## Ordered steps

1. Re-read live graph id on main (do not assume defense19).
2. SI lookup for the five + SPR negative control.
3. Close GE/BWXT only with primary 10-K/Ex.21 + UEI receipts, or leave `mapping_needed`.
4. Product: filmstrip uses mapping/coverage/candidate states from D1 hydrate, never Members only.
5. Tests: IRDM still reviewed; GE cannot emit `grc1-*` without a reviewed path; SPR cannot enter the live golden filmstrip.

## Tests and production proof

- Existing graph tests plus five-issuer fixtures.
- Entitled browser: five dossiers match the graph, GE/BWXT show Link pending.

## Rollback

Revert graph proposal PR; keep defenseN-v1 that was live. No silent graph id bump.

## Stop condition

Five-issuer pilot proven. Do not expand to the full 31. Return, then D3.

## Continuation

Handoff must name the graph id D2 shipped and the remaining mapping_needed tickers.
