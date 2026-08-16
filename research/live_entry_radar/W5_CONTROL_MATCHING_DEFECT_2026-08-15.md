# W5 §7 control matching — two defects that emptied every control pool (2026-08-15)

**Status:** both fixed in this PR. **Scope:** `scripts/entry_radar_replay.py` only —
no file under `engine/entry_radar/replay/` is touched, so no frozen §7 primitive moves.
**Why this is not a performance PR:** it CHANGES results. It decides which control rows
the frozen matching law is shown.

## 1. What was wrong

### D1 — the session lookup keyed on a dtype the panel never has (total blackout)

`feature_panel._as_dates` returns `datetime.date`, `build_feature_rows` writes
`"session": session` from that loop, and `cross_sectionalize` preserves it — so the
feature panel's `session` column is **object dtype holding `datetime.date`**.
`_ctx_session_rows` looked it up with `panel["session"] == pd.Timestamp(session)`.

`date(2020, 2, 26) == pd.Timestamp("2020-02-26")` is **False** in Python: `Timestamp`
subclasses `datetime`, and `date.__eq__(datetime)` is False. So the mask was all-False
for **every** session, `_ctx_session_rows` raised `KeyError`, and `_attach_and_match`
caught it into `{"reason": "control_match_unavailable"}` with `matches.append(None)` —
which `_assemble_frame` reads as `uninformative_no_control=True, n_cell=0`.

Every episode. Every panel. Every run. The §7 control arm was structurally empty.

The reason this survived review is that it **failed into a refusal, not an exception**:
the output was a plausible-looking refusal census, not a stack trace. A 100 %
`control_match_unavailable` census and a genuinely control-poor universe are the same
artifact.

### D2 — session offsets were counted in decision slots, not trading sessions

`build_match_context` built `session_pos_by_date` from the panel's own rows:

```python
pos = {pd.Timestamp(s): i for i, s in enumerate(sorted(
    {pd.Timestamp(x) for x in features["session"].unique()}))}
```

The panel carries **only decision sessions** (`sessions = sorted({ep.decision_session
…})`), so those positions count slots between fires, not trading sessions.
`controls._session_offset` reads that map for the two frozen §7 exclusions — "did NOT
fire that detector within **±5 sessions** of D" and "does NOT fire it anywhere in
**(D, D+H]**" — and `assembly.q5_pairs` reads the same map for Q5's ±30-**session** gap.

Decision-slot distance is always ≤ trading-session distance, so both exclusions
**over-exclude** and every control pool silently shrinks. Measured in the mutation
control: two decision sessions 20 trading sessions apart produced the map
`{2017-02-27: 0, 2017-03-27: 1}` — offset **1**, inside ±5, so a lawful control was
dropped.

`feature_panel.attach_session_positions` takes a bench `calendar` argument for exactly
this reason, and `tests/test_entry_radar_w5_data.py` already asserted "a bench calendar
must override the panel's own". Production simply never passed one;
`panels.session_calendar` had **zero callers** in the replay stack.

## 2. Evidence

**Mechanism (D1), reproduced through the production builder** — pandas 3.0.3, at
`f76ec0b8` and again at `65f9669f`:

```
panel = feature_panel.cross_sectionalize(feature_panel.build_feature_rows(...))
panel["session"].dtype                                 -> object
type(panel["session"].iloc[0])                         -> datetime.date
(panel["session"] == pd.Timestamp(sessions[0])).sum()  -> 0
(panel["session"] == sessions[0]).sum()                -> 1
```

**Real-run receipt.** No `w5_results_panel_*.json` exists anywhere on the build host,
and a machine-wide search for `control_match_unavailable` returns nothing — the
definitive Panel-A/Panel-B confirmatory outputs do not exist. The only executed replay
is recorded in the TrialLedger: 82 `entry_radar` rows, 2026-08-15T09:01–09:33Z, one
`declared_budget` (n=253) plus **81 `source: w5_replay` looks, all carrying
`names_shard: ["NVDA","KO","JPM","MSFT","XOM"]`** — a 5-name smoke run (`--names` is
documented "sharding / smoke runs"). Its Panel-B census row reads:

```json
{"cell": "refusal_census", "panel": "B", "n_refusals": 543, "n_episodes": 502}
```

**Refusals exceed episodes.** That is D1's signature and not the signature of a
control-poor universe: an empty CEM cell does not refuse — it returns a `ControlMatch`
with `uninformative_no_control=True`. A refusal can only come from `_ctx_session_rows`
raising (or the vendor plane failing). The 5 smoke names span 5 sectors, so their cells
would have been empty anyway; that confound is why the census is corroboration and the
deterministic reproduction above is the proof. D1 is input-independent — the mask is
all-False for every session on every universe — so no artifact is needed to establish
that the full run would have behaved identically.

