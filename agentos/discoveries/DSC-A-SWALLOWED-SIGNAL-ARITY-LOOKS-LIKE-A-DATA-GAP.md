---
key: A-SWALLOWED-SIGNAL-ARITY-LOOKS-LIKE-A-DATA-GAP
claim: >
  `research/signal_engine/walk_forward.py` wraps its whole per-ticker body in
  `except Exception as e: dropped[t] = f"ERROR: ..."`, so a signal callable that violates
  the harness's calling contract fails IDENTICALLY to a name with no usable price history:
  both leave `by_ticker` empty and report `n_names: 0`. `scripts/evaluate_cortex_hypotheses.py`
  defined `signal_fn(close, **_kwargs)` while the harness calls `signal_fn(daily, high, low)`
  positionally, so every ticker died on `TypeError: signal_fn() takes 1 positional argument
  but 3 were given` and Path B produced `wf_n_names: 0` for its entire life. The 2026-08-26
  experiments audit read that zero as a price-panel join failure ("data/yahoo lacks the
  symbols or the spine symbol column is empty"); BOTH hypotheses are false — the spine
  symbol column is 100% populated across 5,017 distinct symbols, data/yahoo carries 5,219
  parquets, and `_load_price_panel` admitted 52 of 60 requested names on the first try.
  Fixing only the arity is still not enough: the closure resolved its ticker as
  `close.name`, but the harness passes `df["close"]`, whose `.name` is the literal string
  `"close"`, so every per-ticker lookup missed and no signal would have fired anyway.
  A third defect sat behind those two — the result was read as
  `wf_result["pooled"]["stop_out_rate"]`, a key that exists at no nesting level
  (`pooled[view]` is a percentile distribution), and the harness reports stop_out_rate in
  PERCENT (46.67), not as a fraction.
falsifier: >
  `python3 -m pytest tests/test_cortex_evaluator_repairs.py::TestW5PathB` passing against a
  `signal_fn` restored to a single positional parameter, or any `walk_forward` run whose
  `dropped` values contain `TypeError` while `n_names` is reported without comment.
so_what: >
  `n_names: 0` from walk_forward is NOT evidence about data coverage — always read
  `wf_result["dropped"]` before concluding anything about the panel, because a contract
  violation and a data gap are the same observation there. More generally: when a harness
  swallows per-item exceptions into a diagnostic dict, the dict is the instrument, and a
  caller that reports only the aggregate has no way to tell "nothing qualified" from "I
  called it wrong". Any consumer of walk_forward must (a) match `fn(close, high=None,
  low=None)` exactly, (b) carry ticker identity on `index.name` — `Series.name` is taken by
  the column label — and (c) read the metric from `by_ticker`, trade-weighted, and divide
  by 100.
kind: landmine
verified_at: 2026-08-26
verified_by: >
  direct reproduction against unmodified scripts/evaluate_cortex_hypotheses.py
  (`dropped == {'AAPL': 'ERROR: TypeError: signal_fn() takes 1 positional argument but 3
  were given'}`); post-repair H4 run wf_n_names 0 -> 52, 19,447 signals bound, pooled
  stop-out 0.8246 over 57 trades; governance.jsonl article3_review events 2026-08-04 (H1,
  n=25,824) and 2026-08-10 (H4, n=33,930), both `wf_n_names: 0` with no `wf_error`
scope:
  - mastermindx-market-intelligence/macro
  - scripts/evaluate_cortex_hypotheses.py
  - research/signal_engine/walk_forward.py
confidence: verified
---

The audit's diagnosis was reasonable and wrong in an instructive way. `wf_n_names: 0`
alongside an ample post-registration `n` genuinely does look like a join that matched
nothing, and the evaluator's own code reinforces the reading — it checks `if not panel:`
and reports "no price panel available", so a reader naturally infers that a run which got
PAST that check and still returned zero names must have had a panel full of unusable
data. In fact the panel was fine; the harness rejected the caller.

What made this invisible for two months is that the failing detail was recorded in a field
nobody read. `walk_forward` does print dropped-on-ERROR names to stderr, but the evaluator
runs inside a nightly step that redirects into a log and only surfaces a `::warning` on a
non-zero return code — and the whole module is deliberately degrade-never-raise, so the rc
was always 0. Three independent layers of "keep the nightly alive" combined into "the
verdict is wrong and nothing says so."

The general lesson is about where a contract lives. The harness header states
`fn(close, high=None, low=None)` in prose; nothing enforced it, and a `**kwargs` signature
looks maximally permissive at the call site while being strictly narrower than the actual
contract. `**kwargs` absorbs unexpected KEYWORD arguments and rejects extra POSITIONAL
ones, which is exactly backwards for a harness that passes positionally.
