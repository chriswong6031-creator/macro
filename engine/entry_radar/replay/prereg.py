"""Frozen W5 preregistration constants — the code mirror of the merged prereg.

Single source of truth for every frozen number the replay/outcome machinery
consumes.  ``research/live_entry_radar/W5_FORWARD_EVIDENCE_PREREG.md`` is the
governing document; this module restates its load-bearing values so that (a) the
engine never parses prose, and (b) a doc↔code drift is a test failure, not a
silent reinterpretation (tests pin the values below against exact strings in the
doc).

The two ``PREREG_*`` identity constants are set in PR-5b AFTER the prereg-only
PR-5a merges (they name the merged commit and the file's sha256 at that commit).
While they are the ``_UNSET`` sentinel every §14 gate refuses — machinery built
before the prereg merged cannot read an outcome, by construction.
"""
from __future__ import annotations

import hashlib
from datetime import date

# --------------------------------------------------------------------------- #
# §14 identity gates (set in PR-5b once PR-5a is merged; _UNSET refuses)
# --------------------------------------------------------------------------- #
_UNSET = "UNSET"

#: 40-hex sha of the merged PR-5a commit that landed the prereg on main.
#: _UNSET until PR-5b stamps the real merged sha — every gate refuses meanwhile.
PREREG_COMMIT: str = "416bb8cab3ae9239916aa3952f4541665917d5cc"

#: 64-hex sha256 of research/live_entry_radar/W5_FORWARD_EVIDENCE_PREREG.md at
#: that commit (and, unless amended, on disk at run time).  _UNSET until PR-5b.
PREREG_DOC_SHA256: str = "5e67ab8ecc617ee5d0255533de16dc6d10716631edd97bb650992c6db74a7c01"

#: Repo-relative path of the governing document.
PREREG_DOC_PATH = "research/live_entry_radar/W5_FORWARD_EVIDENCE_PREREG.md"

#: §14 G-1 frozen-prefix law (B4 fix): the hash covers the file's bytes up to
#: and INCLUDING the first line that startswith this marker; §16 amendments
#: append strictly after it, so a lawful amendment never changes the G-1 hash.
PREREG_FROZEN_MARKER = "## §16 Amendments (append-only"

# --------------------------------------------------------------------------- #
# §1 detector identity (W3 lock — must match engine.entry_radar.detectors)
# --------------------------------------------------------------------------- #
EXPECTED_SPEC_HASHES: dict[str, str] = {
    "G0_GREY_DOT@1": "9be89a8acc8b905c",
    "C1_1D_LIVE_WASHOUT@1": "f0bbd6cf3a6e2339",
    "C2_1D_TURN@1": "d8ba60a25cfa7400",
    "C3_1D_4H_RECOVERY@1": "d54dc1e55c4261c8",
    "C4_MTF_TURN@1": "dce21ac680233ee2",
    "C5_BOTTOM_WATCH@1": "13dec66345a0376c",
}

#: The A5.6-pinned Terminal commit the staged G0/C5 emitter runs at.
TERMINAL_PIN = "82cb8cbf799fc3a91c9bee0f11a4db718fde68eb"

# --------------------------------------------------------------------------- #
# §1 eras / §12-of-doc holdout  (decision-session membership)
# --------------------------------------------------------------------------- #
REPLAY_ERA_START = date(2011, 1, 3)
FIT_END = date(2020, 6, 30)          # FIT = [REPLAY_ERA_START, FIT_END]
TEST_START = date(2020, 7, 1)        # TEST = [TEST_START, HOLDOUT_BOUNDARY]
HOLDOUT_BOUNDARY = date(2026, 2, 13)  # holdout = strictly after this session

# --------------------------------------------------------------------------- #
# §7 outcomes / false start / §10 horizons
# --------------------------------------------------------------------------- #
HORIZON_PRIMARY = 10                       # trading sessions; Radar's own ruler
HORIZONS_SECONDARY = (3, 5, 21)            # diagnostics only
FALSE_START_ADVERSE_ATR = 1.25             # MAE >= 1.25 x A0 ...
FALSE_START_FAVORABLE_ATR = 1.00           # ... before MFE >= 1.00 x A0
TARGET_ATR = 1.00                          # target  = P0 + 1.00 x A0
INVALIDATION_ATR = 1.25                    # invalid = P0 - 1.25 x A0
WASHOUT_LOW_FALLBACK_SESSIONS = 63         # G0/C5/incumbent washout-low window

