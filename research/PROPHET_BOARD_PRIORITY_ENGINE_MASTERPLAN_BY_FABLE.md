# Prophet Board Priority Engine — US parity + unified pick surface (masterplan by Fable)

Date: 2026-08-02 · Status: CHARTERED — operator-directed (2026-08-02 session: "figure out how we
can best sort picks, create robust engine for sorting picks… surface the best possible signal
picks to the top with Featured entries… US board first"). Program id: `prophet_board_priority`.
Siblings: `research/US_BOARD_MEASUREMENT.md` (the evidence), `engine/china_board_rank.py`
(cn_prophet_v2, the architecture precedent, PR #4029), `research/US_STOCKS_DASHBOARD_UX_HANDOFF_2026-07-29.md`
(page-IA program — NOT this program; see §7 scope fence).

---

## §0 ACCEPTANCE GATES (binding on every build lane — "not done unless")

- **G0.1 — US board renders in priority order.** us_stocks Prophet cards are ordered by
  `display_rank` from the new `us_prophet_v1` machinery: stage bucket first (Live → Setting up →
  Ran → Blocked), priority score desc within bucket. The old lane-partition heading order is
  replaced by stage-bucket headings; bottoming/continuation survives as a per-card chip. No card
  with `entry_signal.status ∈ {blocked, exit, avoid}` or label DOWNTREND may render above any
  `buy_now/partial` card.
- **G0.2 — Featured works on both boards.** US: featured rows = the CN-mirrored requirements
  (§3.4) with sector cap 4 / board cap 12, flagged `featured: true` + glow treatment; buy-lane
  MEMBERSHIP unchanged (featured is a flag + order, never a population change — DNR §1 row 49
  fence). CN: featured (6 today) and `more_actionable` (105) render in ONE grid, same full card
  idiom, featured glowing on top, score-ordered — the second-class "More live setups" compact
  list is deleted.
- **G0.3 — The software cohort is visible.** On the 2026-07-31 artifact fixture: the leaders
  lane v2 must contain ≥3 members of `ai_software`/`non_ai_software` baskets (MSFT/PLTR/APP/CRWD
  class — momentum-ranked, theme-boosted), and TEAM (fresh T1, IT-capped out of buy today) must
  surface on the board (buy or its stage bucket). A fixture-pinned test asserts the leaders lane
  is momentum-selected, not residual-alpha-selected.
- **G0.4 — Ran lane exists on US.** Names whose cross fired 3–15 sessions ago with intact trend
  (above200 ∧ weekly_bull ∧ dir≠down) render as muted "ran" rows with "+X% since signal ·
  fired Nd ago" — the CN `ran` idiom ported. MSFT-class names no longer vanish the day their
  cross stales.
- **G0.5 — Theme linkage.** Board/leader/ran cards carry a theme chip when the name belongs to a
  top-8 basket with reco ∈ {accumulate, enter} (from `data/baskets/latest.json` + membership).
  A "themes in favour" mini-strip above the board names the top themes and their on-board
  leaders. Display-tier context language only.
- **G0.6 — Filters + NEW on US.** Stage filter chips (All / Live now / Setting up / Ran — don't
  chase / Blocked) client-side like CN's; NEW badge when `signal.asof == as_of`.
- **G0.7 — Honest score framing.** The artifact `ranking` block mirrors CN:
  `score_kind: "transparent priority heuristic; not a calibrated return forecast"`, formula
  points disclosed, `zero_score_authority` listed. No "validated"/forecast language anywhere
  (CI: check_validated_claims).
- **G0.8 — Ledger continuity.** `rank_by`/`board_definition` stamped `us_prophet_v1`;
  grade_us_board keeps grading the FULL buy lane membership (unchanged rule); leaders keeps its
  forward cohort; `ran` joins LANES as a new forward cohort from ship date. No retroactive
  re-grading; definition change disclosed in artifact meta.
- **G0.9 — Visual proof in the PR.** Rendered screenshots (US + CN, light + dark, EN + ZH for
  the changed sections, desktop + 390px) posted in the PR body. Reduced-motion: glow static,
  no pulse.
- **G0.10 — Downstream suite green.** test_us_board_lanes / outcomes / w3_evidence /
  dashboard_template_render / china render tests updated to the new contract and passing;
  check_template_site_sync; check_title_i18n; check_validated_claims (templates AND rendered);
  contract registry version bump for us_standouts schema additions (leaders precedent #3933).

## §1 Evidence (measured 2026-08-02, artifacts as_of 2026-07-31)

1. **The buy lane is mis-ordered for actionability.** 71 rows sorted alpha-desc regardless of
   entry state: slot #1 = Macy's (band=low, "Extended — don't chase"), DOWNTREND/`avoid` rows
   (ORA, NXE) mid-board above `buy_now` rows. rank_by="confluence" is the lane partition +
   alpha; nothing encodes "can I act".
2. **US_BOARD_MEASUREMENT (§1–§5, Conf A):** published board order was ANTI-predictive at the
   top (P@1 0.20 vs 0.60 alpha-ordered; corr(position, excess)=+0.07; top-5 −13.7pts vs base);
   timing IC negative at every horizon ("risk placement, not return prediction"); ruling:
   **order by edge, gate by timing, never the reverse**. `reports/setup-score-phase0.md`
   confirms additive timing dilutes alpha (its blend was reverted).
3. **The software absence is structural, three-part.** (a) Freshness: the entire ai_software /
   non_ai_software leadership (MSFT ticks=4, CRM/ADBE/INTU/CRWD/APP=7, META/PLTR/NOW/WDAY=8,
   GOOGL=27, ORCL=40…) is gate-ineligible as stale crosses — the board catches the FIRST cross
   then deletes the name while the theme runs for weeks (archaeology: APP 1 day 07-08, PLTR
   1 day 07-14, MSFT 3 days 07-20..22, each never seen again). (b) Caps: TEAM is T1-fresh
   (ticks≤2) TODAY and invisible — IT sector cap + watch-slice cut. (c) The leaders lane
   (07-28) has held ZERO software names ever: `_select_leaders` ranks by residual (beta-stripped)
   alpha ≥0.5, which structurally erases a beta-heavy theme rally and selects idiosyncratic
   small-caps (Callaway Golf, Tompkins Financial) instead of market leadership.
4. **The theme engine already knows.** `data/baskets/latest.json` (nightly): ai_software rank 3,
   non_ai_software rank 4, both "dominant/accumulate", clean_entry=true, bull_days 3–5;
   membership + rationale in `data/baskets/membership.json` (47 curated baskets). Zero linkage
   into pick admission, scoring, or display.
5. **CN precedent (cn_prophet_v2, PR #4029):** transparent 100-pt priority score (signal 35 /
   entry 25 / runway 20 / bottom_quality 10 / reversal 10), featured requirements, lifecycle
   lanes (`more_actionable`, `late_or_unfillable`, `forming`, `ran`), definition-aware ledger.
   The architecture is proven in-house; the US lacks all of it.

## §2 Governance adjacency (cited; nothing here re-opens a kill)

| Registry row / ruling | Why this program is outside its fence |
|---|---|
| DNR §1 row 49 — Top-setups data merge / "single blended conviction×timing ranking" FORBIDDEN | No setups.json population enters the graded board; buy MEMBERSHIP rule byte-identical; featured = flag + order within buy. The priority score is CN-class display ordering ("priority heuristic", zero return-forecast claim), and within-stage ordering is EDGE-led per the measurement — not the killed conviction×timing return-blend. |
| Phase-0 timing-blend null (`reports/setup-score-phase0.md`) | Honoured, not re-opened: timing decides stage GROUPING (eligibility class), alpha decides order within stage. No claim that the blend ranks returns. |
| Mag-7 forced-call kill (row 117) | Leaders v2 is engine-derived (momentum + structure gates + theme boost from the nightly baskets engine), display-tier, stance "watch — don't chase", forward-graded. No operator-pinned directional call. Mag-7 names may appear only by passing the same engine rules ("plain data display… allocation's own 200d-gated sleeve stays lawful"). |
| Ignition Radar suspension (row 149) | No "igniting/#N theme" claims. Theme chips restate the existing baskets board's reco (its own governed surface) as per-card context. |
| PSF Stage-2 ranking-bonus kill (row 113) | No Stage/EC term anywhere in the score. |
| PTT-W1a outcome-audition kill (row 69) | No per-name fitted anything; all constants frozen at definition time. |
| CN standout masterplan R-2 ("display ships, rank is gated") | US rank change is not un-evidenced: US_BOARD_MEASUREMENT Conf-A knob table + operator directive 2026-08-02. Disclosure via rank_by/board_definition stamp + ranking block; forward ledger continues unbroken (G0.8). |

## §3 Design — `engine/us_board_rank.py` (us_prophet_v1)

Mirror `china_board_rank.py`'s shape: frozen constants, pure functions, artifact `ranking`
block. US-specific evidence differences are deliberate and documented in-module:

### 3.1 Stage buckets (timing = grouping authority, the WHEN-gate)
- `live`: entry_signal.status ∈ {buy_now, partial, buy_soon}
- `setting_up`: {await_confluence, bounce_wait, watch}
- `ran`: {extended, topping, hold} ∪ the ran-lane rows (§3.5)
- `blocked`: {blocked, exit, avoid} or label DOWNTREND
Chip labels (EN/ZH): Live now/现在可操作 · Setting up/形成中 · Ran — don't chase/已启动 — 勿追 ·
Blocked/受阻 · All/全部.

### 3.2 Priority score (100 pts, display order within stage; artifact-disclosed)
- `entry` 25 — CN's `_ENTRY_VALUE` map verbatim (statuses shared).
- `signal` 30 — tier base {T2:1.0, T1:0.9, T3:0.7} × freshness decay (ticks==2 → ×0.85;
  provisional −0.1) — CN's `_signal_value` with the same frozen constants.
- `edge` 25 — **US-specific: residual-alpha percentile within the current eligible pool**,
  clip01((pctile−0.25)/0.75) so bottom-quartile alpha earns 0. Basis: the ONLY positive-IC leg
  (measurement §3); conviction/composite_z has ZERO score authority (measured anti-predictive).
- `runway` 10 — 1−clip01(ext) where ext = extension evidence (ext_z scaled /
  antichase_shadow_blocked → 0); unknown extension earns 0 (CN's fail-closed rule).
- `quality` 10 — coiled star 1.0 / coiled 0.8 / washout ctx 0.4 (CN `_bottom_quality_value`).
`zero_score_authority`: conviction_composite, setup, sector_turn, narrative, quality(factor),
low_vol, risk_sizing, smartmoney, insider, SUE, options/GEX, theme (chips are context, never
points — Ignition fence).
Sort key: (stage_order, −score, ticker). `score_rank` = pool rank, `display_rank` = rendered.

### 3.3 NEW badge
`new: true` iff signal.asof == board as_of. ZH 新.

### 3.4 Featured (the glow; flag within buy, cap 12, sector cap 4)
ALL of: stage live (buy_now/partial only — buy_soon excluded), tier ∈ {T1,T2,T3}, ticks ≤ 2,
not provisional, no antichase/extension block, alpha ≥ 0 (edge floor, measurement §5),
earnings blackout clear, sector cap 4, board cap 12 by score. Fewer than 12 qualifying renders
fewer — honest emptiness (UX handoff §5.4).

### 3.5 Leaders v2 + Ran lane (the software fix; display-tier, forward-graded)
- **Leaders v2** (replaces `_select_leaders` body; same artifact key): universe = full scored
  pool; gates above200 ∧ weekly_bull ∧ dir≠down + liquidity/price sanity; rank by the composite
  **momentum leg z** (total momentum, NOT residual alpha) desc; **theme boost** +0.5 when member
  of a top-8 in-favour basket (§3.6); soft near-high preference; alpha as tiebreak only;
  cap 15; dual-class dedup; stance copy unchanged ("watch — don't chase"). Expected on the
  07-31 fixture: MSFT/PLTR/APP/CRWD-class names enter; Callaway-class residual freaks drop.
- **Ran lane** (new artifact key `ran`, CN idiom): verdict.eligible==False ∧ ticks ∈ [3,15] ∧
  above200 ∧ weekly_bull ∧ dir≠down; carries `pct_since` (close vs close at cross), `ticks`;
  ordered ticks asc then pct_since desc; cap 12. Copy: "signal fired {n}d ago · +{x}% since —
  wait for the next entry" / 「信号{n}天前触发 · 此后+{x}% — 等待下一个入场点」.
- Both graded forward: grade_us_board LANES += `ran` (leaders already in from #3929).

### 3.6 Theme linkage (context chips, zero score authority)
Loader reads `data/baskets/latest.json` + `membership.json` at build: top-8 themes by rank with
reco ∈ {accumulate, enter} → ticker→{id, name, name_zh, rank, reco, bull_days, clean_entry} map
(first/highest-ranked theme wins; sector-ETF pseudo-baskets `us_sector_*` excluded — GICS is
already on the card). Stamp `theme` onto every board/leaders/ran row. Board header mini-strip:
top-3 themes + their on-board tickers. Fail-soft: file absent → no chips (never a build failure).

### 3.7 Theme-confirmed re-arm (display-tier; the front-running surface)
Operationalizes `US_STOCKS_FRONTRUN_AND_FEEDER_INTEGRATION_AUDIT_FOR_FABLE.md` Cluster D
(sector-clock vs stock-clock desync) without touching admission: ran/leaders rows whose theme
has `bull_days ≤ 7` get `theme_confirmed: true` — "the name's cross staled while its theme was
still unconfirmed; the theme has NOW confirmed". Ran lane orders theme_confirmed first, then
ticks asc. Copy: "Theme just confirmed — watch for the next entry / 主题刚确认 — 关注下一个买点".
No score authority, no gate change; full re-arm-as-admission stays a chartered follow-up
(pick-lab book candidate + prereg — see §8).

### 3.8 Score display slot
CN precedent (china.html.j2 ~L3337): when `row.prophet.score` exists, the pv_card number slot
shows **Priority** (0–100) with the honest formula tooltip; legacy `score_edge` "Edge" display
is the fail-soft for old artifacts. Legacy fields (alpha, score_edge, score_timing) stay
emitted — downstream consumers read them.

## §4 CN board (china.html.j2 mode=stocks) — presentation unification

Engine (`china_board_rank`) untouched. Template: featured + more_actionable render as ONE
score-ordered grid (featured first, glow), full card idiom for every row (compact second-class
list deleted); `late_or_unfillable`/`forming`/`watch`/`ripening` stay behind the existing filter
chips; lane_counts row intact; NEW badges intact. CN lane vocab maps to the same stage-filter
contract as US (featured+more_actionable=live, forming/ripening=setting_up, late_or_unfillable=
ran, watch=too early) so both boards speak one filter language.

## §5 Measurement & ledger wiring

- `rank_by`/`board_definition` = `us_prophet_v1`; meta discloses the definition date; ledger
  keeps accruing on unchanged membership (order-sensitive stats P@k become definition-aware
  exactly as the existing `rank_by` history requires).
- LANES += ran (forward cohort from ship date, `LEDGER_FLOOR` note in grader).
- Nightly forward record is the promotion path for any future claim ("featured beats board
  average" etc.) — NO such claim ships now.

## §6 Build lanes (this session, one PR)

1. **ENGINE (builder/Opus):** engine/us_board_rank.py + build_stock_library wiring (score/stage/
   featured/new/theme stamps, leaders v2, ran lane) + grade_us_board LANES + contract version +
   tests (fixture-pinned G0.3 assertion; existing lane tests updated). CN engine: none.
2. **US UI (designer/Opus):** dashboard.html.j2 Prophet section — stage-bucket headings +
   score order, filter chips, featured glow, NEW badge, theme chips + mini-strip, ran/leaders
   presentation. Owns shared files (_prophet_card.html.j2, _stock_decision.css.j2, theme.css/js)
   if touched.
3. **CN UI (designer/Opus):** china.html.j2 stocks-mode unified grid + glow + full-card
   more_actionable. May NOT touch shared files (de-conflict rule).
4. **VERIFY (reviewer/Opus + main loop):** §0 gates, downstream suite, screenshots, adversarial
   review of engine math.

## §7 Scope fences

- **Buy Board 2.0 coexistence.** `scripts/build_stock_board_v2.py` (shadow us_standouts_v2 +
  us_stocks_v2.html + `_v2` ledgers) is a separate running program with its own flip-to-live
  charter (precision@k vs the live board). This program does not touch it; the shadow keeps
  accruing against the new live ordering (its baseline updates automatically via the graders).
  Neither program blocks the other.

- The 07-29 UX handoff's page-IA teardown (command header, change digest, drawers, count
  reconciliation) is NOT this program — its §24 forbade ranking changes; today's operator order
  supersedes that for ranking only. Don't start the IA rebuild here.
- prophet plans index / prophet_bridge intake: untouched (chips continue reading the artifacts).
- prophet_bridge: one-line tie-key hardening so intake is provably order-invariant; selection rule
  otherwise untouched.
- HK/Canada: explicitly out of scope this session (operator: "after US board has reached
  complete perfection"); the rank module is written market-parameterizable for that follow-on.
- No admission-gate loosening (FRESH_TICKS, signal_gate) — US_BOARD_MEASUREMENT §5 keeps the
  window tight; visibility of stale winners comes from the ran lane, not gate widening.

## §8 Chartered follow-ups (registered here, NOT built this session)

1. **Theme-confirmed re-arm as admission** — when a theme newly confirms (bull_days ≤ K,
   clean_entry), re-open a constituent's entry window if its cross fired within N sessions.
   The frontrun audit's Cluster-D fix at authority tier. Path: pick-lab book (display-only
   forward ledger) → prereg → gauntlet. §3.7's display chip is the measurement-free precursor.
2. **US ripening machinery** — port `engine/setup_tier.assign_stage/assign_ripening_zone` to
   the US builder so the setting_up bucket gains CN's imminence evidence (W1/W2 cross distance);
   today's US proxy is entry statuses only.
3. **HK/Canada parity** — apply us_board_rank (market-parameterized) + the unified board UI to
   hk_standouts/canada_standouts once the US ships and survives a week of nightlies.
4. **Leading tailwind** — replace the 20d trailing relative-return tailwind leg with the
   leading components (accel, Improving-quadrant, coiled cohort) — frontrun audit Cluster B;
   needs its own evidence loop before touching composite weights.
