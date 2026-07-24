# Marketing — Autonomous Posting Cadence Masterplan

**Status:** Design, scaffolded 2026-07-24 (operator-directed). Buildable now; stays DARK behind the existing kill-switch until the operator arms it. Extends — does not duplicate — `MARKETING_REALTIME_FASTLANE_ARCHITECTURE_BY_FABLE.md` (the breaking-event *detection→publish mechanism*) and docket `D02_X_ACTUATION_COMPUTER_CONTROL.md`. This doc owns the **cadence policy** (when things post), not the detection plumbing.

Author: main-loop (Opus). Operator decisions captured live in the 2026-07-24 session.

---

## §0 — ACCEPTANCE GATES (a build is NOT done unless every box is true)

1. **Dark by default.** Nothing posts to X unless `MARKETING_PUBLISH_ENABLED == '1'` (existing kill-switch VARIABLE) AND `BUFFER_TOKEN` is set. Autonomy (auto-approve) sits behind its own separate flag, default off. Turning either on is an operator action, never a code default.
2. **10-minute global floor is provable.** A test shows: two due items where the last post was <10 min ago → the second is deferred to `last_post + 10 min`, never posts inside the window. This holds across signal↔signal, signal↔breaking, breaking↔breaking.
3. **Unlimited daily volume is provable.** A test shows ≥6 approved+due items in one day all clear the cadence-cap gate (no `cadence_cap_daily` quarantine), i.e. the 2/day floor is lifted.
4. **Links stay gated for the warm-up window.** A test shows a link-bearing post is quarantined while the account is inside the 2-week link-gate, and passes after. (The 10-min floor + link gate are the two anti-spam guards that survive the unlimited-cap change.)
5. **Signal ladder lands on Pacific clock slots.** A test shows an approved signal post is scheduled to the next 4 AM–6 PM Pacific / 2-hour slot, with the Pacific→UTC conversion correct across DST.
6. **Breaking budges in, respecting the floor.** A test shows a breaking item posts immediately when clear, or at `last_post + 10 min` when something posted recently, and does NOT re-anchor the signal ladder by 2 h (superseded design — see §3).
7. **Existing marketing tests stay green** (`test_marketing_outbox`, `test_marketing_social_publisher`, `test_marketing_publisher_autoapprove`, `test_marketing_sentinel`, `test_marketing_fastlane`, `test_marketing_publish_time_content`, …). No safety gate (Sentinel policy, tape gate, near-dup, cashtag breadth, advice lexicon, disclosure) is weakened.
8. **No self-merge on first pass.** The build ships as a PR with the test evidence in the body; it waits for operator/orchestrator review before merge.

---

## §1 — Decisions locked (operator, 2026-07-24)

| # | Decision | Value |
|---|---|---|
| D1 | Daily post cap | **Unlimited** (lift the `max_posts_per_account_per_day: 2` new-account floor) |
| D2 | Signal-post cadence | **2-hour ladder**, 4 AM → 6 PM **Pacific**, every 2 h → **8 slots/day** (assumption: keep all 8; operator earlier said "7" — see §10 Q3) |
| D3 | Breaking/news posts | Fire **live** on arrival (event-driven), subject only to the floor below |
| D4 | Global anti-spam floor | **No two posts within 10 minutes.** Anything due inside the window defers to `last_post + 10 min`. Max burst ≈ 6 posts/hour. This is the operator's chosen spam-avoidance mechanism. |
| D5 | Links | **Gated for the first 2 weeks**, then open (links on a cold account are a documented X suspension trigger — kept even under "unlimited") |
| D6 | Budging | A breaking post costs **10 min** of spacing, NOT a 2-hour re-anchor of the ladder (supersedes the earlier "push scheduled back 2 h" idea) |
| D7 | Autonomy | Not day-one. Run **supervised (approve-each) ~2 weeks**, then graduate auto-approval **by content-kind** |

---

## §2 — Current-state findings (what is ACTUALLY enforced today)

Grounded in the code as of 2026-07-24 — these correct two assumptions the design leaned on:

