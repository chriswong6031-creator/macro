"""TOP ANATOMY Phase-0 harness — extended-move anatomy: topped vs continued.

Runs the frozen construction in `research/top_anatomy/TOPA_PHASE0_PREREG.md` §4
over two tracks and writes the two committed artifacts: a vintage-stamped summary
JSON and `reports/top-anatomy-phase0.md`.

THE QUESTION. Among days when a name is ALREADY EXTENDED, does anything
point-in-time separate the days that go on to top from the days that keep going —
beyond what extension magnitude and realized volatility already separate (they
are matched away)? Never "collapsed names vs average names": extension is a
prerequisite for some tops, not proof of one, so the only honest contrast is
extended-that-topped against extended-that-continued.

WHAT RUNS (prereg §4–§5)
  E1   36 features x matched-control contrast, month-block CI, BH-FDR within family
  E1b  pooled AUC increment over an extension-only baseline (grouped + walk-forward)
  E2   lead-time profiles -> EARLY / MID / LATE / POST-TOP CONFIRMATION labels
  E3   descriptive first-crossing ordering of survivors
  E4   era and dollar-volume-tercile sign stability
  G0.2 delisting verification (the Wide track's dead names, named not assumed)
  Today's tape: the current extended cohort with its feature readout

TIER. Research / display tier, zero scored authority; AVOID-not-SHORT (the outputs
are entry-side avoidance and trim-conviction CONTEXT, never a directional bear
position and never an exit rule). A discovery phase-0 has no program kill on a
null: a well-powered null re-scopes Wave-1 copy, it does not close the search.

DATA HONESTY
  * Track W (`data/massive_stock_day`, the registration track) is UNADJUSTED; split
    repair reuses the canonical yahoo-verified `scripts.replay_standout_pipeline
    .split_adjust`. Dividends are not adjusted (a small stated downward drift).
  * Tickers get REUSED. Every ticker's tape is cut at interior gaps > 60 sessions;
    Track W's declared `sanity-segmented` repair arm also cuts residual repaired-
    close up-jumps >=3x. Neither seam may contribute history to the next identity.
  * Track D (`engine.price_ladder` adjusted rungs, first-rung-wins) is a CURATED
    universe: names that topped and died are underrepresented, so its topped-arm
    severity is understated. Every D table says so.
  * The run's last data day is derived FROM THE PANEL, never from a manifest, and
    stamped on every artifact alongside the git sha.

W2 TIER-WIDENING ARMS (`--w2-arm`, `research/top_anatomy/TOPA_W2_PREREG.md`)
  The same pipeline with ONE moved variable: the §4.1 trigger term, taken from the
  engine's existing `extended_mask(variant=...)` arms (`r63`, `atrz`). Track W only.
  Each arm reports two panels — FULL (all arm episodes) and DISJOINT (arm episodes
  sharing zero EXT days with the phase-0 primary mask, where the generalization
  claim lives) — a §5 coverage gate that leads the result, five one-sided
  confirmatory legs, and the other 31 features as exploratory. No engine change.

Run:
  python -m scripts.research_top_anatomy_phase0 --data-root <primary>/data
  python -m scripts.research_top_anatomy_phase0 --data-root <...> --track W --quick 300
  python -m scripts.research_top_anatomy_phase0 --data-root <...> --w2-arm r63
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from collectors.massive_stock_day import (  # noqa: E402
    StaleLocalMirrorError, check_local_mirror_freshness)
from engine import price_ladder, top_anatomy as ta  # noqa: E402
from scripts.replay_standout_pipeline import split_adjust  # noqa: E402

FAMILY = "top_anatomy_p0"
CACHE_SUBDIR = "research/top_anatomy_p0"
#: `raw_close`/`raw_dvol` carry the AS-PRINTED prints the §3 floors are evaluated on;
#: `split_day` flags the factor step day (ineligible). Everything else is repaired.
W_PANEL_COLS = ("close", "open", "high", "low", "volume", "raw_close", "raw_dvol",
                "split_day")
D_START = "1997-01-01"
#: §4.8 windows, stated POSITIVE-BEFORE-PEAK: days_to_peak = peak_date − d.
E2_BUCKETS = ((22, 63), (6, 21), (1, 5), (-5, 0))
E2_LABELS = {(22, 63): "EARLY", (6, 21): "MID", (1, 5): "LATE",
             (-5, 0): "POST-TOP CONFIRMATION"}
PARITY_SAMPLE_NAMES = 3               # §3 hard pre-run gate, per track
PARITY_TOLERANCE = 1e-9
#: The W store opens 2021-07-06 and MIN_PRIOR_SESSIONS=260 is served INSIDE a
#: segment, so no EXT day can exist before 2022-07-18. The first era cell is named
#: for the span it can actually hold; "2021H2" would advertise an empty period.
W_EXT_LEFT_EDGE = "2022-07-18"
W_ERAS = (("2022H2", W_EXT_LEFT_EDGE, "2022-12-31"),
          ("2023-2024", "2023-01-01", "2024-12-31"),
          ("2025-2026", "2025-01-01", "2099-12-31"))
D_ERAS = (("1997-2003", "1997-01-01", "2003-12-31"),
          ("2004-2012", "2004-01-01", "2012-12-31"),
          ("2013-2020", "2013-01-01", "2020-12-31"),
          ("2021-2026", "2021-01-01", "2099-12-31"))
COVERAGE_FLOOR = 0.60
#: §4.6 fields whose observed separation runs AGAINST the declared direction. They
#: register nothing; they are profiled so the anchor counter-explanation is testable.
WRONG_SIGN_EXHIBITS = ("F1_episode_age", "F3_days_since_63d_high", "B3_rsi14_chg10")
#: G0.5 is a COVERAGE gate: run-1's fabricated extensions were found by reading the
#: whole cohort, so the appendix prints every extended name. Display-only; no frozen
#: quantity rides on it. `None` = uncapped.
TODAY_TAPE_CAP: int | None = None
W_REPAIR_ARM = "sanity-segmented"
W_RESIDUAL_UP_RATIO_BREAK = ta.RESIDUAL_UP_RATIO_BREAK
#: Run-1 (`pre-repair`, gap rule only) and run-2 (`sanity-segmented` on the
#: pre-audit instrument) are retained beside the headline summary as audit arms.
PREREPAIR_SUMMARY = _REPO / "data/research/top_anatomy_p0_summary_prerepair.json"
RUN2_SUMMARY = _REPO / "data/research/top_anatomy_p0_summary_run2_preaudit.json"
#: Run-2 executed an UNCOMMITTED working tree; its summary stamps the committed head
#: instead. The code survives only here, unpushed, so run-2 cannot be re-run.
RUN2_INSTRUMENT_SHA = "9f4a38b83be"

_T0 = time.time()


def say(msg: str) -> None:
    """Plain progress print — no logging config, no GitHub annotations (off-lane)."""
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# panels
# ══════════════════════════════════════════════════════════════════════════════
def _wide(segments: dict[str, pd.DataFrame], col: str) -> pd.DataFrame:
    have = {k: v[col] for k, v in segments.items() if col in v.columns}
    return pd.DataFrame(have).sort_index() if have else pd.DataFrame()


def repair_bars(df: pd.DataFrame) -> pd.DataFrame:
    """THE repair path: split-repair one ticker's RAW bars, carrying the factor to all legs.

    `split_adjust` recovers a share-split factor from the close series; §3 requires
    it to be carried to **open/high/low/close by DIVISION and to volume by
    MULTIPLICATION**, so repaired close×volume is invariant across the repair and a
    liquidity floor cannot move because a name split. The as-printed `raw_close` and
    `raw_dvol` ride along because the §3 price/liquidity floors are evaluated on the
    RAW prints, and `split_day` marks the factor STEP DAY, which is ineligible.

    This is the single function both `build_panel_w` and the full-series-vs-prefix
    parity gate call — a parity test against a re-implementation of the repair would
    prove nothing about the repair the study actually runs.
    """
    px = pd.to_numeric(df["close"], errors="coerce").dropna()
    factor = (px / split_adjust(px)).reindex(df.index).ffill().bfill()
    raw_c = pd.to_numeric(df["close"], errors="coerce")
    raw_v = pd.to_numeric(df["volume"], errors="coerce") if "volume" in df.columns \
        else pd.Series(np.nan, index=df.index)
    out = {"close": raw_c / factor, "volume": raw_v * factor,
           "raw_close": raw_c, "raw_dvol": raw_c * raw_v,
           "split_day": factor.diff().fillna(0.0).abs() > 1e-9}
    for c in ("open", "high", "low"):
        if c in df.columns:
            out[c] = pd.to_numeric(df[c], errors="coerce") / factor
    return pd.DataFrame(out).dropna(subset=["close"])


def _repair_arm_counts(
    segments: dict[str, pd.DataFrame],
    calendar: pd.DatetimeIndex,
) -> dict[str, int]:
    """EXT/episode accounting on only the names touched by the repair arm."""
    if not segments:
        return {"n_segments": 0, "n_ext_days": 0, "n_episodes": 0}
    legs = {c: _wide(segments, c).reindex(calendar) for c in W_PANEL_COLS}
    close = legs["close"]
    volume = legs["volume"]
    dvol = close * volume
    ext = ta.extended_mask(
        close, dvol, high_df=legs["high"], low_df=legs["low"],
        raw_close_df=legs["raw_close"], raw_dollar_vol_df=legs["raw_dvol"],
        split_day_df=legs["split_day"].fillna(False).astype(bool),
    )
    episodes = ta.extract_episodes(ext, close)
    return {
        "n_segments": int(len(segments)),
        "n_ext_days": int(ext.to_numpy().sum()),
        "n_episodes": int(len(episodes)),
    }


def _finish_panel(
    bars: dict[str, pd.DataFrame],
    cache: Path,
    tag: str,
    *,
    residual_up_ratio_break: float | None = None,
    ext_variant: str | None = None,
) -> dict:
    """Identity-segment a per-ticker store, widen it, and cache the frames.

    ``ext_variant`` stamps which §4.1 EXTENSION DEFINITION the cached content is
    downstream of. Panel content is upstream of every EXT mask — `repair_bars` and
    `split_identity_segments` read raw prints and tape gaps only, and the sole
    `extended_mask` call in this function feeds `meta["repair_impact"]` diagnostics,
    never a panel leg — so a panel is written with `None`, meaning "no extension
    definition entered this content". Anything a caller builds downstream of an EXT
    mask (episodes, races, cases, matching, estimates) must pass its arm name, and
    `_load_cached` then refuses a cache built under a different one.
    """
    calendar = pd.DatetimeIndex(sorted({d for b in bars.values() for d in b.index}))
    gap_segs = ta.split_identity_segments(bars, calendar)
    segs = ta.split_identity_segments(
        bars, calendar, residual_up_ratio_break=residual_up_ratio_break)
    gap_counts: dict[str, int] = {}
    final_counts: dict[str, int] = {}
    for s in gap_segs:
        tk = ta.segment_ticker(s)
        gap_counts[tk] = gap_counts.get(tk, 0) + 1
    for s in segs:
        tk = ta.segment_ticker(s)
        final_counts[tk] = final_counts.get(tk, 0) + 1
    gap_split = {tk for tk, n in gap_counts.items() if n > 1}
    residual_split = {tk for tk, n in final_counts.items()
                      if n > gap_counts.get(tk, 0)}
    n_split = len(gap_split)
    say(f"{tag}: {len(bars)} tickers -> {len(segs)} identity segments "
        f"({n_split} tickers split on a >60-session gap; "
        f"{len(residual_split)} on the residual-up rule)")
    panel = {c: _wide(segs, c) for c in W_PANEL_COLS}
    panel["close"] = panel["close"].reindex(calendar)
    for c in W_PANEL_COLS:
        if not panel[c].empty:
            panel[c] = panel[c].reindex(index=calendar, columns=panel["close"].columns)
            if c == "split_day":
                panel[c] = panel[c].fillna(False).astype(bool)
    cache.mkdir(parents=True, exist_ok=True)
    for c, fr in panel.items():
        if not fr.empty:
            fr.to_parquet(cache / f"panel_{c}.parquet")
    meta = {"n_tickers": len(bars), "n_segments": len(segs), "n_tickers_split": n_split,
            "n_split_factor_step_days": (int(panel["split_day"].to_numpy().sum())
                                         if not panel["split_day"].empty else 0),
            "residual_up_ratio_break": residual_up_ratio_break,
            "ext_variant": ext_variant,
            "n_tickers_residual_up_split": len(residual_split),
            "n_residual_up_breaks": int(len(segs) - len(gap_segs))}
    if residual_up_ratio_break is not None:
        pre_affected = {s: b for s, b in gap_segs.items()
                        if ta.segment_ticker(s) in residual_split}
        post_affected = {s: b for s, b in segs.items()
                         if ta.segment_ticker(s) in residual_split}
        pre_counts = _repair_arm_counts(pre_affected, calendar)
        post_counts = _repair_arm_counts(post_affected, calendar)
        meta["repair_arm"] = W_REPAIR_ARM
        meta["repair_impact"] = {
            "n_tickers_affected": len(residual_split),
            "n_additional_identity_segments": int(len(segs) - len(gap_segs)),
            "pre_repair_affected_names": pre_counts,
            "sanity_segmented_affected_names": post_counts,
            "removed_from_affected_names": {
                "n_ext_days": pre_counts["n_ext_days"] - post_counts["n_ext_days"],
                "n_episodes": pre_counts["n_episodes"] - post_counts["n_episodes"],
            },
        }
    (cache / "meta.json").write_text(json.dumps(meta, indent=2))
    return {"panel": panel, "meta": meta}


#: Legs a cache MUST carry to be usable. `raw_close`/`raw_dvol`/`split_day` are the
#: §3 floor inputs: a cache written before they existed would silently fall the
#: floors back to repaired prices — the exact leak §3 closes — so a cache missing
#: any of them is REBUILT, never partially loaded.
_REQUIRED_PANEL_LEGS = ("close", "raw_close", "raw_dvol", "split_day")


def _load_cached(
    cache: Path,
    *,
    residual_up_ratio_break: float | None = None,
    ext_variant: str | None = None,
) -> dict | None:
    if not (cache / "meta.json").exists():
        return None
    meta = json.loads((cache / "meta.json").read_text())
    # The stamp must be PRESENT and EQUAL. An absent stamp is a panel some other
    # line segmented: track D is gap-only here, so accepting an unstamped cache
    # would silently run D on whatever rule wrote it. A missing key is a mismatch.
    if "residual_up_ratio_break" not in meta \
            or meta["residual_up_ratio_break"] != residual_up_ratio_break:
        say(f"cache at {cache} carries identity rule "
            f"{meta.get('residual_up_ratio_break', meta.get('identity_rules', 'unstamped'))}"
            f", this track needs {residual_up_ratio_break} ({W_REPAIR_ARM} on W, "
            "gap-only on D) — rebuilding rather than seeding features from it")
        return None
    # W2 arm keying (TOPA_W2_PREREG §2). `None` is the STAMPED value of an
    # EXT-independent panel, not an absent stamp: `_finish_panel` never lets an
    # extension definition into panel content, so every panel ever written — before
    # or after this key existed — is honestly `None`. A caller asking for an arm's
    # downstream cache therefore mismatches a panel-only cache and rebuilds, which
    # is the hard-check the prereg asks for; a caller asking for the panel keeps its
    # cache hit and phase-0 behaviour is unchanged.
    if meta.get("ext_variant") != ext_variant:
        say(f"cache at {cache} was built under extension variant "
            f"{meta.get('ext_variant')!r}, this run needs {ext_variant!r} — rebuilding "
            "rather than reading an arm's episodes/races/cases off another arm's mask")
        return None
    missing = [c for c in _REQUIRED_PANEL_LEGS
               if not (cache / f"panel_{c}.parquet").exists()]
    if missing:
        say(f"cache at {cache} predates the raw-eligibility legs ({', '.join(missing)}) "
            "— rebuilding rather than running the floors on repaired prices")
        return None
    panel = {}
    for c in W_PANEL_COLS:
        p = cache / f"panel_{c}.parquet"
        panel[c] = pd.read_parquet(p) if p.exists() else pd.DataFrame()
    if not panel["split_day"].empty:
        panel["split_day"] = panel["split_day"].fillna(False).astype(bool)
    return {"panel": panel, "meta": meta}


# ══════════════════════════════════════════════════════════════════════════════
# §6 repair arm — what the PRE-REPAIR arm counted on fabricated extension
# ══════════════════════════════════════════════════════════════════════════════
def _read_panel(cache: Path) -> dict[str, pd.DataFrame]:
    """Raw panel read with NO identity-rule check — for auditing a pre-repair cache."""
    panel = {}
    for c in W_PANEL_COLS:
        f = cache / f"panel_{c}.parquet"
        panel[c] = pd.read_parquet(f) if f.exists() else pd.DataFrame()
    if not panel.get("split_day", pd.DataFrame()).empty:
        panel["split_day"] = panel["split_day"].fillna(False).astype(bool)
    return panel


def jump_table(close: pd.DataFrame,
               min_ratio: float = W_RESIDUAL_UP_RATIO_BREAK
               ) -> tuple[pd.DataFrame, dict[str, np.ndarray]]:
    """Every residual single-day up-ratio >= `min_ratio` in a repaired close panel.

    Returns the long table (segment / date / ratio / the two closes) and a
    segment -> bar-position map, which is what the contamination attribution needs
    to ask "was a fabricated bar inside this day's trailing 126 sessions?".
    """
    rows, pos_map = [], {}
    for col in close.columns:
        c = close[col]
        c = c[c.notna()]
        if len(c) < 2:
            continue
        br = ta.residual_up_break_positions(c, min_ratio=min_ratio)
        if br.size == 0:
            continue
        pos_map[col] = br
        v = c.to_numpy(dtype=float)
        for i in br:
            rows.append({"segment": col, "ticker": ta.segment_ticker(col),
                         "date": c.index[int(i)], "prev_close": float(v[int(i) - 1]),
                         "close": float(v[int(i)]),
                         "ratio": float(v[int(i)] / v[int(i) - 1])})
    cols = ["segment", "ticker", "date", "prev_close", "close", "ratio"]
    return pd.DataFrame(rows, columns=cols), pos_map


def _tape_contamination(close: pd.DataFrame, ext: pd.DataFrame,
                        pos_map: dict[str, np.ndarray]) -> dict:
    """Of the names EXTENDED on the last session, how many rode a fabricated bar?"""
    if close.empty or ext.empty:
        return {"tape_names_extended": 0, "tape_names_contaminated": 0, "tape_names": []}
    asof = close.index.max()
    row = ext.loc[asof]
    live = list(row.index[row.fillna(False).to_numpy(dtype=bool)])
    hit = []
    for col in live:
        jp = pos_map.get(col)
        if jp is None or jp.size == 0:
            continue
        c = close[col]
        c = c[c.notna()]
        if asof not in c.index:
            continue
        p = int(pd.Series(np.arange(len(c)), index=c.index)[asof])
        k = int(np.searchsorted(jp, p, side="right")) - 1
        if k >= 0 and (p - jp[k]) < 126:
            hit.append({"segment": col, "ticker": ta.segment_ticker(col),
                        "jump_date": str(pd.Timestamp(c.index[int(jp[k])]).date()),
                        "ratio": float(c.iloc[int(jp[k])] / c.iloc[int(jp[k]) - 1])})
    hit.sort(key=lambda r: -r["ratio"])
    return {"tape_asof": str(pd.Timestamp(asof).date()),
            "tape_names_extended": len(live),
            "tape_names_contaminated": len(hit),
            "tape_names": hit[:25]}


def run1_contamination_audit(cache: Path, *,
                             min_ratio: float = W_RESIDUAL_UP_RATIO_BREAK) -> dict:
    """Quantify what the PRE-REPAIR arm counted on fabricated extension (§6).

    Reads a panel exactly as run-1 segmented it (gap rule only), finds the residual
    up-jumps the split repair missed, and attributes run-1's own EXT days, episodes
    and matched cases to them. A day is CONTAMINATED when a fabricated bar sits
    inside its trailing 126 sessions — the window `r126` reads, and therefore the
    window that decides EXTENDED.

    Cases are re-derived without race labels (they only need episodes + peaks), so
    this audit costs one EXT/episode/peak pass rather than a second full pipeline.
    """
    if not (cache / "panel_close.parquet").exists():
        return {"available": False,
                "reason": f"no pre-repair panel at {cache} to audit"}
    meta_f = cache / "meta.json"
    meta = json.loads(meta_f.read_text()) if meta_f.exists() else {}
    # Two stamp formats have existed for the repaired rule; a cache carrying EITHER
    # holds no residual jumps by construction, and its zeros would read as
    # "run-1 was clean" — the opposite of the measurement. Fail closed on both.
    stamped = (meta.get("residual_up_ratio_break") is not None
               or (meta.get("identity_rules") or {}).get("jump_ratio") is not None
               or meta.get("repair_arm") is not None)
    if stamped:
        say("repair arm: the cached panel is already sanity-segmented — the "
            "contamination audit needs the PRE-REPAIR panel and is reported as "
            "unavailable rather than as a spurious zero")
        return {"available": False,
                "reason": ("the panel at this path was already rebuilt under the "
                           "sanity-segmented identity rules, so it contains no "
                           "residual jumps by construction; the pre-repair counts "
                           "stand as recorded in the first repaired run")}
    say(f"repair arm: auditing the PRE-REPAIR panel at {cache}")
    panel = _read_panel(cache)
    close = panel["close"]
    vol = panel.get("volume")
    dvol = (close * vol).reindex_like(close) if vol is not None and not vol.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    floors = {"raw_close_df": panel.get("raw_close"),
              "raw_dollar_vol_df": panel.get("raw_dvol"),
              "split_day_df": panel.get("split_day")}
    floors = {k: (v if v is not None and not v.empty else None) for k, v in floors.items()}

    jumps, pos_map = jump_table(close, min_ratio)
    if jumps.empty:
        # An unstamped cache can still be a repaired one. Zero jumps is what a
        # sanity-segmented panel looks like, so it is refused, not reported.
        say("repair arm: the cached panel carries no residual up-jumps at all — "
            "indistinguishable from a sanity-segmented panel; reported as unavailable")
        return {"available": False,
                "reason": ("the panel at this path carries no residual up-jumps at "
                           "all, which is exactly what a sanity-segmented panel looks "
                           "like by construction; a zero here is not a measurement "
                           "that the pre-repair arm was clean")}
    say(f"repair arm: {len(jumps)} residual >={min_ratio}x up-days on "
        f"{len(pos_map)} of {close.shape[1]} pre-repair segments")

    ext = ta.extended_mask(close, dvol, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    episodes = ta.extract_episodes(ext, close)
    episodes, dtp = ta.episode_peaks(close, episodes, ext)

    def _contaminated(col: str, dates) -> np.ndarray:
        """Which of `dates` on `col` had a fabricated bar in the trailing 126 sessions?"""
        jp = pos_map.get(col)
        c = close[col]
        c = c[c.notna()]
        p = pd.Series(np.arange(len(c)), index=c.index).reindex(dates).to_numpy(dtype=float)
        if jp is None or jp.size == 0:
            return np.zeros(len(p), dtype=bool)
        k = np.searchsorted(jp, p, side="right") - 1
        ok = k >= 0
        out = np.zeros(len(p), dtype=bool)
        out[ok] = (p[ok] - jp[k[ok]]) < 126
        return out

    n_ext_total = int(ext.to_numpy().sum())
    ext_hit, ext_on_seg = 0, 0
    bad_segments = set(pos_map)
    for col in close.columns:
        if col not in bad_segments or not bool(ext[col].any()):
            continue
        dates = ext.index[ext[col].fillna(False).to_numpy(dtype=bool)]
        ext_on_seg += len(dates)
        ext_hit += int(_contaminated(col, dates).sum())

    dtp = dtp.copy()
    dtp["bad"] = False
    for col, g in dtp.groupby("segment", sort=False):
        if col in bad_segments:
            dtp.loc[g.index, "bad"] = _contaminated(col, pd.DatetimeIndex(g["date"]))
    bad_eps = set(dtp.loc[dtp["bad"], "episode_id"])

    e1_eps = episodes[~episodes["micro"]]
    topped = set(e1_eps.loc[e1_eps["outcome"] == "TOPPED", "episode_id"])
    cases = dtp[dtp["episode_id"].isin(topped)
                & dtp["days_to_peak"].isin(ta.CASE_OFFSETS)]

    tape = _tape_contamination(close, ext, pos_map)
    out = {
        "available": True, "arm": "pre-repair (gap rule only)",
        "recomputed_this_run": True,
        "jump_ratio": float(min_ratio),
        "pre_repair_segments": int(close.shape[1]),
        "n_jump_days": int(len(jumps)),
        "n_segments_with_jump": int(len(bad_segments)),
        "max_ratio": float(jumps["ratio"].max()) if not jumps.empty else None,
        "top_offenders": _records(jumps.sort_values("ratio", ascending=False).head(15)),
        "run1_ext_days": n_ext_total,
        "run1_ext_days_on_jump_segments": int(ext_on_seg),
        "run1_ext_days_contaminated_r126": int(ext_hit),
        "run1_episodes": int(len(episodes)),
        "run1_episodes_contaminated": int(len(bad_eps)),
        "run1_topped_e1_episodes": int(len(topped)),
        "run1_topped_e1_episodes_contaminated": int(len(topped & bad_eps)),
        "run1_cases": int(len(cases)),
        "run1_cases_contaminated": int(cases["bad"].sum()),
        "run1_case_episodes": int(cases["episode_id"].nunique()),
        "run1_case_episodes_contaminated": int(
            cases.loc[cases["bad"], "episode_id"].nunique()),
        **tape,
    }
    say(f"repair arm: run-1 counted {out['run1_ext_days_contaminated_r126']:,} "
        f"contaminated EXT days ({out['run1_episodes_contaminated']:,} episodes, "
        f"{out['run1_cases_contaminated']:,} cases); "
        f"{out['tape_names_contaminated']} of {out['tape_names_extended']} "
        "today's-tape names carried a fabricated bar in their trailing 126 sessions")
    return out


def preserved_contamination(path: Path, live_reason: str | None = None) -> dict | None:
    """Carry the recorded pre-repair measurement when its panel no longer exists.

    Run-2 rebuilt `data/research/top_anatomy_p0_{W,D}` in place under the repaired
    identity rules, so the pre-repair panel cannot be re-read and the audit above
    can only report `available: False`. The numbers it produced survive in the
    preserved run-2 summary and are carried forward VERBATIM with provenance —
    never recomputed from a sanity-segmented panel, which would print zeros.
    """
    if not path.exists():
        return None
    try:
        block = json.loads(path.read_text()).get("repair_arm", {}).get("contamination")
    except Exception as exc:  # noqa: BLE001 — the audit trail never kills the run
        say(f"repair arm: could not read the preserved contamination block: {exc}")
        return None
    if not isinstance(block, dict) or not block.get("available"):
        return None
    out = dict(block)
    out["recomputed_this_run"] = False
    out["source_artifact"] = str(path.relative_to(_REPO))
    out["provenance"] = (
        "measured on run-1's panel, 2026-08-10, preserved artifact "
        f"{path.relative_to(_REPO)}; the pre-repair panel cache no longer exists on "
        "disk (run-2 rebuilt it in place under the repaired identity rules), so "
        "these counts are carried forward rather than recomputed")
    if live_reason:
        out["live_audit_unavailable_reason"] = live_reason
    say(f"repair arm: carrying the preserved run-1 contamination measurement from {path.name}")
    return out


def build_panel_w(data_root: Path, cache: Path, *, quick: int | None = None,
                  allow_stale: bool = False) -> dict:
    """Track W: split-repaired, identity-segmented wide OHLCV from `massive_stock_day`.

    The pre-filter is a strict SUPERSET of §3 eligibility — a name is dropped only
    when it can never clear a floor on ANY day (its whole-series maximum close is
    under $3, its best 21d median dollar volume is under $2M, or it has fewer bars
    than the 261 a single EXT day needs). Dropping on a per-day floor here would
    silently delete the population the study exists to measure.
    """
    # The store is R2-canonical and a local copy is an unmaintained mirror: this
    # track read a mirror frozen at 2026-07-02 for 5.5 weeks (audit 2026-08-10).
    # BEFORE the cache short-circuit — a cache built from a frozen store is equally
    # poisoned, and the cache hit is exactly the path that never touches the files.
    try:
        check_local_mirror_freshness(
            data_root, entrypoint="scripts/research_top_anatomy_phase0.py",
            allow_stale=allow_stale)
    except StaleLocalMirrorError:
        sys.exit(2)   # the banner names the lag and the fix; nothing to add
    cached = _load_cached(cache, residual_up_ratio_break=W_RESIDUAL_UP_RATIO_BREAK)
    if cached is not None:
        say(f"track W: panel cache hit at {cache} "
            f"({cached['meta']['n_segments']} segments)")
        return cached
    files = sorted((data_root / "massive_stock_day").glob("*.parquet"))
    if quick:
        files = files[:quick]
    say(f"track W: scanning {len(files)} ticker files in {data_root / 'massive_stock_day'}")
    keep: dict[str, pd.DataFrame] = {}
    # MF-10 left-edge census, counted EXACTLY during the scan (never sampled): the
    # study's survivorship honesty is RIGHT-edge honesty. A name whose tape is too
    # short to serve the 260-session history floor contributes zero observations,
    # and one that also died before the first possible EXT day is invisible to every
    # table in the report — including the "who is missing" section.
    left_edge = pd.Timestamp(W_EXT_LEFT_EDGE)
    drops = {"n_dropped_short_history": 0, "n_short_but_liquid": 0,
             "n_short_liquid_dead_before_ext_left_edge": 0}
    short_liquid_dead: list[str] = []
    for k, f in enumerate(files):
        if k and k % 2500 == 0:
            say(f"track W: ...{k}/{len(files)} scanned, {len(keep)} kept")
        try:
            df = pd.read_parquet(f)
        except Exception:  # noqa: BLE001 — one torn vendor file must not kill the scan
            continue
        if not {"close", "volume"} <= set(df.columns):
            continue
        df = df[~df.index.duplicated(keep="last")].sort_index()
        px = pd.to_numeric(df["close"], errors="coerce").dropna()
        vol = pd.to_numeric(df["volume"], errors="coerce").reindex(px.index)
        dv21 = (px * vol).rolling(21, min_periods=21).median() if len(px) >= 21 \
            else pd.Series(dtype=float)
        if len(px) < 261:
            drops["n_dropped_short_history"] += 1
            if float(px.max() if len(px) else 0.0) >= ta.MIN_CLOSE \
                    and bool(len(dv21) and dv21.max() >= ta.MIN_MEDIAN_DVOL21):
                drops["n_short_but_liquid"] += 1
                if px.index.max() < left_edge:
                    drops["n_short_liquid_dead_before_ext_left_edge"] += 1
                    if len(short_liquid_dead) < 12:
                        short_liquid_dead.append(f.stem)
            continue
        if float(px.max()) < ta.MIN_CLOSE:
            continue
        if not (dv21.max() >= ta.MIN_MEDIAN_DVOL21):
            continue
        frame = repair_bars(df)
        if len(frame) >= 261:
            keep[f.stem] = frame
    say(f"track W: {len(keep)} tickers pass the superset pre-filter; "
        f"{drops['n_dropped_short_history']} dropped under 261 bars "
        f"({drops['n_short_but_liquid']} of them once-liquid, "
        f"{drops['n_short_liquid_dead_before_ext_left_edge']} dead before "
        f"{W_EXT_LEFT_EDGE})")
    built = _finish_panel(keep, cache, "track W",
                          residual_up_ratio_break=W_RESIDUAL_UP_RATIO_BREAK)
    built["meta"]["left_edge_census"] = {
        "n_files_scanned": len(files), **drops,
        "ext_left_edge": W_EXT_LEFT_EDGE,
        "examples_short_liquid_dead": short_liquid_dead,
    }
    (cache / "meta.json").write_text(json.dumps(built["meta"], indent=2))
    return built


_D_RUNGS = (("baskets_ohlcv", "baskets/ohlcv"), ("yahoo", "yahoo"), ("data_stocks", "stocks"))


def build_panel_d(data_root: Path, cache: Path, *, quick: int | None = None) -> dict:
    """Track D: adjusted OHLCV on the `engine.price_ladder` rungs, FIRST-RUNG-WINS.

    The ladder contract is imported rather than restated (`price_ladder
    .ADJUSTED_SOURCES`), but the per-name read pulls OHLCV instead of close alone,
    since `resolve_close` returns only the close leg. Rungs carry different column
    sets — `yahoo` has no open/high/low, `data_stocks` has no open — so those
    features are NULL on those names and counted, never imputed.

    SURVIVORSHIP: this is a curated-current universe. Names that topped and died
    before basket curation are missing, so the topped arm is understated here. D
    is era CONTEXT and can never register a claim.
    """
    cached = _load_cached(cache)
    if cached is not None:
        say(f"track D: panel cache hit at {cache} "
            f"({cached['meta']['n_segments']} segments)")
        return cached
    assert price_ladder.ADJUSTED_SOURCES[:3] == tuple(s for s, _ in _D_RUNGS), \
        "the ladder's adjusted rung ORDER moved; re-read engine/price_ladder.py"
    names: list[str] = []
    for _, sub in _D_RUNGS:
        d = data_root / sub
        if d.exists():
            names.extend(p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_"))
    names = sorted(set(names))
    if quick:
        names = names[:quick]
    say(f"track D: {len(names)} names across the adjusted rungs")
    keep: dict[str, pd.DataFrame] = {}
    rung_counts = {src: 0 for src, _ in _D_RUNGS}
    for tk in names:
        for src, sub in _D_RUNGS:
            p = data_root / sub / f"{tk}.parquet"
            if not p.exists():
                continue
            try:
                df = pd.read_parquet(p)
            except Exception:  # noqa: BLE001
                continue
            col = next((c for c in ("close", "close_price") if c in df.columns), None)
            if col is None:
                continue
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.index = pd.to_datetime(df.index)
            df = df[df.index >= pd.Timestamp(D_START)]
            out = {"close": pd.to_numeric(df[col], errors="coerce")}
            for c in ("open", "high", "low", "volume"):
                if c in df.columns:
                    out[c] = pd.to_numeric(df[c], errors="coerce")
            # The D rungs are ALREADY split+dividend adjusted, so there is no repair
            # to carry and no factor step day: the as-printed leg IS the adjusted
            # leg. Stated rather than left implicit — a reader must be able to see
            # that raw-level eligibility means something different on this track.
            out["raw_close"] = out["close"]
            out["raw_dvol"] = out["close"] * out.get(
                "volume", pd.Series(np.nan, index=df.index))
            out["split_day"] = pd.Series(False, index=df.index)
            frame = pd.DataFrame(out).dropna(subset=["close"])
            if len(frame) >= 261:
                keep[tk] = frame
                rung_counts[src] += 1
            break                       # first-rung-wins, per the frozen ladder
    say(f"track D: {len(keep)} names kept; rungs {rung_counts}")
    res = _finish_panel(keep, cache, "track D")
    res["meta"]["rung_counts"] = rung_counts
    (cache / "meta.json").write_text(json.dumps(res["meta"], indent=2))
    return res


# ══════════════════════════════════════════════════════════════════════════════
# assembly helpers
# ══════════════════════════════════════════════════════════════════════════════
def _segment_bars(panel: dict[str, pd.DataFrame], segments) -> dict[str, pd.DataFrame]:
    """Per-segment OHLCV frames (each compacted to its own bars) for the feature library."""
    close = panel["close"]
    out = {}
    for s in segments:
        c = close[s]
        c = c[c.notna()]
        if c.empty:
            continue
        d = {"close": c}
        for col in ("open", "high", "low", "volume"):
            fr = panel.get(col)
            if fr is not None and not fr.empty and s in fr.columns:
                d[col] = fr[s].reindex(c.index)
        out[s] = pd.DataFrame(d)
    return out


def _gate_context(close: pd.DataFrame, dvol: pd.DataFrame) -> pd.DataFrame:
    """r126 / rv63 / dvol21 at every bar — the matching gates, computed once."""
    frames = []
    for col in close.columns:
        c = close[col]
        c = c[c.notna()]
        if len(c) < 130:
            continue
        lr = np.log(c).diff()
        dv = dvol[col].reindex(c.index) if col in dvol.columns else pd.Series(np.nan, index=c.index)
        frames.append(pd.DataFrame({
            "segment": col, "ticker": ta.segment_ticker(col), "date": c.index,
            "r126": (c / c.shift(126) - 1.0).to_numpy(),
            "rv63": (lr.rolling(63, min_periods=63).std() * np.sqrt(252.0)).to_numpy(),
            "dvol21": dv.rolling(21, min_periods=21).median().to_numpy(),
        }))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _pick(df: pd.DataFrame, keys: pd.DataFrame) -> pd.DataFrame:
    """Left-join `df`'s VALUE columns onto the (segment, date) rows in `keys`.

    Only columns `keys` does not already carry are joined, so a shared label like
    `ticker` can never split into `ticker_x`/`ticker_y` and silently break a
    downstream contract.
    """
    take = ["segment", "date"] + [c for c in df.columns
                                  if c not in ("segment", "date") and c not in keys.columns]
    return keys.merge(df[take], on=["segment", "date"], how="left")


def _describe(x) -> dict:
    s = pd.Series(x, dtype="float64").dropna()
    if s.empty:
        return {"n": 0, "median": None, "p25": None, "p75": None, "mean": None}
    return {"n": int(len(s)), "median": float(s.median()),
            "p25": float(s.quantile(0.25)), "p75": float(s.quantile(0.75)),
            "mean": float(s.mean())}


# ══════════════════════════════════════════════════════════════════════════════
# §3 hard pre-run gate: a future split may not move a past feature value
# ══════════════════════════════════════════════════════════════════════════════
def _parity_side(rep: pd.DataFrame, d: pd.Timestamp, eqw: pd.Series,
                 cross_returns: pd.DataFrame | None = None) -> pd.DataFrame:
    """One side of the parity check: features at d, with the EPISODE anchor rebuilt
    from that side's own bars and the cross-section held fixed.

    The episode context is rebuilt per side on purpose — an episode-anchored feature
    (F1/F2/F5) reading a boundary that moved would fail here. The equal-weight index
    is deliberately NOT rebuilt per side: it compounds the per-day CROSS-SECTIONAL
    MEDIAN DAILY RETURN over thousands of names, and repairing one name's splits
    rescales that name's closes by a constant, which leaves its returns — and
    therefore the index — untouched. Rebuilding it from the single name under test
    would instead make `rs_line = c / index` a degenerate near-constant whose
    63-session argmax is decided by float noise, and the gate would fail on E3f/E4f
    for a reason that has nothing to do with the repair (measured on ABVE, 2026-08).
    The RS family is still fully exercised: `rs_line` carries the split factor, so a
    broken carry would still move E5f's log-slope and E3f's lag.
    """
    close = pd.DataFrame({"T": rep["close"]})
    dvol = pd.DataFrame({"T": rep["close"] * rep.get("volume", np.nan)})
    floors = {"raw_close_df": pd.DataFrame({"T": rep["raw_close"]}),
              "raw_dollar_vol_df": pd.DataFrame({"T": rep["raw_dvol"]}),
              "split_day_df": pd.DataFrame({"T": rep["split_day"]})}
    ext = ta.extended_mask(close, dvol, high_df=pd.DataFrame({"T": rep["high"]})
                           if "high" in rep else None,
                           low_df=pd.DataFrame({"T": rep["low"]}) if "low" in rep else None,
                           **floors)
    eps = ta.extract_episodes(ext, close)
    return ta.feature_library({"T": rep}, eqw, {"T": [d]}, episodes=eps,
                              cross_sectional_returns=cross_returns)


def prefix_parity_report(bars: pd.DataFrame, d: pd.Timestamp,
                         eqw: pd.Series | None = None,
                         cross_returns: pd.DataFrame | None = None) -> pd.DataFrame:
    """Feature values at d computed from the FULL series vs from a prefix ending at d+1.

    Both sides go through `repair_bars`, the real repair path. The prefix cannot see
    any split after d+1, so its recovered factor differs from the full series' factor
    at every bar ≤ d — if a feature value at d moves with it, that feature is reading
    the future through the repair, and no matched contrast built on it would mean
    anything. ``eqw`` is the track's cross-section, identical on both sides (see
    `_parity_side`). Returns one row per feature with both values and their gap.
    """
    idx = bars.index
    pos = int(idx.searchsorted(pd.Timestamp(d)))
    a = _parity_side(repair_bars(bars), d, eqw, cross_returns)
    b = _parity_side(repair_bars(bars.iloc[:min(pos + 2, len(idx))]), d, eqw,
                     cross_returns)
    rows = []
    for f in ta.FEATURES:
        va = float(a[f].iloc[0]) if len(a) else float("nan")
        vb = float(b[f].iloc[0]) if len(b) else float("nan")
        both_null = not np.isfinite(va) and not np.isfinite(vb)
        gap = 0.0 if both_null else abs(va - vb)
        rows.append({"feature": f, "family": ta.FEATURE_FAMILY[f], "full": va,
                     "prefix": vb, "abs_gap": gap, "null_both": both_null})
    return pd.DataFrame(rows)


def assert_prefix_parity(panel: dict, track: str, eqw: pd.Series,
                         cross_returns: pd.DataFrame | None = None, *,
                         n_names: int = PARITY_SAMPLE_NAMES,
                         tol: float = PARITY_TOLERANCE) -> dict:
    """§3 HARD GATE — run the parity check on sampled names and raise before experiments.

    The synthetic version of this lives in `tests/test_top_anatomy.py`; this is the
    runtime half, so the gate also fires on REAL bars with real vendor splits. It runs
    before a single label is computed: a repair that leaks the future must stop the
    run, not appear as a footnote under a result.
    """
    close = panel["close"]
    step = panel.get("split_day")
    cands = []
    if step is not None and not step.empty:                 # prefer names that split
        cands = list(step.columns[step.fillna(False).any().to_numpy()])
    pool = [c for c in cands if close[c].notna().sum() > 400]
    pool += [c for c in close.columns if c not in pool and close[c].notna().sum() > 400]
    checked, worst = [], 0.0
    for seg in pool[:n_names]:
        c = close[seg]
        c = c[c.notna()]
        bars = pd.DataFrame({
            "close": panel["raw_close"][seg].reindex(c.index)
            if not panel.get("raw_close", pd.DataFrame()).empty else c,
            "volume": (panel["raw_dvol"][seg].reindex(c.index)
                       / panel["raw_close"][seg].reindex(c.index))
            if not panel.get("raw_dvol", pd.DataFrame()).empty
            else pd.Series(np.nan, index=c.index),
        }).dropna(subset=["close"])
        if len(bars) < 400:
            continue
        d = bars.index[int(len(bars) * 0.7)]
        rep = prefix_parity_report(bars, d, eqw, cross_returns)
        bad = rep[(rep["abs_gap"] > tol) & rep["abs_gap"].notna()]
        worst = max(worst, float(rep["abs_gap"].max(skipna=True) or 0.0))
        if not bad.empty:
            raise AssertionError(
                f"§3 prefix-parity gate FAILED on track {track} segment {seg} at "
                f"{pd.Timestamp(d).date()}: "
                + ", ".join(f"{r.feature} full={r.full!r} prefix={r.prefix!r}"
                            for r in bad.itertuples())
                + " — a future split is moving a past feature value; stop and fix the "
                  "repair carry before reading any outcome.")
        checked.append({"segment": seg, "asof": str(pd.Timestamp(d).date()),
                        "n_features_compared": int((~rep["null_both"]).sum()),
                        "max_abs_gap": float(rep["abs_gap"].max())})
    say(f"[{track}] §3 prefix-parity gate PASSED on {len(checked)} name(s); "
        f"worst |gap| = {worst:.3g}")
    return {"passed": True, "tolerance": tol, "n_names_checked": len(checked),
            "worst_abs_gap": worst, "names": checked}


def _instrument_census(panel: dict, ext: pd.DataFrame, elig: pd.DataFrame,
                       n_files: int) -> dict:
    """§3 — PRINT the instrument/dead-name census instead of inferring it from a file count."""
    close = panel["close"]
    if close.empty:
        return {"n_files_scanned": n_files, "n_segments": 0}
    last_day = close.index.max()
    cutoff = close.index[max(0, len(close.index) - 61)]
    lasts = close.apply(lambda s: s.last_valid_index())
    dead = lasts[lasts.notna() & (lasts < cutoff)]
    dead_with_ext = [s for s in dead.index if s in ext.columns and bool(ext[s].any())]
    return {
        "n_files_scanned": int(n_files),
        "n_tickers_kept": int(len({ta.segment_ticker(c) for c in close.columns})),
        "n_segments": int(close.shape[1]),
        "n_segments_ever_eligible": int((elig.sum() > 0).sum()),
        "n_segments_with_ext": int((ext.sum() > 0).sum()),
        "last_panel_day": str(last_day.date()),
        "dead_cutoff_last_bar_before": str(pd.Timestamp(cutoff).date()),
        "n_segments_candidate_dead": int(len(dead)),
        "n_candidate_dead_with_ext_day": int(len(dead_with_ext)),
        "share_candidate_dead": (float(len(dead) / close.shape[1])
                                 if close.shape[1] else 0.0),
    }


# ══════════════════════════════════════════════════════════════════════════════
# the track pipeline
# ══════════════════════════════════════════════════════════════════════════════
def run_track(track: str, panel: dict, meta: dict, *, seed: int, quick: bool,
              n_files: int = 0) -> dict:
    """EXT -> episodes -> race -> peaks -> cases/controls -> features -> E1..E4."""
    close = panel["close"]
    volume = panel.get("volume")
    dvol = (close * volume).reindex_like(close) if volume is not None and not volume.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    raw_close = panel.get("raw_close")
    raw_dvol = panel.get("raw_dvol")
    split_day = panel.get("split_day")
    floors = {"raw_close_df": raw_close if raw_close is not None and not raw_close.empty
              else None,
              "raw_dollar_vol_df": raw_dvol if raw_dvol is not None and not raw_dvol.empty
              else None,
              "split_day_df": split_day if split_day is not None and not split_day.empty
              else None}
    out: dict = {"track": track, "panel": dict(meta)}
    out["panel"].update({
        "n_sessions": int(close.shape[0]), "n_segments": int(close.shape[1]),
        "first_session": str(close.index.min().date()) if len(close) else None,
        "last_session": str(close.index.max().date()) if len(close) else None,
        "floors_on_raw_prints": floors["raw_close_df"] is not None,
    })

    # §3 eligibility and the PIT cross-section come first — neither is an outcome —
    # then the HARD GATE, before a single label exists.
    elig = ta.eligibility_mask(close, dvol, **floors)
    min_cross_names = 20 if not quick else 1
    eqw = ta.equal_weight_median_index(close, elig, min_names=min_cross_names)
    cross_returns = ta.cross_sectional_median_returns(
        close, elig, min_names=min_cross_names)
    out["prefix_parity_gate"] = assert_prefix_parity(
        panel, track, eqw, cross_returns)

    say(f"[{track}] EXT mask (primary; floors on raw prints, split-step days excluded)")
    ext = ta.extended_mask(close, dvol, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    n_ext = int(ext.to_numpy().sum())
    per_day = ext.sum(axis=1)
    out["ext"] = {"n_ext_days": n_ext,
                  "n_eligible_days": int(elig.to_numpy().sum()),
                  "n_segments_with_ext": int((ext.sum() > 0).sum()),
                  # The left edge is a STRUCTURAL fact, not a data gap: the history
                  # floor is served inside a segment, so the store's opening months
                  # can hold no EXT day at all and no era table may claim them.
                  "first_ext_day": (str(per_day[per_day > 0].index.min().date())
                                    if bool((per_day > 0).any()) else None),
                  "n_sessions_zero_ext": int((per_day == 0).sum()),
                  "pct_sessions_zero_ext": (round(100.0 * float((per_day == 0).mean()), 1)
                                            if len(per_day) else None)}
    out["census"] = _instrument_census(panel, ext, elig, n_files)
    say(f"[{track}] {n_ext} EXT days on {out['ext']['n_segments_with_ext']} segments")
    c = out["census"]
    say(f"[{track}] census: {c.get('n_files_scanned')} files scanned · "
        f"{c.get('n_tickers_kept')} tickers · {c.get('n_segments')} segments · "
        f"{c.get('n_segments_ever_eligible')} ever-eligible · "
        f"{c.get('n_segments_candidate_dead')} candidate-dead (last bar before "
        f"{c.get('dead_cutoff_last_bar_before')}) · "
        f"{c.get('n_candidate_dead_with_ext_day')} of those held >=1 EXT day")

    say(f"[{track}] sensitivity arms (report-only)")
    out["ext_variants"] = {"primary": n_ext}
    for variant in ("r63", "atrz"):
        try:
            m = ta.extended_mask(close, dvol, variant=variant, high_df=panel.get("high"),
                                 low_df=panel.get("low"), **floors)
            out["ext_variants"][variant] = int(m.to_numpy().sum())
            out["ext_variants"][f"{variant}_overlap_with_primary"] = int(
                (m & ext).to_numpy().sum())
        except Exception as exc:  # noqa: BLE001 — a report-only arm never kills the run
            out["ext_variants"][variant] = None
            out["ext_variants"][f"{variant}_error"] = str(exc)

    if n_ext == 0:
        out["null_reason"] = "no EXT days on this track"
        return out

    say(f"[{track}] episodes")
    episodes = ta.extract_episodes(ext, close)
    out["episodes"] = {
        "n_episodes": int(len(episodes)),
        "n_micro_under_5_ext_days": int(episodes["micro"].sum()),
        "n_e1_eligible": int((~episodes["micro"]).sum()),
        "n_names": int(episodes["ticker"].nunique()),
        "ext_days_per_episode": _describe(episodes["n_ext_days"]),
    }
    say(f"[{track}] {len(episodes)} episodes "
        f"({int(episodes['micro'].sum())} micro) on {episodes['ticker'].nunique()} names")

    say(f"[{track}] race labels")
    race = ta.race_labels(close, ext)
    counts = race["label"].value_counts().to_dict()
    out["race"] = {
        "counts": {k: int(v) for k, v in counts.items()},
        "censor_reasons": {k: int(v) for k, v in
                           race.loc[race["label"] == "CENSORED", "censor_reason"]
                           .value_counts().to_dict().items()},
        "sessions_to_resolve": _describe(race["sessions_to_resolve"]),
        "fwd_ret_63_by_label": {
            k: _describe(g["fwd_ret_63"]) for k, g in race.groupby("label")},
    }
    say(f"[{track}] race: {out['race']['counts']}")

    say(f"[{track}] episode peaks")
    episodes, dtp = ta.episode_peaks(close, episodes, ext)
    out["episodes"]["outcomes"] = {k: int(v) for k, v in
                                   episodes["outcome"].value_counts().to_dict().items()}
    out["episodes"]["n_peak_window_censored"] = int(episodes["peak_window_censored"].sum())
    # Peak-window censoring is not spread evenly: an episode peaking inside the last
    # PEAK_SEAL_WINDOW sessions can only be sealed TOPPED if its -20% prints before
    # the tape ends, so the right edge selects for FAST toppers and censors the rest.
    _cens = episodes[episodes["peak_window_censored"]]
    _last = close.index.max()
    _cut = (close.index[-ta.PEAK_SEAL_WINDOW] if len(close.index) > ta.PEAK_SEAL_WINDOW
            else close.index.min())
    out["episodes"]["peak_window_censored_by_year"] = {
        str(k): int(v) for k, v in
        sorted(pd.to_datetime(_cens["peak_date"]).dt.year.value_counts().to_dict().items())}
    # `_cut` is the PEAK_SEAL_WINDOW-th session from the end, so an episode peaking
    # ON it already has fewer than a full sealing window behind it: the boundary is
    # inclusive, and the printed wording must say "on or after" to match the count.
    out["episodes"]["right_edge_selection"] = {
        "seal_window": ta.PEAK_SEAL_WINDOW,
        "peaks_on_or_after": str(_cut.date()),
        "last_session": str(_last.date()),
        "n_censored_peaking_in_seal_window": int(
            (pd.to_datetime(_cens["peak_date"]) >= _cut).sum()),
    }
    out["episodes"]["days_to_peak"] = _describe(dtp["days_to_peak"])
    topped_eps = episodes[(episodes["outcome"] == "TOPPED") & (~episodes["micro"])]
    out["episodes"]["n_topped_e1_eligible"] = int(len(topped_eps))
    say(f"[{track}] episode outcomes {out['episodes']['outcomes']}; "
        f"{len(topped_eps)} TOPPED and E1-eligible")

    # ── case / control assembly (§4.5) ───────────────────────────────────────
    gates = _gate_context(close, dvol)
    e1_eps = set(episodes.loc[~episodes["micro"], "episode_id"])
    dtp_e1 = dtp[dtp["episode_id"].isin(e1_eps)]
    topped_ids = set(topped_eps["episode_id"])

    cases = dtp_e1[dtp_e1["episode_id"].isin(topped_ids)
                   & dtp_e1["days_to_peak"].isin(ta.CASE_OFFSETS)].copy()
    cases["offset"] = cases["days_to_peak"]
    cases["case_id"] = (cases["episode_id"] + "@" + cases["offset"].astype(str))
    out["cases"] = {
        "n_cases": int(len(cases)),
        "per_offset": {int(k): int(v) for k, v in
                       cases["offset"].value_counts().to_dict().items()},
        "n_case_episodes": int(cases["episode_id"].nunique()),
    }

    # Controls are ALL EXT days whose day-level race CONTINUED. The five-EXT-day
    # floor applies to case episodes only; excluding continued days merely because
    # they live in micro-spells would change the frozen control population.
    pool = race[race["label"] == "CONTINUED"][["segment", "ticker", "date"]].copy()
    pool["case_id"] = ["p%d" % i for i in range(len(pool))]
    out["cases"]["n_control_candidates"] = int(len(pool))

    cases = _pick(gates, cases).dropna(subset=["r126", "rv63", "dvol21"])
    pool = _pick(gates, pool).dropna(subset=["r126", "rv63", "dvol21"])
    say(f"[{track}] {len(cases)} cases vs {len(pool)} CONTINUED control candidates")

    pairs, diag = ta.matched_controls(cases, pool)
    out["matching"] = diag
    say(f"[{track}] matched {diag['n_matched']}/{diag['n_cases']} cases "
        f"({diag['n_pairs']} pairs, {diag['n_dropped_no_control']} dropped)")

    # ── the days features are actually needed on ─────────────────────────────
    ext_long = race[["segment", "ticker", "date"]].copy()
    # §4.7 pins E1b to ALL EXT days. A systematic 1-in-k shortcut changes both the
    # day-level AUC population and the top-ruler fire set, so feature every EXT day.
    e1b_days = ext_long.copy()
    e3_days = dtp[dtp["episode_id"].isin(topped_ids)][["segment", "ticker", "date"]]
    e2_days = _pick(gates, _e2_case_days(dtp_e1, topped_ids)) \
        .dropna(subset=["r126", "rv63", "dvol21"])
    ctrl_days = (pairs[["control_segment", "control_ticker", "control_date"]]
                 .set_axis(["segment", "ticker", "date"], axis=1)
                 if not pairs.empty else
                 pd.DataFrame(columns=["segment", "ticker", "date"]))
    need = pd.concat([
        cases[["segment", "ticker", "date"]], ctrl_days,
        e1b_days[["segment", "ticker", "date"]], e3_days,
        e2_days[["segment", "ticker", "date"]],
    ], ignore_index=True).drop_duplicates(["segment", "date"])
    say(f"[{track}] features on {len(need)} (segment, day) points "
        f"({len(e1b_days)} ALL-EXT rows for E1b/ruler)")

    bars = _segment_bars(panel, sorted(set(need["segment"])))
    feats = ta.feature_library(
        bars, eqw, need[["segment", "date"]], episodes=episodes,
        cross_sectional_returns=cross_returns)
    out["feature_coverage"] = {
        f: float(feats[f].notna().mean()) for f in ta.FEATURES if f in feats.columns}
    out["feature_coverage_floor"] = COVERAGE_FLOOR
    out["features_below_coverage_floor"] = sorted(
        f for f, c in out["feature_coverage"].items() if c < COVERAGE_FLOOR)

    # ── E1 (EPISODE-FIRST, §4.5) ─────────────────────────────────────────────
    say(f"[{track}] E1 matched deltas -> episode-first aggregation -> "
        f"episode-peak-month bootstrap (B={ta.BOOTSTRAP_B})")
    case_deltas = ta.matched_deltas(pairs, feats)
    ep_deltas = ta.episode_deltas(case_deltas, cases, episodes)
    e1 = ta.matched_delta_stats(ep_deltas, b=ta.BOOTSTRAP_B if not quick else 400,
                                seed=seed, coverage_floor=COVERAGE_FLOOR)
    n_months = (int(pd.to_datetime(ep_deltas["peak_date"]).dt.to_period("M").nunique())
                if not ep_deltas.empty else 0)
    out["e1"] = {
        "aggregation": "episode-first (median over the episode's {21,10,5} snapshots)",
        "n_case_sets": int(len(case_deltas)),
        "n_episodes": int(len(ep_deltas)),
        "n_distinct_peak_months": n_months,
        "min_peak_months_required": ta.MIN_EPISODE_MONTHS,
        "min_finite_controls": ta.MIN_FINITE_CONTROLS,
        "snapshots_per_episode": _describe(ep_deltas["n_snapshots"])
        if not ep_deltas.empty else _describe([]),
        "table": _records(e1),
        "n_separating": int(e1["separates"].sum()) if not e1.empty else 0,
        "separating": sorted(e1.loc[e1["separates"], "feature"]) if not e1.empty else [],
        "registered_separating": sorted(e1.loc[e1["grade"] == "REGISTERED", "feature"])
        if not e1.empty else [],
        "exploratory_separating": sorted(
            e1.loc[e1["grade"] == "EXPLORATORY-DISCOVERY", "feature"]) if not e1.empty else [],
        "by_family": ({fam: {"n_tested": int(len(g)), "n_separating": int(g["separates"].sum())}
                       for fam, g in e1.groupby("family")} if not e1.empty else {}),
    }
    say(f"[{track}] E1: {out['e1']['n_separating']} of {len(ta.FEATURES)} separate "
        f"(N = {len(ep_deltas)} episodes / {len(case_deltas)} case-sets, "
        f"{n_months} peak-months vs the {ta.MIN_EPISODE_MONTHS} required)")

    # ── E1b ──────────────────────────────────────────────────────────────────
    say(f"[{track}] E1b pooled AUC increment")
    out["e1b"] = _e1b(feats, race, episodes, e1b_days, close.index,
                       seed=seed, quick=quick)

    # ── E2 / E3 / E4 ─────────────────────────────────────────────────────────
    survivors = out["e1"]["separating"]
    # §2/§4.8: the control tail is DIRECTION-ALIGNED; an exploratory field has no
    # declared risk side, so its OBSERVED sign picks the tail (discovery-only).
    obs = ({r["feature"]: r["median_delta"] for r in out["e1"]["table"]}
           if out["e1"]["table"] else {})
    grades = ({r["feature"]: r.get("grade", "") for r in out["e1"]["table"]}
              if out["e1"]["table"] else {})
    say(f"[{track}] E2 lead-time profiles on {len(survivors)} survivor(s)")
    out["e2"] = _e2(e2_days, pool, feats, survivors, episodes, grades,
                    seed=seed, quick=quick)
    # The wrong-sign exhibits carry mechanical counter-explanations (a case day
    # anchored near the episode argmax; a rising leg by construction; length-biased
    # day-weighted controls). The four-window profile is what discriminates: a PURE
    # anchor artefact strengthens monotonically toward the peak. Same machinery as
    # the survivors' profile, so the two tables are read on one scale.
    wrong_sign = [f for f in WRONG_SIGN_EXHIBITS if f in feats.columns]
    if wrong_sign:
        say(f"[{track}] E2 four-window profile on {len(wrong_sign)} wrong-sign exhibit(s)")
        out["e2_wrong_sign"] = _e2(e2_days, pool, feats, wrong_sign, episodes, {},
                                   seed=seed, quick=quick)
    say(f"[{track}] E3 ordering")
    out["e3"] = _e3(feats, dtp, topped_ids, pool, survivors, obs)
    say(f"[{track}] E4 era / dollar-volume stability")
    out["e4"] = _e4(ep_deltas, gates, cases, survivors,
                    W_ERAS if track == "W" else D_ERAS, seed=seed, quick=quick)

    # ── the ruler (§2) ───────────────────────────────────────────────────────
    say(f"[{track}] top ruler on survivor legs")
    out["ruler"] = _ruler(feats, ext, episodes, close, pool, survivors, obs,
                           seed=seed, quick=quick)

    # ── G0.2 + today's tape ──────────────────────────────────────────────────
    out["g0_2_delisting"] = _delisting_check(close, episodes)
    out["today_tape"] = _today_tape(close, ext, feats, bars, eqw, cross_returns,
                                     episodes, gates, ruler=out["ruler"])
    out["episodes_table_sample"] = _records(
        episodes.sort_values("n_ext_days", ascending=False).head(25)
        [["episode_id", "ticker", "start", "end", "n_ext_days", "peak_date",
          "peak_close", "outcome", "peak_window_censored"]])
    return out


def _records(df: pd.DataFrame) -> list[dict]:
    """JSON-safe records (timestamps to ISO dates, numpy scalars to python)."""
    if df is None or df.empty:
        return []
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_datetime64_any_dtype(d[c]):
            d[c] = d[c].dt.strftime("%Y-%m-%d")
    return json.loads(d.to_json(orient="records"))


def _e2_case_days(dtp_e1: pd.DataFrame, topped_ids: set) -> pd.DataFrame:
    """The E2 lead-time case set: up to 2 EXT days per (TOPPED episode, bucket).

    §4.5's three registered offsets populate only two of §4.8's four buckets, so the
    lead-time PROFILE (a descriptive read, no new test) needs days sampled across
    all four. Sampling is deterministic — the earliest days in each bucket.
    """
    d = dtp_e1[dtp_e1["episode_id"].isin(topped_ids)].copy()
    if d.empty:
        return d.assign(bucket=None, case_id=None)
    # §4.8 windows are stated POSITIVE-BEFORE-PEAK, so the bucket variable IS
    # days_to_peak (= peak_date − d): +22..+63 EARLY through 0..−5 POST-TOP.
    lab = []
    for lo, hi in E2_BUCKETS:
        g = d[(d["days_to_peak"] >= lo) & (d["days_to_peak"] <= hi)].copy()
        g["bucket"] = _bucket_tag(lo, hi)
        lab.append(g.sort_values("days_to_peak", ascending=False)
                   .groupby("episode_id", as_index=False).head(2))
    out = pd.concat(lab, ignore_index=True) if lab else d.head(0)
    out["case_id"] = (out["episode_id"] + "@" + out["bucket"] + "@"
                      + out["days_to_peak"].astype(str))
    return out


def _bucket_tag(lo: int, hi: int) -> str:
    """`+22..+63` style tag — days BEFORE the peak read positive (§4.8, entry (a))."""
    return f"{hi:+d}..{lo:+d}" if lo > 0 else f"{hi:+d}..{lo:+d}"


def _episode_block_ci(y: np.ndarray, p: np.ndarray, blocks: np.ndarray, auc_fn,
                      *, b: int, seed: int, paired: np.ndarray | None = None) -> dict:
    """95% percentile CI for an AUC (and, when `paired` is given, for the ΔAUC).

    Resamples EPISODE blocks with replacement: EXT days inside one episode are the
    same event looked at repeatedly, so a row-level interval would be a fiction. The
    ΔAUC uses the SAME draws as the two AUCs, which is what makes it a paired
    interval rather than two independent ones subtracted.
    """
    rng = np.random.default_rng(seed)
    keys, inv = np.unique(blocks, return_inverse=True)
    members = [np.flatnonzero(inv == i) for i in range(len(keys))]
    k = len(members)
    if k < 5:
        return {"ci_lo": None, "ci_hi": None, "n_blocks": int(k),
                "reason": "fewer than 5 episode blocks"}
    a_draws, d_draws = [], []
    for _ in range(b):
        idx = np.concatenate([members[j] for j in rng.integers(0, k, k)])
        if len(np.unique(y[idx])) < 2:
            continue
        a_draws.append(auc_fn(y[idx], p[idx]))
        if paired is not None:
            d_draws.append(a_draws[-1] - auc_fn(y[idx], paired[idx]))
    if len(a_draws) < 50:
        return {"ci_lo": None, "ci_hi": None, "n_blocks": int(k),
                "reason": "too few two-class resamples"}
    lo, hi = np.percentile(a_draws, [2.5, 97.5])
    out = {"ci_lo": float(lo), "ci_hi": float(hi), "n_blocks": int(k)}
    if d_draws:
        dlo, dhi = np.percentile(d_draws, [2.5, 97.5])
        out["delta_ci_lo"], out["delta_ci_hi"] = float(dlo), float(dhi)
    return out


def _e1b(feats: pd.DataFrame, race: pd.DataFrame, episodes: pd.DataFrame,
        ext_days: pd.DataFrame, calendar: pd.DatetimeIndex, *, seed: int,
        quick: bool = False) -> dict:
    """§4.7 pooled increment: NESTED M0 ⊂ M1 ⊂ M2, two CV schemes, episode-block CIs.

    M0 = r126 alone. M1 = M0 + the rv63 realized-volatility nuisance control.
    M2 = M1 + the other 35 frozen features (r126 appears once). The models are
    NESTED on purpose: the question is what the library adds over extension AND
    volatility, so M1 is the baseline that must be beaten, not M0.

    Leakage discipline (§4.7): every fold fits its median-imputer and its
    standardization on TRAINING ROWS ONLY — they live inside the sklearn Pipeline,
    so a test row can never contribute to its own scaling. No missingness
    indicators, no full-sample preprocessing, and rows are IMPUTED rather than
    dropped (dropping every incomplete row is itself a full-sample decision, and it
    silently deletes the thin-coverage names the study cares about).

    CV-A: 5-fold grouped by RAW TICKER, so every identity segment of a reused ticker
    stays on one side. CV-B: expanding walk-forward by calendar quarter with a
    250-SESSION purge between train end and test start — the full race-label
    horizon, because a training row's label can be resolved by bars up to 250
    sessions later and anything shorter trains on the test window's own outcome.

    Descriptive: E1b creates no registered test. AUCs and the paired ΔAUC carry
    episode-block bootstrap CIs.
    """
    try:
        from sklearn.impute import SimpleImputer
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import roc_auc_score
        from sklearn.model_selection import GroupKFold
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import StandardScaler
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(
            "E1b is a frozen required experiment; install repository requirements "
            f"before running TOPA (scikit-learn import failed: {exc})") from exc

    lab = race[race["label"].isin(("TOPPED", "CONTINUED"))][
        ["segment", "ticker", "date", "label"]]
    d = ext_days[["segment", "date"]].merge(lab, on=["segment", "date"], how="inner")
    d = d.merge(feats, on=["segment", "date"], how="left", suffixes=("", "_f"))
    d["y"] = (d["label"] == "TOPPED").astype(int)
    if d.empty or d["y"].nunique() < 2:
        return {"error": "no two-class EXT-day sample", "n": int(len(d))}

    # rv63 is the §4.7 nuisance control; the library carries rv21 and rv21/rv63, so
    # it is reconstructed exactly rather than re-derived from bars on a second path.
    d["N1_rv63"] = d["C1_rv21"] / d["C2_rv21_over_rv63"].replace(0.0, np.nan)
    m0 = ["A3_r126"]
    m1 = [*m0, "N1_rv63"]
    m2 = [*m1, *[f for f in ta.FEATURES if f not in m1]]
    models = {"M0": m0, "M1": m1, "M2": m2}

    # Episode membership: the block key for every bootstrap and the episode-AUC join.
    ep = episodes[["segment", "start", "end", "episode_id", "outcome"]]
    j = d[["segment", "date"]].reset_index().merge(ep, on="segment", how="left")
    j = j[(j["date"] >= j["start"]) & (j["date"] <= j["end"])]
    d["episode_id"] = pd.Series(j.set_index("index")["episode_id"]).reindex(d.index)
    d["episode_id"] = d["episode_id"].fillna("_" + d["segment"].astype(str))

    b_boot = 300 if quick else 1000
    out: dict = {"n_rows": int(len(d)), "base_rate_topped": float(d["y"].mean()),
                 "population": "all resolved EXT days (TOPPED or CONTINUED)",
                 "n_names": int(d["ticker"].nunique()),
                 "n_episodes_in_sample": int(d["episode_id"].nunique()),
                 "nested": "M0 (r126) subset M1 (+rv63) subset M2 (+the other 35)",
                 "preprocessing": "median-impute + standardize, fit on TRAIN folds only",
                 "embargo_sessions": ta.E1B_EMBARGO_SESSIONS, "models": {}}

    y_all = d["y"].to_numpy()
    dates = pd.to_datetime(d["date"]).to_numpy()
    probs: dict[str, dict[str, np.ndarray]] = {}

    def oof(cols: list[str], scheme: str) -> np.ndarray | str:
        """Out-of-fold probabilities, or a string reason why there are none."""
        x = d[cols].to_numpy(dtype=float)
        if len(y_all) < 200:
            return "too thin"
        prob = np.full(len(y_all), np.nan)
        pipe = make_pipeline(
            SimpleImputer(strategy="median", keep_empty_features=True),
            StandardScaler(),
            LogisticRegression(C=1.0, max_iter=2000, random_state=seed))
        if scheme == "grouped":
            g = d["ticker"].to_numpy()
            n_split = min(5, len(np.unique(g)))
            if n_split < 2:
                return "one group"
            for tr, te in GroupKFold(n_splits=n_split).split(x, y_all, groups=g):
                if len(np.unique(y_all[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y_all[tr]).predict_proba(x[te])[:, 1]
        else:
            q = pd.PeriodIndex(pd.to_datetime(d["date"]), freq="Q")
            uq = sorted(q.unique())
            for i in range(4, len(uq)):
                te = np.flatnonzero(q == uq[i])
                # 250-SESSION label purge on the panel's own trading calendar: a
                # training row's race label can need 250 forward sessions to resolve,
                # so anything shorter trains on the test window's own outcome.
                pos = int(calendar.searchsorted(uq[i].start_time))
                cut = calendar[max(0, pos - ta.E1B_EMBARGO_SESSIONS)]
                tr = np.flatnonzero(dates < np.datetime64(cut))
                if len(tr) < 200 or len(te) == 0 or len(np.unique(y_all[tr])) < 2:
                    continue
                prob[te] = pipe.fit(x[tr], y_all[tr]).predict_proba(x[te])[:, 1]
        return prob

    for name, cols in models.items():
        cols = [c for c in cols if c in d.columns]
        entry: dict = {"features": cols, "n_features": len(cols)}
        probs[name] = {}
        for scheme in ("grouped", "walk_forward"):
            p = oof(cols, scheme)
            if isinstance(p, str):
                entry[scheme] = {"auc": None, "reason": p}
                continue
            m = np.isfinite(p)
            if m.sum() < 100 or len(np.unique(y_all[m])) < 2:
                entry[scheme] = {"auc": None, "n": int(m.sum()), "reason": "no scored fold"}
                continue
            probs[name][scheme] = p
            res = {"auc": float(roc_auc_score(y_all[m], p[m])), "n": int(m.sum())}
            res.update(_episode_block_ci(y_all[m], p[m],
                                         d["episode_id"].to_numpy()[m], roc_auc_score,
                                         b=b_boot, seed=seed))
            scored = d[m].copy()
            scored["p"] = p[m]
            agg = scored[scored["episode_id"].isin(set(ep["episode_id"]))] \
                .groupby("episode_id").agg(p=("p", "max"))
            agg = agg.join(ep.set_index("episode_id")["outcome"], how="inner")
            if not agg.empty and (agg["outcome"] == "TOPPED").nunique() == 2:
                ep_y = (agg["outcome"] == "TOPPED").astype(int).to_numpy()
                ep_p = agg["p"].to_numpy(dtype=float)
                res["episode_auc"] = float(roc_auc_score(ep_y, ep_p))
                res["n_episodes"] = int(len(agg))
                ep_ci = _episode_block_ci(
                    ep_y, ep_p, agg.index.to_numpy(), roc_auc_score,
                    b=b_boot, seed=seed)
                res["episode_auc_ci_lo"] = ep_ci.get("ci_lo")
                res["episode_auc_ci_hi"] = ep_ci.get("ci_hi")
                res["episode_auc_n_blocks"] = ep_ci.get("n_blocks")
            entry[scheme] = res
        out["models"][name] = entry

    for scheme in ("grouped", "walk_forward"):
        a2 = out["models"]["M2"][scheme].get("auc")
        a1 = out["models"]["M1"][scheme].get("auc")
        out[f"increment_{scheme}"] = (a2 - a1) if (a2 is not None and a1 is not None) else None
        p2, p1 = probs["M2"].get(scheme), probs["M1"].get(scheme)
        if p2 is not None and p1 is not None:
            m = np.isfinite(p2) & np.isfinite(p1)
            if m.sum() >= 100:
                ci = _episode_block_ci(y_all[m], p2[m], d["episode_id"].to_numpy()[m],
                                       roc_auc_score, b=b_boot, seed=seed + 1,
                                       paired=p1[m])
                out[f"increment_{scheme}_ci"] = [ci.get("delta_ci_lo"),
                                                 ci.get("delta_ci_hi")]
                scored = d.loc[m, ["episode_id"]].copy()
                scored["p2"] = p2[m]
                scored["p1"] = p1[m]
                ep_scored = (scored[scored["episode_id"].isin(set(ep["episode_id"]))]
                             .groupby("episode_id").agg(p2=("p2", "max"),
                                                        p1=("p1", "max")))
                ep_scored = ep_scored.join(
                    ep.set_index("episode_id")["outcome"], how="inner")
                if (not ep_scored.empty
                        and (ep_scored["outcome"] == "TOPPED").nunique() == 2):
                    ey = (ep_scored["outcome"] == "TOPPED").astype(int).to_numpy()
                    e2 = ep_scored["p2"].to_numpy(dtype=float)
                    e1 = ep_scored["p1"].to_numpy(dtype=float)
                    out[f"episode_increment_{scheme}"] = float(
                        roc_auc_score(ey, e2) - roc_auc_score(ey, e1))
                    eci = _episode_block_ci(
                        ey, e2, ep_scored.index.to_numpy(), roc_auc_score,
                        b=b_boot, seed=seed + 2, paired=e1)
                    out[f"episode_increment_{scheme}_ci"] = [
                        eci.get("delta_ci_lo"), eci.get("delta_ci_hi")]
    incs = [out.get("increment_grouped"), out.get("increment_walk_forward")]
    out["sign_consistent"] = (all(i is not None for i in incs)
                              and (incs[0] > 0) == (incs[1] > 0))
    return out


def _e2(e2_days: pd.DataFrame, pool: pd.DataFrame, feats: pd.DataFrame,
        survivors: list[str], episodes: pd.DataFrame, grades: dict, *,
        seed: int, quick: bool) -> dict:
    """§4.8 lead-time profile: matched Δ per positive-before-peak window, with the label.

    Windows are stated POSITIVE-BEFORE-PEAK: EARLY +22..+63, MID +6..+21, LATE
    +1..+5, POST-TOP CONFIRMATION 0..−5. A survivor takes the EARLIEST pre-peak
    window whose episode-block CI excludes 0; a survivor that separates only in the
    last window is POST-TOP CONFIRMATION and may never be described as detection
    (G0.4). An exploratory field keeps an `EXPLORATORY ` prefix and cannot reach
    DETECTION grade whatever its lead time.
    """
    if not survivors or e2_days.empty or pool.empty:
        return {"labels": {}, "buckets": {}, "note": "no E1 survivors to profile",
                "convention": "positive = sessions BEFORE the peak"}
    res: dict = {"buckets": {}, "labels": {},
                 "convention": "positive = sessions BEFORE the peak"}
    for lo, hi in E2_BUCKETS:
        tag = _bucket_tag(lo, hi)
        sub = e2_days[e2_days["bucket"] == tag]
        if sub.empty:
            res["buckets"][tag] = {"n_cases": 0, "n_episodes": 0, "table": []}
            continue
        pairs, diag = ta.matched_controls(sub, pool)
        # episode-first here too: a window contributes one row per episode.
        ep_d = ta.episode_deltas(ta.matched_deltas(pairs, feats), sub, episodes)
        stats = ta.matched_delta_stats(ep_d, survivors,
                                       b=500 if quick else ta.BOOTSTRAP_B, seed=seed,
                                       coverage_floor=COVERAGE_FLOOR)
        res["buckets"][tag] = {
            "window": E2_LABELS[(lo, hi)], "n_cases": int(diag["n_matched"]),
            "n_episodes": int(len(ep_d)),
            "n_episodes_available": int(sub["episode_id"].nunique()),
            "table": _records(stats),
        }
    for f in survivors:
        label = "NO PRE-PEAK SEPARATION"
        for lo, hi in E2_BUCKETS:
            t = res["buckets"].get(_bucket_tag(lo, hi), {}).get("table", [])
            row = next((r for r in t if r["feature"] == f), None)
            # E2 is a descriptive profile of already-FDR-controlled E1 survivors,
            # not a second registered test. §4.8 pins the label to the earliest
            # bucket whose episode-block CI excludes zero in the declared sign;
            # re-applying FDR/min-month gates here would silently move a real
            # EARLY/MID read to "no separation" despite the literal CI rule.
            direction = ta.FEATURE_DIRECTION.get(f, 0)
            if row:
                lo_ci, hi_ci = row.get("ci_lo"), row.get("ci_hi")
                med = row.get("median_delta")
                ci_clear = (lo_ci is not None and hi_ci is not None
                            and ((lo_ci > 0) or (hi_ci < 0)))
                sign_ok = (direction == 0
                           or (direction > 0 and med is not None and med > 0)
                           or (direction < 0 and med is not None and med < 0))
            else:
                ci_clear = sign_ok = False
            if ci_clear and sign_ok:
                label = E2_LABELS[(lo, hi)]
                break
        if grades.get(f) == "EXPLORATORY-DISCOVERY":
            label = f"EXPLORATORY {label}"
        res["labels"][f] = label
    return res


def _tail_for(feat: str, observed: dict) -> tuple[int, float]:
    """(direction, control-tail quantile) for a survivor leg — §2's direction-aligned tail."""
    direction = ta.FEATURE_DIRECTION.get(feat, 0)
    return direction, ta.direction_tail(direction, float(observed.get(feat, np.nan)))


