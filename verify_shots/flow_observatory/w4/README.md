# Flow Observatory V2 — W4 visual evidence

Official-vs-curated lenses, coverage floors, overlap disclosure, concentration and
contribution (`research/flow_observatory/W4_SPEC.md`).

**REPAIR ROUND (2026-09-03)** — this file, and the 16 crops it describes, were
regenerated against an independent review that returned FAIL (missing CI wiring, a
denominator/mean disagreement, a collector safety gap, and — the reason this file
exists — no declared LIGHT art direction, TP-0). Everything below is the POST-repair
state. See "Repair items" and "Honest correction" further down for exactly what
changed and why the published numbers moved slightly.

Captured via Playwright Chromium (`/private/tmp/pwvenv`, headless), `reduced_motion:
"reduce"`, against the REAL rebuilt `site/flow_velocity.html` served statically
(`python3 -m http.server <port> --directory site`) — same method as the W1/W2/W3
verify_shots. A small JS pass forces `opacity:1`/`.is-in` on every `.fv-reveal` section
(the page's own IntersectionObserver reveal otherwise leaves off-screen sections at
`opacity:0` for a screenshot taken without a full scroll pass) and scrolls to the
lens tabset before each capture. `theme`/`lang` are set via `localStorage` before load
(the page's own boot script reads them); the "official" shots additionally click
`#lens-tab-official` to switch the tab. Capture script: throwaway, not committed (this
README is the durable record).

Every one of the 16 captures below also had its `document.documentElement.scrollWidth`
checked against `window.innerWidth` (no horizontal PAGE scroll) and its Chromium
console drained for `error`-level messages — both are clean across the full matrix
(`console_errors.json`, committed alongside; zero horizontal-scroll violations, zero
console errors).

## TP-0 art-direction declaration (dark + light, per element)

This is the packet law this repair round exists to satisfy: dark and light are TWO
material treatments, never one skin swapped via token substitution.

**Insufficient-coverage pill** (`.fv-cov-badge.insufficient` / `.qchip.coverage-
insufficient`) — the state chip that fires for 28 of 31 official sectors and never for
a curated theme today (all 22 sit at 100% coverage).
- **DARK TREATMENT (existing, kept, now declared explicitly):** a flat amber wash
  mixed toward `--muted` (`color-mix(in srgb,var(--amber) 82%, var(--muted))` /
  `14%,transparent` background) — reads as a glow/tint against the dark card, the
  command-center idiom every other W2 state chip in this template already uses.
- **LIGHT TREATMENT (new this round):** amber-tinted PAPER — a light amber wash mixed
  into `--card` (`color-mix(in srgb,var(--warn) 12%,var(--card))`), not transparent,
  so it reads as tinted material rather than an overlay — plus DEEPENED amber-brown
  ink, mixed toward `--ink` rather than `--muted`
  (`color-mix(in srgb,var(--warn) 65%,var(--ink))`). Same semantic-class family as
  W2's STALE-adjacent "behind" chip (`.fv-src--behind`, this template — a real
  existing light-theme amber-warning recipe, not invented for this pill). Reusing the
  dark formula verbatim on light — the "same CSS renders once tokens swap" failure —
  was the actual pre-repair bug: `color-mix(..., var(--muted))` reads washed-out on a
  white/paper background; mixing toward `--ink` keeps the required contrast.
- Screenshot proof: `lens_official_light_en_1440.png` (Agriculture/Chemicals/Steel
  rows) vs `lens_official_dark_en_1440.png` (same rows) — visibly different material,
  not a re-skin.

**Concentration chip** (`.fv-conc-chip`, "concentrated" / "overlap N") — informational,
never a warning, fires on `cn_insurers`/`cn_appliances` (top1_share > 40%) today.
- **DARK TREATMENT (existing, declared as-is):** neutral hairline border
  (`var(--grid)`), `--muted` ink — no tint in either theme.
