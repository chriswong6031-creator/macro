# CN Breathing Platform — continuation handoff (2026-08-16, session 2)

**Program:** CN-W-L3 / China Breathing Platform.
**Ruling:** `research/CN_BREATHING_PLATFORM_ARCHITECTURE_2026-08-15.md` (#5744).
**Prior:** session-1 handoff `research/CN_BREATHING_PLATFORM_CONTINUATION_HANDOFF_2026-08-15.md` (#5770).
**This wave:** CN-PR-1 engine + VPS service (this PR).

---

## Shipped in this session (CN-PR-1)

| Piece | Path | Notes |
|---|---|---|
| Armed pack | `engine/prophet_live/cn_pack.py` + `scripts/build_cn_live_pack.py` | CN calendar + per-class ±10/±20 band + T2 latch + frozen nightly legs. Reuses `armed_pack` (no second probe). |
| Evaluator + close pass | `engine/prophet_live/cn_states.py` + `scripts/cn_live_evaluator.py` | Lunch freeze, delay-aware quote age, basis audit, 80% close-board floor, no manufactured close. |
| VPS units | `app/deploy/macro-live-cnprophet.{service,timer}` + `update.sh` self-arm | `OnCalendar=Mon..Fri 01..07:03/5 UTC`; script self-gates on `cn_clock.is_evaluable`. |
| Health clause | `scripts/check_vps_live_health.py` | Absent-ok until first ship; ≤6 min morning/afternoon, ≤20 min lunch, close_board by 07:20 UTC. |
| GH backstop | `.github/workflows/cn-prophet-live.yml` | ubuntu-latest; stands down when `VPS_LIVE_PRIMARY=true`. |
| Tradability extract | `scripts/build_china_library.stock_tradability_ok` | Nightly wrapper calls it; counters unchanged. |
| Tests | `tests/test_cn_live_{pack,evaluator,vps_lane}.py` | Replay honesty cases + host wiring. 305 passed with the US prophet-live sibling suites. |

CN-PR-0 (`cn_clock`, `sessions_behind`, `armed_pack` calendar threading) was already on main (#5759).

---

## Resume plan (next session)

Serialized, each off fresh `origin/main`. **Do not stack.**

1. **Own this PR to merge** (CN-PR-1). Arm `merge-on-green`; stay until squash-merged. Shared-file watch: `update.sh`, `r2io.py`, `check_vps_live_health.py`, `build_china_library.py`.
2. **CN-PR-3 — runtime board** (ruling §7): `templates/cn_prophet_live.js` + `china.html.j2` stocks-mode wiring + bilingual chips + committed crops + `tests/test_cn_live_surface.py`. Feed floor + fail-closed to SSR. Byte-pair `templates/` + `site/` if the JS is a paired plain-copy.
3. **CN-PR-4 — watchdog** (ruling §8): additive `freshness_sentinel` surface (id must NOT contain the substring `prophet_live` — suggested `cn_board_live`; keep artifact path `/live/cn_prophet_live.json`) + `scripts/cn_live_rescue.py` + tests. Sentinel was touched by commercial-alerts — rebase fresh.
4. **CN-PR-2 — settlement wiring** (ruling §8): `asia-close.yml` arming step after library rebuild (`timeout-minutes: 12`, `continue-on-error: true`) + `scripts/reconcile_cn_live.py --asia` + confirmation receipt. Receipt-in-hand law (#5220). Timer window extension to ~11:00 UTC is here, not in PR-1.
5. **Acceptance:** replay already in CI; browser proof (static N−1 vs runtime N, desktop/390px/EN/ZH) on PR-3; then arm 3 consecutive live mainland sessions (next session Mon 2026-08-17, first evaluator tick ~01:15 UTC — only after the VPS units have been pulled by `update.sh`).

---

## Standing cautions (unchanged)

- CN-LIMIT-ALPHA isolation: no imports from `research/cn_prophet_audit/`, no China-Intelligence composites, no touching the 5 collectors #5730 owns.
- US sister session may resume — keep `r2io.py` / `update.sh` / `check_vps_live_health.py` diffs additive.
- Do not run the full pytest suite in a sparse tree. This worktree is FULL.
- A merged PR does not update any folder until that folder fast-forwards.