def _e3(feats: pd.DataFrame, dtp: pd.DataFrame, topped_ids: set, pool: pd.DataFrame,
        survivors: list[str], observed: dict) -> dict:
    """§4.8 E3 — descriptive first-crossing ORDER at direction-aligned control tails."""
    if not survivors:
        return {"note": "no E1 survivors to order", "order": []}
    ctrl = _pick(feats, pool[["segment", "date"]])
    rows = []
    d = dtp[dtp["episode_id"].isin(topped_ids)][["segment", "date", "episode_id",
                                                 "days_to_peak"]]
    f = d.merge(feats, on=["segment", "date"], how="left")
    for feat in survivors:
        if feat not in ctrl.columns or ctrl[feat].notna().sum() < 50:
            continue
        direction, tail = _tail_for(feat, observed)
        thr = float(ctrl[feat].quantile(tail))
        cross = f[f[feat] >= thr] if tail >= 0.5 else f[f[feat] <= thr]
        if cross.empty:
            continue
        first = cross.sort_values("days_to_peak", ascending=False) \
            .groupby("episode_id", as_index=False).first()
        rows.append({
            "feature": feat, "direction": direction, "control_tail": tail,
            "threshold": thr,
            "n_episodes_crossing": int(len(first)),
            "median_days_to_peak_at_first_cross": float(first["days_to_peak"].median()),
            "p25": float(first["days_to_peak"].quantile(0.25)),
            "p75": float(first["days_to_peak"].quantile(0.75)),
        })
    rows.sort(key=lambda r: -r["median_days_to_peak_at_first_cross"])
    return {"order": rows, "convention": "positive = sessions BEFORE the peak"}


