#!/usr/bin/env python3
"""CN LIMIT-MOVE ALPHA — P-B2: matched precursor discrimination.

    TZ=UTC python3 research/cn_prophet_audit/pb2_precursor_discrimination.py

AUTHORITY: `none_research_display_only`.  Nothing in this file or its receipts ranks,
sizes, gates, alerts, trades or feeds any production score.  There is NO P-B2 production
ranker: the flagged-set diagnostics of prereg sec.10 are descriptive and end inside the
receipt.  No name is ranked, no threshold is tuned, no production use is proposed.

THE PRE-REGISTRATION IS THE CONTRACT, AND IT IS NOT IN THIS FILE.  Every definition,
threshold, stratum, gate, floor and disposition rule below is read from
`research/cn_prophet_audit/PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md`, which was
committed to git BEFORE the first outcome run of this instrument.  The commit order in
history is the proof that the design preceded the result.  The prereg file is pinned by
sha256 in every receipt.  Deviations are NUMBERED AMENDMENTS in `AMENDMENTS` below and in
both receipts — never silent re-choices.

STOP-SHIP compliance: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` governs.  No withdrawn
artifact, number or receipt is cited.  Grep-verified every run over the instrument source
AND the emitted prose (`verify.stop_ship_reference_scan`, P-B's fragment-assembled scan
imported rather than re-written).

===============================================================================
THE QUESTION (prereg sec.1)
===============================================================================
Among lawful cold A-share name-date states on the W-P0 panel, which of the already-frozen
P-B footprint families carry information about a FIRST tolerant limit-up close within the
next H = 10 of the name's own sessions (secondary H = 5) — beyond session, board,
volatility and, in the M1 arm, the washout carrier itself?

ESTIMAND SCOPE, STATED UP FRONT: all strata are within-session, so every verdict here is a
WITHIN-SESSION CROSS-SECTIONAL statement — does the footprint separate names on the same
tape on the same day.  A null says nothing about market-wide or regime-timing information
in the same family; a "boards cluster when the whole tape is washed out" mechanism is
removed by the session stratum BY CONSTRUCTION.  Instrument verdicts are not market
verdicts.

-------------------------------------------------------------------------------
NO THIRD IMPLEMENTATION (the pin)
-------------------------------------------------------------------------------
The panel, the tolerant detector, the cold rule, the outcome columns, the bands, the
splits, the eras and the eight footprints are IMPORTED — from W-P0
(`washout_onset_w1.py`) and from P-B (`pb_case_decomposition.py`), both import-safe.  This
file re-derives none of them.  Both modules are pinned by sha256 AND by a line-pin table
(`PIN_SYMBOLS_W1`, `PIN_SYMBOLS_PB`); a pin mismatch REFUSES THE RUN before either receipt
is written.  P-B's own helpers are reused directly: `stop_ship_scan`, `_probe`, `jsonable`,
`md_table`, `_r`, `_git`, `build_footprint_panel`, `derive_footprints`, `extract_events`.

WHAT IS NEW HERE, and therefore implemented here: the matched estimator's inference
machinery (block/cluster bootstraps, the fixed-margin permutation, the placebo-feature
calibration), the measurability masks, the quiet-control completeness rule, and the verdict
gates.  Nothing in that list re-derives a W-P0 or P-B definition.

-------------------------------------------------------------------------------
INHERITED LIMITS (they travel with the pin; restating them is not optional)
-------------------------------------------------------------------------------
* BACK-ADJUSTED BASIS — a tolerant-detector cohort, not an exchange-exact legal-limit
  cohort.  The reopen chain to authority-tier limit work is untouched by this study.
* SURVIVORS ONLY, LARGE-CAP SLICE — delisted names are absent from the store.
* CURRENT SECTOR MEMBERSHIP applied to 15 years of history.

-------------------------------------------------------------------------------
COMPUTE DISCIPLINE (prereg sec.12) AND DETERMINISM
-------------------------------------------------------------------------------
The permutation, the session-block bootstrap and the row bootstrap all run on per-stratum
sufficient-statistic tables (n_F1, k_F1, n_F0, k_F0) computed once — never on rows.  The
naive whole-matrix draw at M1's stratum count is a multi-GB allocation and is forbidden.
The session-block bootstrap additionally pre-aggregates strata to BLOCKS, which is exact
(a block weight is constant across the strata it contains) and turns a 4000 x 340k matrix
into a 4000 x ~150 one.  The NAME bootstrap is the one arithmetic that cannot live on the
stratum table — a name's rows span many strata — and prereg sec.6.1 prescribes its form
directly ("name-cluster bootstrap via weighted-row bincount"): rows are weighted by their
name's draw count and the strata are re-aggregated, implemented as four sparse
(stratum x name) incidence matrices times one (name x draw) count matrix, CHUNKED OVER
STRATA so no draw matrix is ever materialised whole.

Every random stream is derived from `SeedSequence(entropy=SEED, spawn_key=<sha256 digest of
the stream's identity>)`, so a stream depends on WHAT is being computed and never on the
order in which cells are visited: reordering, adding or skipping a cell cannot move another
cell's numbers.  Run under TZ=UTC from the repo root.  No wall-clock, runtime, hostname or
locale-dependent ordering enters either receipt; the artifact date is a frozen constant.
Two consecutive full runs at the same commit produce BYTE-IDENTICAL receipts.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from collections import OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.sparse as sps

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "research" / "cn_prophet_audit"
W1_PATH = OUT_DIR / "washout_onset_w1.py"
PB_PATH = OUT_DIR / "pb_case_decomposition.py"
PREREG_PATH = OUT_DIR / "PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md"

# FROZEN. The UTC date this artifact was built. Never computed from the clock.
ARTIFACT_DATE = "2026-08-14"

OUT_JSON_NAME = f"PB2_PRECURSOR_DISCRIMINATION_{ARTIFACT_DATE}.json"
OUT_MD_NAME = f"PB2_PRECURSOR_DISCRIMINATION_{ARTIFACT_DATE}.md"

RAW_DIR = REPO / "data" / "china_stocks_raw"
ZT_P = REPO / "data" / "china_zt_pool" / "pool.parquet"

AUTHORITY = "none_research_display_only"
TIER_STAMP = ("display / research tier — a matched, split-disciplined, WITHIN-SESSION "
              "CROSS-SECTIONAL discrimination study; not a promotion, not a gate, not a "
              "ranker, not a sizing input, and no production consumer exists or is "
              "proposed")
GOVERNING_RULING = "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT"
PROGRAM_HOME = "research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md (sec.3, the P-B2 row)"

# ── FROZEN CONSTANTS (prereg sec.6, sec.8, sec.9) ─────────────────────────────

SEED = 20260814
N_BOOT_SESSION = 4000
N_BOOT_NAME = 2000
N_BOOT_ROW = 2000
N_PERM = 2000
BLOCK_LEN = 21
THIN_STEP = 10
LEAD_CURVE_B = 1000

H_PRIMARY, H_SECONDARY = 10, 5
HORIZONS = (H_PRIMARY, H_SECONDARY)

BOARD_ORDER = ("main", "chinext10", "chinext20", "star")
SPLIT_GROUPS = OrderedDict([("FIT", ("train", "calibration")),
                            ("HOLDOUT", ("test",)),
                            ("AUDIT", ("audit",))])
GATED_SPLITS = ("FIT", "HOLDOUT")

ARMS = ("M0", "M1")
ARM_UNIVERSE = {"M0": "U0", "M1": "U1"}
ARM_FACTORS = {"M0": ("session", "vol"),
               "M1": ("session", "vol", "dd_band", "dur_band")}

# Measurability masks (prereg sec.4) — unmeasurable is NEVER folded into F=FALSE.
MASK_U = "u_eligibility"            # dd250 finite — already U-eligibility
MASK_MA = "ma200_finite"
MASK_SECT = "sector_known"
MASK_RV = "rv_rank_finite"
MASK_VOLZ = "volz_measurable"
MASK_ALL = "all_u_rows"             # declared approximation, prereg sec.4

MEASURABILITY = OrderedDict([
    ("dd_le_m20", MASK_U), ("dd_le_m35", MASK_U),
    ("under_ma200", MASK_MA),
    ("confluence_long", MASK_ALL), ("cb_recent", MASK_ALL),
    ("sector_deep35_ge40", MASK_SECT),
    ("quiet_base", MASK_RV),
    ("volz_gt1", MASK_VOLZ),
])

# Carve-out map (prereg sec.5.3) — FACTORS DROPPED from the arm's stratum design.
CARVEOUT = OrderedDict([
    ("dd_le_m20", {"M0": (), "M1": ("dd_band", "dur_band")}),
    ("dd_le_m35", {"M0": (), "M1": ("dd_band", "dur_band")}),
    ("under_ma200", {"M0": (), "M1": ()}),
    ("confluence_long", {"M0": (), "M1": ()}),
    ("cb_recent", {"M0": (), "M1": ()}),
    ("sector_deep35_ge40", {"M0": (), "M1": ()}),
    ("quiet_base", {"M0": ("vol",), "M1": ("vol",)}),
    ("volz_gt1", {"M0": (), "M1": ()}),
])

# Verdict arm per footprint (prereg sec.5.5). M0 is reported beside every M1 verdict.
VERDICT_ARM = OrderedDict([
    ("dd_le_m20", "M0"), ("dd_le_m35", "M1"), ("under_ma200", "M1"),
    ("confluence_long", "M1"), ("cb_recent", "M1"), ("sector_deep35_ge40", "M1"),
    ("quiet_base", "M1"), ("volz_gt1", "M1"),
])

# Coincident-indicator stamps (prereg sec.4) — these two are NEVER called precursors.
COINCIDENT_STAMP = {
    "volz_gt1": ("COINCIDENT INDICATOR — median arming lead 1 session (P-B sec.5). This "
                 "is a same-bar volume surprise, not an early precursor, and is never "
                 "described as one."),
    "cb_recent": ("NEAR-COINCIDENT INDICATOR — median arming lead 5 sessions (P-B sec.5). "
                  "Never described as a precursor."),
}

# The four frozen banded gradients (prereg sec.4), SECONDARY descriptive families, NO
# verdicts. `drop` follows the sec.5.3 ONE-SERIES rule: dd250 and dd_dur descend from the
# same rolling 250-session high, so a gradient in that family drops BOTH M1 dd factors.
GRADIENTS = OrderedDict([
    ("below_band", {"bands": ("b0_above", "b1_1_20", "b2_21_60", "b3_61_120", "b4_gt120"),
                    "mask": MASK_MA, "drop": {"M0": (), "M1": ()},
                    "what": "consecutive sessions below the 200DMA"}),
    ("dur_band", {"bands": ("t0_le20", "t1_20_60", "t2_60_120", "t3_gt120"),
                  "mask": MASK_U, "drop": {"M0": (), "M1": ("dd_band", "dur_band")},
                  "what": "sessions since the last new 250-session high (DD/duration "
                          "family — sec.5.3 ONE-SERIES carve-out)"}),
    ("sect35_band", {"bands": ("s0_le20", "s1_20_40", "s2_40_60", "s3_gt60"),
                     "mask": MASK_SECT, "drop": {"M0": (), "M1": ()},
                     "what": "share of sector members 35%+ off their own highs, "
                             "leave-one-out"}),
    ("volz_band", {"bands": ("v0_le0", "v1_0_1", "v2_1_2", "v3_gt2"),
                   "mask": MASK_VOLZ, "drop": {"M0": (), "M1": ()},
                   "what": "volume z-score band of the bar"}),
])
# The sec.5.3-named DEPTH gradient. sec.4 froze the REPORTED gradient list at the four
# above, so this one is emitted to the JSON only and appears in no MD verdict or gradient
# table. See READING_NOTES[0].
DEPTH_GRADIENT = ("dd_band", ("d3_le_m50", "d2_m35_m50", "d1_m20_m35", "d0_gt_m20"),
                  MASK_U, {"M0": (), "M1": ("dd_band", "dur_band")})

# ── gates and floors (prereg sec.8) ───────────────────────────────────────────

G1_BOARD_FIT_EPISODES = 200
G1_BOARD_HOLDOUT_EPISODES = 60
G1_FP_FIT_EPISODES = 50
G1_FP_MIN_ROWS_PER_CLASS = 30
G1_RETENTION_MIN = 0.50
G1_PREVALENCE_LO, G1_PREVALENCE_HI = 0.005, 0.995
G1_ERA_EPISODES = 50
G2_Z = 2.81
G4_FRACTION = 2.0 / 3.0
G5_Z = 1.28
CONCENTRATION_CAP = 0.40
BAND_LOCAL_SHARE = 0.80
LIFT_EXP_FLOOR = 0.005              # exp < 0.5% absolute -> lift suppressed
PLACEBO_NOMINAL = 0.005             # the G2 bar's two-sided nominal size
PLACEBO_FAIL_MULT = 5.0             # > 5x nominal (2.5%) fails calibration

# ── lead-curve battery (prereg sec.9) ─────────────────────────────────────────

LEAD_GRID = (1, 2, 3, 5, 7, 10, 15, 20, 30, 40, 60)
NARRATIVE_WINDOWS = OrderedDict([("ignition", (1, 5)), ("approach", (6, 20)),
                                 ("structural", (21, 60))])
CONTROL_FORWARD = 60                # sessions of verified-quiet forward chain
CONSTANT_COHORT_FOOTPRINTS = ("under_ma200", "confluence_long", "cb_recent",
                              "sector_deep35_ge40", "quiet_base", "volz_gt1")

# ── placebo-feature calibration (prereg sec.6.3) ──────────────────────────────

PLACEBO_SHIFTS = (250, 500, 1000)

# ── pins ──────────────────────────────────────────────────────────────────────

PIN_SYMBOLS_W1 = OrderedDict([
    ("LIMIT_CLOSE_TOL", (353, "LIMIT_CLOSE_TOL")),
    ("MAX_STEP_GAP_DAYS", (354, "MAX_STEP_GAP_DAYS")),
    ("COLD_LOOKBACK_K", (357, "COLD_LOOKBACK_K")),
    ("HORIZONS", (358, "HORIZONS")),
    ("EMBARGO_SESSIONS", (362, "EMBARGO_SESSIONS")),
    ("DD_LOOKBACK/DD_MINP", (371, "DD_LOOKBACK")),
    ("MA_LEN/MA_MINP", (372, "MA_LEN")),
    ("RV_LEN/RV_RANK_LOOKBACK", (373, "RV_LEN")),
    ("SPLITS", (378, "SPLITS")),
    ("ERA_BOUNDS", (387, "ERA_BOUNDS")),
    ("SURVIVORSHIP_STAMP", (401, "SURVIVORSHIP_STAMP")),
    ("streak_lengths", (535, "def streak_lengths")),
    ("era_of", (584, "def era_of")),
    ("process_ticker", (947, "def process_ticker")),
    ("tolerant_detector", (986, "LIMIT_CLOSE_TOL")),
    ("cold_rule", (990, "cold = live")),
    ("win_ok_H", (1045, "win_ok_")),
    ("fb_H", (1046, "fb_")),
    ("build_panel", (1088, "def build_panel")),
    ("assign_splits", (1135, "def assign_splits")),
    ("_band", (1154, "def _band")),
    ("attach_conditioners", (1173, "def attach_conditioners")),
    ("dd_band", (1209, "dd_band")),
    ("dur_band", (1211, "dur_band")),
    ("below_band", (1214, "below_band")),
    ("sect35_band", (1217, "sect35_band")),
    ("volz_band", (1219, "volz_band")),
    ("base_flag", (1221, "base_flag")),
    ("volatility_matched", (1386, "def volatility_matched")),
    ("import_safe_guard", (2285, '__name__ == "__main__"')),
])

PIN_SYMBOLS_PB = OrderedDict([
    ("FOOTPRINTS", (257, "FOOTPRINTS")),
    ("BAND_COLS", (280, "BAND_COLS")),
    ("WITHDRAWN_TOKENS", (294, "WITHDRAWN_TOKENS")),
    ("stop_ship_scan", (332, "def stop_ship_scan")),
    ("_r", (362, "def _r")),
    ("_git", (371, "def _git")),
    ("jsonable", (380, "def jsonable")),
    ("build_footprint_panel", (401, "def build_footprint_panel")),
    ("derive_footprints", (414, "def derive_footprints")),
    ("extract_events", (436, "def extract_events")),
    ("_probe", (846, "def _probe")),
    ("md_table", (1500, "def md_table")),
    ("import_safe_guard", (2089, '__name__ == "__main__"')),
])


def _load_module(path: Path, alias: str, what: str):
    """Import a pinned module BY PATH. Returns (module, sha256)."""
    if not path.exists():
        raise SystemExit(
            f"MISSING PIN SOURCE: {path}\nP-B2 imports {what} and re-derives none of it. "
            "Run this on a checkout where that file is tracked.")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod, sha


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_seq(*parts) -> np.random.SeedSequence:
    """A deterministic, ORDER-INDEPENDENT stream identity.

    The spawn key is the sha256 of the stream's own name, so a stream depends on WHAT is
    computed and never on the order cells are visited in. Reordering or skipping a cell
    cannot move another cell's numbers, which is a stronger determinism guarantee than a
    positional spawn order.
    """
    key = "|".join(str(p) for p in parts).encode()
    d = hashlib.sha256(key).digest()
    return np.random.SeedSequence(entropy=SEED,
                                  spawn_key=tuple(int.from_bytes(d[i:i + 4], "big")
                                                  for i in range(0, 16, 4)))


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 1 — the plane: W-P0's panel through P-B's own footprint derivation
# ══════════════════════════════════════════════════════════════════════════════

DD_BAND_ORDER = ("d3_le_m50", "d2_m35_m50", "d1_m20_m35", "d0_gt_m20", "na")
DUR_BAND_ORDER = ("t0_le20", "t1_20_60", "t2_60_120", "t3_gt120", "na")
BIG = int(np.iinfo(np.int32).max)


class Plane:
    """Every per-row array the batteries consume, built ONCE from the panel.

    Nothing here re-derives a W-P0 or P-B definition: the columns are read, and the only
    NEW quantities are (a) the panel-axis next-board distance used by the label-identity
    check and the quiet-control rule, (b) the panel-axis forward-chain length used by the
    same rule, (c) the measurability masks, and (d) integer stratum factor codes.
    """

    def __init__(self, panel: pd.DataFrame, w1, pb):
        panel = panel.sort_values(["ticker", "date"], kind="mergesort").reset_index(
            drop=True)
        self.panel = panel
        self.n = int(len(panel))
        self.date = panel["date"].to_numpy()
        self.board = panel["board_key"].to_numpy()
        self.split = panel["split"].to_numpy()
        self.era = panel["era"].astype(str).to_numpy()
        self.lu = panel["lu"].to_numpy(bool)

        self.tcode, self.tuniq = pd.factorize(panel["ticker"].to_numpy(), sort=True)
        self.dcode, self.duniq = pd.factorize(self.date, sort=True)

        # per-name contiguous groups (the panel is ticker-major, date-sorted)
        starts = np.r_[0, np.flatnonzero(np.diff(self.tcode) != 0) + 1, self.n]
        self.grp_starts, self.grp_ends = starts[:-1], starts[1:]
        glen = np.diff(starts)
        self.pos_in_name = np.arange(self.n) - np.repeat(self.grp_starts, glen)
        self.fwd_avail = np.repeat(glen, glen) - self.pos_in_name - 1

        # (a) panel-axis distance to the next tolerant board, and its ROW (episode key)
        dist = np.full(self.n, BIG, np.int64)
        nxt = np.full(self.n, -1, np.int64)
        for a, b in zip(self.grp_starts, self.grp_ends):
            p = np.flatnonzero(self.lu[a:b])
            if not p.size:
                continue
            idx = np.arange(b - a)
            j = np.searchsorted(p, idx, side="right")
            ok = j < p.size
            hit = p[np.clip(j, 0, p.size - 1)]
            dist[a:b] = np.where(ok, hit - idx, BIG)
            nxt[a:b] = np.where(ok, a + hit, -1)
        self.dist_next = dist
        self.episode_row = nxt

        # (b) panel-axis forward chain length under W-P0's own MAX_STEP_GAP_DAYS rule.
        # Panel bars are all LIVE by construction, so a forward step is exactly "the next
        # panel bar is within the closure-tolerant gap".
        days = self.date.astype("datetime64[D]").astype(np.int64)
        step = np.zeros(self.n, bool)
        gaps = np.r_[np.diff(days), BIG]
        step[:-1] = gaps[:-1] <= int(w1.MAX_STEP_GAP_DAYS)
        last = np.zeros(self.n, bool)
        last[self.grp_ends - 1] = True
        step[last] = False
        self.fwd_run = w1.streak_lengths(step[::-1])[::-1].astype(np.int64)

        # (c) measurability masks
        dd = panel["dd250"].to_numpy(np.float64)
        rv = panel["rv_rank"].to_numpy(np.float64)
        self.dd = dd
        self.masks = {
            MASK_U: np.isfinite(dd),
            MASK_MA: np.isfinite(dd),          # see MA200_COVERING_LEMMA / verify sec.11
            MASK_SECT: (panel["sector"].to_numpy() != "UNKNOWN")
            & (panel["sect35_band"].to_numpy() != "na"),
            MASK_RV: np.isfinite(rv),
            MASK_VOLZ: (panel["volz_band"].to_numpy() != "na"),
            MASK_ALL: np.ones(self.n, bool),
        }

        # (d) stratum factor codes, packed so the session is always the leading factor
        dec = np.full(self.n, 10, np.int64)
        fin = np.isfinite(rv)
        dec[fin] = np.minimum((rv[fin] * 10).astype(np.int64), 9)
        self.dec = dec
        dbmap = {b: i for i, b in enumerate(DD_BAND_ORDER)}
        tbmap = {b: i for i, b in enumerate(DUR_BAND_ORDER)}
        self.db = np.array([dbmap[str(x)] for x in panel["dd_band"].to_numpy()], np.int64)
        self.tb = np.array([tbmap[str(x)] for x in panel["dur_band"].to_numpy()], np.int64)

        # universes
        assigned = pd.notna(panel["split"]).to_numpy()
        self.U0 = panel["cold"].to_numpy(bool) & assigned & np.isfinite(dd)
        self.U1 = self.U0 & (dd <= -0.20)
        self.universe = {"U0": self.U0, "U1": self.U1}
        self.excluded_no_split = int((panel["cold"].to_numpy(bool) & ~assigned).sum())
        self.excluded_dd_na = int((panel["cold"].to_numpy(bool) & assigned
                                   & ~np.isfinite(dd)).sum())

        # labels
        self.fb = {H: panel[f"fb_{H}"].to_numpy(bool) for H in HORIZONS}
        self.win_ok = {H: panel[f"win_ok_{H}"].to_numpy(bool) for H in HORIZONS}

        # footprint columns and gradient band columns
        self.F = {k: panel[k].to_numpy(bool) for k in pb.FKEYS}
        self.bandcol = {g: panel[g].astype(str).to_numpy() for g in GRADIENTS}
        self.bandcol[DEPTH_GRADIENT[0]] = panel[DEPTH_GRADIENT[0]].astype(str).to_numpy()

        self.split_group = np.array(
            [next((g for g, ss in SPLIT_GROUPS.items() if s in ss), "")
             for s in self.split], dtype=object)
        # Integer codes for the two keys every cell selection filters on. A string
        # comparison over 4.8M rows costs ~0.5 s, and `cell_rows` is called hundreds of
        # times; on codes it is a cached integer compare.
        bmap = {b: i for i, b in enumerate(BOARD_ORDER)}
        smap = {g: i for i, g in enumerate(SPLIT_GROUPS)}
        self.board_code = np.array([bmap.get(str(b), -1) for b in self.board], np.int8)
        self.split_gcode = np.array([smap.get(str(s), -1) for s in self.split_group],
                                    np.int8)
        self._rows_cache: dict = {}
        self.sector_code, _su = pd.factorize(panel["sector"].to_numpy(), sort=True)
        self.sector_known = (panel["sector"].to_numpy() != "UNKNOWN")

        # era as integer codes: string comparison over millions of rows is the single
        # most expensive thing a per-cell composition table can do
        self.era_code, self.era_labels = pd.factorize(self.era, sort=True)
        self.era_labels = [str(x) for x in self.era_labels]
        self._packed_cache: dict = {}

    # ── stratum packing ───────────────────────────────────────────────────────
    def packed(self, factors) -> np.ndarray:
        """Packed stratum key. The session code is ALWAYS the leading factor, so the
        session of a stratum is recoverable as `key // 704` for every design.

        Cached per factor tuple: there are at most six distinct designs in the whole run
        and each one is an 8-pass sweep over the full panel."""
        key = tuple(sorted(factors))
        hit = self._packed_cache.get(key)
        if hit is not None:
            return hit
        dec = self.dec if "vol" in factors else np.zeros(self.n, np.int64)
        db = self.db if "dd_band" in factors else np.zeros(self.n, np.int64)
        tb = self.tb if "dur_band" in factors else np.zeros(self.n, np.int64)
        out = ((self.dcode.astype(np.int64) * 11 + dec) * 8 + db) * 8 + tb
        self._packed_cache[key] = out
        return out


SESSION_DIVISOR = 11 * 8 * 8        # packed // SESSION_DIVISOR == the session code


def arm_factors(fkey_or_drop, arm: str, drop=None) -> tuple:
    base = ARM_FACTORS[arm]
    dropped = drop if drop is not None else CARVEOUT[fkey_or_drop][arm]
    return tuple(f for f in base if f not in dropped)


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 2 — sufficient statistics and the matched estimator (prereg sec.5)
# ══════════════════════════════════════════════════════════════════════════════


def suff_stats(scodes: np.ndarray, ns: int, F: np.ndarray, y: np.ndarray):
    """Per-stratum (n_F1, k_F1, n_F0, k_F0) — computed ONCE per cell, never per draw."""
    n1 = np.bincount(scodes[F], minlength=ns).astype(np.int64)
    k1 = np.bincount(scodes[F & y], minlength=ns).astype(np.int64)
    n0 = np.bincount(scodes[~F], minlength=ns).astype(np.int64)
    k0 = np.bincount(scodes[~F & y], minlength=ns).astype(np.int64)
    return n1, k1, n0, k0


def point_estimate(n1, k1, n0, k0):
    """ATT-weighted direct standardisation — W-P0's `volatility_matched` shape (L1386),
    extended from state-vs-rest to F=TRUE-vs-F=FALSE inside the same stratum."""
    use = (n1 > 0) & (n0 > 0)
    if not use.any():
        return None
    W = n1[use].astype(np.float64)
    r = k0[use] / n0[use]
    obs = float(k1[use].sum()) / float(W.sum())
    exp = float((W * r).sum() / W.sum())
    return {"use": use, "W": W, "r": r,
            "obs": obs, "exp": exp, "excess_pp": 100.0 * (obs - exp),
            "lift": (obs / exp) if exp >= LIFT_EXP_FLOOR and exp > 0 else None,
            "lift_suppressed_low_exp": bool(exp < LIFT_EXP_FLOOR),
            "n_use_strata": int(use.sum()),
            "n_matched_F1_rows": int(W.sum()),
            "n_matched_F0_rows": int(n0[use].sum())}


# ── inference (prereg sec.6) ──────────────────────────────────────────────────


def se_session_block(n1, k1, n0, k0, use, strat_sessions, stream,
                     draws=N_BOOT_SESSION) -> dict:
    """Session-BLOCK bootstrap, blocks of BLOCK_LEN consecutive sessions, block count
    preserved.  A block weight is CONSTANT across the strata it contains, so the estimator
    aggregates exactly to the block level first — a 4000 x n_strata draw matrix collapses
    to 4000 x n_blocks with no approximation whatsoever."""
    if not use.any():
        return {"se": None, "blocks": 0, "status": "NO_MATCHABLE_STRATUM"}
    sess = strat_sessions[use]
    order = np.unique(sess)
    rank = np.searchsorted(order, sess)
    blk = rank // BLOCK_LEN
    ub, bcode = np.unique(blk, return_inverse=True)
    nb = int(ub.size)
    W = n1[use].astype(np.float64)
    r = k0[use] / n0[use]
    A = np.bincount(bcode, weights=(k1[use] - W * r), minlength=nb)
    B = np.bincount(bcode, weights=W, minlength=nb)
    rng = np.random.default_rng(stream)
    C = rng.multinomial(nb, np.full(nb, 1.0 / nb), size=draws).astype(np.float64)
    num, den = C @ A, C @ B
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.where(den > 0, 100.0 * num / den, np.nan)
    ok = np.isfinite(d)
    return {"se": float(np.std(d[ok], ddof=1)) if ok.sum() > 1 else None,
            "blocks": nb, "sessions": int(order.size), "draws": int(draws),
            "draws_used": int(ok.sum()),
            "ci95": [float(np.percentile(d[ok], 2.5)),
                     float(np.percentile(d[ok], 97.5))] if ok.sum() > 1 else None}


def se_name_cluster(scodes, ns, use, ncodes, nn, F, y, stream, chunk=10000) -> dict:
    """Name-cluster bootstrap: rows weighted by their NAME's bootstrap count, strata
    re-aggregated, `use` recomputed per draw.  Implemented as four sparse (stratum x name)
    incidence matrices times one (name x draw) count matrix, CHUNKED OVER STRATA per
    prereg sec.12 — the dense equivalent at M1's stratum count is a multi-GB allocation."""
    if not use.any():
        return {"se": None, "status": "NO_MATCHABLE_STRATUM"}
    keep = use[scodes]
    sc = scodes[keep]
    compact = np.searchsorted(np.flatnonzero(use), sc)
    nu = int(use.sum())
    nc = ncodes[keep]
    Fk, yk = F[keep], y[keep]

    def _csr(m):
        return sps.csr_matrix((np.ones(int(m.sum()), np.float32),
                               (compact[m], nc[m])), shape=(nu, nn))
    M_n1, M_k1 = _csr(Fk), _csr(Fk & yk)
    M_n0, M_k0 = _csr(~Fk), _csr(~Fk & yk)
    rng = np.random.default_rng(stream)
    C = rng.multinomial(nn, np.full(nn, 1.0 / nn),
                        size=N_BOOT_NAME).T.astype(np.float32)
    num = np.zeros(N_BOOT_NAME, np.float64)
    den = np.zeros(N_BOOT_NAME, np.float64)
    for a in range(0, nu, chunk):
        b = min(a + chunk, nu)
        a1 = M_n1[a:b] @ C
        a0 = M_n0[a:b] @ C
        u = (a1 > 0) & (a0 > 0)
        b1 = M_k1[a:b] @ C
        b0 = M_k0[a:b] @ C
        with np.errstate(invalid="ignore", divide="ignore"):
            rr = np.where(a0 > 0, b0 / np.maximum(a0, 1e-9), 0.0)
        num += np.where(u, b1 - a1 * rr, 0.0).sum(0, dtype=np.float64)
        den += np.where(u, a1, 0.0).sum(0, dtype=np.float64)
    with np.errstate(invalid="ignore", divide="ignore"):
        draws = np.where(den > 0, 100.0 * num / den, np.nan)
    ok = np.isfinite(draws)
    return {"se": float(np.std(draws[ok], ddof=1)) if ok.sum() > 1 else None,
            "names": int(nn), "draws_used": int(ok.sum()),
            "ci95": [float(np.percentile(draws[ok], 2.5)),
                     float(np.percentile(draws[ok], 97.5))] if ok.sum() > 1 else None}


