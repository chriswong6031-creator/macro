# Research Factory — Surfacing Lane (program seed, for a future Fable session)

**Status:** NOT STARTED — the charter (`research/RESEARCH_FACTORY_MASTERPLAN_BY_FABLE.md` §8 answer 9) rules paper-monitor artifacts **admin-only first**; any wider surfacing is a separate ruling. Factory W0–W7 COMPLETE 2026-07-06.
**Prepared:** 2026-07-06 by the Fable session that built the factory.
**Current visibility:** paper candidates already reach the admin Experiments tab automatically — `research_factory_decide.py` writes a `registry_seed.json` entry with `hook='track_record'` + `track_json` pointing at `data/research_factory/track/<id>.json`, and `engine/experiments_registry.py`'s overlay refreshes status/days-until each build. A15 is live there now (come_back 2027-03-13). Nothing else is surfaced anywhere.

## 1. What this program is

Graduate factory artifacts to operator-facing surfaces in tiers:
- **Tier 1 (low risk, likely first):** a dedicated Factory panel in the admin console (admin.mastermind-x.com) — funnel health (`data/research_factory/health.jsonl`), the review queue (`data/research_factory/review/queue.md/json`), paper candidates with tripwires and monitor rows (`paper_monitor.jsonl`), kill ledger with reasons.
- **Tier 2 (separate ruling required):** committee.html / Neural Web surfaces showing factory context (e.g. "N candidates in paper, M killed this month") — display-only narrative context, never inputs.

## 2. Binding constraints (verified in the 2026-07-06 census — the traps are specific)

- **`validated`-language CI:** `scripts/check_validated_claims.py` SCAN_GLOBS covers ONLY `templates/` (`*.j2`,`*.js`) and `site/` — and it runs in `cycle-calibration.yml` (monthly), NOT ci.yml. If factory metrics surface into templates/site, (a) never emit the word "validated" (the review-queue builder already avoids it — keep that discipline), (b) extend SCAN_GLOBS to the new template paths in the same PR, (c) consider whether the monthly-only cadence is acceptable or the check needs PR-time wiring for those paths.
- **Article-2 perimeter:** surfacing is READ display; any read of `data/research_factory/` from a module on `synapse.yml meta.article2_surfaces` (alert_triage, board_ordering, top_setups, attention_queue, push_floor) hard-fails `scripts/check_research_factory_authority.py` in ci.yml. Admin/committee builders are not on that list — but if a shared partial is imported by one, the guard fires; keep factory panels in factory-specific builders.
- Every rendered surface carries the display-only phrasing (the artifacts embed `"note": "display-only; no scored-path authority"` — render it, don't strip it).
- **Bilingual UI laws:** EN/ZH; NO translated text in `title=` attributes (use the `data-tip-en`/`data-tip-zh` popover pattern; `check_title_i18n` CI guard); zh flips up/down color tokens at the root (memory `zh-updown-token-flip`).
- Nav architecture: `_navlinks` is the shared menu; out-of-loop builders freeze the nav (memory `nav-chrome-architecture`) — an admin tab is safer than a new public page.
- Render budget: admin pages build off the render path today — keep it that way; the factory panel reads committed JSONL, no compute.

## 3. Design sketch (Tier 1)

Admin console already has an Experiments tab reading `site/marketdata/experiments.json`. Add a Factory tab: a small builder (`scripts/build_admin_factory_panel.py` or extend the existing admin build) emitting a compact JSON {funnel counts by state + trend, kill histogram by kill_class, challenger advisory-vs-decision divergence (the rubber-stamp detector — health.jsonl already computes it), paper candidates with tripwires + latest monitor row, pending review-queue count}. Wire into whatever step builds the admin console today (find it — memory `admin-console-deployed`, `admin-experiments-tracker`).

## 4. Fable decision checklist

1. Tier 1 scope: full ledger browsing or the summary JSON above? (Recommend summary — the queue.md is already the deep-dive artifact.)
2. Is the kill ledger (with challenger steelmen) operator-visible? Recommend yes — kill-scrutiny symmetry says kills deserve the same visibility as promotions.
3. Tier 2: does committee.html get factory context at all, and if so who writes the narrative (a Brain at A1-EXPLAIN reading factory artifacts is legal; verify it's not on an Article-2 surface)?
4. ZH translations for the panel now or EN-first?

## 5. What to read first in a fresh session

Charter RF-11/RF-16 + §8 answer 9; `scripts/check_validated_claims.py` (SCAN_GLOBS); `scripts/check_research_factory_authority.py`; `engine/experiments_registry.py` (the overlay you're extending); memory `admin-console-deployed`, `admin-experiments-tracker`, `t-macro-not-in-attributes`, `research-factory-program`.
