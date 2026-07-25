# Transmission chain schema (TXI-R1)

A *chain* is a versioned, human-auditable description of one macro→micro cascade:
an ordered list of observable **nodes**, the directed **hops** between them (with
sign, lag window, regime condition, mechanism prose, and a strength prior), the
**falsifiers** that kill it, the naive **null model** it must beat, the per-name
**exposure screens** that resolve its blast radius (W2 — declared here, not resolved
in W1), and its **provenance** + **rev** + **tier**.

Chains live in `knowledge/transmission/*.yaml`, one file per chain, PR-reviewed. The
compiler (`engine/transmission_chains.py`) turns each chain into a deterministic
episode tracker; it never scores, ranks, sizes, or escalates anything (masterplan §4).
Killed chains move to `knowledge/transmission/killed/` (TXI-R10).

**The hard law (TXI-R1 validator):** every `node.src`/`node.test` must resolve to a
*real, collected* artifact/field through a named source adapter in the engine. A node
whose adapter is missing is `unresolvable` and its chain **cannot arm** — the validator
surfaces it, the compiler skips it. Never fake a detector to make a chain green.

---

## Top-level fields

| field | type | meaning |
|---|---|---|
| `chain` | str (slug) | stable id; MUST equal the filename stem. Never renamed (edits bump `rev`). |
| `rev` | int | revision; bump on any edit, with a `changelog` line. |
| `tier` | enum | `hypothesis` \| `probe` \| `calibrated`. See **Tier** below. In W1 every seed is `hypothesis` (base rates untested until W3). |
| `title` | `{en, zh}` | short bilingual chain title. |
| `nodes` | map | `id -> {src, field/test, ...}`; the observable states. See **Nodes**. |
| `hops` | list | directed edges between node ids. See **Hops**. |
| `falsifiers` | list[str] | plain-word conditions that KILL an armed episode → `failed`. Each maps to a compiled check (see **Falsifiers**). |
| `null_model` | str | the naive baseline the chain must beat at promotion (W3); prose in W1. |
| `exposure_screens` | map | `flag_name -> {field_expr, note}`; per-name blast screens. **DECLARED but NOT resolved in W1** (W2 resolves them). |
| `provenance` | map | `{theory:[...], episodes:[...], added_by, added_on}`. |
| `changelog` | list[str] | one line per rev (optional at rev 0). |
| `validator_note` | str | (optional) honest note on any weakened/proxy binding or missing observable. |

## Tier

- **`hypothesis`** — every node resolves and the chain arms, but its per-hop conditional
  base rates are UNTESTED (no episode miner / forward ledger yet). Prints "untested".
  This is the honest W1 tier for all four seeds (masterplan §6). **Also** the forced tier
  for any chain that has an `unresolvable` node — such a chain never arms at all.
- **`probe`** — arms and has ≥1 quarter of forward-ledger episodes, base rates printed
  with n. (W3+.)
- **`calibrated`** — survived its pre-registered gauntlet at promotion (authority only via
  the gauntlet — never in W1; display-tier regardless of tier).

A chain never emits an alpha score, gate, or size at ANY tier (DNR row 45 / TXI Article 1/2).

## Nodes

`nodes: {<id>: {src: <adapter>, ...}}`. Each node is one observable boolean state. Keys:

| key | meaning |
|---|---|
| `src` | the **source adapter** name (registered in `engine/transmission_chains.SOURCE_ADAPTERS`). Resolvable set in W1: `yahoo` / `commodity` (via `lib.store.read`), `transmission_state` (`data/transmission/latest.json`), `regime_state` (`data/regime/latest.json`), `forex_state` (`data/forex/latest.json`). |
| `test` | a small **structured test dict** the adapter evaluates → bool + a numeric receipt. NOT eval'd Python — a whitelisted operator dict (see **Node tests**). |
| `title` | `{en, zh}` short label (optional). |

### Node tests (whitelisted — no `eval`)

A `test` is a dict the adapter reads. Supported forms (fail-loud on an unknown op at load):

