# R3B1-14 — mutation suite results

Candidate: `proposal/MASTERMIND_SECTOR_CENTRAL_R3_CANDIDATE.html`. Every mutation below is applied to an in-memory COPY of the built candidate inside a throwaway temp directory; the real proposal file is never touched.

**Pristine baseline green:** YES

## Per-mutation results

| capability | got a red | failing checks |
|---|---|---|
| `sizing_directive` | yes | D1 [sizing_directive] sizing_pct |
| `method_caveat_clause_a` | yes | D1 [method_caveat_clause_a] caveat_not_forecast |
| `method_caveat_clause_b` | yes | D1 [method_caveat_clause_b] caveat_construction_lag |
| `migration_note` | yes | D1 [migration_note] migration_note |
| `allocation_destination` | yes | D1 [allocation_destination] allocation_href<br>D1 [allocation_destination] allocation_text<br>D2 [destination_family] allocation_family has >=1 real href |
| `hero_enrichment_outgoing` | yes | D1 [hero_enrichment_outgoing] hero_enrichment_outgoing |
| `hero_enrichment_incoming` | yes | D1 [hero_enrichment_incoming] hero_enrichment_incoming |
| `hero_enrichment_counts` | yes | D1 [hero_enrichment_counts] hero_counts_categories<br>D1 [hero_enrichment_counts] hero_counts_themes |
| `sp_coverage_sentence` | yes | D1 [sp_coverage_sentence] sp_coverage_gateable<br>D1 [sp_coverage_sentence] sp_coverage_phrase<br>D1 [sp_coverage_sentence] sp_coverage_thin<br>D1 [sp_coverage_sentence] sp_coverage_total |
| `conviction_picks_label` | yes | D1 [conviction_picks_label] conviction_label |
| `destination_family_basket` | yes | D2 [destination_family] basket_family has >=1 real href<br>D2 [destination_family] every data-ref-nav href matches an allowed family |

## Pairwise distinctness

All mutations produced pairwise-distinct failing-check sets — no two capabilities collapse to the same red.

## Method

Each mutation targets the exact JS source construct Lane A/B restored for that capability (a return-early guard, a ternary condition forced false, or a literal string fragment blanked) — the built candidate embeds the view partials' JS source verbatim, so the mutation operates on the same bytes the browser executes, not on the fixture or the producer contract. `destination_family_basket` instead does a global byte substitution of the literal `basket/` prefix, proving direction 2 (candidate -> allowed) catches a stripped destination family, not only direction 1's hero-copy pins.