- **LIGHT TREATMENT (new):** the SAME neutral hairline border (still no tint — the
  chip stays informational), but ink deepened toward `--ink`
  (`color-mix(in srgb,var(--ink) 55%,var(--muted))`) — `--muted` alone reads too pale
  on white/paper for a chip with no fill of its own to lean on (unlike the coverage
  badge below, which sits on its own `--tile` fill and can afford `--muted` contrast).
- Screenshot proof: `lens_curated_light_en_1440.png` (Insurers row, "concentrated"
  chip) vs `lens_curated_dark_en_1440.png` (same row).

**Coverage badge** (`.fv-cov-badge`, the plain `n_covered/n_members` pill before the
`.insufficient` modifier applies) — "muted tabular numerals both themes."
- **INTENTIONALLY SHARED, declared as such** — this is the one W4 element with no real
  per-theme material decision to make: `color:var(--muted); background:var(--tile)`
  plus `font-variant-numeric:tabular-nums; font-family:var(--num)` (added this round —
  the digits were not actually tabular before). Both themes read the identical CSS
  rule; only the underlying `--muted`/`--tile` token VALUES differ per theme (already
  theme-aware from the existing `:root` vs `html[data-theme="dark"]` blocks). Sharing
  a rule here is not the "same CSS renders once tokens swap" failure TP-0 forbids —
  that failure is about skipping a REQUIRED material decision, and this element
  genuinely has none: a coverage count is not a warning state, so light gets no
  "deepened ink" treatment of its own.

**Accruing-sparkline placeholder** (`.fv-accruing`, N2, new this round) — same
intentionally-shared muted family as the coverage badge (informational, no warning
semantics): `color:var(--faint); background:var(--tile)`, tabular numerals. Visible in
`lens_official_*_1440.png` on Nonferrous Metals / Non-bank Financials as
"accruing — 1/130 sessions" (EN) / "累积中（1/130）" (ZH) — the membership store was
seeded TODAY (2026-09-03), so real accrual sits at 1 of the 130-session spark window
on every capture.

## Repair items (this round)

**B1 — CI wiring.** `tests/test_flow_observatory_groups.py` (416 lines, 20+ tests) was
named by NO job in EITHER `.github/ci/legacy-jobs.yml` or `.github/workflows/ci.yml`'s
path gate — the whole suite was dark from the original W4 merge onward, and the prior
round's "wired" claim was false. Fixed: added to the `flow-velocity measure guards`
job's `run:` line, plus explicit `ci.yml` path-gate entries for the test file and
`collectors/china_sectors.py` (the official lens' membership source;
`engine/flow_observatory/groups.py` was already covered by the `engine/flow_observatory/**`
glob). `data/china_sectors/**` is NOT a path-gate subject (house law: data files are
never CI path subjects).

**B2 — collector safety** (`collectors/china_sectors.py`). Three fixes, each with a
failing-first test in `tests/test_flow_observatory_groups.py`: (1) an EMPTY fetched
snapshot refuses to diff at all — an akshare outage used to read as "every sector's
membership vanished today" (measured: 5,211 rows would have closed from one empty
fetch against the real seeded store); (2) closures are scoped to l1_codes this run
ACTUALLY OBSERVED — a partial outage no longer closes the FAILED codes' intervals
too; (3) a re-entry (a ticker whose prior row is CLOSED, not open) can never mint an
overlapping interval — its `start_date` is pinned to `today` whenever the source's own
reported date would not clear the prior close, and a new store invariant
(`overlapping_intervals()`) re-checks the whole merged table before every write.

**B3+M2 — the published statistic's member set IS the declared denominator.** The
aggregate mean (`sect_flow`) was computed over `cols` (members present in the flow
panel, scored OR NOT) while `n_covered`/`excluded` described the narrower `covered`
(scored-only) set — an unscored member's raw flow was silently riding inside the
published mean even though it rendered in the excluded list. Fixed in BOTH
`engine.flow_observatory.groups.aggregate_lens` and
`engine.flow_velocity.ashare_sector_velocity`: the mean/kinetics/contributions/
coverage/excluded set is now uniformly `covered`. The row's DISPLAYED `rate_rel` is
now wired to equal Σ(member contributions) exactly — tested against the ROW FIELD,
not a self-defined `group_rel` (the prior test only checked the concentration math
against itself, never the wiring).

