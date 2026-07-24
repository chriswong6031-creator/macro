# Prophet × Top-setups presentation merge — masterplan

Status: CHARTERED 2026-07-24 (operator: "tickers overlap on the two boards … weird to
have two boards cuz it will just confuse users"). One-PR scope, display-tier only.

Operator question was "should we just merge Top Setups' posts into Prophet?" —
adjudicated as a **presentation merge, not a data merge** (see §2 for why the data
merge is forbidden).

## §0 ACCEPTANCE GATES — not done unless

1. **One board to the user's eye.** On us_stocks.html, a Prophet card whose entry
   trigger has fired carries a visible ⚡ chip; the sub-board below lists ONLY names
   that are not carded above. No ticker appears twice at rest. (Measured baseline
   2026-07-24: 9 of 10 visible Top-setups rows duplicated Prophet cards.)
2. **Ledger untouched.** `site/factordata/us_standouts.json` and
   `site/factordata/setups.json` byte-identical in behavior — no engine, builder, or
   payload change. `grade_us_board.py` population, `us_board_ledger`, the track-record
   dialog, and the landing Prophet showcase are unaffected. Template-only diff
   (+ tests + this doc).
3. **Both empty states honest and distinct.** (a) triggers exist but all are carded
   above → "already on the board above — look for ⚡"; (b) no triggers at all →
   existing "no fresh buy triggers today" copy. Neither state renders an empty table.
4. **Doctrine-compliant copy.** Tier-1 budgets hold (title ≤ 4 words, subtitle ≤ 14);
   no MACD/StochRSI/confluence vocabulary at rest — mechanics live in data-tips and
   the `?` help. No `t()` in attributes; no translated `title=`; the word
   "validated" does not enter user-facing text in this PR.
5. **Fail-soft proven by tests.** `top_setups` absent/None → cards render with no
   chips, sub-board absent (current behavior); `us_standouts` absent → sub-board
   shows unfiltered trigger rows. Render suite green both modes.
6. **Visual artifact in the PR body.** Production-data render crops: panel with
   chips (light + dark + zh) and the filtered sub-board, plus the all-overlap empty
   state if reproducible from live data. First-pass flagship UI → **no self-merge**;
   PR waits for operator review.

## §1 The two boards (as-built, 2026-07-24)

Both are emitted by the same `scripts/build_stock_library.py` run, from the same
candidate pool, ranked by the same α leg; rows share one schema (incl. the
`signal` dict with `tier_cascade` T1/T2/T3 + `provisional`).

| | Prophet Stock Signals | Top setups |
|---|---|---|
| Payload | `us_standouts.json` (~41 buy cards) | `setups.json` (12 buy rows today) |
| Question | worth owning? (+ entry read) | which entry triggers just fired? |
| Gate | decisive cycle signal | HARD `signal_gate.is_buyable` (T1/T2 fresh cross, T3 imminent) |
| Graded | YES — `us_board_ledger` → track record + landing showcase | no |
| Governance | species registry binds | article2 surface (synapse.yml; factor-boundary + research-factory-authority checkers) |

Overlap is structural, not a bug: a conviction name whose trigger fires appears in
both. The defect is presentation — two side-by-side "picks lists" with ~90% ticker
duplication and no visible relationship.

## §2 Why the data merge is FORBIDDEN (adjudication record)

1. **Ledger contamination.** `grade_us_board.py` grades Prophet-board membership
   (git archaeology + snapshots). Changing the population changes what the published
   win rate means, silently — poisoning the track-record dialog, the landing
   showcase (#3365/#3391), and species-registry accrual.
2. **Killed construction.** Phase-0 (`reports/setup-score-phase0.md`) found blending
   timing into the α rank dilutes forward returns; a single merged ranking
   re-introduces it. Related DNR row: Stage-2 as win-rate gate on the timing entry.
3. **Governed surface.** `top_setups` is a named article2 surface with CI authority
   checkers; `signal_gate.json` from the same lane feeds discovery Top Picks.
4. **Empty-state honesty.** "No fresh triggers today" is a real, informative state
   the merged board could not express.

Any future proposal to merge the *data* lanes must re-open this section.

## §3 Build spec (template-only)

### 3a. ⚡ trigger chip on Prophet cards

- `templates/_prophet_card.html.j2`: new OPTIONAL `cx.trigger` slot
  (`{kind: 'fired'|'imminent', tip_en, tip_zh}`), rendered in the top-left overlay
  after the verb chip, before ⚠N. Absent → nothing (CN/HK/CA/INTL callers
  unchanged). Chip inherits the card hue `--pvh` (one-hue law); `imminent` renders
  with a dashed border (pending semantics). Same 10px/800 pill type as the verb chip.
- `templates/dashboard.html.j2` US caller: membership = ticker ∈ `top_setups.buy`
  (the artifact IS the gate — never re-derive freshness from row `signal`, that
  drifts). kind: `tier_cascade` T1/T2 → fired, T3 → imminent. Chip text:
  "⚡ Triggered" / "⚡ 已触发"; "⚡ Imminent" / "⚡ 即将触发" ("Near" avoided — collides
  with the Near verb). Tier-2 tip carries mechanics + the provisional caveat in
  plain words ("about 1 in 10 of these vanish when the bar completes") when
  `signal.provisional`.
- Verb still rules the card: a Wait card with ⚡ means "trigger fired but price is
  extended — don't chase"; the chip tip says so explicitly. This resolves today's
  live contradiction where Prophet says Wait while Top setups lists the same name
  as a buy row with no extension caveat.

### 3b. Sub-board: residual triggers only

- Filter `top_setups.buy` by `ticker not in` the carded set (from `_su.buy`) —
  BEFORE the display cap, so residual names below rank 10 still surface
  (today: VZ + 1 other, previously invisible behind 10 duplicated rows).
- Retitle: "⚡ More fresh triggers" / "⚡ 更多新触发"; subtitle "Buy triggers fired
  elsewhere in the S&P 1500 — names not already carded above." + bridge count
  ("N of today's M triggers are cards above — marked ⚡") when overlap > 0.
- Table columns/rows unchanged. `?` help updated to describe the split. Discovery
  "Top Picks →" link stays.
- Empty states per §0.3.

### 3c. Tests

Extend `tests/test_dashboard_template_render.py` (env mirrors build_site exactly):
chip presence/absence, filter behavior, both empty states, fail-soft on absent
payloads, both modes render.

## §4 Out of scope / follow-ups

- Table-view (`USStockTable`) trigger column — the JSON data element doesn't carry
  the tier today; the bridge line keeps the relationship legible in table view.
  Follow-up if operator wants parity.
- CN/HK/CA boards have their own standout/setups pairs — port the same idiom only
  after US ships and is reviewed.
- Any promotion of the trigger to rank/gate/size on the Prophet board = gauntlet
  territory, separate charter.
