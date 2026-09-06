# W6 frozen spec — history, compare, drilldown, research workflow

`child: macro-flow-observatory-v2-w6-research-workflow-20260902-fable-001`
`governing freeze: research/FLOW_OBSERVATORY_V2_MASTERPLAN_BY_FABLE.md §7 (Tier-2/3 homes), §11 (workflow owners), packet W6`
`design authority: this spec. Builders implement; they do not redesign.`

## 0. Not done unless (wave gates)

1. A user can drill from a group row into a 60-session history (absolute rate AND
   relative pressure, state bands, revision markers where ledger data exists), compare
   two groups, see similar prior episodes, and open contributing names in the Terminal.
2. Replay honesty: every history/episode visual computed by causal replay under the
   CURRENT method is labeled as such (pinned strings below); published-state history
   (from the W3 ledger) is visually distinct from replayed context and appears only
   where real ledger rows exist. Thin-ledger bootstrap renders honest accruing states —
   nothing fabricated, nothing blank-broken.
3. Watches: a user can watch a theme/sector via the EXISTING client watch store; watched
   groups surface a chip and sort affordance. No server-side alert engine is built —
   the alert-on-onset dependency is recorded (report + PR body) against the existing
   sentinel owner.
4. Evidence matrix for changed surfaces (dark/light × EN/ZH × 1440 + one 390 per
   theme), zero console errors, no page-level horizontal scroll, both themes judged as
   designs with declared treatments.
5. Targeted suites green; contract-delta 0 introduced (new test file wired both halves
   same commit); canonical rebuild committed; PR DRAFT/unlabeled; tree clean.

## 1. History drawer (per group, both lenses)

Interaction: clicking a group row's trend cell (or a new ⌄ affordance) opens an inline
history panel (server-rendered `<details>`-based; JS enhances, JS-off shows the panel
expanded for the top-3 themes only to bound page weight — state which in a comment).

Contents (60 sessions, from causal replay over the flow stores using current engine
methods/thresholds):
- dual sparkline pair: absolute 4wk rate series + relative pressure (vel) series
  (reuse the existing server-side SVG spark util `_spark`/illus idiom — no new chart
  machinery, no Plotly);
- state bands: background tint bands under the pressure line where the replayed state
  is non-neutral (up-tint above-norm, down-tint below-norm; both themes' band inks
  authored separately — dark: low-alpha fills; light: hatched or 6% tinted fills with
  hairline edges — declare treatments);
- revision markers: ◆ glyphs at sessions whose LEDGER rows carry revision_id > 0
  (only where ledger data exists);
- published-vs-replay split: sessions covered by real ledger rows get a thin baseline
  tick row ("published record"); earlier sessions are replay-only.
- REQUIRED caption (pinned): EN "Replayed under today's method — not what was published
  historically. Published record accrues from {ledger_start}." ZH
  "按当前方法回放——非历史发布值。发布记录自{ledger_start}起累积。"

## 2. Compare two groups

A compare affordance (checkbox per row, max 2; or a select pair control) renders a
side-by-side panel: both groups' §1 histories aligned on the same session axis + a
compact stat table (current abs, rel, quadrant, coverage, top contributor). Same-lens
comparisons only (theme↔theme, sector↔sector — cross-lens comparison is REFUSED with
a one-line reason: different denominators/universes; test this refusal). JS-off: the
compare control hides; a note names the JS dependency.

## 3. Prior episodes

For the selected group: the 3 nearest historical sessions (from the replayed 60-session
window extended to the store depth, max 250) by L2 distance on the normalized pair
(rel_pressure, abs_rate z-scored over the window), excluding the trailing 5 sessions
(no self-match). Rendered as small cards: date, the pair's values, what happened NEXT
in the replay over the following 10 sessions summarized DESCRIPTIVELY (pinned form: EN
"over the next 10 sessions, pressure {rose/faded/held} and absolute flow {improved/
worsened/held}" ZH "此后10个交易日，压力{回升/回落/持平}，绝对流向{改善/恶化/持平}")
— NO returns, NO predictive claim, and the panel carries the §1 replay caption plus:
EN "similar setups, not forecasts" ZH "相似情形，非预测". Episodes exclude any session
whose 10-session forward window would cross the current session (no future leakage —
test).

## 4. Terminal links + watches

- Member drilldown rows: name links to the Terminal instrument page using the EXISTING
  ticker-identity contract (find the current canonical URL pattern used by other pages
  — grep templates for terminal links; reuse exactly; never invent a new URL scheme).
  A member without a Terminal page renders unlinked (no dead links — test with a fake
  ticker).
- Watch chip: reuse templates/watchstore.js's existing store API (read it first; extend
  its key namespace with `flowgroup:<lens>:<id>` if its API allows arbitrary keys —
  if it does NOT, record the limitation and ship without watches rather than forking
  the store). Watched groups: ★ chip + a "watched first" sort toggle. Watches are
  client-side only; the PR body records the server-side alert-on-onset dependency as:
  "flow-state onset alerts belong to the watchlist-sentinel owner; not built here."

## 5. Tests (tests/test_flow_observatory_workflow.py, new — wire both CI halves same
commit)

1. replay history uses source-effective sessions (no build timestamps on the axis);
2. state bands match the replayed classifications at the current thresholds;
3. revision markers appear ONLY at ledger revision rows (fixture ledger);
4. published-record ticks appear only for ledger-covered sessions; bootstrap (empty
   ledger) renders the accruing caption and no ticks;
5. compare refuses cross-lens pairs with the pinned reason;
6. episode selection excludes future-crossing windows and the trailing 5 sessions;
7. episode summaries are descriptive-vocabulary only (assert no %-return strings, no
   banned predictive words: "will", "target", "expect" / "将", "目标", "预期");
8. Terminal links follow the existing contract; unknown ticker → unlinked;
9. watch-store integration: key namespace honored OR the recorded-limitation path taken
   (test whichever shipped);
10. JS-off: top-3 expanded histories render; compare hidden with note;
11. no new chart library; sparks server-side;
12. mutation M1: strip the replay caption → tests 1/4-adjacent caption assertions fail
    (paste output).

## 6. Real proof (PR body)

Use the real current data: a genuine drill (group → history → episode → member →
Terminal URL) walked in the evidence with crops; watch chip exercised (or limitation
recorded); full §0.4 matrix; performance note (page weight delta — history panels are
server-rendered; state the KB delta and keep the page under 800KB total, else demote
depth); authority context_only; limitations: server-side alerts dependency, thin-ledger
bootstrap, episodes are descriptive.
