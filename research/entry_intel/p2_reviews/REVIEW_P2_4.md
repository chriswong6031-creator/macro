# REVIEW — P2.4 Board Contract v2 (branch `ei/p2-board-stack`, PR #1472)

**Reviewer:** Opus 4.8 subagent (Entry Intelligence, Phase-2 BUILD review)
**Date:** 2026-07-05
**Spec:** `research/entry_intel/P2_4_BOARD_CONTRACT_V2_DESIGN.md` (APPROVED, Fable 2026-07-05)
**Method:** read-only cumulative diff (`git diff origin/main...origin/ei/p2-board-stack`); no shared-checkout mutation; ACs verified by inspection + read-only replay where the live snapshot permits.

**VERDICT: CLEAN (with advisories) — stage may be built upon.**

No blocking findings. Ranking-neutrality holds, scope boundary (§5) respected, i18n law satisfied, `_lane_for` logic correct, template renders without error on all edge cases. Two design deviations from the registered spec are documented as ADVISORY — both are defensible and arguably improve the build, but they are unregistered and the next stage (P2.1 shadow ledger, P3 cell rollups) should be aware the *displayed* `align_tier` vocabulary changed.

---

## Files changed (verified)
Only two files touched: `scripts/build_stock_library.py` (+~115 net) and `templates/dashboard.html.j2` (+48). **No `engine/` file touched.** Confirmed via `git diff --name-only`.

Branch builder `py_compile`s clean. Branch template passes `scripts/check_title_i18n`.

---

## Per-AC results

| AC | Verdict | Basis |
|---|---|---|
| AC-1 no row dropped | **PASS (structural)** | Diff adds fields + changes lane derivation only. `buyable`, `_recovery_cands`, `watch`, `buyable_trend[:120]` are all READ, never reassigned/filtered. Sort (`_alpha_key`) and `[:120]` cap unchanged. No filter added to buy/watch/laggards assembly. Byte-diff harness could not be run (needs full nightly build over R2/Massive stores absent from git) — builder's "0 dropped" is *simulated*, but the code path cannot drop rows. |
| AC-2 lane_counts logged + non-zero | **PASS (structural)** | Builder unconditionally sets `wide["lane_counts"] = dict(Counter(...))` over `buy+watch` and `log.info("P2.4 lane_counts: %s", ...)`. JSON field always present. Non-zero contingent on real build (live snapshot predates change; not runnable here). |
| AC-3 continuation set-membership + branch fires | **PASS (logic-verified)** | `_lane_for` transcribed and unit-tested (10/10 cases): ARMED/near/APPROACHING/bear_recovering/turning + `weekly_phase=="rising"` → `continuation`; everything else correct; UNKNOWN branch logs + defaults `bottoming`. Loud-failure path: the spec's AC-3 `sys.exit(1)` lives in a *standalone post-build check script*, NOT builder code — the builder has no `sys.exit` if the branch goes dead (it relies on the external AC-3 script + `log.warning` on UNKNOWN tiers). Branch-fires "PASS" is simulated. See ADVISORY-1. |
| AC-4 i18n parity (no translated `title=`) | **PASS (verified, discriminating)** | Ran `python3 -m scripts.check_title_i18n` against the branch's `dashboard.html.j2` → `OK`. Positive control: this guard historically fires on real violations (#1095), so a clean pass has power. All new translated text uses `data-tip-en`/`data-tip-zh`; the only `title=` tokens in added lines are inside comments asserting "no title= attribute". |
| AC-5 above_trend on continuation rows | **PASS-conditional (path real, unpopulated in snapshot)** | `_get_above_trend` reads `r["tech"]["above200"]`; `tech` IS attached to rows at `build_stock_library.py:372` (`"tech": snapshot(c)`), and `snapshot`→`engine/canon.py:475` produces `above200`. Path is real. Field is null in the cached snapshot (computed at build time) — cannot verify populated value read-only. NOTE source deviation, ADVISORY-2. |
| AC-6 setups.json rank_by="alpha" + lane fields | **PASS (verified against live gap)** | Confirmed live `setups.json` has `rank_by=None` and buy rows lack `lane` (the latent gap the spec named). Step F backfills `_sr["lane"]` for every buy row and sets `setups["rank_by"]="alpha"` when None, then re-writes. `setups` is in-scope at the Step F site (both at `main()` body indent). Logic correct. |
| AC-7 weekly_phase on board rows | **PASS-conditional** | Step A populates `r["weekly_phase"]` from `profiles[t]["alignment"]["weekly"]` for buyable/recovery/watch rows before `_tag`. All null in cached snapshot (MTF not run in cached data); genuine value contingent on full build. Builder claims 21/21 buy rows carry it (simulated). |

**Live snapshot ground truth (read-only):** `us_standouts.json` currently has `align_tier ∈ {aligned, None}`, `lane ∈ {trend, None}`, no `lane_counts`, all `weekly_phase=None` — i.e. it is the pre-v2 (v1) artifact. Every builder AC result is therefore a *simulation*, not an observed build output. This is expected (nightly build needs R2/Massive stores) and the builder disclosed it. It means AC-1/2/3/5/7 are verified at the *code-path* level here, not at the *rendered-artifact* level.

---

