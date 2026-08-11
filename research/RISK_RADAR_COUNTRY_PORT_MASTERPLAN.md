# Risk Radar Country Port — CN · HK · CA (+ international card)

Status: **BUILDING** (operator order 2026-08-11, this session). Owner session: risk-radar-macro-styling.
Program note: radar core is unmapped in `config/mastermind_programs.yml` (nearest: `market-regime-risk`;
`hk-canada` is an explicitly unresolved split label). This build proceeds under direct operator order;
ownership mapping is flagged, not forced, here.

**One sentence:** surface the already-built, already-graded `engine/risk_radar_intl.py` per-market radar
as a full US-style Risk Radar dialog on china/hk/canada (design cloned from `#dlg-risk` on macro.html),
plus the compact shared `.rrx` card on the five international dashboards — display-tier only, no new
model authority, no new data ingestion.

---

## §0 ACCEPTANCE GATES (not done unless)

1. **macro.html popover de-dim:** opening `#mx5PopFactors` (the "N of M supportive · K warning" chip)
   no longer dims the page — `.mx5-popover-backdrop` stays as an invisible click-away layer only — and
   the popover's shadow is a light house-normal elevation, not `0 24px 64px rgba(0,0,0,.72)`. Click-away
   and Esc still close it. The eleven `.mx5-dlg` modals' backdrop is untouched.
2. **Full radar dialog on all three country pages:** pressing the existing pullback-risk entry points on
   china/hk/canada opens a full-height Risk Radar dialog visually matching the US `#dlg-risk` idiom
   (header ladder + `.rrx` card + odds + tile grid + country factor block + leaders + FX + footer).
   The old thin `#cnx/#hkx/#cax-dlg-risk` bodies are superseded, and **none of China's extra content is
   lost**: recession + slowdown gauges and the FX-context block live inside the new dialog (this
   supersedes the 2026-07-21 hand-roll ruling at `templates/china.html.j2:2024-2032` by *including* the
   CN gauges the shared card lacked — update that comment in place).
3. **Per-country factor blocks render from existing stores only** (§3 table). A missing store renders an
   honest plain-word absence ("coverage building" / nothing), never a blank error and never blocks render.
4. **Copy law:** Tier-1 copy passes `docs/DESIGN_DOCTRINE.md` §5 — stance words present, no banned
   vocabulary, numbers arrive with meaning, ONE as-of + ONE merged footnote per surface. No falsifier
   vocabulary anywhere front-facing (no "falsifier / refuted / 证伪"); the word "validated" appears
   nowhere in emitted copy (CI-guarded). zh copy is zh-shaped (not transliterated English), and risk
   coloring uses only the zh-flipping `--down/--warn/--up` family — never literal hexes.
5. **No authority creep:** the gross chip displays `gross_factor` exactly as the engine emits it; no new
   composite numbers, no calendar-GATED legs (`DNR:KILL-CALENDAR-GATED-RISK` — calendar content is
   display-only listing), no forward-ledger writes committed (local render side-effects under `data/`
   are restored before commit; `git status` clean of data/ churn).
6. **Verified, not asserted:** all four country pages + macro.html rebuilt locally from real `data/`;
   playwright screenshots of each new dialog open, in **light + dark + zh**, saved and posted in the PR
   body; targeted tests green (`check_validated_claims`, template/i18n suites that cover touched files).
7. **Intl card:** the five international dashboards (JP/KR/EZ/UK/IN) show the compact `.rrx` radar card
   fed by their existing nightly `risk_radar_intl` snapshots; absent-safe when a market's snapshot is
   missing.
8. **Ship loop:** commit → push → PR (screenshots inline) → `merge-on-green` armed → live verification
   owned by the shared render lane.

## §1 What already exists (verified 2026-08-11)

- Engine: `engine/risk_radar_intl.py` — `RadarProfile` dataclass, 10 profiles (`cn hk ca kr jp tw in au
  gb ez`), `snapshot()` → `risk_radar_intl.v1` (state, top_score, scares[], drawdown_prob h5/h10/h21,
  trajectory, gross_factor, context_gate, caveat_en/zh). CN composite lift 2.07× (p=0.01), HK ~1.5×,
  CA ~1.4–1.6× (`research/CHINA_ENGINE_REASSESSMENT.md:99`, `research/INTL_FIX_MASTERPLAN.md`).
