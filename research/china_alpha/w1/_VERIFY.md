# W1 VERIFY — three-shelf lifecycle wave (adversarial gate)

**Verdict: FIX-NEEDED.** One blocker, reachable on TODAY's live panel, that aborts the china build
(and, absent that assert, ships green BUY banding on the honesty shelf — the exact F6 contradiction
this wave exists to kill). Everything else — engine math, stage rules, exemplar fixtures (a-e),
i18n, non-ASCII delimiters, F3 discipline, hygiene — passes.

Date: 2026-07-03. Panel: `data/china_search/closes.parquet` (1225×1514, through 2026-07-03).

---

## BLOCKER (build-aborting + F6 violation)

### B1 — buy_now/partial + extended names route to RAN_LATE, then crash the build / leak green banding

**Reachable on live data TODAY.** The current shipped artifact
`site/factordata/china_standouts.json` (pre-W1, 06:35) has **2 buy rows** with
`extension.extended=True` AND `entry_signal.status=="buy_now"`:
- `002896.SZ` — ext score 0.177, "+9% 1mo · fresh limit-up"
- `002472.SZ` — ext score 0.323, "+14% 1mo · -9% off 52w high · +2.2σ · fresh limit-up"

Under the W1 wiring these become RAN_LATE (rule 2, via `_overext = _ext_flag or ...`, and rule 1
now carries `and not overextended` — correct). Two independent failures follow:

1. **Build abort.** `scripts/build_china_library.py:1554-1559` asserts
   `not _r2_bad` where `_r2_bad` = RAN_LATE rows whose `entry_status=="buy_now"`. Both live names
   satisfy exactly that. On the next real build this `assert` raises `AssertionError` and **aborts
   the entire china build**. The wave routes buy_now+extended to RAN_LATE (rule 2) and then asserts
   that state can never exist — a self-inflicted landmine on live data.

2. **Display leak (F6).** `templates/china.html.j2:1492` — the RAN_LATE card reuses the full nbcard
   body including `<div class="nb-entry nbe-{{ es.status }}" title="... {{ es.action }}">`. For a
   `partial`-status overextended name (which the `_r2_bad` assert does NOT catch — it only checks
   `"buy_now"`) this renders:
   - `nbe-partial` → green (`--up`) left border (CSS line 172)
   - `nbe-dot a3` → green act-dot (CSS line 182)
   - tooltip text "Buy now"
   The `.nb-stage-ran-card` modifier (line 314) mutes only `.nb-cscore`, NOT the entry gauge.
   This is F6 verbatim: "no BUY-family wording outside the ENTRY shelf; no green banding on a name
   whose entry gauge says hold." Verified by rendering the W1-C block with a partial+overext RAN row:
   `nbe-partial` present, `nbe-dot a3` present, "Buy now" present, `stg-entry` absent.

**Root cause.** `assign_stage` rule 2 correctly re-shelves the name, but neither the builder nor the
template neutralizes the underlying `entry_signal` block, so the card still paints the green
"window open" gauge. `_r2_bad` was written to catch this — but as a build-crashing `assert` on a
condition that live data actually produces, and it misses `partial`.

**Fix direction (F3-safe; no bonus/blend touch):** when a buy row is assigned RAN_LATE, clear/override
its actionable entry-gauge (e.g. force the card's `es.status` to a non-actionable value, or gate the
`nb-entry` block on `n.stage != 'RAN_LATE'` in the template), AND turn `_r2_bad` into a warning-only
guard covering both `buy_now` and `partial` (or drop it once the gauge is neutralized). Add a render
test: a RAN_LATE buy row with entry_status in {buy_now, partial} must render NO `nbe-buy_now`/
`nbe-partial` and NO "Buy now" string.

---

## Exemplar fixtures (live panel, PYTHONPATH=$PWD python3)

| # | Case | Result | Values |
|---|---|---|---|
| a | 300725.SZ → ENTRY | **PASS** | gate eligible=True T1 ticks=2 (buy 06-29); w2 stoch=24 stoch_x=True; 1W cross 06-26 d=9.3 bars=1; buy_now → **ENTRY** |
| b | 603129.SS → RAN_LATE | **PASS** | gate eligible=False ticks=3 "rolled-over"; last buy 06-24; rule-3 → **RAN_LATE** "signal fired 2026-06-24 (7 sessions ago), +8.9%"; hold_state=launched anchor 06-26 (basing_chip None — see note) |
| c | 688306.SS RIPENING (historical cutoff) | **PASS** | cutoff 2026-06-15 (pre its 06-18 gate fire): gate eligible=False, w2 stoch=18 (washout ≤35), setup_live=True → **RIPENING** "2W stoch washout". The owner's front-running case reproduces. |
| d | Blasted-off regression NOT ENTRY | **PASS** | 198 live names ≥8% 5d run + 3D StochRSI ≥80; assign_stage with overextended/extended/topping → RAN_LATE for all; only clean buy_now → ENTRY. Rule-1 `and not overextended` pins the JNJ invariant. |
| e | Builder w_setup universe timing | **PASS** | full 1478-name (≥200-bar) pass = **9.1s** (6.1 ms/name), 1462 non-None. Budget 300s. |
| f | Template render, 3 shelves | **PARTIAL** | All three shelves render, stage badges correct, dual-span, backward-compat fallback works — BUT B1 leaks green banding + "Buy now" onto RAN_LATE cards (partial-status case escapes the builder assert). |

