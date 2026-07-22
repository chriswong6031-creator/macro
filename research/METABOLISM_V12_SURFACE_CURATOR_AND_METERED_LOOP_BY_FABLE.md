# Metabolism V12 — The Surface Curator & the Metered Loop

**Author:** Fable (main loop), operator-directed 2026-07-21
**Status:** BUILD (operator order — not a loop-authored proposal)
**Prior art:** V2-D (UX-simplicity gate), V9 (attention economy), V10 (operator throttle), V11 (budget gate UX)
**Operator intent (verbatim gist):** loop improvements are cramming dashboards with more scoreboards without considering the page as it is; most additions are display-only and low-value; the site cannot ship as "a landfill of half-assed pieces" when real users arrive. New features stay welcome, but each must prove usefulness, prove it doesn't already exist elsewhere, and consider the page/site as a whole — including deleting or consolidating something to make room. Separately: the loops maxed out subscription tokens; need a real "take it down a notch," per-lobe importance targeting, and weekly cadence for unimportant lobes.

---

## 0. Diagnosis (what the audit found, 2026-07-21)

### The cramming has structural causes, not model causes alone

1. **The proposer is design-blind.** The PROPOSE lobe-brain prompt (`engine/metabolism/propose.py`) contains zero reference to `docs/DESIGN_DOCTRINE.md`, zero page context, no crowding concept, and lists `"ui"` as a first-class kind on equal footing with `"test"`. Its dedup corpus is DO_NOT_REBUILD + open PR lanes only — **nothing tells it what is already ON the pages.**
2. **The adjudicator is design-blind.** `_ORCH_SYSTEM` / `_ADV_SYSTEM` rule on fitness contracts and case-law collisions only. No usefulness bar, no page-holism criterion.
3. **The V2-D UX gate is dead code on the live path.** It fires only when a proposal declares `changed_files` — and `build_docket`'s pass-through whitelist **drops `changed_files`** (only charter keys survive), so docket proposals can never trigger it. Its density arm is honor-system (`numbers_added_to_default_view` defaults to 0 when omitted). The comment claiming "all front-page changes are T2-tapped" (R-V2-6) has no enforcing code — UI is plain T1.
4. **The audit checks code, not surfaces.** `_AUDIT_SYSTEM` rejects scope creep and correctness defects; a perfectly-scoped, correctly-coded, useless 40th scoreboard passes.
5. **Sonnet builds with no design guidance.** The build session prompt is proposal + fitness contract + containment rules; no doctrine, no "integrate, don't stack." (#3179, open, flips builds to Opus — necessary, not sufficient.)

### The token burn has three compounding causes

1. **The default pace is not "one loop a day."** V11's loops ladder floors at 1 loop per 5h window (`single`→1), so the hourly `metabolism-cycle` cron runs ~4–5 full chains/day *by default*, on top of the daily staggered chain. There is **no rung below 1/5h** short of `AUTONOMY_PAUSED`.
2. **The budget gate is blind, and blind = fail-open.** Ratelimit headers have never been captured (every `key_usage.jsonl` row has `headers: {}`), est-token fallbacks are disabled (`null`), so every key reads `pct_5h: null` → `eligible` → chains keep launching. Cooling (429'd) keys still count as eligible in the gate. Result on disk: 5 of 8 keys 429ing in daily clusters; `key_pool_degraded` immune events 4 days running. The loop's stop condition is *physically hitting the wall*.
3. **Attention has no operator pinning and no weekly rung.** V9 bands are LLM-discretionary with cadence sampling (1/2, 1/4); there is no deterministic "this lobe runs weekly" and no operator list of what matters. `METAB_INTENSITY=low` only scales docket size — propose/adjudicate/audit call volume is untouched.

## 1. Rulings

- **R-V12-1 (Surface law).** The site is a product with a scarce surface budget, not an append-only log. "Built and accruing" is decoupled from "displayed": data/context organs ship freely (epistemics law unchanged), but **pixels are earned**. Every `ui` proposal must declare: `target_page`, `user_question` (the plain-words question the panel answers), `ui_mode` ∈ add|improve|consolidate|remove, `panel_delta` (int), and `displacement` (what it removes/merges, when adding). Missing fields on a ui/front-page proposal = structural invalidity (fail-closed — the omission loophole is gone).
- **R-V12-2 (Surface census as evidence).** `data/metabolism/site_surface_map.json` — a deterministic census of every shipped page (bytes, structural-marker count, outline) built by `scripts/build_surface_map.py`, regenerated in the AGENDA stage. It is evidence, not judgment (mirrors V9 criticality). PROPOSE and ADJUDICATE receive the target pages' rows; a proposal whose panel title token-collides with an existing outline entry (same page or sitewide) is deterministically denied — "already exists elsewhere" is now checked against the *site*, not just PR titles.
- **R-V12-3 (Saturation one-in-one-out).** Pages above the saturation thresholds in `config/metabolism_surface_rules.yml` (IMMUTABLE) accept **no net-positive panel delta** from the loop: `ui_mode=add`/`panel_delta>0` on a SATURATED page is denied at propose AND adjudicate. Replace, consolidate, remove, improve remain open — and are the *preferred* moves everywhere.
- **R-V12-4 (Realized-delta teeth).** AUDIT computes the realized structural-marker delta and net byte delta from the actual PR diff with the same counter the census uses. Deny when: a front-page file gains markers under a non-ui proposal (undeclared surface change); realized delta exceeds the declared `panel_delta`; or a SATURATED page gains markers/bytes beyond the configured allowance. Declarations are now checked against the diff, never trusted.
- **R-V12-5 (Consolidation is fitness).** `ui_mode=consolidate|remove` proposals are first-class and explicitly encouraged in the proposer prompt. Surface debt (SATURATED pages a lobe owns) is injected as agenda pressure. The loop is rewarded for making pages *smaller and clearer*, not only bigger.
- **R-V12-6 (Design floor for UI builds).** Any `kind=ui` build session prompt carries the DESIGN LAWS block: read `docs/DESIGN_DOCTRINE.md` before touching a surface; glance tier = state + plain-word stance; technicals demoted to hover/Tier-2; bilingual EN/ZH pairing; **integrate, don't stack**. (Build-model upgrade to Opus is #3179's lane; V12 does not touch the model pin.)
- **R-V12-7 (The daily rung).** `METAB_PACE=daily` is a real rung: the hourly chain-runner cron no-ops entirely; only the daily staggered chain runs. Fail-open default remains `single` (R-V10-2 unchanged) — but the operator finally has a genuine "down a notch."
- **R-V12-8 (Operator lobe pins).** `config/metabolism_attention.yml` (already IMMUTABLE) gains `operator_pins`: `core` (proposes every eligible cycle, band-floored STANDARD), `weekly` (deterministic one-day-a-week cadence, spread by lobe-id hash), `paused` (zero improvement spend; URGENT_FIX supremacy G3 still overrides). Pins outrank LLM attention discretion; unpinned lobes keep V9 behavior. `METAB_INTENSITY=low` additionally doubles cadence denominators for unpinned lobes (eco mode that actually cuts call volume).
- **R-V12-9 (429s are readings).** A key cooling on a window 429 IS Anthropic reporting "window done": the budget gate scores it `pct_5h=100 (src=429_window)`. Verdicts expose `known_readings`; RUN_UNTIL burn modes refuse to chain when zero readings are known (blind burn is the one thing the gate must never do). Normal pace gating stays fail-open (R-V10-2).
- **R-V12-10 (Scope honesty).** W1 enforcement covers template/site-file diffs. Panels injected purely by Python builders bypass the realized-delta check until VERIFY-side re-census (W2) — the propose/adjudicate gates still bind them by declaration. Printed, not hidden.

## 2. W1 (this build)

`engine/metabolism/surface_map.py` (census + dup + realized-delta, shared counter) · `scripts/build_surface_map.py` (CLI) · `config/metabolism_surface_rules.yml` (thresholds; joins the self-mod fence) · propose: surface fields + validation + SURFACE LAW + map/design blocks + pass-through fix (`changed_files` now survives `build_docket`) · adjudicate: `_surface_screen` (fail-closed fields, saturation, sitewide dup) + rubric lines in both role prompts · audit: realized-delta pre-screen + auditor bullet · build: DESIGN LAWS block on ui kinds · throttle: `daily` rung + eco cadence factor · attention: operator pins · budget_gate: 429-derived readings + `known_readings` · metabolism-cycle.yml: blind-burn guard · agenda workflow: census regen step · admin: `daily` in pace vocab · tests + ci rows · initial committed census.

**Default pins shipped (operator may re-ratify in one line):** `core: [til]`; `weekly: [site-us-standouts, site-china-standouts, prophet, event-windows-forward-log, opex-windows-forward-log]`.

## 3. Deferred waves

- **W2:** VERIFY-side re-census (closes R-V12-10's builder-path gap by comparing the nightly-rendered census before/after `check_by`); digest "surfaces" section (panels added/removed by the loop, 30d); admin pins editor + surface-debt card; optional flagship rule: `panel_delta>0` on named flagship pages → T2 operator tap (needs tap UX; operator to ratify).
- **W3:** DREAM reads surface history — did consolidations hold? did added panels earn their `user_question`? Feed the preference prior.

## 4. Operator decisions

1. **Pins split** — `core: [til]` + everything else weekly is the shipped maximum-reduction posture; promote lobes to `core` by editing one line in `config/metabolism_attention.yml`.
2. **Throttle setting** — per your "too consuming": after merge, `METAB_PACE=daily` + `METAB_INTENSITY=low` are set (revert anytime: `gh variable set METAB_PACE --body single`).
3. **Saturation thresholds** — shipped values calibrated so today's flagship boards classify SATURATED (see `config/metabolism_surface_rules.yml`); tighten/loosen there (T2 — file is fenced).
4. **W2 flagship T2 tap** — say the word and net-new panels on flagships route to your phone even on unsaturated pages.