- Display transform: `engine/market_state.py:578 _radar_to_rd()` already normalizes US and intl engines
  into one `rd` shape; every country builder already calls `market_state_snapshot(..., profile=…)`.
- Shared card: `templates/_risk_radar_card.html.j2` (.rrx) + its CSS already included on all four country
  pages via `templates/_market_state.css.j2:40`; markup invoked today only by `dashboard.html.j2:11993`.
- US full modal: `templates/dashboard.html.j2:11938-12879` (`#dlg-risk`) — design source of truth.
- Bespoke thin dialogs to supersede: `templates/china.html.j2:2401-2474` (`#cnx-dlg-risk`, has CN gauges
  + FX), `templates/hk.html.j2:2696-2750` (`#hkx-dlg-risk`, FX), `templates/canada.html.j2:1765-1794`
  (`#cax-dlg-risk`, thin; hardcoded "HIGH" pill at :1514).
- Overseas pressure: `data/contagion_links/latest.json["pressure"]` carries ALL 11 market keys (verified).
- Track record: `site/riskdata/scorecard.json` `markets` per-market sections (feeds the
  `risk_radar_reliability` lobe summarizer, `engine/neuralweb/mastermind_context.py:1082`).
- Forward ledgers per market accruing, display-only until `can_force` (≥30 graded, ≥8 alerts, lift
  ≥1.25×) — `research/INTL_FIX_MASTERPLAN.md:39`.
- Popover defect: backdrop `templates/dashboard.html.j2:2053` + CSS `:4492-4496` (rgba(0,0,0,.32) dim,
  z-90); deep shadow `:4505`; mechanism unique to `#mx5PopFactors` (grep-verified).

## §2 Architecture

One new shared partial pair, cloned from the US modal's design (not from scratch):

- `templates/_risk_radar_dlg.html.j2` — Jinja macro `risk_radar_dlg(mkt, rd, scares, ctx)` where `ctx`
  is a dict of optional per-market payloads (tiles, policy chips, country block, leaders, fx, gauges).
  Every section is conditional on its payload — absent-safe by construction.
- `templates/_risk_radar_dlg.css.j2` — included from `templates/_market_state.css.j2` (single include
  point already shared by all four pages). Class prefix `rrd-` (new, page-neutral); reuse `.rrx` tokens
  and the zh color-flip pattern (`theme.css` `html[data-lang="zh"] .rrx` precedent).
- The US `#dlg-risk` is NOT rewritten this pass (risk containment). Countries get the same look via the
  partial; US convergence is a follow-up.
