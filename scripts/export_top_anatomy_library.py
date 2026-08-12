#!/usr/bin/env python3
"""Export the TOP ANATOMY analog library + the frozen display thresholds (ONE-SHOT).

WHAT THIS IS. The bridge between the Phase-0 research harness
(`scripts/research_top_anatomy_phase0.py`, whose panel cache this reads) and the
nightly display surface (`engine/top_maturation.py` → Winner Health). It writes
two committed artifacts:

  data/top_anatomy/library.parquet   the analog-memory library: one row per
                                     SAMPLED track-W EXT day, carrying the six
                                     kNN dimensions and what that day's run went
                                     on to do.
  data/top_anatomy/thresholds.json   the frozen display-heuristic constants — the
                                     P90/P10 of each leg feature over the
                                     library's CONTINUED-labelled days.

Both are FROZEN CONSTANTS for the nightly: it reads them, it never recomputes
them. Re-running this exporter is the only way they change, and that is a
deliberate, reviewable act.

TIER. Display / research tier with ZERO scored authority, inherited wholesale
from `engine.top_anatomy`. Nothing here ranks, gates, sizes or escalates; the
outputs feed plain-word context beside a name a human already owns. This is the
AVOID-not-SHORT lobe (`DNR:KILL-DIRECTIONAL-SHORTING`). Promotion of anything
here to authority needs its own gauntlet prereg and an operator ruling.

WHY THE LIBRARY IS THE SYSTEMATIC SAMPLE ONLY (judgment call, recorded).
The harness computes features on the UNION of five day-sets: the 1-in-5
systematic EXT sample, the §4.5 CASE days (21/10/5 sessions before a TOPPED
episode peak), their matched CONTROLS, the E2 lead-time days and the E3 days.
Those four extra arms exist to make a MATCHED-INFERENCE contrast and are
case-enriched on purpose. Pooling them into a neighbour library would inflate
every base rate the Winner Health card prints — a reader would be told "14 of 41
fell back hard" from a sample deliberately over-weighted toward runs that
topped. So the library is exactly the harness's 1-in-`SAMPLE_EVERY` systematic
sample of ALL EXT days: an unbiased 20% slice of the tape, which is what a base
rate needs. The `sample_arm` column records the provenance so a future arm can be
appended without re-reading this docstring.

PURITY. Reads the harness's cached panel parquets and `engine.top_anatomy`.
Writes only under `--root`. Never touches the harness cache.

PER-TIER LIBRARIES (W2b). `--variant` cuts the whole pipeline through one of the
three §4.1 extension definitions and writes a SUFFIXED pair
(`library_r63.parquet` + `thresholds_r63.json`, and the `atrz` siblings). The
primary pair keeps its unsuffixed names. Nothing is shared between them: each
tier's thresholds are the P90/P10 of ITS OWN CONTINUED-labelled days, which is
what lets the surface promise that no threshold ever crosses a tier boundary.

Usage:
    python -m scripts.export_top_anatomy_library --data-root <primary>/data
    python -m scripts.export_top_anatomy_library --data-root <...>/data \
        --root <...>/data --track W
    python -m scripts.export_top_anatomy_library --data-root <...>/data \
        --root <...>/data --variant r63
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from engine import top_anatomy as ta  # noqa: E402

CACHE_SUBDIR = "research/top_anatomy_p0"
#: Mirrors `scripts.research_top_anatomy_phase0.SAMPLE_EVERY`. Kept as a literal
#: rather than imported so this exporter does not drag the harness's own imports
#: (and its module-level clock) into a one-shot build.
SAMPLE_EVERY = 5
PANEL_COLS = ("close", "open", "high", "low", "volume", "raw_close", "raw_dvol",
              "split_day")

#: The six standardised dimensions the nightly matches on. Shape and age only —
#: never the company, never its industry (the card says so in as many words).
KNN_DIMS = ("r126", "r63", "late_gain_share", "episode_age", "rv_ratio",
            "drawdown_in_episode")
#: library column  ->  the frozen `engine.top_anatomy` feature it carries.
_FEATURE_MAP = {
    "r126": "A3_r126",
    "r63": "A2_r63",
    "late_gain_share": "A7_late_gain_share",
    "episode_age": "F1_episode_age",
    "rv_ratio": "C2_rv21_over_rv63",
    "drawdown_in_episode": "F2_drawdown_in_episode",
    "rs_peak_lag": "E3f_rs_peak_lag",
    "rs_decel": "E5f_rs_decel",
    "ppe_chg21": "D4_ppe_chg21",
    "updown_dvol": "D3_updown_dvol_ratio21",
    "semivol_ratio": "C3_semivol_ratio63",
    #: Backs the W2b `running_hot` leg ("hotter than most like it") on the two
    #: WIDENED tiers only. Carried for every variant so a tier's own P90 can be
    #: cut from its own CONTINUED days; whether the leg RENDERS is a per-tier
    #: decision in `engine.top_maturation`, never a function of a threshold
    #: happening to exist here.
    "rsi14": "B2_rsi14",
}

#: leg key -> (library column, quantile). The direction is the leg's own firing
#: side: a P90 leg fires HIGH, a P10 leg fires LOW. Read by
#: `engine.top_maturation` and by nothing else.
THRESHOLD_SPEC = {
    "rs_peak_lag_p90": ("rs_peak_lag", 0.90),
    "rs_decel_p10": ("rs_decel", 0.10),
    "effort_result_p10": ("ppe_chg21", 0.10),
    "updown_volume_p10": ("updown_dvol", 0.10),
    "vol_asymmetry_p90": ("semivol_ratio", 0.90),
    "late_verticality_p90": ("late_gain_share", 0.90),
    "episode_age_p90": ("episode_age", 0.90),
    "running_hot_p90": ("rsi14", 0.90),
}

#: The "fell back hard" barrier the analog card prints, and its horizon. Both are
#: echoed into `wh.library` so the surface can never describe a barrier the
#: library did not measure.
FELL_BACK_DD = 0.20
FELL_BACK_HORIZON_TD = 63
POST_PEAK_WINDOW = 126

_T0 = time.time()


def say(msg: str) -> None:
    """Plain progress print — off-lane, so no GitHub annotations."""
    print(f"[{time.time() - _T0:7.1f}s] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# the harness panel cache
# ══════════════════════════════════════════════════════════════════════════════
def panel_identity_stamp(cache: Path) -> dict:
    """The identity rules the cached panel was segmented under — FAIL CLOSED.

    The harness's own `_load_cached` refuses an UNSTAMPED cache because an absent
    stamp means "some other line segmented this panel", and seeding features from
    it runs a track on whatever rule happened to write it. The same hazard lands
    here one step downstream and is strictly worse: these thresholds are FROZEN
    into the nightly, so a library cut from the wrong panel would keep defining
    "showing wear" for every future night, silently, long after the panel that
    produced it was replaced.

    Two stamp formats have existed for the repaired rule — the flat
    `residual_up_ratio_break` + `repair_arm` pair, and the older `identity_rules`
    dict (`{max_gap_sessions, jump_ratio}`). Either is accepted and BOTH are
    recorded verbatim into thresholds.json, so the artifact carries the identity
    of the panel it was cut from and a reader never has to trust a filename.
    Deliberately NOT an equality check against a hard-coded rule: the harness owns
    which value each track needs, and duplicating that constant here is how the
    two drift apart. Presence is what this guard can honestly assert.
    """
    meta = json.loads((cache / "meta.json").read_text())
    stamp = {k: meta[k] for k in ("residual_up_ratio_break", "repair_arm",
                                  "identity_rules", "n_segments", "n_tickers")
             if k in meta}
    if (meta.get("residual_up_ratio_break") is None
            and (meta.get("identity_rules") or {}).get("jump_ratio") is None
            and meta.get("repair_arm") is None):
        raise SystemExit(
            f"panel cache at {cache} carries NO identity-rule stamp — refusing to cut "
            f"frozen thresholds from a panel whose segmentation rule is unknown. Re-run "
            f"scripts.research_top_anatomy_phase0 so it writes a stamped meta.json.")
    return stamp


def load_panel(cache: Path) -> dict[str, pd.DataFrame]:
    """Read the harness's cached wide panel frames (read-only, never written)."""
    if not (cache / "meta.json").exists():
        raise SystemExit(
            f"no harness panel cache at {cache} — run scripts.research_top_anatomy_phase0 "
            f"first (it writes panel_*.parquet + meta.json there)")
    missing = [c for c in ("close", "raw_close", "raw_dvol", "split_day")
               if not (cache / f"panel_{c}.parquet").exists()]
    if missing:
        raise SystemExit(
            f"panel cache at {cache} predates the raw-eligibility legs ({', '.join(missing)}); "
            f"delete it and let the harness rebuild")
    panel: dict[str, pd.DataFrame] = {}
    for c in PANEL_COLS:
        p = cache / f"panel_{c}.parquet"
        if p.exists():
            fr = pd.read_parquet(p)
            panel[c] = fr.fillna(False).astype(bool) if c == "split_day" else fr
    return panel