Note (b): the builder attaches `hold_summary` to the RAN array only when `state=="intact"`; 603129 is
`launched`, so its RAN row carries `hold_summary=None`. The prompt's exemplar (b) says "hold summary
present". This is a minor spec-vs-impl gap, not a blocker (sublabel + cross_date + pct_since are all
present; a "launched" name is not basing so the omission is defensible). Flagging for the owner.

---

## Diff review (hostile, whole tree)

- **Stage spec (engine/setup_tier.py):** rules 1-5 match THE STAGE SPEC line by line. Rule 1's added
  `and not overextended` is a correct reading of Rule 2's "(or alignment.overextended)" and is what
  makes the (d) regression hold. `hold_state.state=="intact"` is used where the spec text says
  "state=basing" — the W0-ported `engine/hold.py` emits `intact` (no `basing` state), so this is a
  correct adaptation of the spec vocabulary to the actual module. NOT a deviation.
- **F3 discipline:** `_cn_bonus` weights untouched; `blend_sorted` math untouched; ENTRY shelf
  preserves existing order (partition only). CONFIRMED clean.
- **Non-ASCII attribute delimiters:** whole-file regex scan = NONE (no curly-quote defect this wave).
- **t()/td() inside attributes:** NONE in added lines and whole file. Bilingual title attributes use
  raw " en · zh " strings (the accepted idiom), not t().
- **Jinja missing-key:** ripening/ran rows use `.get()` throughout; RAN_LATE buy cards reuse the
  existing ENTRY nbcard idiom (same attribute access on the same buy dicts) — safe by parity.
- **Artifact compat:** `buy` array admission semantics unchanged; every buy row gains `stage`;
  new `ripening` + `ran` arrays additive on both `wide` and `setups`. Downstream `buy` consumers
  unaffected. Ledger `stage` column schema-union safe (NaN on old parquet rows).
- **shadow_pit_china.py:** measurement-only (`measure_wsetup_repaint`), no live path touched.
- **Orphan hunk (minor):** `scripts/build_china_library.py:1475` `_cand_tickers` is assigned and
  never used — dead line, safe to drop.
- **Ledger log cosmetic (minor):** builder logs "logged %d names (ledger=%d)" where the second value
  is total combined ledger length, not names appended this run. Cosmetic.

---

## Tests

- `tests/test_setup_tier.py` + `tests/test_china_alpha_w1b.py` + `tests/test_china_stocks_w1c_render.py`:
  **94 passed, 1 warning** (pytest 8 class-fixture deprecation, benign).
- Bounded smoke `pytest tests -q -k "china or setup_tier or standout"`:
  **540 passed, 1 failed, 1 skipped**.
  - The 1 failure — `tests/test_china_news.py::test_adapter_is_registered_without_akshare` —
    is **PRE-EXISTING and unrelated**: `ImportError: cannot import name 'all_adapters' from
    scripts.collect`. `all_adapters` does not exist in `scripts/collect.py`; last commit touching
    that file (#1052) is unrelated to W1; no W1 wave file touches collect.py or the news adapter.
    NOT a W1 blocker.
- **Test-coverage gap:** the W1-C render test's `test_no_buy_family_words_on_ripening_shelf` only
  populates the rule-3/4 arrays, never a buy_now/partial-status RAN_LATE buy card — which is why it
  missed B1. The fix must add that case.

---

## Hygiene

- `git status` clean except expected wave files (4 modified, 6 untracked incl. w1/ reports).
- No tracked DATA files dirtied by tests; `data/china_standout_track/ripening.parquet` NOT created
  (tests used tmp paths).
- `data/vector/regime_calibration.json` — **PRE-EXISTING, not this wave**: untracked, never
  committed, referenced by NO W1 wave file. Must NOT be committed with W1.
- No git write operations performed.

---

## Bottom line

The engine, stage rules, and 5 of 6 exemplars are correct and the math reproduces the probes exactly.
But B1 is a hard blocker: on today's panel the wave will crash the china build (buy_now+extended →
RAN_LATE trips the `_r2_bad` assert on 002896.SZ/002472.SZ), and the partial-status variant escapes
that assert to ship green BUY banding on the honesty shelf — the precise F6 contradiction the wave was
chartered to eliminate. Ship-blocked until B1 is fixed and covered by a render test.
