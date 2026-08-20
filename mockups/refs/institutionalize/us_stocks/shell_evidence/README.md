# P-MP1-SHELL §11 evidence — shell_evidence/

Forced-state matrix the commissioning session required as committed crops
(gap 3 of the Day-2 follow-up commission), referenced from the PR body.
Rendered from `templates/dashboard.html.j2` (mode=stocks) via a standalone
Jinja harness (not `scripts/build_site.py` — no claim is made that this
harness reproduces the nightly build byte-for-byte for page regions this
packet does not touch), captured with headless Chromium (Playwright).

**Real payload, real per Δ = `site/prophet/index.json` asof 2026-08-19 +
`site/factordata/us_standouts.json` + `site/factordata/setups.json`, exactly
as committed on this branch — every card, count, and chip in the "real"
crops below is a live production value, not authored.**

**Synthetic fixture, marked `-SYNTH`** = a deterministic single-row clone
of a real row with only `lifecycle_state` (and the minimum fields that
implies) forced, used ONLY where the real payload has zero rows in that
cell tonight (N3: Watch and Overtime — see MP-1 §11's own N3 note). The
count/ladder numbers in these two crops are the real numbers **plus the one
synthetic row**, never presented as the night's true counts.

| # | File | Source | What it proves |
|---|---|---|---|
| 1 | `01-main-{dark,light}-{en,zh}-{1440,390}.png` (8 files) | real | Main board, light+dark×EN+ZH at 1440 and 390px. |
| 2 | `10-empty.png` **[recaptured, round 2]** | synthetic (empty `plans: []`) | §10 empty state: all-zero ladder still renders + `.mx-empty` message + the required `.mx-empty-why` cause line ("No qualifying rows today · refreshes after the next close" — added by repair-round finding S4, theme.css:1983-1988's law); Candidates/Recently-fired unaffected. |
| 3 | `11-loading.png` | synthetic (`us_prophet_book=None`) | §10 loading: skeleton shimmer, no words, geometry intact. |
| 4 | `12-error.png` | synthetic (`us_prophet_book_error=True`) | §10/Amendment 2 error state: `.mx-error`, the shipped three-section copy, ≥40px Retry — and Candidates/Recently-fired/footnote **do** stay current, proving the promise the copy makes. |
| 5 | `13-watch-key-absence.png` **[recaptured, round 2]** | synthetic (`intake.early_turn_watch` key removed) | §6 fn.1 / §10: em dash + disclosure line, distinct from a zero. The ZH string is now the §10-ratified `观察档自下一次夜间构建起发布。` (repair-round finding S5 — the prior copy was a paraphrase); not visible in this EN-language shot (same single-language convention as this row's original capture) but pinned by `tests/test_p_mp1_shell_repair_round.py::test_s5_*`. |
| 6 | `14-watch-present-at-zero.png` | real (tonight's actual payload state) | Amendment 1 P-K19: `early_turn_watch: []` present-and-empty renders the normal zero-count cell, no disclosure line. |
| 7 | `20-filter-ready.png` | real | `?life=ready` — 77 real rows. |
| 8 | `20-filter-entered.png` | real | `?life=entered` — 154 real rows. |
| 9 | `20-filter-delivering.png` | real | `?life=delivering` — the 1 real row (RBLX). |
| 10 | `20-filter-invalidated.png` | real | `?life=invalidated` — 4 real rows. |
| 11 | `20-filter-resolved.png` | real | `?life=resolved` — 26 real rows, two-total law (0 leak into the default view). |
| 12 | `20-filter-watch-SYNTH.png` | **synthetic** | N3: zero real Watch rows tonight — one synthetic row, filtered. |
| 13 | `20-filter-overtime-SYNTH.png` | **synthetic** | N3: zero real Overtime rows tonight — one synthetic row, filtered. |
| 14 | `30-two-episode-ticker.png` **[recaptured, round 2]** | real (FBRT, one of the real multi-episode tickers tonight) | The episode chip now reads "Episode 2 · opened Aug 10" — repair-round finding S6 dropped "of N" and formats the date (was "Episode 2 of 2 · 2026-08-10", a raw ISO string). Captured with the client-side tier lock and show-more collapse temporarily neutralized via an injected `!important` override (episode-chip demo only — the lock states themselves are captured separately in #15/#16, unmodified). |
| 15 | `40-free-tier-lock.png` | real | Free tier (`MMXAccessPreview.tier()==='free'`, cap=3): 3 sharp cards + 2 blurred, simulated via a session-storage/cookie fixture consumed by `tier_preview.js`'s own real tier-resolution code — no product code changed for this shot. |
| 16 | `41-anon-lock.png` | real | Anonymous tier (default, no session): 1 sharp card + 2 blurred — identical file to `01-main-dark-en-1440.png`, duplicated under this name for the lock-distinction pairing. |

## Round-2 recapture (repair round 2, finding "Evidence recapture")

`10-empty.png`, `13-watch-key-absence.png` and `30-two-episode-ticker.png`
photographed superseded copy after repair-round findings S4/S5/S6 changed
the rendered strings in those three states. Recaptured against the SAME
committed payload (`site/prophet/index.json`/`us_standouts.json`/
`setups.json`, unchanged since round 1 — the ladder/candidate counts in the
table above are identical) using the committed tooling below, run through a
throwaway local Playwright install (`python3 -m venv`, not a repo
dependency — same external-tooling assumption `capture.py` already makes).
The other 19 files were NOT recaptured: their underlying states render no
byte this repair round touched, so re-shooting them would only add capture-
time noise (live-quote pill jitter, timestamp drift) without proving
anything — confirmed by inspecting the diff class-by-class before deciding
which three actually needed a new shot.

## N3 (MP-1 §11) — still named, not resolved by this evidence

Watch and Overtime carry **zero real rows** in tonight's payload
(`site/prophet/index.json` `lifecycle_counts.watch == lifecycle_counts.overtime
== 0`), so no real card-level crop of either cell is possible from tonight's
data — matching MP-1's own N3 disclosure that the reference itself never
had one either. Delivering, previously grouped with Watch/Overtime as
unphotographable in the original commission, **now has one real row
(RBLX)** and is photographed for real in #9 above — N3 narrows to Watch and
Overtime only, going forward.

## Regeneration

Committed tooling, in this directory's own `tools/` (same convention as the
reference's `gen_fixture.py`/`capture.py`):

```
# 1. render every state to standalone HTML + copy the static assets it needs
for s in default empty loading error watch-absent overtime-synth watch-row-synth; do
  python3 mockups/refs/institutionalize/us_stocks/tools/gen_shell_evidence.py "$s" /tmp/shell_ev
done

# 2. serve it (never write into the repo's own site/ — see MM_DATA_GUARD, CLAUDE.md)
cd /tmp/shell_ev && python3 -m http.server 8946 &

# 3. capture (requires Playwright + Chromium: pip install playwright && playwright install chromium)
python3 mockups/refs/institutionalize/us_stocks/tools/capture_shell_evidence.py \
  http://localhost:8946 mockups/refs/institutionalize/us_stocks/shell_evidence
```

`gen_shell_evidence.py` renders `templates/dashboard.html.j2` directly
(not `scripts/build_site.py` — no claim is made that this harness
reproduces the nightly build byte-for-byte for page regions this packet
does not touch) against the real committed payload, with the same synthetic
vm scaffolding `tests/test_dashboard_template_render.py` uses for every
field this repo has no other real producer for.