def segment_bars(panel: dict[str, pd.DataFrame], segments) -> dict[str, pd.DataFrame]:
    """Per-segment OHLCV frames compacted to their own bars (harness idiom)."""
    close = panel["close"]
    out: dict[str, pd.DataFrame] = {}
    for s in segments:
        if s not in close.columns:
            continue
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


# ══════════════════════════════════════════════════════════════════════════════
# outcomes
# ══════════════════════════════════════════════════════════════════════════════
def post_peak_drawdowns(close_df: pd.DataFrame, episodes: pd.DataFrame,
                        *, window: int = POST_PEAK_WINDOW) -> pd.DataFrame:
    """Deepest close-to-close drawdown from each episode's peak, inside `window` bars.

    Returned NEGATIVE (a −0.24 is a 24% give-back), and NaN when the window ran
    off the end of the tape with nothing observed — an unobserved give-back is a
    null, never a zero.
    """
    rows = []
    for col, grp in episodes.groupby("segment", sort=False):
        c = close_df[col] if col in close_df.columns else None
        if c is None:
            continue
        c = c[c.notna()]
        if c.empty:
            continue
        v = c.to_numpy(dtype=float)
        pos = pd.Series(np.arange(len(v)), index=c.index)
        for _, ep in grp.iterrows():
            pk_date = ep.get("peak_date")
            if pk_date is None or pd.isna(pk_date) or pk_date not in pos.index:
                continue
            pk = int(pos[pk_date])
            pk_c = float(v[pk])
            fwd = v[pk + 1:min(len(v), pk + window + 1)]
            dd = float(np.nanmin(fwd) / pk_c - 1.0) if fwd.size and pk_c > 0 else np.nan
            rows.append({"episode_id": ep["episode_id"], "post_peak_dd_126": dd})
    return pd.DataFrame(rows, columns=["episode_id", "post_peak_dd_126"])


