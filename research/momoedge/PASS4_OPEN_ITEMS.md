# MomoEdge Program — Pass 4 Open-Items Build Docket

Status: BUILD DOCKET (operator-directed, 2026-07-09). Context source for the pass-4 build
lanes. Program home: `research/momoedge/MASTER_BUILD_DOCKET.md`; memory:
`momoedge-competitive-build-program`.

Prior state: passes 1–3d shipped and deployed (Terminal suite + Prophet live at
app.mastermind-x.com; macro #1811/#1815/#1816/#1820/#1826/#1873/#1899/#1910/#1911;
terminal #20/#21/#22/#23/#31/#34). This docket covers the remaining open items.

House laws that bind every lane here: display-tier only (no scoring/money-path);
OI[t-1] law; nightly is the sole ledger advancer; "validated" is CI-enforced; EN/ZH
bilingual with no translated `title=`; branch off fresh origin/main (macro) or
origin/master (terminal); commit → push → PR → same-day squash-merge; never touch main
checkouts' git state; no bare `git stash`; secrets (.env) are sourced, never printed.

---

## Item A — Wire `build_options_matrix` into nightly ops (task #15, PRISM freshness)

**Status update (2026-08-10): CLOSED and scheduled.**
`scripts/build_options_matrix.py` (merged #1820, expiry fix #1899) is the one-shot
publisher: ThetaData EOD store → `options_structure/matrix/<ROOT>.json` on R2, default
10 roots (SPY QQQ IWM NVDA TSLA AAPL MSFT META AMD GOOGL). It is wired through
`ops/launchd/com.macro.optionsmatrix.plist` and `ops/launchd/run_options_matrix.sh`;
it is deliberately not a `daily.yml` lane.

**Home decision (settled by orchestrator recon):** a sibling **launchd** job, NOT
daily.yml. Grounds: the GitHub self-hosted runner has a virtualized FS and cannot see
`~/theta-ops-wt/data/thetadata_eod` (the store); launchd lanes in `$HOME` avoid the
~/Documents TCC denial. Precedents in-repo: `ops/launchd/com.mastermind.optionshub.plist`
(16:45 ET weekdays, runs from `/Users/chriswong/flow-ops-wt` via
`ops/launchd/run_with_env.sh` + `.env`) and `com.mastermind.liveflow.plist`.

**Timing constraint:** the theta store is fed by `com.macro.thetadata-backfill`, a
KeepAlive *loop* (no fixed completion time). So the matrix job must gate on **store
freshness**, not clock order: schedule ~19:00 ET weekdays, and the runner script checks
the store's latest session (SPY EOD present for today per NYSE calendar — reuse
`lib/nyse_calendar` semantics from the #1917 freshness-gate pattern) with a bounded
retry (e.g. every 20 min, ≤6 tries), then runs
`python -m scripts.build_options_matrix --publish`. Per-root failures already log+skip.

Delivered in-repo: `ops/launchd/com.macro.optionsmatrix.plist` + its runner script.
The deployment pattern installs the plist under `~/Library/LaunchAgents` and points at
`/Users/chriswong/flow-ops-wt`, same as optionshub. `git -C ~/flow-ops-wt pull
--ff-only` remains the update rule for that checkout. Manual `launchctl kickstart`
and `options_structure/matrix/SPY.json` re-fetch by `asof` remain the production-proof
pattern; logs are `/tmp/optionsmatrix.*.log`.

## Item B — GICS sector + market cap into the nightly heatmap manifest

The heatmap manifest (~8.7k rows, served via Terminal `/api/flow?f=manifest`) is
OTHER-dominant on sector and uses a dollar-volume proxy for size. Enrich the nightly
manifest build with real GICS sector + market cap (Polygon reference data —
`ingest/build_polygon_universe.py` is the existing universe builder to extend or reuse;
investigate where the manifest is written in `scripts/build_options_hub_nightly.py`
first). Null-honest: names without reference data keep OTHER/no-mcap (never invent).
Verify: manifest rows carry `sector`/`mcap`; OTHER share drops materially; Terminal
heatmap groups + cap-sizes correctly against the new manifest.

Reference (extracted verbatim from their `heatmap-widget.js`, for parity checks):
per-name flow sentiment `sent = clamp((callPrem − putPrem)/max(totalPrem,1), −1, +1)`;
sector chip % in flow mode = `mean(sent over flow-active names) × 100` (breadth =
bullish-count/active-count); price mode chip = equal-weighted `mean(change_pct)` with
breadth = gainers/total. Their tile data comes cap-ordered (`market_cap.desc`).

## Item C — Terminal perf + Tape SWR + Prophet live-mark overlay (terminal repo)

1. **Feed virtualization/cap**: `.obs-fd-list` renders ~2000 event cards as live DOM
   (twice-flagged perf smell). Virtualize (windowed rendering) or cap with incremental
   "load more" — keep the 2-rows-plus-peek scroll UX and `.obs-scroll` styling intact.
2. **Tape SWR adoption**: `OptionsHubView.tsx` tape-path raw `fetch()`es (~lines
   1082–1295) bypass the `flowClientCache.ts` SWR layer (`flowGet`) — migrate them so
   tab switches stop refetching cold.
3. **Prophet live-mark overlay**: consume `prophet.live_marks/v1` (contract in Item E).
   Add `prophet_marks` to the `/api/flow` f-param map (same R2-then-fallback chain). On
   the Prophet option card: if a mark for the plan's OCC symbol is fresh (≤20 min old,
   during RTH), show it tagged `LIVE`; otherwise show the existing EOD mark tagged
   `EOD`. Absent file = silent EOD fallback (the publisher may ship after this lands).
   Display-only; no plan math changes.
4. **Review gate must re-verify the 中文 toggle** across every hub tab (a prior
   reviewer couldn't reproduce switching once) — rendered evidence both languages.

## Item D — CLOSED (no lane)

- 07:00 PT scheduled task `momoedge-terminal-deploy-verify`: fired 2026-07-07, disabled.
- Sector-chip formula extraction: recorded in Item B above.

## Item E — Prophet live premium marks publisher (macro, data side)

MomoEdge shows live option premium on picks; ours is EOD-mark only. Contract
(orchestrator-fixed, both sides build to it independently):

```json
R2 key: live_flow/prophet_marks.json
{ "schema": "prophet.live_marks/v1", "asof_utc": "...", "session_date": "YYYY-MM-DD",
  "marks": { "<OCC symbol>": { "bid": 1.23, "ask": 1.31, "mid": 1.27,
              "last": 1.25, "ts_utc": "..." } } }
```

Publisher = a **new lightweight sibling launchd job** (e.g.
`com.mastermind.prophetmarks`, every 5 min during RTH from `~/flow-ops-wt`): read active
plans from `site/prophet/index.json` (R2 copy is fine), pull current quotes for the ≤12
active OCC contracts from ThetaData v3 (per-contract snapshot — remember v3 rejects
wildcard-exp current-day pulls, #1774), publish the small JSON. **Do NOT touch the
existing live-flow poller** (its cycle time is already strained; that lane has an
owner). Fail-soft: any error → skip cycle, never crash-loop (ThrottleInterval). Same
plist/install/verify pattern as Item A. Display-only.

## Item F — CLOSED: UNUSUAL baselines + VEX experimental field (macro, data side)

1. **Flow baseline (shipped earlier):** the nightly per-root 30-session volume
   baseline remains `data/live_flow_out/unusual_baseline.json` + R2
   `live_flow/unusual_baseline.json` (`flow.unusual_baseline/v1`). Poller consumption
   remains behind `UNUSUAL_BASELINE=1`, with the producer on and the poller flag off
   until that lane's owner promotes it.
2. **VEX (shipped, EXPERIMENTAL):** `engine/options_matrix.py` publishes per-cell
   `vex_mn` from closed-form BS vanna and OI[t-1], with payload `experimental: true`.
   S-VANNA-RELIEF remains only a registered family: this field is display plumbing,
   not a new signal, and has no scoring path.
3. **PRISM per-side UNUSUAL closure (2026-08-10):** the daily matrix measures call
   and put independently as today's observed side volume divided by the median of its
   observations inside the 30 most recent strictly-prior root EOD sessions for the exact
   `(expiration, strike, right)` contract side. It requires 10 observations; an
   explicit zero is retained, while a missing contract-day is not a zero. Ratios
   `>=3.0` are `unusual`, otherwise `normal`, and are conservatively truncated to two
   decimals. Each side can be null independently; the outer field is null only when
   neither is eligible. This reliable-magnitude lens remains display/context only
   with no score, money-path, or authority change.

## Verification gates (all lanes)

Macro lanes: artifact JSON inspected (schema + asof + spot fields sane), pytest for any
engine change, R2 object re-fetched after publish, launchd one-shot kickstart proven
from its log file. Terminal lane: `npm run build` green + rendered browser evidence at
1440/1000 widths + EN/ZH + no console errors; the orchestrator deploys to the VPS after
merge (rsync pattern; re-verify origin/master tip contains the merge SHA first — known
propagation race).
