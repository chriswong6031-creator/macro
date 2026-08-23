# R3B.2 closure mutation results

Every mutation was applied to a throwaway copy of the assembled candidate; the real proposal file was never modified.

**Pristine figure guard green:** YES

**Pristine closure guard green:** YES

**Pairwise-distinct reds:** YES

| mutation | guard | got red | failing check ids |
|---|---|---:|---|
| `b2_05_strength` | fig | yes | `b2_05.strength.census`<br>`b2_05.strength.label`<br>`b2_05.strength.proof` |
| `b2_05_delta` | fig | yes | `b2_05.delta.census`<br>`b2_05.delta.label`<br>`b2_05.delta.proof` |
| `b2_05_entry` | fig | yes | `b2_05.entry.census`<br>`b2_05.entry.label`<br>`b2_05.entry.proof` |
| `b2_05_conviction` | fig | yes | `b2_05.conviction.census`<br>`b2_05.conviction.label`<br>`b2_05.conviction.proof` |
| `b2_01_strength_term` | closure | yes | `b2_01.one_path_one_term`<br>`b2_01.overview_header` |
| `b2_12_authority_term` | closure | yes | `b2_12.distinct_authority_terms`<br>`b2_12.low_confidence_term` |
| `b2_13_shared_receipt` | closure | yes | `b2_13.exact_shared_control_census`<br>`b2_13.overview_control` |
| `b2_15_context_scope` | closure | yes | `b2_15.localized_clauses`<br>`b2_15.qualification_present`<br>`b2_15.visual_separation` |

## Distinctness

All eight independently removed semantics produced non-empty, pairwise-distinct failing-check sets.

The four B2-05 mutations cover the two independently named Overview measurements and the Entry tier and Conviction figure classes. The remaining mutations cover the one-path/one-term law, the distinct authority terms, the shared receipt target, and the producer-derived context qualification.