# ══════════════════════════════════════════════════════════════════════════════
# the library
# ══════════════════════════════════════════════════════════════════════════════
def build_library(panel: dict[str, pd.DataFrame], track: str,
                  variant: str = "primary") -> tuple[pd.DataFrame, dict]:
    """EXT → episodes → race → peaks → the sampled analog library.

    ``variant`` selects the §4.1 EXTENSION DEFINITION this library is cut through
    (`engine.top_anatomy.extended_mask`): `primary` (r126>=+0.50), `r63`
    (r63>=+0.35) or `atrz` ((close-MA200)/ATR63>=6). EVERYTHING downstream — the
    episodes, the race labels, the peaks, the sampled days and therefore every
    P90/P10 cut in `build_thresholds` — is re-derived from that mask, so a tier's
    library and its thresholds are cut from that tier's own history and from no
    other's. That is the whole point: the surface may never borrow a threshold
    across tiers, so the artifacts may not either.

    The PANEL is deliberately shared across variants and this is sound, not a
    shortcut: `research_top_anatomy_phase0._finish_panel` documents that panel
    content is UPSTREAM of every EXT mask (`repair_bars` and
    `split_identity_segments` read raw prints and tape gaps only), which is why a
    panel is honestly stamped `ext_variant: None`. Re-running the harness per arm
    would rebuild byte-identical panel frames.
    """
    close = panel["close"]
    volume = panel.get("volume")
    dvol = ((close * volume).reindex_like(close)
            if volume is not None and not volume.empty
            else pd.DataFrame(np.nan, index=close.index, columns=close.columns))
    floors = {
        "raw_close_df": panel.get("raw_close"),
        "raw_dollar_vol_df": panel.get("raw_dvol"),
        "split_day_df": panel.get("split_day"),
    }
    floors = {k: (v if v is not None and not v.empty else None) for k, v in floors.items()}

    say(f"[{track}] §3 eligibility + the PIT equal-weight median index")
    elig = ta.eligibility_mask(close, dvol, **floors)
    eqw = ta.equal_weight_median_index(close, elig, min_names=20)

    say(f"[{track}] §4.1 EXT mask (variant={variant})")
    ext = ta.extended_mask(close, dvol, variant=variant, high_df=panel.get("high"),
                           low_df=panel.get("low"), **floors)
    n_ext = int(ext.to_numpy().sum())
    say(f"[{track}] {n_ext} EXT days on {int((ext.sum() > 0).sum())} segments")
    if n_ext == 0:
        raise SystemExit(f"track {track}: no EXT days — nothing to export")

    say(f"[{track}] §4.2 episodes")
    episodes = ta.extract_episodes(ext, close)
    say(f"[{track}] {len(episodes)} episodes on {episodes['ticker'].nunique()} names")

    say(f"[{track}] §4.3 race labels (this is the slow leg)")
    race = ta.race_labels(close, ext)

    say(f"[{track}] §4.4 episode peaks")
    episodes, dtp = ta.episode_peaks(close, episodes, ext)

    sample = race.iloc[::SAMPLE_EVERY].copy()
    say(f"[{track}] 1-in-{SAMPLE_EVERY} systematic sample: {len(sample)} EXT days")

    say(f"[{track}] §4.6 features on the sample")
    bars = segment_bars(panel, sorted(set(sample["segment"])))
    feats = ta.feature_library(bars, eqw, sample[["segment", "date"]], episodes=episodes)

    keep_race = ["segment", "date", "entry_close", "label", "max_dd_63"]
    keep_race = [c for c in keep_race if c in sample.columns]
    lib = feats.merge(sample[keep_race], on=["segment", "date"], how="inner")
    lib = lib.merge(dtp[["segment", "date", "episode_id"]], on=["segment", "date"], how="left")
    ep_cols = ["episode_id", "outcome", "peak_close", "peak_date", "micro",
               "peak_window_censored"]
    lib = lib.merge(episodes[[c for c in ep_cols if c in episodes.columns]],
                    on="episode_id", how="left")
    lib = lib.merge(post_peak_drawdowns(close, episodes), on="episode_id", how="left")

    # remaining upside to the episode's own peak — negative for a day already past
    # it, which is the honest reading and not an error.
    lib["remaining_upside"] = np.where(
        (lib["entry_close"] > 0) & lib["peak_close"].notna(),
        lib["peak_close"] / lib["entry_close"].replace(0.0, np.nan) - 1.0, np.nan)
    lib["fell_back_hard_63"] = (lib.get("max_dd_63", pd.Series(np.nan, index=lib.index))
                                <= -FELL_BACK_DD).fillna(False).astype(bool)

    out = pd.DataFrame({
        "ticker": lib["ticker"].astype("string"),
        "segment": lib["segment"].astype("string"),
        "date": pd.to_datetime(lib["date"]),
        "episode_id": lib["episode_id"].astype("string"),
        "episode_outcome": lib["outcome"].astype("string"),
        "race_label": lib["label"].astype("string"),
        "sample_arm": pd.Series(["systematic"] * len(lib), dtype="string"),
    })
    for name, feat in _FEATURE_MAP.items():
        out[name] = pd.to_numeric(lib[feat], errors="coerce").astype("float32")
    for name in ("remaining_upside", "post_peak_dd_126"):
        out[name] = pd.to_numeric(lib[name], errors="coerce").astype("float32")
    out["fell_back_hard_63"] = lib["fell_back_hard_63"].astype(bool)
    out["track"] = pd.Series([track] * len(lib), dtype="string")

    # A neighbour with a hole in any matching dimension cannot be matched ON, and
    # imputing one would fabricate a shape. Dropped here, counted, never filled.
    before = len(out)
    out = out.dropna(subset=list(KNN_DIMS)).reset_index(drop=True)
    diag = {
        "n_ext_days": n_ext,
        "n_episodes": int(len(episodes)),
        "n_sampled_days": int(before),
        "n_rows": int(len(out)),
        "n_dropped_incomplete_knn_dims": int(before - len(out)),
        "n_names": int(out["ticker"].nunique()) if len(out) else 0,
        "n_library_episodes": int(out["episode_id"].nunique()) if len(out) else 0,
        "race_label_counts": ({k: int(v) for k, v in
                               out["race_label"].value_counts().to_dict().items()}
                              if len(out) else {}),
        "episode_outcome_counts": ({k: int(v) for k, v in
                                    out["episode_outcome"].value_counts().to_dict().items()}
                                   if len(out) else {}),
        "fell_back_hard_rate": float(out["fell_back_hard_63"].mean()) if len(out) else None,
    }
    return out, diag