def _e4(ep_deltas: pd.DataFrame, gates: pd.DataFrame, cases: pd.DataFrame,
        survivors: list[str], eras, *, seed: int, quick: bool) -> dict:
    """§4.9 descriptive sign stability of survivors across eras and dollar-volume terciles.

    Stratifies the EPISODE-level deltas (§4.5 aggregation), keyed on the episode's
    peak date, so an era cell counts episodes rather than snapshots.
    """
    if not survivors or ep_deltas.empty:
        return {"eras": {}, "dvol_terciles": {}, "note": "no E1 survivors to stratify"}
    d = ep_deltas.copy()
    d["peak_date"] = pd.to_datetime(d["peak_date"])
    dv = (cases[["episode_id", "dvol21"]].groupby("episode_id", as_index=False).median()
          if "dvol21" in cases.columns else pd.DataFrame(columns=["episode_id", "dvol21"]))
    d = d.merge(dv, on="episode_id", how="left")
    b = 400 if quick else 1000
    res: dict = {"eras": {}, "dvol_terciles": {}, "unit": "distinct episodes"}
    for name, lo, hi in eras:
        sub = d[(d["peak_date"] >= pd.Timestamp(lo)) & (d["peak_date"] <= pd.Timestamp(hi))]
        res["eras"][name] = {
            "n_episodes": int(len(sub)),
            "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                     coverage_floor=COVERAGE_FLOOR))
            if len(sub) >= 20 else [],
        }
    if "dvol21" in d.columns and d["dvol21"].notna().sum() >= 30:
        try:
            d["_terc"] = pd.qcut(d["dvol21"].rank(method="first"), 3,
                                 labels=["low", "mid", "high"])
        except ValueError:
            d["_terc"] = "all"
        for terc, sub in d.groupby("_terc", observed=True):
            res["dvol_terciles"][str(terc)] = {
                "n_episodes": int(len(sub)),
                "table": _records(ta.matched_delta_stats(sub, survivors, b=b, seed=seed,
                                                         coverage_floor=COVERAGE_FLOOR))
                if len(sub) >= 20 else [],
            }
    return res