- Entry points: each page's existing chips/cards/popovers retarget to open the new dialog; page-local
  dialog open/close JS conventions reused (`cnxOpenDlg`-style helpers or shared minimal JS in the
  partial — builder's call, one mechanism per page, Esc + backdrop-click close).
- View-model: assembled in each `scripts/build_<country>.py` as a plain `radar_dlg` dict on the existing
  view-model (no new engine modules; render-time reads of existing stores only, mirroring how
  `build_site.py:5526-5562` attaches contagion/cross-asset to the US radar).

## §3 Per-country content (the adjudicated factor map)

Shared spine, all markets: headline ladder (top scare label + intensity /100 + plain what-to-do) →
`.rrx` card (state pill, scares, amplifier, gross chip, 5/10/21-session pullback odds vs normal) →
tile row → context chips → country factor block → leaders → FX context → merged footer
(profile `caveat_en/zh` + "windows, not certainties — re-drawn nightly" + one as-of).

| Section | China | Hong Kong | Canada |
|---|---|---|---|
| Leading tile | SSE vs 200d stretch + top leg | HSI vs 200d + top leg | TSX vs 200d + top leg |
| Overseas tile | `pressure.cn` | `pressure.hk` | `pressure.ca` |
| Track-record tile | `scorecard.markets.cn` | `.hk` | `.ca` |
| Calendar tile | next high-impact events, display-only (`engine/china_event_calendar.py`) | same (`engine/hk_event_calendar.py`) | omit v1 (no calendar engine) |
| Correlation tile | omit v1 (store is US-centric) | omit v1 | omit v1 |
| Policy context chips | PBoC stance (exists, `china.html.j2:2179` source) + USDCNH | Peg distance (existing gauge) + HIBOR direction | BoC stance (exists, `canada.html.j2:1656` source) + USDCAD |
| Country factor block | recession + slowdown gauges (ported from cnx dialog); margin-to-mcap; QVIX level; southbound 5d flow; limit-up micro froth (count · sealed rate · 2+ streaks) — all from `engine/china_participation.py` / `china_microstructure.py` stores | VHSI level/trend; southbound holdings trend; CBBC turnover note; explicit plain-word breadth caveat (profile has no breadth history — say so) | commodities complex: WTI · gold · copper/gold + terms-of-trade tag (`engine/canada_overlay.py`); breadth participation line |
| Leaders block | standout-board top names (existing `china_standout_track` ledger) + the micro froth line as the "leader heat" read | `hk_board_rank`/`hk_leadership` top cohort + southbound concentration | "coverage building" plain-word line (no leaders ledger yet — honest absence) |
| FX context block | exists (`lib/forex_link.attach_fx_context`, wired) | exists (wired) | **wire now**: mirror `build_china.py:1092-1103` for USDCAD |

Numbers ship with meaning (Law 3): each factor row = plain label + value + one-word read (e.g. "high /
building / calm"), receipts and mechanics demoted to `data-tip-en/zh` hovers.

## §4 Copy pins (Tier 1)

Reuse-first: before minting any string, grep for an existing EN/ZH twin (`.rrx` card, cnx/hkx/cax
dialogs, `engine/i18n.py` LEX). New-string pins (EN → zh, zh-shaped):
Pullback odds → 回调概率 · Policy stance → 政策取向 · Margin balance → 两融余额 ·
Limit-up breadth → 涨停梯队 · Southbound flow → 南向资金 · Peg distance → 联汇偏离 ·
Commodities tailwind/headwind → 大宗商品顺风/逆风 · Leaders → 龙头 · Track record → 往绩 ·
Coverage building → 数据积累中 · Windows, not certainties — re-drawn nightly → 是概率窗口而非定论——每晚重算.
Stance vocabulary only (Act / Get ready / Watch — don't chase / Protect gains / Stand aside / Ignore);
what-to-do lines come from the engine's `do_en/do_zh` untouched.

## §5 Waves

- **W1 (opus builder):** popover de-dim + shadow fix; create `_risk_radar_dlg.html.j2/.css.j2`; wire
  China (view-model + template + entry retarget + comment supersession); local render; screenshots.
- **W2 (opus builder):** wire HK + Canada (incl. CA `attach_fx_context`); kill the hardcoded "HIGH"
  pill (severity from state like CN/HK); local render; screenshots.
- **W3 (opus builder):** intl card on `templates/international_macro.html.j2` for JP/KR/EZ/UK/IN —
  extend what `engine/intl_run.py` persists per market to the full `rd` display shape (or transform at
  build in `scripts/build_international_macro.py`); absent-safe; local render; screenshots. Docs: this
  file → SHIPPED state; note in `docs/MASTERMIND_SYSTEM_MAP.md` only if trivially safe.
- **W4 (opus reviewer):** adversarial pass of the full diff against §0 gates + doctrine §5 checklist +
  zh parity + light-mode parity + no-authority-creep; findings fixed before ship.
- Ship: single PR, screenshots inline, `merge-on-green` armed.

## §6 Lobe + governance

The neuralweb layer is already multi-market: `risk_radar_reliability` summarizer distils
`site/riskdata/scorecard.json` per market; grading closure registers `risk_radar_intl_{cn,hk,ca,…}`
(`scripts/audit_grading_closure.py:196-290`). This build adds **no lobe code** — it surfaces the same
artifacts. Standing law kept verbatim: display/context only; no LLM, no model scores, no signal
origination in this lobe (`mastermind_context.py:170-172`, constitution A7).

## §7 Future (recorded, NOT chartered)

Operator direction 2026-08-11: eventually give the radar lobe LLM access and persistent per-market
state so it becomes context/plane-aware. Any such build must keep A7: the LLM may only de-escalate
calibrated keys and narrate context — never originate signals, scores, or escalations. Natural home:
a `risk_radar` section in the Live Market State Packet (`engine/neuralweb/market_packet.py`) +
persistent per-market memo state graded like every other ledger. Charter separately before building.