#: 27-cell diagnostic grid (favorable x adverse x horizon) — pre-counted looks.
SENSITIVITY_FAVORABLE = (0.75, 1.00, 1.50)
SENSITIVITY_ADVERSE = (1.00, 1.25, 1.50)
SENSITIVITY_HORIZONS = (5, 10, 15)

# --------------------------------------------------------------------------- #
# §7 matched controls
# --------------------------------------------------------------------------- #
CONTROL_K = 5
CONTROL_NO_FIRE_NEAR_SESSIONS = 5          # no fire within +/-5 sessions of D
CONTROL_MAX_DISTANCE = 1.0                 # M6: L1 cap over 4 axes normalized to [0,1]
CAP_BUCKET_EDGES_USD = (2e9, 10e9, 200e9)  # <2B / 2-10B / 10-200B / >200B
PROXIMITY_WINDOW_SESSIONS = 63             # 63-bar close-min proximity
HOT_RELVOL_DECILE = 9                      # hotness PIT proxy thresholds
HOT_ABS_RET5_DECILE = 9

# --------------------------------------------------------------------------- #
# §9 NC-2 proximity kill arm
# --------------------------------------------------------------------------- #
NC2_OVERLAP_FLOOR = 0.50                   # below => UNINFORMATIVE, never KILLED

# --------------------------------------------------------------------------- #
# §10 confirmatory family / §12 floors / §11 inference
# --------------------------------------------------------------------------- #
BH_Q = 0.10
BH_M_TOTAL = 5                             # M2: denominator fixed at the family size
NB_BOOTSTRAP = 1000
FLOOR_EPISODES_PER_ARM = 30
FLOOR_DISTINCT_MONTHS = 12
FLOOR_EFF_NAMES = 8.0                      # M3: 1/HHI over per-name episode shares
Q3_NONINFERIORITY_MARGIN_PP = -1.0         # three-state guardrail margin (§10)
Q5_FALSESTART_MARGIN_PP = 5.0              # three-state guardrail margin (§10)
Q5_INCUMBENT_JOIN_SESSIONS = 30            # NEAREST incumbent fire within ±30 (B2)
Q5_MIN_LEAD_SESSIONS = 2.0                 # B2: practically-meaningful minimum lead
ROW16_AGREEMENT_FLOOR = 0.90               # M14: below => Q1/Q5 UNINFORMATIVE
PLACEBO_R = 5                              # N8: draws per candidate, averaged

#: C32 decline-deceleration conditioner (frozen final form).
C32_FRESH_LOW_SESSIONS = 60
C32_ROC_SESSIONS = 20

#: Market-regime tag: SPY 63-session drawdown <= -10% at D => "stressed".
REGIME_DRAWDOWN_SESSIONS = 63
REGIME_DRAWDOWN_STRESSED = -0.10

# --------------------------------------------------------------------------- #
# §11 costs
# --------------------------------------------------------------------------- #
COST_TIER_FLOORS_BPS = ((50e6, 5.0), (5e6, 15.0), (0.0, 40.0))  # (ADV floor, bps/side)
ADV_WINDOW_SESSIONS = 60                   # median trailing dollar volume
SPREAD_QUOTE_LOOKBACK_MINUTES = 15         # quotes in [T-15min, T]
SPREAD_QUOTE_MAX_N = 50                    # last <=50 quotes at/before T

# --------------------------------------------------------------------------- #
# §13 look ledger — budget + the enumerated cell names (M10: the runner's
# look-logger refuses any cell outside LOOK_CELLS; that refusal is the
# mechanism behind §15.C's "undeclared look ⇒ caught")
# --------------------------------------------------------------------------- #
TRIAL_FAMILY = "entry_radar"
DECLARED_BUDGET = 253

