# GD-3 Commission — Live provisional Risk Envelope (display/advisory only)

**Commissioned by:** Fable COO 2026-08-20, on GD-2 production acceptance (Gate 8 closed
2026-08-20: first production publish `fae690766555`, live DOM verified at 390/768/1440,
bundle `fd9ccdbe47f7f008`). Sol's GD-3 authorization is the standing wave graph (GD-3
depends only on GD-2; matrix row 16 "Fable-directed builder", authority "display/advisory").
**Wave:** `WS:GREY-DEER-RISK-INTELLIGENCE` GD-3 · **One PR.**
**Authority: DISPLAY/ADVISORY ONLY.** All four envelope authority booleans stay false.
No policy authority, no Prophet restriction, no alerts (GD-8A is a separate wave).
**Governing law (precedence):** architecture freeze → command packet §GD-3 ("Live
provisional envelope and pending escalation") → this commission. On conflict, stop and
return to Fable.

## §0 Acceptance gates (not done unless)

1. **Same composer.** The live builder feeds the EXISTING pure composer
   (`engine/risk_envelope.py`) with live-clock-valid inputs. No second composer, no
   live-only stage arithmetic, no new weighted risk number. Semantic laws from GD-2R1
   are inherited verbatim: V0 descriptive vocabulary only
   (`NONE | FRAGILE | TRANSMITTING | BREAKDOWN | null`), LC BROKEN alone → FRAGILE
   never TRANSMITTING, `stage_since: null` in V0, required-unmappable source nulls the
   stage, coherence compares market reads only (posture excluded), zero-policy copy
   ("no Grey Deer policy active").
2. **Output = `site/live/risk_envelope.json`** written by a new
   `scripts/build_live_risk_envelope.py` on the existing VPS live plane (fast lane),
   atomic write, schema `mastermind.risk_envelope/v1` plus the live-plane freshness
   fields the plane already uses (`built`, `stale_after_min`, `live_active`,
   `stale_reason` — copy the shape from `scripts/build_risk_state.py`). The payload
   carries `lineage: provisional` (or equivalent frozen field) and the settled bundle id
   it overlays, so the browser can prove live-over-settled identity.
3. **Clock law (freeze §GD-3):** only evidence whose first-known clock is valid at the
   live observation may enter. `future-dated live input is refused` (test). The live
   lane NEVER writes durable forward ledgers: builder runs with `COLLECT_LANE` unset and
   a test asserts no ledger append on any code path (`engine/ledger_lane.py`
   `nightly_advance_enabled()` gate family is the law; do not add a new arm anywhere).
4. **Stale-vs-settled law:** a live observation older than the newest settled envelope
   session can never overwrite or visually outrank it (test + browser check). When the
   nightly settles a session, the provisional lineage for that session is
   superseded/cleared correctly on the next live fire (test with a fixture pair).
5. **Debounce/pending law (freeze §GD-3):** a same-tick stage escalation is visible
   immediately as a PENDING badge; the authoritative live stage change follows the
   frozen persistence contract (pick up the existing debounce fields
   `band_changed`/`pending` convention from `build_risk_state.py`; freeze the chosen
   persistence window in the PR body). De-escalation is never faster than escalation
   merely because a source disappeared: source outage → `data_state: DEGRADED` /
   stage `null` ("Not enough to say"), NEVER a calm/Risk-on vote (test).
6. **Consumer surface:** the existing GD-2 band on macro.html gains a live-provisional
   overlay only — reuse the band's existing visual language (chip/badge idiom already
   in the band CSS); NO new design surface, no new page. If any genuinely new visual
   element is needed, stop and route it through the Design lane (designer/Fable), then
   hand the frozen markup back to the builder. Falsifier language law holds on all
   user-facing copy. EN/ZH, dark/light, 390/768/1440 with no page-level horizontal
   overflow (the GD-2 gate, re-asserted on the overlay).
7. **Access boundary unchanged:** `site/live/risk_envelope.json` stays default-deny for
   anonymous (the house payload gate). Do NOT edit the Caddyfile PUBLIC-BOUNDARY
   allowlist in this PR. Anonymous visitors keep the settled bake; the live overlay
   paints for authenticated tiers per the existing tier-preview pattern. If product
   wants the live overlay public, that is a separate operator decision.
8. **Production proof (closes the wave, not the PR):** on production substrate, a real
   live source change flows source → `site/live/risk_envelope.json` on the VPS →
   browser overlay within the fast-lane cadence (fast lane fires every 60s; served
   file must reflect the change within ≤2 fires, browser within its poll interval).
   Record the four-clock latency receipt
   `event_time → observed_at → produced_at → browser_seen_at` with real timestamps in
   the wave record, plus proof the durable data tree is unchanged
   (`git status` clean on `data/` over the observation window; forward logs
   row-count-stable).

## Scope (owned paths this PR)

`scripts/build_live_risk_envelope.py` · `scripts/vps_live_orchestrator.py` (fast-lane
dispatch block only — model on the `scripts.build_risk_state` entry at `:303`) ·
`site/live/risk_envelope.json` (gitignored live artifact; nothing under `site/live/` is
committed) · band overlay JS/CSS via the existing band templates
(`templates/_risk_envelope_band.html.j2` / `_risk_envelope_band.css.j2`) and the
existing live consumer idiom (`templates/risk_state_live.js` is the reference consumer;
a new `templates/risk_envelope_live.js` is acceptable if it follows the same staleness
pattern and is added to the render/asset pipeline the same way) ·
`tests/test_live_risk_envelope*` folded into an existing wired suite `run:` step (a new
test file no `run:` step names reds `legacy-job-workflow-yaml`).