## Ranking-neutrality audit (special attention item) — PASS

- No occurrence of `_combine_key`, `_asort`, `_atier`, `_entry_ok`, `_alpha_key`, sector-cap, or admission logic in added *code* lines (only in comments/docstrings).
- `buyable_trend = sorted(buyable, key=_alpha_key)` and the `[:120]` cap are **unchanged**; ordering is computed *before* `_tag` runs.
- `_tag` mutates only display fields (`align_tier`, `lane`) — after ordering — and does not feed back into the sort.
- `rank_by` in `us_standouts.json` header stays `"bottoming-alignment"` (untouched).
- `setups.json` still ranked by `rank_setups(..., rank_by="alpha")`; Step F only *labels* (`lane`) and fills the header `rank_by` string — no re-sort of setups rows.

**Ranking is not touched. §3.3 / §5 boundary respected.**

---

## ADVISORY findings

**ADVISORY-1 — `_tag` overrides `align_tier` with `conviction.alignment.tier` (unregistered deviation).**
Spec §4.1 Step B `_tag` does `r["align_tier"] = tier` (the `_atier` board value: `aligned`/`near`) and derives lane from `_lane_for(tier, weekly_ph)`. The implementation instead computes `_eff_tier = conviction.alignment.tier or tier` and uses `_eff_tier` for BOTH the stored `align_tier` AND `_lane_for`. Consequence: the *displayed* `align_tier` for trend rows changes from `aligned/near` to `PRIME/ARMED` when conviction data exists. This is the mechanism that lets the continuation branch actually fire on live data (live board vocabulary was `aligned/None`, which never hits `_ARMED_EQUIV`). It is defensible and arguably necessary for AC-3 to ever produce continuation rows — but it is an **unregistered contract change to the emitted `align_tier` value** that downstream consumers (P2.1 shadow ledger stratifies by lane/tier; P3 cell rollups) will now see. Recommend Fable ratify this as an intentional vocabulary switch, or the spec §4.1 be amended to match. Not blocking (display field, additive, no rank effect).

**ADVISORY-2 — `above_trend` sourced from `tech.above200`, not spec's `gate.get("above_200dma")`.**
Spec §3.2/Step C sources `above_trend` from `gate.get("above_200dma")` (already computed at L760). The implementation sources from `tech.above200` (via `_get_above_trend`, `stock_technicals.snapshot`). Both are valid same-concept computations, but they are *different* code paths and could in principle disagree at boundary cases (SMA reindex/ffill in canon.py vs the gate's `above_200dma`). Path is real and populated at build time. Recommend confirming the two agree on a real build, or standardizing on one source.

**ADVISORY-3 — `_NEAR_EQUIV` expanded with `bear_recovering`, `turning` (weekly_phase-domain values in an align_tier set).**
Spec §4.1 registers `_NEAR_EQUIV = {"APPROACHING","near"}`. The implementation adds `"bear_recovering","turning"`. These are `weekly_phase` values, not `align_tier` values, so they will effectively never match as tiers — harmless, but an undocumented expansion. Cosmetic; recommend dropping them or moving the note into the design.

**ADVISORY-4 — Spec §4.2 named the wrong template (`us_stocks_v2.html.j2`); implementation correctly used `dashboard.html.j2`.**
Spec §4.2 targeted `templates/us_stocks_v2.html.j2` and cited its L88-89 `border-left-color` / "ENTRY OPEN / SETTING UP" headers. That template renders a *different* shadow artifact (`us_standouts_v2.json`) with a different lane vocabulary (`entry_open`/`setting_up`). The **production** standout board (`us_standouts.json` → `_su`, with `nb-lane`/`lane-trend` chips) is rendered by `dashboard.html.j2:2659+`, which the builder writes at L2478. The implementation correctly modified `dashboard.html.j2`. This is a **spec error, not an implementation error** — the builder made the right call. Flagging so the spec is corrected before P3 references §4.2.

---

## Adversarial / edge-case checks performed (all clean)
- Jinja fragments (lane_counts pill, 200DMA badge, ext_z chip) rendered against synthetic data incl. missing keys, `ext_z=0.0` (falsy-but-not-none renders correctly), missing `lane_counts` (empty, no crash). No jinja-missing-key crash: all guards use `.get()` + `is not none`.
- `_lane_for` unit-tested 10/10 including UNKNOWN-guard.
- `ext_z` comparison `_ez > 2.0` protected by `is not none` + builder float-rounds `ext_z`, so no str-vs-float TypeError.
- Step F re-write of `setups.json` is in-scope and idempotent; overwrites the earlier L1948 write with lane+rank_by added.

## What could NOT be verified (honest gap)
Full nightly build (over R2/Massive stores absent from git) was not run. AC-1/2/3(branch-fires)/5/7 populated-value assertions are code-path-verified only. First-run failure point to watch: whether `conviction.alignment.tier` and `tech.above200` are actually populated on standout rows in the real build — if `conviction` is null for a row, `_eff_tier` falls back to the passed `tier` (safe); if `tech` is null, `above_trend` stays absent (AC-5 becomes vacuously pass). Recommend the orchestrator confirm AC-1/2/3/5/7 against the next real nightly artifact before P2.1 consumes the lane field.