def _ruler(feats: pd.DataFrame, ext: pd.DataFrame, episodes: pd.DataFrame,
           close: pd.DataFrame, pool: pd.DataFrame, survivors: list[str],
           observed: dict, *, seed: int, quick: bool) -> dict:
    """§2 wrong-ruler check per survivor leg, at the DIRECTION-ALIGNED control tail."""
    if not survivors:
        return {"note": "no E1 survivors to rule", "legs": {}}
    ctrl = _pick(feats, pool[["segment", "date"]])
    # The all-EXT-days null is the same for every leg, and it is the expensive pass
    # (it walks every EXT day in the tape) — compute it ONCE.
    null = ta.top_ruler(ext, episodes, close, b=0, seed=seed)
    legs = {}
    for feat in survivors:
        if feat not in ctrl.columns or ctrl[feat].notna().sum() < 50:
            continue
        direction, tail = _tail_for(feat, observed)
        thr = float(ctrl[feat].quantile(tail))
        f = feats[["segment", "date", feat]].dropna()
        f = f[f[feat] >= thr] if tail >= 0.5 else f[f[feat] <= thr]
        fires = pd.DataFrame(False, index=ext.index, columns=ext.columns)
        for seg, g in f.groupby("segment"):
            if seg in fires.columns:
                fires.loc[fires.index.isin(g["date"]), seg] = True
        r = ta.top_ruler(
            fires & ext, episodes, close, ext_mask=ext,
            b=400 if quick else ta.BOOTSTRAP_B, seed=seed)
        legs[feat] = {"direction": direction, "control_tail": tail,
                      "threshold": thr, **r}
    return {"legs": legs, "all_ext_null": null}


def _delisting_check(close: pd.DataFrame, episodes: pd.DataFrame) -> dict:
    """G0.2 — NAME the dead tickers in the tape instead of assuming they are there."""
    if close.empty:
        return {"n_candidates": 0, "named": []}
    last_day = close.index.max()
    cutoff_pos = max(0, len(close.index) - 61)
    cutoff = close.index[cutoff_pos]
    lasts = close.apply(lambda s: s.last_valid_index())
    dead = lasts[lasts.notna() & (lasts < cutoff)]
    in_ep = set(episodes["segment"]) if not episodes.empty else set()
    named = [{"segment": s, "ticker": ta.segment_ticker(s), "last_bar": str(pd.Timestamp(v).date())}
             for s, v in dead.items() if s in in_ep]
    named.sort(key=lambda r: r["last_bar"])
    # Audited terminal-session anchors for unambiguous 2022–2024 acquisitions or
    # removals. G0.2 requires bars THROUGH the final trading day, not merely a name
    # that happens to stop early, so the gate keys on exact terminal-bar receipts.
    terminal = {
        "TWTR": "2022-10-27", "SIVB": "2023-03-09", "SBNY": "2023-03-10",
        "FRC": "2023-04-28", "ATVI": "2023-10-12", "HZNP": "2023-10-05",
        "VMW": "2023-11-21", "SGEN": "2023-12-13", "PXD": "2024-05-02",
    }
    known = [r for r in named if r["ticker"] in terminal]
    verified = [r for r in known if r["last_bar"] == terminal[r["ticker"]]]
    # The episode-membership list above resolves to ACQUISITIONS, which prove the
    # tape keeps trading names but say nothing about names that FAILED. These are
    # audited failure terminal bars, checked against the panel WITHOUT the episode
    # filter — most never cleared the extension bar at all, and that absence is
    # itself the survivorship receipt this gate exists to print.
    failures = {
        "SIVB": "2023-03-09", "SBNY": "2023-03-10", "FRC": "2023-04-28",
        "RIDE": "2023-07-06", "VLDR": "2023-02-10", "PTRA": "2023-08-16",
        "TWTR": "2022-10-27", "CTXS": "2022-09-29", "WE": "2023-11-03",
    }
    seen: dict[str, dict] = {}
    for s, v in lasts.items():
        tk = ta.segment_ticker(s)
        if tk not in failures or pd.isna(v):
            continue
        bar = str(pd.Timestamp(v).date())
        if tk not in seen or bar > seen[tk]["last_bar"]:
            seen[tk] = {"segment": s, "ticker": tk, "last_bar": bar,
                        "expected_last_bar": failures[tk],
                        "terminal_bar_verified": bar == failures[tk],
                        "held_an_ext_day": s in in_ep}
    failed_named = sorted(seen.values(), key=lambda r: r["last_bar"])
    return {
        "last_data_day": str(last_day.date()),
        "cutoff_last_bar_before": str(pd.Timestamp(cutoff).date()),
        "n_dead_segments": int(len(dead)),
        "n_dead_with_an_episode": len(named),
        "named": named[:40],
        "known_delistings_found": known,
        "known_terminal_bars_verified": verified,
        "verified_failures": failed_named,
        "n_verified_failures": sum(1 for r in failed_named
                                   if r["terminal_bar_verified"]),
        "n_verified_failures_with_ext_day": sum(
            1 for r in failed_named if r["terminal_bar_verified"] and r["held_an_ext_day"]),
        "gate_g0_2_satisfied": len(verified) >= 3,
    }


#: Names whose absence from the cohort is itself the G0.5 finding: the program was
#: motivated by moderate-velocity leadership, and a +50%/126d bar excludes it.
TAPE_LEADERSHIP_WATCH = ("NVDA", "AVGO", "AMD", "MU", "SMCI", "VRT", "ANET",
                         "MRVL", "PLTR", "ORCL", "ARM", "CRDO", "ALAB", "DELL")


def _today_tape(close: pd.DataFrame, ext: pd.DataFrame, feats: pd.DataFrame,
                bars: dict, eqw: pd.Series, cross_returns: pd.DataFrame,
                episodes: pd.DataFrame,
                gates: pd.DataFrame, ruler: dict | None = None) -> dict:
    """G0.5 — the CURRENT extended cohort with its feature readout (display-tier)."""
    if close.empty or ext.empty:
        return {"asof": None, "rows": []}
    asof = close.index.max()
    row = ext.loc[asof]
    live = list(row.index[row.fillna(False).to_numpy(dtype=bool)])
    if not live:
        return {"asof": str(asof.date()), "n_extended_today": 0, "rows": [],
                "note": "nothing extended on the last session — an honest null"}
    need = pd.DataFrame({"segment": live, "date": asof})
    have = feats.merge(need, on=["segment", "date"], how="right")
    missing = sorted(set(need["segment"]) - set(feats.loc[feats["date"] == asof, "segment"]))
    if missing:
        extra_bars = {s: b for s, b in bars.items() if s in missing}
        if len(extra_bars) < len(missing):
            extra_bars.update({s: pd.DataFrame({"close": close[s].dropna()})
                               for s in missing if s not in extra_bars})
        extra = ta.feature_library(
            extra_bars, eqw, {s: [asof] for s in missing}, episodes=episodes,
            cross_sectional_returns=cross_returns)
        have = pd.concat([have.dropna(subset=["A3_r126"]), extra], ignore_index=True)
    g = gates[gates["date"] == asof][["segment", "r126", "rv63", "dvol21"]]
    have = have.merge(g, on="segment", how="left")
    have = have.sort_values("r126", ascending=False)
    if TODAY_TAPE_CAP is not None:
        have = have.head(TODAY_TAPE_CAP)
    # G0.5 asks whether the DISCOVERED discriminators say anything about the cohort
    # that exists now, so every survivor leg rides along with its fire flag at the
    # ruler's own direction-aligned control-tail threshold. Printing only one leg
    # would let the appendix look answered while four fifths of the finding is absent.
    legs = dict((ruler or {}).get("legs", {}))
    cohort: dict = {}
    for f, v in legs.items():
        if f not in have.columns:
            continue
        thr, tail = v.get("threshold"), v.get("control_tail")
        if thr is None or tail is None:
            continue
        fired = (have[f] >= thr) if tail >= 0.5 else (have[f] <= thr)
        fired = fired.fillna(False)
        have[f"fires_{f}"] = fired
        cohort[f] = {
            "threshold": float(thr), "control_tail": float(tail),
            "fires_when": "at or above" if tail >= 0.5 else "at or below",
            "n_fires": int(fired.sum()),
            "pct_fires": round(100.0 * float(fired.mean()), 1) if len(have) else None,
            "n_null": int(have[f].isna().sum()),
            "cohort_min": float(have[f].min()), "cohort_median": float(have[f].median()),
            "cohort_max": float(have[f].max()),
            "names": sorted(have.loc[fired, "ticker"].astype(str)),
        }
    fire_cols = [c for c in have.columns if c.startswith("fires_")]
    n_legs_firing = (have[fire_cols].sum(axis=1) if fire_cols
                     else pd.Series(0, index=have.index))
    present = set(have["ticker"].astype(str))
    keep = ["segment", "ticker", "date", "r126", "rv63", "dvol21",
            "A4_r252", "B2_rsi14", "C6_tr5_over_tr63", "D1_dvol_z",
            "D3_updown_dvol_ratio21",
            "A5_ext_ma50_atr21", "A6_ext_ma200_atr21", "A7_late_gain_share",
            "B1_accel_r21", "C2_rv21_over_rv63", "C3_semivol_ratio63",
            "D6_churn21", "E3f_rs_peak_lag",
            "E4f_price_rs_gap", "E5f_rs_decel", "F1_episode_age",
            "F2_drawdown_in_episode", "F3_days_since_63d_high", *fire_cols]
    keep = [c for c in keep if c in have.columns]
    return {"asof": str(asof.date()), "n_extended_today": len(live),
            "n_rows": int(len(have)), "capped_at": TODAY_TAPE_CAP,
            "survivor_legs": cohort,
            "n_legs_firing": {str(k): int(v) for k, v in
                              n_legs_firing.value_counts().sort_index().to_dict().items()},
            "leadership_watch_present": sorted(
                t for t in TAPE_LEADERSHIP_WATCH if t in present),
            "leadership_watch_absent": sorted(
                t for t in TAPE_LEADERSHIP_WATCH if t not in present),
            "rows": _records(have[keep])}


# ══════════════════════════════════════════════════════════════════════════════
# W2 — tier-widening arms (research/top_anatomy/TOPA_W2_PREREG.md)
#
# Plumbing only. Every construction decision is frozen in that file: the arms are
# the existing `extended_mask(variant=...)` masks, the pipeline below them is
# phase-0 run-3 unchanged, and the ONLY moved variable is the §4.1 trigger term.
# Track W only (§2): the D-track's absence is a declared decision, not an omission.
# ══════════════════════════════════════════════════════════════════════════════
W2_FAMILY = "top_anatomy_w2"
W2_PREREG = "research/top_anatomy/TOPA_W2_PREREG.md"
W2_ARMS = ("r63", "atrz")
#: §3 confirmatory set — the five phase-0 W-track survivors with the direction the
#: phase-0 result observed. One-sided IN THAT DIRECTION; nothing else in W2 can earn
#: a confirmatory grade.
W2_CONFIRMATORY: tuple[tuple[str, int], ...] = (
    ("A4_r252", -1), ("B2_rsi14", +1), ("C6_tr5_over_tr63", -1),
    ("D1_dvol_z", -1), ("D3_updown_dvol_ratio21", -1),
)
W2_CONFIRMATORY_LEGS: tuple[str, ...] = tuple(f for f, _ in W2_CONFIRMATORY)
W2_DECLARED_DIRECTION: dict[str, int] = dict(W2_CONFIRMATORY)
#: The other 31 — two-sided within-family BH, grade capped at EXPLORATORY-DISCOVERY.
W2_EXPLORATORY: tuple[str, ...] = tuple(f for f in ta.FEATURES
                                        if f not in W2_DECLARED_DIRECTION)
#: §5 coverage gate: the motivating exemplars, named. AI leadership reuses the
#: phase-0 G0.5 watchlist verbatim so the two censuses are read on one list.
W2_MINER_WATCH = ("NEM", "GOLD", "AEM", "WPM", "FNV", "RGLD", "PAAS", "KGC", "HL",
                  "AGI", "SSRM", "HMY", "GFI", "AU", "BVN", "SBSW")
#: §6 declared fallback — an arm past this wall is DEFERRED with its reason printed,
#: never silently capped and never subsampled.
W2_WALL_LIMIT_SECONDS = 12 * 3600
#: Conventional display bands for the roster composition sketch (§5c). Nothing rides
#: on them: they label a census, they are not a population definition.
W2_MCAP_TIERS = ((2e9, "micro/small <$2B"), (1e10, "mid $2–10B"),
                 (2e11, "large $10–200B"), (float("inf"), "mega >=$200B"))
W2_MCAP_REFERENCE = "polygon_universe/reference.parquet"


def _num(x) -> float | None:
    """JSON-safe float: a non-finite estimate is emitted as `null`, never as `NaN`.

    `_records` already does this via `to_json`; the W2 tables are assembled as plain
    dicts, so they need the same discipline or the deliverable stops being strict
    JSON for every parser that is not Python's.
    """
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if np.isfinite(v) else None


def _sha256(path: Path) -> str | None:
    """Content hash of the frozen prereg — the freeze proof travels with the result."""
    import hashlib
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _w2_wall_exceeded() -> bool:
    return (time.time() - _T0) > W2_WALL_LIMIT_SECONDS


def w2_one_sided_p(two_sided_p: float, median_delta: float, direction: int, *,
                   b: int) -> float:
    """One-sided p in the DECLARED direction, read off the same block-bootstrap draws.

    `ta.matched_delta_stats` reports the two-sided sign-tail p that `_median_ci`
    computes as ``2·min(a, c)`` with ``a = P(draw <= 0)``, ``c = P(draw >= 0)`` over
    the B episode-peak-month block resamples of the median, floored at ``1/(B+1)``.
    The declared-direction one-sided p is the bootstrap mass on the NULL side of the
    declared sign: ``a`` for a declared POSITIVE direction, ``c`` for a NEGATIVE one.

    ``min(a, c)`` is always the tail opposite the observed median, so that mass is
    exactly ``two_sided / 2`` when the observed median carries the declared sign and
    its complement ``1 − two_sided / 2`` when it does not (``a + c = 1 + P(draw = 0)``,
    and a bootstrap median of a continuous panel is a.s. non-zero). Re-floored at
    ``1/(B+1)``: halving a two-sided p that was already at its floor would otherwise
    print a one-sided p finer than B resamples can resolve.

    An observed median of exactly zero matches no declared sign and lands on the
    complement branch, which is the honest read — a distribution centred on zero has
    ~half its mass on the null side whichever direction was declared.
    """
    if not np.isfinite(two_sided_p) or not np.isfinite(median_delta):
        return float("nan")
    sign_matches = (direction > 0 and median_delta > 0) or \
                   (direction < 0 and median_delta < 0)
    p = (two_sided_p / 2.0) if sign_matches else (1.0 - two_sided_p / 2.0)
    return float(min(max(p, 1.0 / (b + 1.0)), 1.0))


def w2_confirmatory_table(stats: pd.DataFrame, *, b: int) -> list[dict]:
    """§3 — the five legs, one-sided in the declared direction, BH-FDR over the 5.

    ``stats`` is a `ta.matched_delta_stats` frame computed over the FULL 36-feature
    tuple, so every per-feature bootstrap seed keeps its phase-0 ordinal and the
    confirmatory and exploratory tables are read off ONE set of draws. The engine's
    own `q_value` there is a two-sided BH over all 36 within six letter families; it
    is carried through under an explicit name and is NOT what grades a leg.

    The multiplicity family is exactly these five one-sided tests (prereg §3), so BH
    runs over the 5 together rather than within letter families.
    """
    rows = []
    for feat in W2_CONFIRMATORY_LEGS:
        r = stats[stats["feature"] == feat]
        if r.empty:
            rows.append({"feature": feat,
                         "declared_direction": W2_DECLARED_DIRECTION[feat],
                         "reason_absent": "feature not present in the panel's deltas"})
            continue
        r = r.iloc[0].to_dict()
        direction = W2_DECLARED_DIRECTION[feat]
        med = float(r["median_delta"])
        p1 = w2_one_sided_p(float(r["p_value"]), med, direction, b=b)
        rows.append({
            "feature": feat, "family": r["family"], "declared_direction": direction,
            "n_episodes": int(r["n_episodes"]), "n_blocks": int(r["n_blocks"]),
            "coverage": _num(r["coverage"]),
            "meets_coverage_floor": bool(r["interpretable"]),
            "meets_peak_month_floor": bool(int(r["n_blocks"]) >= ta.MIN_EPISODE_MONTHS),
            "median_delta": _num(med), "ci_lo": _num(r["ci_lo"]), "ci_hi": _num(r["ci_hi"]),
            "ci_excludes_zero": bool((r["ci_lo"] > 0) or (r["ci_hi"] < 0)),
            "sign_matches_declared": bool((direction > 0 and med > 0)
                                          or (direction < 0 and med < 0)),
            "p_value_two_sided": _num(r["p_value"]),
            "p_value_one_sided": _num(p1),
            "q_value_two_sided_all36_letter_family": _num(r["q_value"]),
            "ticker_ci_lo": _num(r["ticker_ci_lo"]), "ticker_ci_hi": _num(r["ticker_ci_hi"]),
        })
    have = [r for r in rows if r.get("p_value_one_sided") is not None]
    if have:
        q = ta.bh_fdr(np.array([r["p_value_one_sided"] for r in have], dtype=float))
        for r, qv in zip(have, q):
            r["q_value_one_sided"] = _num(qv)
            r["passes_q"] = bool(np.isfinite(qv) and qv <= ta.FDR_Q)
            r["separates_one_sided"] = bool(r["sign_matches_declared"] and r["passes_q"])
    for r in rows:
        r.setdefault("q_value_one_sided", None)
        r.setdefault("passes_q", False)
        r.setdefault("separates_one_sided", False)
    return rows


def w2_exploratory_table(stats: pd.DataFrame, *, ranked: bool) -> dict:
    """§3 exploratory set — the other 31 under phase-0's two-sided within-family BH.

    The five confirmatory legs are removed BEFORE the BH step: they are declared as
    their own family of five one-sided tests, so leaving them in the letter families
    would spend their trial budget twice. Grade is capped at EXPLORATORY-DISCOVERY —
    no W2 result creates or upgrades a registration.

    ``ranked=False`` (the DISJOINT panels) prints the same table with no grade
    attached: the numbers are printed regardless of sign or significance, but the
    panel carries no discovery ranking.
    """
    e = stats[stats["feature"].isin(W2_EXPLORATORY)].copy()
    if e.empty:
        return {"ranked": ranked, "n_features": 0, "table": [], "separating": []}
    e["q_value"] = np.nan
    for _fam, g in e.groupby("family", sort=False):
        e.loc[g.index, "q_value"] = ta.bh_fdr(g["p_value"].to_numpy(dtype=float))
    ci_excl = (e["ci_lo"] > 0) | (e["ci_hi"] < 0)
    sign_ok = np.where(e["direction"] > 0, e["median_delta"] > 0,
                       np.where(e["direction"] < 0, e["median_delta"] < 0, True))
    e["separates"] = (ci_excl & pd.Series(sign_ok, index=e.index)
                      & (e["q_value"] <= ta.FDR_Q) & e["interpretable"]
                      & (e["n_blocks"] >= ta.MIN_EPISODE_MONTHS)).astype(bool)
    e["grade"] = np.where(e["separates"] & ranked, "EXPLORATORY-DISCOVERY", "")
    e = e.sort_values(["family", "feature"], ignore_index=True)
    return {
        "ranked": ranked,
        "bh_family": "letter family, within the 31 exploratory features only",
        "grade_cap": ("EXPLORATORY-DISCOVERY" if ranked else
                      "none — printed unranked on the DISJOINT panel (prereg §3)"),
        "n_features": int(len(e)),
        "n_separating": int(e["separates"].sum()),
        "separating": sorted(e.loc[e["separates"], "feature"]),
        "table": _records(e),
    }