- **F1 — The ramp table is decorative.** `config/marketing.yml` has a `ramp:` block (weeks_1_2 → weeks_3_4 → week_5_plus, stepping caps 2→3→4/day and opening links at week 5). **There is no account-age selector anywhere** — the actuator has no tier-picking code; the comment "D02 actuator RAISES caps by ramp tier" describes intent, not built behavior. Only the **base** caps are enforced (`sentinel.py:_DEFAULT_MAX_POSTS_PER_ACCOUNT_PER_DAY = 2`, `links_allowed: false`, `max_media_posts…: 1`). **Consequence:** "gate links 2 weeks then auto-open" needs a *mechanism* — it will not happen on its own (§6, §10 Q1).
- **F2 — Posting cadence is 3 Actions cron slots**, not a scheduler: `marketing-publish.yml` fires at 14:00 / 17:30 / 20:15 UTC weekdays. The only publish path to X. Slots are labels `D<n>-{AM|PM|EOD}` → times via `outbox.slot_datetime()` / `_SLOT_SUFFIX_TIMES` (`AM=T14:00Z, PM=T17:30Z, EOD=T20:15Z`). Content Studio generates labels in `_slot_labels()` (3/day). **The 8-slot 2 h ladder replaces this AM/PM/EOD triple.**
- **F3 — Buffer has no "post now" mode.** `social_publisher.create_post` uses `mode: customScheduled` (with `dueAt`) for timed items and `mode: addToQueue` for immediate ones. `addToQueue` parks a "breaking" post in *Buffer's own* queue, adding latency. For true immediacy, immediate items must use `customScheduled` with `dueAt = now`.
- **F4 — The daily cap is a hard Sentinel gate.** `cadence_cap_daily` quarantines posts past `max_posts_per_account_per_day` (via `sentinel.py:_cap`). Lifting to unlimited means the cap logic must accept a "no limit" sentinel and short-circuit that gate.
- **F5 — Publisher already has the primitives we need:** `_is_due`, `_is_immediate`, `_select_approved_due`, the auto-approve pass, and per-item `scheduled_at`. The build extends these; it does not rebuild the pipeline.

---

## §3 — The cadence policy (the design)

**Two streams, one hard timing law.**

**Stream A — Signal / scheduled posts** (signals, movers, themes): scheduled onto the **2-hour Pacific ladder** (§5). Each approved signal takes the next open slot; overflow rolls to the next day's ladder, and the tape gate drops any that have gone stale.

**Stream B — News / breaking posts** (earnings, political, market-moving headlines): fire **live** the moment they clear the content gates (Sentinel policy + tape verify), via the fast-lane mechanism in the realtime architecture doc.

**The one hard timing law — 10-minute global floor (D4):** the publisher never posts within 10 minutes of the last post. Anything due (either stream) inside the window is deferred to `last_post + 10 min`. Signals are 2 h apart so they rarely trip it; it exists to pace breaking bursts and smooth signal↔breaking collisions. A 5-tweet storm posts at 0, +10, +20 … with near-dup dedup collapsing near-identical ones.

**Budging (D6):** breaking does **not** re-anchor the ladder by 2 h. It slots into the gaps under the 10-min floor. Net cost of one breaking post to the schedule ≈ 10 minutes, not two hours. (This supersedes the earlier "reset the 2-hour countdown" model; the operator chose the simpler, more lenient floor.)

---

## §4 — Config changes (`config/marketing.yml`)

- `max_posts_per_account_per_day: 2` → **unlimited sentinel** (proposed: `null`; `_cap()` and the `cadence_cap_daily` check treat `null`/absent as "no limit"). Mirror in `ramp:` tiers so a future age-selector can't silently re-cap.
- Keep `min_minutes_between_posts: 120` as the **signal ladder cadence**.
- Add `min_minutes_between_any_posts: 10` — the **hard global floor** the publisher enforces at post time for every item (D4).
- `links_allowed: false` stays for the gate window; opened by the §6 mechanism after 2 weeks (D5).
- Leave intact (content-safety, not volume): `near_dup_jaccard`, `max_cashtags_per_post`, `lexicon_phrases/patterns`, `max_receipt_age_days`, disclosure. **`max_media_posts_per_account_per_day`** may rise (operator: lift media) — proposed `null`/high.

---

## §5 — Signal ladder (Pacific → UTC, DST-safe)

Slots defined in **Pacific local time**, converted per-date with `zoneinfo("America/Los_Angeles")` (never hardcode a UTC offset — DST would drift the whole ladder by an hour twice a year).

| Pacific | UTC (PDT, summer) | UTC (PST, winter) |
|---|---|---|
| 4 AM | 11:00 | 12:00 |
| 6 AM | 13:00 | 14:00 |
| 8 AM | 15:00 | 16:00 |
| 10 AM | 17:00 | 18:00 |
| 12 PM | 19:00 | 20:00 |
| 2 PM | 21:00 | 22:00 |
| 4 PM | 23:00 | 00:00 (+1) |
| 6 PM | 01:00 (+1) | 02:00 (+1) |

