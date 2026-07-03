# W1-B Builder Wiring Report — 2026-07-03

## Outcome

DONE. All 6 builder tasks implemented and invariant-verified. 111 tests pass (44 setup_tier +
13 china_standout_track + 20 china_alpha_w0 + 34 new W1-B). No full render required.

## What was built

### 1. Universe-wide w_setup scan

`scripts/build_china_library.py` now scans the FULL closes-panel universe (>=200 bars)
via `engine/setup_tier.w_setup` after the main `_analyze_universe` loop completes, storing
results in `_wsetup_by: dict[str, dict | None]`.

**Performance (measured on actual panel):** 6.4ms/name × 1478 valid names = ~9.5 seconds.
Well inside the 2-minute budget. No prefilter needed.

Reuses the already-loaded closes from `uni` — does NOT re-read per name.

### 2. Stage assignment on buy rows (rules 1-2)

Each buy row in `eligible_rows` gains:
- `stage`: ENTRY or RAN_LATE or None
- `stage_sublabel`: human-readable rule 2 label when applicable
- `stage_detail`: structured detail dict
- `why_ranked`: compact string of actual blend inputs (tier + washout_2w + coiled − ext penalty)

The ENTRY shelf preserves the existing `blend_sorted` order UNCHANGED (F3 discipline: no rank
change from this wave). `why_ranked` is display-only.

Rule 2 arbiter: a gate-eligible name with `entry_status` in {hold, extended, topping, ...}
or `overextended=True` reads RAN_LATE even while technically cascade-eligible. This kills
the 77/110 extended-chip contradiction per masterplan F1.

### 3. RAN array (rule 3)

Built from the full `uni` universe, excluding gate-eligible names. Fires when:
- NOT gate-eligible
- Last signal_gate marker is a buy-type
- `sessions_since` cross <= 15 (inclusive boundary)

Computed fields: cross_date, sessions_since, pct_since (from close series), sublabel,
basing_chip (when hold_state == "intact"). Sorted by sessions_since ascending (most recent
first). Capped at 15.

**Verified on 603129.SS:** cross 2026-06-24, sessions_since=7, pct_since=+8.9%.
Reads RAN_LATE "signal fired 2026-06-24 (7 sessions ago), +8.9%" — matches owner's
"already ran 5-8 days ago" (probes-inline.md Probe 2).

### 4. RIPENING array (rule 4)

Built from the full closes-panel universe (all >=200-bar names). Excludes:
- Gate-eligible names
- Names with a recent cross (sessions_since <= 15 → rule-3 territory)

Includes when: `wsetup.setup_live = True`. Sorted by imminence (macd_bars_to_cross
ascending; washout-only names sort last). Capped at 24.

Row fields: ticker, name, sector, reasons, imminence (macd_bars_to_cross), w2_stoch,
w2_macd_approaching, w2_macd_cross_up, w1_cross_date, w1_d_at_cross, spot_pct_in_range.

### 5. Artifact compat

`china_standouts.json` structure:
- `buy` array: UNCHANGED semantics. Every row gains `stage`, `stage_sublabel`,
  `stage_detail`, `why_ranked` — additive fields, zero breaking changes.
- `ripening`: NEW array (rule-4 names, cap 24)
- `ran`: NEW array (rule-3 names, cap 15)

Consumers of `buy` verified:
- `build_china.py`: reads `buy` key by name — unaffected
- `backfill_stock_open.py`: iterates `("buy", "laggards")` — unaffected
- `china_standout_track.append_board`: takes buy rows — stage field added to ledger
- `compute_china_standouts`: enriches buy rows — additive fields don't conflict

### 6. Ledger wiring

`engine/china_standout_track.append_board` gains a `"stage"` column (schema-union safe:
old parquet rows read as NaN via pd.concat, which handles missing cols transparently).

`engine/china_standout_track.append_ripening` is a NEW function:
- Separate parquet: `data/china_standout_track/ripening.parquet`
- Same asia-lane gate as `append_board`
- Row schema: date, ticker, reasons (comma-joined), imminence, w2_stoch, setup_live
- Keep-FIRST per (date, ticker) — same append discipline
- W6 conversion grading will use this history to compute RIPENING→ENTRY conversion rate

Ripening append runs inside the existing `if cand:` block after `append_board`, with the
same try/except guard (ledger failures are never fatal to the build).

### 7. Build-time invariants (all 5 from spec)

Implemented as `assert` statements in the builder, fail loudly before write:

1. Every buy row has a `stage` field
2. No rule-2 row (stage=RAN_LATE) carries entry_status=buy_now
3. Ripening rows are never gate-eligible
4. Ripening cap <= 24 respected
5. RAN cap <= 15 respected

Log line at build time: `W1-B stage partition: N ENTRY + M RAN_LATE + K no-shelf (buy rows);
P RIPENING + Q RAN (non-buy universe)`.

## Consumer audit

`grep -rn "china_standouts"` across all .py/.js files (excluding the builder itself):

| Consumer | Access pattern | Impact |
|---|---|---|
| `build_china.py` | `.get("buy")` | None — `buy` key unchanged |
| `backfill_stock_open.py` | `for key in ("buy", "laggards")` | None |
| `china_standout_track.append_board` | takes `buy` rows | `stage` field added (additive) |
| `compute_china_standouts` | enriches `buy` rows | additive fields don't conflict |
| `export_signal_contracts.py` | references artifact path only | None |

No consumer reads the `ripening` or `ran` keys yet — both are new. No existing consumer
iterates the `buy` field list by exact name (they use `.get("ticker")`, `.get("price")`, etc.).

## Files changed

- `engine/china_standout_track.py`: +53 lines (append_ripening + stage column in append_board)
- `scripts/build_china_library.py`: +228 lines (W1-B wiring block)
- `tests/test_china_alpha_w1b.py`: NEW (34 tests)

Note: `scripts/shadow_pit_china.py` appears in `git diff HEAD` but was pre-modified by the
W1-A agent before this session. This wave did not touch it.

## Tests

111 passed, 0 failed, 1 deprecation warning (pre-existing):
- `tests/test_setup_tier.py`: 44 passed (existing W1-A tests, no regression)
- `tests/test_china_standout_track.py`: 13 passed (existing tests + new append_ripening schema)
- `tests/test_china_alpha_w0.py`: 20 passed (W0 tests, no regression)
- `tests/test_china_alpha_w1b.py`: 34 passed (new W1-B tests)

New test coverage:
- Stage assignment rules 1-4 on synthetic buy rows
- Build-time invariants (all 5 from spec)
- Artifact shape (buy has stage/why_ranked, ripening and ran arrays present)
- why_ranked chip content for each input flag
- Ripening sorted by imminence, RAN sorted by recency
- Rule-3 15-tick boundary (inclusive)
- Rule-3 16-tick boundary (excluded)
- basing_chip added to RAN when hold_state==intact
- append_ripening: lane gate, empty input, missing asof
- stage column present in append_board schema
- ripening.parquet colocated with board.parquet

## Open items not addressed in this wave

- Template rendering of `stage`, `ripening`, `ran` — W1-C/display wave
- `why_ranked` chip display in Jinja — W1-C/display wave
- RIPENING card design (F1: "explicitly labeled setup forming — not an entry signal") — W1-C
- W-tier setup state in the click-through (china_lookup.html) — W2 or later