def se_row_closed_form(n1, k1, n0, k0, use) -> dict:
    """Row bootstrap SE — AMENDMENT A1, closed form instead of N_BOOT_ROW simulation.

    On the frozen sufficient-statistic table the fixed-design row bootstrap draws
    k_F1(z) ~ Bin(n_F1(z), p1(z)) and k_F0(z) ~ Bin(n_F0(z), p0(z)) INDEPENDENTLY across
    strata, with n_F1, n_F0 and the `use` set held at the design.  The standardised excess
    is then a linear combination of independent binomials, so its bootstrap variance is
    exact and no draws are needed:

        Var = ( 100 / SUM n1 )^2 * SUM_z [ n1*p1*(1-p1) + (n1/n0)^2 * n0*p0*(1-p0) ]

    `verify.se_row_closed_form_matches_simulation` runs the literal N_BOOT_ROW = 2000
    simulation on sampled cells and reports the agreement.
    """
    if not use.any():
        return {"se": None, "status": "NO_MATCHABLE_STRATUM"}
    a1 = n1[use].astype(np.float64)
    a0 = n0[use].astype(np.float64)
    p1 = k1[use] / a1
    p0 = k0[use] / a0
    var = float((a1 * p1 * (1 - p1) + (a1 / a0) ** 2 * a0 * p0 * (1 - p0)).sum())
    d0 = float(a1.sum())
    return {"se": 100.0 * float(np.sqrt(var)) / d0 if d0 > 0 else None,
            "method": "closed form (amendment A1)"}


def se_row_simulated(n1, k1, n0, k0, use, stream, chunk=200) -> float | None:
    """The literal N_BOOT_ROW-draw fixed-design row bootstrap. Used ONLY by the
    verification check that validates the closed form — never on the hot path."""
    if not use.any():
        return None
    a1 = n1[use].astype(np.int64)
    a0 = n0[use].astype(np.int64)
    p1 = k1[use] / a1
    p0 = k0[use] / a0
    d0 = float(a1.sum())
    rng = np.random.default_rng(stream)
    out = []
    K = int(use.sum())
    for a in range(0, N_BOOT_ROW, chunk):
        d = min(chunk, N_BOOT_ROW - a)
        b1 = rng.binomial(np.broadcast_to(a1, (d, K)), np.broadcast_to(p1, (d, K)))
        b0 = rng.binomial(np.broadcast_to(a0, (d, K)), np.broadcast_to(p0, (d, K)))
        out.append(100.0 * (b1 - (a1 / a0) * b0).sum(1) / d0)
    s = np.concatenate(out)
    return float(np.std(s, ddof=1))


def cgm_two_way(se_sess, se_name, se_row):
    """se_2way = sqrt(se_session^2 + se_name^2 - se_row^2); a non-positive radicand
    degenerates to max(se_session, se_name) and the cell is flagged."""
    if se_sess is None or se_name is None or se_row is None:
        return None, True
    rad = se_sess ** 2 + se_name ** 2 - se_row ** 2
    if rad <= 0:
        return max(se_sess, se_name), True
    return float(np.sqrt(rad)), False


def permutation_diag(n1, k1, n0, k0, use, observed_excess, stream, chunk=200) -> dict:
    """Within-stratum FIXED-MARGIN permutation — DIAGNOSTIC ONLY, stamped anticonservative.

    Its null treats each row as an independent draw while one episode contributes ~10
    positive rows, so it understates the null SD by ~sqrt(10) and NEVER gates.  The FULL
    standardised excess is recomputed per draw: `exp` moves with every draw and is never
    held fixed (`verify.permutation_recomputes_exp`).
    """
    if not use.any():
        return {"status": "NO_MATCHABLE_STRATUM"}
    a1 = n1[use].astype(np.int64)
    a0 = n0[use].astype(np.int64)
    ktot = (k1[use] + k0[use]).astype(np.int64)
    ntot = a1 + a0
    d0 = float(a1.sum())
    rng = np.random.default_rng(stream)
    K = int(use.sum())
    exc, exps = [], []
    for a in range(0, N_PERM, chunk):
        d = min(chunk, N_PERM - a)
        g = np.broadcast_to(ktot, (d, K))
        bd = np.broadcast_to(ntot - ktot, (d, K))
        ns = np.broadcast_to(a1, (d, K))
        b1 = rng.hypergeometric(np.maximum(g, 0), np.maximum(bd, 0), ns)
        b0 = ktot - b1
        e = (a1 * (b0 / a0)).sum(1) / d0
        exc.append(100.0 * (b1.sum(1) / d0 - e))
        exps.append(100.0 * e)
    draws = np.concatenate(exc)
    expd = np.concatenate(exps)
    ge = int((draws >= observed_excess).sum())
    le = int((draws <= observed_excess).sum())
    return {
        "draws": int(draws.size),
        "p_right_tail": (1 + ge) / (1 + N_PERM),
        "p_left_tail": (1 + le) / (1 + N_PERM),
        "p_two_sided_min_tail_x2": min(1.0, 2.0 * min((1 + ge) / (1 + N_PERM),
                                                      (1 + le) / (1 + N_PERM))),
        "null_sd_pp": float(np.std(draws, ddof=1)),
        "exp_leg_sd_pp": float(np.std(expd, ddof=1)),
        "exp_leg_distinct_values": int(np.unique(np.round(expd, 9)).size),
        "stamp": ("ANTICONSERVATIVE AND DIAGNOSTIC ONLY — never gates. One episode "
                  "contributes ~10 positive anchor rows, so a row-exchangeable null "
                  "understates the null SD by roughly sqrt(10)."),
    }


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 3 — the cell: honest-N first, then retention, then inference
# ══════════════════════════════════════════════════════════════════════════════


def honest_n(pl: Plane, rows: np.ndarray, y: np.ndarray) -> dict:
    """rows / episodes / names / sessions. EPISODES AND SESSIONS PRINT FIRST everywhere;
    a row count is never presented as an independent observation."""
    epi = pl.episode_row[rows][y]
    return OrderedDict([
        ("episodes", int(np.unique(epi).size) if epi.size else 0),
        ("sessions", int(np.unique(pl.dcode[rows]).size) if rows.size else 0),
        ("names", int(np.unique(pl.tcode[rows]).size) if rows.size else 0),
        ("rows", int(rows.size)),
        ("positive_rows", int(y.sum())),
    ])


def _composition(codes: np.ndarray, weights: np.ndarray, labels) -> dict:
    tot = float(weights.sum())
    if tot <= 0:
        return {}
    out = {}
    for i, lab in enumerate(labels):
        m = codes == i
        if m.any():
            out[lab] = round(100.0 * float(weights[m].sum()) / tot, 2)
    return out


