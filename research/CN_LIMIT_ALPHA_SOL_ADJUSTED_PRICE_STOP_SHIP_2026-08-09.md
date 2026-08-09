# CN limit-alpha adjusted-price STOP-SHIP — 2026-08-09

Status: **superseded; STOP-SHIP**

Authority: `none_research_display_only`

## Disposition

The original Wave-1 implementation and its generated evidence are withdrawn. This
branch no longer carries the adjusted-price event tape, reconstructed limit bands,
completeness manifest, onset/continuation measurements, forward seed or ledger, or
the code and tests that could reproduce or promote them. Nothing from that result
may rank, gate, size, alert, trade, or establish numerical strategy authority.

The withdrawn 71,692-event tape could not support an exact historical legal-limit
claim. Yahoo history requested with `auto_adjust=False` remains split-adjusted
(`collectors/_stock_ohlc.py` documents the resulting rebase seam), so historical
nominal CNY prices and exchange limits cannot be reconstructed exactly from it.
The implementation also used Python/NumPy ties-to-even rounding instead of the
exchange half-up rule. Correcting rounding alone cannot repair an adjusted input
plane.

## Replacement boundary

The merged construction packet in
`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` is the governing
replacement path. Its foundation remains `context_only` and requires the separate
authorization and completeness gates written there. The reconciliation ledger from
the follow-on CN governance wave must preserve this invalidation rather than merge
the withdrawn results into the new plane.

Exact-limit research may be rerun only after all of the following exist together:

- authorized, unadjusted TuShare `daily` prices;
- vendor `stk_limit` upper/lower limits as the event authority;
- integer-cent equality and exchange-compatible half-up validation;
- point-in-time full-universe and effective-date completeness receipts; and
- a fresh, provenance-bound measurement built solely from that substrate.

Until then, the prior construction and ORE ideas are context for future research
only. They are not evidence that an implementable edge exists.