Build: replace the AM/PM/EOD triple in `content_studio._slot_labels()` + `outbox._SLOT_SUFFIX_TIMES`/`slot_datetime()` with a clock ladder (labels e.g. `D1-S1..S8`, resolved through zoneinfo). Every-day (7 days/week) — weekend signal content is thinner, so weekends naturally post fewer items; breaking still fires.

---

## §6 — Publisher & breaking changes

- **10-min floor:** in `marketing_publisher`, before posting a due item, read the last post's timestamp (publications ledger / status ledger) and, if `< min_minutes_between_any_posts`, defer (leave queued for the next run, or set `scheduled_at = last + 10min`). Enforced for BOTH streams — this is the single choke point.
- **Buffer share-now (F3):** immediate items → `customScheduled` with `dueAt = now` instead of `addToQueue`, so a breaking post leaves Buffer immediately.
- **Breaking dispatch:** earnings auto-detected by the fast-lane daemon (exists) → gates → immediate post (dispatch publisher now, **skip the 0–10 min humanizing jitter** for immediate items, Buffer share-now, 10-min floor). Non-earnings breaking → operator **"Post now"** button in the admin (Outbox/Publisher panel) → same immediate path (admin already has `github_api.dispatch`). Assumption — see §10 Q2.
- **Links gate mechanism (F1):** simplest correct option = keep `links_allowed: false` now; operator flips it (config or an admin toggle) at the ~2-week graduation, which they're already reviewing. Optional nicety: a `links_open_date` that auto-flips. NOT the decorative ramp — that does nothing today.
- **Publisher cadence:** signals need the publisher to run more than 3×/day. Move `marketing-publish.yml` to a frequent sweep (~every 15 min) that posts due ladder items; breaking stays **event-driven dispatch** (Actions cron is too laggy for "live"). Cost: cheap no-op runs when nothing is due.

---

## §7 — Kill-switch & autonomy staging

- **Phase 0 (now):** arm the publisher (kill-switch on, token set) but keep **approve-each**. Ladder + 10-min floor + breaking path all active; every post still needs an operator yes. This is the 2-week supervised window.
- **Graduation gate (end of ~2 weeks):** flip auto-approve ON for low-risk kinds **only if** (a) operator override rate on the system's recommendations ≈ 0, (b) no gate-escaped embarrassment (wrong number, advice phrasing, a signal that reversed right after posting), (c) the tape gate is catching what it should. Log the system's would-auto-approve verdict next to each item during Phase 0 so this is measured, not vibes.
- **Phase 1:** auto-approve low-risk kinds (scheduled movers/themes/market-tone); open links.
- **Phase 2:** broaden to more kinds; single-name price-target signals and political hot-takes stay manual or on a lighter glance-gate longest.
- Autonomy behind its own flag (e.g. `MARKETING_AUTONOMOUS` / config), separate from the posting kill-switch.

---

## §8 — Phased build plan (each phase = its own verified unit; dark throughout)

1. **Config + Sentinel cap** — unlimited-cap sentinel, `min_minutes_between_any_posts: 10`, media lift; `_cap`/`cadence_cap_daily` honor "no limit". Tests: gates 3–6 (cap) + config load.
2. **Signal ladder** — Pacific clock slots in content_studio + outbox, zoneinfo/DST. Tests: gate 5.
3. **Publisher floor + Buffer share-now** — 10-min floor enforcement, immediate→customScheduled dueAt=now. Tests: gates 2, 6.
4. **Breaking dispatch** — fast-lane immediate hook + admin "Post now" + skip-jitter for immediate; workflow_dispatch wiring. Tests: gate 6 + dispatch.
5. **Cadence + autonomy flag** — publisher cron → frequent sweep; `MARKETING_AUTONOMOUS` flag + would-auto-approve logging; runbook update. Tests: autoapprove-shadow.

---

## §10 — Open assumptions (proceeding on these defaults unless corrected)

- **Q1 — Links-gate mechanism:** operator manually flips `links_allowed` at ~2 weeks (default), vs building a `links_open_date` auto-flip. *Default: manual flip* (operator is reviewing at graduation anyway; no age-wiring exists to lean on).
- **Q2 — Breaking sources:** earnings auto-detected (fast-lane); everything else (political/headlines) is an operator "Post now" button for now, with a headline detector added later. *Default: as stated.*
- **Q3 — Ladder count:** 8 slots (4 AM–6 PM inclusive) vs 7 (operator said "7" once). *Default: 8.*
- **Q4 — New-account risk (honest flag):** going unlimited on a cold account is the one place "X doesn't punish over-posting" has an exception; the 10-min floor + 2-week link gate mitigate most of it, and the supervised window is a natural warm-up. Not blocking — just the residual risk the operator is accepting.