```yaml
# a series metric from a store adapter (yahoo / commodity / fred). UNITS: ret / rs /
# ratio_ret emit PERCENT (×100); ret_bp emits BASIS POINTS; ma_slope emits a raw
# price-delta. Thresholds MUST match the metric's unit.
test: {series: "CL=F", metric: ret, window: 60, op: gt, value: 25}       # 60d return > +25%
test: {series: "CL=F", metric: ma_slope, window: 50, lookback: 5, op: gt, value: 0}
test: {series: "T10YIE", metric: ret_bp, window: 22, op: gt, value: 15}  # Δ ~30d > +15bp
# a relative-strength cohort proxy (two series; requires 'vs'; value in pct points):
test: {series: "QQQ", vs: "SPY", metric: rs, window: 63, op: lt, value: 0}  # RS_63d < 0
# a ratio metric (two series → one price ratio; requires 'ratio'; value in pct):
test: {series: "HYG", ratio: "LQD", metric: ratio_ret, window: 22, op: lt, value: -2.0}
# a field pulled from a state adapter (dotted path into the JSON):
test: {path: "state.rates.direction", op: eq, value: rising}
test: {path: "state.rates.real_10y_chg_63d_bp", op: gt, value: 30}
test: {path: "dollar_desk.trend", op: eq, value: up}
# membership: needle 'value' inside a list-valued path (e.g. headwind_for):
test: {path: "transmission.headwind_for", op: in_contains, value: "EM equities"}
# a boolean field:
test: {path: "froth_fragility.unwind_risk", op: is_true}
# an AND / OR of sub-tests:
test: {all: [ {path: "...", op: eq, value: rising}, {path: "...", op: gt, value: 30} ]}
test: {any: [ {path: "...", op: in, value: [warning]}, {path: "...", op: gte, value: 25} ]}
```

Ops: `gt gte lt lte eq ne is_true is_false in in_contains`. Metrics (store adapters):
`ret` (pct change over `window` trading days), `ret_bp` (absolute Δ of a level series in
basis points), `ma_slope` (change in the `window`-day MA over `lookback` days), `rs`
(RS = own `window`-return minus `vs`-return, in pct points; requires `vs`), `ratio_ret`
(pct return of the `series/ratio` price ratio; requires `ratio`). A `vs` is required by
(and only by) `rs`; a `ratio` by (and only by) `ratio_ret` — the validator rejects a
stray companion key so a metric-name typo can't silently compute the wrong thing. A
`path` is a dotted key path into the state adapter's JSON. Missing series/path → the node
is `unresolvable` (chain can't arm), NOT `False` — the validator distinguishes them.

A structured falsifier may carry a top-level `src:` (adapter) when its `when` test reads a
different source than the chain's terminal node (e.g. the oil chain's breakeven falsifier
reads `fred`).

## Hops

`hops:` is an ordered list; hop *k* connects node *k* to node *k+1*. Keys:

| key | meaning |
|---|---|
| `from`, `to` | node ids (must exist in `nodes`). |
| `label` | `{en, zh}` short bilingual DISPLAY label for the transition (optional; W4). Names the hop for the Cascade Monitor + site-published subset (e.g. "Oil shock → breakevens rise"). Distinct from `mechanism` (the long causal prose) and from the node `title`s. |
| `sign` | `+` \| `-` — expected co-movement direction (documentation; the node tests carry the actual thresholds). |
| `lag_d` | `[lo, hi]` — the confirmation window in **calendar days**: `to` must confirm within `hi` days of `from`'s confirmation, else the episode `expires`. `lo` is documentary (earliest plausible). |
| `condition` | plain-word regime gate (`{en, zh}` or str) — the regime where the hop SHOULD work (TXI-R6). W1 records it; regime-conditional calibration is W3. |
| `mechanism` | `{en, zh}` prose — the causal story. |
| `prior` | str — the hop-strength prior source (a transmission-matrix IC key if present, else theory). Documentary in W1. |

## Falsifiers

`falsifiers:` is a list. Each entry is either plain prose (documentary) OR a structured
`{when: <node-test>, note: "..."}` that the compiler checks each night on an ARMED
episode. A fired falsifier → the episode transitions to `failed` (and, at promotion, the
kill is logged into the CHF null library). W1 supports the structured form; bare-prose
falsifiers are recorded but not auto-checked (noted as such).

## Exposure screens (W2 — declared only)

`exposure_screens: {<flag>: {field_expr: "...", note: "..."}}`. Per-ticker screens that,
in W2, resolve an armed chain to named blast-radius flags with field receipts
(`refinancing_channel`, `long_duration_valuation`, `fcf_burner`, ...). **W1 declares them
for schema forward-compatibility and does NOT evaluate them** — `chain_state.json.blast`
is `[]` in W1.

---

## Episode state machine (TXI-R2)

`dormant → arming → propagating(hop k) → expressed | failed | expired`

- **arming** — node 0's test is TRUE (the chain's trigger fired).
- **propagating(hop k)** — hops `1..k` have each confirmed (their `to`-node test went true
  within the hop's `lag_d` window of the prior confirmation). `k` counts confirmed hops.
- **expressed** — the final hop confirmed (terminal node true in-window).
- **expired** — a hop's `lag_d[hi]` window closed with its `to`-node still false.
- **failed** — a declared (structured) falsifier fired on the armed episode.

Evaluated nightly from the existing artifacts; **idempotent** per `asof` (a same-day
re-run appends no duplicate ledger line and produces the same state). Transitions append
to `data/transmission/chain_episodes.jsonl` (forward ledger — nightly-advanced only).