## Archaeology you inherit (verified on main 2026-08-20)

- Live plane transport: VPS systemd `macro-live-fast.timer` (60s) →
  `scripts/vps_live_orchestrator.py --lane fast`; the fast-lane dispatch imports sit at
  `:295`–`:303` (`build_live_overlay`, `build_risk_state`) — your builder joins that
  block. The orchestrator is executed per fire (timer-exec), so a new module is picked
  up on the next `macro-update` pull + fire; VERIFY on the box whether an
  orchestrator-file edit itself needs anything from `app/deploy/update.sh` (its restart
  regex does not cover `scripts/build_live_*`; the orchestrator-edit restart question
  is open — answer it with a receipt, don't assume).
- `site/live/` is GITIGNORED (`.gitignore:251`), so the 3-min `macro-update` pull never
  clobbers live artifacts — and nothing you write there can leak into a commit.
- Closest template: `scripts/build_risk_state.py` → `site/live/risk_state.json`
  (freshness fields, debounce `band_changed`/`pending`, atomic write, fcntl lock).
- Intraday-discard law: `engine/ledger_lane.py` `nightly_advance_enabled()` +
  per-module `ledger_lane_armed()` family. GD-4A just armed the CN/HK settled steps
  per-step — do not touch any arm.
- Consumer staleness idiom: `templates/live.js` (staleness classes) and
  `templates/risk_state_live.js` (the live risk widget already on the public asset
  allowlist).
- The settled artifact your overlay compares against: `site/riskdata/risk_envelope.json`
  (bundle id in the baked DOM binds page↔artifact; GD-2 Gate 8 receipts 2026-08-20).

## §0b Sol clarifications (2026-08-20, next-wave authorization — BINDING, additive to §0)

1. **No stage-ceiling promotion in GD-3.** Source competence is unchanged. With no
   promoted Grey Deer expert, current live sources may not originate `TRANSMITTING` or
   `BREAKDOWN`; raising any `SourceRead.stage_ceiling` is out of scope (test: the live
   builder's mapped reads carry ceilings identical to the settled builder's).
2. **One source-adapter authority.** Settled and live builders share the EXACT
   source-native mappings, requiredness, and stage ceilings. If the settled adapters
   live inside the settled builder, refactor them into a pure shared helper both
   builders import; never duplicate them (test: shared-helper identity, not copied
   tables).
3. **Raw reads only.** Do not consume `site/live/risk_state.json` `.display` (or any
   display-derived field) as evidence. Consume the raw live Market State / Risk Radar
   reads. Grey Deer owns its own pending presentation metadata — no double-debounce.
4. **Observed stage ≠ dwell state.** The pure composer produces the current descriptive
   candidate. A `live_transition` block may carry `candidate_stage`, `stable_stage`,
   `pending`, `ticks`, `needs`. Pending is visible immediately; neither field gains
   rank/gate/size/execute authority.
5. **Four clocks stay truthful.** Never substitute builder time for source event time;
   unknown clock → `null`/`UNKNOWN`. Every live envelope binds to the settled
   `bundle_id` it overlays.
6. **Precedence law.** Stale, future-dated, or older-than-settled live evidence loses
   overlay precedence and can never vote calm or loosen anything.
7. **No new quote owner, timer, scheduler, Caddy/public-boundary change, forward-ledger
   write, or policy authority** (re-affirms §0.3/§0.7 and the reject-if card).

Production acceptance remains §0.8 (Gate-8-equivalent): real live source change → VPS
live envelope within ≤2 fast fires → authenticated browser overlay, four-clock receipt
(`event_time → observed_at → produced_at → browser_seen_at`), plus proof `data/` and all
forward ledgers remained unchanged over the window.

## Non-goals / stop conditions

NOT in this PR: GD-6/GD-7 (Prophet sidecar / CN entry safety), GD-8A alerts, GD-8B
Terminal mirror, GD-9A Portfolio adapter, any GD-5 expert work (GD-5A/B/C remain CLOSED
— `DEC:GD1-ACCEPTED-NO-PROMOTION`; GD-1C ended BLOCKED_NO_PROMOTION), Portfolio cutover,
new model training, automatic exits, new quote streams, new schedulers/timers, new
monitoring planes, Caddyfile/public-boundary edits, forward-ledger writes.
**Reject-if (matrix card):** a new quote owner or scheduler appears — the PR is wrong,
return to Fable. If the live plane cannot express a state without violating the clock
law or the pure-composer law — STOP, return to Fable.

## Worktree law

Full checkout before touching `site/`/`templates/` paired assets:
`python3 scripts/worktree_sparse.py full`. If any paired plain-copy asset is touched,
`python -m scripts.check_template_site_sync --fix` in the same PR. Never `git add -A`
an unexpected `data/`/`site/` diff. `scripts/**` edits make the PR authority-changing —
verify main's latest ci baseline is green before merging.
