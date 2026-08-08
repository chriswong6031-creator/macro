# Breathing Platform — continuation handoff (2026-08-08, session 1 close)

**Program:** `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md` — MERGED to
main (#4975, 2026-08-08 10:42Z) incl. §7½ Massive addendum. Operator RATIFIED
same day. Run the program as a session chain over this doc + the masterplan.

## State at handoff (~11:00Z Sat 2026-08-08)

| Item | State |
|---|---|
| W-L0 gate 1 — append semantics (#4982) | armed merge-on-green; 42/72 board names measured flipping; adds `probe_center_buyable` (additive; evaluator reads named keys only) |
| W-L0 gate 2 — fade hysteresis (#4978) | armed merge-on-green |
| W-L0 gate 4 — prophet sentinel surface + engine timing rows (#4981) | armed; root cause was H3: finish step never SCHEDULED on cap-cancel (5-min grace), moved ahead of delivery tail |
| W-L0 gates 3+5 (F3 price basis, F5 dormant honesty) | **NOT built — first task of next session** once the three PRs above land (same target files; spawning earlier guarantees conflicts) |
| Terminal live prices + 1s bars | mastermind-terminal **#363** OPEN — review-merge when its Terminal CI job concludes (2/3 green at handoff). Real-time serving behind `HUB_REALTIME_QUOTES`, OFF pending operator gating decision (rec: sign-in) + Monday measurement |
| Terminal financials 17y | mastermind-terminal **#364** OPEN — same review-merge path. Vendor floor measured: statements start 2009 (XBRL mandate), 17 FY max. Fixed live −158.8B fabricated opex row |
| M1 real-time label flip (19 sites) | chip session ran Sat → market closed, correctly could not verify. **Completes Monday premarket** — rerun the chip/prompt; entitlement itself verified (trades/quotes 403→200, 2026-08-08) |
| tushare | token fixed by operator; CN badges revive on next asia run (verify `check_tushare_freshness` clears) |
| Tick/WS + second-agg wiring | OWNED BY ANOTHER SESSION. Seam rule agreed: write into the EXISTING plane files (`quotes_full.json`/`quotes.json` freshest-wins; bars in the `data/intraday` shape) so every consumer upgrades transparently; evaluator cadence 5min→1min then needs only a timer change |
| 52/53-week `fiscal_q_label` defect | chip running in another session |

## Next session: spawn F3+F5 (specs pinned), then W-L1

**F3 — one price basis (masterplan §0-3).** Armed edges derive from
dividend-adjusted series; evaluator compares raw Polygon prints; the
reconciler's `fill_vs_cross_pct` mixes bases (`scripts/reconcile_prophet_live.py:151-160,292-296`).
Fix: name the basis at every seam + startup assertion comparing pack
`as_of_close` vs quote `prev_close` per name. Durable direction: M5 vendor
corporate-actions service. Builder: opus, isolated worktree, scoped tests.

**F5 — dormant honesty (masterplan §0-5).** Original: down-band never probed
yet `dormant` asserts over it. NEW concrete case from #4982: a cross-class
name whose anchor is buyable has NO lower edge and `live_states` keys
`dormant` off `lo is None` — a name whose interval HOLDS at the live price
renders "nothing forming". Also needs a RULING (from #4978): suppressed
cross-path fades emit no `FADE_UNCONFIRMED` marker — adding one mints a new
event kind → new reconciler ledger rows; decide before building.

**W-L1 — evening close-pass (masterplan §4, gates §0 W-L1).** Picks live by
18:30 ET on 5 consecutive green sessions; provisional board published to the
live plane; per-name nightly confirmation delta published; zero `data/`
writes. Design pass first (provisional-board surface copy/placement is
user-facing → design lane law), then opus builders on the idle mac pool.
Collect attribution (run_status `elapsed_sec` → timings bands) rides along.

## Open operator decisions (masterplan §6)
Terminal real-time gating (anonymous vs sign-in) · D3 VPS tier / ThetaData
re-home · D5 alert channels (email first) · D6 era discipline (standing) ·
chartered-not-ratified: survivorship-true universe + minute-resolution
track-record self-audit (offered 2026-08-08, operator has not yet ruled).

## Loose ends worth one line each
- CLAUDE.md fleet line says "4 Linux render boxes" — measured: ONE
  (`pc-render-1`, WSL2). Docs-only fix candidate.
- `docs/VPS_LIVE_ORCHESTRATION.md` still claims china.html emits no board
  stamp (superseded by #4812) — partially healed in #4981; re-check after it
  lands.
- November DST: daily.yml 22:30Z cron races the FINRA file when EDT→EST
  (`daily.yml:10-11`) — unowned, scheduled failure.
- #4982 flagged local store lacks `russell_breadth` cache (1,763 vs ~2,900
  names) — A/B measurement was same-universe, but production armed counts will
  differ from the PR body's absolutes.