def w2_episode_overlap(ext_arm: pd.DataFrame, ext_primary: pd.DataFrame,
                       close: pd.DataFrame, episodes: pd.DataFrame) -> pd.DataFrame:
    """§4 panel assignment — how much of each arm episode the phase-0 bar already saw.

    An episode's EXT-day set is the (identity-segment, session) pairs where the ARM
    mask is true inside [start, end] on the segment's own bars — the same
    `mask & bars` rule `extract_episodes` and `episode_peaks` use, so the count here
    is the episode's own `n_ext_days`, not a recount on a different calendar.

    DISJOINT: zero of those days are also phase-0-PRIMARY EXT days. PARTIAL_OVERLAP:
    some. FULLY_SHARED: all. Only DISJOINT episodes carry a generalization claim.
    """
    cols = ["episode_id", "segment", "n_ext_days_in_span", "n_shared_with_primary",
            "share_shared", "overlap_class"]
    if episodes.empty:
        return pd.DataFrame(columns=cols)
    prim = ext_primary.reindex(index=ext_arm.index, columns=ext_arm.columns)
    pos = pd.Series(np.arange(len(ext_arm.index)), index=ext_arm.index)
    rows = []
    for seg, g in episodes.groupby("segment", sort=False):
        if seg not in ext_arm.columns:
            continue
        bars = close[seg].notna().to_numpy(dtype=bool) if seg in close.columns \
            else np.ones(len(ext_arm.index), dtype=bool)
        a = ext_arm[seg].fillna(False).to_numpy(dtype=bool) & bars
        s = a & prim[seg].fillna(False).to_numpy(dtype=bool)
        ca = np.concatenate([[0], np.cumsum(a)])
        cs = np.concatenate([[0], np.cumsum(s)])
        for r in g.itertuples():
            if r.start not in pos.index or r.end not in pos.index:
                continue
            i0, i1 = int(pos[r.start]), int(pos[r.end])
            n_arm = int(ca[i1 + 1] - ca[i0])
            n_sh = int(cs[i1 + 1] - cs[i0])
            rows.append({
                "episode_id": r.episode_id, "segment": seg,
                "n_ext_days_in_span": n_arm, "n_shared_with_primary": n_sh,
                "share_shared": (float(n_sh / n_arm) if n_arm else None),
                "overlap_class": ("DISJOINT" if n_sh == 0 else
                                  "FULLY_SHARED" if n_sh >= n_arm else
                                  "PARTIAL_OVERLAP"),
            })
    return pd.DataFrame(rows, columns=cols)


def w2_coverage_census(close: pd.DataFrame, ext_arm: pd.DataFrame,
                       episodes: pd.DataFrame, gates: pd.DataFrame,
                       data_root: Path, *, arm: str) -> dict:
    """§5 coverage gate — the wave's FIRST question, before any statistic.

    (a) the vintage-date extended roster and its size, (b) the motivating exemplars
    BY NAME on two separate readings — in the roster on the vintage date, and holding
    ANY arm episode anywhere on the tape — and (c) a composition sketch. Absence is
    split into "not in the tape at all" and "in the tape, never cleared this arm's
    bar", because those are different findings and only the second is about the bar.
    """
    asof = close.index.max()
    row = ext_arm.loc[asof]
    live = list(row.index[row.fillna(False).to_numpy(dtype=bool)])
    roster = sorted({ta.segment_ticker(s) for s in live})
    roster_set = set(roster)
    ever = set(episodes["ticker"].astype(str)) if not episodes.empty else set()
    in_tape = {ta.segment_ticker(c) for c in close.columns}

    watch = {"ai_leaders": tuple(TAPE_LEADERSHIP_WATCH),
             "gold_pgm_miners": W2_MINER_WATCH}
    by_name: dict[str, dict] = {}
    for group, names in watch.items():
        by_name[group] = {
            "n_watched": len(names),
            "in_roster_on_vintage_date": sorted(t for t in names if t in roster_set),
            "absent_from_roster_on_vintage_date": sorted(
                t for t in names if t not in roster_set),
            "has_any_arm_episode_ever": sorted(t for t in names if t in ever),
            "no_arm_episode_ever": sorted(t for t in names if t not in ever),
            "not_in_the_tape_at_all": sorted(t for t in names if t not in in_tape),
            "in_the_tape_but_no_arm_episode": sorted(
                t for t in names if t in in_tape and t not in ever),
        }

    sketch: dict = {"n_roster_names": len(roster), "n_roster_segments": len(live)}
    g = gates[gates["date"] == asof]
    g = g[g["segment"].isin(live)] if not g.empty else g
    if not g.empty:
        sketch["dvol21_usd"] = _describe(g["dvol21"])
        sketch["r126"] = _describe(g["r126"])
        sketch["rv63"] = _describe(g["rv63"])
        dv = pd.to_numeric(g["dvol21"], errors="coerce").dropna()
        sketch["dvol21_bands"] = {
            "under_10m": int((dv < 1e7).sum()), "10m_to_100m": int(((dv >= 1e7) & (dv < 1e8)).sum()),
            "100m_to_1b": int(((dv >= 1e8) & (dv < 1e9)).sum()), "at_or_over_1b": int((dv >= 1e9).sum())}
    px = close.loc[asof, live].astype(float) if live else pd.Series(dtype=float)
    if not px.empty:
        sketch["close_bands"] = {
            "under_10": int((px < 10).sum()), "10_to_50": int(((px >= 10) & (px < 50)).sum()),
            "50_to_200": int(((px >= 50) & (px < 200)).sum()),
            "at_or_over_200": int((px >= 200).sum())}

    # (c) mcap tiers — cheap, but the only reference the repo carries is a large-cap
    # index roster, so its COVERAGE is printed beside every tier count. A tier table
    # over 5% of the roster is a statement about who is missing from the reference,
    # not about the cohort, and must not be read as the latter.
    ref_path = data_root / W2_MCAP_REFERENCE
    mcap: dict = {"source": W2_MCAP_REFERENCE, "available": ref_path.exists()}
    if ref_path.exists():
        try:
            ref = pd.read_parquet(ref_path)
            caps = pd.to_numeric(ref["market_cap_usd"], errors="coerce")
            caps.index = ref.index.astype(str)
            hit = caps.reindex(roster).dropna()
            tiers = {label: 0 for _, label in W2_MCAP_TIERS}
            for v in hit.to_numpy(dtype=float):
                for edge, label in W2_MCAP_TIERS:
                    if v < edge:
                        tiers[label] += 1
                        break
            mcap.update({
                "reference_asof": (str(ref["asof"].iloc[0]) if "asof" in ref.columns
                                   and len(ref) else None),
                "reference_n_names": int(len(ref)),
                "n_roster_names_with_mcap": int(len(hit)),
                "coverage_share_of_roster": (round(float(len(hit) / len(roster)), 4)
                                             if roster else None),
                "tiers_on_covered_names_only": tiers,
                "sector_counts_on_covered_names_only": (
                    ref.reindex(hit.index)["gics_sector"].value_counts().to_dict()
                    if "gics_sector" in ref.columns else {}),
                "note": ("the reference carries a large-cap index roster only, so the "
                         "uncovered remainder of the roster is not 'unknown mcap' at "
                         "random — it is everything outside that index"),
            })
        except Exception as exc:  # noqa: BLE001 — a census sketch never kills the run
            mcap["error"] = str(exc)
    sketch["mcap"] = mcap

    return {
        "vintage_date": str(pd.Timestamp(asof).date()),
        "vintage_date_source": "derived from the panel's last session, never a manifest",
        "arm": arm,
        "n_extended_on_vintage_date": len(live),
        "n_distinct_names_on_vintage_date": len(roster),
        "n_names_with_any_arm_episode_ever": len(ever),
        "n_names_in_the_tape": len(in_tape),
        "roster_names_on_vintage_date": roster,
        "exemplars": by_name,
        "composition_sketch": sketch,
    }


def w2_panel_slice(name: str, ids: set[str] | None, race: pd.DataFrame,
                   dtp: pd.DataFrame, ext: pd.DataFrame,
                   close: pd.DataFrame) -> dict:
    """The four EXT-day populations one §4 panel runs on.

    ``ids=None`` is the FULL panel and applies NO restriction at all, so FULL is the
    phase-0 pipeline with the arm's mask substituted and nothing else moved. The
    DISJOINT panel restricts every population to its episodes: cases, the CONTINUED
    control pool, the all-EXT-day E1b/ruler population, and the ruler's own mask.
    `dtp` is the day→episode map — `episode_peaks` emits one row per EXT day inside
    an episode, so no interval join is needed and no EXT day is assigned twice.
    """
    if ids is None:
        return {"panel": name, "race": race, "dtp": dtp, "ext": ext,
                "restricted": False}
    keep_dtp = dtp[dtp["episode_id"].isin(ids)]
    keyed = race.merge(keep_dtp[["segment", "date", "episode_id"]],
                       on=["segment", "date"], how="left")
    keep_race = keyed[keyed["episode_id"].notna()].drop(columns=["episode_id"])
    sub = pd.DataFrame(False, index=ext.index, columns=ext.columns)
    for seg, g in keep_dtp.groupby("segment", sort=False):
        if seg in sub.columns:
            sub.loc[sub.index.isin(pd.DatetimeIndex(g["date"])), seg] = True
    return {"panel": name, "race": keep_race, "dtp": keep_dtp,
            "ext": sub & ext, "restricted": True}


def run_w2_panel(panel_name: str, sl: dict, *, episodes: pd.DataFrame,
                 close: pd.DataFrame, gates: pd.DataFrame, feats: pd.DataFrame,
                 seed: int, quick: bool, run_e_series: bool | str) -> dict:
    """One §4 panel end to end: cases → matched controls → E1 → (E1b / E2 / ruler).

    ``run_e_series="floor"`` is the DISJOINT rule: the E-series runs only where the
    ≥12 distinct peak-month floor is met, and the floor verdict prints either way.
    """
    race, dtp, ext = sl["race"], sl["dtp"], sl["ext"]
    out: dict = {"panel": panel_name, "restricted_to_panel_episodes": sl["restricted"]}
    ep_ids = set(dtp["episode_id"]) if not dtp.empty else set()
    eps = episodes[episodes["episode_id"].isin(ep_ids)] if sl["restricted"] else episodes
    e1_eps = eps[~eps["micro"]]
    topped_eps = e1_eps[e1_eps["outcome"] == "TOPPED"]
    out["episodes"] = {
        "n_episodes": int(len(eps)),
        "n_micro_under_5_ext_days": int(eps["micro"].sum()) if len(eps) else 0,
        "n_e1_eligible": int(len(e1_eps)),
        "n_names": int(eps["ticker"].nunique()) if len(eps) else 0,
        "n_topped_e1_eligible": int(len(topped_eps)),
        "outcomes": {k: int(v) for k, v in
                     eps["outcome"].value_counts().to_dict().items()} if len(eps) else {},
        "n_peak_window_censored": (int(eps["peak_window_censored"].sum())
                                   if len(eps) else 0),
        "n_ext_days": int(ext.to_numpy().sum()),
    }
    out["race"] = {"counts": {k: int(v) for k, v in
                              race["label"].value_counts().to_dict().items()}}
    if topped_eps.empty or race.empty:
        out["null_reason"] = "no TOPPED E1-eligible episodes on this panel"
        return out

    dtp_e1 = dtp[dtp["episode_id"].isin(set(e1_eps["episode_id"]))]
    topped_ids = set(topped_eps["episode_id"])
    cases = dtp_e1[dtp_e1["episode_id"].isin(topped_ids)
                   & dtp_e1["days_to_peak"].isin(ta.CASE_OFFSETS)].copy()
    cases["offset"] = cases["days_to_peak"]
    cases["case_id"] = cases["episode_id"] + "@" + cases["offset"].astype(str)
    pool = race[race["label"] == "CONTINUED"][["segment", "ticker", "date"]].copy()
    pool["case_id"] = ["p%d" % i for i in range(len(pool))]
    out["cases"] = {"n_cases": int(len(cases)),
                    "n_case_episodes": int(cases["episode_id"].nunique()),
                    "per_offset": {int(k): int(v) for k, v in
                                   cases["offset"].value_counts().to_dict().items()},
                    "n_control_candidates": int(len(pool))}
    cases = _pick(gates, cases).dropna(subset=["r126", "rv63", "dvol21"])
    pool = _pick(gates, pool).dropna(subset=["r126", "rv63", "dvol21"])
    say(f"[W2 {panel_name}] {len(cases)} cases vs {len(pool)} CONTINUED candidates")
    pairs, diag = ta.matched_controls(cases, pool)
    out["matching"] = dict(diag)
    out["matching"]["bin_edges"] = ("quintile/tercile edges cut WITHIN CALENDAR "
                                    "QUARTER over this panel's own case+control "
                                    "union (prereg §2: bins are population-relative)")
    say(f"[W2 {panel_name}] matched {diag['n_matched']}/{diag['n_cases']} cases")
    if pairs.empty:
        out["null_reason"] = "no matched pairs on this panel"
        return out

    b = ta.BOOTSTRAP_B if not quick else 400
    case_deltas = ta.matched_deltas(pairs, feats)
    ep_deltas = ta.episode_deltas(case_deltas, cases, eps)
    stats = ta.matched_delta_stats(ep_deltas, b=b, seed=seed,
                                   coverage_floor=COVERAGE_FLOOR)
    n_months = (int(pd.to_datetime(ep_deltas["peak_date"]).dt.to_period("M").nunique())
                if not ep_deltas.empty else 0)
    floor_met = n_months >= ta.MIN_EPISODE_MONTHS
    out["e1"] = {
        "aggregation": "episode-first (median over the episode's {21,10,5} snapshots)",
        "bootstrap_b": b, "seed": seed,
        "n_case_sets": int(len(case_deltas)), "n_episodes": int(len(ep_deltas)),
        "n_distinct_peak_months": n_months,
        "min_peak_months_required": ta.MIN_EPISODE_MONTHS,
        "meets_peak_month_floor": bool(floor_met),
        "peak_month_floor_verdict": (
            f"{n_months} distinct episode-peak months vs the "
            f"{ta.MIN_EPISODE_MONTHS} required — "
            + ("floor MET" if floor_met else "floor NOT met")),
        "min_finite_controls": ta.MIN_FINITE_CONTROLS,
        "feature_coverage_floor": COVERAGE_FLOOR,
        "snapshots_per_episode": (_describe(ep_deltas["n_snapshots"])
                                  if not ep_deltas.empty else _describe([])),
    }
    out["confirmatory"] = {
        "legs": list(W2_CONFIRMATORY_LEGS),
        "test": "one-sided in the declared direction, from the same episode-peak-month "
                "block bootstrap; BH-FDR over exactly these 5 tests",
        "one_sided_derivation": (w2_one_sided_p.__doc__ or "").strip().split("\n")[0],
        "q_threshold": ta.FDR_Q,
        "table": w2_confirmatory_table(stats, b=b),
    }
    out["exploratory"] = w2_exploratory_table(stats, ranked=(panel_name == "FULL"))
    out["feature_coverage"] = {f: float(feats[f].notna().mean())
                               for f in ta.FEATURES if f in feats.columns}
    out["features_below_coverage_floor"] = sorted(
        f for f, c in out["feature_coverage"].items() if c < COVERAGE_FLOOR)

    # E2 / E1b / ruler ride on whatever SEPARATED on this panel — the union of the
    # confirmatory legs that cleared their one-sided q and the exploratory flags.
    # These are descriptive readouts (§4.7/§4.8), never a second registered test, so
    # the leg set carries no inferential weight; it is stated rather than implied.
    conf_sep = [r["feature"] for r in out["confirmatory"]["table"]
                if r.get("separates_one_sided")]
    survivors = sorted(set(conf_sep) | set(out["exploratory"]["separating"]))
    out["survivors"] = survivors
    out["survivor_definition"] = ("confirmatory legs clearing the one-sided q on this "
                                  "panel, plus exploratory features flagged separating "
                                  "— descriptive readouts only")
    do_e = bool(floor_met) if run_e_series == "floor" else bool(run_e_series)
    if not do_e:
        out["e_series_skipped"] = (
            "E1b / E2 / ruler are run on FULL panels and on DISJOINT panels only where "
            f"the >={ta.MIN_EPISODE_MONTHS} distinct peak-month floor is met "
            f"(prereg §2); this panel: {out['e1']['peak_month_floor_verdict']}")
        return out

    obs = {r["feature"]: r["median_delta"] for r in _records(stats)}
    grades = {f: "EXPLORATORY-DISCOVERY" for f in out["exploratory"]["separating"]}
    say(f"[W2 {panel_name}] E1b pooled AUC increment")
    out["e1b"] = _e1b(feats, race, eps, race[["segment", "date"]], close.index,
                      seed=seed, quick=quick)
    say(f"[W2 {panel_name}] E2 lead-time profiles on {len(survivors)} leg(s)")
    e2_days = _pick(gates, _e2_case_days(dtp_e1, topped_ids)) \
        .dropna(subset=["r126", "rv63", "dvol21"])
    out["e2"] = _e2(e2_days, pool, feats, survivors, eps, grades,
                    seed=seed, quick=quick)
    say(f"[W2 {panel_name}] remaining-upside ruler on {len(survivors)} leg(s)")
    out["ruler"] = _ruler(feats, ext, eps, close, pool, survivors, obs,
                          seed=seed, quick=quick)
    return out