**Impact, stated exactly.** No published W5 confirmatory read is corrupted, because
none was ever produced (the pre-merge review receipt records "Results seen: NONE", and
PR-5b landed the machinery only at 2026-08-15T11:39Z). What did happen: the 81 smoke
looks — including `q1_primary`, `nc2_q1`, `q5_primary`, `q5_guardrail_falsestart` — were
spent against a dead control path. The §13 budget is not damaged: shard-restricted
looks ride `names_shard` in the config, so a full-panel run spends its own cells and a
true re-run of the same universe dedups.

## 3. The fix, and why this shape

The choice was "make the panel `datetime64` throughout" vs "key the lookup on `date`".
**The column is canonically `datetime.date`**, so the lookup was the defect:

* `controls.ControlMatch.session` is annotated `date`, and is populated straight from
  `candidate_row["session"]` — a datetime64 column would change the §7 result object's
  own type and its serialized shape.
* `controls.eligible_pool(candidate_session: date)` and `_session_offset(other: date,
  base: date)` are `date` throughout.
* `attach_session_positions` is the ONE declared place where `date → Timestamp`
  happens; it is documented as returning `dict[pd.Timestamp, int]`.
* The other two consumers already convert defensively (`assembly.q5_pairs` via
  `pd.Timestamp(r["session"])`, `ruler._month_key` via `pd.to_datetime`), so neither
  was affected by D1 and neither constrains the choice.

So: `_session_key` pins the canonical spelling; `build_match_context` normalizes the
column once at the seam where the panel is born; `_ctx_session_rows` keys on `date` and
looks up the datetime64 spelling explicitly rather than assuming (the cost of guessing
wrong here is silence). D2 is fixed by passing `panels.session_calendar(spy)` — the bench
calendar the docstring already demanded. Both `controls._session_offset` and
`assembly.q5_pairs` read the same corrected map.

### Rebased onto #5775

This PR now sits on top of the merged 58x perf refactor, and keeps both properties. The
lookup stays #5775's `groupby.indices` + `take` (no return to the whole-panel boolean
scan) and is simply keyed correctly; the position map stays wrapped in
`panels.SessionPositions` so it is shared rather than deep-copied through `attrs` — which
matters *more* here, not less, because the bench calendar makes the map larger than the
panel-derived one it replaces.

#5775's `test_ctx_session_rows_equals_the_boolean_mask_it_replaced` asserted the index
agreed with the mask on both shapes — which on the object/date shape meant agreeing on
finding nothing. Its own closing comment instructed the revision: *"if a later change
makes the object/date lookup start matching, this test must be revisited together with
the control-matching refusal census it would change."* It is now
`test_ctx_session_rows_returns_every_row_of_the_session`: the datetime64 leg still pins
the row-for-row identity that licensed the refactor (including shared `attrs`), the
object/date leg pins the fixed behaviour, and a mutation control keeps the legacy mask's
failure on that shape on the record.

**No frozen law changed.** §7's text is unmodified; this repairs the code's ability to
apply it. Both repairs move strictly toward the frozen law — D1 from "no controls" to
"the controls §7 specifies", D2 from over-exclusion to the specified window.

### Guard against recurrence

A panel that resolves **zero** decision sessions now raises `ReplayRefusal` instead of
emitting a 100 % refusal census, and a partial resolution prints a `::warning` with the
`resolvable/total` count. The original defect's entire cost was that it stayed inside
the per-episode refusal path; a structural impossibility must not be reportable as data.

## 4. What still must be done (not in this PR)

1. **Run the definitive Panel-A and Panel-B replays.** They have never been run; there
   is nothing to re-run, only to run. Every §7-matched read (Q1 primary, NC-2 Q1
   proximity shadow, Q5 primary and its guardrail, the cohort/regime cells) is
   unproduced until then.
2. **Treat the 09:19–09:33Z smoke looks as void for interpretation.** They are
   append-only ledger facts and must stay; they are not evidence about controls.
3. **Re-check the §9 overlap diagnostic** once real pools exist — its 0.50 floor
   measures proximity common support, and it has never seen a non-empty pool.

## 5. Verification

| claim | command | result |
|---|---|---|
| D1 reproduces through the production builder | the snippet in §2 | `object` / `datetime.date` / `0` / `1` |
| new tests pass | `pytest tests/test_entry_radar_w5_data.py -k "session_key or ctx_session_rows or match_context"` | 6 passed |
| D1 mutation control (post-rebase) | restore `by_session.get(pd.Timestamp(session))` | 3 failed, incl. the revised #5775 leg |
| D2 mutation control (post-rebase) | restore `attach_session_positions(features)` | 1 failed, `assert 2 == 400` |
| no regression in the radar suite | `pytest tests/test_entry_radar_*.py` | 1394 passed, 2 skipped |

Both mutation controls were re-run against the rebased implementation rather than
carried over — the lookup changed shape on the rebase, so the pre-rebase proofs no
longer covered it.