**M1 — official-sector ledger + validate().** `official_sectors` rows never flowed
through `contract.build_v2`'s theme loop (that assembly lives entirely in
`scripts/build_flow_velocity.py`, per OWNED-FILES scope) — so they never got
`rank_change`/`state_*`, and `validate()` never checked them at all.
`_apply_official_rank_change` (new) mirrors the theme treatment: ledger-derived
(`entity_kind="sector"`) once ≥2 sessions accrue, else an honest
`rank_change=None`/`"first tracked session"` — never a permanent dash by construction.
Official-sector observations now append to the ledger in the SAME guarded call as
themes. `validate()` gained a shared `_validate_group_rows` check (quadrant/axis
consistency + the `coverage_state` enum) applied to BOTH `official_sectors` and
`ashare_sectors` rows.

**M3 — disclosure UI.** The excluded/missing list and the concentration drilldown line
carried a BAKED `' show'` class independent of whether the sector's accordion was ever
opened — both were visible above the fold before any interaction. Fixed: no baked
default (both now ride the same accordion show/hide as the member rows); the excluded
list additionally moved behind a native `<details class="fv-disc">` (Tier-2) whose
`<summary>` carries only the count ("53 excluded" / "53只未纳入"). Official-lens
excluded entries now show a real display NAME (`name_map` threaded into
`aggregate_lens`, sourced from `engine.flow_velocity._name_map()`) — the ticker slug
rides only in the entry's own LENS tip (`data-tip-en`/`data-tip-zh`), never as the
primary label when a name exists.

**A real bug the M3 fix exposed (caught during THIS evidence pass, fixed before the
final capture — same precedent as the two bugs the original W4 evidence pass caught):**
`concrow`/`excludedrow` are shared macros between the curated lens (bare `r.id`
`data-sector`, matching its own sector-row/member-rows) and the official lens (which
prefixes EVERY sector-row/member-row `data-sector` with `"off-"` to disambiguate SW
codes from theme ids) — but concrow/excludedrow always emitted the BARE id, never the
`"off-"` prefix. The pre-repair baked `' show'` default masked this: the rows were
always visible regardless, so the mismatch never mattered. The moment the baked
default was removed (M3, above), the official lens' concentration/excluded rows became
**permanently unreachable** — the accordion click toggles `.mrow[data-sector="<the
clicked row's own value>"]`, which for an official-lens row is always `"off-{id}"`, a
value bare concrow/excludedrow never carried. Fixed: both macros accept an explicit
`sector_id` override; the official lens now passes `'off-' + r.id`, the same value its
own sector-row/member-rows use. Regression-tested:
`test_official_lens_concrow_and_excludedrow_share_the_off_prefixed_sector_id`.

**N1 — coverage floor compares the RAW ratio.** `coverage_pct` is rounded to 1dp for
display; 241/402 members (59.9502...%) rounds to a displayed "60.0%" — which would
silently CLEAR a 60% floor it does not actually meet. `coverage_stats()` now also
returns `coverage_ratio` (unrounded); the floor check in both lenses compares that
raw ratio, never the rounded percentage. Boundary-tested at 241/402 (insufficient) and
242/402 (ok). Today's real data has no sector sitting at that exact rounding boundary
(the natural break is 57.6%→62.1%, see the calibration note below), so N1 changed no
real published classification — it closes a LATENT gap, not a currently-manifest one.

**N2 — official-lens sparkline suppressed until membership history accrues.** The
lens applies TODAY's membership retroactively across the whole flow panel (spec §2A —
current membership, no historical replay) — a sparkline drawn from that backfill
implies a composition depth the store has not actually observed. `spark` is now `None`
until `accrued_sessions >= 130` (the same window the spark tail uses); a muted
`.fv-accruing` placeholder names the progress instead. The LENS receipt gained one
line: EN "current-membership basis — constituents as of {seed_date}" / ZH "按当前成分
计算——成分截至{seed_date}" (rate/vel columns stay — same current-membership basis as
themes, already labeled by the existing lens-header line).