def build_thresholds(lib: pd.DataFrame, track: str, diag: dict,
                     panel_stamp: dict | None = None,
                     variant: str = "primary") -> dict:
    """P90/P10 of each leg feature over the library's CONTINUED-labelled days.

    CONTINUED is the reference population on purpose: a leg should fire when a
    name looks unlike the runs that KEPT GOING, so the yardstick is drawn from
    those runs and not from the pooled tape (which already contains the tops).

    ``ext_variant`` is stamped into the artifact because these constants are
    FROZEN into the nightly per tier. A reader — and
    `engine.top_maturation.load_thresholds` — must be able to tell which
    extension definition a threshold was cut through WITHOUT trusting a filename;
    the surface's one hard rule is that no threshold crosses a tier boundary, and
    a stamp is what makes that auditable after the fact.
    """
    ref = lib[lib["race_label"] == "CONTINUED"]
    if len(ref) < 200:                       # too thin to cut a tail on
        say(f"WARNING: only {len(ref)} CONTINUED rows — thresholds fall back to the "
            f"full library")
        ref = lib
    thresholds: dict[str, float | None] = {}
    coverage: dict[str, float] = {}
    for key, (col, q) in THRESHOLD_SPEC.items():
        s = pd.to_numeric(ref[col], errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
        coverage[key] = round(float(len(s) / len(ref)), 4) if len(ref) else 0.0
        thresholds[key] = float(np.quantile(s, q)) if len(s) >= 100 else None
    dates = pd.to_datetime(lib["date"])
    return {
        "vintage_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "track": track,
        "ext_variant": variant,
        "source": "scripts/export_top_anatomy_library.py",
        # WHICH PANEL these frozen constants were cut from. Carried in the
        # artifact so a reader can tell a run-1 threshold from a run-3 one without
        # trusting a filename or a vintage timestamp.
        "panel_identity": panel_stamp or {},
        "reference_population": "CONTINUED-labelled days in the library",
        "n_reference_rows": int(len(ref)),
        "n_library_rows": int(len(lib)),
        "n_library_episodes": diag.get("n_library_episodes"),
        "window_start": str(dates.min().date()) if len(dates) else None,
        "window_end": str(dates.max().date()) if len(dates) else None,
        "fell_back_hard_drawdown_pct": int(FELL_BACK_DD * 100),
        "fell_back_hard_horizon_td": FELL_BACK_HORIZON_TD,
        "post_peak_window_td": POST_PEAK_WINDOW,
        "thresholds": thresholds,
        "coverage": coverage,
        "diagnostics": diag,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--data-root", required=True, type=Path,
                    help="data root holding research/top_anatomy_p0/ (the harness cache)")
    ap.add_argument("--root", type=Path, default=None,
                    help="data root to WRITE into (default: this repo's data/)")
    ap.add_argument("--track", default="W", choices=("W", "D"),
                    help="which harness track's cache to export (default W)")
    ap.add_argument("--variant", default="primary", choices=("primary", "r63", "atrz"),
                    help="which §4.1 extension definition to cut this library through "
                         "(default primary). Non-primary variants write SUFFIXED "
                         "artifacts and never overwrite the frozen primary pair.")
    a = ap.parse_args(argv)

    out_root = a.root if a.root is not None else (_REPO / "data")
    out_dir = out_root / "top_anatomy"
    out_dir.mkdir(parents=True, exist_ok=True)
    cache = a.data_root / CACHE_SUBDIR / a.track
    # The primary pair keeps its historical unsuffixed names — it is a frozen,
    # committed artifact the nightly already reads, and renaming it would be a
    # silent re-cut of the live board.
    sfx = "" if a.variant == "primary" else f"_{a.variant}"

    say(f"reading harness panel cache {cache}")
    stamp = panel_identity_stamp(cache)
    say(f"panel identity: {json.dumps(stamp, sort_keys=True)}")
    panel = load_panel(cache)
    say(f"panel: {panel['close'].shape[0]} sessions x {panel['close'].shape[1]} segments")

    lib, diag = build_library(panel, a.track, variant=a.variant)
    diag["ext_variant"] = a.variant
    lib_path = out_dir / f"library{sfx}.parquet"
    lib.to_parquet(lib_path, index=False, compression="snappy")
    size_mb = lib_path.stat().st_size / 1e6

    thr = build_thresholds(lib, a.track, diag, panel_stamp=stamp, variant=a.variant)
    thr["library_bytes"] = int(lib_path.stat().st_size)
    thr_path = out_dir / f"thresholds{sfx}.json"
    thr_path.write_text(json.dumps(thr, indent=2) + "\n")

    say(f"wrote {lib_path} — {len(lib)} rows, {size_mb:.1f} MB")
    say(f"wrote {thr_path}")
    for k, v in thr["thresholds"].items():
        say(f"  {k:24s} = {'null' if v is None else f'{v:.5g}'}")
    if size_mb > 10.0:
        say(f"NOTE: library is {size_mb:.1f} MB (>10 MB) — flag for an R2 decision; "
            f"this exporter deliberately does not wire R2 itself")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