def build_cell(pl: Plane, fkey: str, fvals: np.ndarray, mask_key: str, factors: tuple,
               rows_all: np.ndarray, H: int, label: str, want_inference: bool,
               want_permutation: bool = False, era_gate: bool = False,
               thin: bool = False) -> dict:
    """One (footprint, board, split, arm, horizon) matched comparison, end to end."""
    y_all = pl.fb[H]
    ok_all = pl.win_ok[H]
    mask = pl.masks[mask_key]

    eligible = rows_all[ok_all[rows_all]]              # censored rows enter NEITHER class
    censored = rows_all[~ok_all[rows_all]]
    rows = eligible[mask[eligible]]                    # measurability — sec.4
    excluded_unmeasurable = int(eligible.size - rows.size)

    F = fvals[rows]
    y = y_all[rows]
    cell = OrderedDict([
        ("cell", label), ("footprint", fkey), ("horizon", H),
        ("stratum_factors", list(factors)),
        ("measurability_mask", mask_key),
        ("honest_n_all", honest_n(pl, rows, y)),
        ("honest_n_F_true", honest_n(pl, rows[F], y[F])),
        ("honest_n_F_false", honest_n(pl, rows[~F], y[~F])),
        ("censored_rows_excluded", int(censored.size)),
        ("censored_rows_F_true", int((fvals[censored] & mask[censored]).sum())),
        ("censored_rows_F_false", int((~fvals[censored] & mask[censored]).sum())),
        ("rows_excluded_unmeasurable", excluded_unmeasurable),
    ])
    if rows.size == 0 or F.all() or (~F).all():
        cell["status"] = "NOT_EVALUABLE"
        cell["not_evaluable_reason"] = (
            "empty cell" if rows.size == 0 else
            ("F is constant-TRUE on this universe — no F=FALSE counterfactual exists"
             if F.all() else "F is constant-FALSE on this universe"))
        return cell

    packed = pl.packed(factors)[rows]
    scodes, uniq = pd.factorize(packed, sort=True)
    ns = int(uniq.size)
    strat_sessions = (uniq // SESSION_DIVISOR).astype(np.int64)
    n1, k1, n0, k0 = suff_stats(scodes, ns, F, y)
    pe = point_estimate(n1, k1, n0, k0)
    if pe is None:
        cell["status"] = "NOT_EVALUABLE"
        cell["not_evaluable_reason"] = "no stratum carries both F-classes"
        cell["strata_total"] = ns
        return cell
    use = pe["use"]

    # ── retention diagnostics and the sec.5.6 refusal ─────────────────────────
    keep_row = use[scodes]
    epi_all = pl.episode_row[rows]
    f1_pos = F & y
    f1_pos_epi = np.unique(epi_all[f1_pos])
    f1_pos_epi_kept = np.unique(epi_all[f1_pos & keep_row])
    ret_epi = (f1_pos_epi_kept.size / f1_pos_epi.size) if f1_pos_epi.size else 0.0
    W_rows = F & keep_row
    dbc, tbc, decc = pl.db[rows], pl.tb[rows], pl.dec[rows]
    era_rows_all = pl.era_code[rows]
    dd_share = _composition(dbc[W_rows], np.ones(int(W_rows.sum())), DD_BAND_ORDER)
    band_local = None
    if dd_share:
        top = max(dd_share, key=dd_share.get)
        if dd_share[top] > 100.0 * BAND_LOCAL_SHARE:
            band_local = top
    cell["retention"] = OrderedDict([
        ("strata_total", ns), ("strata_contrast_bearing", int(use.sum())),
        ("F_true_rows_retained_pct", round(100.0 * float(W_rows.sum())
                                           / max(int(F.sum()), 1), 2)),
        ("F_true_positive_episodes_retained_pct", round(100.0 * ret_epi, 2)),
        ("F_true_positive_episodes_full", int(f1_pos_epi.size)),
        ("F_true_positive_episodes_retained", int(f1_pos_epi_kept.size)),
        ("F_false_rows_retained_pct", round(100.0 * float((~F & keep_row).sum())
                                            / max(int((~F).sum()), 1), 2)),
        ("composition_retained_F_true", {
            "dd_band": dd_share,
            "dur_band": _composition(tbc[W_rows], np.ones(int(W_rows.sum())),
                                     DUR_BAND_ORDER),
            "vol_decile": _composition(decc[W_rows], np.ones(int(W_rows.sum())),
                                       [str(d) for d in range(11)]),
            "era": _composition(era_rows_all[W_rows], np.ones(int(W_rows.sum())),
                                pl.era_labels),
        }),
        ("composition_full_F_true", {
            "dd_band": _composition(dbc[F], np.ones(int(F.sum())), DD_BAND_ORDER),
            "dur_band": _composition(tbc[F], np.ones(int(F.sum())), DUR_BAND_ORDER),
            "vol_decile": _composition(decc[F], np.ones(int(F.sum())),
                                       [str(d) for d in range(11)]),
            "era": _composition(era_rows_all[F], np.ones(int(F.sum())), pl.era_labels),
        }),
        ("band_local_label", band_local),
        ("session_factor_composition_note",
         "the session factor's composition is summarised by ERA share above; a "
         "per-session table over ~3,000 sessions is not a printable diagnostic"),
    ])

    cell["estimate"] = OrderedDict([
        ("observed_F_true_rate_pct", round(100.0 * pe["obs"], 4)),
        ("expected_matched_rate_pct", round(100.0 * pe["exp"], 4)),
        ("matched_excess_pp", round(pe["excess_pp"], 4)),
        ("matched_lift", round(pe["lift"], 4) if pe["lift"] is not None else None),
        ("lift_suppressed_exp_below_0p5pct", pe["lift_suppressed_low_exp"]),
        ("matched_F_true_rows", pe["n_matched_F1_rows"]),
        ("matched_F_false_rows", pe["n_matched_F0_rows"]),
        ("F_prevalence_in_retained_sample", round(
            float(W_rows.sum()) / max(float(keep_row.sum()), 1.0), 6)),
    ])

    # concentration on positive EPISODES (never rows)
    if f1_pos_epi_kept.size:
        ep = epi_all[f1_pos & keep_row]
        nm = pl.tcode[rows][f1_pos & keep_row]
        uniq_ep, first = np.unique(ep, return_index=True)
        cnt = np.bincount(nm[first])
        conc = float(cnt.max()) / float(uniq_ep.size)
    else:
        conc = 0.0
    cell["max_single_name_positive_episode_share"] = round(conc, 4)
    cell["concentrated"] = bool(conc > CONCENTRATION_CAP)

    # ── inference ─────────────────────────────────────────────────────────────
    if want_inference:
        ncodes_full, nn = pd.factorize(pl.tcode[rows], sort=True)
        s1 = se_session_block(n1, k1, n0, k0, use, strat_sessions,
                              _seed_seq("session", label, fkey, H))
        s2 = se_name_cluster(scodes, ns, use, ncodes_full, int(len(nn)), F, y,
                             _seed_seq("name", label, fkey, H))
        s3 = se_row_closed_form(n1, k1, n0, k0, use)
        se2, degen = cgm_two_way(s1["se"], s2["se"], s3["se"])
        z = (pe["excess_pp"] / se2) if (se2 and se2 > 0) else None
        cell["inference"] = OrderedDict([
            ("se_session_block_pp", round(s1["se"], 5) if s1["se"] else None),
            ("se_name_cluster_pp", round(s2["se"], 5) if s2["se"] else None),
            ("se_row_pp", round(s3["se"], 5) if s3["se"] else None),
            ("se_2way_cgm_pp", round(se2, 5) if se2 else None),
            ("cgm_degenerate", bool(degen)),
            ("z_2way", round(z, 4) if z is not None else None),
            ("z_form", "normal approximation on the CGM two-way clustered SE — stamped "
                       "as such; sec.6.3 placebo calibration is the empirical guard"),
            ("session_blocks", s1.get("blocks")), ("name_clusters", s2.get("names")),
            ("session_block_ci95_pp", [round(v, 4) for v in s1["ci95"]]
             if s1.get("ci95") else None),
            ("name_cluster_ci95_pp", [round(v, 4) for v in s2["ci95"]]
             if s2.get("ci95") else None),
            ("design_effect_session_over_row",
             round(s1["se"] / s3["se"], 3) if (s1["se"] and s3["se"]) else None),
        ])
        if want_permutation:
            cell["permutation_diagnostic"] = permutation_diag(
                n1, k1, n0, k0, use, pe["excess_pp"], _seed_seq("perm", label, fkey, H))

    # ── thinned-anchor sensitivity (G3) ───────────────────────────────────────
    if thin:
        thin_rows = _thin_rows(pl, rows)
        tf, ty = fvals[thin_rows], y_all[thin_rows]
        tp = pl.packed(factors)[thin_rows]
        tsc, tun = pd.factorize(tp, sort=True)
        tn1, tk1, tn0, tk0 = suff_stats(tsc, int(tun.size), tf, ty)
        tpe = point_estimate(tn1, tk1, tn0, tk0)
        cell["thinned"] = OrderedDict([
            ("thin_step", THIN_STEP),
            ("rows", int(thin_rows.size)),
            ("matched_excess_pp", round(tpe["excess_pp"], 4) if tpe else None),
            ("sign_matches_full", (None if tpe is None else
                                   bool(np.sign(tpe["excess_pp"])
                                        == np.sign(pe["excess_pp"])))),
            ("rule", "every THIN_STEP-th eligible session per name, deterministic phase = "
                     "the name's first eligible row; non-overlapping at H=10 so at most "
                     "one positive row per episode"),
        ])

    # ── era table (G4) ────────────────────────────────────────────────────────
    if era_gate:
        eras = OrderedDict()
        packed_all = pl.packed(factors)
        for ec in np.unique(era_rows_all):
            e = pl.era_labels[int(ec)]
            m = era_rows_all == ec
            epos = np.unique(epi_all[m & y])
            rec = {"positive_episodes": int(epos.size),
                   "measurable": bool(epos.size >= G1_ERA_EPISODES)}
            if rec["measurable"]:
                esc, eun = pd.factorize(packed_all[rows[m]], sort=True)
                a, b, c, d = suff_stats(esc, int(eun.size), F[m], y[m])
                epe = point_estimate(a, b, c, d)
                rec["matched_excess_pp"] = round(epe["excess_pp"], 4) if epe else None
                rec["sign_matches_full"] = (
                    None if epe is None else
                    bool(np.sign(epe["excess_pp"]) == np.sign(pe["excess_pp"])))
            eras[e] = rec
        meas = [v for v in eras.values() if v["measurable"]]
        agree = [v for v in meas if v.get("sign_matches_full")]
        cell["eras"] = OrderedDict([
            ("per_era", eras),
            ("measurable_eras", len(meas)),
            ("eras_agreeing_in_sign", len(agree)),
            ("fraction_agreeing", round(len(agree) / len(meas), 4) if meas else None),
        ])
    return cell


def _thin_rows(pl: Plane, rows: np.ndarray) -> np.ndarray:
    """Every THIN_STEP-th eligible row per name; phase = the name's FIRST eligible row."""
    if rows.size == 0:
        return rows
    order = np.lexsort((rows, pl.tcode[rows]))
    r = rows[order]
    t = pl.tcode[r]
    starts = np.r_[0, np.flatnonzero(np.diff(t) != 0) + 1]
    idx = np.arange(r.size) - np.repeat(starts, np.diff(np.r_[starts, r.size]))
    return np.sort(r[idx % THIN_STEP == 0])


def manski_bounds(pl: Plane, fvals, mask_key, factors, rows_all, H) -> dict:
    """Coarse Manski robustness: recompute the matched excess with ALL censored F=TRUE
    rows counted positive, then all counted negative. Censoring is never scored as a miss
    in the primary estimator; this bounds what it could have been."""
    mask = pl.masks[mask_key]
    ok_all, y_all = pl.win_ok[H], pl.fb[H]
    rows = rows_all[mask[rows_all]]
    F = fvals[rows]
    cens = ~ok_all[rows]
    out = {}
    for name, val in (("censored_F_true_all_positive", True),
                      ("censored_F_true_all_negative", False)):
        keep = (~cens) | (cens & F)
        rr = rows[keep]
        FF = F[keep]
        yy = y_all[rr].copy()
        yy[cens[keep] & FF] = val
        p = pl.packed(factors)[rr]
        sc, un = pd.factorize(p, sort=True)
        a, b, c, d = suff_stats(sc, int(un.size), FF, yy)
        pe = point_estimate(a, b, c, d)
        out[name] = round(pe["excess_pp"], 4) if pe else None
    return out


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 4 — universes, labels, board floors
# ══════════════════════════════════════════════════════════════════════════════


def cell_rows(pl: Plane, universe: str, board: str, split_group: str) -> np.ndarray:
    """Row indices of one (universe, board, split) cell — cached; there are 24 of them and
    they are re-selected hundreds of times across the batteries."""
    key = (universe, board, split_group)
    hit = pl._rows_cache.get(key)
    if hit is not None:
        return hit
    bi = BOARD_ORDER.index(board)
    si = list(SPLIT_GROUPS).index(split_group)
    out = np.flatnonzero(pl.universe[universe] & (pl.board_code == bi)
                         & (pl.split_gcode == si))
    pl._rows_cache[key] = out
    return out


def universe_tables(pl: Plane) -> dict:
    out = OrderedDict()
    for u in ("U0", "U1"):
        for sg in SPLIT_GROUPS:
            for b in BOARD_ORDER:
                r = cell_rows(pl, u, b, sg)
                out[f"{u}|{b}|{sg}"] = OrderedDict([
                    ("sessions", int(np.unique(pl.dcode[r]).size) if r.size else 0),
                    ("names", int(np.unique(pl.tcode[r]).size) if r.size else 0),
                    ("rows", int(r.size)),
                ])
    return out


def label_tables(pl: Plane) -> dict:
    """The exact partition positives / negatives / censored, per H x board x split, plus
    the differential-censoring counts per footprint F-class and the broken-window
    diagnostic (prereg sec.3)."""
    out = OrderedDict()
    for H in HORIZONS:
        y, ok = pl.fb[H], pl.win_ok[H]
        for u in ("U0", "U1"):
            for b in BOARD_ORDER:
                for sg in SPLIT_GROUPS:
                    r = cell_rows(pl, u, b, sg)
                    if not r.size:
                        continue
                    pos = int(y[r].sum())
                    cen = int((~ok[r]).sum())
                    neg = int((ok[r] & ~y[r]).sum())
                    broken = int(((~ok[r]) & (pl.dist_next[r] <= H)).sum())
                    epi = np.unique(pl.episode_row[r][y[r]])
                    rec = OrderedDict([
                        ("positive_episodes", int(epi.size)),
                        ("sessions", int(np.unique(pl.dcode[r]).size)),
                        ("names", int(np.unique(pl.tcode[r]).size)),
                        ("rows_eligible", int(r.size)),
                        ("positives", pos), ("negatives", neg), ("censored", cen),
                        ("partition_exact", bool(pos + neg + cen == r.size)),
                        ("board_visible_inside_broken_window", broken),
                        ("broken_window_pct_of_positives",
                         round(100.0 * broken / max(pos, 1), 3)),
                    ])
                    for fk in FKEYS_ORDER:
                        m = pl.masks[MEASURABILITY[fk]][r]
                        cm = (~ok[r]) & m
                        rec[f"censored_{fk}_F_true"] = int((cm & pl.F[fk][r]).sum())
                        rec[f"censored_{fk}_F_false"] = int((cm & ~pl.F[fk][r]).sum())
                    out[f"H{H}|{u}|{b}|{sg}"] = rec
    return out


def panel_row_lookup(pl: Plane):
    """(ticker, date) -> panel row, on INTEGER keys.

    A pandas MultiIndex over 4.8M (str, Timestamp) tuples costs minutes to build and to
    `.loc` against; the same join on a sorted int64 key is milliseconds. The key packs the
    ticker code and the day ordinal, both small integers.
    """
    day = pl.date.astype("datetime64[D]").astype(np.int64)
    key = pl.tcode.astype(np.int64) * 100000 + day
    order = np.argsort(key, kind="stable")
    return key[order], order, pd.Index(pl.tuniq)


def find_rows(idx, tickers, dates):
    """Panel rows for (ticker, date) pairs; unmatched pairs are dropped and reported."""
    keys, order, tidx = idx
    tc = tidx.get_indexer(np.asarray(tickers))
    day = pd.DatetimeIndex(dates).to_numpy().astype("datetime64[D]").astype(np.int64)
    q = tc.astype(np.int64) * 100000 + day
    pos = np.clip(np.searchsorted(keys, q), 0, max(keys.size - 1, 0))
    ok = (tc >= 0) & (keys.size > 0) & (keys[pos] == q)
    return order[pos][ok], ok


def episode_overlap(pl: Plane, ev: pd.DataFrame) -> dict:
    """prereg sec.3 cross-check — by W-P0's ladder-0 lemma every positive row's realised
    board should also be a cold-eve first board in P-B's own `extract_events` cohort. The
    OVERLAP COUNT is printed rather than asserted: a shortfall is a fact about the two
    constructions, not a licence to quietly reconcile them."""
    er, _ok = find_rows(panel_row_lookup(pl), ev["ticker"].to_numpy(),
                        ev["event_date"].to_numpy())
    pb_events = np.unique(er)
    out = OrderedDict()
    for H in HORIZONS:
        for u in ("U0", "U1"):
            for b in BOARD_ORDER:
                r = cell_rows(pl, u, b, "FIT")
                if not r.size:
                    continue
                epi = np.unique(pl.episode_row[r][pl.fb[H][r]])
                inter = int(np.intersect1d(epi, pb_events).size)
                out[f"H{H}|{u}|{b}|FIT"] = {
                    "positive_episodes": int(epi.size),
                    "also_a_pb_extract_events_first_board": inter,
                    "overlap_pct": round(100.0 * inter / max(int(epi.size), 1), 3)}
    out["_rule"] = ("the cold rule guarantees every positive is a genuine 0->1 ignition "
                    "(W-P0 sec.5 ladder-0 lemma), so a positive row's realised board is a "
                    "cold-eve first board. P-B's cohort additionally requires the eve->"
                    "event pair to sit inside the 21-day closure-tolerant step rule, "
                    "which is why the overlap is reported as a count and not asserted to "
                    "be 100%.")
    return out


def board_floors(pl: Plane) -> dict:
    """G1 board floor, evaluated per horizon x arm-universe (prereg sec.8)."""
    out = OrderedDict()
    for H in HORIZONS:
        for arm in ARMS:
            u = ARM_UNIVERSE[arm]
            for b in BOARD_ORDER:
                ep = {}
                for sg in ("FIT", "HOLDOUT"):
                    r = cell_rows(pl, u, b, sg)
                    ep[sg] = int(np.unique(pl.episode_row[r][pl.fb[H][r]]).size) \
                        if r.size else 0
                ok = (ep["FIT"] >= G1_BOARD_FIT_EPISODES
                      and ep["HOLDOUT"] >= G1_BOARD_HOLDOUT_EPISODES)
                out[f"H{H}|{arm}|{b}"] = OrderedDict([
                    ("fit_positive_episodes", ep["FIT"]),
                    ("holdout_positive_episodes", ep["HOLDOUT"]),
                    ("verdict_eligible", bool(ok)),
                    ("status", "VERDICT_ELIGIBLE" if ok else "DESCRIPTIVE_ONLY"),
                    ("floors", [G1_BOARD_FIT_EPISODES, G1_BOARD_HOLDOUT_EPISODES]),
                ])
    return out


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 5 — the primary battery and the verdict gates (prereg sec.8)
# ══════════════════════════════════════════════════════════════════════════════


def g1_footprint(cell: dict, split_group: str) -> dict:
    """Footprint-evaluable inside a cell. A dead feature prints NOT_EVALUABLE, never
    NULL."""
    if cell.get("status") == "NOT_EVALUABLE":
        return {"passed": False, "reason": cell.get("not_evaluable_reason")}
    est, ret = cell["estimate"], cell["retention"]
    reasons = []
    if split_group == "FIT" and ret["F_true_positive_episodes_retained"] \
            < G1_FP_FIT_EPISODES:
        reasons.append(f"retained F=TRUE positive episodes "
                       f"{ret['F_true_positive_episodes_retained']} < "
                       f"{G1_FP_FIT_EPISODES}")
    if est["matched_F_true_rows"] < G1_FP_MIN_ROWS_PER_CLASS:
        reasons.append(f"retained F=TRUE rows {est['matched_F_true_rows']} < "
                       f"{G1_FP_MIN_ROWS_PER_CLASS}")
    if est["matched_F_false_rows"] < G1_FP_MIN_ROWS_PER_CLASS:
        reasons.append(f"retained F=FALSE rows {est['matched_F_false_rows']} < "
                       f"{G1_FP_MIN_ROWS_PER_CLASS}")
    if ret["F_true_positive_episodes_retained_pct"] < 100.0 * G1_RETENTION_MIN:
        reasons.append(f"retained-episode fraction "
                       f"{ret['F_true_positive_episodes_retained_pct']}% < "
                       f"{100 * G1_RETENTION_MIN}% (sec.5.6 REFUSAL)")
    pv = est["F_prevalence_in_retained_sample"]
    if not (G1_PREVALENCE_LO <= pv <= G1_PREVALENCE_HI):
        reasons.append(f"F prevalence {pv:.5f} outside "
                       f"[{G1_PREVALENCE_LO}, {G1_PREVALENCE_HI}]")
    return {"passed": not reasons, "reason": "; ".join(reasons) if reasons else None}


def norm_sf(z: float) -> float:
    """Upper-tail normal survival — the stamped approximation the gates are read under."""
    from math import erfc, sqrt
    return 0.5 * erfc(z / sqrt(2.0))


def verdict_for(fit: dict, hold: dict, board_ok: bool, placebo_failed: bool) -> dict:
    g = OrderedDict()
    if not board_ok:
        return {"verdict": "DESCRIPTIVE_ONLY", "gates": {"G1_board": False},
                "why": "board floor not met (prereg sec.8) — no footprint on this board "
                       "receives a gated verdict"}
    f1 = g1_footprint(fit, "FIT")
    g["G1_board"] = True
    g["G1_footprint"] = f1["passed"]
    if not f1["passed"]:
        return {"verdict": "NOT_EVALUABLE", "gates": dict(g), "why": f1["reason"]}
    z = fit.get("inference", {}).get("z_2way")
    exc = fit["estimate"]["matched_excess_pp"]
    g["G2_fit_z_ge_2.81"] = bool(z is not None and abs(z) >= G2_Z)
    g["G3_thinned_sign"] = bool(fit.get("thinned", {}).get("sign_matches_full"))
    frac = fit.get("eras", {}).get("fraction_agreeing")
    g["G4_era_sign_2of3"] = bool(frac is not None and frac >= G4_FRACTION)
    hz = hold.get("inference", {}).get("z_2way") if hold else None
    hex_ = hold.get("estimate", {}).get("matched_excess_pp") if hold else None
    g5 = False
    if hz is not None and hex_ is not None and np.sign(hex_) == np.sign(exc):
        g5 = bool((hz if exc > 0 else -hz) >= G5_Z)
    g["G5_holdout"] = g5
    strong = bool(z is not None and abs(z) >= 1.96)
    if all(g.values()):
        v = "DISCRIMINATOR"
    elif strong:
        v = "SUGGESTIVE"
    else:
        v = "NULL"
    caps = []
    if v == "DISCRIMINATOR" and fit.get("concentrated"):
        v, _ = "SUGGESTIVE", caps.append("CONCENTRATED (>40% of F=TRUE positive episodes "
                                         "from one name) — capped at SUGGESTIVE")
    if v == "DISCRIMINATOR" and placebo_failed:
        v, _ = "SUGGESTIVE", caps.append("the (board, horizon) family FAILED its sec.6.3 "
                                         "placebo calibration — no DISCRIMINATOR may "
                                         "stand in it")
    p_nominal = 2.0 * norm_sf(abs(z)) if z is not None else None
    return {"verdict": v, "gates": dict(g), "caps": caps,
            "fit_z_2way": z, "fit_excess_pp": exc,
            "holdout_z_2way": hz, "holdout_excess_pp": hex_,
            "p_two_sided_normal": p_nominal,
            "band_local": fit["retention"]["band_local_label"],
            "concentrated": fit.get("concentrated")}


def holm(pvals: dict) -> dict:
    """Holm-adjusted p inside a (board, horizon) family — a REFERENCE column that changes
    no gate (prereg sec.8)."""
    items = [(k, v) for k, v in pvals.items() if v is not None]
    items.sort(key=lambda kv: kv[1])
    m = len(items)
    out, running = {}, 0.0
    for i, (k, p) in enumerate(items):
        adj = min(1.0, max(running, (m - i) * p))
        running = adj
        out[k] = round(adj, 6)
    for k, v in pvals.items():
        out.setdefault(k, None)
    return out


def run_primary(pl: Plane, floors: dict, fvals_override=None, tag="primary",
                splits=GATED_SPLITS, want_inference=True, boards=None,
                progress=None) -> dict:
    """The primary battery: every footprint x board x split x arm x horizon."""
    res = OrderedDict()
    fvals_override = fvals_override or {}
    for H in HORIZONS:
        for arm in ARMS:
            u = ARM_UNIVERSE[arm]
            for b in (boards or BOARD_ORDER):
                board_ok = floors[f"H{H}|{arm}|{b}"]["verdict_eligible"]
                for sg in splits:
                    rows = cell_rows(pl, u, b, sg)
                    if not rows.size:
                        continue
                    for fk in FKEYS_ORDER:
                        fac = arm_factors(fk, arm)
                        lab = f"{tag}|H{H}|{arm}|{b}|{sg}"
                        infer = want_inference and board_ok and sg in GATED_SPLITS
                        cell = build_cell(
                            pl, fk, fvals_override.get(fk, pl.F[fk]),
                            MEASURABILITY[fk], fac, rows, H, lab,
                            want_inference=infer,
                            want_permutation=(infer and sg == "FIT"
                                              and H == H_PRIMARY and tag == "primary"),
                            era_gate=(sg == "FIT" and board_ok),
                            thin=(sg == "FIT" and board_ok))
                        cell["board"] = b
                        cell["split"] = sg
                        cell["arm"] = arm
                        cell["board_verdict_eligible"] = board_ok
                        res[f"H{H}|{arm}|{b}|{sg}|{fk}"] = cell
                        if progress:
                            progress()
    return res


def vz_no_vol_sensitivity(pl: Plane, floors: dict, boards) -> dict:
    """prereg sec.5.3 — VZ KEEPS the vol-decile stratum (realised return-vol and volume
    surprise are distinct series), and a no-vol-stratum sensitivity is printed beside it."""
    out = OrderedDict()
    fk = "volz_gt1"
    for H in HORIZONS:
        for b in boards:
            if not floors[f"H{H}|M1|{b}"]["verdict_eligible"]:
                continue
            for sg in GATED_SPLITS:
                rows = cell_rows(pl, "U1", b, sg)
                if not rows.size:
                    continue
                c = build_cell(pl, fk, pl.F[fk], MEASURABILITY[fk],
                               arm_factors(None, "M1", ("vol",)), rows, H,
                               f"vz_no_vol|H{H}|M1|{b}|{sg}", want_inference=True)
                base = f"H{H}|M1|{b}|{sg}|{fk}"
                c["board"], c["split"] = b, sg
                c["compare_to_primary_cell"] = base
                out[f"H{H}|{b}|{sg}"] = c
    out["_why"] = ("printed beside VZ's primary verdict so the reader can see what the "
                   "vol stratum is doing to it; the VERDICT stays on the vol-stratified "
                   "arm, which is the frozen sec.5.3 choice")
    return out


def shift_footprints(pl: Plane, shift: int) -> tuple[dict, dict]:
    """PLACEBO (prereg sec.6.3): move each name's footprint tape FORWARD by `shift`
    sessions on its own axis. Within-name persistence, cross-sectional prevalence and
    session structure survive; only the alignment with outcomes is broken. Rows whose
    shifted source falls before the name's first bar carry no footprint value and are
    EXCLUDED AND COUNTED (they are removed from every F-class by a shifted mask)."""
    src = np.arange(pl.n) - shift
    valid = np.zeros(pl.n, bool)
    for a, b in zip(pl.grp_starts, pl.grp_ends):
        valid[a + shift:b] = True
    src = np.clip(src, 0, pl.n - 1)
    out, masks = {}, {}
    for fk in FKEYS_ORDER:
        out[fk] = pl.F[fk][src] & valid
        masks[fk] = pl.masks[MEASURABILITY[fk]][src] & valid
    return out, masks


def _pmask(fk: str) -> str:
    """Mask key for a placebo-shifted footprint — a shifted footprint carries its own
    shifted measurability, and the key says so in the receipt."""
    return f"shifted_measurability::{fk}::{MEASURABILITY[fk]}"


def run_placebo(pl: Plane, floors: dict, boards, progress=None) -> dict:
    """Measured false-positive guard: the FULL primary battery per shift, FIT only (the
    G2 bar is a FIT gate), and the realised rejection rate at that bar."""
    per_shift = OrderedDict()
    for s in PLACEBO_SHIFTS:
        fv, fm = shift_footprints(pl, s)
        saved = {k: pl.masks[k] for k in pl.masks}
        try:
            # a shifted footprint carries its own shifted measurability
            for fk in FKEYS_ORDER:
                pl.masks[_pmask(fk)] = fm[fk]
            cells = OrderedDict()
            for H in HORIZONS:
                for arm in ARMS:
                    u = ARM_UNIVERSE[arm]
                    for b in boards:
                        if not floors[f"H{H}|{arm}|{b}"]["verdict_eligible"]:
                            continue
                        rows = cell_rows(pl, u, b, "FIT")
                        for fk in FKEYS_ORDER:
                            c = build_cell(pl, fk, fv[fk], _pmask(fk),
                                           arm_factors(fk, arm), rows, H,
                                           f"placebo{s}|H{H}|{arm}|{b}|FIT",
                                           want_inference=True)
                            c.update({"board": b, "arm": arm, "shift": s})
                            cells[f"H{H}|{arm}|{b}|{fk}"] = c
                            if progress:
                                progress()
        finally:
            for fk in FKEYS_ORDER:
                pl.masks.pop(_pmask(fk), None)
            pl.masks.update(saved)
        per_shift[str(s)] = cells

    fam = OrderedDict()
    for s, cells in per_shift.items():
        for key, c in cells.items():
            H, arm, b, fk = key.split("|")
            f = f"{b}|{H}"
            d = fam.setdefault(f, {"tested": 0, "rejected": 0, "not_evaluable": 0,
                                   "rejections": []})
            z = c.get("inference", {}).get("z_2way")
            if z is None:
                d["not_evaluable"] += 1
                continue
            d["tested"] += 1
            if abs(z) >= G2_Z:
                d["rejected"] += 1
                d["rejections"].append(f"shift{s}|{arm}|{fk}|z={round(z, 2)}")
    for f, d in fam.items():
        rate = d["rejected"] / d["tested"] if d["tested"] else None
        d["rejection_rate"] = round(rate, 5) if rate is not None else None
        d["nominal"] = PLACEBO_NOMINAL
        d["bar"] = PLACEBO_FAIL_MULT * PLACEBO_NOMINAL
        d["calibration_failed"] = bool(rate is not None
                                       and rate > PLACEBO_FAIL_MULT * PLACEBO_NOMINAL)
    return {"per_shift": per_shift, "family_calibration": fam,
            "shifts": list(PLACEBO_SHIFTS),
            "consequence": ("a (board, horizon) family whose realised rejection rate at "
                            "the G2 bar exceeds 5x nominal (> 2.5%) has NO DISCRIMINATOR: "
                            "every one downgrades to SUGGESTIVE and the receipt states "
                            "that the inference machinery failed its own calibration")}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 6 — secondary descriptive families, S-arm, lead curves, flagged sets
# ══════════════════════════════════════════════════════════════════════════════


def run_gradients(pl: Plane, floors: dict, boards, spec=None, tag="gradients") -> dict:
    """The frozen banded gradients — SECONDARY, DESCRIPTIVE, NO VERDICTS. Point estimate
    plus a session-block CI only: nothing here is gated, so the name/row bootstraps that
    exist to build a gate are not spent on it."""
    out = OrderedDict()
    spec = spec or GRADIENTS
    for gname, g in spec.items():
        col = pl.bandcol[gname]
        for band in g["bands"]:
            fv = col == band
            for H in HORIZONS:
                for arm in ARMS:
                    u = ARM_UNIVERSE[arm]
                    for b in boards:
                        for sg in GATED_SPLITS:
                            rows = cell_rows(pl, u, b, sg)
                            if not rows.size:
                                continue
                            c = build_cell(pl, f"{gname}={band}", fv, g["mask"],
                                           arm_factors(None, arm, g["drop"][arm]),
                                           rows, H, f"{tag}|H{H}|{arm}|{b}|{sg}",
                                           want_inference=False)
                            if c.get("status") != "NOT_EVALUABLE":
                                pk = pl.packed(arm_factors(None, arm, g["drop"][arm]))
                                mrows = rows[pl.masks[g["mask"]][rows]
                                             & pl.win_ok[H][rows]]
                                sc, un = pd.factorize(pk[mrows], sort=True)
                                n1, k1, n0, k0 = suff_stats(sc, int(un.size),
                                                            fv[mrows], pl.fb[H][mrows])
                                pe = point_estimate(n1, k1, n0, k0)
                                s1 = se_session_block(
                                    n1, k1, n0, k0, pe["use"],
                                    (un // SESSION_DIVISOR).astype(np.int64),
                                    _seed_seq("grad", gname, band, H, arm, b, sg))
                                c["session_block_ci95_pp"] = (
                                    [round(v, 4) for v in s1["ci95"]]
                                    if s1.get("ci95") else None)
                            c.update({"family": gname, "band": band, "board": b,
                                      "split": sg, "arm": arm, "verdict": "DESCRIPTIVE"})
                            out[f"{gname}|{band}|H{H}|{arm}|{b}|{sg}"] = c
    return out


def run_s_arm(pl: Plane, boards) -> dict:
    """sec.5.4 — M1 strata x SECTOR, non-SECT-family footprints only, FIT only,
    SENSITIVITY TABLE ONLY. Never citable for SECT's own incremental value; thin cells
    refuse."""
    out = OrderedDict()
    sect_codes = pl.sector_code
    for H in HORIZONS:
        for b in boards:
            rows = cell_rows(pl, "U1", b, "FIT")
            if not rows.size:
                continue
            for fk in FKEYS_ORDER:
                if fk == "sector_deep35_ge40":
                    continue
                fac = arm_factors(fk, "M1")
                packed = pl.packed(fac).astype(np.int64) * 64 + sect_codes
                mask = pl.masks[MEASURABILITY[fk]]
                r = rows[mask[rows] & pl.win_ok[H][rows] & pl.sector_known[rows]]
                if r.size < 2 * G1_FP_MIN_ROWS_PER_CLASS:
                    out[f"H{H}|{b}|{fk}"] = {"status": "REFUSED_THIN_CELL",
                                             "rows": int(r.size)}
                    continue
                sc, un = pd.factorize(packed[r], sort=True)
                n1, k1, n0, k0 = suff_stats(sc, int(un.size), pl.F[fk][r], pl.fb[H][r])
                pe = point_estimate(n1, k1, n0, k0)
                if pe is None:
                    out[f"H{H}|{b}|{fk}"] = {"status": "NOT_EVALUABLE",
                                             "reason": "no stratum carries both classes"}
                    continue
                epi = np.unique(pl.episode_row[r][pl.F[fk][r] & pl.fb[H][r]
                                                  & pe["use"][sc]])
                out[f"H{H}|{b}|{fk}"] = OrderedDict([
                    ("retained_F_true_positive_episodes", int(epi.size)),
                    ("matched_F_true_rows", pe["n_matched_F1_rows"]),
                    ("matched_excess_pp", round(pe["excess_pp"], 4)),
                    ("status", "SENSITIVITY_ONLY"),
                ])
    return out


def quiet_controls(pl: Plane) -> tuple[np.ndarray, dict]:
    """sec.9 quiet-control rows: same-session U1 rows with a COMPLETE 60-session forward
    chain (60 consecutive forward panel steps each inside MAX_STEP_GAP_DAYS) and no
    tolerant board inside those 60 sessions.

    A row whose remaining tape cannot PROVE 60 quiet sessions is EXCLUDED AND COUNTED. The
    next-board-distance sentinel would otherwise admit every end-of-data row as "verified
    quiet" — right-truncation that enriches the control arm with exactly the names whose
    future is unobserved.
    """
    complete = pl.fwd_run >= CONTROL_FORWARD
    quiet = pl.dist_next > CONTROL_FORWARD
    admitted = pl.U1 & complete & quiet
    meta = {
        "u1_rows": int(pl.U1.sum()),
        "excluded_incomplete_forward_chain": int((pl.U1 & ~complete).sum()),
        "excluded_board_inside_60": int((pl.U1 & complete & ~quiet).sum()),
        "admitted": int(admitted.sum()),
        "forward_sessions_required": CONTROL_FORWARD,
        "step_gap_days": 21,
        "note": ("case anchors at every grid lead are automatically outside this pool: a "
                 "case anchor at lead l <= 60 has a board within 60 sessions, so the "
                 "quiet rule ejects it by construction — no extra exclusion rule is "
                 "needed and none is applied"),
    }
    return admitted, meta


def run_lead_curves(pl: Plane, ev: pd.DataFrame, controls: np.ndarray, boards) -> dict:
    """sec.9 two-speed battery — DESCRIPTIVE, gates nothing, no permutation p anywhere."""
    coh = ev[ev["in_cohort"].to_numpy()]
    ev_rows, _ok = find_rows(panel_row_lookup(pl), coh["ticker"].to_numpy(),
                             coh["event_date"].to_numpy())

    ctrl_rows = np.flatnonzero(controls)
    curves, eligibility = OrderedDict(), OrderedDict()
    anchors_by_lead = {}
    # A4 — the per-lead masks are kept so the SAME accounting can be re-scoped to each
    # (board, split) cohort below. The global series is still emitted, unchanged.
    inside_by_lead, keep_by_lead = {}, {}
    for L in LEAD_GRID:
        a = ev_rows - L
        same_name = pl.tcode[np.maximum(a, 0)] == pl.tcode[ev_rows]
        inside = (a >= 0) & same_name
        cand = np.where(inside, a, -1)
        keep = inside & (cand >= 0)
        keep &= np.where(keep, pl.U1[np.maximum(cand, 0)], False)
        anchors_by_lead[L] = cand[keep]
        inside_by_lead[L], keep_by_lead[L] = inside, keep
        eligibility[str(L)] = OrderedDict([
            ("events_in_cohort", int(ev_rows.size)),
            ("excluded_no_bar_at_lead", int((~inside).sum())),
            ("excluded_not_u1_eligible",
             int(inside.sum() - int(keep.sum()))),
            ("case_anchors", int(keep.sum())),
        ])
    const_cohort = np.ones(ev_rows.size, bool)
    for L in LEAD_GRID:
        a = ev_rows - L
        same = (a >= 0) & (pl.tcode[np.maximum(a, 0)] == pl.tcode[ev_rows])
        const_cohort &= same & np.where(same, pl.U1[np.maximum(a, 0)], False)

    ev_board, ev_split = pl.board_code[ev_rows], pl.split_gcode[ev_rows]
    elig_bs = OrderedDict()

    for b in boards:
        bi = BOARD_ORDER.index(b)
        for sg in GATED_SPLITS:
            si = list(SPLIT_GROUPS).index(sg)
            # the control pool for this (board, split) is selected ONCE, not once per
            # footprint x mode x lead — it is ~1M rows and the loop below is ~200 deep
            ctrl_bs = ctrl_rows[(pl.board_code[ctrl_rows] == bi)
                                & (pl.split_gcode[ctrl_rows] == si)]
            anchors_bs = {L: v[(pl.board_code[v] == bi) & (pl.split_gcode[v] == si)]
                          for L, v in anchors_by_lead.items()}
            # A4 — eligibility accounting scoped to THIS cohort. The case and control
            # sets the curve tables describe are already per (board, split), so a global
            # exclusion series printed beside them is wrong-scoped.
            in_coh = (ev_board == bi) & (ev_split == si)
            per_lead = OrderedDict()
            for L in LEAD_GRID:
                ins, kp = inside_by_lead[L], keep_by_lead[L]
                cca = ev_rows - L
                cca = cca[const_cohort & (cca >= 0)]
                cca = cca[pl.U1[cca]]
                cca = cca[(pl.board_code[cca] == bi) & (pl.split_gcode[cca] == si)]
                no_bar = int((in_coh & ~ins).sum())
                not_u1 = int((in_coh & ins & ~kp).sum())
                per_lead[str(L)] = OrderedDict([
                    ("events_in_cohort", int(in_coh.sum())),
                    ("excluded_no_bar_at_lead", no_bar),
                    ("excluded_not_u1_eligible", not_u1),
                    ("excluded_total", no_bar + not_u1),
                    ("case_anchors_full_cohort", int(anchors_bs[L].size)),
                    ("case_anchors_constant_cohort", int(cca.size)),
                    ("controls", int(ctrl_bs.size)),
                ])
            elig_bs[f"{b}|{sg}"] = per_lead
            for fk in FKEYS_ORDER:
                fac = arm_factors(fk, "M1")
                packed = pl.packed(fac)
                mask = pl.masks[MEASURABILITY[fk]]
                fv = pl.F[fk]
                co = ctrl_bs[mask[ctrl_bs]]
                for mode, sel in (("full_cohort", None),
                                  ("constant_cohort", const_cohort)):
                    if mode == "constant_cohort" and fk not in \
                            CONSTANT_COHORT_FOOTPRINTS:
                        continue
                    rows_out = OrderedDict()
                    for L in LEAD_GRID:
                        if sel is None:
                            ca = anchors_bs[L]
                        else:
                            a = ev_rows - L
                            ca = a[sel & (a >= 0)]
                            ca = ca[pl.U1[ca]]
                            ca = ca[(pl.board_code[ca] == bi)
                                    & (pl.split_gcode[ca] == si)]
                        ca = ca[mask[ca]]
                        if ca.size == 0 or co.size == 0:
                            rows_out[str(L)] = {"status": "EMPTY",
                                                "case_anchors": int(ca.size),
                                                "controls": int(co.size)}
                            continue
                        allr = np.concatenate([ca, co])
                        is_case = np.r_[np.ones(ca.size, bool), np.zeros(co.size, bool)]
                        yv = fv[allr]
                        sc, un = pd.factorize(packed[allr], sort=True)
                        n1, k1, n0, k0 = suff_stats(sc, int(un.size), is_case, yv)
                        pe = point_estimate(n1, k1, n0, k0)
                        if pe is None:
                            rows_out[str(L)] = {"status": "NO_MATCHABLE_STRATUM",
                                                "case_anchors": int(ca.size),
                                                "controls": int(co.size)}
                            continue
                        s1 = se_session_block(
                            n1, k1, n0, k0, pe["use"],
                            (un // SESSION_DIVISOR).astype(np.int64),
                            _seed_seq("lead", b, sg, fk, mode, L),
                            draws=LEAD_CURVE_B)      # prereg sec.9 pins B here
                        rows_out[str(L)] = OrderedDict([
                            ("case_anchors", int(ca.size)),
                            ("case_names", int(np.unique(pl.tcode[ca]).size)),
                            ("case_sessions", int(np.unique(pl.dcode[ca]).size)),
                            ("controls", int(co.size)),
                            ("control_names", int(np.unique(pl.tcode[co]).size)),
                            ("case_prevalence_pct", round(100.0 * pe["obs"], 3)),
                            ("matched_control_prevalence_pct",
                             round(100.0 * pe["exp"], 3)),
                            ("excess_prevalence_pp", round(pe["excess_pp"], 3)),
                            ("ci95_pp", [round(v, 3) for v in s1["ci95"]]
                             if s1.get("ci95") else None),
                            ("matched_case_anchors", pe["n_matched_F1_rows"]),
                        ])
                    curves[f"{b}|{sg}|{fk}|{mode}"] = rows_out
    return {
        "curves": curves, "eligibility_per_lead": eligibility,
        "eligibility_per_lead_by_board_split": elig_bs,
        "eligibility_scope_note": (
            "`eligibility_per_lead` is the GLOBAL series over the whole cohort. "
            "`eligibility_per_lead_by_board_split` is the same accounting re-scoped to "
            "each (board, split) cohort, and it is what the curve tables print. "
            "EXCLUSIONS are keyed on the EVENT's own board and split — an excluded event "
            "either has no anchor bar at that lead, or has one that is not U1-eligible "
            "and may therefore carry no split assignment at all, so the event's own split "
            "is the only defined key. CASE ANCHOR counts are keyed on the ANCHOR's own "
            "split (reading note R3), which is the set the curves actually use. The two "
            "keys disagree only for an anchor that crosses a split boundary, so a "
            "cohort's rows are not required to sum exactly to its event count."),
        "lead_grid": list(LEAD_GRID),
        "narrative_windows": {k: list(v) for k, v in NARRATIVE_WINDOWS.items()},
        "bootstrap_draws": LEAD_CURVE_B,
        "known_mechanical_break": (
            "coldness at lead <= 20 is IMPLIED by the event's own cold eve "
            "(COLD_LOOKBACK_K = 20), so cold-driven exclusions are ~0 through lead 20 and "
            "jump at lead 21 — exactly the [6,20] -> [21,60] window boundary. NO "
            "comparison may be made across that boundary on the full-cohort curve; the "
            "boundary is a COLD_LOOKBACK_K artifact, not a signal."),
        "constant_cohort_scope": (
            "printed ONLY for " + ", ".join(CONSTANT_COHORT_FOOTPRINTS) + ". It is NOT "
            "interpretable for the DD / depth / duration families — U1-eligibility at "
            "every lead IS the DD condition, so their constant-cohort curves are "
            "tautologically flat — and is therefore not printed for them. Its absence "
            "there is deliberate, not an omission."),
        "split_assignment": ("a case anchor and its controls are compared inside the "
                             "ANCHOR's own session, so both carry that session's split by "
                             "construction"),
    }


def flagged_sets(pl: Plane, boards) -> dict:
    """sec.10 — DESCRIPTIVE, EXPLICITLY NOT A RANKER. No threshold is tuned, nothing is
    combined or ranked, no per-name selection exists, and no number here may be quoted as
    a strategy result."""
    out = OrderedDict()
    H = H_PRIMARY
    for fk in FKEYS_ORDER:
        u = ARM_UNIVERSE[VERDICT_ARM[fk]]
        for b in boards:
            for sg in SPLIT_GROUPS:
                rows = cell_rows(pl, u, b, sg)
                rows = rows[pl.masks[MEASURABILITY[fk]][rows] & pl.win_ok[H][rows]]
                if not rows.size:
                    continue
                F, y = pl.F[fk][rows], pl.fb[H][rows]
                nF = int(F.sum())
                # counted over EVERY session in the cell — a session with zero flags is a
                # zero, not an absence, or the median is biased upward by construction
                scode, suni = pd.factorize(pl.dcode[rows], sort=True)
                per_sess = np.bincount(scode[F], minlength=len(suni))
                out[f"{fk}|{b}|{sg}"] = OrderedDict([
                    ("positive_episodes",
                     int(np.unique(pl.episode_row[rows][y]).size)),
                    ("sessions", int(np.unique(pl.dcode[rows]).size)),
                    ("names", int(np.unique(pl.tcode[rows]).size)),
                    ("rows", int(rows.size)),
                    ("arm_universe", u),
                    ("flag_rate_pct", round(100.0 * nF / rows.size, 3)),
                    ("precision_pct", round(100.0 * float((F & y).sum()) / nF, 3)
                     if nF else None),
                    ("capture_pct", round(100.0 * float((F & y).sum())
                                          / max(int(y.sum()), 1), 3)),
                    ("flagged_per_session_median", float(np.median(per_sess))),
                    ("flagged_per_session_iqr", [float(np.percentile(per_sess, 25)),
                                                 float(np.percentile(per_sess, 75))]),
                ])
    out["_stamp"] = ("DESCRIPTIVE ONLY — no threshold tuned, nothing combined or ranked, "
                     "no per-name selection (DNR:KILL-OUTCOME-AUDITION respected). None "
                     "of these numbers is a strategy result and none may be quoted as "
                     "one.")
    return out


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 7 — verification battery: 17 prereg checks, each paired with a mutation
# ══════════════════════════════════════════════════════════════════════════════


def verify_battery(pl, w1, pb, w1_sha, pb_sha, primary, floors, lead_keys, controls,
                   ctrl_meta, ev, boards, vintage) -> dict:
    checks: "OrderedDict[str, dict]" = OrderedDict()
    _probe = pb._probe

    def _add(name, why, fn, base_arg, probes):
        ok, det = fn(base_arg)
        recs = [_probe(fn, m, lab) for m, lab in probes]
        checks[name] = {
            "why": why, "passed": bool(ok), "detail": det,
            "mutation_probe": {
                "mutation": " | ".join(r["mutation"] for r in recs),
                "detected": all(r["detected"] for r in recs),
                "via": " | ".join(r["via"] for r in recs),
                "probes": recs},
        }

    # ── 1. label_identity ────────────────────────────────────────────────────
    def _label_identity(off: int):
        per = {}
        bad = 0
        for H in (5, 10, 20):
            y = pl.panel[f"fb_{H}"].to_numpy(bool)
            ok = pl.panel[f"win_ok_{H}"].to_numpy(bool)
            scope = pl.fwd_avail >= H
            rhs = ok & (pl.dist_next <= (H + off))
            mism = int((y[scope] != rhs[scope]).sum())
            # IN SCOPE this must be 0. Out of scope it is not: the raw store runs a week
            # past WINDOW_END, so a handful of end-of-tape bars carry fb_H from a board
            # that is live but OUTSIDE the panel window. Those rows are counted, and the
            # count that actually matters — how many of them reach a universe — is 0 by
            # W-P0's own 20-session split embargo, which leaves the tail unassigned.
            outside_in_scope = int((y & scope & (pl.dist_next > H)).sum())
            tail = y & ~scope & (pl.dist_next > H)
            per[f"H{H}"] = {
                "rows_scoped": int(scope.sum()), "mismatches": mism,
                "positives_in_scope_with_board_outside_the_panel": outside_in_scope,
                "positives_out_of_scope_with_board_beyond_WINDOW_END": int(tail.sum()),
                "of_those_inside_U0": int((tail & pl.U0).sum()),
                "of_those_inside_U1": int((tail & pl.U1).sum()),
            }
            bad += mism + (outside_in_scope + int((tail & pl.U0).sum())
                           if off == 0 else 0)
        return bad == 0, {
            "per_horizon": per,
            "rule": ("fb_H == win_ok_H AND (panel-re-derived next-board distance <= H), "
                     "exactly, scoped to rows with T+H inside the panel window. Inside "
                     "that scope the count of positives whose board bar falls outside "
                     "WINDOW_END must be 0, and so must the count of end-of-tape "
                     "positives that reach a universe — W-P0's 20-session split embargo "
                     "leaves the final sessions without a split, which is exactly what "
                     "keeps the out-of-window boards out of every estimator"),
        }
    _add("label_identity",
         "prereg sec.11.1 — the label is W-P0's fb_H verbatim; a re-derivation on the "
         "panel axis must reproduce it exactly or the outcome being scored is not the "
         "outcome that was frozen",
         _label_identity, 0,
         [(lambda: 1, "off-by-one the panel-axis re-derivation (distance <= H+1)")])

    # ── 2. no_lookahead (fixed anchors) ──────────────────────────────────────
    sample = sorted(p.stem for p in sorted(RAW_DIR.glob("*.parquet"))[::28])[:64]
    CUTS = (pd.Timestamp("2015-01-05"), pd.Timestamp("2019-01-02"),
            pd.Timestamp("2022-01-04"))
    PAST_SLAB = pd.Timestamp("2020-01-02")
    base_sub = pb._sub_panel(w1, sample)

    sample_idx = pd.Index(sample)
    ddb_idx, durb_idx = pd.Index(DD_BAND_ORDER), pd.Index(DUR_BAND_ORDER)

    def _fingerprint(sub, cut):
        """Anchor-keyed footprint AND stratum fingerprint, on sorted integer keys.

        Deliberately not a MultiIndex: aligning two ~150k-row (ticker, date) MultiIndexes
        with `.intersection` + `.loc` is minutes of the run for a check that is one
        `np.intersect1d` away from being instant."""
        m = sub["date"].to_numpy() <= cut.to_datetime64()
        s = sub.loc[m]
        key = (sample_idx.get_indexer(s["ticker"].to_numpy()).astype(np.int64) * 100000
               + s["date"].to_numpy().astype("datetime64[D]").astype(np.int64))
        rv = s["rv_rank"].to_numpy(np.float64)
        dec = np.where(np.isfinite(rv),
                       np.minimum((np.nan_to_num(rv) * 10).astype(np.int64), 9), 10)
        cols = [s[c].to_numpy().astype(np.int16) for c in pb.FKEYS]
        cols += [dec.astype(np.int16),
                 ddb_idx.get_indexer(s["dd_band"].astype(str).to_numpy()).astype(np.int16),
                 durb_idx.get_indexer(s["dur_band"].astype(str).to_numpy())
                 .astype(np.int16)]
        o = np.argsort(key, kind="stable")
        return (key[o], np.column_stack(cols)[o], s["fb_10"].to_numpy(bool)[o],
                s["date"].to_numpy()[o])

    def _mut(after, cut):
        def _m(df):
            d = df.copy()
            sel = (d.index > cut) if after else \
                ((d.index > PAST_SLAB) & (d.index <= cut))
            d.loc[sel, ["open", "high", "low", "close"]] = \
                d.loc[sel, ["open", "high", "low", "close"]] * 1.35
            return d
        return _m

    def _nolook(direction):
        cuts = CUTS if direction == "future" else (CUTS[-1],)
        per = []
        for cut in cuts:
            bk, bF, blab, bday = _fingerprint(base_sub, cut)
            sub = pb._sub_panel(w1, sample, mutate=_mut(direction == "future", cut))
            mk, mF, mlab, _md = _fingerprint(sub, cut)
            common, bi, mi = np.intersect1d(bk, mk, return_indices=True)
            cells = int((bF[bi] != mF[mi]).sum())
            strict = pd.DatetimeIndex(bday[bi]) <= (cut - pd.Timedelta(days=45))
            lab_strict = int((blab[bi][strict] != mlab[mi][strict]).sum())
            lab_cross = int((blab[bi][~strict] != mlab[mi][~strict]).sum())
            per.append({"cut": str(cut.date()), "anchor_rows_compared": int(common.size),
                        "rows_missing_after_corruption": int(bk.size - common.size),
                        "footprint_and_stratum_cells_changed": cells,
                        "label_changes_strict_set": lab_strict,
                        "label_changes_window_crossing_set": lab_cross})
        bad = sum(r["footprint_and_stratum_cells_changed"]
                  + r["label_changes_strict_set"] + r["rows_missing_after_corruption"]
                  for r in per)
        return bad == 0, {
            "direction_corrupted": direction, "tickers_sampled": len(sample),
            "prices_scaled_by": 1.35, "per_cut": per,
            "past_slab": [str(PAST_SLAB.date()), str(CUTS[-1].date())],
            "why": ("every footprint AND every stratum value is read at the anchor bar, so "
                    "a bar strictly after the anchor may not move one. Labels may move "
                    "only on the WINDOW-CROSSING set (rows whose forward H-window reaches "
                    "past the cut); those are reported separately and include the "
                    "detector-rounding flips that round(pc*(1+w),2) makes unavoidable "
                    "under a price scaling — they never void the receipt, and the strict "
                    "set must be exactly 0."),
        }
    _add("no_lookahead",
         "prereg sec.11.2 — a bar after the anchor must not move a footprint or a stratum "
         "value; if it can, the whole comparison is contaminated",
         _nolook, "future",
         [(lambda: "past", "scale a two-year slab INSIDE the pre-cut history instead of "
                           "the post-cut tail (must move the footprints)")])

    # ── 3. stratum_outcome_independence ──────────────────────────────────────
    def _strat_keys(y, leak):
        k = pl.packed(("session", "vol", "dd_band", "dur_band"))
        return (k * 2 + y.astype(np.int64)) if leak else k

    def _si(leak):
        y = pl.fb[H_PRIMARY]
        rng = np.random.default_rng(_seed_seq("stratum_indep"))
        grp = pd.factorize(pl.board, sort=True)[0].astype(np.int64) * (pl.dcode.max() + 1) \
            + pl.dcode
        # rows listed grouped by `grp`: stably on the left, in random order on the right.
        srt = np.argsort(grp, kind="stable")
        order = np.lexsort((rng.random(pl.n), grp))
        yp = np.empty_like(y)
        yp[srt] = y[order]                       # a permutation INSIDE each (board, session)
        a, b = _strat_keys(y, leak), _strat_keys(yp, leak)
        changed = int((a != b).sum())
        return changed == 0, {
            "rows": pl.n, "stratum_keys_changed_under_label_permutation": changed,
            "labels_moved": int((y != yp).sum()),
            "rule": "stratum keys are functions of the tape and the calendar ONLY; "
                    "permuting the label inside (board, session) may not move one bit",
        }
    _add("stratum_outcome_independence",
         "prereg sec.11.3 — a stratum key that saw the label would match on the outcome "
         "and manufacture the excess it is supposed to remove",
         _si, False,
         [(lambda: True, "leak the permuted label into the stratum key")])

    # ── 4. cold_universe ─────────────────────────────────────────────────────
    cand = np.flatnonzero(pl.U0 & (pl.pos_in_name >= 150))
    ct = None
    for i in cand:
        t = str(pl.panel["ticker"].to_numpy()[i])
        if (RAW_DIR / f"{t}.parquet").exists():
            ct, cd = t, pd.Timestamp(pl.date[i])
            break

    def _cold(offset):
        if ct is None:
            return False, {"status": "no probe anchor available"}
        raw = pd.read_parquet(RAW_DIR / f"{ct}.parquet").sort_index()
        board = w1._board_from_ticker(ct)
        pos = int(pd.DatetimeIndex(raw.index).searchsorted(cd.to_datetime64(), "left"))
        p = pos - offset
        d = raw.copy()
        wdt = float(w1.limit_width_for_date(board, pd.Timestamp(raw.index[p])))
        lim = round(float(d["close"].iloc[p - 1]) * (1.0 + wdt), 2)
        d.iloc[p, d.columns.get_loc("close")] = lim
        d.iloc[p, d.columns.get_loc("high")] = max(lim, float(d["high"].iloc[p]))
        d.iloc[p, d.columns.get_loc("volume")] = max(1.0, float(d["volume"].iloc[p]))
        out, _ = w1.process_ticker(ct, d, board)
        row = out[out["date"] == cd.to_datetime64()]
        still = bool(len(row) and bool(row["cold"].iloc[0]))
        return (not still), {
            "probe_ticker": ct, "probe_anchor": str(cd.date()),
            "planted_offset_sessions": offset,
            "anchor_still_cold": still, "cold_lookback_K": int(w1.COLD_LOOKBACK_K),
            "rule": ("a board planted INSIDE the prior-20 window (the anchor bar "
                     "included) must eject the anchor from the cold universe; one "
                     "planted OUTSIDE it must not"),
        }
    _add("cold_universe",
         "prereg sec.11.4 — the cold rule is what makes every positive a genuine 0->1 "
         "ignition rather than a re-board; it must be enforced, not asserted",
         _cold, 5,
         [(lambda: 25, "plant the same board 25 sessions back — OUTSIDE the prior-20 "
                       "window, where the anchor must stay cold (so the check fails)")])

    # ── 5. censoring_partition ───────────────────────────────────────────────
    def _cens(fold_censored_in):
        bad, per = 0, {}
        for H in HORIZONS:
            y, ok = pl.fb[H], pl.win_ok[H]
            for u in ("U0", "U1"):
                for b in BOARD_ORDER:
                    for sg in GATED_SPLITS:
                        r = cell_rows(pl, u, b, sg)
                        if not r.size:
                            continue
                        tot = int(r.size)
                        s = int(y[r].sum()) + int((ok[r] & ~y[r]).sum()) \
                            + int((~ok[r]).sum())
                        analysed = r if fold_censored_in else r[ok[r]]
                        cens_in = int((~ok[analysed]).sum())
                        bad += int(s != tot) + cens_in
                        per[f"H{H}|{u}|{b}|{sg}"] = {
                            "eligible_rows": tot, "partition_sum": s,
                            "censored_rows_inside_the_estimator": cens_in}
        return bad == 0, {"cells": len(per), "violations": bad, "per_cell": per,
                          "rule": "eligible == positives + negatives + censored, exactly, "
                                  "and no censored row enters any estimator"}
    _add("censoring_partition",
         "prereg sec.11.5 — a censored row is a row whose window is unobservable; scoring "
         "it as a miss would invent negatives out of missing tape",
         _cens, False,
         [(lambda: True, "fold censored rows into the analysed set as negatives")])

    # ── 6. board_era_disjointness ────────────────────────────────────────────
    def _disjoint(keys):
        bad = {}
        for name, ks in keys.items():
            ks = [str(k) for k in ks]
            if sorted(ks) != sorted(set(ks)):
                bad[name] = "duplicate group key"
            bs = {k.split("|")[0] for k in ks} if name.startswith("lead") else \
                {p for k in ks for p in k.split("|") if p in BOARD_ORDER
                 or p.startswith("ALL")}
            extra = sorted(b for b in bs if b not in BOARD_ORDER)
            if extra:
                bad[name] = f"non-board key(s): {extra}"
            for k in ks:
                if "ALL_BOARDS" in k or "|all|" in k or k.endswith("|pooled"):
                    bad[name] = f"pooled key: {k}"
        return (not bad), {"tables_checked": len(keys), "violations": bad,
                           "rule": "main / chinext10 / chinext20 / star are four "
                                   "populations and share no cell; eras are never "
                                   "averaged and no pooled key may exist"}
    tabs = {"primary": list(primary), "floors": list(floors),
            "lead_curves": list(lead_keys)}
    _add("board_era_disjointness",
         "prereg sec.11.6 — the target-class law; a pooled board or era key would make "
         "every rate in the receipt a blend of different populations",
         _disjoint, tabs,
         [(lambda: {**tabs, "primary": list(primary) + ["H10|M1|ALL_BOARDS|FIT|cb_recent"]},
           "inject a pooled ALL_BOARDS row into an output table")])

    # ── 7. feature_liveness ──────────────────────────────────────────────────
    ref = None
    for b in boards:
        k = f"H{H_PRIMARY}|M1|{b}|FIT"
        if cell_rows(pl, "U1", b, "FIT").size:
            ref = (b, cell_rows(pl, "U1", b, "FIT"))
            break

    def _liveness(colmap):
        b, rows = ref
        bad, seen = 0, {}
        for key, c in primary.items():
            if c.get("board_verdict_eligible") and c.get("split") == "FIT" \
                    and c.get("status") != "NOT_EVALUABLE":
                if c["estimate"]["matched_F_true_rows"] < 1 \
                        or c["estimate"]["matched_F_false_rows"] < 1:
                    bad += 1
        degen = {}
        for lab, col in colmap.items():
            c = build_cell(pl, lab, col, MASK_ALL, arm_factors("cb_recent", "M1"),
                           rows, H_PRIMARY, f"liveness|{b}", want_inference=False)
            v = verdict_for(c, None, True, False)
            degen[lab] = v["verdict"]
            if c.get("status") != "NOT_EVALUABLE" or v["verdict"] != "NOT_EVALUABLE":
                bad += 1
        return bad == 0, {
            "verdict_cells_with_an_empty_F_class": bad,
            "degenerate_column_verdicts": degen,
            "rule": "every gated cell carries both F-classes; a zeroed column AND an "
                    "all-TRUE column must BOTH surface as NOT_EVALUABLE, never as NULL",
        }
    base_cols = {"zeroed_column": np.zeros(pl.n, bool),
                 "all_true_column": np.ones(pl.n, bool)}
    _add("feature_liveness",
         "prereg sec.11.7 — a dead feature that prints NULL reads as 'measured and "
         "absent'; it must print NOT_EVALUABLE",
         _liveness, base_cols,
         [(lambda: {"zeroed_column": np.zeros(pl.n, bool),
                    "leaked_live_column": pl.F["cb_recent"]},
           "swap one degenerate column for a LIVE one, which must stop printing "
           "NOT_EVALUABLE (so the check fails)")])

    # ── 8. carveout_applied ──────────────────────────────────────────────────
    def _carve(cmap):
        bad = {}
        for key, c in primary.items():
            fk = c.get("footprint")
            arm = c.get("arm")
            if fk not in cmap:
                continue
            want = list(arm_factors(None, arm, cmap[fk][arm]))
            if list(c["stratum_factors"]) != want:
                bad[key] = {"expected": want, "applied": list(c["stratum_factors"])}
        return (not bad), {"cells_checked": len(primary), "violations": bad,
                           "map": {k: {a: list(v[a]) for a in ARMS}
                                   for k, v in cmap.items()},
                           "rule": "a footprint is never evaluated inside strata built "
                                   "from its own underlying series; dd250 and dd_dur "
                                   "share the 250-session high, so the DD/duration family "
                                   "is ONE series"}
    _add("carveout_applied",
         "prereg sec.11.8 / sec.5.3 — a footprint matched against strata built from its "
         "own series is compared against itself and its excess is an artifact",
         _carve, CARVEOUT,
         [(lambda: {**CARVEOUT, "quiet_base": {"M0": (), "M1": ()}},
           "flip the QB carve-out entry so the vol decile is no longer dropped")])

    # ── 9. concentration_guard ───────────────────────────────────────────────
    def _conc(dup):
        bad, seen = {}, 0
        for key, c in primary.items():
            if c.get("split") != "FIT" or c.get("horizon") != H_PRIMARY \
                    or c.get("status") == "NOT_EVALUABLE" \
                    or "max_single_name_positive_episode_share" not in c:
                continue
            H = c["horizon"]
            fk = c["footprint"]
            fac = tuple(c["stratum_factors"])
            rows = cell_rows(pl, ARM_UNIVERSE[c["arm"]], c["board"], "FIT")
            rows = rows[pl.masks[MEASURABILITY[fk]][rows] & pl.win_ok[H][rows]]
            F, y = pl.F[fk][rows], pl.fb[H][rows]
            sc, un = pd.factorize(pl.packed(fac)[rows], sort=True)
            n1, k1, n0, k0 = suff_stats(sc, int(un.size), F, y)
            pe = point_estimate(n1, k1, n0, k0)
            if pe is None:
                continue
            sel = rows[F & y & pe["use"][sc]]          # the RETAINED F=TRUE positives
            if not sel.size:
                continue
            ep, nm = pl.episode_row[sel], pl.tcode[sel]
            if dup:
                # The statistic is keyed on EPISODES, so re-appending the same rows is a
                # VACUOUS mutation — `np.unique` collapses them straight back and the
                # share never moves (measured: probe undetected). The mutation has to give
                # one name MORE EPISODES, so the clones carry synthetic episode ids.
                nm0 = nm[0]
                m = nm == nm0
                ep = np.concatenate([ep] + [ep[m] + 10 ** 9 * (i + 1)
                                            for i in range(dup)])
                nm = np.concatenate([nm] + [np.full(int(m.sum()), nm0)] * dup)
            u, first = np.unique(ep, return_index=True)
            share = float(np.bincount(nm[first]).max()) / float(u.size)
            seen += 1
            if abs(share - c["max_single_name_positive_episode_share"]) > 1e-4:
                bad[key] = {"recomputed_share": round(share, 4),
                            "reported": c["max_single_name_positive_episode_share"]}
            elif bool(share > CONCENTRATION_CAP) != bool(c["concentrated"]):
                bad[key] = {"flag_disagrees_with_share": round(share, 4)}
        return (not bad), {"cells_checked": seen, "violations": bad,
                           "cap": CONCENTRATION_CAP,
                           "rule": "concentration is measured on positive EPISODES, never "
                                   "on rows; > 40% from one name flags CONCENTRATED and "
                                   "caps the verdict at SUGGESTIVE"}
    _add("concentration_guard",
         "prereg sec.11.9 — one name printing many boards can carry a whole cell; the "
         "guard must be keyed to episodes and must actually fire",
         _conc, 0,
         [(lambda: 40, "duplicate one name's positive rows 40x so it dominates the "
                       "episode count")])

    # ── 10. placebo_sensitivity ──────────────────────────────────────────────
    pb_board = boards[0]
    pl_rows = cell_rows(pl, "U1", pb_board, "FIT")
    rngp = np.random.default_rng(_seed_seq("placebo_sensitivity"))
    sub_mask = np.zeros(pl.n, bool)
    sub_mask[pl_rows[rngp.random(pl_rows.size) < 0.30]] = True
    planted = pl.fb[H_PRIMARY] & sub_mask

    def _plant_z(shift):
        if shift == 0:
            fv = planted
        else:
            src = np.clip(np.arange(pl.n) - shift, 0, pl.n - 1)
            valid = np.zeros(pl.n, bool)
            for a, b in zip(pl.grp_starts, pl.grp_ends):
                valid[a + shift:b] = True
            fv = planted[src] & valid
        c = build_cell(pl, "planted", fv, MASK_ALL, arm_factors("cb_recent", "M1"),
                       pl_rows, H_PRIMARY, f"plantcheck|{shift}", want_inference=True)
        return c.get("inference", {}).get("z_2way")

    def _psens(shifts):
        z0 = _plant_z(0)
        zs = {str(s): _plant_z(s) for s in shifts}
        vals = [abs(v) for v in zs.values() if v is not None]
        leak_ok = bool(z0 is not None and abs(z0) >= 10.0)
        ceil = max(G2_Z, abs(z0) / 10.0) if z0 else G2_Z
        calib_ok = bool(vals and max(vals) <= ceil)
        return (leak_ok and calib_ok), {
            "unshifted_planted_z": round(z0, 3) if z0 else None,
            "shifted_planted_z": {k: (round(v, 3) if v is not None else None)
                                  for k, v in zs.items()},
            "leak_bar": 10.0, "calibration_ceiling": round(ceil, 3),
            "subsample_share": 0.30, "board": pb_board,
            "rule": ("a synthetic footprint planted EQUAL TO THE LABEL on a subsample must "
                     "reject enormously UNSHIFTED and fall back toward nominal under the "
                     "sec.6.3 shifts — otherwise the placebo battery cannot see a real "
                     "leak and its calibration verdict is worthless"),
        }
    _add("placebo_sensitivity",
         "prereg sec.11.10 — the placebo calibration is only evidence if it can detect a "
         "leak it is supposed to detect",
         _psens, PLACEBO_SHIFTS,
         [(lambda: (0,) + PLACEBO_SHIFTS,
           "put shift 0 (the planted leak itself) into the calibration set and assert it "
           "is calibrated")])

    # ── 11. missing_not_false ────────────────────────────────────────────────
    ma200_probe = _ma200_covering_lemma(w1, sample)

    def _missing(apply_masks):
        viol, per = 0, {}
        for fk in FKEYS_ORDER:
            m = pl.masks[MEASURABILITY[fk]]
            for b in boards:
                rows = cell_rows(pl, ARM_UNIVERSE[VERDICT_ARM[fk]], b, "FIT")
                rows = rows[pl.win_ok[H_PRIMARY][rows]]
                analysed = rows[m[rows]] if apply_masks else rows
                f0 = analysed[~pl.F[fk][analysed]]
                bad = int((~m[f0]).sum())
                viol += bad
                per[f"{fk}|{b}"] = {"analysed_F_false_rows": int(f0.size),
                                    "unmeasurable_rows_inside_F_false": bad,
                                    "rows_excluded_by_mask":
                                        int(rows.size - analysed.size)}
        return viol == 0, {
            "violations": viol, "per_footprint_board": per,
            "masks": dict(MEASURABILITY),
            "ma200_covering_lemma": ma200_probe,
            "rule": ("P-B's boolean derivation codes MISSING as FALSE; leaving that in "
                     "the F=FALSE class would estimate the counterfactual from a mixture "
                     "of measured negatives and unmeasurables. Every footprint's F=FALSE "
                     "class therefore contains zero rows failing that footprint's "
                     "measurability mask."),
        }
    _add("missing_not_false",
         "prereg sec.11.11 — an unmeasurable row is not a measured FALSE; mixing them "
         "estimates the counterfactual off the wrong population",
         _missing, True,
         [(lambda: False, "re-admit unmeasurable rows into the F=FALSE class")])

    # ── 12. control_completeness ─────────────────────────────────────────────
    def _ctrl(require_chain):
        adm = pl.U1 & (pl.dist_next > CONTROL_FORWARD)
        if require_chain:
            adm = adm & (pl.fwd_run >= CONTROL_FORWARD)
        bad = int((adm & (pl.fwd_run < CONTROL_FORWARD)).sum())
        return bad == 0, {
            "admitted_controls": int(adm.sum()),
            "admitted_with_incomplete_60_session_chain": bad,
            **ctrl_meta,
            "rule": ("a control must PROVE 60 quiet forward sessions. The "
                     "next-board-distance sentinel (no future board => distance = BIG) "
                     "would otherwise admit every end-of-data row as 'verified quiet' — "
                     "right-truncation that enriches the control arm with exactly the "
                     "rows whose future is unobserved."),
        }
    _add("control_completeness",
         "prereg sec.11.12 — an unverifiable quiet control is a right-truncation bias "
         "wearing a control's clothes",
         _ctrl, True,
         [(lambda: False, "admit controls whose 60-session forward chain is incomplete")])

    # ── 13. permutation_recomputes_exp ───────────────────────────────────────
    perm_ref = next((c for c in primary.values()
                     if c.get("permutation_diagnostic", {}).get("draws")), None)

    def _perm_exp(hold_fixed):
        if perm_ref is None:
            return False, {"status": "no permutation diagnostic computed"}
        d = perm_ref["permutation_diagnostic"]
        moved = d["exp_leg_distinct_values"] > 1 and d["exp_leg_sd_pp"] > 0
        if hold_fixed:
            moved = False
        return bool(moved), {
            "cell": perm_ref["cell"], "footprint": perm_ref["footprint"],
            "exp_leg_sd_pp": d["exp_leg_sd_pp"],
            "exp_leg_distinct_values": d["exp_leg_distinct_values"],
            "p_two_sided": d["p_two_sided_min_tail_x2"],
            "rule": "the permutation recomputes the FULL standardised excess per draw; a "
                    "permutation that holds `exp` at its observed value tests a different "
                    "and easier null",
        }
    _add("permutation_recomputes_exp",
         "prereg sec.11.13 — holding the expected leg fixed silently changes the null the "
         "diagnostic reports",
         _perm_exp, False,
         [(lambda: True, "hold exp fixed across draws")])

    # ── 14. stop_ship_reference_scan ─────────────────────────────────────────
    scan_targets = {"pb2_precursor_discrimination.py": Path(__file__).read_text()}
    ok, det = pb.stop_ship_scan(scan_targets)
    checks["stop_ship_reference_scan"] = {
        "why": ("prereg sec.11.14 / DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT — zero "
                "references to withdrawn artifacts, grep-verified over the instrument AND "
                "the emitted prose (main() re-runs it over the receipt)"),
        "passed": ok, "detail": det, "ruling_cited": GOVERNING_RULING,
        "mutation_probe": _probe(
            pb.stop_ship_scan,
            lambda: {**scan_targets,
                     "synthetic": f"this sentence cites {pb.WITHDRAWN_TOKENS[6]} table 3"},
            "introduce a withdrawn-artifact reference into a scanned surface"),
    }

    # ── 15. detector_vs_zt_pool ──────────────────────────────────────────────
    # Integer-keyed on purpose: a Python set over millions of (ticker, date) tuples is a
    # gigabyte of avoidable overhead on the full panel.
    zt = pd.read_parquet(ZT_P, columns=["ticker", "date"])
    zt["date"] = pd.to_datetime(zt["date"])
    shared_dates = np.intersect1d(zt["date"].unique(), pl.panel["date"].unique())
    pm = np.isin(pl.date, shared_dates)
    zm = np.isin(zt["date"].to_numpy(), shared_dates)
    pday = pl.date[pm].astype("datetime64[D]").astype(np.int64)
    zday = zt["date"].to_numpy()[zm].astype("datetime64[D]").astype(np.int64)
    tuniq = pd.Index(pl.tuniq)
    pkey = pl.tcode[pm].astype(np.int64) * 100000 + pday
    zcode = tuniq.get_indexer(zt["ticker"].to_numpy()[zm])
    zkey = np.unique((zcode.astype(np.int64) * 100000 + zday)[zcode >= 0])
    zin = np.intersect1d(zkey, pkey)
    lu_real = pl.lu[pm]

    def _det(flags):
        ds = pkey[flags]
        agree = int(np.intersect1d(zin, ds).size)
        rec = (agree / zin.size) if zin.size else 0.0
        return (rec >= 0.99), {
            "shared_dates": int(shared_dates.size),
            "zt_pairs_inside_universe": int(zin.size),
            "agree": agree, "zt_only_detector_missed": int(zin.size - agree),
            "recall_pct": round(100.0 * rec, 2),
            "note": ("RECALL-ONLY BY CONSTRUCTION — china_zt_pool is a PARTIAL vendor "
                     "store, so a detector board absent from the pool is not evidence of "
                     "a false positive and no precision claim is made"),
        }

    def _mut_det():
        f = lu_real.copy()
        on = np.flatnonzero(f)
        f[on[:max(1, on.size // 20)]] = False
        return f
    ok, det = _det(lu_real)
    checks["detector_vs_zt_pool"] = {
        "why": "prereg sec.11.15 — cross-check the tolerant detector where vendor "
               "coverage overlaps",
        "passed": ok, "detail": det,
        "mutation_probe": _probe(_det, _mut_det,
                                 "switch off 5% of the detector's board flags"),
    }

    # ── 16. provenance (A4 / A5) ─────────────────────────────────────────────
    STAMPS = ("raw_store_commit", "members_commit", "st_snapshot_commit",
              "zt_pool_commit", "w1_pin_commit", "pb_pin_commit", "prereg_commit")

    def _real_non_ancestor(head: str) -> str:
        """A REAL, LOCALLY PRESENT commit that is not an ancestor of the build head.

        The obvious probe — a fabricated 40-hex OID — is a TRAP in this checkout, and the
        trap is worth naming because it costs minutes and depends on the network. This
        repo is a `blob:none` PARTIAL CLONE with a promisor remote
        (`remote.origin.promisor=true`), so ANY reference to an absent object makes git
        ask the remote for it. Measured 2026-08-14: `git merge-base --is-ancestor` on a
        fabricated OID hung for over three minutes before origin answered
        "upload-pack: not our ref". A verification probe must never make the instrument's
        runtime — or its result — depend on a network round trip, so the probe uses a
        commit that genuinely exists here and genuinely is not an ancestor. Its identity
        is deliberately NOT recorded: refs move between runs and the receipts are
        byte-identical by contract.
        """
        refs = PBMOD._git("for-each-ref", "--format=%(objectname)",
                          "refs/remotes/origin/main", "refs/remotes", "refs/heads")
        seen = []
        for sha in refs.split():
            if len(sha) != 40 or sha in seen:
                continue
            seen.append(sha)
            if subprocess.run(["git", "merge-base", "--is-ancestor", sha, head],
                              cwd=REPO, capture_output=True).returncode != 0:
                return sha
            if len(seen) >= 50:
                break
        # No local ref is a non-ancestor (a fresh clone with one branch). Fall back to a
        # syntactically INVALID name, which git rejects instantly and never fetches.
        return "not-a-commit-object"

    def _prov(stamps):
        head = vintage["build_head_sha"]
        bad, seen = {}, {}
        for k in STAMPS:
            c = stamps.get(k, "UNAVAILABLE")
            if c.startswith("SHALLOW_BOUNDARY_UNRESOLVED(") or c == "UNAVAILABLE":
                seen[k] = c
                continue
            rc = subprocess.run(["git", "merge-base", "--is-ancestor", c, head],
                                cwd=REPO, capture_output=True).returncode
            seen[k] = f"{c[:12]} ancestor={rc == 0}"
            if rc != 0:
                bad[k] = c
        return (not bad), {
            "build_head": head[:12], "stamps": seen, "non_ancestor_stamps": bad,
            "repo_is_shallow": vintage["repo_is_shallow"],
            "stamps_unresolved_by_shallow_graft":
                vintage["stamps_unresolved_by_shallow_graft"],
            "rule": "every store stamp must be an ancestor of the build head, else the "
                    "checkout moved mid-run and the provenance is polluted; a stamp "
                    "resolving to a shallow graft is RELABELLED, never printed as "
                    "provenance",
            "probe_note": ("the mutation uses a REAL locally present commit that is not "
                           "an ancestor of the build head, never a fabricated OID: this "
                           "checkout is a blob:none partial clone with a promisor "
                           "remote, so a fabricated OID sends git to the network and "
                           "hung `merge-base` for minutes when measured"),
        }
    _add("provenance",
         "prereg sec.11.16 — a confident wrong vintage is worse than no vintage",
         _prov, {k: vintage[k] for k in STAMPS},
         [(lambda: {**{k: vintage[k] for k in STAMPS},
                    "raw_store_commit": _real_non_ancestor(vintage["build_head_sha"])},
           "assert a non-ancestor stamp passes (a real local commit off the build "
           "head's ancestry)")])

    # ── 17. lead_anchor_position ─────────────────────────────────────────────
    coh = ev[ev["in_cohort"].to_numpy()]
    er, _ok = find_rows(panel_row_lookup(pl), coh["ticker"].to_numpy(),
                        coh["event_date"].to_numpy())
    samp = er[:: max(1, er.size // 500)][:500]

    def _lead_anchor(off):
        bad, checked = 0, 0
        for L in LEAD_GRID:
            a = samp - L + off
            good = (a >= 0) & (pl.tcode[np.maximum(a, 0)] == pl.tcode[samp])
            aa, ss = a[good], samp[good]
            checked += int(aa.size)
            bad += int(((pl.pos_in_name[ss] - pl.pos_in_name[aa]) != L).sum())
        return bad == 0, {
            "events_sampled": int(samp.size), "anchor_checks": checked,
            "position_mismatches": bad, "lead_grid": list(LEAD_GRID),
            "rule": "the case anchor at lead l is EXACTLY the event bar minus l on the "
                    "name's own session axis",
        }
    _add("lead_anchor_position",
         "prereg sec.11.17 — an off-by-one lead would slide the entire two-speed curve "
         "against the board it is measured from",
         _lead_anchor, 0,
         [(lambda: 1, "off-by-one the lead offset")])

    # ── amendment A1 control (NOT one of the prereg's 17) ────────────────────
    def _serow(scale):
        rows_out, worst = {}, 0.0
        for b in boards[:2]:
            rows = cell_rows(pl, "U1", b, "FIT")
            fk = "cb_recent"
            rows = rows[pl.masks[MEASURABILITY[fk]][rows]
                        & pl.win_ok[H_PRIMARY][rows]]
            fac = arm_factors(fk, "M1")
            sc, un = pd.factorize(pl.packed(fac)[rows], sort=True)
            n1, k1, n0, k0 = suff_stats(sc, int(un.size), pl.F[fk][rows],
                                        pl.fb[H_PRIMARY][rows])
            pe = point_estimate(n1, k1, n0, k0)
            cf = se_row_closed_form(n1, k1, n0, k0, pe["use"])["se"] * scale
            sim = se_row_simulated(n1, k1, n0, k0, pe["use"],
                                   _seed_seq("serow", b))
            rel = abs(cf - sim) / sim if sim else 1.0
            worst = max(worst, rel)
            rows_out[b] = {"closed_form_pp": round(cf, 6),
                           "simulated_pp": round(sim, 6),
                           "relative_gap_pct": round(100.0 * rel, 3),
                           "simulation_draws": N_BOOT_ROW}
        return worst <= 0.05, {
            "per_board": rows_out, "tolerance_pct": 5.0,
            "monte_carlo_error_of_a_2000_draw_se_pct": round(
                100.0 / np.sqrt(2 * (N_BOOT_ROW - 1)), 2),
            "rule": "amendment A1 — the closed-form fixed-design row-bootstrap SE must "
                    "agree with the literal N_BOOT_ROW-draw simulation to within Monte "
                    "Carlo error",
        }
    _add("se_row_closed_form_matches_simulation",
         "AMENDMENT A1 CONTROL (not one of the prereg's 17) — the closed form replaces a "
         "2000-draw simulation, so it must be shown to reproduce it",
         _serow, 1.0,
         [(lambda: 1.5, "inflate the closed form by 50%")])

    prereg17 = [k for k in checks if k != "se_row_closed_form_matches_simulation"]
    n_pass = sum(1 for k in prereg17 if checks[k]["passed"])
    n_probe = sum(1 for k in prereg17 if checks[k]["mutation_probe"]["detected"])
    extra = checks["se_row_closed_form_matches_simulation"]
    return {
        "checks": checks,
        "summary": {
            "prereg_checks_run": len(prereg17), "prereg_checks_passed": n_pass,
            "prereg_probes_detected": n_probe,
            "all_prereg_passed": n_pass == len(prereg17),
            "all_prereg_probes_detected": n_probe == len(prereg17),
            "amendment_controls_run": 1,
            "amendment_controls_passed": int(bool(extra["passed"])),
            "amendment_control_probes_detected":
                int(bool(extra["mutation_probe"]["detected"])),
            "checks_run": len(checks),
            "all_passed": (n_pass == len(prereg17)) and bool(extra["passed"]),
            "all_probes_detected": (n_probe == len(prereg17))
            and bool(extra["mutation_probe"]["detected"]),
        },
        "doctrine": ("A check that cannot fail is a defect. Every check above is paired "
                     "with a mutation it MUST detect; `detected: false` anywhere means "
                     "the check is vacuous and the run is not evidence."),
    }


def _ma200_covering_lemma(w1, sample) -> dict:
    """MEASURED, not assumed: `isfinite(ma200)` is implied by U-eligibility.

    W-P0 keeps `under_ma` but not `ma200` itself, so the sec.4 MA200 mask is implemented
    as U-eligibility and the covering implication is MEASURED here rather than asserted.
    ma200 = close.rolling(MA_LEN, min_periods=MA_MINP=150); dd250 rides
    high.rolling(DD_LOOKBACK, min_periods=DD_MINP=200) on the SAME per-name axis. With no
    non-finite price anywhere in the raw store, dd250-finite (bar index >= 199) implies
    ma200-finite (bar index >= 149) exactly.
    """
    nanc = nanh = 0
    checked = 0
    viol = 0
    for t in sample:
        p = RAW_DIR / f"{t}.parquet"
        if not p.exists():
            continue
        d = pd.read_parquet(p, columns=["close", "high"]).sort_index()
        nanc += int(d["close"].isna().sum())
        nanh += int(d["high"].isna().sum())
        c = d["close"].to_numpy(np.float64)
        h = d["high"].to_numpy(np.float64)
        ma = pd.Series(c).rolling(int(w1.MA_LEN), min_periods=int(w1.MA_MINP)).mean() \
            .to_numpy()
        hi = pd.Series(h).rolling(int(w1.DD_LOOKBACK),
                                  min_periods=int(w1.DD_MINP)).max().to_numpy()
        dd_fin = np.isfinite(hi) & (hi > 0)
        checked += int(dd_fin.sum())
        viol += int((dd_fin & ~np.isfinite(ma)).sum())
    return {"tickers_sampled": len(sample), "dd_finite_bars_checked": checked,
            "bars_dd_finite_but_ma200_not": viol,
            "raw_nan_close": nanc, "raw_nan_high": nanh,
            "ma_len_minp": [int(w1.MA_LEN), int(w1.MA_MINP)],
            "dd_lookback_minp": [int(w1.DD_LOOKBACK), int(w1.DD_MINP)],
            "conclusion": ("the sec.4 MA200 / below-gradient measurability mask is "
                           "SATISFIED IDENTICALLY by U-eligibility on this store — "
                           "measured, not assumed")}


# ══════════════════════════════════════════════════════════════════════════════
# STAGE 8 — receipts
# ══════════════════════════════════════════════════════════════════════════════


def build_vintage(w1_sha: str, pb_sha: str, prereg_sha: str) -> dict:
    g = lambda *a: PBMOD._git(*a)                                    # noqa: E731
    v = OrderedDict([
        ("base_sha", g("merge-base", "HEAD", "origin/main")),
        ("build_head_sha", g("rev-parse", "HEAD")),
        ("raw_store_commit", g("log", "-1", "--format=%H", "--",
                               "data/china_stocks_raw")),
        ("members_commit", g("log", "-1", "--format=%H", "--",
                             "data/china_search/members.parquet")),
        ("st_snapshot_commit", g("log", "-1", "--format=%H", "--",
                                 "data/china_st/st_snapshot.parquet")),
        ("zt_pool_commit", g("log", "-1", "--format=%H", "--",
                             "data/china_zt_pool/pool.parquet")),
        ("w1_pin_commit", g("log", "-1", "--format=%H", "--",
                            "research/cn_prophet_audit/washout_onset_w1.py")),
        ("pb_pin_commit", g("log", "-1", "--format=%H", "--",
                            "research/cn_prophet_audit/pb_case_decomposition.py")),
        ("prereg_commit", g("log", "-1", "--format=%H", "--",
                            f"research/cn_prophet_audit/{PREREG_PATH.name}")),
        ("w1_sha256", w1_sha), ("pb_sha256", pb_sha), ("prereg_sha256", prereg_sha),
    ])
    graft = set()
    gd = Path(g("rev-parse", "--git-common-dir"))
    gf = gd if gd.is_absolute() else (REPO / gd)
    sp = gf / "shallow"
    if sp.exists():
        graft = {ln.strip() for ln in sp.read_text().splitlines() if ln.strip()}
    v["repo_is_shallow"] = bool(graft)
    v["shallow_graft_commits"] = sorted(graft)
    hit = sorted(k for k, val in v.items() if isinstance(val, str) and val in graft)
    for k in hit:
        v[k] = f"SHALLOW_BOUNDARY_UNRESOLVED({v[k]})"
    v["stamps_unresolved_by_shallow_graft"] = hit
    v["determinism"] = ("no wall-clock, runtime or hostname enters either receipt; the "
                        "artifact date is a frozen constant and every random stream is "
                        "keyed by a sha256 of its own identity rather than by visit "
                        "order. Two consecutive TZ=UTC full runs at the same commit are "
                        "byte-identical.")
    return v


AMENDMENTS = [
    {"id": "A1",
     "what": "`se_row` is computed as the EXACT closed-form standard deviation of the "
             "fixed-design row bootstrap instead of simulating N_BOOT_ROW = 2000 draws. "
             "N_BOOT_ROW is still used — by the verification control that validates the "
             "closed form.",
     "why": "On the frozen sufficient-statistic table the row bootstrap draws "
            "k_F1(z) ~ Bin(n_F1(z), p1(z)) and k_F0(z) ~ Bin(n_F0(z), p0(z)) "
            "independently across strata, so the standardised excess is a linear "
            "combination of independent binomials and its bootstrap variance is available "
            "in closed form with ZERO Monte Carlo error. Simulating it instead costs "
            "2 x n_strata x 2000 variates per cell — measured at 11.4 s for a single M1 "
            "main cell, i.e. over an hour across the primary and placebo batteries — "
            "which is precisely the whole-matrix cost prereg sec.12 forbids.",
     "risk_controlled_by": "`verify.se_row_closed_form_matches_simulation` runs the "
                           "literal 2000-draw simulation on sampled cells and requires "
                           "agreement inside 5% (the Monte Carlo error of a 2000-draw SE "
                           "is itself ~1.6%); its probe inflates the closed form by 50% "
                           "and must be detected."},
    {"id": "A2",
     "what": "The diagnostic within-stratum permutation is computed for the PRIMARY "
             "horizon (H=10) FIT cells on verdict-eligible boards, in both arms — not for "
             "every cell in the receipt.",
     "why": "prereg sec.6.2 says 'where computed' and stamps the permutation as "
            "DIAGNOSTIC ONLY that NEVER gates. A fixed-margin hypergeometric draw over "
            "M1's stratum count costs ~5.4 s per cell; spending it on cells no gate reads "
            "buys nothing and would push the run past its budget.",
     "risk_controlled_by": "the permutation gates nothing by construction, the scope is "
                           "printed on every table that carries one, and "
                           "`verify.permutation_recomputes_exp` still runs against a real "
                           "computed cell."},
    {"id": "A3",
     "what": "The three cluster bootstraps are computed only for cells whose BOARD passes "
             "the frozen G1 board floor; boards that fail it are DESCRIPTIVE_ONLY and "
             "carry point estimates, honest-N and retention diagnostics but no SE.",
     "why": "A DESCRIPTIVE_ONLY board can receive no verdict under prereg sec.8, so its "
            "z-statistic is unreadable by any gate. The floor is a FROZEN, "
            "pre-registered rule and skipping inference behind it is not a post-hoc "
            "selection.",
     "risk_controlled_by": "the floor result is printed for every board x horizon x arm "
                           "including the ones it excludes, with the episode counts that "
                           "decided it, so the exclusion is auditable rather than "
                           "silent."},
    {"id": "A4",
     "what": "receipt-presentation repairs adjudicated by the round-2 adversarial "
             "review; no verdict, gate or estimator changed",
     "items": [
         "**Per-cell placebo visibility (sec.5, sec.6).** The verdict tables gained "
         "`placebo max|excess| pp` and `placebo max|z|` — the maximum over the three "
         "sec.6.3 shifts for that exact cell — and sec.6 now prints every rejection "
         "individually (shift, footprint, arm, excess, z) instead of only the per-family "
         "count. The family rate was the only placebo number a reader could see, so a "
         "family-level FAILED could not be read down to the cells that caused it.",
         "**Mechanism evidence for the calibration failure (sec.6).** The measured "
         "signature of the 26 rejections is printed and read, so the failure is bounded "
         "rather than left as an unexplained machine fault.",
         "**Headline fairness (sec.5).** The section now states how many gated cells "
         "cleared G1-G5 and that every one was downgraded by the frozen sec.6.3 "
         "consequence, BEFORE it states that no DISCRIMINATOR stands, and records that "
         "sec.14's disposition precondition did not obtain on `main`.",
         "**The SUGGESTIVE bar inherits the miscalibration (sec.6, sec.12).** Stated "
         "explicitly: inside a family that failed calibration at the G2 bar, the |z| >= "
         "1.96 bar is at least as uncalibrated.",
         "**Lead-curve exclusions re-scoped (sec.8).** The per-lead exclusion counts are "
         "computed inside each (board, split) cohort. The identical global series had "
         "been printed under all four tables, whose case and control sets are already "
         "per (board, split).",
         "**Constant-cohort curves printed (sec.8).** They existed only in the JSON; the "
         "six eligible footprints now carry a printed constant-cohort table beneath each "
         "board x split full-cohort table. The DD-family absence statement is unchanged.",
         "**Matched-N honesty in the lead curves (sec.8).** The `cases` / `controls` "
         "columns were DD20's numbers standing in for every footprint; they are relabelled "
         "`eligible cases (cohort)` / `eligible controls (cohort)`, computed for the "
         "cohort itself, with the per-footprint matched N named in the JSON and one "
         "worked example of the gap printed.",
         "**R4's scope named (sec.10).** The reading note now names the exactly two cells "
         "its convention moves, the direction of the move, and their H=5 fragility.",
         "**Placebo subsample shrinkage disclosed (sec.6).** The shifted panel loses rows "
         "as S grows (a name shorter than S vanishes); the series is printed and its "
         "direction stated.",
         "**Per-F-class censoring asymmetry printed (sec.2).** The counts were in the "
         "JSON only; the widest imbalances are now printed with the JSON pointer kept.",
         "**The sec.2 censoring-magnitude sentence corrected.** 'The values above are of "
         "order several per cent' described neither the cells under the 1% trigger nor "
         "the spread of the ones over it; the measured distribution replaces it.",
         "**Survivorship stamp attributed (footer).** The kept-name count for THIS run is "
         "printed, and W-P0's percentages are attributed to W-P0's own store snapshot "
         "rather than reading as this run's N.",
         "**Two-speed READING paragraph (sec.8).** A descriptive reading of the printed "
         "curves — it gates nothing, adds no statistic, and does not cross the lead-21 "
         "composition break.",
     ],
     "why": "The round-2 adversarial review found the receipt under-reporting its own "
            "evidence rather than mis-computing it: per-cell placebo behaviour was "
            "aggregated away behind four family rates, the null was stated in an order "
            "that read as absence of structure, three bookkeeping series were printed at "
            "the wrong scope or under the wrong label, and several quantities that "
            "existed in the JSON were never surfaced. Each item is a presentation or "
            "bookkeeping repair to what the receipt SAYS about numbers it already "
            "computed.",
     "risk_controlled_by": "nothing in the statistical machinery is touched: no stratum, "
                           "gate, floor, SE, placebo draw or verdict rule moved, the "
                           "frozen sec.6.3 consequence sentence is printed verbatim and "
                           "applied as frozen, and the corrected counts are the ones this "
                           "amendment names. The run is byte-deterministic, so the whole "
                           "pass is auditable as a diff against the pre-A4 build in which "
                           "every verdict, gate glyph, excess, z, Holm p and honest-N is "
                           "identical. (The `A4 GUARD` string in the instrument's "
                           "provenance check is prereg sec.11.16's own A4/A5 label and is "
                           "unrelated to this amendment.)"},
]

READING_NOTES = [
    {"id": "R1",
     "point": "prereg sec.4 freezes the reported gradient families at FOUR "
              "(`below_band`, `dur_band`, `sect35_band`, `volz_band`), while sec.5.3 "
              "names 'the depth gradient and the duration gradient' when stating the "
              "DD/duration ONE-SERIES carve-out.",
     "reading": "sec.4's explicit enumeration governs what is REPORTED; sec.5.3 is a rule "
                "about which strata a family may be evaluated inside, and it applies to "
                "whatever is reported. `dur_band` is the DD/duration-family gradient and "
                "therefore drops BOTH M1 dd factors. The sec.5.3-named DEPTH gradient "
                "(`dd_band`) is computed with the same carve-out and emitted to the JSON "
                "under `depth_gradient_reference` so the numbers exist, but it is absent "
                "from every MD gradient table because sec.4 froze the reported list at "
                "four.",
     "materiality": "NIL for every verdict — gradients receive no verdicts under sec.5.5 "
                    "and are excluded from the constant-cohort curve under sec.9 either "
                    "way. Flagged here so the reading is adjudicable rather than silent."},
    {"id": "R2",
     "point": "prereg sec.4 lists the MA200 measurability mask as `isfinite(ma200)`, but "
              "W-P0 keeps `under_ma` and does not export `ma200`.",
     "reading": "The mask is implemented as U-eligibility and the covering implication is "
                "MEASURED, not assumed: ma200 rides min_periods = 150 and dd250 rides "
                "min_periods = 200 on the SAME per-name bar axis, and the raw store "
                "carries no non-finite close or high, so dd250-finite implies "
                "ma200-finite exactly. `verify.missing_not_false.ma200_covering_lemma` "
                "reports the measurement.",
     "materiality": "NIL — the sec.4 mask is satisfied identically, not approximated."},
    {"id": "R3",
     "point": "prereg sec.9 does not say which split a lead-curve case anchor belongs to.",
     "reading": "The ANCHOR's own split. Controls are same-session rows, so cases and "
                "controls share a split by construction and the comparison is never "
                "across a split boundary.",
     "materiality": "Stated on the curves themselves."},
    {"id": "R4",
     "point": "prereg sec.8 defines SUGGESTIVE as 'G1 met, FIT |z| >= 1.96, but fails "
              ">= 1 of G3/G4/G5' and NULL as 'G1 met and neither'. A cell with "
              "1.96 <= |z| < 2.81 that passes G3, G4 and G5 fits neither sentence "
              "literally: it fails G2, so it is not a DISCRIMINATOR, but it fails none of "
              "G3/G4/G5.",
     "reading": "SUGGESTIVE. The SUGGESTIVE bar in the frozen text is |z| >= 1.96 and "
                "this cell clears it; calling it NULL would contradict NULL's own "
                "definition ('neither'), since it is not a DISCRIMINATOR and it is above "
                "the SUGGESTIVE bar. Implemented as: DISCRIMINATOR iff every gate passes, "
                "else SUGGESTIVE iff |z| >= 1.96, else NULL.",
     "materiality": "Affects only cells in the 1.96-2.81 band that pass all of "
                    "G3/G4/G5; the gate columns are printed per cell so any such row can "
                    "be re-read under the other convention."},
]

ORE_LEDGER = [
    "MARKET-TIMING / REGIME FORMS OF THE SAME FAMILIES. Every stratum here is "
    "within-session, so a 'boards cluster when the whole tape is washed out' mechanism is "
    "removed BY CONSTRUCTION. That form is untested here and a null here is not evidence "
    "against it. It is the single largest reserved question and it needs its own "
    "preregistration.",
    "CONJUNCTIONS. P-D owns stacking; W-P0's S6 conjunction masks are deliberately not "
    "re-read here and no pair, triple or grid search of the eight booleans exists.",
    "DEEPER LAWFUL DATA (P-C). Auction demand, seal-time structure and chip-concentration "
    "shifts cannot enter this instrument because the histories do not exist in this "
    "checkout.",
    "LIQUIDITY / SIZE MATCHING. Omitted with reason: on a back-adjusted store, "
    "cross-name turnover ranks inherit per-name adjustment factors and are not a lawful "
    "liquidity measure. Full-A `daily_basic` is the future fix; the vol-decile stratum is "
    "the only wildness control M0 claims.",
    "THE EXACT LEGAL-LIMIT PLANE. Untouched. This is a tolerant-detector cohort on a "
    "back-adjusted store and the reopen chain is unmodified "
    "(DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT).",
    "THE CENSORING MECHANISM ITSELF. Broken windows are counted, bounded (Manski) and "
    "printed, never modelled. A suspension-aware forward-chain model is reserved.",
]

DOES_NOT_ESTABLISH = [
    "WITHIN-SESSION CROSS-SECTIONAL SCOPE, WHICH BOUNDS EVERY VERDICT HERE. All strata "
    "are within-session, so each verdict answers only: does this footprint separate names "
    "on the SAME tape on the SAME day. A NULL says nothing about market-wide or "
    "regime-timing information in the same family — a 'boards cluster when the whole tape "
    "is washed out' mechanism is removed by the session stratum by construction. "
    "Instrument verdicts are not market verdicts.",
    "NO PRODUCTION USE, NO RANKER, NO THRESHOLD. Nothing here ranks names, tunes a "
    "threshold, sizes, gates, alerts or trades. There is no P-B2 production consumer and "
    "none is proposed; the sec.10 flagged-set diagnostics are descriptive and end inside "
    "this receipt (DNR:KILL-OUTCOME-AUDITION respected).",
    "NO CAUSALITY. A matched excess is a statement about two conditional rates inside the "
    "same session and volatility stratum. It is not evidence that the footprint produced "
    "the board, nor that either would recur.",
    "NO EXPECTANCY, NO RETURN, NO ENTRY BOOK. The outcome is a BOOLEAN — a first tolerant "
    "limit-up close inside H sessions. No price, return, slippage or fill is modelled, "
    "and a precision figure is not a strategy result.",
    "NOT A CONTINUATION OR AN INTRADAY CLAIM. The label is a FIRST board out of a cold "
    "state. An intraday touch, a generic big day and a continuation board after a prior "
    "board are different physical objects and none of them is the label.",
    "SURVIVORS ONLY, LARGE-CAP SLICE. W-P0's curated universe: delisted names are absent, "
    "so every rate is measured on names that lived. Nothing supports a claim about small "
    "caps or the delisted in either direction.",
    "BACK-ADJUSTED BASIS. A tolerant-detector cohort, not an exchange-exact legal-limit "
    "cohort. The residual is MEASURED in verify.detector_vs_zt_pool, not assumed away.",
    "CURRENT SECTOR MEMBERSHIP applied to 15 years of history — the sector-washout "
    "footprint is not a point-in-time statistic and eras are not comparable on it without "
    "that qualifier.",
    "THE PERMUTATION IS NOT A P-VALUE YOU MAY QUOTE. It is stamped anticonservative and "
    "gates nothing: one episode contributes ~10 positive anchor rows, so a "
    "row-exchangeable null understates the null SD by roughly sqrt(10).",
    "A NORMAL APPROXIMATION IS DOING WORK. The gates read z on a CGM two-way clustered SE "
    "under the normal approximation, stamped as such. The sec.6.3 placebo calibration is "
    "the empirical guard on that approximation, and a family that fails it has no "
    "DISCRIMINATOR.",
    "RETAINED SAMPLES ARE NOT THE FULL SAMPLE. Contrast-bearing strata are a non-random, "
    "density-biased subset; the retained fractions and their composition are printed on "
    "every cell, and a cell retaining under half of its F=TRUE positive episodes is "
    "NOT_EVALUABLE rather than a verdict.",
    "VZ AND CB ARE COINCIDENT INDICATORS, NOT PRECURSORS. Median arming leads of 1 and 5 "
    "sessions (P-B sec.5). Any verdict on them carries that stamp and neither is ever "
    "described as an early precursor.",
    "NOTHING ABOUT THE WITHDRAWN EARLIER-WAVE CONSTRUCTIONS. No number and no artifact "
    "from them is cited (grep-verified in verify.stop_ship_reference_scan).",
    "A SUGGESTIVE INSIDE AN UNCALIBRATED FAMILY IS NOT A WEAKER VERDICT. Where a (board, "
    "horizon) family failed its sec.6.3 placebo calibration at the G2 bar, the SUGGESTIVE "
    "bar (|z| >= 1.96) is a LOWER bar on the same statistic and is therefore at least as "
    "uncalibrated. Nothing in this receipt supports reading a SUGGESTIVE in a failed "
    "family as a small, safe version of a DISCRIMINATOR.",
]


def _cap(t: str) -> str:
    """First letter only — `str.capitalize()` would lowercase W-P0, DISCRIMINATOR, G2."""
    return (t[:1].upper() + t[1:]) if t else t


def _f(x, nd=2, plus=False):
    if x is None:
        return "—"
    s = f"{x:+.{nd}f}" if plus else f"{x:.{nd}f}"
    return s


def _placebo_extremes(p: dict, H, arm: str, board: str, fk: str):
    """A4 — the worst placebo behaviour of ONE cell across the sec.6.3 shifts.

    Returns (max |matched excess| pp, max |z|) over S in PLACEBO_SHIFTS for exactly this
    (horizon, arm, board, footprint), or (None, None) where no shift computed it. The
    family rejection rate is an average over 48 such cells and cannot be read down to
    them; this is the per-cell view the verdict table needs.
    """
    ex, zz = [], []
    for s in p["placebo"].get("shifts", PLACEBO_SHIFTS):
        c = p["placebo"]["per_shift"].get(str(s), {}).get(f"H{H}|{arm}|{board}|{fk}")
        if not c:
            continue
        e = c.get("estimate", {}).get("matched_excess_pp")
        z = c.get("inference", {}).get("z_2way")
        if e is not None:
            ex.append(abs(float(e)))
        if z is not None:
            zz.append(abs(float(z)))
    return (max(ex) if ex else None), (max(zz) if zz else None)


def _r4_population(p: dict) -> list:
    """A4 — the cells reading note R4's convention actually moves: G1 met, FIT |z| in
    [1.96, G2_Z), and G3/G4/G5 all passed. Computed, never asserted."""
    out = []
    for k, v in p["verdicts"].items():
        g, z = v["gates"], v.get("fit_z_2way")
        if z is None or not g.get("G1_footprint"):
            continue
        if 1.96 <= abs(float(z)) < G2_Z and all(
                g.get(x) for x in ("G3_thinned_sign", "G4_era_sign_2of3", "G5_holdout")):
            out.append((k, v))
    return out


def build_md(p: dict, pb) -> str:
    T = pb.md_table
    L, A = [], None
    A = L.append
    A(f"# P-B2 — matched precursor discrimination ({p['artifact_date']})")
    A("")
    A(f"Authority: `{p['authority']}`. Tier: {p['tier']}")
    A("")
    A("**The pre-registration is the contract and it was frozen before this run.** "
      f"`{PREREG_PATH.name}` (sha256 `{p['pin']['prereg_sha256'][:16]}…`) was committed "
      "before the first outcome run of this instrument; the commit order in history is "
      "the proof. Every definition, stratum, floor and gate below is read from it. "
      f"Deviations are numbered amendments (§10) — there are {len(AMENDMENTS)}.")
    A("")
    A(f"Governing ruling: `{p['governing_ruling']}`. Program home: `{PROGRAM_HOME}`. "
      "Pinned definitions: `washout_onset_w1.py` (W-P0) and `pb_case_decomposition.py` "
      "(P-B), **imported — not re-derived**.")
    A("")
    A("> **Estimand scope, which bounds every verdict below.** All strata are "
      "within-session, so every P-B2 verdict is a **within-session cross-sectional** "
      "statement: does the footprint separate names on the same tape on the same day. A "
      "NULL here says nothing about market-wide or regime-timing information in the same "
      "family. Instrument verdicts are not market verdicts.")
    A("")
    A("---")
    A("")

    # §1
    fp = p["footprint_plane"]
    A("## 1. What was read")
    A("")
    A(f"One store, one panel: `data/china_stocks_raw` through W-P0's own `build_panel()` "
      f"+ `attach_conditioners(panel, None)` over W-P0's own window "
      f"**{fp['window'][0]} → {fp['window'][1]}** — {fp['panel_rows']:,} live bars, "
      f"{fp['panel_names']:,} names, {fp['panel_sessions']:,} sessions. No third "
      "implementation of any definition exists.")
    A("")
    A("**Anchor universes** (a row = one (ticker, session) panel bar). Honest-N first, "
      "always.")
    A("")
    rows = []
    for u in ("U0", "U1"):
        for b in BOARD_ORDER:
            r = [u, b]
            for sg in SPLIT_GROUPS:
                c = p["universes"][f"{u}|{b}|{sg}"]
                r.append(f"{c['sessions']} sess / {c['names']} nm / {c['rows']:,} r")
            rows.append(r)
    A(T(["universe", "board", "FIT", "HOLDOUT", "AUDIT"], rows))
    A("")
    A(f"U0 = cold ∧ split assigned ∧ dd250 finite. U1 = U0 ∧ dd250 ≤ −20%. Cold rows "
      f"excluded for carrying no split (W-P0's 20-session embargo): "
      f"**{p['universe_exclusions']['cold_rows_without_a_split']:,}**; excluded for an "
      f"unmeasurable drawdown (`na` band, under 200 bars of history): "
      f"**{p['universe_exclusions']['cold_rows_with_dd_na']:,}**. Neither is silently "
      "folded anywhere.")
    A("")

    # §2 labels
    A("## 2. Labels, censoring, and what censoring is never allowed to become")
    A("")
    A("POSITIVE = `fb_H`. NEGATIVE = `win_ok_H` ∧ ¬`fb_H`. CENSORED = ¬`win_ok_H` — "
      "**censored rows enter neither class and are never scored as misses.** The "
      "partition is exact everywhere (`verify.censoring_partition`).")
    A("")
    rows = []
    bw = []
    for H in HORIZONS:
        for b in BOARD_ORDER:
            for sg in ("FIT", "HOLDOUT"):
                k = f"H{H}|U1|{b}|{sg}"
                c = p["labels"].get(k)
                if not c:
                    continue
                bw.append((f"H{H} {b} {sg}", float(c["broken_window_pct_of_positives"]),
                           sg))
                rows.append([H, b, sg, c["positive_episodes"], c["sessions"],
                             f"{c['positives']:,}", f"{c['negatives']:,}",
                             f"{c['censored']:,}", "yes" if c["partition_exact"] else "NO",
                             f"{c['board_visible_inside_broken_window']:,}",
                             f"{c['broken_window_pct_of_positives']}%"])
    A(T(["H", "board", "split", "pos episodes", "sessions", "positives", "negatives",
         "censored", "partition exact", "board visible in broken window",
         "% of positives"], rows))
    A("")
    under = [x for x in bw if x[1] <= 1.0]
    over = sorted((x for x in bw if x[1] > 1.0), key=lambda t: -t[1])
    top = [x for x in over if x[1] >= 5.0]
    A("**The censoring diagnostic must be discussed, and here it is.** The prereg "
      "requires that if the count of rows where a board is visible inside a broken window "
      f"exceeds 1% of positives on any board, the receipt discuss it. **{len(under)} of "
      f"the {len(bw)} board × split cells above sit under that 1% trigger** ("
      + ", ".join(f"{n} {v}%" for n, v, _s in under)
      + f"); the other {len(over)} run from {min(x[1] for x in over)}% to "
      f"{max(x[1] for x in over)}% and are the cells the prereg requires discussed. The "
      f"{len(top)} largest are "
      + ", ".join(f"{n} {v}%" for n, v, _s in top)
      + (" — every one of them a FIT cell, where the suspension-broken windows are "
         "denser" if top and all(s == "FIT" for _n, _v, s in top) else "")
      + ". The mechanism is W-P0's "
      "closure-tolerant completeness rule — a row whose forward chain breaks (a "
      "suspension gap over 21 calendar days) fails `win_ok_H` even when a tolerant board "
      "is visible inside the nominal window. Those rows are **censored, not negative**, "
      "which is the conservative direction for a discrimination study: they are removed "
      "from both classes rather than counted as misses. Because the removal is not "
      "guaranteed to be balanced across F-classes, the per-F-class censored counts are in "
      "the JSON for every footprint, and every DISCRIMINATOR carries the coarse Manski "
      "bound below.")
    A("")

    # F10 — the per-F-class asymmetry itself, not only its existence
    fam_k = f"H{H_PRIMARY}|M1|{p['verdict_summary']['verdict_boards'][0]}|FIT"
    asym = []
    for fk in FKEYS_ORDER:
        c = p["primary"].get(f"{fam_k}|{fk}")
        if not c or c.get("status") == "NOT_EVALUABLE":
            continue
        ct, cf = c["censored_rows_F_true"], c["censored_rows_F_false"]
        nt = ct + c["honest_n_F_true"]["rows"]
        nf = cf + c["honest_n_F_false"]["rows"]
        if not nt or not nf:
            continue
        pt, pf = 100.0 * ct / nt, 100.0 * cf / nf
        asym.append((pb.FSHORT[fk], pt, pf, pt / pf if pf else None))
    if asym:
        hi = max(asym, key=lambda t: t[3])
        lo = min(asym, key=lambda t: t[3])
        A("**How unbalanced that removal actually is.** Censoring is not guaranteed even "
          f"across F-classes, so the measurement is printed rather than only stored. In "
          f"the primary family (`{fam_k}`), as each class's own censored share, the widest "
          f"imbalance is **{hi[0]}** ({hi[1]:.2f}% of F=TRUE rows vs {hi[2]:.2f}% of "
          f"F=FALSE, ratio {hi[3]:.2f}) and the widest in the other direction is "
          f"**{lo[0]}** (ratio {lo[3]:.2f}); every footprint in that family:")
        A("")
        A(T(["footprint", "censored share of F=TRUE rows", "censored share of F=FALSE "
             "rows", "ratio T/F"],
            [[n, f"{a:.2f}%", f"{b_:.2f}%", f"{r:.2f}"] for n, a, b_, r in asym]))
        A("")
        A("The same counts for every other cell — every footprint, board, split, arm and "
          "horizon, in the primary and placebo batteries alike — are in the JSON under "
          "`primary.*.censored_rows_F_true` / `censored_rows_F_false` beside each cell's "
          "`honest_n_F_true` / `honest_n_F_false`. No DISCRIMINATOR stands here, so no "
          "Manski bound was triggered; the asymmetry is printed anyway because it bounds "
          "how a future verdict on this substrate would have to be read.")
        A("")

    ov = [(k, v) for k, v in p["episode_overlap_with_pb_cohort"].items()
          if not k.startswith("_")]
    A("**Episode identity cross-check.** A positive row's episode key is its realised "
      "board. By W-P0's ladder-0 lemma every such board should also be a cold-eve first "
      "board in P-B's own `extract_events` cohort; the overlap is printed, not asserted — "
      + ", ".join(f"`{k}` {v['overlap_pct']}%" for k, v in ov
                  if k.startswith(f"H{H_PRIMARY}|U1")) + ". "
      + _cap(p["episode_overlap_with_pb_cohort"]["_rule"]))
    A("")

    # §3 measurability
    A("## 3. Measurability — unmeasurable is never FALSE")
    A("")
    A("P-B's boolean derivation codes missing as FALSE. Leaving that in the F=FALSE class "
      "would estimate the counterfactual from a mixture of measured negatives and "
      "unmeasurables, so a row enters footprint F's analysis only if F is measurable on "
      "it.")
    A("")
    rows = [[pb.FSHORT[k], k, MEASURABILITY[k],
             f"{p['measurability']['rows_excluded'][k]:,}",
             f"{p['measurability']['pct_excluded'][k]}%"] for k in FKEYS_ORDER]
    A(T(["code", "footprint", "mask", "U0 rows excluded", "% of U0"], rows))
    A("")
    lem = p["measurability"]["ma200_covering_lemma"]
    A(f"CONF and CB are treated measurable on all U rows — a **declared approximation** "
      f"(prereg §4): their indicator warm-up is covered by the 200-bar dd-finiteness "
      f"floor. MA200 and the below-gradient use the same covering, and it is *measured* "
      f"rather than assumed: across {lem['tickers_sampled']} sampled names, "
      f"{lem['dd_finite_bars_checked']:,} dd-finite bars carried "
      f"**{lem['bars_dd_finite_but_ma200_not']}** bars with a non-finite 200DMA "
      f"(raw store non-finite closes: {lem['raw_nan_close']}, highs: "
      f"{lem['raw_nan_high']}). See reading note R2.")
    A("")

    # §4 board floors
    A("## 4. G1 board floors — which boards can receive a verdict at all")
    A("")
    rows = []
    for H in HORIZONS:
        for arm in ARMS:
            for b in BOARD_ORDER:
                f = p["board_floors"][f"H{H}|{arm}|{b}"]
                rows.append([H, arm, b, f["fit_positive_episodes"],
                             f["holdout_positive_episodes"], f["status"]])
    A(T(["H", "arm", "board", "FIT pos episodes", "HOLDOUT pos episodes", "status"], rows))
    A("")
    A(f"Floors: ≥ {G1_BOARD_FIT_EPISODES} distinct positive episodes in FIT **and** ≥ "
      f"{G1_BOARD_HOLDOUT_EPISODES} in HOLDOUT. `chinext10` is DESCRIPTIVE_ONLY **by "
      "construction** — the board key exists only before 2020-08-24, so it has zero "
      "HOLDOUT rows, forever. The prereg's frozen expectation was that `star` fails the "
      "FIT floor and the realistic gated ceiling is ≤ 8 footprints × 2 boards × 2 "
      f"horizons = 32; the measured outcome is "
      f"**{p['verdict_summary']['gated_cells']} gated cells** on "
      f"{', '.join(p['verdict_summary']['verdict_boards'])}.")
    A("")

    # §5 verdicts
    A("## 5. Verdicts")
    A("")
    A("**DISCRIMINATOR** requires G1 floors ∧ G2 (FIT |z₂ᵥᵥ| ≥ 2.81) ∧ G3 (thinned-anchor "
      "sign) ∧ G4 (sign agrees in ≥ ⅔ of measurable FIT eras) ∧ G5 (HOLDOUT same sign and "
      "one-sided z ≥ 1.28). **SUGGESTIVE** = G1 met, |z| ≥ 1.96, ≥ 1 of G3/G4/G5 failed. "
      "**NULL** = G1 met and neither. A dead feature prints **NOT_EVALUABLE**, never NULL.")
    A("")
    for H in HORIZONS:
        A(f"### H = {H} {'(primary)' if H == H_PRIMARY else '(secondary)'}")
        A("")
        rows = []
        for b in p["verdict_summary"]["verdict_boards"]:
            for fk in FKEYS_ORDER:
                v = p["verdicts"].get(f"H{H}|{b}|{fk}")
                if not v:
                    continue
                g = v["gates"]
                gs = "".join(("✓" if g.get(k) else "·") for k in
                             ("G1_footprint", "G2_fit_z_ge_2.81", "G3_thinned_sign",
                              "G4_era_sign_2of3", "G5_holdout"))
                lab = pb.FSHORT[fk] + (f" ({v['band_local']})" if v.get("band_local")
                                       else "")
                pex, pz = _placebo_extremes(p, H, v["arm"], b, fk)
                rows.append([b, lab, v["arm"], v["honest_n"], _f(v.get("fit_excess_pp"),
                                                                 3, True),
                             _f(v.get("fit_z_2way"), 2), _f(v.get("holdout_excess_pp"),
                                                            3, True),
                             _f(v.get("holdout_z_2way"), 2), gs, v["verdict"],
                             _f(v.get("holm_p"), 4) if v.get("holm_p") is not None
                             else "—", _f(pex, 3), _f(pz, 2)])
        A(T(["board", "footprint", "arm", "honest-N (F=TRUE, retained)",
             "FIT excess pp", "FIT z₂ᵥᵥ", "HOLD excess pp", "HOLD z", "G1..G5", "verdict",
             "Holm p (ref)", "placebo max\\|excess\\| pp", "placebo max\\|z\\|"], rows))
        A("")
    A("The two placebo columns are the maximum over the three §6.3 shifts (S ∈ {250, 500, "
      "1000}) **for that exact cell** — the same footprint, arm, board and horizon, on the "
      "shifted panel where no alignment with outcomes survives. They are printed beside "
      "each verdict because a family-level calibration rate cannot tell a reader which "
      "cells carried it; `—` means the placebo cell was not computed there. Read the DD "
      "rows against their own FIT columns.")
    A("")
    A("**Coincident-indicator stamps, which travel with every verdict on them.** "
      + " ".join(f"**{pb.FSHORT[k]}** — {v}" for k, v in COINCIDENT_STAMP.items()))
    A("")
    vz = [(k, v) for k, v in p["vz_no_vol_stratum_sensitivity"].items()
          if not k.startswith("_")]
    if vz:
        A("**VZ no-vol-stratum sensitivity** (prereg §5.3 — VZ keeps the vol decile; this "
          "is printed beside it, and the verdict stays on the vol-stratified arm): "
          + ", ".join(
              f"`{k}` {_f(v.get('estimate', {}).get('matched_excess_pp'), 3, True)} pp"
              for k, v in vz) + ".")
        A("")
    A("Gate glyphs are `G1_footprint · G2 · G3 · G4 · G5`; `✓` passed, `·` failed. A "
      "`(dX)` beside a footprint is the **band-local** label — over 80% of the retained "
      "F=TRUE mass sits in that single depth band, which the prereg predicted for MA200 "
      "and SECT and which the verdict must say out loud. Holm-adjusted p is a reference "
      "column inside each (board, horizon) family and changes no gate.")
    A("")
    if p["verdict_summary"]["discriminators"]:
        A("**Manski robustness on every DISCRIMINATOR** — the matched excess recomputed "
          "with all censored F=TRUE rows counted positive, then all counted negative.")
        A("")
        rows = [[k.replace("|", " · "),        # a bare '|' would end the markdown cell
                 _f(v["excess_pp"], 3, True), _f(v["bounds"]
                                                 ["censored_F_true_all_positive"],
                                                 3, True),
                 _f(v["bounds"]["censored_F_true_all_negative"], 3, True),
                 "yes" if v["sign_survives"] else "**NO**"]
                for k, v in p["manski"].items()]
        A(T(["cell", "point excess pp", "all censored F=TRUE positive",
             "all censored F=TRUE negative", "sign survives"], rows))
        A("")
    else:
        gk = ("G1_footprint", "G2_fit_z_ge_2.81", "G3_thinned_sign", "G4_era_sign_2of3",
              "G5_holdout")
        cleared = [(k, v) for k, v in p["verdicts"].items()
                   if v["verdict"] != "NOT_EVALUABLE" and all(v["gates"].get(x)
                                                              for x in gk)]
        by_hb: "OrderedDict[str, list]" = OrderedDict()
        for k, v in cleared:
            by_hb.setdefault(f"H{v['horizon']} {v['board']}", []).append(
                pb.FSHORT[v["footprint"]])
        capped = sum(1 for _k, v in cleared if v["verdict"] != "DISCRIMINATOR")
        A(f"**{len(cleared)} of the {p['verdict_summary']['gated_cells']} gated cells "
          f"cleared G1–G5** — "
          + "; ".join(f"{h} {'/'.join(f_)}" for h, f_ in by_hb.items())
          + (" — and **every one of them was downgraded by the frozen §6.3 family "
             "consequence**" if capped == len(cleared) else
             f" — and **{capped} of those {len(cleared)} were downgraded by the frozen "
             "§6.3 family consequence**")
          + ", which is why **no DISCRIMINATOR verdict stands anywhere**. No Manski bound "
          "is therefore required; a null is a valid ship (prereg §14) and it ships as "
          "one.")
        A("")
        mb = p["verdict_summary"]["verdict_boards"][0]
        per_h = {H: sum(1 for _k, v in cleared
                        if v["board"] == mb and v["horizon"] == H) for H in HORIZONS}
        A("**What that null is, stated precisely.** prereg §14 frames the disposition on "
          "the precondition that *the footprints mostly fail these gates against matched "
          f"controls*. That precondition did **not** obtain on `{mb}`: "
          + " and ".join(f"{per_h[H]} of the {len(FKEYS_ORDER)} footprints at H={H}"
                         for H in HORIZONS)
          + " cleared every gate there, at honest-N in the millions of rows and thousands "
          "of episodes. What removed those verdicts was the §6.3 calibration failure of "
          "the inference machinery in the same families — so the shipped null is a "
          "**calibration-governed null, not a measured absence of structure**. §6 states "
          "what the calibration failure is evidence of and what it is not; the "
          "consequence is applied as frozen either way.")
        A("")

    # §6 placebo
    A("## 6. Placebo-feature calibration — the measured false-positive guard")
    A("")
    A("The entire footprint panel is shifted forward by S ∈ {250, 500, 1000} sessions "
      "along each name's own axis — within-name persistence, cross-sectional prevalence "
      "and session structure all survive; only the alignment with outcomes is broken — "
      "and the full primary battery is re-run per shift.")
    A("")
    rows = [[k.replace("|", " · "), v["tested"], v["rejected"],
             f"{100 * v['rejection_rate']:.2f}%" if v["rejection_rate"] is not None
             else "—",
             f"{100 * v['bar']:.1f}%",
             "**FAILED**" if v["calibration_failed"] else "passed"]
            for k, v in p["placebo"]["family_calibration"].items()]
    A(T(["family (board · H)", "cells tested", "rejections at the G2 bar",
         "realised rate",
         "fail bar (5× nominal)", "calibration"], rows))
    A("")

    # F1 — the rejections themselves, not only their count
    A("**Every rejection, individually.** A family rate is an average over its cells; "
      "these are the cells that produced it. `excess pp` is the matched excess measured "
      "on the SHIFTED panel, where no alignment with outcomes is supposed to survive.")
    A("")
    rows = []
    for fam, v in p["placebo"]["family_calibration"].items():
        fb_, fh_ = fam.split("|")
        for r in v.get("rejections", []):
            sh, arm, fk, _zs = r.split("|")
            s = sh.replace("shift", "")
            c = p["placebo"]["per_shift"].get(s, {}).get(f"{fh_}|{arm}|{fb_}|{fk}", {})
            rows.append([fam.replace("|", " · "), s, pb.FSHORT[fk], arm,
                         _f(c.get("estimate", {}).get("matched_excess_pp"), 3, True),
                         _f(c.get("inference", {}).get("z_2way"), 2)])
    A(T(["family (board · H)", "shift S", "footprint", "arm", "excess pp", "z₂ᵥᵥ"], rows))
    A("")

    # F2 — the measured signature of the failure, and what it does and does not mean
    dd_fam = ("dd_le_m20", "dd_le_m35")
    n_rej = n_pos = n_dd = nd_tested = nd_rej = 0
    for _s, cells in p["placebo"]["per_shift"].items():
        for key, c in cells.items():
            fk = key.split("|")[3]
            z = c.get("inference", {}).get("z_2way")
            if z is None:
                continue
            hit = abs(float(z)) >= G2_Z
            if fk not in dd_fam:
                nd_tested += 1
                nd_rej += int(hit)
            if hit:
                n_rej += 1
                n_dd += int(fk in dd_fam)
                e = c.get("estimate", {}).get("matched_excess_pp")
                n_pos += int(e is not None and float(e) > 0)
    mb = p["verdict_summary"]["verdict_boards"][0]
    shifts = p["placebo"].get("shifts", list(PLACEBO_SHIFTS))

    def _plseries(fk):
        arm = VERDICT_ARM[fk]
        real = (p["primary"].get(f"H{H_PRIMARY}|{arm}|{mb}|FIT|{fk}", {})
                .get("estimate", {}).get("matched_excess_pp"))
        vals = [(p["placebo"]["per_shift"].get(str(s), {})
                 .get(f"H{H_PRIMARY}|{arm}|{mb}|{fk}", {})
                 .get("estimate", {}).get("matched_excess_pp")) for s in shifts]
        return real, vals
    dd20_real, dd20_pl = _plseries("dd_le_m20")
    dd35_real, dd35_pl = _plseries("dd_le_m35")
    dd35_share = [100.0 * v / dd35_real for v in dd35_pl
                  if v is not None and dd35_real] or [0.0]
    plant = p["verify"]["checks"]["placebo_sensitivity"]["detail"]
    pz = plant["shifted_planted_z"]
    A("**What the failure is, measured.** The signature is not the shape of a broken "
      f"standard error. All **{n_pos} of the {n_rej}** placebo rejections are "
      f"**positive-signed**, and **{n_dd} of {n_rej}** sit in the DD family "
      f"(`{pb.FSHORT['dd_le_m20']}` / `{pb.FSHORT['dd_le_m35']}`); across every non-DD "
      f"footprint the realised rejection rate is **{nd_rej}/{nd_tested} = "
      f"{100.0 * nd_rej / max(nd_tested, 1):.2f}%**, inside the "
      f"{100 * PLACEBO_FAIL_MULT * PLACEBO_NOMINAL:.1f}% bar. The magnitudes say the same "
      f"thing: on `{mb}` at H={H_PRIMARY}, {pb.FSHORT['dd_le_m20']}'s placebo excess "
      f"({', '.join(_f(v, 3, True) for v in dd20_pl)} pp at S = "
      f"{', '.join(str(s) for s in shifts)}) **reproduces its real excess** "
      f"({_f(dd20_real, 3, True)} pp) essentially in full, and "
      f"{pb.FSHORT['dd_le_m35']}'s reproduces "
      f"{min(dd35_share):.0f}–{max(dd35_share):.0f}% of its real "
      f"{_f(dd35_real, 3, True)} pp. And the sensitivity control agrees: a label planted "
      f"EQUAL TO THE OUTCOME prints z = {_f(plant['unshifted_planted_z'], 2)} unshifted "
      "and still carries z = "
      + " / ".join(_f(pz.get(str(s)), 3) for s in shifts)
      + f" **after** shifting — non-zero residual leak, under the soft ceiling "
      f"max(G2 = {G2_Z}, |z₀|/10) = {_f(plant['calibration_ceiling'], 2)} the check is "
      "measured against.")
    A("")
    A("**The reading.** That is the signature of **residual feature–outcome alignment for "
      "multi-year persistent states**: `dd250` at t−250, t−500 and even t−1000 is still "
      "correlated with `dd250` at t on the same name, so shifting the tape does not "
      "break the alignment it is designed to break. For a persistent feature the placebo "
      "**null itself is false**, and a rejection under it is not a false positive in the "
      "sense the guard assumes. What this is **not**: it is not evidence of a symmetric "
      "standard-error failure — a broken SE would reject in both signs and across "
      "footprints, and neither happened — and on the non-DD footprints the same machinery "
      "measured calibrated at nominal. That bounds the failure; it does not repair it, "
      "and it changes no verdict here.")
    A("")

    # F4 — the SUGGESTIVE bar inherits the miscalibration
    A(f"**The SUGGESTIVE bar inherits this.** Inside a family that failed calibration at "
      f"the G2 bar (|z| ≥ {G2_Z}), the SUGGESTIVE bar (|z| ≥ 1.96) is a **lower** bar on "
      "the same statistic and is therefore **at least as uncalibrated**. Every SUGGESTIVE "
      "printed in a failed family carries that; none of them is a weaker but sounder "
      "verdict.")
    A("")

    # F9 — the shifted panel is a shrinking subsample, and the direction of that
    ukey = f"H{H_PRIMARY}|{VERDICT_ARM['dd_le_m20']}|{mb}"
    useries = [(p["primary"].get(f"{ukey}|FIT|dd_le_m20", {})
                .get("rows_excluded_unmeasurable"))]
    useries += [(p["placebo"]["per_shift"].get(str(s), {})
                 .get(f"{ukey}|dd_le_m20", {}).get("rows_excluded_unmeasurable"))
                for s in shifts]
    A("**The placebo subsample shrinks with S, and that is disclosed rather than "
      "absorbed.** A shifted row whose source bar falls before its own name's first bar "
      "carries no footprint value and is excluded and counted, so a name shorter than S "
      f"vanishes entirely. On `{ukey}|FIT|{pb.FSHORT['dd_le_m20']}` the rows excluded as "
      "unmeasurable run "
      + " → ".join(f"{v:,}" if v is not None else "—" for v in useries)
      + f" at S = 0 (unshifted), {', '.join(str(s) for s in shifts)}. The direction is "
      "conservative for a false-positive guard: a smaller subsample means a larger "
      "standard error and therefore FEWER rejections, so the measured rejection rate is "
      "if anything an understatement of the miscalibration, never an inflation of it.")
    A("")
    A(_cap(p["placebo"]["consequence"]) + ". The consequence is applied as frozen; the "
      "mechanism evidence above bounds what the failure means, and does not soften what "
      "it costs.")
    A("")

    # §7 retention
    A("## 7. Retention — contrast-bearing strata are a biased subset, and this says how")
    A("")
    A(f"Strata are sparse at these densities, and the `exp` leg collapses first. A cell "
      f"retaining **< {100 * G1_RETENTION_MIN:.0f}%** of its F=TRUE positive episodes is "
      "**NOT_EVALUABLE** — never NULL, never a verdict.")
    A("")
    rows = []
    for b in p["verdict_summary"]["verdict_boards"]:
        for fk in FKEYS_ORDER:
            c = p["primary"].get(f"H{H_PRIMARY}|{VERDICT_ARM[fk]}|{b}|FIT|{fk}")
            if not c or c.get("status") == "NOT_EVALUABLE":
                continue
            r = c["retention"]
            comp = r["composition_retained_F_true"]["dd_band"]
            top = f"{max(comp, key=comp.get)} {max(comp.values())}%" if comp else "—"
            rows.append([b, pb.FSHORT[fk], VERDICT_ARM[fk],
                         f"{r['strata_contrast_bearing']:,}/{r['strata_total']:,}",
                         f"{r['F_true_rows_retained_pct']}%",
                         f"{r['F_true_positive_episodes_retained_pct']}%",
                         f"{r['F_false_rows_retained_pct']}%", top,
                         r["band_local_label"] or "—"])
    A(T(["board", "footprint", "arm", "contrast strata", "F=TRUE rows kept",
         "F=TRUE pos episodes kept", "F=FALSE rows kept", "top retained dd_band",
         "band-local"], rows))
    A("")

    # §8 lead curves
    A("## 8. Two-speed lead curves (secondary, descriptive, gates nothing)")
    A("")
    A(p["lead_curves"]["known_mechanical_break"])
    A("")
    A(p["lead_curves"]["constant_cohort_scope"])
    A("")
    # F7 — the N columns say what they are, and the per-footprint matched N is named
    lcv, elig_all = p["lead_curves"]["curves"], p["lead_curves"][
        "eligibility_per_lead_by_board_split"]
    A("**What the N columns are.** `eligible cases (cohort)` and `eligible controls "
      "(cohort)` are the (board, split) cohort's own counts at that lead — every "
      "U1-eligible case anchor and every verified-quiet control on that board and split, "
      "**before** any footprint's measurability mask and **before** matching. They are "
      "NOT any one footprint's N: each footprint then drops the rows its mask cannot "
      "measure, and the estimator keeps only rows landing in a stratum that carries both "
      "classes. `excluded` is this cohort's own per-lead exclusion count, not the "
      "cohort-wide one.")
    A("")
    ex_b = p["verdict_summary"]["verdict_boards"][0]
    ex_fk = "sector_deep35_ge40"
    ex_c = lcv.get(f"{ex_b}|FIT|{ex_fk}|full_cohort", {}).get("1", {})
    ex_e = elig_all.get(f"{ex_b}|FIT", {}).get("1", {})
    if ex_c and ex_e:
        A(f"**The gap is large enough to name.** `{ex_b} · FIT`, ℓ = 1, "
          f"{pb.FSHORT[ex_fk]}: **{ex_e['case_anchors_full_cohort']:,}** cohort-eligible "
          f"case anchors → **{ex_c['case_anchors']:,}** measurable for that footprint → "
          f"**{ex_c['matched_case_anchors']:,}** actually matched into a contrast-bearing "
          "stratum. Every footprint's matched N at every lead is in the JSON as "
          "`lead_curves.curves.<board>|<split>|<footprint>|<mode>.<lead>."
          "matched_case_anchors`, beside its own `case_anchors`.")
        A("")
    for b in p["verdict_summary"]["verdict_boards"]:
        for sg in GATED_SPLITS:
            any_row = any(f"{b}|{sg}|{fk}|full_cohort" in lcv for fk in FKEYS_ORDER)
            if not any_row:
                continue
            elig = elig_all.get(f"{b}|{sg}", {})
            A(f"**{b} · {sg}** — excess prevalence of the footprint among case anchors vs "
              "matched quiet controls, pp, with a session-block 95% CI.")
            A("")
            rows = []
            for lead in LEAD_GRID:      # NEVER `L` here — `L` is the writeup's line list
                el = elig.get(str(lead), {})
                r = [lead, f"{el.get('case_anchors_full_cohort', 0):,}",
                     f"{el.get('controls', 0):,}", f"{el.get('excluded_total', 0):,}"]
                for fk in FKEYS_ORDER:
                    c = lcv.get(f"{b}|{sg}|{fk}|full_cohort", {}).get(str(lead), {})
                    if "excess_prevalence_pp" in c:
                        ci = c.get("ci95_pp")
                        r.append(f"{c['excess_prevalence_pp']:+.1f}"
                                 + (f" ({ci[0]:+.1f},{ci[1]:+.1f})" if ci else ""))
                    else:
                        r.append("—")
                rows.append(r)
            A(T(["lead ℓ", "eligible cases (cohort)", "eligible controls (cohort)",
                 "excluded"] + [pb.FSHORT[k] for k in FKEYS_ORDER], rows))
            A("")
            # F6 — the constant-cohort curves, printed rather than JSON-only
            cc_fks = [fk for fk in FKEYS_ORDER
                      if f"{b}|{sg}|{fk}|constant_cohort" in lcv]
            if not cc_fks:
                continue
            A(f"**{b} · {sg}, constant cohort** — the SAME events at every lead (an event "
              "enters only if it is U1-eligible at all "
              f"{len(LEAD_GRID)} grid leads), so the curve's shape cannot be a "
              "composition change. Printed for the "
              f"{len(cc_fks)} eligible footprints only; see the scope note above for why "
              "the DD / depth / duration families are absent.")
            A("")
            rows = []
            for lead in LEAD_GRID:
                el = elig.get(str(lead), {})
                r = [lead, f"{el.get('case_anchors_constant_cohort', 0):,}",
                     f"{el.get('controls', 0):,}"]
                for fk in cc_fks:
                    c = lcv.get(f"{b}|{sg}|{fk}|constant_cohort", {}).get(str(lead), {})
                    if "excess_prevalence_pp" in c:
                        ci = c.get("ci95_pp")
                        r.append(f"{c['excess_prevalence_pp']:+.1f}"
                                 + (f" ({ci[0]:+.1f},{ci[1]:+.1f})" if ci else ""))
                    else:
                        r.append("—")
                rows.append(r)
            A(T(["lead ℓ", "eligible cases (constant cohort)",
                 "eligible controls (cohort)"] + [pb.FSHORT[k] for k in cc_fks], rows))
            A("")
    A(p["lead_curves"]["eligibility_scope_note"])
    A("")

    # F13 — a descriptive reading of the printed curves. Gates nothing, adds no statistic.
    def _lead(fk, lead, board, mode="full_cohort", sgp="FIT"):
        return lcv.get(f"{board}|{sgp}|{fk}|{mode}", {}).get(
            str(lead), {}).get("excess_prevalence_pp")
    rb = p["verdict_summary"]["verdict_boards"][0]
    d35 = [_lead("dd_le_m35", x, rb) for x in (1, 20, 30, 60)]
    ma_1, ma_20 = _lead("under_ma200", 1, rb), _lead("under_ma200", 20, rb)
    mac_1, mac_20 = (_lead("under_ma200", 1, rb, "constant_cohort"),
                     _lead("under_ma200", 20, rb, "constant_cohort"))
    vz = [_lead("volz_gt1", x, rb) for x in (1, 2, 3)]
    if None not in (*d35, ma_1, ma_20, mac_1, mac_20, *vz):
        A(f"**Reading these curves (descriptive — no gate, no statistic, `{rb} · FIT`).** "
          f"{pb.FSHORT['dd_le_m35']} is flat-to-RISING with lead **inside** the pre-break "
          f"window: {_f(d35[0], 1, True)} pp at ℓ = 1 against {_f(d35[1], 1, True)} pp at "
          "ℓ = 20. That is the shape of a **persistent state**, not of a precursor "
          "turning on before ignition — the same multi-year persistence §6 measures "
          "defeating the placebo shift, seen from the other side. (Read on its own, the "
          f"structural window sits at the same level — {_f(d35[2], 1, True)} pp at ℓ = 30, "
          f"{_f(d35[3], 1, True)} pp at ℓ = 60 — but that is a level, **not** a "
          "continuation of the series above: the ℓ = 21 composition break forbids reading "
          f"across it.) {pb.FSHORT['under_ma200']} runs the other way, and entirely inside "
          f"the same window: its deficit DEEPENS toward ignition ({_f(ma_20, 1, True)} pp "
          f"at ℓ = 20 → {_f(ma_1, 1, True)} pp at ℓ = 1), so the reclaim is the fast leg — "
          "and the constant-cohort curve, whose composition cannot change with lead at "
          f"all, moves the same way ({_f(mac_20, 1, True)} → {_f(mac_1, 1, True)} pp). "
          f"{pb.FSHORT['volz_gt1']} spikes only at ℓ ≤ 2 ({_f(vz[0], 1, True)} pp at "
          f"ℓ = 1, {_f(vz[1], 1, True)} at ℓ = 2, {_f(vz[2], 1, True)} at ℓ = 3) — "
          "coincident, exactly as its stamp says. **No reading here compares across the "
          "ℓ = 21 boundary**; the mechanical composition break above forbids it, and none "
          "of these three statements needs it.")
        A("")

    # §9 flagged sets
    A("## 9. Flagged-set diagnostics (descriptive — explicitly not a ranker)")
    A("")
    rows = []
    for b in p["verdict_summary"]["verdict_boards"]:
        for fk in FKEYS_ORDER:
            for sg in ("FIT", "HOLDOUT"):
                c = p["flagged_sets"].get(f"{fk}|{b}|{sg}")
                if not c:
                    continue
                rows.append([b, sg, pb.FSHORT[fk], c["arm_universe"],
                             c["positive_episodes"], f"{c['flag_rate_pct']}%",
                             f"{c['precision_pct']}%" if c["precision_pct"] is not None
                             else "—", f"{c['capture_pct']}%",
                             f"{c['flagged_per_session_median']:.0f} "
                             f"[{c['flagged_per_session_iqr'][0]:.0f},"
                             f"{c['flagged_per_session_iqr'][1]:.0f}]"])
    A(T(["board", "split", "footprint", "universe", "pos episodes", "flag rate",
         "precision P(fb₁₀|F)", "capture P(F|fb₁₀)", "flagged/session med [IQR]"], rows))
    A("")
    A(p["flagged_sets"]["_stamp"])
    A("")

    # §10 amendments + reading notes
    A("## 10. Amendments and reading notes")
    A("")
    for a in AMENDMENTS:
        A(f"**{a['id']} — {a['what']}**")
        A("")
        for it in a.get("items", ()):
            A(f"- {it}")
        if a.get("items"):
            A("")
        A(f"*Why:* {a['why']}")
        A("")
        A(f"*Risk controlled by:* {a['risk_controlled_by']}")
        A("")
    A("Reading notes record where the prereg admitted more than one reading; each names "
      "its materiality so the choice is adjudicable rather than silent.")
    A("")
    for r in READING_NOTES:
        A(f"**{r['id']}** — {r['point']}")
        A("")
        A(f"*Reading taken:* {r['reading']} *Materiality:* {r['materiality']}")
        A("")
        # F8 — R4's population is small enough to enumerate, so it is enumerated
        if r["id"] == "R4":
            pop = _r4_population(p)
            sec = []
            for _k, v in pop:
                alt = (p["verdicts"].get(f"H{H_SECONDARY}|{v['board']}|{v['footprint']}")
                       if v["horizon"] == H_PRIMARY else None)
                if alt:
                    sec.append(f"`{pb.FSHORT[v['footprint']]}` z = "
                               f"{_f(alt.get('fit_z_2way'), 2)} → {alt['verdict']}")
            if pop:
                A(f"*Cells this convention actually moves — computed, not asserted:* "
                  f"exactly {len(pop)}, "
                  + ", ".join(f"`H{v['horizon']} · {v['board']} · "
                              f"{pb.FSHORT[v['footprint']]}` (FIT z = "
                              f"{_f(v.get('fit_z_2way'), 2)} → {v['verdict']})"
                              for _k, v in pop)
                  + ". The move is **upward only**: each is SUGGESTIVE under the reading "
                  "taken and NULL under the literal alternative, and no other cell in the "
                  "receipt sits in the 1.96–2.81 band with G3, G4 and G5 all passed."
                  + (f" They are fragile at the secondary horizon — the same cells at "
                     f"H = {H_SECONDARY} print " + ", ".join(sec)
                     + ", below the SUGGESTIVE bar and therefore NULL under either "
                     "reading." if sec else ""))
                A("")

    # §11 verify
    A("## 11. Verification battery — every check paired with a mutation it must detect")
    A("")
    sm = p["verify"]["summary"]
    A(f"**{sm['prereg_checks_passed']}/{sm['prereg_checks_run']} prereg §11 checks "
      f"passed; {sm['prereg_probes_detected']}/{sm['prereg_checks_run']} mutation probes "
      f"detected.** Plus {sm['amendment_controls_run']} amendment control "
      f"({sm['amendment_controls_passed']} passed, "
      f"{sm['amendment_control_probes_detected']} probe detected).")
    A("")
    rows = []
    for k, c in p["verify"]["checks"].items():
        mp = c["mutation_probe"]
        rows.append([k, "PASS" if c["passed"] else "**FAIL**",
                     "detected" if mp["detected"] else "**NOT DETECTED**",
                     mp["mutation"][:170]])
    A(T(["check", "result", "probe", "mutation applied"], rows))
    A("")
    A(p["verify"]["doctrine"])
    A("")

    # §12 what this does not establish
    A("## 12. What this does NOT establish")
    A("")
    for s in DOES_NOT_ESTABLISH:
        A(f"- {s}")
    A("")
    A("## 13. Ore ledger — what was deliberately not built")
    A("")
    for s in ORE_LEDGER:
        A(f"- {s}")
    A("")
    A("---")
    A("")
    v = p["vintage"]
    A(f"Vintage: base `{v['base_sha'][:12]}`, head `{v['build_head_sha'][:12]}`, raw "
      f"store `{str(v['raw_store_commit'])[:12]}`, W-P0 pin "
      f"`{p['pin']['w1_sha256'][:16]}…`, P-B pin `{p['pin']['pb_sha256'][:16]}…`, prereg "
      f"`{p['pin']['prereg_sha256'][:16]}…`. {v['determinism']}")
    A("")
    # F12 — this run's own N first; W-P0's percentages attributed to W-P0's own snapshot
    fpm = p["footprint_plane"]
    stamp = p["survivorship_stamp"]
    try:
        tk = stamp.split()
        w1_n = tk[tk.index("curated") - 1]
    except (ValueError, IndexError):
        w1_n = "the curated-name count quoted inside it"
    A(f"Survivorship, measured on THIS run: **{fpm['tickers_kept']:,} names kept of "
      f"{fpm['files_found']:,} files** in `{fpm['raw_store'].split(' (')[0]}` — "
      f"{fpm['tickers_skipped_st']:,} skipped as ST, "
      f"{fpm['tickers_skipped_thin_or_unreadable']:,} as thin or unreadable — carrying "
      f"{fpm['panel_rows']:,} live bars over {fpm['panel_sessions']:,} sessions. W-P0's "
      "stamp follows verbatim; its counts and **every percentage in it were measured by "
      f"W-P0 on W-P0's OWN store snapshot of {w1_n} curated names**, not on this run's "
      f"{fpm['tickers_kept']:,}, and are quoted as W-P0 measured them rather than "
      "re-derived here. The qualitative claim is what carries across — a large-cap, "
      "survivors-only slice — and it carries at either N.")
    A("")
    A(f"W-P0's stamp: {stamp}")
    A("")
    return "\n".join(L) + "\n"


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

PBMOD = None
FKEYS_ORDER: tuple = ()


def check_pins(path: Path, symbols: dict, who: str) -> dict:
    lines = path.read_text().splitlines()
    bad = {}
    for name, (ln, needle) in symbols.items():
        line = lines[ln - 1] if 0 < ln <= len(lines) else ""
        if needle not in line:
            bad[name] = {"expected_line": ln, "needle": needle,
                         "found": line.strip()[:80]}
    if bad:
        raise SystemExit(
            f"PIN MISMATCH in {who} ({path.name}): {json.dumps(bad, indent=2)}\n"
            "P-B2 refuses to write receipts against an unpinned definition source. "
            "Re-resolve the line-pin table against the current file before re-running.")
    return {"symbols_pinned": len(symbols), "source_lines": len(lines), "unresolved": {}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=None,
                    help="DEV ONLY. Required whenever a dev flag is used, so no dev run "
                         "can ever overwrite the real receipts.")
    ap.add_argument("--panel-cache", default=None,
                    help="DEV ONLY. Load/save the built panel to speed up iteration.")
    ap.add_argument("--dev-slice", type=int, default=0,
                    help="DEV ONLY. Keep every Nth ticker.")
    a = ap.parse_args(argv)
    dev = bool(a.panel_cache or a.dev_slice)
    if dev and not a.out_dir:
        raise SystemExit("--panel-cache / --dev-slice are DEV flags and require "
                         "--out-dir; the shipped receipts come only from a full run.")
    out_dir = Path(a.out_dir) if a.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json, out_md = out_dir / OUT_JSON_NAME, out_dir / OUT_MD_NAME

    global PBMOD, FKEYS_ORDER
    print("P-B2 — matched precursor discrimination", flush=True)
    w1, w1_sha = _load_module(W1_PATH, "_pb2_w1", "W-P0's panel and definitions")
    pb, pb_sha = _load_module(PB_PATH, "_pb2_pb", "P-B's footprint derivation")
    PBMOD = pb
    FKEYS_ORDER = tuple(pb.FKEYS)
    if not PREREG_PATH.exists():
        raise SystemExit(f"MISSING PRE-REGISTRATION: {PREREG_PATH}\nThe prereg IS the "
                         "contract; P-B2 refuses to run without it.")
    prereg_sha = _sha(PREREG_PATH)
    pin_w1 = check_pins(W1_PATH, PIN_SYMBOLS_W1, "W-P0")
    pin_pb = check_pins(PB_PATH, PIN_SYMBOLS_PB, "P-B")
    print(f"  [1/9] pins resolved  w1={w1_sha[:16]}…  pb={pb_sha[:16]}…  "
          f"prereg={prereg_sha[:16]}…", flush=True)

    cache = Path(a.panel_cache) if a.panel_cache else None
    if cache and cache.exists():
        panel = pd.read_parquet(cache)
        pmeta = json.loads((cache.with_suffix(".meta.json")).read_text())
    else:
        panel, pmeta = pb.build_footprint_panel(w1)
        panel = pb.derive_footprints(panel)
        if cache:
            panel.to_parquet(cache)
            cache.with_suffix(".meta.json").write_text(
                json.dumps(pb.jsonable(pmeta), indent=2))
    if a.dev_slice:
        keep = sorted(pd.unique(panel["ticker"]))[::a.dev_slice]
        panel = panel[panel["ticker"].isin(keep)].reset_index(drop=True)
    pmeta["window"] = [str(w1.WINDOW_START.date()), str(w1.WINDOW_END.date())]
    print(f"  [2/9] footprint plane  {len(panel):,} rows", flush=True)

    pl = Plane(panel, w1, pb)
    ev = pb.extract_events(pl.panel, w1)
    floors = board_floors(pl)
    boards = [b for b in BOARD_ORDER
              if floors[f"H{H_PRIMARY}|M1|{b}"]["verdict_eligible"]
              or floors[f"H{H_PRIMARY}|M0|{b}"]["verdict_eligible"]]
    print(f"  [3/9] plane + floors  U0={int(pl.U0.sum()):,} U1={int(pl.U1.sum()):,}  "
          f"verdict boards={boards}", flush=True)
    if not boards:
        raise SystemExit(
            "NO BOARD MEETS THE FROZEN G1 BOARD FLOOR — every footprint on every board "
            "would be DESCRIPTIVE_ONLY and the verification battery has no reference cell "
            "to probe. Refusing to write a vacuous receipt.")

    n = [0]

    def tick():
        n[0] += 1
        if n[0] % 40 == 0:
            print(f"        … {n[0]} cells", flush=True)
    primary = run_primary(pl, floors, splits=tuple(SPLIT_GROUPS), progress=tick)
    print(f"  [4/9] primary battery  {len(primary)} cells", flush=True)

    placebo = run_placebo(pl, floors, boards, progress=tick)
    print(f"  [5/9] placebo calibration  {len(PLACEBO_SHIFTS)} shifts", flush=True)

    gradients = run_gradients(pl, floors, boards)
    depth_ref = run_gradients(pl, floors, boards,
                              spec={DEPTH_GRADIENT[0]: {"bands": DEPTH_GRADIENT[1],
                                                        "mask": DEPTH_GRADIENT[2],
                                                        "drop": DEPTH_GRADIENT[3],
                                                        "what": "washout depth band — "
                                                                "sec.5.3-named depth "
                                                                "gradient, JSON only "
                                                                "(reading note R1)"}},
                              tag="depth_ref")
    s_arm = run_s_arm(pl, boards)
    vz_sens = vz_no_vol_sensitivity(pl, floors, boards)
    overlap = episode_overlap(pl, ev)
    controls, ctrl_meta = quiet_controls(pl)
    leads = run_lead_curves(pl, ev, controls, boards)
    flagged = flagged_sets(pl, boards)
    print(f"  [6/9] gradients + S-arm + lead curves + flagged sets", flush=True)

    # ── verdicts ─────────────────────────────────────────────────────────────
    verdicts, manski = OrderedDict(), OrderedDict()
    fam_fail = {k: v["calibration_failed"]
                for k, v in placebo["family_calibration"].items()}
    for H in HORIZONS:
        for b in BOARD_ORDER:
            pvals = {}
            for fk in FKEYS_ORDER:
                arm = VERDICT_ARM[fk]
                fit = primary.get(f"H{H}|{arm}|{b}|FIT|{fk}")
                hold = primary.get(f"H{H}|{arm}|{b}|HOLDOUT|{fk}")
                if fit is None:
                    continue
                ok = floors[f"H{H}|{arm}|{b}"]["verdict_eligible"]
                v = verdict_for(fit, hold, ok, fam_fail.get(f"{b}|H{H}", False))
                v["arm"] = arm
                v["footprint"] = fk
                v["board"] = b
                v["horizon"] = H
                v["coincident_stamp"] = COINCIDENT_STAMP.get(fk)
                v["honest_n"] = (
                    f"{fit['retention']['F_true_positive_episodes_retained']} ep / "
                    f"{fit['estimate']['matched_F_true_rows']:,} r"
                    if fit.get("status") != "NOT_EVALUABLE" else "—")
                v["m0_excess_pp"] = (primary.get(f"H{H}|M0|{b}|FIT|{fk}", {})
                                     .get("estimate", {}).get("matched_excess_pp"))
                verdicts[f"H{H}|{b}|{fk}"] = v
                pvals[fk] = v.get("p_two_sided_normal")
                if v["verdict"] == "DISCRIMINATOR":
                    rows = cell_rows(pl, ARM_UNIVERSE[arm], b, "FIT")
                    mb = manski_bounds(pl, pl.F[fk], MEASURABILITY[fk],
                                       arm_factors(fk, arm), rows, H)
                    e = v["fit_excess_pp"]
                    manski[f"H{H}|{b}|{pb.FSHORT[fk]}"] = {
                        "excess_pp": e, "bounds": mb,
                        "sign_survives": bool(
                            all(x is not None and np.sign(x) == np.sign(e)
                                for x in mb.values()))}
            for fk, adj in holm(pvals).items():
                if f"H{H}|{b}|{fk}" in verdicts:
                    verdicts[f"H{H}|{b}|{fk}"]["holm_p"] = adj

    tally = {}
    for v in verdicts.values():
        tally[v["verdict"]] = tally.get(v["verdict"], 0) + 1
    vsum = {
        "verdict_boards": boards,
        "gated_cells": sum(1 for v in verdicts.values()
                           if v["verdict"] in ("DISCRIMINATOR", "SUGGESTIVE", "NULL")),
        "tally": tally,
        "discriminators": sorted(k for k, v in verdicts.items()
                                 if v["verdict"] == "DISCRIMINATOR"),
        "suggestive": sorted(k for k, v in verdicts.items()
                             if v["verdict"] == "SUGGESTIVE"),
        "families_failing_placebo_calibration": sorted(k for k, f in fam_fail.items()
                                                       if f),
    }
    print(f"  [7/9] verdicts  {tally}", flush=True)

    vintage = build_vintage(w1_sha, pb_sha, prereg_sha)
    verify = verify_battery(pl, w1, pb, w1_sha, pb_sha, primary, floors,
                            list(leads["curves"]), controls, ctrl_meta, ev, boards,
                            vintage)
    sm = verify["summary"]
    print(f"  [8/9] verify  {sm['prereg_checks_passed']}/{sm['prereg_checks_run']} "
          f"prereg checks  {sm['prereg_probes_detected']}/{sm['prereg_checks_run']} "
          f"probes detected", flush=True)
    if not sm["all_passed"]:
        bad = sorted(k for k, c in verify["checks"].items() if not c["passed"])
        print(f"::error title=pb2-verify-failed::P-B2 verify battery failed: "
              f"{', '.join(bad)}", flush=True)
    if not sm["all_probes_detected"]:
        bad = sorted(k for k, c in verify["checks"].items()
                     if not c["mutation_probe"]["detected"])
        print(f"::error title=pb2-vacuous-check::P-B2 mutation probe undetected (the "
              f"check cannot fail): {', '.join(bad)}", flush=True)
    if vsum["families_failing_placebo_calibration"]:
        print(f"::warning title=pb2-placebo-uncalibrated::placebo calibration FAILED in "
              f"{', '.join(vsum['families_failing_placebo_calibration'])} — every "
              f"DISCRIMINATOR in those families downgrades to SUGGESTIVE", flush=True)
    if vintage["stamps_unresolved_by_shallow_graft"]:
        print(f"::warning title=pb2-shallow-vintage::vintage stamp(s) "
              f"{', '.join(vintage['stamps_unresolved_by_shallow_graft'])} resolve to a "
              f"shallow-clone graft and are relabelled, not printed as provenance",
              flush=True)

    meas_excluded = {}
    meas_pct = {}
    u0 = int(pl.U0.sum())
    for fk in FKEYS_ORDER:
        ex = int((pl.U0 & ~pl.masks[MEASURABILITY[fk]]).sum())
        meas_excluded[fk] = ex
        meas_pct[fk] = round(100.0 * ex / max(u0, 1), 3)

    payload = OrderedDict([
        ("instrument", "pb2_precursor_discrimination"),
        ("wave", "CN LIMIT-MOVE ALPHA — P-B2: matched precursor discrimination"),
        ("artifact_date", ARTIFACT_DATE),
        ("authority", AUTHORITY), ("tier", TIER_STAMP),
        ("governing_ruling", GOVERNING_RULING), ("program_home", PROGRAM_HOME),
        ("preregistration", {
            "path": f"research/cn_prophet_audit/{PREREG_PATH.name}",
            "sha256": prereg_sha,
            "frozen_before_outcome_access": True,
            "role": "THE CONTRACT — every definition, stratum, floor, gate and "
                    "disposition rule is read from it; deviations are numbered "
                    "amendments, never silent re-choices",
        }),
        ("pin", {
            "mode": "IMPORTED (both modules are import-safe; nothing copied, nothing "
                    "re-derived). A pin mismatch REFUSES the run before any receipt is "
                    "written.",
            "w1_sha256": w1_sha, "pb_sha256": pb_sha, "prereg_sha256": prereg_sha,
            "w1_symbols": {k: f"L{ln}" for k, (ln, _n) in PIN_SYMBOLS_W1.items()},
            "pb_symbols": {k: f"L{ln}" for k, (ln, _n) in PIN_SYMBOLS_PB.items()},
            "w1_pin_receipt": pin_w1, "pb_pin_receipt": pin_pb,
        }),
        ("definitions", {
            "universes": {
                "U0": "cold AND split assigned (W-P0's embargoed split column) AND dd250 "
                      "finite",
                "U1": "U0 AND dd250 <= -0.20",
            },
            "labels": {"positive": "fb_H", "negative": "win_ok_H AND NOT fb_H",
                       "censored": "NOT win_ok_H — enters NEITHER class, never a miss",
                       "horizons": {"primary": H_PRIMARY, "secondary": H_SECONDARY}},
            "episode_identity": "a positive row's episode key is its realised board — the "
                                "panel-axis row of the first tolerant board after T; "
                                "distinct-episode counts are the honest event N "
                                "everywhere",
            "estimator": "ATT-weighted direct standardisation; obs = sum k_F1 / sum n_F1, "
                         "exp = sum n_F1*(k_F0/n_F0) / sum n_F1, over strata carrying "
                         "BOTH F-classes; excess = 100*(obs-exp) pp",
            "arms": {"M0": "U0, strata = session x own-vol decile (stratum 10 = "
                           "unmeasurable), board a hard subset",
                     "M1": "U1, strata = session x vol decile x dd_band x dur_band"},
            "carveout_map": {k: {a: list(v[a]) for a in ARMS}
                             for k, v in CARVEOUT.items()},
            "verdict_arm": dict(VERDICT_ARM),
            "measurability": dict(MEASURABILITY),
            "frozen_constants": {
                "SEED": SEED, "N_BOOT_SESSION": N_BOOT_SESSION,
                "N_BOOT_NAME": N_BOOT_NAME, "N_BOOT_ROW": N_BOOT_ROW, "N_PERM": N_PERM,
                "BLOCK_LEN": BLOCK_LEN, "THIN_STEP": THIN_STEP,
                "LEAD_CURVE_B": LEAD_CURVE_B, "PLACEBO_SHIFTS": list(PLACEBO_SHIFTS),
                "G2_Z": G2_Z, "G5_Z": G5_Z, "LEAD_GRID": list(LEAD_GRID)},
            "coincident_indicator_stamps": COINCIDENT_STAMP,
        }),
        ("footprint_plane", pmeta),
        ("universes", universe_tables(pl)),
        ("universe_exclusions", {
            "cold_rows_without_a_split": pl.excluded_no_split,
            "cold_rows_with_dd_na": pl.excluded_dd_na,
            "rule": "excluded AND counted, never folded into a class"}),
        ("labels", label_tables(pl)),
        ("episode_overlap_with_pb_cohort", overlap),
        ("measurability", {"rows_excluded": meas_excluded, "pct_excluded": meas_pct,
                           "u0_rows": u0,
                           "ma200_covering_lemma":
                               verify["checks"]["missing_not_false"]["detail"]
                               ["ma200_covering_lemma"]}),
        ("board_floors", floors),
        ("primary", primary),
        ("verdicts", verdicts),
        ("verdict_summary", vsum),
        ("manski", manski),
        ("placebo", placebo),
        ("gradients", gradients),
        ("depth_gradient_reference", depth_ref),
        ("s_arm_sector_sensitivity", s_arm),
        ("vz_no_vol_stratum_sensitivity", vz_sens),
        ("quiet_controls", ctrl_meta),
        ("lead_curves", leads),
        ("flagged_sets", flagged),
        ("verify", verify),
        ("does_not_establish", DOES_NOT_ESTABLISH),
        ("ore_ledger", ORE_LEDGER),
        ("amendments", AMENDMENTS),
        ("reading_notes", READING_NOTES),
        ("survivorship_stamp", w1.SURVIVORSHIP_STAMP),
        ("vintage", vintage),
    ])

    # A4 provenance-stability guard — REFUSE to write polluted provenance.
    head = payload["vintage"]["build_head_sha"]
    for k in ("raw_store_commit", "members_commit", "st_snapshot_commit",
              "zt_pool_commit", "w1_pin_commit", "pb_pin_commit", "prereg_commit"):
        c = payload["vintage"][k]
        if c.startswith("SHALLOW_BOUNDARY_UNRESOLVED(") or c == "UNAVAILABLE":
            continue
        if subprocess.run(["git", "merge-base", "--is-ancestor", c, head],
                          cwd=REPO, capture_output=True).returncode != 0:
            raise SystemExit(
                f"A4 GUARD: vintage stamp {k}={c} is not an ancestor of build head "
                f"{head} — the checkout moved mid-run; refusing to write polluted "
                "provenance")

    md = build_md(payload, pb)
    final_ok, final_det = pb.stop_ship_scan({
        "pb2_precursor_discrimination.py": Path(__file__).read_text(),
        out_md.name: md})
    ss = payload["verify"]["checks"]["stop_ship_reference_scan"]
    ss["passed"], ss["detail"] = final_ok, final_det
    if not final_ok:
        raise SystemExit(f"withdrawn-artifact reference(s) found: {final_det['hits']} — "
                         f"{GOVERNING_RULING}; refusing to write")

    out_json.write_text(json.dumps(pb.jsonable(payload), indent=2, sort_keys=False)
                        + "\n")
    out_md.write_text(md)
    print(f"  [9/9] wrote {out_json.name} ({out_json.stat().st_size / 1e6:.2f} MB) and "
          f"{out_md.name} ({out_md.stat().st_size / 1e3:.1f} kB, "
          f"{len(md.splitlines())} lines)", flush=True)
    return 0 if (sm["all_passed"] and sm["all_probes_detected"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
