# Incremental IC — how much of our selection edge is real (vs repackaged factors)

_Generated 2026-06-21T10:36:21+00:00_ · universe 110 survivor mega-caps · neutralized against market_beta, size(log $vol), mom_12_1, low_vol

> Even the incremental IC is an **optimistic survivor bound**; the signal is the **relative collapse** raw→incremental. Multiple-testing N logged to `data/trial_ledger.jsonl`; incremental p-values BH-FDR'd.


| signal | h | raw IC | raw t(HAC) | incremental IC | incr t(HAC) | survives | FDR reject |
|---|--:|--:|--:|--:|--:|--:|:--:|
| mom_12_1 | 21 | 0.0345 | 3.809 | 0.0259 | 3.3 | 0.751 | ✓ |
| mom_12_1 | 63 | 0.042 | 2.962 | 0.0325 | 2.743 | 0.774 | ✓ |
| near_52w_high | 21 | -0.0155 | -1.879 | -0.0352 | -5.288 | 2.271 | ✓ |
| near_52w_high | 63 | -0.0123 | -0.989 | -0.0297 | -3.271 | 2.415 | ✓ |
| fip_continuity | 21 | 0.0103 | 1.382 | -0.0025 | -0.396 | -0.243 | · |
| fip_continuity | 63 | 0.0175 | 1.646 | -0.005 | -0.592 | -0.286 | · |

**Read:** a signal whose incremental IC collapses toward 0 (low `survives`, no FDR-✓) carries little information beyond the style factors we already own — its raw IC was mostly repackaged beta/size/momentum/low-vol. That de-biasing is the institutional point: rank on what *survives*, not raw IC.