_DETS = ("G0", "C1", "C2A", "C3", "C5")
_COHORT_KEYS = ("ipo_young", "gap_catalyst", "deep_mtf_washout",
                "full_daily_washout", "partial_shallow_washout",
                "smallcap_highvol_momentum", "damaged_trend_rebound",
                "leader_reset")

LOOK_CELLS: tuple[str, ...] = tuple(
    [f"q{i}_primary" for i in (1, 2, 3, 4, 5)]
    + ["q3_guardrail_excess", "q5_guardrail_falsestart"]
    + [f"nc2_q{i}" for i in (1, 2, 3, 4, 5)]
    + [f"fs_grid_f{int(f*100):03d}_a{int(a*100):03d}_h{h}_{d}"
       for f in SENSITIVITY_FAVORABLE for a in SENSITIVITY_ADVERSE
       for h in SENSITIVITY_HORIZONS for d in _DETS]
    + [f"sec_h{h}_{d}" for h in HORIZONS_SECONDARY for d in _DETS]
    + [f"primary_table_{d}" for d in _DETS]
    + [f"fit_table_{d}" for d in _DETS]
    + [f"cohort_{c}_{d}" for c in _COHORT_KEYS for d in _DETS]
    + [f"c32_{q}_{arm}_{coh}" for q in ("q1", "q2", "q3")
       for arm in ("with", "without") for coh in ("gapcat", "deepwash")]
    + [f"placebo_q{i}" for i in (1, 2, 3)]
    + [f"c2variant_{v}" for v in ("b", "c", "d", "e", "f")]
    + ["incumbent_table", "common_eligibility", "refusal_census",
       "survivorship_arm_q1", "basis_fidelity_row16",
       "q2_pit_clean_sensitivity"]
    + [f"regime_{r}_{d}" for r in ("stressed", "quiet") for d in _DETS]
    + [f"c4_strata_rc{n}" for n in (1, 2, 3)]
    + ["exemplar_read", "anchor_asymmetry_bounding"]
)
assert len(LOOK_CELLS) == DECLARED_BUDGET, (
    f"LOOK_CELLS enumerates {len(LOOK_CELLS)} != declared {DECLARED_BUDGET}")
assert len(set(LOOK_CELLS)) == len(LOOK_CELLS), "duplicate look cell names"

# --------------------------------------------------------------------------- #
# §11 seeds
# --------------------------------------------------------------------------- #
_SEED_NAMESPACE = "entry_radar_w5:"


def seed_for(cell: str) -> int:
    """Frozen seed rule: int(sha256("entry_radar_w5:"+cell)[:8], 16)."""
    return int(hashlib.sha256((_SEED_NAMESPACE + cell).encode("utf-8")).hexdigest()[:8], 16)


#: Confirmatory seeds pinned in the prereg §11 (tests recompute + compare).
CONFIRMATORY_SEEDS = {
    "Q1_g0_vs_controls": 3597397836,
    "Q2_c2_vs_c1minus": 2910048454,
    "Q3_c3_vs_c2": 2348434836,
    "Q4_lobe_enlisted": 3766887129,
    "Q5_g0_vs_incumbent": 3329020363,
}

# --------------------------------------------------------------------------- #
# §17 qledger registration (live-forward only; nightly reconciler only)
# --------------------------------------------------------------------------- #
QLEDGER_DESK = "entry_radar"
QLEDGER_HORIZON_D = 21                     # on-rung: grades [5, 21]; NEVER 10
REGISTRATION_NOTE = (
    "accruing forward meter; registration implies no directional performance "
    "claim; no backfill; promotion requires clearing the §11 gauntlet and "
    "DNR:KILL-WASHOUT-TURN falsifier territory."
)

AUTHORITY = {
    "can_rank": False,
    "can_size": False,
    "can_gate": False,
    "can_originate_signal": False,
    "can_escalate": False,
}

#: Live-forward ledger state while no lawful W4 spool stream exists.
WAITING_FOR_LIVE_SOURCE = "WAITING_FOR_LIVE_SOURCE"

__all__ = [n for n in dir() if not n.startswith("_")]