def run_w2_arm(arm: str, panel: dict, meta: dict, data_root: Path, *, seed: int,
               quick: bool, n_files: int = 0) -> dict:
    """One tier-widening arm: variant EXT mask, then the frozen phase-0 pipeline."""
    close = panel["close"]
    volume = panel.get("volume")
    dvol = (close * volume).reindex_like(close) if volume is not None and not volume.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    raw_close, raw_dvol = panel.get("raw_close"), panel.get("raw_dvol")
    split_day = panel.get("split_day")
    floors = {"raw_close_df": raw_close if raw_close is not None and not raw_close.empty
              else None,
              "raw_dollar_vol_df": raw_dvol if raw_dvol is not None and not raw_dvol.empty
              else None,
              "split_day_df": split_day if split_day is not None and not split_day.empty
              else None}
    out: dict = {"arm": arm, "track": "W", "panel": dict(meta)}
    out["panel"].update({
        "n_sessions": int(close.shape[0]), "n_segments": int(close.shape[1]),
        "first_session": str(close.index.min().date()) if len(close) else None,
        "last_session": str(close.index.max().date()) if len(close) else None,
        "floors_on_raw_prints": floors["raw_close_df"] is not None,
        "panel_cache_shared_with_phase0": True,
        "panel_cache_sharing_basis": (
            "panel content is upstream of every EXT mask — split repair reads raw "
            "prints, identity segmentation reads tape gaps and repaired-close "
            "up-ratios, and no panel leg is a function of an extension definition"),
    })

    elig = ta.eligibility_mask(close, dvol, **floors)
    min_cross_names = 20 if not quick else 1
    eqw = ta.equal_weight_median_index(close, elig, min_names=min_cross_names)
    cross_returns = ta.cross_sectional_median_returns(close, elig,
                                                      min_names=min_cross_names)
    out["prefix_parity_gate"] = assert_prefix_parity(panel, f"W2-{arm}", eqw,
                                                     cross_returns)
    out["prefix_parity_gate"]["note"] = (
        "the §3 repair gate is a PANEL property; its internal episode anchor uses the "
        "primary variant, so this receipt is about the repair, not about the arm")

    say(f"[W2 {arm}] EXT mask (variant={arm}) and the phase-0 primary mask for §4 panels")
    ext = ta.extended_mask(close, dvol, variant=arm, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    ext_primary = ta.extended_mask(close, dvol, variant="primary",
                                   high_df=panel.get("high"), low_df=panel.get("low"),
                                   **floors)
    n_ext = int(ext.to_numpy().sum())
    per_day = ext.sum(axis=1)
    out["ext"] = {
        "variant": arm, "n_ext_days": n_ext,
        "n_ext_days_primary": int(ext_primary.to_numpy().sum()),
        "n_ext_days_shared_with_primary": int((ext & ext_primary).to_numpy().sum()),
        "n_eligible_days": int(elig.to_numpy().sum()),
        "n_segments_with_ext": int((ext.sum() > 0).sum()),
        "first_ext_day": (str(per_day[per_day > 0].index.min().date())
                          if bool((per_day > 0).any()) else None),
        "n_sessions_zero_ext": int((per_day == 0).sum()),
    }
    out["census"] = _instrument_census(panel, ext, elig, n_files)
    say(f"[W2 {arm}] {n_ext:,} EXT days on {out['ext']['n_segments_with_ext']} segments "
        f"({out['ext']['n_ext_days_shared_with_primary']:,} shared with primary)")
    if n_ext == 0:
        out["null_reason"] = "no EXT days under this arm"
        return out

    say(f"[W2 {arm}] episodes")
    episodes = ta.extract_episodes(ext, close)
    say(f"[W2 {arm}] race labels on {len(episodes)} episodes")
    race = ta.race_labels(close, ext)
    say(f"[W2 {arm}] episode peaks")
    episodes, dtp = ta.episode_peaks(close, episodes, ext)

    say(f"[W2 {arm}] §4 panel assignment (arm episodes vs the primary EXT-day set)")
    overlap = w2_episode_overlap(ext, ext_primary, close, episodes)
    counts = overlap["overlap_class"].value_counts().to_dict() if not overlap.empty else {}
    disjoint_ids = set(overlap.loc[overlap["overlap_class"] == "DISJOINT", "episode_id"])
    out["episode_census"] = {
        "n_episodes": int(len(episodes)),
        "n_disjoint": int(counts.get("DISJOINT", 0)),
        "n_partial_overlap": int(counts.get("PARTIAL_OVERLAP", 0)),
        "n_fully_shared": int(counts.get("FULLY_SHARED", 0)),
        "n_unassigned": int(len(episodes) - len(overlap)),
        "share_shared_days": _describe(overlap["share_shared"]) if not overlap.empty
        else _describe([]),
        "definition": ("DISJOINT = the episode's arm EXT-day set shares ZERO "
                       "(segment, session) days with the phase-0 primary EXT-day set"),
    }
    say(f"[W2 {arm}] episode census {out['episode_census']['n_disjoint']} disjoint / "
        f"{out['episode_census']['n_partial_overlap']} partial / "
        f"{out['episode_census']['n_fully_shared']} fully shared")

    gates = _gate_context(close, dvol)
    say(f"[W2 {arm}] §5 coverage gate")
    out["coverage_gate"] = w2_coverage_census(close, ext, episodes, gates, data_root,
                                              arm=arm)
    ex = out["coverage_gate"]["exemplars"]
    say(f"[W2 {arm}] coverage: roster {out['coverage_gate']['n_distinct_names_on_vintage_date']} "
        f"names; AI leaders in-roster {len(ex['ai_leaders']['in_roster_on_vintage_date'])}"
        f"/{ex['ai_leaders']['n_watched']}, ever-episode "
        f"{len(ex['ai_leaders']['has_any_arm_episode_ever'])}; miners in-roster "
        f"{len(ex['gold_pgm_miners']['in_roster_on_vintage_date'])}"
        f"/{ex['gold_pgm_miners']['n_watched']}, ever-episode "
        f"{len(ex['gold_pgm_miners']['has_any_arm_episode_ever'])}")

    if _w2_wall_exceeded():
        out["deferral"] = _w2_deferral(arm, "after the coverage gate")
        return out

    # ONE feature pass for both panels: the FULL panel's need-set is every EXT day
    # (E1b/ruler are pinned to all of them), and DISJOINT is a subset of it, so a
    # second pass would recompute identical values under the same arm episodes.
    need = race[["segment", "ticker", "date"]].drop_duplicates(["segment", "date"])
    say(f"[W2 {arm}] features on {len(need):,} (segment, day) points")
    bars = _segment_bars(panel, sorted(set(need["segment"])))
    feats = ta.feature_library(bars, eqw, need[["segment", "date"]], episodes=episodes,
                               cross_sectional_returns=cross_returns)
    out["feature_panel"] = {
        "n_rows": int(len(feats)), "n_segments": int(need["segment"].nunique()),
        "arm_keyed": True,
        "arm_keying_basis": ("the F family (F1_episode_age / F2_drawdown_in_episode / "
                             "F5_reclaim_speed) is anchored on `episodes`, which come "
                             "from this arm's EXT mask — feature values are NOT "
                             "EXT-definition-independent, so this panel is built per "
                             "arm and never shared with the phase-0 pass"),
    }

    out["panels"] = {}
    for panel_name, ids in (("FULL", None), ("DISJOINT", disjoint_ids)):
        if _w2_wall_exceeded():
            out["deferral"] = _w2_deferral(arm, f"before the {panel_name} panel")
            break
        say(f"[W2 {arm}] ── {panel_name} panel ──")
        sl = w2_panel_slice(panel_name, ids, race, dtp, ext, close)
        out["panels"][panel_name] = run_w2_panel(
            panel_name, sl, episodes=episodes, close=close, gates=gates, feats=feats,
            seed=seed, quick=quick,
            run_e_series=(True if panel_name == "FULL" else "floor"))
        say(f"[W2 {arm}] {panel_name} panel complete")

    out["confirmatory_grades"] = w2_grade(out.get("panels", {}))
    return out


#: The leg the G0.5 red-team asks a current-cohort question about. Phase-0's review
#: demanded the same read for D3; W2's confirmed leg is B2, so B2 is what gets read.
W2_ROSTER_READ_FEATURE = "B2_rsi14"


def w2_vintage_roster_read(arm: str, panel: dict, arm_result: dict, *, seed: int,
                           quick: bool,
                           feature: str = W2_ROSTER_READ_FEATURE) -> dict:
    """POST-HOC descriptive read: where the vintage-date roster sits on one leg.

    Display-tier reporting, computed AFTER the confirmatory results were read and
    therefore carrying no confirmatory standing whatever it shows — it answers "what
    does the discovered leg say about the cohort that exists on the vintage date",
    which is the current-cohort question phase-0's G0.5 red-team asked of D3.

    Three levels are put side by side on ONE construction: the roster's own value on
    the vintage date, the DISJOINT panel's topped-episode value, and that panel's
    matched-control value. Case and control levels are aggregated exactly as §4.5
    aggregates the contrast — per case the control arm is the MEAN of its finite
    controls, then each episode collapses to the median over its {21,10,5}
    snapshots, then the median is taken across DISTINCT EPISODES — so the two are on
    the same footing as the Δ the arm reports, not a snapshot-pooled lookalike.

    The fire threshold is READ from the arm's own DISJOINT ruler leg rather than
    recomputed, so "at or beyond" means the same thing here as it does in the ruler.
    Feature values come from `ta.feature_library`; no statistic here re-implements a
    feature the engine already owns.
    """
    close = panel["close"]
    volume = panel.get("volume")
    dvol = (close * volume).reindex_like(close) if volume is not None and not volume.empty \
        else pd.DataFrame(np.nan, index=close.index, columns=close.columns)
    floors = {k: (v if v is not None and not v.empty else None) for k, v in
              (("raw_close_df", panel.get("raw_close")),
               ("raw_dollar_vol_df", panel.get("raw_dvol")),
               ("split_day_df", panel.get("split_day")))}
    out: dict = {
        "post_hoc": True, "arm": arm, "feature": feature,
        "provenance": ("computed AFTER the confirmatory results for this arm were "
                       "read, at the commissioning session's request; descriptive "
                       "display-tier reporting, not a registered quantity and not "
                       "part of the prereg's declared test set"),
        "tier": "research/display tier; no rank, no size, no gate, no exit rule",
    }
    leg = ((arm_result.get("panels", {}).get("DISJOINT", {}).get("ruler", {}) or {})
           .get("legs", {}) or {}).get(feature)
    if not leg or leg.get("threshold") is None:
        out["threshold_available"] = False
        out["reason"] = (f"{feature} carries no DISJOINT ruler leg on this arm, so "
                         "there is no fire threshold to read the roster against")
        return out

    thr, tail = float(leg["threshold"]), float(leg["control_tail"])
    say(f"[W2 {arm}] post-hoc roster read on {feature} "
        f"(DISJOINT ruler threshold {thr:.4f}, control tail {tail:.2f})")
    elig = ta.eligibility_mask(close, dvol, **floors)
    min_cross = 20 if not quick else 1
    eqw = ta.equal_weight_median_index(close, elig, min_names=min_cross)
    xr = ta.cross_sectional_median_returns(close, elig, min_names=min_cross)
    ext = ta.extended_mask(close, dvol, variant=arm, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    prim = ta.extended_mask(close, dvol, variant="primary", high_df=panel.get("high"),
                            low_df=panel.get("low"), **floors)
    episodes = ta.extract_episodes(ext, close)
    race = ta.race_labels(close, ext)
    episodes, dtp = ta.episode_peaks(close, episodes, ext)
    ov = w2_episode_overlap(ext, prim, close, episodes)
    ids = set(ov.loc[ov["overlap_class"] == "DISJOINT", "episode_id"])
    need = race[["segment", "ticker", "date"]].drop_duplicates(["segment", "date"])
    feats = ta.feature_library(_segment_bars(panel, sorted(set(need["segment"]))), eqw,
                               need[["segment", "date"]], episodes=episodes,
                               cross_sectional_returns=xr)

    # ── the vintage-date roster ──────────────────────────────────────────────
    asof = close.index.max()
    row = ext.loc[asof]
    live = list(row.index[row.fillna(False).to_numpy(dtype=bool)])
    r = feats[(feats["date"] == asof) & (feats["segment"].isin(live))]
    vals = pd.to_numeric(r[feature], errors="coerce")
    finite = vals.dropna()
    fires = (finite >= thr) if tail >= 0.5 else (finite <= thr)
    out.update({
        "vintage_date": str(pd.Timestamp(asof).date()),
        "threshold_available": True,
        "fire_threshold": thr, "control_tail": tail,
        "fires_when": "at or above" if tail >= 0.5 else "at or below",
        "threshold_source": ("this arm's DISJOINT-panel ruler leg for the feature — "
                             "read, not recomputed"),
        "n_roster_segments": len(live),
        "n_roster_names": len({ta.segment_ticker(s) for s in live}),
        "n_roster_with_finite_feature": int(len(finite)),
        "n_roster_at_or_beyond_threshold": int(fires.sum()),
        "share_roster_at_or_beyond_threshold": (
            round(float(fires.mean()), 4) if len(finite) else None),
        "share_denominator": "roster segments carrying a finite feature value",
        "roster_names_at_or_beyond_threshold": sorted(
            r.loc[fires[fires].index, "ticker"].astype(str)) if bool(fires.any()) else [],
    })

    # ── the DISJOINT panel's own two levels, on the §4.5 aggregation ─────────
    sl = w2_panel_slice("DISJOINT", ids, race, dtp, ext, close)
    d_dtp, d_race = sl["dtp"], sl["race"]
    eps = episodes[episodes["episode_id"].isin(set(d_dtp["episode_id"]))]
    e1_eps = eps[~eps["micro"]]
    topped = set(e1_eps.loc[e1_eps["outcome"] == "TOPPED", "episode_id"])
    d_e1 = d_dtp[d_dtp["episode_id"].isin(set(e1_eps["episode_id"]))]
    cases = d_e1[d_e1["episode_id"].isin(topped)
                 & d_e1["days_to_peak"].isin(ta.CASE_OFFSETS)].copy()
    cases["case_id"] = cases["episode_id"] + "@" + cases["days_to_peak"].astype(str)
    pool = d_race[d_race["label"] == "CONTINUED"][["segment", "ticker", "date"]].copy()
    pool["case_id"] = ["p%d" % i for i in range(len(pool))]
    gates = _gate_context(close, dvol)
    cases = _pick(gates, cases).dropna(subset=["r126", "rv63", "dvol21"])
    pool = _pick(gates, pool).dropna(subset=["r126", "rv63", "dvol21"])
    pairs, diag = ta.matched_controls(cases, pool)

    def _episode_first(frame: pd.DataFrame, col: str) -> tuple[float | None, int]:
        """Episode-first median of a LEVEL: snapshots -> episode median -> across."""
        if frame.empty:
            return None, 0
        per_ep = frame.groupby("episode_id")[col].median()
        per_ep = per_ep[np.isfinite(per_ep)]
        return ((float(per_ep.median()), int(len(per_ep))) if len(per_ep) else (None, 0))

    fp = feats.copy()
    fp["date"] = pd.to_datetime(fp["date"])
    key = fp.set_index(["segment", "date"])[feature]
    key = key[~key.index.duplicated(keep="first")]
    case_lv = cases[["episode_id", "segment", "date"]].copy()
    case_lv["date"] = pd.to_datetime(case_lv["date"])
    case_lv[feature] = key.reindex(
        pd.MultiIndex.from_arrays([case_lv["segment"], case_lv["date"]])).to_numpy()
    case_med, n_case_eps = _episode_first(case_lv, feature)

    ctrl_med, n_ctrl_eps = None, 0
    if not pairs.empty:
        p = pairs.copy()
        p["control_date"] = pd.to_datetime(p["control_date"])
        p[feature] = key.reindex(pd.MultiIndex.from_arrays(
            [p["control_segment"], p["control_date"]])).to_numpy()
        # §4.5: the control arm of a matched set is the MEAN of its finite controls.
        per_case = p.groupby("case_id")[feature].mean().rename(feature).reset_index()
        per_case = per_case.merge(cases[["case_id", "episode_id"]], on="case_id",
                                  how="left")
        ctrl_med, n_ctrl_eps = _episode_first(per_case, feature)

    out["levels"] = {
        "aggregation": ("episode-first: per case the control arm is the mean of its "
                        "finite controls, each episode collapses to the median over "
                        "its {21,10,5} snapshots, then the median across episodes"),
        "vintage_roster_median": (float(finite.median()) if len(finite) else None),
        "disjoint_topped_episode_median": case_med,
        "disjoint_matched_control_median": ctrl_med,
        "n_roster_finite": int(len(finite)),
        "n_disjoint_topped_episodes": n_case_eps,
        "n_disjoint_control_episodes": n_ctrl_eps,
        "n_matched_cases": int(diag.get("n_matched", 0)),
    }
    lv = out["levels"]
    say(f"[W2 {arm}] roster {feature} median {lv['vintage_roster_median']} vs DISJOINT "
        f"topped {lv['disjoint_topped_episode_median']} vs matched-control "
        f"{lv['disjoint_matched_control_median']}; "
        f"{out['n_roster_at_or_beyond_threshold']}/{out['n_roster_with_finite_feature']} "
        "roster names at or beyond the ruler threshold")
    return out


def _w2_deferral(arm: str, where: str) -> dict:
    """§6 declared fallback — print the deferral, never a silent cap or a subsample."""
    hrs = (time.time() - _T0) / 3600.0
    msg = (f"arm {arm} passed the declared {W2_WALL_LIMIT_SECONDS / 3600:.0f} h wall "
           f"at {hrs:.2f} h ({where}); prereg §6 defers the arm to its own wave with "
           "the reason printed rather than capping or subsampling it")
    say(f"[W2 {arm}] DEFERRED — {msg}")
    return {"deferred": True, "wall_hours": hrs,
            "wall_limit_hours": W2_WALL_LIMIT_SECONDS / 3600.0,
            "stopped_at": where, "reason": msg,
            "subsampled": False, "capped": False}


def w2_grade(panels: dict) -> dict:
    """§3 grades — DISJOINT is where a generalization claim lives; FULL is support."""
    def _row(panel: str, feat: str) -> dict | None:
        t = (panels.get(panel, {}).get("confirmatory", {}) or {}).get("table", [])
        return next((r for r in t if r["feature"] == feat), None)

    out: dict = {}
    for feat, direction in W2_CONFIRMATORY:
        dj, fu = _row("DISJOINT", feat), _row("FULL", feat)
        dj_ok = bool(dj and dj.get("separates_one_sided"))
        fu_ok = bool(fu and fu.get("separates_one_sided"))
        grade = ("W2-CONFIRMED" if dj_ok else
                 "W2-PARTIAL" if fu_ok else "W2-NOT-CONFIRMED")
        keep = ("median_delta", "ci_lo", "ci_hi", "q_value_one_sided",
                "p_value_one_sided", "n_episodes", "n_blocks", "coverage",
                "sign_matches_declared", "meets_peak_month_floor")
        out[feat] = {
            "declared_direction": direction, "grade": grade,
            "disjoint": ({k: dj.get(k) for k in keep} if dj else None),
            "full": ({k: fu.get(k) for k in keep} if fu else None),
        }
    counts: dict[str, int] = {}
    for v in out.values():
        counts[v["grade"]] = counts.get(v["grade"], 0) + 1
    return {"grades": out, "counts": counts,
            "rule": ("W2-CONFIRMED = DISJOINT sign matches the declared direction AND "
                     "one-sided BH q <= 0.10; W2-PARTIAL = the same on FULL only; "
                     "W2-NOT-CONFIRMED = neither. Printed with equal prominence.")}


# ══════════════════════════════════════════════════════════════════════════════
# report
# ══════════════════════════════════════════════════════════════════════════════
def _fmt(x, nd: int = 4) -> str:
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "null"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    if isinstance(x, (float, np.floating)):
        return f"{float(x):.{nd}f}"
    return str(x)


def _e1_table(rows: list[dict]) -> list[str]:
    out = ["| feature | family | dir | episodes | peak-months | cov | median Δ "
           "| 95% CI (peak-month block) | q | grade |",
           "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        d = {1: "higher⇒TOPPED", -1: "lower⇒TOPPED", 0: "exploratory"}[r["direction"]]
        ci = f"[{_fmt(r['ci_lo'])}, {_fmt(r['ci_hi'])}]"
        grade = r.get("grade") or ("no" if not r.get("separates") else "**YES**")
        out.append(f"| `{r['feature']}` | {r['family']} | {d} | "
                   f"{_fmt(r.get('n_episodes'))} | {_fmt(r.get('n_blocks'))} | "
                   f"{_fmt(r['coverage'], 2)} | {_fmt(r['median_delta'])} | {ci} | "
                   f"{_fmt(r['q_value'], 3)} | {grade} |")
    return out


def _arm_headline(summary: dict) -> dict:
    """Per-track numbers one arm is diffed against another with in §1a."""
    out = {"run_date": summary.get("run_date"), "git_sha": summary.get("git_sha")}
    for tk, t in (summary.get("tracks") or {}).items():
        e1 = t.get("e1", {})
        b = t.get("e1b", {})
        out[tk] = {
            "n_segments": t.get("panel", {}).get("n_segments"),
            "n_ext_days": t.get("ext", {}).get("n_ext_days"),
            "n_episodes": t.get("episodes", {}).get("n_episodes"),
            "n_topped_e1": t.get("episodes", {}).get("n_topped_e1_eligible"),
            "e1_n_episodes": e1.get("n_episodes"),
            "e1_registered": e1.get("registered_separating", []),
            "e1_exploratory": e1.get("exploratory_separating", []),
            "e1b_increment_grouped": b.get("increment_grouped"),
            "e1b_increment_walk_forward": b.get("increment_walk_forward"),
            "ruler_legs": sorted((t.get("ruler", {}).get("legs") or {}).keys()),
            "e2_labels": t.get("e2", {}).get("labels", {}),
            "tape_extended": t.get("today_tape", {}).get("n_extended_today"),
        }
    return out


#: §1a movement rows: (label, `_arm_headline` key).
_MOVEMENT_ROWS = (("segments", "n_segments"), ("EXT days", "n_ext_days"),
                  ("episodes", "n_episodes"),
                  ("TOPPED E1-eligible episodes", "n_topped_e1"),
                  ("E1 N (episodes)", "e1_n_episodes"),
                  ("today's-tape EXTENDED", "tape_extended"))


def _window_table(A, block: dict) -> None:
    """One row per feature per §4.8 window, medians with their episode-block CIs."""
    buckets = block.get("buckets", {})
    feats: list[str] = []
    for blk in buckets.values():
        for r in blk.get("table", []):
            if r["feature"] not in feats:
                feats.append(r["feature"])
    if not feats:
        return
    heads = [f"{b.get('window', t)} `{t}`" for t, b in buckets.items()]
    A("| feature | " + " | ".join(heads) + " |")
    A("|---" * (len(heads) + 1) + "|")
    for f in feats:
        cells = []
        for blk in buckets.values():
            r = next((x for x in blk.get("table", []) if x["feature"] == f), None)
            cells.append("null" if not r else
                         f"{_fmt(r['median_delta'], 4)} [{_fmt(r['ci_lo'], 3)}, "
                         f"{_fmt(r['ci_hi'], 3)}]")
        A(f"| `{f}` | " + " | ".join(cells) + " |")
    A("")
    A("| feature | " + " | ".join(f"n eps `{t}`" for t in buckets) + " |")
    A("|---" * (len(buckets) + 1) + "|")
    for f in feats:
        cells = []
        for blk in buckets.values():
            r = next((x for x in blk.get("table", []) if x["feature"] == f), None)
            cells.append("null" if not r else _fmt(r.get("n_episodes")))
        A(f"| `{f}` | " + " | ".join(cells) + " |")


def _stability_table(A, blk: dict, feature: str, eras) -> None:
    """The 6 stability cells for one leg, WITH the primary block CI in every cell."""
    rows = []
    for name, _, _ in eras:
        e = blk.get("eras", {}).get(name)
        if e:
            rows.append((f"era {name}", e))
    for t, e in blk.get("dvol_terciles", {}).items():
        rows.append((f"dollar-volume {t}", e))
    if not rows:
        return
    A(f"**`{feature}` stability cells** — point estimate, primary episode-peak-month "
      "block CI, and the block count the CI rests on.")
    A("")
    A("| cell | episodes | peak-month blocks | median Δ | 95% CI (primary) | p "
      "| CI excludes 0 |")
    A("|---|---|---|---|---|---|---|")
    n_excl = 0
    for label, e in rows:
        r = next((x for x in e.get("table", []) if x["feature"] == feature), None)
        if not r:
            A(f"| {label} | {_fmt(e.get('n_episodes'))} | — | null | null | null | — |")
            continue
        excl = (r["ci_lo"] > 0) or (r["ci_hi"] < 0)
        n_excl += bool(excl)
        A(f"| {label} | {_fmt(r.get('n_episodes'))} | {_fmt(r.get('n_blocks'))} | "
          f"{_fmt(r['median_delta'], 4)} | [{_fmt(r['ci_lo'], 3)}, "
          f"{_fmt(r['ci_hi'], 3)}] | {_fmt(r.get('p_value'), 3)} | "
          f"{'**yes**' if excl else 'no'} |")
    A("")
    A(f"Excludes zero in **{n_excl} of {len(rows)}** cells. A cell resting on few "
      "peak-month blocks is not credible evidence on its own: the ≥"
      f"{ta.MIN_EPISODE_MONTHS}-block registration guard applies to the E1 separates "
      "flag, NOT to these descriptive cells.")
    A("")


def _repair_arm_section(A, summary: dict, w: dict, d: dict) -> None:
    """§1a — the `sanity-segmented` arm: trigger, rule, cost, and what moved."""
    ra = summary.get("repair_arm", {})
    A("## 1a. Repair arm — `sanity-segmented` (prereg §6)")
    A("")
    A(f"**Trigger.** {ra.get('trigger', '')}. Run-1's today's-tape appendix is what "
      "surfaced it: names showing +1,000% to +12,000% single days that are reverse "
      "splits, not moves.")
    A("")
    A(f"**Rule.** {ra.get('rule', '')} — the same segmentation machinery as the "
      "60-session tape-gap rule, so each side is an independent name with its own "
      "260-session history floor and nothing (window, race, or feature) spans the "
      f"break. **What was NOT done:** {ra.get('not_done', '')}.")
    A("")

    repair = w.get("panel", {}).get("repair_impact", {})
    if repair:
        pre_repair = repair.get("pre_repair_affected_names", {})
        repaired = repair.get("sanity_segmented_affected_names", {})
        removed = repair.get("removed_from_affected_names", {})
        A(f"**What the rule did to THIS run's panel** (track W, arm "
          f"`{w.get('panel', {}).get('repair_arm')}`; recomputed from the raw bars, "
          "not carried). A repaired-close up-jump ≥"
          f"{_fmt(w.get('panel', {}).get('residual_up_ratio_break'), 1)}x starts a new "
          "identity; there is no down-jump screen. "
          f"{_fmt(repair.get('n_tickers_affected'))} tickers gained "
          f"{_fmt(repair.get('n_additional_identity_segments'))} boundaries. On those "
          f"affected names, pre-repair → headline accounting is "
          f"{_fmt(pre_repair.get('n_segments'))} → {_fmt(repaired.get('n_segments'))} "
          f"segments, {_fmt(pre_repair.get('n_ext_days'))} → "
          f"{_fmt(repaired.get('n_ext_days'))} EXT days, and "
          f"{_fmt(pre_repair.get('n_episodes'))} → "
          f"{_fmt(repaired.get('n_episodes'))} episodes (removed: "
          f"{_fmt(removed.get('n_ext_days'))} EXT days / "
          f"{_fmt(removed.get('n_episodes'))} episodes). The pre-repair arm is audit-only.")
        A("")

    c = ra.get("contamination", {})
    if c.get("available"):
        prov = c.get("provenance")
        A("**How much of run-1 was fabricated** (measured on run-1's own panel, before "
          "the rebuild):")
        A("")
        A("| pre-repair quantity | count | of which contaminated |")
        A("|---|---|---|")
        A(f"| residual ≥{_fmt(c.get('jump_ratio'), 1)}x up-days | "
          f"{_fmt(c.get('n_jump_days'))} | — |")
        A(f"| segments carrying one | {_fmt(c.get('n_segments_with_jump'))} of "
          f"{_fmt(c.get('pre_repair_segments'))} | — |")
        A(f"| EXT days | {_fmt(c.get('run1_ext_days'))} | "
          f"**{_fmt(c.get('run1_ext_days_contaminated_r126'))}** with a fabricated bar "
          f"inside the trailing 126 sessions ({_fmt(c.get('run1_ext_days_on_jump_segments'))} "
          "on an affected segment at all) |")
        A(f"| episodes | {_fmt(c.get('run1_episodes'))} | "
          f"**{_fmt(c.get('run1_episodes_contaminated'))}** |")
        A(f"| TOPPED E1-eligible episodes | {_fmt(c.get('run1_topped_e1_episodes'))} | "
          f"**{_fmt(c.get('run1_topped_e1_episodes_contaminated'))}** |")
        A(f"| matched cases | {_fmt(c.get('run1_cases'))} | "
          f"**{_fmt(c.get('run1_cases_contaminated'))}** "
          f"(across {_fmt(c.get('run1_case_episodes_contaminated'))} of "
          f"{_fmt(c.get('run1_case_episodes'))} case-episodes) |")
        A(f"| today's-tape EXTENDED names ({c.get('tape_asof')}) | "
          f"{_fmt(c.get('tape_names_extended'))} | "
          f"**{_fmt(c.get('tape_names_contaminated'))}** carried one inside their "
          "trailing 126 sessions |")
        A("")
        if prov:
            A(f"*Provenance: {prov}. The audit code that produced them "
              "(`run1_contamination_audit`) still runs against any pre-repair cache and "
              "refuses to report a sanity-segmented panel's structural zeros as a "
              "measurement.*")
            A("")
        off = c.get("top_offenders", [])
        if off:
            A("Worst fabrications in the pre-repair tape:")
            A("")
            A("| ticker | date | close before → after | ratio |")
            A("|---|---|---|---|")
            for r in off[:10]:
                # Significant digits, not fixed decimals: a sub-cent pre-split print
                # is the evidence, and 2dp would render it as "0.00 -> 0.00".
                px = [f"{float(r[k]):.8g}" for k in ("prev_close", "close")]
                A(f"| {r['ticker']} | {str(r['date'])[:10]} | {px[0]} → "
                  f"{px[1]} | {_fmt(r['ratio'], 1)}x |")
            A("")
    else:
        A(f"*Contamination not quantified: {c.get('reason', 'no pre-repair panel')}.*")
        A("")

    r1, r2 = ra.get("run1", {}), ra.get("run2", {})
    if not (r1 or r2):
        return
    r3 = _arm_headline(summary)
    A("**What moved across the three arms.** Run-1 = pre-repair (gap rule only). "
      f"Run-2 = `sanity-segmented` on the PRE-AUDIT instrument ({r2.get('run_date', 'n/a')}), "
      "retained as a cross-check arm. Run-3 = the reconciled instrument "
      "(independent-audit compliance repairs + the same declared ≥3.0x residual "
      "up-jump rule) and is the HEADLINE arm.")
    A("")
    # A run stamps the COMMITTED head, not the working tree it executed. Run-2's code
    # was uncommitted at run time and survives only as an unpushed local snapshot, so
    # the stamped sha does not identify the instrument and must not be cited as if it did.
    A(f"*Reproducibility limitation: run-2's summary stamps git "
      f"`{r2.get('git_sha', 'n/a')}`, which is the committed HEAD at run time, NOT the "
      f"code that ran. The run-2 instrument is local snapshot commit "
      f"`{RUN2_INSTRUMENT_SHA}`, which was never pushed — run-2 is therefore not "
      "independently reproducible from the repository, and its column below is a "
      "preserved reading rather than a re-runnable arm.*")
    A("")
    A("**Each step changes exactly one variable, which is why run-2 is kept.** "
      "run-1 → run-2 holds the ESTIMATOR fixed and changes the PANEL: that movement "
      "is contamination removal. run-2 → run-3 holds the PANEL fixed and changes the "
      "ESTIMATOR: that movement is the audit's compliance repairs (all-EXT-day E1b "
      "and ruler, micro-spell days in the control pool, literal same-day cross-"
      "sectional medians for E1f/E2f, window-bounded B6, simple-daily-return C3/D6, "
      "frozen-rule E2 labels, within-name ruler shares). The track W panel rows "
      "below are IDENTICAL across run-2 and run-3 — segments, EXT days, episodes and "
      "TOPPED counts all match — which is the receipt that the second comparison is "
      "clean. Neither step changed a frozen quantity, threshold, population, or "
      "outcome rule.")
    A("")
    A("| | run-1 W | run-2 W | run-3 W | run-1 D | run-2 D | run-3 D |")
    A("|---|---|---|---|---|---|---|")
    for lab, key in _MOVEMENT_ROWS:
        cells = [_fmt(r.get(tk, {}).get(key)) for tk in ("W", "D") for r in (r1, r2, r3)]
        A(f"| {lab} | " + " | ".join(cells) + " |")
    A("")
    A("*Track D reads differently across the arms by construction: the ≥3.0x residual "
      "up-jump rule is a repair for the UNADJUSTED massive store, so it is applied to "
      "track W only. Run-2's line also applied it to the adjusted D ladder; run-3 "
      "returns D to gap-only segmentation, which is what run-1 used. A D column that "
      "moves 1→2 and back 2→3 is that instrument difference, not a data change.*")
    A("")
    for tk in ("W", "D"):
        a1, a2, a3 = (r.get(tk, {}) for r in (r1, r2, r3))
        A(f"- **Track {tk} E1 registered:** run-1 `{a1.get('e1_registered') or 'none'}` "
          f"→ run-2 `{a2.get('e1_registered') or 'none'}` → run-3 "
          f"`{a3.get('e1_registered') or 'none'}`")
        A(f"- **Track {tk} E1 exploratory:** run-1 `{a1.get('e1_exploratory') or 'none'}` "
          f"→ run-2 `{a2.get('e1_exploratory') or 'none'}` → run-3 "
          f"`{a3.get('e1_exploratory') or 'none'}`")
        A(f"- **Track {tk} E1b ΔAUC (grouped):** run-1 "
          f"{_fmt(a1.get('e1b_increment_grouped'), 3)} → run-2 "
          f"{_fmt(a2.get('e1b_increment_grouped'), 3)} → run-3 "
          f"{_fmt(a3.get('e1b_increment_grouped'), 3)}")
        A(f"- **Track {tk} ruler legs:** run-1 `{a1.get('ruler_legs') or 'none'}` → "
          f"run-2 `{a2.get('ruler_legs') or 'none'}` → run-3 "
          f"`{a3.get('ruler_legs') or 'none'}`")
        A(f"- **Track {tk} E2 labels:** run-1 `{a1.get('e2_labels') or {}}` → run-2 "
          f"`{a2.get('e2_labels') or {}}` → run-3 `{a3.get('e2_labels') or {}}`")
    A("")
    A(f"Run-1 is retained at `{ra.get('prerepair_summary')}` as the **pre-repair arm** "
      f"and run-2 at `{ra.get('run2_summary')}` as the **pre-audit-instrument "
      "cross-check arm**. The reconciled run-3 above is the headline arm.")
    A("")


def write_report(path: Path, summary: dict) -> None:
    """The house phase-0 report: verdict first, nulls printed, honest N everywhere."""
    w = summary["tracks"].get("W", {})
    d = summary["tracks"].get("D", {})
    e1 = w.get("e1", {})
    n_sep = e1.get("n_separating", 0)
    eps = w.get("episodes", {})
    L: list[str] = []
    A = L.append

    if not e1:
        verdict = "NO REGISTRATION TRACK RESULT — the W pipeline produced no matched set"
    elif n_sep == 0:
        verdict = ("ZERO of 36 features separate TOPPED from CONTINUED extended days "
                   "on the registration track")
    else:
        labels = w.get("e2", {}).get("labels", {})
        pre = [f for f, lab in labels.items() if lab in ("EARLY", "MID", "LATE")]
        verdict = (f"{n_sep} of 36 features separate; "
                   f"{len(pre)} carry a PRE-PEAK lead-time label"
                   if pre else
                   f"{n_sep} of 36 features separate — all POST-TOP CONFIRMATION, "
                   "no detection claim")

    A("# TOP ANATOMY Phase-0 — extended-move anatomy: topped vs continued")
    A("")
    # Placeholder only. The SHIPPED report carries four ratified prose paragraphs
    # (verdict / who this describes / what the anatomy says / instrument honesty)
    # written in a post-run prose pass and corrected by the G0.5 red-team; a fresh
    # run re-emits this line and the prose pass is re-applied on top.
    A(f"**Verdict: {verdict}.** *(prose pass pending — numbers below are the run's own.)*")
    A("")
    A(f"- **Date:** {summary['run_date']} · **Family:** `{FAMILY}`")
    A(f"- **Prereg:** `research/top_anatomy/TOPA_PHASE0_PREREG.md` (frozen "
      f"{summary['prereg_frozen']}, before any result) · **Masterplan:** "
      "`research/TOP_ANATOMY_MASTERPLAN_BY_FABLE.md`")
    A(f"- **Reproduce:** `{summary['reproduce']}`")
    A(f"- **Vintage:** git `{summary['git_sha']}` · track W data through "
      f"**{w.get('panel', {}).get('last_session')}** · track D through "
      f"**{d.get('panel', {}).get('last_session')}**")
    A("- **Tier:** research / display, zero scored authority. AVOID-not-SHORT: nothing "
      "here is a directional bear position, a rank, a size, or an exit rule. A TOPPED "
      "label is a statement about the declared race (−20% from the post-entry running "
      "peak before +15% from entry, inside 250 sessions) — never that a move \"is over\".")
    A("")
    A("---")
    A("")

    A("## 1. The tape")
    A("")
    A("| | track W (registration) | track D (era context, TILTED) |")
    A("|---|---|---|")
    for lab, key, sub in (("segments (identity-split names)", "panel", "n_segments"),
                          ("sessions", "panel", "n_sessions"),
                          ("first session", "panel", "first_session"),
                          ("last session", "panel", "last_session"),
                          ("tickers split on a >60-session gap", "panel", "n_tickers_split"),
                          ("EXT days", "ext", "n_ext_days"),
                          ("segments with ≥1 EXT day", "ext", "n_segments_with_ext")):
        A(f"| {lab} | {_fmt(w.get(key, {}).get(sub))} | {_fmt(d.get(key, {}).get(sub))} |")
    for lab, sub in (("episodes", "n_episodes"),
                     ("…micro (<5 EXT days, excluded from E1)", "n_micro_under_5_ext_days"),
                     ("…E1-eligible", "n_e1_eligible"), ("distinct names", "n_names"),
                     ("TOPPED episodes (E1-eligible)", "n_topped_e1_eligible"),
                     ("peak-window censored", "n_peak_window_censored")):
        A(f"| {lab} | {_fmt(w.get('episodes', {}).get(sub))} | "
          f"{_fmt(d.get('episodes', {}).get(sub))} |")
    A("")
    A("Extension sensitivity arms (report-only, no registration claim rides on them): "
      f"primary `r126≥+0.50` = {_fmt(w.get('ext_variants', {}).get('primary'))} EXT days; "
      f"`r63≥+0.35` = {_fmt(w.get('ext_variants', {}).get('r63'))}; "
      f"`(c−MA200)/ATR63≥6` = {_fmt(w.get('ext_variants', {}).get('atrz'))}.")
    A("")

    _repair_arm_section(A, summary, w, d)

    A("## 1b. Instrument / dead-name census (§3) and the §3 parity gate")
    A("")
    A("Counted from the panel, never inferred from a file count.")
    A("")
    A("| | track W | track D |")
    A("|---|---|---|")
    for lab, key in (("files scanned", "n_files_scanned"),
                     ("tickers kept", "n_tickers_kept"),
                     ("identity segments", "n_segments"),
                     ("segments ever ELIGIBLE", "n_segments_ever_eligible"),
                     ("segments with ≥1 EXT day", "n_segments_with_ext"),
                     ("segments CANDIDATE-DEAD (last bar >60 sessions back)",
                      "n_segments_candidate_dead"),
                     ("…of those, held ≥1 EXT day", "n_candidate_dead_with_ext_day")):
        A(f"| {lab} | {_fmt(w.get('census', {}).get(key))} | "
          f"{_fmt(d.get('census', {}).get(key))} |")
    A("")
    pg = (w.get("prefix_parity_gate") or d.get("prefix_parity_gate") or {})
    pg_track = "W" if w.get("prefix_parity_gate") else "D"
    A(f"**§3 full-series-vs-prefix parity gate: PASSED** on "
      f"{_fmt(pg.get('n_names_checked'))} sampled track-{pg_track} name(s) "
      f"(worst |gap| {_fmt(pg.get('worst_abs_gap'), 12)}, tolerance "
      f"{_fmt(pg.get('tolerance'), 12)}). Features at d are recomputed from the "
      "series truncated just after d, through the same repair path — so a split "
      "discovered later cannot move a value the study already read. The gate runs "
      "before any label is computed and hard-fails the run; the synthetic twin lives "
      "in `tests/test_top_anatomy.py`.")
    A("")
    A("Split-factor step days are INELIGIBLE, and the §3 price/liquidity floors are "
      "evaluated on the **raw as-printed** close and close×volume — an adjusted-price "
      "floor would evict 2022 days on a 2025 split. The recovered factor divides "
      "open/high/low/close and multiplies volume, so repaired dollar volume is "
      "invariant across the repair.")
    A("")
    lec = w.get("panel", {}).get("left_edge_census") or {}
    if lec:
        pct = (100.0 * lec["n_dropped_short_history"] / lec["n_files_scanned"]
               if lec.get("n_files_scanned") else None)
        ex = lec.get("examples_short_liquid_dead") or []
        A("**The survivorship honesty in §11 is RIGHT-edge honesty.** Counted exactly "
          f"during the scan: {_fmt(lec.get('n_dropped_short_history'))} of "
          f"{_fmt(lec.get('n_files_scanned'))} scanned files "
          f"({_fmt(pct, 1)}%) were dropped for carrying fewer than 261 bars — too "
          "short to serve the 260-session in-segment history floor. "
          f"{_fmt(lec.get('n_short_but_liquid'))} of those were ONCE LIQUID (they "
          "cleared the $3 price and $2M median-dollar-volume ceilings at some point), "
          f"and {_fmt(lec.get('n_short_liquid_dead_before_ext_left_edge'))} of them "
          f"had already stopped trading before {lec.get('ext_left_edge')}, the first "
          "date on which any extended day can exist. Those names contribute ZERO "
          "observations to every table in this report and cannot appear in the "
          "dead-name census either"
          + (f" (e.g. {', '.join(ex[:6])})." if ex else "."))
        A("")
    A("## 2. Race labels (§4.3) — the outcome, with its nulls printed")
    A("")
    A("| label | track W | track D |")
    A("|---|---|---|")
    for lab in ("TOPPED", "CONTINUED", "CENSORED"):
        A(f"| {lab} | {_fmt(w.get('race', {}).get('counts', {}).get(lab, 0))} | "
          f"{_fmt(d.get('race', {}).get('counts', {}).get(lab, 0))} |")
    cr = w.get("race", {}).get("censor_reasons", {})
    A("")
    A(f"Censoring splits {cr.get('horizon', 0):,} at the 250-session horizon and "
      f"{cr.get('data_end', 0):,} at the tape's end (delisting without a −20% print; a "
      "delisting that collapses fires TOPPED on its own bars).")
    A("")
    eps_w = w.get("episodes", {})
    by_year = eps_w.get("peak_window_censored_by_year") or {}
    rsel = eps_w.get("right_edge_selection") or {}
    if by_year:
        A(f"**Peak-window censoring is a RIGHT-EDGE selection, not a uniform loss.** "
          f"{_fmt(eps_w.get('n_peak_window_censored'))} episodes are peak-window "
          "censored, by peak year: "
          + ", ".join(f"{y} {v:,}" for y, v in by_year.items()) + ". "
          f"{_fmt(rsel.get('n_censored_peaking_in_seal_window'))} of them peak on or "
          f"after **{rsel.get('peaks_on_or_after')}** — inside the final "
          f"{rsel.get('seal_window')}-session sealing window. An episode peaking there "
          f"can be sealed TOPPED only if its −20% prints before the tape ends "
          f"({rsel.get('last_session')}), so the recent end of the sample keeps FAST "
          "toppers and censors slow ones. Every recent-era cell inherits that tilt.")
        A("")

    A("## 3. E1 — matched-control separation (registration track W)")
    A("")
    if not e1:
        A("*Track W was not run in this pass, so there is no registration result. "
          "Track D can never register a claim (survivorship tilt, §11).*")
        A("")
    A(f"Cases: {_fmt(w.get('cases', {}).get('n_cases'))} snapshots at `days_to_peak ∈ "
      f"{{21, 10, 5}}` from {_fmt(w.get('cases', {}).get('n_case_episodes'))} TOPPED "
      f"episodes (per offset: {w.get('cases', {}).get('per_offset', {})}). Controls: "
      f"{_fmt(w.get('cases', {}).get('n_control_candidates'))} CONTINUED EXT-day "
      "candidates, matched within calendar quarter × r126 quintile × rv63 tercile × "
      "dollar-volume tercile, ≤4 nearest neighbours by |Δr126| then |Δrv63|, never from "
      "the case's own name.")
    A("")
    m = w.get("matching", {})
    A(f"**Honest N: {_fmt(e1.get('n_episodes'))} DISTINCT EPISODES** "
      f"(from {_fmt(e1.get('n_case_sets'))} matched case-sets; "
      f"{_fmt(m.get('n_dropped_no_control'))} cases dropped with zero eligible "
      f"controls, {_fmt(m.get('controls_per_case_mean'), 2)} controls per matched "
      "case). §4.5 aggregation is EPISODE-FIRST: an episode's {21,10,5} snapshots "
      "collapse to their median Δ before anything is pooled, because three looks at "
      "one event are not three events. A Δ exists only where the case and ≥"
      f"{ta.MIN_FINITE_CONTROLS} controls are finite.")
    A("")
    A(f"Distinct episode-peak months: **{_fmt(e1.get('n_distinct_peak_months'))}** "
      f"against the {ta.MIN_EPISODE_MONTHS} a registered separation requires.")
    A("")
    A(f"**{n_sep} of 36 features separate** (≥{ta.MIN_EPISODE_MONTHS} peak-months "
      "AND the 95% episode-peak-month block CI excluding 0 AND the declared sign "
      "where one was declared AND BH-FDR q ≤ 0.10 within family AND ≥60% coverage). "
      f"Registered: {e1.get('registered_separating') or 'none'}. "
      f"Exploratory (discovery-only, never DETECTION): "
      f"{e1.get('exploratory_separating') or 'none'}. "
      f"By family: {e1.get('by_family', {})}.")
    A("")
    L.extend(_e1_table(e1.get("table", [])))
    A("")
    tab = e1.get("table", [])
    seps = e1.get("separating") or []
    if tab and seps:
        qa = dict(zip((r["feature"] for r in tab),
                      ta.bh_fdr([r["p_value"] for r in tab])))
        passes = [f for f in seps if qa.get(f, 1.0) <= ta.FDR_Q]
        fails = [f for f in seps if qa.get(f, 1.0) > ta.FDR_Q]
        A("**Under a FAMILY-WIDE BH instead of the prereg's within-family BH**, the "
          "survivors read "
          + ", ".join(f"`{f}` {_fmt(qa.get(f), 3)}" for f in seps)
          + f" — {', '.join('`%s`' % f for f in passes) or 'none'} still pass at "
          f"q ≤ {ta.FDR_Q}"
          + (f", and **{', '.join('`%s`' % f for f in fails)} would not**." if fails
             else "."))
        # BH is monotone-adjusted, so a feature's reported q can be INHERITED from a
        # worse-ranked sibling. Printing the raw step value keeps that legible.
        fam: dict[str, list[dict]] = {}
        for r in tab:
            fam.setdefault(r["family"], []).append(r)
        for f in seps:
            row = next((r for r in tab if r["feature"] == f), None)
            if not row:
                continue
            sib = sorted(fam[row["family"]], key=lambda r: r["p_value"])
            rank = [r["feature"] for r in sib].index(f) + 1
            step = row["p_value"] * len(sib) / rank
            if step > row["q_value"] + 1e-9:
                A(f"`{f}`'s within-family q ({_fmt(row['q_value'], 3)}) is INHERITED by "
                  f"BH monotonicity from a worse-ranked sibling; its own step value is "
                  f"{_fmt(step, 3)}.")
        A("")
    A("The block CI and the p-value are two readings of the SAME percentile "
      "distribution, so a CI that excludes zero and a small p are one piece of "
      "evidence, not two independent confirmations.")
    A("")
    below = w.get("features_below_coverage_floor", [])
    A(f"Features under the 60% coverage floor on track W (not interpreted): "
      f"{', '.join('`%s`' % f for f in below) if below else 'none'}.")
    A("")

    A("## 4. E1b — pooled AUC increment over extension + volatility (§4.7)")
    A("")
    b = w.get("e1b", {})
    if not b:
        A("Track W was not run in this pass — no E1b.")
    elif b.get("error"):
        A(f"Not computed: {b['error']}.")
    else:
        A(f"Nested: {b.get('nested')}. Preprocessing: {b.get('preprocessing')}. "
          f"Walk-forward purge = {b.get('embargo_sessions')} sessions (the full "
          "race-label horizon, so a training row's label cannot be resolved by bars "
          "inside the test window).")
        A("")
        A("| model | features | grouped-by-ticker AUC [95% CI] | walk-forward AUC "
          "[95% CI] | episode AUC (grouped) |")
        A("|---|---|---|---|---|")
        for k in ("M0", "M1", "M2"):
            mm = b.get("models", {}).get(k, {})
            g, wf = mm.get("grouped", {}), mm.get("walk_forward", {})
            gci = f"[{_fmt(g.get('ci_lo'), 3)}, {_fmt(g.get('ci_hi'), 3)}]"
            wci = f"[{_fmt(wf.get('ci_lo'), 3)}, {_fmt(wf.get('ci_hi'), 3)}]"
            A(f"| {k} | {mm.get('n_features', len(mm.get('features', [])))} | "
              f"{_fmt(g.get('auc'), 3)} {gci} | {_fmt(wf.get('auc'), 3)} {wci} | "
              f"{_fmt(g.get('episode_auc'), 3)} |")
        A("")
        # §4.7 declares day-level AND episode-level paired increments under BOTH CV
        # schemes. Printing the day-level pair alone hides a sign disagreement.
        A("All four preregistered paired increments, AUC(M2) − AUC(M1), episode-block CI:")
        A("")
        A("| level | CV scheme | ΔAUC | 95% CI |")
        A("|---|---|---|---|")
        for lvl, scheme, key in (("day", "grouped by ticker", "increment_grouped"),
                                 ("day", "walk-forward", "increment_walk_forward"),
                                 ("episode", "grouped by ticker", "episode_increment_grouped"),
                                 ("episode", "walk-forward",
                                  "episode_increment_walk_forward")):
            ci = b.get(f"{key}_ci") or [None, None]
            A(f"| {lvl} | {scheme} | {_fmt(b.get(key), 3)} | "
              f"[{_fmt(ci[0], 3)}, {_fmt(ci[1], 3)}] |")
        A("")
        dg, dw = b.get("increment_grouped"), b.get("increment_walk_forward")
        eg = b.get("episode_increment_grouped")
        ew = b.get("episode_increment_walk_forward")
        egc = b.get("episode_increment_grouped_ci") or [None, None]
        ewc = b.get("episode_increment_walk_forward_ci") or [None, None]
        scope = ""
        if None not in (dg, dw, eg, ew) and (eg < 0) != (ew < 0):
            scope = (f" — **sign-consistent at day level only** ({_fmt(dg, 3)} / "
                     f"{_fmt(dw, 3)}); at episode level the two schemes disagree "
                     f"(grouped {_fmt(eg, 3)} [{_fmt(egc[0], 3)}, {_fmt(egc[1], 3)}], "
                     f"walk-forward {_fmt(ew, 3)} [{_fmt(ewc[0], 3)}, "
                     f"{_fmt(ewc[1], 3)}])")
        A(f"The run's `sign_consistent` flag reads **{b.get('sign_consistent')}** and is "
          f"computed on the DAY-level pair{scope}. "
          f"n = {_fmt(b.get('n_rows'))} EXT days on {_fmt(b.get('n_names'))} names / "
          f"{_fmt(b.get('n_episodes_in_sample'))} episodes, base rate TOPPED = "
          f"{_fmt(b.get('base_rate_topped'), 3)}. Descriptive — E1b registers no test.")
        A("")
        m0 = (b.get("models", {}).get("M0", {}).get("walk_forward", {}) or {}).get("auc")
        m2 = (b.get("models", {}).get("M2", {}).get("walk_forward", {}) or {}).get("auc")
        if None not in (m0, m2):
            A(f"**The full library does not beat trailing return alone out of sample:** "
              f"walk-forward M2 − M0 = {_fmt((m2 - m0), 3)} "
              f"(M0 {_fmt(m0, 3)} vs M2 {_fmt(m2, 3)}).")
            A("")
        dm = d.get("e1b", {}).get("models", {})
        daucs = {k: (dm.get(k, {}).get("walk_forward", {}) or {}).get("auc")
                 for k in ("M0", "M1", "M2")}
        if daucs.get("M2") is not None and all(
                v is not None and v < 0.5 for v in daucs.values()):
            A(f"**Track D's walk-forward AUCs are below 0.50 for every model** "
              f"(M0 {_fmt(daucs['M0'], 3)}, M1 {_fmt(daucs['M1'], 3)}, "
              f"M2 {_fmt(daucs['M2'], 3)}), so its "
              f"{_fmt(d.get('e1b', {}).get('increment_walk_forward'), 3)} M2−M1 "
              "increment is movement inside a sub-coin-flip regime, not evidence of "
              "structure; D is survivorship-tilted context and registers nothing "
              "either way.")
            A("")
    A("")

    A("## 5. E2 — lead-time labels (§4.8; G0.4 is mandatory)")
    A("")
    A("A feature that separates only in the last window (`0..-5`, peak day through "
      "five sessions after) is **POST-TOP CONFIRMATION** and may never be described "
      "as detection. An exploratory field keeps an `EXPLORATORY` prefix and can never "
      "reach DETECTION grade.")
    A("")
    labels = w.get("e2", {}).get("labels", {})
    if labels:
        A("| survivor | lead-time label |")
        A("|---|---|")
        for f, lab in labels.items():
            A(f"| `{f}` | **{lab}** |")
    else:
        A(f"No survivors to profile — {w.get('e2', {}).get('note', '')}.")
    A("")
    A("Windows are stated **positive-before-peak** (`days_to_peak = peak_date − d`): "
      "EARLY +22..+63, MID +6..+21, LATE +1..+5, POST-TOP CONFIRMATION 0..−5.")
    A("")
    _window_table(A, w.get("e2", {}))
    A("")
    A("**Read the columns, not the row.** These bucket populations are a LARGER "
      "sample than E1's three frozen offsets (prereg §6-iii samples up to 2 extra EXT "
      "days per episode per bucket to populate the descriptive profile), and each "
      "window is computed on a DIFFERENT episode set — so a trend across windows is "
      "composition-confounded as well as timing-driven.")
    for tag, blk in w.get("e2", {}).get("buckets", {}).items():
        A(f"- `{tag}` ({blk.get('window', '')}): {_fmt(blk.get('n_episodes'))} episodes "
          f"from {_fmt(blk.get('n_cases'))} matched cases "
          f"({_fmt(blk.get('n_episodes_available'))} available).")
    A("")

    ws = w.get("e2_wrong_sign", {})
    if ws.get("buckets"):
        A("## 5a. The wrong-sign exhibits against the anchor explanation")
        A("")
        A("`F1`, `F3` and `B3` separate AGAINST their declared directions, and each "
          "has a mechanical counter-explanation this design cannot exclude: `F3` is "
          "partly definitional (the case day sits 5/10/21 sessions before the episode "
          "argmax while controls carry no local-max anchor), `B3` is measured over a "
          "rising leg by construction, and `F1` is what length-biased, day-weighted "
          "control sampling produces when nothing matches on age or episode length. "
          "A PURE anchor artefact strengthens monotonically as the case day "
          "approaches the peak; the same four-window machinery that profiles the "
          "survivors is the discriminating diagnostic.")
        A("")
        _window_table(A, ws)
        A("")
        A("These register nothing — the sign discipline exists so a tight CI cannot "
          "promote a backwards hypothesis — and the profile does not settle the "
          "mechanism either way. Any phase-1 re-registration must carry an "
          "anchor-matched control design that can tell anatomy from the anchor.")
        A("")

    A("## 6. E3 — first-crossing order (descriptive)")
    A("")
    order = w.get("e3", {}).get("order", [])
    if order:
        n_e1 = w.get("e1", {}).get("n_episodes")
        A("| survivor | control tail | threshold | episodes crossing (of "
          f"{_fmt(n_e1)}) | median | p25 | p75 |")
        A("|---|---|---|---|---|---|---|")
        for r in order:
            n_x = r.get("n_episodes_crossing")
            share = (f" ({100.0 * n_x / n_e1:.1f}%)"
                     if n_x is not None and n_e1 else "")
            A(f"| `{r['feature']}` | P{int(r.get('control_tail', 0.9) * 100)} | "
              f"{_fmt(r['threshold'])} | {_fmt(n_x)}{share} | "
              f"{_fmt(r['median_days_to_peak_at_first_cross'], 1)} | "
              f"{_fmt(r.get('p25'), 1)} | {_fmt(r.get('p75'), 1)} |")
        A("")
        A("Positive = sessions BEFORE the peak, so a NEGATIVE quartile is a crossing "
          "that lands AFTER the top. The denominator is every TOPPED E1 episode: an "
          "episode that never crosses contributes no row, which is why the crossing "
          "count is the honest N for this table and the median is a median over "
          "crossers only.")
    else:
        A(f"Nothing to order — {w.get('e3', {}).get('note', 'no survivors')}.")
    A("")

    A("## 7. E4 — era and dollar-volume stability (descriptive)")
    A("")
    for f in (w.get("e1", {}).get("registered_separating") or []) \
            + (w.get("e1", {}).get("exploratory_separating") or []):
        _stability_table(A, w.get("e4", {}), f, W_ERAS)
    for track_key, blk, eras in (("W", w.get("e4", {}), W_ERAS), ("D", d.get("e4", {}), D_ERAS)):
        A(f"**Track {track_key}**"
          + (" — survivorship-TILTED, era context only, never a registration claim."
             if track_key == "D" else ""))
        rows = blk.get("eras", {})
        if not rows:
            A(f"- {blk.get('note', 'track not run')}")
        for name, _, _ in eras:
            if name not in rows:
                continue
            e = rows[name]
            signs = {r["feature"]: _fmt(r["median_delta"]) for r in e.get("table", [])}
            note = "" if signs else " — under the 20-case floor, not estimated (printed null)"
            A(f"- `{name}`: {_fmt(e.get('n_episodes'))} episodes · median Δ "
              f"{signs if signs else 'null'}{note}")
        terc = blk.get("dvol_terciles", {})
        for t, e in terc.items():
            signs = {r["feature"]: _fmt(r["median_delta"]) for r in e.get("table", [])}
            A(f"- dollar-volume tercile `{t}`: {_fmt(e.get('n_episodes'))} episodes · "
              f"median Δ {signs if signs else 'null (under the 20-episode floor)'}")
        A("")

    A("## 8. The top ruler (§2) — is a fire a GOOD warning?")
    A("")
    legs = w.get("ruler", {}).get("legs", {})
    if legs:
        A("| survivor leg @ direction-aligned control tail | fires | episodes "
          "| median remaining upside to peak [95% CI] | all-EXT null remaining upside "
          "| within 5% of peak price | within ±10td of peak | fwd-63 of fires "
          "| fwd-63 excess vs null |")
        A("|---|---|---|---|---|---|---|---|---|")
        for f, r in legs.items():
            ci = r.get("median_remaining_upside_ci") or [None, None]
            A(f"| `{f}` @P{int(r.get('control_tail', 0.9) * 100)} | "
              f"{_fmt(r.get('n_fires'))} | {_fmt(r.get('n_fire_episodes'))} | "
              f"{_fmt(r.get('median_remaining_upside'), 3)} "
              f"[{_fmt(ci[0], 3)}, {_fmt(ci[1], 3)}] | "
              f"{_fmt(r.get('null_median_remaining_upside'), 4)} | "
              f"{_fmt(r.get('share_within_peak_price'), 3)} | "
              f"{_fmt(r.get('share_within_peak_time'), 3)} | "
              f"{_fmt(r.get('fwd_63_fires'), 4)} | "
              f"{_fmt(r.get('fwd_63_excess'), 4)} |")
        A("")
        ups = [r.get("median_remaining_upside") for r in legs.values()
               if r.get("median_remaining_upside") is not None]
        nul = next((r.get("null_median_remaining_upside") for r in legs.values()
                    if r.get("null_median_remaining_upside") is not None), None)
        abso = [r.get("fwd_63_fires") for r in legs.values()
                if r.get("fwd_63_fires") is not None]
        exc = [r.get("fwd_63_excess") for r in legs.values()
               if r.get("fwd_63_excess") is not None]
        tms = [r.get("share_within_peak_time") for r in legs.values()
               if r.get("share_within_peak_time") is not None]
        if ups and nul is not None:
            A(f"**Every leg's fires carry MORE remaining upside than a random extended "
              f"day** ({_fmt(min(ups), 3)}–{_fmt(max(ups), 3)} vs the all-EXT null "
              f"{_fmt(nul, 4)}) — the fires are, if anything, EARLIER in the move than "
              "the average extended day, which is the opposite of a top call.")
        if tms:
            A(f"The median NAME places at most {_fmt(100.0 * max(tms), 0)}% of its "
              f"fires within ±10 sessions of the peak "
              f"({sum(1 for t in tms if t == 0)} of {len(tms)} legs place 0%).")
        if abso and exc:
            A(f"Forward-63 after a fire is better than the all-extended-day base "
              f"(excess up to {_fmt(max(exc), 4)}) but still NEGATIVE in absolute terms "
              f"({_fmt(min(abso), 4)} to {_fmt(max(abso), 4)}). **A warning that leaves "
              "you better off than the average extended day is not a top call.**")
        A("")
        A("Every metric is computed per NAME first and then pooled by median, so one "
          "heavily-fired name cannot carry a number. A warning with large remaining "
          "upside is a bad warning even when the episode eventually tops.")
    else:
        A(f"Nothing to rule — {w.get('ruler', {}).get('note', 'no survivors')}.")
    A("")

    A("## 9. G0.2 — delisting verification (the dead names, NAMED)")
    A("")
    g = w.get("g0_2_delisting", {})
    A(f"Track W carries {_fmt(g.get('n_dead_segments'))} segments whose last bar predates "
      f"{g.get('cutoff_last_bar_before')} (60 sessions before the tape's end of "
      f"{g.get('last_data_day')}); {_fmt(g.get('n_dead_with_an_episode'))} of them were "
      f"inside an extended episode. **Gate satisfied: {g.get('gate_g0_2_satisfied')}.**")
    A("")
    named = g.get("known_delistings_found") or g.get("named", [])[:10]
    if named:
        A("Episode-carrying dead names (these resolve to ACQUISITIONS — a name that was "
          "bought is not evidence that the tape keeps names that FAILED):")
        A("")
        A("| segment | ticker | last bar |")
        A("|---|---|---|")
        for r in named[:15]:
            A(f"| `{r['segment']}` | {r['ticker']} | {r['last_bar']} |")
        A("")
    fails = g.get("verified_failures") or []
    if fails:
        A("Audited **failure** terminal bars, checked against the panel without the "
          "episode filter:")
        A("")
        A("| ticker | segment | last bar | expected | verified | held an EXT day |")
        A("|---|---|---|---|---|---|")
        for r in fails:
            A(f"| {r['ticker']} | `{r['segment']}` | {r['last_bar']} | "
              f"{r['expected_last_bar']} | "
              f"{'**yes**' if r['terminal_bar_verified'] else 'NO'} | "
              f"{'yes' if r['held_an_ext_day'] else 'no'} |")
        A("")
        A(f"{_fmt(g.get('n_verified_failures'))} of {_fmt(len(fails))} terminal bars "
          f"match their audited date, and "
          f"{_fmt(g.get('n_verified_failures_with_ext_day'))} of them ever held an "
          "extended day. The bank failures, EV collapses and take-unders are all "
          "IN the tape with bars through their final session — they simply never "
          "cleared the +50%/126-session bar, so they contribute nothing to any table "
          "above. That absence is the survivorship receipt, not a gap.")
    A("")

    A("## 10. Today's tape (G0.5) — the current extended cohort")
    A("")
    t = w.get("today_tape", {})
    cap = t.get("capped_at")
    cohort = t.get("survivor_legs", {}) or {}
    reg = (w.get("e1", {}).get("registered_separating") or [None])[0]
    if reg and reg in cohort:
        c = cohort[reg]
        A(f"**The registered leg against the cohort that exists now.** `{reg}` fires on "
          f"**{_fmt(c.get('n_fires'))} of {_fmt(t.get('n_extended_today'))} "
          f"({_fmt(c.get('pct_fires'), 1)}%)** — "
          + ("below" if (c.get("pct_fires") or 0) <
             100.0 * min(c.get("control_tail", 0.1), 1 - c.get("control_tail", 0.1))
             else "at or above")
          + " its own "
          f"{_fmt(100.0 * min(c.get('control_tail', 0.1), 1 - c.get('control_tail', 0.1)), 0)}% "
          f"control-tail base rate: {', '.join(c.get('names', [])) or 'none'} "
          f"(cohort `{reg}` min {_fmt(c.get('cohort_min'), 3)} / median "
          f"{_fmt(c.get('cohort_median'), 3)} / max {_fmt(c.get('cohort_max'), 3)}).")
        A("")
    absent = t.get("leadership_watch_absent") or []
    if absent:
        A(f"**Zero extended AI leaders**: {', '.join(absent)} are all absent from the "
          "cohort — the same exclusion that keeps gold/PGM miners out. The "
          "moderate-velocity leadership that motivated this program does not clear a "
          "+50%/126-session bar, so nothing here describes it.")
        A("")
    if cohort:
        A("| leg | fires when | threshold | fires | % of cohort | cohort min "
          "| cohort median | cohort max |")
        A("|---|---|---|---|---|---|---|---|")
        for f, c in cohort.items():
            A(f"| `{f}` | {c.get('fires_when')} | {_fmt(c.get('threshold'), 4)} | "
              f"{_fmt(c.get('n_fires'))} | {_fmt(c.get('pct_fires'), 1)}% | "
              f"{_fmt(c.get('cohort_min'), 3)} | {_fmt(c.get('cohort_median'), 3)} | "
              f"{_fmt(c.get('cohort_max'), 3)} |")
        A("")
        legs_firing = t.get("n_legs_firing", {})
        if legs_firing:
            A("Legs firing per name: "
              + ", ".join(f"{v} name(s) fire {k}" for k, v in legs_firing.items())
              + ". These are counts at descriptive thresholds — never a score, a rank, "
              "or a probability.")
            A("")
    A(f"As of **{t.get('asof')}**: {_fmt(t.get('n_extended_today'))} names are EXTENDED "
      f"under the primary definition; all {_fmt(t.get('n_rows'))} print below, ordered "
      f"by r126 ({'uncapped' if cap is None else f'capped at {cap}'}). G0.5 is a "
      "COVERAGE gate — run-1's fabricated extensions were found by reading the whole "
      "cohort, and a truncated appendix is exactly what would have hidden them. The "
      "cohort admits LEVERAGED ETFs under the floors-only eligibility (LABU, TNA, URTY "
      "and the inverse YANG are present; TNA and URTY are near-duplicate small-cap 3x "
      "vehicles), so read them as instruments, not as independent names.")
    A("")
    rows = t.get("rows", [])
    if rows:
        # Every survivor leg AND its fire flag: G0.5 asks what the discovered
        # discriminators say about the cohort that exists now, and one leg of five
        # cannot answer that.
        fire_cols = [c for c in rows[0] if c.startswith("fires_")]
        cols = ["ticker", "r126", "A4_r252", "B2_rsi14", "C6_tr5_over_tr63",
                "D1_dvol_z", "D3_updown_dvol_ratio21", "A6_ext_ma200_atr21",
                "A7_late_gain_share", "C3_semivol_ratio63", "E3f_rs_peak_lag",
                "E4f_price_rs_gap", "F1_episode_age", "F3_days_since_63d_high",
                *fire_cols]
        cols = [c for c in cols if c in rows[0]]
        heads = [c.replace("fires_", "fires ") for c in cols]
        A("| " + " | ".join(heads) + " |")
        A("|" + "---|" * len(cols))
        for r in rows:
            cells = []
            for c in cols:
                v = r.get(c)
                cells.append(("**Y**" if v else "·") if c.startswith("fires_")
                             else _fmt(v, 3))
            A("| " + " | ".join(cells) + " |")
        A("")
        A("*Display-tier readout only: these are present-tense descriptive facts about "
          "names that are already extended, not a ranking, a call, or a probability.*")
    else:
        A("*Nothing extended on the last session — that is a finding, not an empty table.*")
    A("")

    A("## 11. Who is missing (survivorship)")
    A("")
    A("**Track W is honest by construction**: it is a whole-market pull, so names that "
      "topped and then died are in the tape with bars through their final trading day "
      "(§9 names them rather than assuming them). Its own limits are stated: dividends "
      "are unadjusted, and no derivative/warrant/unit filtering is applied beyond the "
      "price and liquidity floors.")
    A("")
    dl = d.get("panel", {})
    span = (f"{_fmt(dl.get('n_segments'))} segments, {dl.get('first_session')} → "
            f"{dl.get('last_session')}" if dl.get("n_segments") else "not run in this pass")
    A("**Track D is TILTED and can never register a claim.** It is a curated-current "
      f"universe ({span}) built from the adjusted "
      "price ladder on a FIRST-RUNG-WINS basis. The names that are missing are exactly "
      "the ones this study cares most about: companies that topped and were delisted, "
      "acquired, or dropped from basket curation before the current universe was drawn. "
      "The topped arm is therefore UNDERSTATED on D, and every D number above is era "
      "context for a W finding — never standalone evidence.")
    A("")
    # Like the four opening paragraphs, §12 is adjudication PROSE written in a
    # post-run pass; the run emits the stub so the section exists in a fresh report.
    A("## 12. Adjudication — what this buys, and what it does not")
    A("")
    A("*(prose pass pending — chartered/not-chartered rulings and standing debts are "
      "written against the numbers above.)*")
    A("")
    A("---")
    A("")
    A(f"*Generated by `{summary['reproduce']}` · seed {summary['seed']} · "
      f"{summary['wall_seconds']:.0f}s wall.*")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n")


# ══════════════════════════════════════════════════════════════════════════════
# entry point
# ══════════════════════════════════════════════════════════════════════════════
def _source_file_count(data_root: Path, track: str, quick: int | None) -> int:
    """How many source files the census denominator should use (cache-hit safe)."""
    if track == "W":
        n = len(list((data_root / "massive_stock_day").glob("*.parquet")))
    else:
        names: set[str] = set()
        for _, sub in _D_RUNGS:
            d = data_root / sub
            if d.exists():
                names |= {p.stem for p in d.glob("*.parquet") if not p.stem.startswith("_")}
        n = len(names)
    return min(n, quick) if quick else n


def _git_sha() -> str:
    try:
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_REPO,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def _last_commit_for(path: str) -> str:
    """The commit that last touched a path — resolved at run time, never hardcoded.

    The G0.1 freeze proof is the ORDER (the prereg lands before any result), and
    that survives a rebase; a literal short SHA does not, because a branch rebased
    onto a moving main rewrites it. The content hash beside this field is the
    rebase-invariant half of the proof.
    """
    try:
        r = subprocess.run(["git", "log", "-1", "--format=%h", "--", path], cwd=_REPO,
                           capture_output=True, text=True, timeout=20)
        return r.stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def w2_out_json(arm: str, quick: int | None = None) -> Path:
    """The arm-keyed deliverable path (prereg §6). The arm rides in the FILENAME."""
    return _REPO / (f"data/research/top_anatomy_w2_{arm}_summary"
                    + (f"_quick{quick}" if quick else "") + ".json")


def _main_w2_roster_read(a, *, quick: bool) -> int:
    """`--w2-roster-read`: add the post-hoc roster read to an ALREADY-WRITTEN summary.

    Kept as its own mode rather than folded into `run_w2_arm` for one reason: the
    read was requested AFTER the arms had reported, and a run that emitted it inline
    would present it as part of the preregistered output. Injecting it under a
    `post_hoc` key from a named command keeps the artifact reproducible AND keeps its
    standing legible — the block says what it is, and so does the command that made it.
    """
    arm = a.w2_arm
    path = a.w2_roster_read
    summary = json.loads(path.read_text())
    if summary.get("arm") != arm:
        raise SystemExit(f"{path} is arm {summary.get('arm')!r}, not {arm!r}")
    cache = a.data_root / CACHE_SUBDIR / (f"W_quick{a.quick}" if quick else "W")
    built = build_panel_w(a.data_root, cache, quick=a.quick, allow_stale=a.allow_stale)
    block = w2_vintage_roster_read(arm, built["panel"], summary["arm_result"],
                                   seed=a.seed, quick=quick)
    block["computed_at_utc"] = pd.Timestamp.now("UTC").isoformat()
    block["computed_at_git_sha"] = _git_sha()
    block["reproduce"] = ("python -m scripts.research_top_anatomy_phase0 --data-root "
                          f"{a.data_root} --w2-arm {arm} --w2-roster-read {path}"
                          + (" --allow-stale" if a.allow_stale else ""))
    summary["vintage_roster_b2_read"] = block
    path.write_text(json.dumps(summary, indent=2, default=str))
    say(f"wrote the post-hoc roster read into {path}")
    return 0


def _main_w2(a, *, quick: bool) -> int:
    """The `--w2-arm` entry point: track W, one arm, one summary, no report prose."""
    arm = a.w2_arm
    if a.track not in ("W", "both"):
        raise SystemExit("W2 runs track W only (prereg §2) — drop --track or pass W")
    prereg = _REPO / W2_PREREG
    cache_root = a.data_root / CACHE_SUBDIR
    # The panel cache is SHARED with phase-0 on purpose: panel content carries no
    # extension definition (see `_finish_panel`), and `_load_cached`'s arm stamp is
    # what keeps anything downstream of an EXT mask from being read off it.
    cache = cache_root / (f"W_quick{a.quick}" if quick else "W")
    out_json = a.out_json if a.out_json != _REPO / "data/research/top_anatomy_p0_summary.json" \
        else w2_out_json(arm, a.quick)
    summary = {
        "family": W2_FAMILY,
        "arm": arm,
        "run_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "run_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "git_sha": _git_sha(),
        "prereg": W2_PREREG,
        "prereg_frozen": "2026-08-11",
        "prereg_sha256": _sha256(prereg),
        "prereg_frozen_commit": _last_commit_for(W2_PREREG),
        "phase0_prereg": "research/top_anatomy/TOPA_PHASE0_PREREG.md",
        "phase0_summary": "data/research/top_anatomy_p0_summary.json",
        "seed": a.seed,
        "quick": a.quick,
        "bootstrap_b": ta.BOOTSTRAP_B if not quick else 400,
        "track": "W",
        "track_note": ("track W only — the D-track's absence is a declared decision "
                       "(prereg §2), not an omission"),
        "reproduce": ("python -m scripts.research_top_anatomy_phase0 "
                      f"--data-root {a.data_root} --w2-arm {arm}"
                      + (f" --quick {a.quick}" if quick else "")
                      + (" --allow-stale" if a.allow_stale else "")),
        # The W2 tape is DELIBERATELY the phase-0 vintage (prereg §2: "the SAME
        # vintage as phase-0 — tier definition is the only moved variable"; §7
        # re-verified it at 2026-07-02 and accepted same-vintage comparability as a
        # feature). #5319's local-mirror refusal fires at 20 trading sessions
        # behind, which that vintage now is, so a W2 re-run needs --allow-stale —
        # the guard's banner is the receipt that the staleness is chosen, not
        # unnoticed. Refreshing the store instead would BREAK the prereg.
        "vintage_is_prereg_declared": True,
        "vintage_note": ("prereg §2 pins the phase-0 tape vintage; post-#5319 a "
                         "re-run requires --allow-stale, and the printed banner is "
                         "the receipt that the vintage is chosen rather than stale "
                         "by accident"),
        "allow_stale": bool(a.allow_stale),
        "engine_frozen": ("engine/top_anatomy.py is byte-frozen at main for this wave; "
                          "the arms are its existing extended_mask(variant=...) masks"),
        "tier": ("research/display tier, zero scored authority; AVOID-not-SHORT; "
                 "no rank, no size, no gate, no exit rule"),
        "wall_limit_seconds": W2_WALL_LIMIT_SECONDS,
    }
    built = build_panel_w(a.data_root, cache, quick=a.quick,
                          allow_stale=a.allow_stale)
    n_files = _source_file_count(a.data_root, "W", a.quick)
    summary["arm_result"] = run_w2_arm(arm, built["panel"], built["meta"], a.data_root,
                                       seed=a.seed, quick=quick, n_files=n_files)
    summary["wall_seconds"] = time.time() - _T0
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, default=str))
    say(f"wrote {out_json}")
    say(f"done in {summary['wall_seconds']:.0f}s")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", required=True, type=Path,
                    help="primary checkout's data/ directory (panels + cache live here)")
    ap.add_argument("--track", choices=("W", "D", "both"), default="both")
    ap.add_argument("--quick", type=int, default=None,
                    help="first N tickers alphabetically per track (smoke run)")
    ap.add_argument("--w2-arm", choices=W2_ARMS, default=None,
                    help="run the W2 tier-widening arm instead of phase-0 "
                         f"({W2_PREREG}); track W only, writes its own summary")
    ap.add_argument("--w2-roster-read", type=Path, default=None,
                    help="add the POST-HOC vintage-date roster read for "
                         f"{W2_ROSTER_READ_FEATURE} to an already-written W2 arm "
                         "summary (needs --w2-arm); descriptive, never a registered "
                         "quantity")
    ap.add_argument("--allow-stale", action="store_true",
                    help="run track W against a local massive_stock_day mirror that is "
                         "20+ trading sessions behind (refused by default; the banner "
                         "still prints and the numbers are as of the mirror's date). "
                         "REQUIRED by --w2-arm: W2 pins the phase-0 vintage on purpose "
                         "(prereg §2), and that mirror is now past the refusal bar")
    ap.add_argument("--out-json", type=Path,
                    default=_REPO / "data/research/top_anatomy_p0_summary.json")
    ap.add_argument("--out-report", type=Path,
                    default=_REPO / "reports/top-anatomy-phase0.md")
    ap.add_argument("--seed", type=int, default=20260810)
    a = ap.parse_args(argv)

    quick = a.quick is not None
    if a.w2_roster_read is not None:
        if not a.w2_arm:
            raise SystemExit("--w2-roster-read needs --w2-arm to name the arm")
        return _main_w2_roster_read(a, quick=quick)
    if a.w2_arm:
        return _main_w2(a, quick=quick)
    cache_root = a.data_root / CACHE_SUBDIR
    tracks = ["W", "D"] if a.track == "both" else [a.track]
    summary = {
        "family": FAMILY,
        "run_date": pd.Timestamp.now("UTC").strftime("%Y-%m-%d"),
        "run_timestamp_utc": pd.Timestamp.now("UTC").isoformat(),
        "git_sha": _git_sha(),
        "prereg": "research/top_anatomy/TOPA_PHASE0_PREREG.md",
        "prereg_frozen": "2026-08-10",
        "seed": a.seed,
        "quick": a.quick,
        "reproduce": ("python -m scripts.research_top_anatomy_phase0 "
                      f"--data-root {a.data_root}"
                      + (f" --track {a.track}" if a.track != "both" else "")
                      + (f" --quick {a.quick}" if quick else "")
                      + (" --allow-stale" if a.allow_stale else "")),
        "tier": ("research/display tier, zero scored authority; AVOID-not-SHORT; "
                 "no rank, no size, no gate, no exit rule"),
        "tracks": {},
    }
    # §6 repair arm. The audit runs against the PRE-REPAIR panel; once that cache has
    # been rebuilt under the repaired rules it cannot be recomputed, so the recorded
    # measurement is carried from the preserved artifact rather than re-derived.
    summary["repair_arm"] = {
        "arm": W_REPAIR_ARM,
        "trigger": ("scripts/replay_standout_pipeline._COMMON_SPLITS carries reverse "
                    "splits only to 1:10, so 1:15..1:125 reverse splits survive the "
                    "repair as fabricated +900%..+12,200% single days and manufacture "
                    "EXTENDED days out of a corporate action"),
        "rule": (f"identity break at any residual single-day close ratio >= "
                 f"{W_RESIDUAL_UP_RATIO_BREAK} in the REPAIRED series (UP side only; "
                 "the down side is deliberately unscreened because a one-day collapse "
                 "is a real event)"),
        "not_done": ("_COMMON_SPLITS was NOT widened: a dense reverse grid at 10% snap "
                     "tolerance would 'repair' real squeezes — a genuine +400% day lands "
                     "exactly on 1/5"),
        "prerepair_summary": (str(PREREPAIR_SUMMARY.relative_to(_REPO))
                              if PREREPAIR_SUMMARY.exists() else None),
        "run2_summary": (str(RUN2_SUMMARY.relative_to(_REPO))
                         if RUN2_SUMMARY.exists() else None),
    }
    if "W" in tracks:
        audit = run1_contamination_audit(
            cache_root / (f"W_quick{a.quick}" if quick else "W"))
        if not audit.get("available"):
            audit = preserved_contamination(RUN2_SUMMARY, audit.get("reason")) or audit
        summary["repair_arm"]["contamination"] = audit
    for label, src in (("run1", PREREPAIR_SUMMARY), ("run2", RUN2_SUMMARY)):
        if not src.exists():
            continue
        try:
            summary["repair_arm"][label] = _arm_headline(json.loads(src.read_text()))
        except Exception as exc:  # noqa: BLE001 — the audit trail never kills the run
            summary["repair_arm"][f"{label}_error"] = str(exc)

    for tk in tracks:
        cache = cache_root / (f"W_quick{a.quick}" if (tk == "W" and quick) else
                              f"D_quick{a.quick}" if (tk == "D" and quick) else tk)
        built = (build_panel_w(a.data_root, cache, quick=a.quick,
                               allow_stale=a.allow_stale) if tk == "W"
                 else build_panel_d(a.data_root, cache, quick=a.quick))
        n_files = _source_file_count(a.data_root, tk, a.quick)
        summary["tracks"][tk] = run_track(tk, built["panel"], built["meta"],
                                          seed=a.seed, quick=quick, n_files=n_files)
        say(f"track {tk} complete")

    summary["wall_seconds"] = time.time() - _T0
    a.out_json.parent.mkdir(parents=True, exist_ok=True)
    a.out_json.write_text(json.dumps(summary, indent=2, default=str))
    write_report(a.out_report, summary)
    say(f"wrote {a.out_json}")
    say(f"wrote {a.out_report}")
    say(f"done in {summary['wall_seconds']:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