**N3 — Beijing Stock Exchange tickers.** `normalize_cn_ticker` gained the BSE branch
(`8xxxxx`/`43xxxx`/`92xxxxx` → `.BJ`, checked before the pre-existing `9xxxxx`→`.SS`
legacy-B-share branch so `92xxxx` is never misrouted). A `.BJ` member counts in its
sector's real `n_members` and lands in `excluded(missing)` until the flow grid covers
the BSE — honest, never silently dropped.

**SF — the ZH-name regression test now pins the CALLER.** The original test exercised
only `aggregate_lens`' own plumbing against a hand-written `l1_names` fixture — an
EN-only revert in the ACTUAL production caller (`scripts/build_flow_velocity`) would
have passed silently. `_l1_names()` extracted as its own function;
`test_l1_names_caller_builds_distinct_en_zh_names` imports and asserts on it directly.

**MOBILE (≤640px).** Boards now keep name, abs 4wk, vs norm, quadrant chip, and the
coverage badge (Members column) visible without a page-level scroll; Velocity, rank Δ,
and Flow trend hide via `display:none` (never a clip/ellipsis — nothing is truncated
mid-token). `table.board{min-width:780px}` — a desktop floor that would otherwise force
the table wide regardless of how many columns survive — is overridden to `min-width:0`
for the two board tables inside the media query, with tighter cell padding alongside.
The §4 concentration line and the excluded-list row no longer inherit
`table.board`'s global `white-space:nowrap` (`.fv-conc-row td,.fv-excluded{white-
space:normal;word-break:break-word}`) — verified: with the fix, the concentration line
wraps within its own cell rather than forcing the table wider to keep one unbroken
line. **Honest disclosure, not overclaimed:** at 390px the 5 surviving columns'
natural content width (~538px, measured) still exceeds the viewport, so the last
column (quadrant chip) and the full concentration/excluded text are reached via the
SAME `.tbl-wrap{overflow-x:auto}` inner scroll every board already uses for its full
8-column view — never a page-level scroll (checked programmatically on every capture:
`document.documentElement.scrollWidth === window.innerWidth` on all 16), never a
clipped/ellipsized token. Verified interactively (not part of the pinned 16-crop
matrix; supplementary check during this repair): opening the Nonferrous Metals
drilldown at 390px reveals the concentration line and the excluded `<details>`
disclosure exactly as at 1440px, wrapped, reachable via that same inner scroll.

## Honest correction — published numbers shifted slightly (B3+M2 fix)

Fixing the denominator (B3) and wiring `rate_rel` to Σcontributions (M2) moved a
handful of numbers on the real 2026-09-03 build. Curated themes sit at 100% coverage
today, so the denominator half of B3 changed nothing there — but the M2 `rate_rel`
rewiring (previously computed off the theme-level series' own demean, now the mean of
covered members' individually-demeaned `rate_rel`) moved `rate_rel` on 20 of 22 curated
theme rows, all by ≤0.3: e.g. `cn_robotics` -0.3 → -0.1273, `cn_defense` 1.5 → 1.7308,
`cn_banks` 0.2 → 0.2333. On the official lens, where several sectors genuinely have
unscored members, B3's denominator fix changed real numbers on the 3 sectors that clear
the coverage floor today: **Nonferrous Metals** vel 0.02 → -0.0 (crossed into "near its
norm"), rate_rel 0.0 → -0.0138; **Banks** vel 1.18 → 1.1, rate_now -4.4% → -4.5%,
rate_rel 0.9 → 0.8789; **Non-bank Financials** vel 1.4 → 1.31, rate_4wk -1.7% → -1.8%,
rate_rel 1.5 → 1.3574. Every shift is small and in the direction of removing an
unscored member's contamination from the mean — none flip a quadrant's LOUD reading
(accumulation/distribution) into a different loud reading; Nonferrous Metals' `vel`
crossing 0 stays inside the existing "near its norm" neutral band either side of the
old/new value.

## Crops (dark/light × EN/ZH × 1440 + 390 mobile, curated AND official lens per theme)

| file | shows |
|---|---|
| `lens_curated_dark_en_1440.png` | Theme flow board, dark, curated tab active: lens tabset, `overlap 2` chip (Autos & NEV Makers, shared with another theme), `concentrated` chip (Insurers), coverage badges with tabular numerals, pinned drilldown line |
| `lens_official_dark_en_1440.png` | Official (Shenwan L1) tab, dark: pinned lens label + the new "current-membership basis — constituents as of 2026-09-03" LENS receipt line; 28 of 31 sectors render `insufficient coverage` (amber-glow pill, never dropped); **Nonferrous Metals** (62.1% coverage) shows a real quadrant + `accruing — 1/130 sessions` in place of a sparkline; **Banks** (38/42 = 90.5%) shows `real inflow, above norm` |
| `lens_curated_light_en_1440.png` | Same curated board, LIGHT theme — white/paper material, hairline chips with deepened ink, all W4 chips legible (governed tokens, no new palette) |
| `lens_official_light_en_1440.png` | Same official board, LIGHT theme — amber-tinted-paper insufficient-coverage pills (materially distinct from dark's glow, see TP-0 declaration above) |
| `lens_curated_dark_zh_1440.png` | Curated board, dark + ZH — theme names/labels/chips fully in Chinese, no English leakage |
| `lens_official_dark_zh_1440.png` | Official board, dark + ZH — real Shenwan L1 Chinese names, `覆盖不足` badges, `累积中` sparkline placeholder, excluded list behind a `N只未纳入` disclosure |
| `lens_curated_light_zh_1440.png` | Curated board, light + ZH |
| `lens_official_light_zh_1440.png` | Official board, light + ZH |
| `lens_curated_dark_en_390.png` / `lens_official_dark_en_390.png` | Mobile (390px) crops, dark EN — lens tabset stacks as pills; boards keep name/members(coverage badge)/abs/vs-norm visible without scrolling, quadrant reached via the table's own inner scroll; zero page-level horizontal scroll (checked per capture) |
| `lens_curated_light_en_390.png` / `lens_official_light_en_390.png` | Mobile crops, light EN |
| `lens_curated_dark_zh_390.png` / `lens_official_dark_zh_390.png` | Mobile crops, dark ZH |
| `lens_curated_light_zh_390.png` / `lens_official_light_zh_390.png` | Mobile crops, light ZH |

## Coverage-floor calibration (real data, 2026-09-03)

All 22 curated `baskets_china` themes sit at 100% coverage today — any floor ≤100% keeps
every one of them eligible (trivial). The SW L1 official-sector distribution is the real
"degenerate tail" the floor exists to catch (measured against the same `kmap`, 31
groups): coverage ranges 5.1%–90.5% with a natural break at 57.6%→62.1%. Only **Banks**
(90.5%), **Non-bank Financials** (77.2%), and **Nonferrous Metals** (62.1%) clear a 60%
floor; the other 28 sectors legitimately have too little of their true membership inside
the ~1,800-name Tushare moneyflow panel to publish a non-survivor-biased read. The
starting hypothesis (60%) sits inside that natural gap and is kept as-is (see
`engine/flow_observatory/groups.py` module docstring for the full receipt). N1 (above)
did not move this calibration — no sector sits at the exact rounding boundary today.

## Spike receipt (spec §1)

`ak.index_component_sw(symbol=<SW L1 code>)` — keyless, `www.swsresearch.com` JSON
endpoint, no key/token. Sampled 801780 (Banks, 42 rows) and 801080 (Electronics, 493
rows) before building the full 31-code snapshot (5,211 total constituent rows). SPIKE
SUCCEEDED → §2A implemented (never §2B, though the §2B "unavailable" designed state is
still real, reachable code — exercised by
`tests/test_flow_observatory_groups.py::test_official_lens_unavailable_state_renders_pinned_strings_no_curated_leak`
for the case a fresh checkout's membership store has not collected yet).
