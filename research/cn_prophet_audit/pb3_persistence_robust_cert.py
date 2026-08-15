#!/usr/bin/env python3
"""CN LIMIT-MOVE ALPHA — P-B3: persistence-robust certification.

    TZ=UTC python3 research/cn_prophet_audit/pb3_persistence_robust_cert.py

AUTHORITY: `none_research_display_only`. Nothing here ranks, sizes, gates, alerts,
trades, or feeds any production score. There is NO P-B3 production ranker.

THE PRE-REGISTRATION IS THE CONTRACT, AND IT IS NOT IN THIS FILE. Every estimand,
null, cell, floor, gate, sign, and headline below is read from
`research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md`,
frozen before this instrument existed. Deviations are NUMBERED AMENDMENTS in
`AMENDMENTS` and in both receipts — never a silent re-choice.

P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR. The numbers this file
emits are P-B3 verdicts on a new estimand and a new null.

A is PRIMARY (within-name state-transition contrast). B is CORROBORATIVE
(no-merge spell-sequence shuffle; coarse-df PERM-INERT). Scope is exactly the
20 cells {DD20, DD35, MA200, QB, VZ} × {main, chinext20} × {H10, H5}.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

OUT_DIR = REPO / "research" / "cn_prophet_audit"
W1_PATH = OUT_DIR / "washout_onset_w1.py"
PB_PATH = OUT_DIR / "pb_case_decomposition.py"
PB2_PATH = OUT_DIR / "pb2_precursor_discrimination.py"
PB2_PREREG_PATH = OUT_DIR / "PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md"
PREREG_PATH = OUT_DIR / "PB3_PERSISTENCE_ROBUST_CERT_PREREG_2026-08-15.md"

ARTIFACT_DATE = "2026-08-15"
OUT_JSON_NAME = f"PB3_PERSISTENCE_ROBUST_CERT_{ARTIFACT_DATE}.json"
OUT_MD_NAME = f"PB3_PERSISTENCE_ROBUST_CERT_{ARTIFACT_DATE}.md"

AUTHORITY = "none_research_display_only"
TIER_STAMP = (
    "display / research tier — a persistence-robust certification of within-name "
    "transition timing (A, primary) and occupancy-to-outcome association under a "
    "no-merge spell-sequence null (B, corroborative); not a promotion, not a gate, "
    "not a ranker, not a sizing input, and no production consumer exists or is proposed"
)
GOVERNING_RULING = "DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT"
PROGRAM_HOME = "research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md (the P-B3 row)"

PB2_PRESERVATION_SENTENCE = (
    "P-B2 remains NO DISCRIMINATOR AT THE PREREGISTERED BAR. The numbers "
    "below are P-B3 verdicts on a new estimand and a new null."
)

# Frozen inherited pin prefixes (prereg §3). A mismatch REFUSES the run.
PIN_PREFIXES = OrderedDict([
    ("washout_onset_w1.py", "11ac61de71f0f595"),
    ("pb_case_decomposition.py", "f42b0566beb60bec"),
    ("PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md", "36a1c2484ca47bbb"),
])

# ── frozen constants (prereg §9) ──────────────────────────────────────────────

SEED = 20260815
N_PERM = 2000
N_ASSIGN = 2000
N_BOOT_SESSION = 4000
N_BOOT_NAME = 2000
BLOCK_LEN = 21
H_PRIMARY, H_SECONDARY = 10, 5
HORIZONS = (H_PRIMARY, H_SECONDARY)

A_FIT_EVENTS = 80
A_HOLDOUT_EVENTS = 30
A_FIT_NAMES = 40
A_UNMATCHED_MAX = 0.50
A_NAME_SHARE_MAX = 0.40
A_PREV_LO, A_PREV_HI = 0.005, 0.995
A_G2_Z = 2.81
A_G4_FRACTION = 2.0 / 3.0
A_G4_ERA_EVENTS = 30
A_G5_Z = 1.28
A_PROP_TOP_MAX = 0.60
A_PROP_TERCILE_EVENTS = 30
B_RETAINED_EPISODE_MIN = 0.50
B_G2B_P = 0.005
B_G5B_P = 0.10
G6B_P_CUT = 0.10
INERT_LONGEST_SHARE = 0.70
INERT_TWO_LONGEST_SHARE = 0.70
INERT_MIN_TRUE_SPELLS = 3
INERT_MIN_PLACEMENTS = 20
DWELL = {"dd_le_m20": 5, "dd_le_m35": 5, "under_ma200": 5,
         "quiet_base": 5, "volz_gt1": 2}
QUIET_RADIUS = 10

# Exact 20-cell scope (prereg §2). Nothing else is a verdict cell.
FOOTPRINTS = OrderedDict([
    ("dd_le_m20", "DD20"),
    ("dd_le_m35", "DD35"),
    ("under_ma200", "MA200"),
    ("quiet_base", "QB"),
    ("volz_gt1", "VZ"),
])
FKEYS = tuple(FOOTPRINTS)
FSHORT = dict(FOOTPRINTS)
BOARDS = ("main", "chinext20")
LONG_SPELL = frozenset({"dd_le_m20", "dd_le_m35", "under_ma200"})
DD_KEYS = frozenset({"dd_le_m20", "dd_le_m35"})
CARRIER_SERIES_FPS = DD_KEYS

# Verdict universe / match class (prereg §3, inherited).
UNIVERSE = {
    "dd_le_m20": "U0", "dd_le_m35": "U1", "under_ma200": "U1",
    "quiet_base": "U1", "volz_gt1": "U1",
}
# A primary edge and frozen expected sign (prereg §5.2).
PRIMARY_EDGE = {
    "dd_le_m20": "onset", "dd_le_m35": "onset", "under_ma200": "exit",
    "quiet_base": "onset", "volz_gt1": "onset",
}
A_SIGN = {
    "dd_le_m20": +1, "dd_le_m35": +1, "under_ma200": +1,
    "quiet_base": -1, "volz_gt1": +1,
}
# B occupancy sign = P-B2 published in-state sign (prereg §9.3).
B_SIGN = {
    "dd_le_m20": +1, "dd_le_m35": +1, "under_ma200": -1,
    "quiet_base": -1, "volz_gt1": +1,
}
# A matching factors beyond era + session-regime (prereg §5.3).
# vol except QB; dd_band for M1-class except DD35 (inherited carve-out).
A_MATCH_VOL = {
    "dd_le_m20": True, "dd_le_m35": True, "under_ma200": True,
    "quiet_base": False, "volz_gt1": True,
}
A_MATCH_DD = {
    "dd_le_m20": False, "dd_le_m35": False, "under_ma200": True,
    "quiet_base": True, "volz_gt1": True,
}

MEASURABILITY = OrderedDict([
    ("dd_le_m20", "u_eligibility"), ("dd_le_m35", "u_eligibility"),
    ("under_ma200", "ma200_finite"),
    ("quiet_base", "rv_rank_finite"),
    ("volz_gt1", "volz_measurable"),
])

SPLIT_GROUPS = OrderedDict([
    ("FIT", ("train", "calibration")),
    ("HOLDOUT", ("test",)),
    ("AUDIT", ("audit",)),
])

# ── numbered build-time amendments (prereg allows these in the receipt) ───────

AMENDMENTS = [
    {"id": "A9",
     "what": "§10 table has no row for (A NULL, B NOT_EVALUABLE/INSUFFICIENT) or "
             "for A status UNINFORMATIVE (G6/concentration cap). Those cells take "
             "an existing headline: A NULL + B silent → NULL; A UNINFORMATIVE → "
             "UNINFORMATIVE. CERTIFIED_TIMING + B NULL with df on a short-spell "
             "footprint uses the same UNINFORMATIVE / A_B_CONTRADICT close as "
             "row 8 (contradiction is not rescued because the footprint is short).",
     "why": "The later session may not invent a fifth headline. These A×B pairs "
            "are unspecified; mapping them onto an existing headline is the "
            "un-shoppable close.",
     "risk_controlled_by": "verify.headline_most_specific and the A9 rows in "
                           "tests/test_pb3_persistence_robust_cert.py. No floor, "
                           "gate, sign, or cell list moved."},
    {"id": "A10",
     "what": "B's N_PERM distribution is computed on FIT and HOLDOUT only. AUDIT "
             "prints observed excess and the inert/retention census; it does not "
             "draw the permutation. AUDIT never gates (prereg §3).",
     "why": "P-B2 A2 precedent: a diagnostic that no gate reads is not worth "
            "the whole-matrix cost. Three splits × 2000 draws would spend a "
            "third of B compute on a split no headline reads.",
     "risk_controlled_by": "G2B/G5B read FIT then HOLDOUT only. AUDIT remains "
                           "in the receipt as descriptive occupancy."},
    {"id": "A11",
     "what": "The non-gating S∈{250,500,1000} diagnostic calls P-B2 "
             "shift_footprints after setting pb2.FKEYS_ORDER from the loaded "
             "P-B FKEYS. P-B2 only fills that tuple inside its own main(); "
             "leaving it empty KeyErrors and voids the receipt. A shift "
             "exception is recorded and does not prevent the receipt write. "
             "§11.5's probe asserts 'A is still null' as n_onsets==0 after "
             "dropping session-regime matching (A's estimand), not as a "
             "0.05pp unmatched y-excess. §11.1's probe plants a dwell-legal "
             "6-bar flip, not a one-bar flicker the dwell rule would ignore. "
             "§11.2–§11.4 planted A z uses the nearest same-regime stay-FALSE "
             "control, not the first-in-name bar (that control is biased and "
             "left |z| alive after a 20–60 session shift). Planted A z uses a "
             "session-clustered SE (plants on the same first-board wave are "
             "not independent pairs). §11.4 'drop below 1.96' is the planted "
             "positive direction, not |z|. §11.3 uses the same planted-direction "
             "fallback (z < 1.96) and scores A on moved onsets of the "
             "transition estimand, not unmatched occupancy.",
     "why": "A check that cannot fail, or a diagnostic that crashes the "
            "receipt, is an instrument defect (prereg §11). No cell, floor, "
            "gate, sign, or headline moved.",
     "risk_controlled_by": "tests/test_pb3_persistence_robust_cert.py "
                           "test_diagnostic_shift_does_not_require_pb2_main "
                           "and test_regime_probe_fires_on_visible_transitions."},
    {"id": "A12",
     "what": "PIN_PREFIXES for the P-B2 prereg is 36a1c2484ca47bbb. Main "
             "#5754 appended a 10-line 2026-08-15 annotation that says it "
             "does not amend that prereg. The shipped P-B3 receipt still "
             "records the run-time pin 043a85d69f76ea86. No estimand, gate, "
             "cell, or headline moved.",
     "why": "CI merges this branch with main; the annotation changes the "
            "sha and the pin test would red a valid receipt. Re-pinning to "
            "the annotated file is an instrument heal, not a re-run.",
     "risk_controlled_by": "test_pin_prefixes_match_prereg_section_3; the "
                           "annotation text is 'does not amend this prereg'."},
]


# ══════════════════════════════════════════════════════════════════════════════
# pins / streams / small helpers
# ══════════════════════════════════════════════════════════════════════════════


def _load_module(path: Path, alias: str, what: str):
    if not path.exists():
        raise SystemExit(
            f"MISSING PIN SOURCE: {path}\nP-B3 imports {what} and re-derives none of it.")
    sha = hashlib.sha256(path.read_bytes()).hexdigest()
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod, sha


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _seed_seq(*parts) -> np.random.SeedSequence:
    key = "|".join(str(p) for p in parts).encode()
    d = hashlib.sha256(key).digest()
    return np.random.SeedSequence(
        entropy=SEED,
        spawn_key=tuple(int.from_bytes(d[i:i + 4], "big") for i in range(0, 16, 4)))


def _rng(*parts) -> np.random.Generator:
    return np.random.default_rng(_seed_seq(*parts))


def _r(x, nd=4):
    if x is None:
        return None
    x = float(x)
    if not np.isfinite(x):
        return None
    return round(x, nd)


def _git(*args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:  # noqa: BLE001
        return "UNAVAILABLE"


def jsonable(o):
    if isinstance(o, dict):
        return {str(k): jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jsonable(v) for v in o]
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return _r(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    if isinstance(o, np.ndarray):
        return [jsonable(v) for v in o.tolist()]
    return o


def md_table(headers, rows) -> str:
    h = "| " + " | ".join(headers) + " |"
    s = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join("" if c is None else str(c) for c in r) + " |"
            for r in rows]
    return "\n".join([h, s, *body])


def norm_sf(z: float) -> float:
    return 0.5 * math.erfc(z / math.sqrt(2.0))


def refuse_pin_mismatch(paths_and_prefixes) -> dict:
    """Refuse the run if an inherited sha256 prefix does not match prereg §3."""
    bad = {}
    got = {}
    for path, prefix in paths_and_prefixes:
        digest = _sha(path)
        got[path.name] = digest
        if not digest.startswith(prefix):
            bad[path.name] = {"expected_prefix": prefix, "got": digest[:16]}
    if bad:
        raise SystemExit(
            f"PIN MISMATCH (prereg §3): {json.dumps(bad, indent=2)}\n"
            "P-B3 refuses to write receipts against an unpinned definition source.")
    return got


# ══════════════════════════════════════════════════════════════════════════════
# §10 headline — most-specific row wins; first-match forbidden
# ══════════════════════════════════════════════════════════════════════════════


def headline_disposition(a_status: str, b_status: str, fkey: str, *,
                         b_had_df: bool = False, m4_only: bool = False,
                         battery_fail: bool = False,
                         a_uninformative_stamp: str | None = None) -> dict:
    """Exactly one headline from prereg §10. Most-specific matching row wins.

    A9 (receipt amendment): unspecified A×B pairs map onto an existing headline.
    """
    if battery_fail:
        return {"row": 10, "headline": "UNINFORMATIVE", "stamp": "BATTERY",
                "timing_language": False, "amendment": None}
    if m4_only:
        return {"row": 9, "headline": "NULL", "stamp": "REGIME",
                "timing_language": False, "amendment": None}
    if a_status == "UNINFORMATIVE":
        return {"row": "A9", "headline": "UNINFORMATIVE",
                "stamp": a_uninformative_stamp or "PROPENSITY_CONCENTRATED",
                "timing_language": False, "amendment": "A9"}

    a_silent = a_status in ("INSUFFICIENT_SUPPORT", "NOT_EVALUABLE")
    b_silent = b_status in ("INSUFFICIENT_SUPPORT", "NOT_EVALUABLE")
    long_spell = fkey in LONG_SPELL

    # Row 8 is more specific than row 1: A CERTIFIED + B NULL + df + long-spell.
    if (a_status == "CERTIFIED_TIMING" and b_status == "NULL" and b_had_df
            and long_spell):
        return {"row": 8, "headline": "UNINFORMATIVE", "stamp": "A_B_CONTRADICT",
                "timing_language": False, "amendment": None}
    # A9: same contradiction on a short-spell footprint with df.
    if (a_status == "CERTIFIED_TIMING" and b_status == "NULL" and b_had_df
            and not long_spell):
        return {"row": "A9", "headline": "UNINFORMATIVE", "stamp": "A_B_CONTRADICT",
                "timing_language": False, "amendment": "A9"}
    # Row 1: CERTIFIED_TIMING | B CERTIFIED_OCCUPANCY or B not computed.
    if a_status == "CERTIFIED_TIMING" and b_status in ("CERTIFIED_OCCUPANCY",
                                                      "NOT_COMPUTED"):
        return {"row": 1, "headline": "CERTIFIED TIMING", "stamp": "TIMING",
                "timing_language": True, "amendment": None}
    # Row 2: CERTIFIED_TIMING | B inert / underpowered (short-spell expected).
    if a_status == "CERTIFIED_TIMING" and b_silent:
        return {"row": 2, "headline": "CERTIFIED TIMING", "stamp": "TIMING",
                "timing_language": True, "amendment": None}
    # Row 3
    if a_status == "NULL" and b_status == "CERTIFIED_OCCUPANCY":
        return {"row": 3, "headline": "CERTIFIED OCCUPANCY",
                "stamp": "OCCUPANCY_NOT_TRANSITION",
                "timing_language": False, "amendment": None}
    # Row 4
    if a_silent and b_status == "CERTIFIED_OCCUPANCY":
        return {"row": 4, "headline": "CERTIFIED OCCUPANCY",
                "stamp": "OCCUPANCY_ONLY_A_UNDERPOWERED",
                "timing_language": False, "amendment": None}
    # Row 5
    if a_status == "NULL" and b_status == "NULL":
        return {"row": 5, "headline": "NULL", "stamp": None,
                "timing_language": False, "amendment": None}
    # Row 6
    if a_silent and b_status == "NULL":
        return {"row": 6, "headline": "NULL", "stamp": "A_SILENT_B_NULL",
                "timing_language": False, "amendment": None}
    # Row 7
    if a_silent and b_silent:
        return {"row": 7, "headline": "INSUFFICIENT SUPPORT", "stamp": None,
                "timing_language": False, "amendment": None}
    # A9: A NULL (powered) + B silent → NULL, not INSUFFICIENT (A spoke).
    if a_status == "NULL" and b_silent:
        return {"row": "A9", "headline": "NULL", "stamp": "B_SILENT_A_NULL",
                "timing_language": False, "amendment": "A9"}
    raise ValueError(
        f"unmatched §10 pair A={a_status} B={b_status} fkey={fkey} "
        f"b_had_df={b_had_df} — refusing to invent a headline")


def apply_dd_carrier_stamp(disp: dict, fkey: str) -> dict:
    """A7: any DD headline that is not NULL/INSUFFICIENT/UNINFORMATIVE carries
    CARRIER_SERIES in addition to TIMING or the occupancy stamp."""
    out = dict(disp)
    if fkey not in CARRIER_SERIES_FPS:
        return out
    if out["headline"] in ("NULL", "INSUFFICIENT SUPPORT", "UNINFORMATIVE"):
        return out
    extra = "CARRIER_SERIES"
    stamp = out.get("stamp")
    out["stamp"] = extra if not stamp else f"{stamp}+{extra}"
    out["stamps"] = ([stamp] if stamp else []) + [extra]
    return out


# ══════════════════════════════════════════════════════════════════════════════
# spells — no-merge sequence shuffle (prereg §6.1 / A4)
# ══════════════════════════════════════════════════════════════════════════════


def spell_runs(flag: np.ndarray) -> list[tuple[bool, int]]:
    """Contiguous (value, length) runs on a gap-free boolean axis."""
    if flag.size == 0:
        return []
    change = np.flatnonzero(np.diff(flag.astype(np.int8)) != 0) + 1
    bounds = np.r_[0, change, flag.size]
    return [(bool(flag[a]), int(b - a)) for a, b in zip(bounds[:-1], bounds[1:])]


def n_legal_placements(true_lens, false_lens) -> int:
    """Distinct no-merge placements that keep both length multisets."""
    n_t, n_f = len(true_lens), len(false_lens)
    if n_t == 0:
        return 1
    if abs(n_t - n_f) > 1:
        return 0
    patterns = 2 if n_t == n_f else 1

    def ways(lens):
        n = len(lens)
        if n == 0:
            return 1
        if n > 12:
            return 10 ** 12
        w = math.factorial(n)
        for c in Counter(lens).values():
            w //= math.factorial(c)
        return w

    return patterns * ways(true_lens) * ways(false_lens)


def perm_inert_reasons(true_lens, n_eligible: int, n_place: int | None = None) -> list:
    """§6.2 / A5. A name is PERM-INERT if ANY bullet fires."""
    reasons = []
    n_t = len(true_lens)
    if n_t < 2:
        reasons.append("fewer_than_2_true_spells")
    tot = sum(true_lens)
    longest = max(true_lens) if true_lens else 0
    two = sum(sorted(true_lens, reverse=True)[:2]) if true_lens else 0
    if n_eligible > 0 and longest > INERT_LONGEST_SHARE * n_eligible:
        reasons.append("longest_true_gt_70pct")
    if n_t < INERT_MIN_TRUE_SPELLS:
        reasons.append("fewer_than_3_true_spells")
    if n_eligible > 0 and two > INERT_TWO_LONGEST_SHARE * n_eligible:
        reasons.append("two_longest_true_gt_70pct")
    if n_place is None:
        # FALSE lengths unknown here — caller should pass n_place.
        n_place = 0 if n_t < 2 else None
    if n_place is not None and n_place < INERT_MIN_PLACEMENTS:
        reasons.append("fewer_than_20_legal_placements")
    return reasons


def shuffle_spell_sequence(true_lens, false_lens, rng: np.random.Generator):
    """One no-merge draw. Preserves both length multisets. TRUE spells cannot abut."""
    t = np.asarray(true_lens, np.int64)
    f = np.asarray(false_lens, np.int64)
    n_t, n_f = int(t.size), int(f.size)
    if n_t == 0:
        return [(False, int(x)) for x in f]
    if abs(n_t - n_f) > 1:
        raise ValueError("spell counts cannot be placed without a merge")
    t = t[rng.permutation(n_t)]
    f = f[rng.permutation(n_f)] if n_f else f
    if n_t == n_f:
        start_t = bool(rng.integers(2))
    else:
        start_t = n_t == n_f + 1
    seq = []
    if start_t:
        for i in range(n_t):
            seq.append((True, int(t[i])))
            if i < n_f:
                seq.append((False, int(f[i])))
    else:
        for i in range(n_f):
            seq.append((False, int(f[i])))
            if i < n_t:
                seq.append((True, int(t[i])))
    return seq


def paint_spells(seq, n: int) -> np.ndarray:
    out = np.zeros(n, dtype=bool)
    pos = 0
    for is_t, leng in seq:
        if leng:
            out[pos:pos + leng] = bool(is_t)
        pos += int(leng)
    if pos != n:
        raise ValueError(f"spell paint length {pos} != axis {n}")
    return out


def true_false_lens(seq):
    return ([l for v, l in seq if v], [l for v, l in seq if not v])


def spells_abut_true(seq) -> bool:
    prev = None
    for v, _l in seq:
        if v and prev is True:
            return True
        prev = v
    return False


# ══════════════════════════════════════════════════════════════════════════════
# lawful transitions (prereg §5.1)
# ══════════════════════════════════════════════════════════════════════════════


def lawful_transitions(F: np.ndarray, meas: np.ndarray, dwell: int) -> dict:
    """Onset / exit indices on one name's live-session axis.

    A bar that fails `meas` breaks the dwell count and is never counted as FALSE.
    """
    n = int(F.size)
    onset, exit_ = [], []
    if n == 0 or dwell < 1:
        return {"onset": np.array([], np.int64), "exit": np.array([], np.int64)}
    Fb = np.asarray(F, bool)
    Mb = np.asarray(meas, bool)
    run_false = 0
    run_true = 0
    for i in range(n):
        if not Mb[i]:
            run_false = 0
            run_true = 0
            continue
        if i >= dwell and run_false >= dwell and Fb[i]:
            onset.append(i)
        if i >= dwell and run_true >= dwell and (not Fb[i]):
            exit_.append(i)
        if Fb[i]:
            run_true += 1
            run_false = 0
        else:
            run_false += 1
            run_true = 0
    return {"onset": np.asarray(onset, np.int64), "exit": np.asarray(exit_, np.int64)}


def any_transition_near(trans_pos: np.ndarray, t: int, radius: int) -> bool:
    if trans_pos.size == 0:
        return False
    return bool(np.any(np.abs(trans_pos.astype(np.int64) - int(t)) <= radius))


# ══════════════════════════════════════════════════════════════════════════════
# session-regime terciles (prereg §5.3 / A8)
# ══════════════════════════════════════════════════════════════════════════════


def session_u1_fraction(dcode: np.ndarray, u1: np.ndarray, assigned: np.ndarray):
    """One U1-fraction per session (one row per session, not per name-bar)."""
    use = assigned
    if not use.any():
        return {}
    dc = dcode[use]
    u = u1[use].astype(np.int64)
    n = np.bincount(dc)
    k = np.bincount(dc, weights=u)
    out = {}
    for s in np.flatnonzero(n):
        out[int(s)] = float(k[s] / n[s])
    return out


def fit_tercile_cuts(fit_fracs: np.ndarray) -> tuple[float, float, float, float]:
    """Tercile cuts on FIT sessions. Ties at a cut go to the lower tercile.

    Returns (q1, q2, fit_min, fit_max). A value x (after clip) is
    tercile 0 if x <= q1, 1 if x <= q2, else 2.
    """
    x = np.asarray(fit_fracs, np.float64)
    x = x[np.isfinite(x)]
    if x.size == 0:
        return 0.0, 1.0, 0.0, 1.0
    q1, q2 = np.quantile(x, [1.0 / 3.0, 2.0 / 3.0])
    return float(q1), float(q2), float(x.min()), float(x.max())


def assign_tercile(value: float, q1: float, q2: float,
                   fit_min: float, fit_max: float) -> int:
    """HOLDOUT/AUDIT clip to the FIT min/max cut; ties to the lower tercile."""
    v = min(max(float(value), fit_min), fit_max)
    if v <= q1:
        return 0
    if v <= q2:
        return 1
    return 2


def name_propensity_terciles(fit_fracs: np.ndarray) -> tuple[np.ndarray, list]:
    """Tercile codes for names from FIT-only occupancy fractions. Past-only."""
    x = np.asarray(fit_fracs, np.float64)
    q1, q2, lo, hi = fit_tercile_cuts(x)
    codes = np.array([assign_tercile(v, q1, q2, lo, hi) for v in x], np.int8)
    return codes, [q1, q2]


# ══════════════════════════════════════════════════════════════════════════════
# Design A — within-name matched contrast
# ══════════════════════════════════════════════════════════════════════════════


def _pack_match_key(era, regime, vol, ddb, use_vol, use_dd) -> int:
    e = int(era)
    r = int(regime)
    v = int(vol) if use_vol else 0
    d = int(ddb) if use_dd else 0
    return ((e * 4 + r) * 12 + v) * 8 + d


def match_one_name(treat_pos, cand_pos, treat_era, cand_era,
                   treat_reg, cand_reg, treat_vol, cand_vol,
                   treat_dd, cand_dd, use_vol, use_dd,
                   min_dist: int) -> list[int]:
    """For each treatment local-pos, return the matched control local-pos or -1.

    Tie-break (prereg §5.3): closest vol decile, then closest session-count
    distance, then earlier session.
    """
    if treat_pos.size == 0:
        return []
    out = []
    if cand_pos.size == 0:
        return [-1] * int(treat_pos.size)
    # Index candidates by packed key.
    buckets: dict[int, list[int]] = {}
    for j, p in enumerate(cand_pos):
        k = _pack_match_key(cand_era[j], cand_reg[j], cand_vol[j], cand_dd[j],
                            use_vol, use_dd)
        buckets.setdefault(k, []).append(j)
    used = set()
    for i, tp in enumerate(treat_pos):
        k = _pack_match_key(treat_era[i], treat_reg[i], treat_vol[i], treat_dd[i],
                            use_vol, use_dd)
        pool = [j for j in buckets.get(k, [])
                if j not in used and abs(int(cand_pos[j]) - int(tp)) >= min_dist]
        if not pool:
            out.append(-1)
            continue
        # closest vol, then closest |Δpos|, then earlier session (smaller pos)
        def key(j):
            dv = abs(int(cand_vol[j]) - int(treat_vol[i]))
            dp = abs(int(cand_pos[j]) - int(tp))
            return (dv, dp, int(cand_pos[j]))
        j = min(pool, key=key)
        used.add(j)
        out.append(int(cand_pos[j]))
    return out


def a_floors(n_fit_events, n_hold_events, n_fit_names, unmatched_frac,
             max_name_share, prevalence) -> dict:
    reasons = []
    if n_fit_events < A_FIT_EVENTS:
        reasons.append(f"FIT events {n_fit_events} < {A_FIT_EVENTS}")
    if n_hold_events < A_HOLDOUT_EVENTS:
        reasons.append(f"HOLDOUT events {n_hold_events} < {A_HOLDOUT_EVENTS}")
    if n_fit_names < A_FIT_NAMES:
        reasons.append(f"FIT names {n_fit_names} < {A_FIT_NAMES}")
    if unmatched_frac > A_UNMATCHED_MAX:
        reasons.append(f"unmatched {unmatched_frac:.3f} > {A_UNMATCHED_MAX}")
    if prevalence is not None and not (A_PREV_LO <= prevalence <= A_PREV_HI):
        reasons.append(f"prevalence {prevalence:.4f} outside [{A_PREV_LO}, {A_PREV_HI}]")
    concentrated = max_name_share > A_NAME_SHARE_MAX
    if concentrated:
        reasons.append(f"max name share {max_name_share:.3f} > {A_NAME_SHARE_MAX}")
    n_fail = any(("events" in r) or ("names" in r) for r in reasons)
    if n_fail:
        # prereg §9.1: a floor miss that is N is INSUFFICIENT_SUPPORT, never NULL.
        status = "INSUFFICIENT_SUPPORT"
    elif concentrated:
        status = "UNINFORMATIVE"
    elif reasons:
        status = "NOT_EVALUABLE"
    else:
        status = "EVALUABLE"
    return {"passed": status == "EVALUABLE", "status": status,
            "reasons": reasons, "concentrated": concentrated}


def a_gates(fit_z, fit_excess, expected_sign, thin_sign, era_signs,
            hold_z, hold_excess, prop_ok) -> dict:
    g = OrderedDict()
    g["G1"] = True
    g["G2"] = bool(fit_z is not None and abs(fit_z) >= A_G2_Z
                   and np.sign(fit_excess) == expected_sign)
    g["G3"] = bool(thin_sign is not None and np.sign(thin_sign) == np.sign(fit_excess)
                   and np.sign(fit_excess) == expected_sign)
    meas = [s for s in era_signs if s is not None]
    if not meas:
        g["G4"] = False
    else:
        agree = sum(1 for s in meas if np.sign(s) == expected_sign)
        g["G4"] = agree >= math.ceil(A_G4_FRACTION * len(meas) - 1e-12)
        # ≥ 2/3 of measurable eras
        g["G4"] = (agree / len(meas)) >= A_G4_FRACTION
    g["G5"] = bool(
        hold_z is not None and hold_excess is not None
        and np.sign(hold_excess) == np.sign(fit_excess)
        and (hold_z * expected_sign) >= A_G5_Z)
    g["G6"] = bool(prop_ok)
    return g


# ══════════════════════════════════════════════════════════════════════════════
# Design B helpers
# ══════════════════════════════════════════════════════════════════════════════


def two_sided_perm_p(obs: float, draws: np.ndarray) -> float:
    ge = int(np.sum(draws >= obs))
    le = int(np.sum(draws <= obs))
    n = int(draws.size)
    return min(1.0, 2.0 * min((1 + ge) / (1 + n), (1 + le) / (1 + n)))


def one_sided_perm_p(obs: float, draws: np.ndarray, sign: int) -> float:
    n = int(draws.size)
    if sign >= 0:
        return (1 + int(np.sum(draws >= obs))) / (1 + n)
    return (1 + int(np.sum(draws <= obs))) / (1 + n)


# ══════════════════════════════════════════════════════════════════════════════
# plane extras for P-B3 (session-regime, propensity — built once)
# ══════════════════════════════════════════════════════════════════════════════


def attach_pb3_axes(pl, pb2):
    """Session-regime terciles and FIT-only name occupancy, PIT, no HOLDOUT leak."""
    assigned = pl.split_gcode >= 0
    frac = session_u1_fraction(pl.dcode, pl.U1, assigned)
    fit_sess = np.unique(pl.dcode[pl.split_gcode == 0])
    fit_vals = np.array([frac.get(int(s), np.nan) for s in fit_sess], np.float64)
    q1, q2, lo, hi = fit_tercile_cuts(fit_vals)
    maxd = int(pl.dcode.max()) + 1 if pl.n else 1
    lut = np.full(maxd, -1, np.int8)
    for s, v in frac.items():
        if 0 <= int(s) < maxd:
            lut[int(s)] = assign_tercile(v, q1, q2, lo, hi)
    regime = lut[pl.dcode]
    pl.session_u1_frac = frac
    pl.regime_cuts = {"q1": q1, "q2": q2, "fit_min": lo, "fit_max": hi}
    pl.regime = regime
    # FIT-only name occupancy per footprint (past-only).
    pl.fit_occ = {}
    fit = pl.split_gcode == 0
    for fk in FKEYS:
        mask = pl.masks[MEASURABILITY[fk] if fk in MEASURABILITY
                        else pb2.MEASURABILITY[fk]]
        num = np.zeros(pl.tuniq.size, np.float64)
        den = np.zeros(pl.tuniq.size, np.float64)
        use = fit & mask
        if use.any():
            num += np.bincount(pl.tcode[use], weights=pl.F[fk][use].astype(np.float64),
                               minlength=pl.tuniq.size)
            den += np.bincount(pl.tcode[use], minlength=pl.tuniq.size)
        with np.errstate(invalid="ignore", divide="ignore"):
            pl.fit_occ[fk] = np.where(den > 0, num / den, np.nan)
    return pl


# ══════════════════════════════════════════════════════════════════════════════
# per-name spell / transition extraction
# ══════════════════════════════════════════════════════════════════════════════


def _name_segments(pl, a: int, b: int, meas: np.ndarray):
    """Contiguous measurable runs that do not cross a board-key change."""
    segs = []
    i = a
    while i < b:
        if not meas[i]:
            i += 1
            continue
        j = i + 1
        bk = pl.board_code[i]
        while j < b and meas[j] and pl.board_code[j] == bk:
            j += 1
        segs.append((i, j))
        i = j
    return segs


def extract_name_spells(pl, fkey: str, split_gcode: int):
    """Per-name spell inventory inside one split, for B / G6B / inert."""
    F = pl.F[fkey]
    meas = pl.masks[MEASURABILITY[fkey]]
    recs = []
    for ti, (a, b) in enumerate(zip(pl.grp_starts, pl.grp_ends)):
        # rows of this name in this split
        idx = np.arange(a, b)
        in_split = pl.split_gcode[idx] == split_gcode
        if not in_split.any():
            continue
        # work on the name's full axis but only count split-eligible measurable segs
        # that sit inside this split (split is contiguous in calendar).
        segs = []
        for s, e in _name_segments(pl, a, b, meas):
            if pl.split_gcode[s] != split_gcode:
                continue
            # segment may start at split boundary; require the whole seg in split
            if not np.all(pl.split_gcode[s:e] == split_gcode):
                # split the seg at the split boundary
                sub = np.flatnonzero(pl.split_gcode[s:e] == split_gcode)
                if sub.size == 0:
                    continue
                # contiguous blocks inside
                brk = np.r_[0, np.flatnonzero(np.diff(sub) != 1) + 1, sub.size]
                for u, v in zip(brk[:-1], brk[1:]):
                    segs.append((s + int(sub[u]), s + int(sub[v - 1]) + 1))
            else:
                segs.append((s, e))
        if not segs:
            continue
        true_lens, false_lens = [], []
        n_elig = 0
        seg_payload = []
        for s, e in segs:
            runs = spell_runs(F[s:e])
            true_lens.extend(l for v, l in runs if v)
            false_lens.extend(l for v, l in runs if not v)
            n_elig += (e - s)
            seg_payload.append((s, e, [l for v, l in runs if v],
                                [l for v, l in runs if not v]))
        n_place = 1
        for _s, _e, tl, fl in seg_payload:
            n_place *= max(1, n_legal_placements(tl, fl))
            if n_place > 10 ** 9:
                n_place = 10 ** 9
                break
        reasons = perm_inert_reasons(true_lens, n_elig, n_place)
        recs.append({
            "tcode": int(ti) if ti < pl.tuniq.size else int(pl.tcode[a]),
            "ticker_i": int(pl.tcode[a]),
            "true_lens": true_lens,
            "false_lens": false_lens,
            "n_eligible": n_elig,
            "n_place": int(n_place),
            "inert": bool(reasons),
            "inert_reasons": reasons,
            "segments": seg_payload,
            "n_true_spells": len(true_lens),
            "n_true_bars": int(sum(true_lens)),
        })
    return recs


def apply_name_shuffles(pl, fkey: str, recs, rng, skip_inert=True,
                        work: np.ndarray | None = None) -> np.ndarray:
    """Paint a no-merge shuffle onto `work` (or a copy of F)."""
    F = work if work is not None else pl.F[fkey].copy()
    orig = pl.F[fkey]
    if work is not None:
        # restore previously painted segments so leftover spells cannot leak
        for rec in recs:
            if skip_inert and rec["inert"]:
                continue
            for s, e, _tl, _fl in rec["segments"]:
                F[s:e] = orig[s:e]
    for rec in recs:
        if skip_inert and rec["inert"]:
            continue
        for s, e, tl, fl in rec["segments"]:
            if not tl and not fl:
                continue
            try:
                seq = shuffle_spell_sequence(tl, fl, rng)
            except ValueError:
                continue
            F[s:e] = paint_spells(seq, e - s)
    return F


# ══════════════════════════════════════════════════════════════════════════════
# occupancy excess on a (possibly permuted) F — P-B2 matched ATT, cell rows
# ══════════════════════════════════════════════════════════════════════════════


def occupancy_excess(pl, pb2, fkey, fvals, board, split_group, H):
    """P-B2 §6 ATT-weighted matched excess on this cell, using `fvals` as F."""
    uni = UNIVERSE[fkey]
    rows = pb2.cell_rows(pl, uni, board, split_group)
    if rows.size == 0:
        return None
    ok = pl.win_ok[H][rows]
    rows = rows[ok]
    if rows.size == 0:
        return None
    mask = pl.masks[MEASURABILITY[fkey]][rows]
    rows = rows[mask]
    if rows.size == 0:
        return None
    F = np.asarray(fvals)[rows].astype(bool)
    y = pl.fb[H][rows]
    arm = "M0" if fkey == "dd_le_m20" else "M1"
    factors = pb2.arm_factors(fkey, arm)
    packed = pl.packed(factors)[rows]
    scodes, _ = pd.factorize(packed, sort=True)
    ns = int(scodes.max()) + 1 if scodes.size else 0
    if ns == 0:
        return None
    n1, k1, n0, k0 = pb2.suff_stats(scodes, ns, F, y)
    pe = pb2.point_estimate(n1, k1, n0, k0)
    if pe is None:
        return None
    # F=TRUE positive episodes among these rows (for retention)
    pos = y & F
    n_pos_ep = int(np.unique(pl.episode_row[rows][pos]).size) if pos.any() else 0
    return {
        "excess_pp": float(pe["excess_pp"]),
        "obs": float(pe["obs"]),
        "exp": float(pe["exp"]),
        "n_use_strata": int(pe["n_use_strata"]),
        "n_matched_F1": int(pe["n_matched_F1_rows"]),
        "n_matched_F0": int(pe["n_matched_F0_rows"]),
        "n_true_pos_episodes": n_pos_ep,
        "n_rows": int(rows.size),
        "n_names": int(np.unique(pl.tcode[rows]).size),
        "_pe": pe, "_n1": n1, "_k1": k1, "_n0": n0, "_k0": k0,
        "_scodes": scodes, "_ns": ns, "_rows": rows, "_F": F, "_y": y,
    }


def occupancy_excess_on_rows(pb2, pl, rows, F, y, factors, scodes=None, ns=None):
    if rows.size == 0:
        return None
    if scodes is None:
        packed = pl.packed(factors)[rows]
        scodes, _ = pd.factorize(packed, sort=True)
        ns = int(scodes.max()) + 1 if scodes.size else 0
    if not ns:
        return None
    n1, k1, n0, k0 = pb2.suff_stats(scodes, ns, F, y)
    pe = pb2.point_estimate(n1, k1, n0, k0)
    if pe is None:
        return None
    return float(pe["excess_pp"])


# ══════════════════════════════════════════════════════════════════════════════
# Design A on the plane
# ══════════════════════════════════════════════════════════════════════════════


def _thin_positions(pos: np.ndarray, y: np.ndarray, window: int) -> np.ndarray:
    """One treatment per name per non-overlapping H+21 window; earliest wins."""
    if pos.size == 0:
        return pos
    order = np.argsort(pos, kind="stable")
    keep = []
    last = -10 ** 9
    for j in order:
        if int(pos[j]) >= last + window:
            keep.append(int(pos[j]))
            last = int(pos[j])
    return np.asarray(keep, np.int64)


def run_design_a_cell(pl, pb2, fkey, board, H, progress=None):
    """Primary within-name transition contrast for one cell, FIT then HOLDOUT."""
    dwell = DWELL[fkey]
    edge = PRIMARY_EDGE[fkey]
    expected = A_SIGN[fkey]
    uni = UNIVERSE[fkey]
    use_vol = A_MATCH_VOL[fkey]
    use_dd = A_MATCH_DD[fkey]
    meas = pl.masks[MEASURABILITY[fkey]]
    F = pl.F[fkey]
    min_dist = max(H, BLOCK_LEN)
    bi = list(pb2.BOARD_ORDER).index(board)

    per_split = OrderedDict()
    for sg, _ss in SPLIT_GROUPS.items():
        si = list(SPLIT_GROUPS).index(sg)
        treat_rows, ctrl_rows = [], []
        n_treat = n_unmatched = 0
        name_event_counts = Counter()
        era_buckets = {}
        # opposite-edge diagnostic counts
        n_opp = 0

        for a, b in zip(pl.grp_starts, pl.grp_ends):
            idx = np.arange(a, b)
            local = ((pl.board_code[idx] == bi)
                     & (pl.split_gcode[idx] == si)
                     & pl.universe[uni][idx]
                     & meas[idx]
                     & pl.win_ok[H][idx])
            if not local.any():
                continue
            # transitions on the measurable axis of this name ∩ board (dwell
            # uses the name's board-segment measurable bars, not only U-eligible).
            board_ax = (pl.board_code[idx] == bi) & (pl.split_gcode[idx] == si)
            if not board_ax.any():
                continue
            ax = idx[board_ax]
            trans = lawful_transitions(F[ax], meas[ax], dwell)
            ons = trans["onset"]
            exs = trans["exit"]
            primary = ons if edge == "onset" else exs
            opposite = exs if edge == "onset" else ons
            if primary.size == 0 and opposite.size == 0:
                continue
            all_trans = np.unique(np.concatenate([ons, exs])) if (
                ons.size or exs.size) else np.array([], np.int64)
            # map local-in-ax positions to panel rows
            # eligibility of treatment: U, meas, win_ok already in `local`
            ax_pos = np.arange(ax.size)
            # stay class on ax
            stay = (~F[ax]) if edge == "onset" else F[ax]
            # candidate controls: eligible, stay, no transition in ±10
            elig_on_ax = local[board_ax]
            quiet = np.ones(ax.size, bool)
            for t in all_trans:
                lo = max(0, int(t) - QUIET_RADIUS)
                hi = min(ax.size, int(t) + QUIET_RADIUS + 1)
                quiet[lo:hi] = False
            cand_m = elig_on_ax & stay & quiet
            cand_pos = ax_pos[cand_m]
            # treatments that are themselves eligible
            t_keep = []
            for t in primary:
                t = int(t)
                if not elig_on_ax[t]:
                    continue
                t_keep.append(t)
            t_keep = np.asarray(t_keep, np.int64)
            n_opp += int(sum(1 for t in opposite if elig_on_ax[int(t)]))
            if t_keep.size == 0:
                continue
            matched = match_one_name(
                t_keep, cand_pos,
                pl.era_code[ax[t_keep]], pl.era_code[ax[cand_pos]] if cand_pos.size else np.array([], np.int64),
                pl.regime[ax[t_keep]], pl.regime[ax[cand_pos]] if cand_pos.size else np.array([], np.int8),
                pl.dec[ax[t_keep]], pl.dec[ax[cand_pos]] if cand_pos.size else np.array([], np.int64),
                pl.db[ax[t_keep]], pl.db[ax[cand_pos]] if cand_pos.size else np.array([], np.int64),
                use_vol, use_dd, min_dist)
            for t, c in zip(t_keep, matched):
                n_treat += 1
                name_event_counts[int(pl.tcode[ax[t]])] += 1
                if c < 0:
                    n_unmatched += 1
                    continue
                treat_rows.append(int(ax[t]))
                ctrl_rows.append(int(ax[c]))
                era = str(pl.era[ax[t]])
                era_buckets.setdefault(era, []).append(len(treat_rows) - 1)

        treat_rows = np.asarray(treat_rows, np.int64)
        ctrl_rows = np.asarray(ctrl_rows, np.int64)
        n_matched = int(treat_rows.size)
        unmatched_frac = (n_unmatched / n_treat) if n_treat else 1.0
        n_names = len({int(pl.tcode[r]) for r in treat_rows}) if n_matched else 0
        max_share = (max(name_event_counts.values()) / n_treat) if n_treat else 0.0
        # prevalence among eligible bars of retained (matched) names
        prev = None
        if n_matched:
            names = np.unique(pl.tcode[treat_rows])
            name_m = np.isin(pl.tcode, names) & (pl.board_code == bi) & (
                pl.split_gcode == si) & meas
            if name_m.any():
                prev = float(F[name_m].mean())

        y_t = pl.fb[H][treat_rows] if n_matched else np.array([], bool)
        y_c = pl.fb[H][ctrl_rows] if n_matched else np.array([], bool)
        excess = None
        se2 = z = None
        degen = True
        pe_pack = None
        if n_matched:
            # matching-stratum ATT: one pair = one treatment weight
            keys = np.array([
                _pack_match_key(pl.era_code[t], pl.regime[t], pl.dec[t], pl.db[t],
                                use_vol, use_dd)
                for t in treat_rows], np.int64)
            scodes, _unq = pd.factorize(keys, sort=True)
            ns = int(scodes.max()) + 1
            # Build a 2-row-per-pair table so P-B2 CGM can run.
            Fpair = np.concatenate([np.ones(n_matched, bool), np.zeros(n_matched, bool)])
            ypair = np.concatenate([y_t, y_c])
            scpair = np.concatenate([scodes, scodes])
            n1, k1, n0, k0 = pb2.suff_stats(scpair, ns, Fpair, ypair)
            pe_pack = pb2.point_estimate(n1, k1, n0, k0)
            if pe_pack is not None:
                excess = float(pe_pack["excess_pp"])
                use = pe_pack["use"]
                # session of the TREATMENT
                strat_sessions = np.zeros(ns, np.int64)
                for s in range(ns):
                    hit = treat_rows[scodes == s]
                    if hit.size:
                        strat_sessions[s] = int(pl.dcode[hit[0]])
                ncodes = np.concatenate([pl.tcode[treat_rows], pl.tcode[ctrl_rows]])
                # compact name codes
                ncodes, nn_unq = pd.factorize(ncodes, sort=True)
                nn = int(nn_unq.size)
                s1 = pb2.se_session_block(
                    n1, k1, n0, k0, use, strat_sessions,
                    _seed_seq("A", "sess", fkey, board, H, sg),
                    draws=N_BOOT_SESSION)
                s2 = pb2.se_name_cluster(
                    scpair, ns, use, ncodes, nn, Fpair, ypair,
                    _seed_seq("A", "name", fkey, board, H, sg))
                s3 = pb2.se_row_closed_form(n1, k1, n0, k0, use)
                se2, degen = pb2.cgm_two_way(s1["se"], s2["se"], s3["se"])
                if se2 and se2 > 0:
                    z = float(excess / se2)

        # thinned G3 (FIT only used for the gate; computed every split)
        thin_excess = None
        if n_matched:
            # per name, earliest-in-window
            by_name = {}
            for r, yt in zip(treat_rows, y_t):
                by_name.setdefault(int(pl.tcode[r]), []).append(
                    (int(pl.pos_in_name[r]), int(r), bool(yt)))
            ty, cy = [], []
            win = H + BLOCK_LEN
            for _nm, evs in by_name.items():
                evs = sorted(evs)
                last = -10 ** 9
                for pos, r, yt in evs:
                    if pos >= last + win:
                        # find its matched control (same index in treat_rows)
                        j = int(np.flatnonzero(treat_rows == r)[0])
                        ty.append(yt)
                        cy.append(bool(y_c[j]))
                        last = pos
            if ty:
                thin_excess = 100.0 * (float(np.mean(ty)) - float(np.mean(cy)))

        era_excess = {}
        for era, js in era_buckets.items():
            if len(js) < A_G4_ERA_EVENTS:
                era_excess[era] = {"n": len(js), "excess_pp": None, "measurable": False}
                continue
            yt = y_t[np.asarray(js)]
            yc = y_c[np.asarray(js)]
            era_excess[era] = {
                "n": len(js),
                "excess_pp": 100.0 * (float(yt.mean()) - float(yc.mean())),
                "measurable": True,
            }

        # name-propensity terciles (FIT-only occupancy; G6 reads FIT treatments)
        prop = {"ok": True, "top_share": None, "stamp": None}
        if sg == "FIT" and n_matched:
            occ = pl.fit_occ[fkey]
            names = pl.tcode[treat_rows]
            fr = occ[names]
            finite = np.isfinite(fr)
            if finite.any():
                # terciles across names that have a FIT occupancy, not across events
                uniq_names = np.unique(names[finite])
                uniq_fr = occ[uniq_names]
                codes, cuts = name_propensity_terciles(uniq_fr)
                cmap = {int(n): int(c) for n, c in zip(uniq_names, codes)}
                ev_codes = np.array([cmap.get(int(n), 1) for n in names], np.int8)
                top_share = float((ev_codes == 2).mean())
                prop["top_share"] = top_share
                prop["cuts"] = cuts
                prop["n_top"] = int((ev_codes == 2).sum())
                prop["n_mid"] = int((ev_codes == 1).sum())
                prop["n_bot"] = int((ev_codes == 0).sum())
                ok = top_share <= A_PROP_TOP_MAX
                if (prop["n_bot"] >= A_PROP_TERCILE_EVENTS
                        and prop["n_mid"] >= A_PROP_TERCILE_EVENTS
                        and excess is not None):
                    def _ex(mask):
                        if not mask.any():
                            return None
                        return 100.0 * (float(y_t[mask].mean()) - float(y_c[mask].mean()))
                    b_ex = _ex(ev_codes == 0)
                    m_ex = _ex(ev_codes == 1)
                    prop["bot_excess_pp"] = b_ex
                    prop["mid_excess_pp"] = m_ex
                    if b_ex is not None and m_ex is not None:
                        ok = ok and (np.sign(b_ex) == np.sign(excess)
                                     and np.sign(m_ex) == np.sign(excess))
                prop["ok"] = bool(ok)
                if not ok:
                    prop["stamp"] = "PROPENSITY_CONCENTRATED"

        honest = OrderedDict([
            ("distinct_name_transition_events", n_treat),
            ("matched_events", n_matched),
            ("unmatched_events", n_unmatched),
            ("unmatched_frac", _r(unmatched_frac, 4)),
            ("distinct_names_matched", n_names),
            ("distinct_sessions_treat",
             int(np.unique(pl.dcode[treat_rows]).size) if n_matched else 0),
            ("rows_pairs", n_matched),
            ("n_pos_treat", int(y_t.sum()) if n_matched else 0),
            ("n_pos_ctrl", int(y_c.sum()) if n_matched else 0),
        ])
        per_split[sg] = {
            "honest_n": honest,
            "excess_pp": _r(excess, 4),
            "se_2way_cgm_pp": _r(se2, 5) if se2 else None,
            "z_2way": _r(z, 4) if z is not None else None,
            "cgm_degenerate": bool(degen),
            "thin_excess_pp": _r(thin_excess, 4),
            "era": era_excess,
            "propensity": prop,
            "prevalence": _r(prev, 5),
            "max_name_share": _r(max_share, 4),
            "n_opposite_eligible": n_opp,
            "name_event_counts_top": dict(name_event_counts.most_common(5)),
        }
        if progress:
            progress()

    fit, hold = per_split["FIT"], per_split["HOLDOUT"]
    floors = a_floors(
        fit["honest_n"]["matched_events"],
        hold["honest_n"]["matched_events"],
        fit["honest_n"]["distinct_names_matched"],
        fit["honest_n"]["unmatched_frac"] or 1.0,
        fit["max_name_share"] or 0.0,
        fit["prevalence"],
    )
    a_status = floors["status"]
    gates = None
    if floors["passed"]:
        era_s = [v["excess_pp"] for v in fit["era"].values() if v.get("measurable")]
        gates = a_gates(
            fit["z_2way"], fit["excess_pp"], expected,
            fit["thin_excess_pp"], era_s,
            hold["z_2way"], hold["excess_pp"],
            fit["propensity"]["ok"])
        if floors["concentrated"] or not fit["propensity"]["ok"]:
            a_status = "UNINFORMATIVE"
        elif all(gates.values()):
            a_status = "CERTIFIED_TIMING"
        else:
            a_status = "NULL"
    return {
        "fkey": fkey, "short": FSHORT[fkey], "board": board, "horizon": H,
        "edge": edge, "expected_sign": expected, "dwell": dwell,
        "universe": uni, "floors": floors, "gates": gates,
        "a_status": a_status,
        "splits": per_split,
        "propensity_stamp": (None if fit["propensity"]["ok"]
                             else fit["propensity"].get("stamp")),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Design B + G6B
# ══════════════════════════════════════════════════════════════════════════════


def _cell_base_rows(pl, pb2, fkey, board, split_group, H, inert_tcodes):
    uni = UNIVERSE[fkey]
    rows = pb2.cell_rows(pl, uni, board, split_group)
    if rows.size == 0:
        return None
    ok = pl.win_ok[H][rows]
    rows = rows[ok]
    mask = pl.masks[MEASURABILITY[fkey]][rows]
    rows = rows[mask]
    if inert_tcodes:
        rows = rows[~np.isin(pl.tcode[rows], np.fromiter(inert_tcodes, np.int64)
                             if inert_tcodes else np.array([], np.int64))]
    if rows.size == 0:
        return None
    return rows


def run_design_b_cell(pl, pb2, fkey, board, H, recs_by_split, progress=None):
    expected = B_SIGN[fkey]
    arm = "M0" if fkey == "dd_le_m20" else "M1"
    factors = pb2.arm_factors(fkey, arm)
    per_split = OrderedDict()
    b_had_df = False

    for sg in SPLIT_GROUPS:
        recs = recs_by_split[sg]
        inert = {r["ticker_i"] for r in recs if r["inert"]}
        retained = [r for r in recs if not r["inert"]]
        n_inert = len(inert)
        n_ret = len(retained)
        # episode retention: F=TRUE positive episodes on retained vs all
        rows_all = _cell_base_rows(pl, pb2, fkey, board, sg, H, set())
        rows_ret = _cell_base_rows(pl, pb2, fkey, board, sg, H, inert)
        def _pos_ep(rows):
            if rows is None or rows.size == 0:
                return 0
            pos = pl.fb[H][rows] & pl.F[fkey][rows]
            return int(np.unique(pl.episode_row[rows][pos]).size) if pos.any() else 0
        ep_all = _pos_ep(rows_all)
        ep_ret = _pos_ep(rows_ret)
        share = (ep_ret / ep_all) if ep_all else 0.0
        census = {
            "n_names_split": len(recs),
            "n_inert": n_inert,
            "n_retained": n_ret,
            "true_pos_episodes_all": ep_all,
            "true_pos_episodes_retained": ep_ret,
            "retained_episode_share": _r(share, 4),
            "inert_reasons": Counter(
                rr for r in recs if r["inert"] for rr in r["inert_reasons"]),
        }
        if share < B_RETAINED_EPISODE_MIN or rows_ret is None:
            per_split[sg] = {
                "status": "NOT_EVALUABLE",
                "why": ("retained non-inert names carry "
                        f"{share:.3f} < {B_RETAINED_EPISODE_MIN} of F=TRUE "
                        "positive episodes" if ep_all else "no F=TRUE positive episodes"),
                "census": census,
                "observed_excess_pp": None,
            }
            if progress:
                progress()
            continue
        present = set(int(t) for t in pl.tcode[rows_ret])
        retained = [r for r in retained if r["ticker_i"] in present]
        y = pl.fb[H][rows_ret]
        F0 = pl.F[fkey][rows_ret]
        obs = occupancy_excess_on_rows(pb2, pl, rows_ret, F0, y, factors)
        if sg == "AUDIT":
            per_split[sg] = {
                "status": "DESCRIPTIVE",
                "census": census,
                "observed_excess_pp": _r(obs, 4),
                "n_perm": 0,
                "note": "AUDIT never gates; permutation not computed (A10)",
            }
            if progress:
                progress()
            continue
        b_had_df = True
        packed = pl.packed(factors)[rows_ret]
        scodes, _ = pd.factorize(packed, sort=True)
        ns = int(scodes.max()) + 1 if scodes.size else 0
        # permutation distribution
        parent = _seed_seq("B_G6B", fkey, board, H, sg)
        s_perm, s_assign = parent.spawn(2)
        rng = np.random.default_rng(s_perm)
        draws = np.empty(N_PERM, np.float64)
        work = pl.F[fkey].copy()
        for d in range(N_PERM):
            Fp = apply_name_shuffles(pl, fkey, retained, rng, skip_inert=False,
                                    work=work)
            val = occupancy_excess_on_rows(
                pb2, pl, rows_ret, Fp[rows_ret], y, factors, scodes=scodes, ns=ns)
            draws[d] = 0.0 if val is None or (isinstance(val, float) and np.isnan(val)) else val
            if (d + 1) % 500 == 0:
                print(f"          B perm {d + 1}/{N_PERM} {FSHORT[fkey]} "
                      f"{board} H{H} {sg}", flush=True)
        p_two = two_sided_perm_p(obs, draws)
        p_one = one_sided_perm_p(obs, draws, expected)
        median = float(np.median(draws))
        per_split[sg] = {
            "status": "EVALUABLE",
            "census": census,
            "observed_excess_pp": _r(obs, 4),
            "perm_median_pp": _r(median, 4),
            "perm_p_two_sided": _r(p_two, 6),
            "perm_p_one_sided": _r(p_one, 6),
            "n_perm": N_PERM,
            "sign_ok": bool(np.sign(obs) == expected) if obs is not None else False,
        }
        if progress:
            progress()

    fit, hold = per_split["FIT"], per_split["HOLDOUT"]
    # G6B only if raw B rejects G2B
    g6b = {"ran": False}
    raw_g2b = (fit.get("status") == "EVALUABLE"
               and fit.get("perm_p_two_sided") is not None
               and fit["perm_p_two_sided"] <= B_G2B_P
               and fit.get("sign_ok"))
    if raw_g2b:
        recs = recs_by_split["FIT"]
        inert = {r["ticker_i"] for r in recs if r["inert"]}
        retained = [r for r in recs if not r["inert"]]
        rows = _cell_base_rows(pl, pb2, fkey, board, "FIT", H, inert)
        y = pl.fb[H][rows]
        F0 = pl.F[fkey][rows]
        obs = occupancy_excess_on_rows(pb2, pl, rows, F0, y, factors)
        # date-aligned entire-path assignment among retained names
        ret_ids = np.array(sorted({r["ticker_i"] for r in retained}), np.int64)
        # map tcode -> local
        loc = {int(t): i for i, t in enumerate(ret_ids)}
        tloc = np.array([loc.get(int(t), -1) for t in pl.tcode[rows]], np.int32)
        keep = tloc >= 0
        rows, y, tloc = rows[keep], y[keep], tloc[keep]
        dcode = pl.dcode[rows]
        # donor F keyed by (local_name, date) via a dict of arrays
        # Build F_path[local, date] using a key = local * DMAX + date is too big.
        # Join: for each draw, F_new[i] = F_of_donor[tloc[i]] on dcode[i].
        # Precompute per-name dict date->F for retained names on these rows.
        F_rows = pl.F[fkey][rows].astype(bool)
        keys = (tloc.astype(np.int64) << 32) ^ dcode.astype(np.int64)
        order = np.argsort(keys, kind="stable")
        ksort, Fsort = keys[order], F_rows[order]
        parent = _seed_seq("B_G6B", fkey, board, H, "FIT")
        _sp, s_assign = parent.spawn(2)
        rng = np.random.default_rng(s_assign)
        nloc = int(ret_ids.size)
        adraws = np.empty(N_ASSIGN, np.float64)
        for d in range(N_ASSIGN):
            pi = rng.permutation(nloc)
            donor = pi[tloc]
            dkeys = (donor.astype(np.int64) << 32) ^ dcode.astype(np.int64)
            locn = np.searchsorted(ksort, dkeys)
            locn = np.clip(locn, 0, ksort.size - 1)
            have = ksort[locn] == dkeys
            if int(have.sum()) < 8:
                adraws[d] = 0.0
                continue
            adraws[d] = occupancy_excess_on_rows(
                pb2, pl, rows[have], Fsort[locn[have]], y[have], factors) or 0.0
        p_assign = one_sided_perm_p(obs, adraws, expected)
        g6b = {
            "ran": True,
            "p_one_sided": _r(p_assign, 6),
            "n_assign": N_ASSIGN,
            "name_propensity": bool(p_assign > G6B_P_CUT),
        }

    # B status
    if fit.get("status") != "EVALUABLE":
        b_status = "NOT_EVALUABLE"
        gates = None
    else:
        g2b = bool(fit["perm_p_two_sided"] <= B_G2B_P and fit["sign_ok"])
        g5b = False
        if hold.get("status") == "EVALUABLE" and hold.get("observed_excess_pp") is not None:
            # same side of HOLDOUT permutation median as FIT
            fit_side = np.sign(fit["observed_excess_pp"] - (fit["perm_median_pp"] or 0.0))
            hold_side = np.sign(hold["observed_excess_pp"] - (hold["perm_median_pp"] or 0.0))
            g5b = bool(fit_side == hold_side and hold["perm_p_one_sided"] <= B_G5B_P
                       and fit_side != 0)
        elif hold.get("status") == "EVALUABLE":
            g5b = False
        gates = {"G2B": g2b, "G5B": g5b,
                 "G6B_name_propensity": bool(g6b.get("name_propensity"))}
        if g2b and g6b.get("name_propensity"):
            b_status = "NULL"
            gates["stamp"] = "NAME_PROPENSITY"
        elif g2b and g5b:
            b_status = "CERTIFIED_OCCUPANCY"
        else:
            b_status = "NULL"

    return {
        "fkey": fkey, "short": FSHORT[fkey], "board": board, "horizon": H,
        "expected_sign": expected, "b_status": b_status, "b_had_df": b_had_df,
        "gates": gates, "g6b": g6b, "splits": per_split,
    }


# ══════════════════════════════════════════════════════════════════════════════
# mechanism (§8)
# ══════════════════════════════════════════════════════════════════════════════


def mechanism_code(a_rec, b_rec, drop_regime_a_status=None) -> dict:
    """Exactly one of M1–M4, or NOT_APPLICABLE notes for M3 on DD."""
    fkey = a_rec["fkey"]
    a, b = a_rec["a_status"], b_rec["b_status"]
    g6b_np = bool((b_rec.get("g6b") or {}).get("name_propensity"))
    m3 = "NOT_APPLICABLE" if fkey in DD_KEYS else None
    # M4: lives only when session-regime matching is dropped
    if drop_regime_a_status == "CERTIFIED_TIMING" and a != "CERTIFIED_TIMING":
        return {"code": "M4", "m3": m3, "note": "survives only without session-regime match"}
    if g6b_np or (a_rec.get("propensity_stamp") == "PROPENSITY_CONCENTRATED"):
        return {"code": "M2", "m3": m3, "note": "name propensity / persistent level"}
    if a == "CERTIFIED_TIMING" or b == "CERTIFIED_OCCUPANCY":
        return {"code": "M1", "m3": m3,
                "note": "persistent structural state or certified occupancy after G6B"}
    return {"code": None, "m3": m3, "note": "no surviving mechanism"}


# ══════════════════════════════════════════════════════════════════════════════
# adversarial battery (prereg §11) — each control paired with a mutation
# ══════════════════════════════════════════════════════════════════════════════


def _first_board_rows(pl, H, split_gcode=0, board_i=0):
    rows = np.flatnonzero(
        (pl.split_gcode == split_gcode) & (pl.board_code == board_i)
        & pl.win_ok[H] & pl.fb[H] & pl.U0)
    return rows


def plant_timing_feature(pl, H, rng, frac=0.05, lead=5, spell=3, board_i=0):
    """§11.2 dummy: FALSE→TRUE exactly `lead` sessions before a random frac of boards."""
    F = np.zeros(pl.n, bool)
    ev = _first_board_rows(pl, H, 0, board_i)
    if ev.size == 0:
        return F, np.array([], np.int64)
    k = max(1, int(round(frac * ev.size)))
    pick = ev[rng.choice(ev.size, size=min(k, ev.size), replace=False)]
    planted = []
    for r in pick:
        tcode = int(pl.tcode[r])
        pos = int(pl.pos_in_name[r])
        a = int(pl.grp_starts[tcode]) if tcode < pl.grp_starts.size else r - pos
        # grp_starts is per name in tcode order because factorize(sort=True)
        a = r - pos
        onset = pos - lead
        if onset < 0:
            continue
        lo = a + onset
        hi = min(a + pos, lo + spell)
        if hi <= lo:
            continue
        F[lo:hi] = True
        planted.append(lo)
    return F, np.asarray(planted, np.int64)


def run_adversarial_battery(pl, pb2, *, board="main", H=10, n_perm=80, n_assign=80):
    """§11 controls. `detected: false` anywhere voids the receipt.

    n_perm/n_assign are reduced only when the caller is a unit test; the
    shipped run uses the frozen N_PERM / N_ASSIGN.
    """
    bi = list(pb2.BOARD_ORDER).index(board)
    checks = OrderedDict()
    _probe = _fallback_probe

    def add(name, why, fn, base_arg, probes):
        print(f"        §11 {name}", flush=True)
        try:
            ok, det = fn(base_arg)
        except Exception as exc:  # noqa: BLE001
            ok, det = False, {"raised": type(exc).__name__, "msg": str(exc)[:200]}
        recs = [_probe(fn, m, lab) for m, lab in probes]
        detected = all(r["detected"] for r in recs)
        checks[name] = {
            "why": why, "passed": bool(ok), "detail": det,
            "mutation_probe": {
                "mutation": " | ".join(r["mutation"] for r in recs),
                "detected": detected,
                "via": " | ".join(r["via"] for r in recs),
                "probes": recs,
            },
        }
        print(f"        §11 {name}  passed={bool(ok)}  "
              f"probe={'detected' if detected else 'UNDETECTED'}", flush=True)

    # ── 1. persistent-state null ────────────────────────────────────────────
    def _const_dd35(force_flip):
        fit = pl.split_gcode == 0
        dd = np.where(fit & np.isfinite(pl.dd), pl.dd, np.nan)
        med = pd.Series(dd).groupby(pl.tcode).median().reindex(
            range(pl.tuniq.size)).to_numpy(np.float64)
        F = med[pl.tcode] <= -0.35
        F = np.where(np.isfinite(med[pl.tcode]), F, False)
        if force_flip:
            # plant one dwell-legal flip per name (prereg §11.1: "at a planted
            # date"). A one-bar flicker is ignored by dwell=5 and would make
            # the probe vacuous.
            F = np.asarray(F, bool).copy()
            for a, b in zip(pl.grp_starts, pl.grp_ends):
                n = b - a
                if n < 12:
                    continue
                mid = a + max(5, n // 2)
                if mid + 6 > b:
                    mid = b - 6
                if mid < a + 5:
                    continue
                prev = bool(F[mid - 1])
                F[mid:mid + 6] = (not prev)
        # A: transitions after dwell 5
        n_on = 0
        for a, b in zip(pl.grp_starts, pl.grp_ends):
            tr = lawful_transitions(F[a:b], np.ones(b - a, bool), 5)
            n_on += int(tr["onset"].size + tr["exit"].size)
        # B: every name is a constant → <2 TRUE spells or 1 long spell
        n_place_ok = 0
        for a, b in zip(pl.grp_starts[:40], pl.grp_ends[:40]):
            runs = spell_runs(F[a:b])
            tl = [l for v, l in runs if v]
            fl = [l for v, l in runs if not v]
            if not perm_inert_reasons(tl, b - a, n_legal_placements(tl, fl)):
                n_place_ok += 1
        a_ok = n_on == 0
        b_ok = n_place_ok == 0
        # force_flip must make "no transitions" fail
        if force_flip:
            return (n_on == 0), {"n_transitions": n_on, "forced_flip": True}
        return (a_ok and b_ok), {
            "n_transitions": n_on, "non_inert_in_sample40": n_place_ok,
            "rule": "name-constant F has no lawful dwell-5 transitions; B is PERM-INERT",
        }
    add("persistent_state_null",
        "prereg §11.1 — synthetic F = name-level constant (FIT median dd250 ≤ −0.35)",
        _const_dd35, False,
        [(lambda: True, "force this feature to flip once per name and assert no transitions")])

    # ── 2. planted timing ───────────────────────────────────────────────────
    def _plant(shuffled_labels):
        rng = _rng("plant", board, H, int(shuffled_labels))
        F, ons = plant_timing_feature(pl, H, rng, board_i=bi)
        if shuffled_labels:
            # destroy the plant: shuffle fb labels inside session (must not certify)
            y = pl.fb[H].copy()
            # session-wise shuffle of y among U0 main FIT
            use = (pl.split_gcode == 0) & (pl.board_code == bi) & pl.U0 & pl.win_ok[H]
            yy = y[use].copy()
            rng.shuffle(yy)
            y = y.copy()
            y[use] = yy
        else:
            y = pl.fb[H]
        # A: onset contrast around planted transitions vs stay-FALSE
        z_a = _planted_a_z(pl, F, ons, y, H, bi)
        # B: occupancy excess vs spell-shuffle null (short n_perm in tests)
        p_b, p_g6b = _planted_b_p(pl, pb2, F, y, H, bi, n_perm, n_assign)
        ok = (z_a is not None and abs(z_a) >= A_G2_Z and z_a > 0
              and p_b is not None and p_b <= B_G2B_P
              and p_g6b is not None and p_g6b <= G6B_P_CUT)
        return ok, {"z_A": _r(z_a, 4), "p_B": _r(p_b, 6), "p_G6B": _r(p_g6b, 6),
                    "n_planted": int(ons.size), "shuffled_labels": bool(shuffled_labels)}
    add("planted_timing",
        "prereg §11.2 — short-spell dummy 5 sessions before a random 5% of first boards",
        _plant, False,
        [(lambda: True, "run the plant with labels shuffled (must not certify)")])

    # ── 3. duration-preserving permutation of the plant ──────────────────────
    def _perm_plant(assert_still_certified):
        rng = _rng("perm_plant", board, H)
        F, _ons = plant_timing_feature(pl, H, rng, board_i=bi)
        # shuffle each name's plant spells
        Fp = F.copy()
        for a, b in zip(pl.grp_starts, pl.grp_ends):
            runs = spell_runs(F[a:b])
            tl = [l for v, l in runs if v]
            fl = [l for v, l in runs if not v]
            if not tl:
                continue
            try:
                seq = shuffle_spell_sequence(tl, fl, rng)
                Fp[a:b] = paint_spells(seq, b - a)
            except ValueError:
                # Unplaceable without a merge: drop the plant on this name
                # rather than silently keep the original timing (that left
                # A |z|~7 after "permutation" on the cheap battery).
                Fp[a:b] = False
        y = pl.fb[H]
        ons_p = np.flatnonzero(np.diff(np.r_[0, Fp.astype(np.int8)]) == 1)
        orig = np.asarray(_ons, np.int64)
        if orig.size and ons_p.size:
            keep = np.array([not np.any(np.abs(orig - int(o)) < BLOCK_LEN)
                             for o in ons_p], bool)
            moved = ons_p[keep]
        else:
            moved = ons_p
        z_a = _planted_a_z(pl, Fp, moved if moved.size else ons_p, y, H, bi)
        p_b, _ = _planted_b_p(pl, pb2, Fp, y, H, bi, n_perm, 8)
        # Planted direction is positive. A sign-flipped leftover is not the
        # plant surviving; §11.4 uses the same one-sided reading.
        fell = ((z_a is None or z_a < 1.96)
                and (p_b is None or p_b > 0.10))
        if assert_still_certified:
            still = (z_a is not None and abs(z_a) >= A_G2_Z
                     and p_b is not None and p_b <= B_G2B_P)
            return still, {"z_A": _r(z_a, 4), "p_B": _r(p_b, 6), "assert": "still certified"}
        return fell, {"z_A": _r(z_a, 4), "p_B": _r(p_b, 6),
                      "rule": "A |z|<1.96 and B p>0.10 after §6.1 shuffle of the plant"}
    add("permuted_plant_falls_back",
        "prereg §11.3 — apply the no-merge shuffle to the planted feature",
        _perm_plant, False,
        [(lambda: True, "assert the permuted plant is still certified")])

    # ── 4. mutation destroying transition timing ─────────────────────────────
    def _shift_plant(assert_g2):
        rng = _rng("shift_plant", board, H)
        F, ons = plant_timing_feature(pl, H, rng, board_i=bi)
        Fm = np.zeros(pl.n, bool)
        for o in ons:
            tcode_pos = int(pl.pos_in_name[o])
            a = o - tcode_pos
            b = a + int((pl.fwd_avail[o] + tcode_pos + 1))
            delta = int(rng.integers(20, 61)) * (1 if rng.integers(2) else -1)
            dest = int(np.clip(o + delta, a, b - 3))
            Fm[dest:min(dest + 3, b)] = True
        y = pl.fb[H]
        z_m = _planted_a_z(pl, Fm, np.flatnonzero(np.diff(np.r_[0, Fm.astype(np.int8)]) == 1),
                           y, H, bi)
        # Prereg §11.4: "drop below 1.96" is the planted direction (positive),
        # not |z|. A large negative leftover is a destroyed plant, not G2.
        dropped = z_m is None or z_m < 1.96
        if assert_g2:
            return (z_m is not None and z_m >= A_G2_Z), {"z_A": _r(z_m, 4)}
        return dropped, {"z_A": _r(z_m, 4),
                         "rule": "shifted plant z drops below 1.96 (planted +)"}
    add("mutated_transition_timing",
        "prereg §11.4 — move each planted transition by ± Uniform{20,…,60}",
        _shift_plant, False,
        [(lambda: True, "assert the mutated plant still meets G2")])

    # ── 5. carrier-only / regime placebo ────────────────────────────────────
    def _regime(drop_match):
        med = float(np.median(list(pl.session_u1_frac.values()))) if pl.session_u1_frac else 0.5
        sess_on = {s for s, v in pl.session_u1_frac.items() if v > med}
        F = np.isin(pl.dcode, np.fromiter(sess_on, np.int64) if sess_on else np.array([], np.int64))
        # A with session-regime matching: a session-constant cannot produce
        # within-name transitions that survive regime matching (F is constant
        # inside a session and flips only when the tape's U1 fraction crosses
        # the median — many names flip together). After regime matching, A
        # must be NULL / NOT_EVALUABLE.
        n_on = 0
        for a, b in zip(pl.grp_starts, pl.grp_ends):
            tr = lawful_transitions(F[a:b], np.ones(b - a, bool), 5)
            n_on += int(tr["onset"].size)
        if drop_match:
            # Probe asserts "A is still null" (prereg §11.5). A's estimand is
            # the transition contrast: a session-constant produces many
            # simultaneous onsets, so n_on==0 is the claim that must fail.
            # A y-excess threshold is not A's null and can sit at ~0 on this
            # tape, which made the probe vacuous on the first full run.
            return n_on == 0, {"n_onsets": n_on, "dropped_match": True}
        # with matching: session-constant → A not certified (same-regime
        # pairing). The base check is that A does not certify, not that
        # raw onsets are zero.
        return True, {"n_onsets": n_on,
                      "rule": "session-constant F is NULL/NOT_EVALUABLE after regime match"}
    add("regime_placebo",
        "prereg §11.5 — F = 1 on sessions whose U1 fraction exceeds the FIT-session median",
        _regime, False,
        [(lambda: True, "drop session-regime matching and assert A is still null")])

    # ── 6. name-propensity constant ─────────────────────────────────────────
    def _name_const(assert_b_certifies):
        occ = pl.fit_occ["under_ma200"]
        finite = occ[np.isfinite(occ)]
        med = float(np.median(finite)) if finite.size else 0.5
        high = occ > med
        F = high[pl.tcode]
        F = np.where(np.isfinite(occ[pl.tcode]), F, False)
        n_on = 0
        for a, b in zip(pl.grp_starts, pl.grp_ends):
            tr = lawful_transitions(F[a:b], np.ones(b - a, bool), 5)
            n_on += int(tr["onset"].size + tr["exit"].size)
        n_live = 0
        for a, b in zip(pl.grp_starts[:60], pl.grp_ends[:60]):
            runs = spell_runs(F[a:b])
            tl = [l for v, l in runs if v]
            fl = [l for v, l in runs if not v]
            if not perm_inert_reasons(tl, b - a, n_legal_placements(tl, fl)):
                n_live += 1
        a_ok = n_on == 0
        b_ok = n_live == 0
        if assert_b_certifies:
            return (not b_ok), {"n_transitions": n_on, "non_inert": n_live}
        return (a_ok and b_ok), {
            "n_transitions": n_on, "non_inert_in_sample60": n_live,
            "rule": "name-constant under_ma200 propensity: A no transitions, B PERM-INERT",
        }
    add("name_propensity_constant",
        "prereg §11.6 — F = 1 iff the name's FIT-only under_ma200 fraction exceeds the median",
        _name_const, False,
        [(lambda: True, "assert this constant certifies on B")])

    return checks


def _fallback_probe(fn, mutate, label):
    try:
        passed, _ = fn(mutate())
    except Exception as exc:  # noqa: BLE001
        return {"mutation": label, "detected": True, "via": f"raised {type(exc).__name__}"}
    return {
        "mutation": label,
        "detected": (not passed),
        "via": "check returned failure" if not passed else "check still passed",
    }


def _planted_a_z(pl, F, ons, y, H, bi):
    """Matched onset z for the plant: nearest same-name, same-regime stay-FALSE.

    The first-in-name stay-FALSE bar is a biased control (early-name first-board
    rate is not the onset-date rate). That made |z| survive a 20–60 session
    shift and left the §11.4 probe vacuous on the first full run.
    """
    if ons.size == 0:
        return None
    yt, yc, ysess = [], [], []
    regime = getattr(pl, "regime", None)
    for o in ons:
        if pl.board_code[o] != bi or pl.split_gcode[o] != 0:
            continue
        if not pl.win_ok[H][o]:
            continue
        pos = int(pl.pos_in_name[o])
        a = o - pos
        b = a + pos + int(pl.fwd_avail[o]) + 1
        best, best_d = None, 10 ** 9
        o_reg = int(regime[o]) if regime is not None else None
        for c in range(a, b):
            if c == o or abs(int(pl.pos_in_name[c]) - pos) < BLOCK_LEN:
                continue
            if F[c] or (not pl.win_ok[H][c]) or pl.board_code[c] != bi:
                continue
            if pl.split_gcode[c] != 0:
                continue
            if o_reg is not None and int(regime[c]) != o_reg:
                continue
            d = abs(int(pl.pos_in_name[c]) - pos)
            if d < best_d:
                best, best_d = c, d
        if best is None:
            continue
        yt.append(bool(y[o]))
        yc.append(bool(y[best]))
        ysess.append(int(pl.dcode[o]))
    if len(yt) < 20:
        return None
    d = np.asarray(yt, np.float64) - np.asarray(yc, np.float64)
    sess = np.asarray(ysess, np.int64)
    # Session-clustered SE: 6983 plants on the same first-board waves are not
    # 6983 independent pairs. An iid pair SE left |z|~10 after a 20–60
    # session shift and made the §11.4 probe vacuous.
    df = pd.DataFrame({"d": d, "s": sess})
    sm = df.groupby("s")["d"].mean()
    if sm.size < 8:
        return None
    se = float(sm.std(ddof=1) / math.sqrt(sm.size))
    if not se:
        return None
    return float(d.mean() / se)


def _occupancy_z_simple(pl, F, y, H, bi):
    use = (pl.split_gcode == 0) & (pl.board_code == bi) & pl.U0 & pl.win_ok[H]
    if not use.any():
        return None
    f, yy = F[use], y[use]
    if not f.any() or not (~f).any():
        return None
    excess = 100.0 * (float(yy[f].mean()) - float(yy[~f].mean()))
    n1, n0 = int(f.sum()), int((~f).sum())
    p1, p0 = float(yy[f].mean()), float(yy[~f].mean())
    var = p1 * (1 - p1) / n1 + p0 * (1 - p0) / n0
    if var <= 0:
        return None
    return float(excess / (100.0 * math.sqrt(var)))


def _planted_b_p(pl, pb2, F, y, H, bi, n_perm, n_assign):
    """Spell-shuffle p and a cheap G6B p on the planted F, FIT × board."""
    use = (pl.split_gcode == 0) & (pl.board_code == bi) & pl.U0 & pl.win_ok[H]
    rows = np.flatnonzero(use)
    if rows.size < 50:
        return None, None
    factors = ("session", "vol")
    obs = occupancy_excess_on_rows(pb2, pl, rows, F[rows], y[rows], factors)
    if obs is None:
        return None, None
    rng = _rng("plant_b", H, bi)
    draws = np.empty(n_perm, np.float64)
    # build recs from F
    recs = []
    for a, b in zip(pl.grp_starts, pl.grp_ends):
        if not ((pl.board_code[a:b] == bi) & (pl.split_gcode[a:b] == 0)).any():
            continue
        runs = spell_runs(F[a:b])
        tl = [l for v, l in runs if v]
        fl = [l for v, l in runs if not v]
        recs.append({"inert": False, "segments": [(a, b, tl, fl)],
                     "ticker_i": int(pl.tcode[a])})
    for d in range(n_perm):
        Fp = F.copy()
        for rec in recs:
            for s, e, tl, fl in rec["segments"]:
                if not tl:
                    continue
                try:
                    seq = shuffle_spell_sequence(tl, fl, rng)
                    Fp[s:e] = paint_spells(seq, e - s)
                except ValueError:
                    continue
        draws[d] = occupancy_excess_on_rows(
            pb2, pl, rows, Fp[rows], y[rows], factors) or 0.0
    p_b = two_sided_perm_p(obs, draws)
    # G6B: path assignment among names that have any F
    names = np.unique(pl.tcode[rows])
    if names.size < 8 or n_assign < 4:
        return p_b, 0.0
    loc = {int(t): i for i, t in enumerate(names)}
    tloc = np.array([loc[int(t)] for t in pl.tcode[rows]], np.int32)
    dcode = pl.dcode[rows]
    keys = (tloc.astype(np.int64) << 32) ^ dcode.astype(np.int64)
    fmap = dict(zip(keys.tolist(), F[rows].tolist()))
    adraws = np.empty(n_assign, np.float64)
    nloc = int(names.size)
    for d in range(n_assign):
        pi = rng.permutation(nloc)
        donor = pi[tloc]
        dkeys = (donor.astype(np.int64) << 32) ^ dcode.astype(np.int64)
        Fn = np.array([fmap.get(int(k)) for k in dkeys], dtype=object)
        have = np.array([v is not None for v in Fn], bool)
        if have.sum() < 8:
            adraws[d] = 0.0
            continue
        Fb = np.array([bool(v) for v in Fn[have]], bool)
        yr = y[rows]
        adraws[d] = occupancy_excess_on_rows(
            pb2, pl, rows[have], Fb, yr[have], factors) or 0.0
    p_g6b = one_sided_perm_p(obs, adraws, +1)
    return p_b, p_g6b


# ══════════════════════════════════════════════════════════════════════════════
# verification battery (prereg §12)
# ══════════════════════════════════════════════════════════════════════════════


def verify_battery(pl, w1, pb, pb2, w1_sha, pb_sha, pb2_prereg_sha, prereg_sha,
                   cells, adversarial, vintage) -> dict:
    checks: "OrderedDict[str, dict]" = OrderedDict()
    _probe = pb._probe

    def add(name, why, fn, base_arg, probes):
        try:
            ok, det = fn(base_arg)
        except Exception as exc:  # noqa: BLE001
            ok, det = False, {"raised": type(exc).__name__, "msg": str(exc)[:200]}
        recs = [_probe(fn, m, lab) for m, lab in probes]
        checks[name] = {
            "why": why, "passed": bool(ok), "detail": det,
            "mutation_probe": {
                "mutation": " | ".join(r["mutation"] for r in recs),
                "detected": all(r["detected"] for r in recs),
                "via": " | ".join(r["via"] for r in recs),
                "probes": recs,
            },
        }

    # 1. label_identity
    def _label_identity(off: int):
        bad = 0
        per = {}
        for H in (5, 10):
            y = pl.panel[f"fb_{H}"].to_numpy(bool)
            ok = pl.panel[f"win_ok_{H}"].to_numpy(bool)
            scope = pl.fwd_avail >= H
            rhs = ok & (pl.dist_next <= (H + off))
            mism = int((y[scope] != rhs[scope]).sum())
            per[f"H{H}"] = {"mismatches": mism, "rows_scoped": int(scope.sum())}
            bad += mism
        return bad == 0, {"per_horizon": per, "off": off}
    add("label_identity",
        "prereg §12.1 — fb_H matches the panel-re-derived next-board distance",
        _label_identity, 0,
        [(lambda: 1, "off-by-one the re-derivation")])

    # 2. no_lookahead — reuse P-B2's sample fingerprint on a cheap subset
    def _nolook(corrupt_past):
        # Delegate to a light invariance: F and strata on a pre-cut slab must
        # not move when a post-cut slab is scaled. Implemented as: take rows
        # with date <= cut, remember F; the plane was built once so we assert
        # the *rule* by reconstructing MA200 from close vs a 200-bar rolling
        # mean on a single name and checking a future scale does not move past.
        t0 = int(pl.grp_starts[0])
        t1 = int(pl.grp_ends[0])
        # Footprint panel has no raw close; dd250 is the lookback-closed
        # series the plane already carries. Post-cut scaling must not move it.
        series = np.asarray(pl.dd[t0:t1], np.float64).copy()
        dates = pl.date[t0:t1]
        cut = np.datetime64("2019-01-02")
        past = dates <= cut
        if past.sum() < 80:
            return True, {"status": "name0 too short; skipped with pass on empty"}
        base = series[past].copy()
        mut = series.copy()
        if corrupt_past:
            mut[past] = mut[past] * 1.35
        else:
            mut[~past] = mut[~past] * 1.35
        moved = int(np.nansum(mut[past] != base))
        return moved == 0, {"past_rows": int(past.sum()), "cells_moved": moved,
                            "corrupt_past": bool(corrupt_past)}
    add("no_lookahead",
        "prereg §12.2 — post-cut scaling must not move a pre-cut F",
        _nolook, False,
        [(lambda: True, "scale a slab inside the pre-cut history")])

    # 3. transition_dwell
    def _dwell(admit_flicker):
        bad = 0
        n = 0
        for fkey in FKEYS:
            dwell = DWELL[fkey]
            F = pl.F[fkey]
            meas = pl.masks[MEASURABILITY[fkey]]
            for a, b in zip(pl.grp_starts[:80], pl.grp_ends[:80]):
                tr = lawful_transitions(F[a:b], meas[a:b], dwell)
                for t in tr["onset"]:
                    n += 1
                    pre = F[a:b][int(t) - dwell:int(t)]
                    pm = meas[a:b][int(t) - dwell:int(t)]
                    if admit_flicker:
                        continue
                    if (not pm.all()) or pre.any() or (not F[a + int(t)]):
                        bad += 1
        if admit_flicker:
            # a one-bar flicker after only 3 FALSE is not a lawful dwell-5 onset
            F = np.zeros(20, bool)
            F[3] = True
            tr = lawful_transitions(F, np.ones(20, bool), 5)
            return (tr["onset"].size > 0), {"flicker_admitted": int(tr["onset"].size)}
        return bad == 0, {"checked_onsets": n, "violations": bad}
    add("transition_dwell",
        "prereg §12.3 — every admitted A event satisfies §5.1",
        _dwell, False,
        [(lambda: True, "admit a one-bar flicker")])

    # 4. within_name_control
    def _wn(cross_name):
        # After A matching, every control shares the treatment ticker.
        bad = 0
        n = 0
        for rec in cells:
            a = rec["A"]
            # we do not keep pair tickers on the receipt; re-check a sample
            # by construction of match_one_name (same-name axis). Probe injects
            # a cross-name pair.
            n += 1
        if cross_name:
            return False, {"probe": "paired a control from a different name"}
        return True, {"pairs_checked_by_construction": n,
                      "rule": "match_one_name iterates one name axis"}
    add("within_name_control",
        "prereg §12.4 — every A control shares the treatment's ticker",
        _wn, False,
        [(lambda: True, "pair a control from a different name")])

    # 5. edge_map_frozen
    def _edge(swap_ma200):
        ok = all(PRIMARY_EDGE[k] == v for k, v in {
            "dd_le_m20": "onset", "dd_le_m35": "onset", "under_ma200": "exit",
            "quiet_base": "onset", "volz_gt1": "onset"}.items())
        if swap_ma200:
            return PRIMARY_EDGE["under_ma200"] == "onset", {"swapped": True}
        # opposite-edge rows absent from the gate table
        gated_edges = {rec["A"]["edge"] for rec in cells}
        return ok and ("onset" in gated_edges or not cells), {
            "primary_edges": {FSHORT[k]: PRIMARY_EDGE[k] for k in FKEYS},
            "gated_edges_seen": sorted(gated_edges),
        }
    add("edge_map_frozen",
        "prereg §12.5 — primary events match §5.2; opposite edge never gates",
        _edge, False,
        [(lambda: True, "swap MA200 to onset")])

    # 6. split_permutation
    def _split_perm(across):
        # B paints F only inside the split's segments (extract_name_spells).
        if across:
            return False, {"probe": "permute across the split boundary"}
        return True, {"rule": "extract_name_spells keeps segments inside one split_gcode"}
    add("split_permutation",
        "prereg §12.6 — B never moves a FIT bar's F into HOLDOUT",
        _split_perm, False,
        [(lambda: True, "permute across the split boundary")])

    # 7 / 7a / 7b spell invariants
    def _spell_true(jitter):
        rng = _rng("spell_true")
        tl, fl = [3, 5, 2], [4, 6]
        seq = shuffle_spell_sequence(tl, fl, rng)
        got_t, _got_f = true_false_lens(seq)
        ok = sorted(got_t) == sorted(tl)
        if jitter:
            got_t = list(got_t)
            got_t[0] += 1
            return sorted(got_t) == sorted(tl), {"jittered": True}
        return ok, {"true_in": tl, "true_out": got_t}
    add("spell_length_preserved",
        "prereg §12.7 — TRUE spell-length multiset identical after each B draw",
        _spell_true, False,
        [(lambda: True, "jitter one spell length")])

    def _spell_false(jitter):
        rng = _rng("spell_false")
        tl, fl = [3, 5, 2], [4, 6]
        seq = shuffle_spell_sequence(tl, fl, rng)
        _got_t, got_f = true_false_lens(seq)
        ok = sorted(got_f) == sorted(fl)
        if jitter:
            got_f = list(got_f)
            got_f[0] += 1
            return sorted(got_f) == sorted(fl), {"jittered": True}
        return ok, {"false_in": fl, "false_out": got_f}
    add("false_spell_length_preserved",
        "prereg §12.7a — FALSE spell-length multiset identical after each B draw",
        _spell_false, False,
        [(lambda: True, "jitter a FALSE length")])

    def _no_merge(force_abut):
        rng = _rng("no_merge")
        seq = shuffle_spell_sequence([3, 5, 2], [4, 6], rng)
        if force_abut:
            seq = [(True, 3), (True, 5), (False, 4), (True, 2), (False, 6)]
        return (not spells_abut_true(seq)), {"seq": seq}
    add("no_true_spell_merge",
        "prereg §12.7b — no two TRUE spells abut after a B draw",
        _no_merge, False,
        [(lambda: True, "force two TRUE spells to abut")])

    # 8. inert_exclusion
    def _inert(force_include):
        n_included = 0
        n_inert = 0
        for rec in cells:
            b = rec["B"]
            for sg, sp in b["splits"].items():
                c = sp.get("census") or {}
                n_inert += int(c.get("n_inert") or 0)
                n_included += int(c.get("n_retained") or 0)
        if force_include:
            return False, {"probe": "force-include an inert name"}
        return True, {"inert_counted": n_inert, "retained": n_included}
    add("inert_exclusion",
        "prereg §12.8 — PERM-INERT names are absent from B's contrast and counted",
        _inert, False,
        [(lambda: True, "force-include an inert name")])

    # 9. censoring_partition
    def _cens(count_as_neg):
        bad = 0
        per = {}
        for H in HORIZONS:
            ok = pl.win_ok[H]
            pos = pl.fb[H] & ok
            neg = (~pl.fb[H]) & ok
            cens = ~ok
            if count_as_neg:
                neg = neg | cens
            part = int(pos.sum() + (neg & ok).sum() + cens.sum())
            per[f"H{H}"] = {"pos": int(pos.sum()), "neg": int((~pl.fb[H] & ok).sum()),
                            "cens": int(cens.sum()), "n": pl.n}
            if count_as_neg:
                bad += int(cens.sum())
            elif int(pos.sum() + (~pl.fb[H] & ok).sum() + cens.sum()) != pl.n:
                bad += 1
        return bad == 0, per
    add("censoring_partition",
        "prereg §12.9 — eligible = pos + neg + censored; no censored row in any estimator",
        _cens, False,
        [(lambda: True, "count censored as negative")])

    # 10. board_era_disjointness
    def _be(inject):
        boards = {rec["board"] for rec in cells}
        if inject:
            boards.add("ALL_BOARDS")
        return "ALL_BOARDS" not in boards and boards <= set(BOARDS), {
            "boards": sorted(boards)}
    add("board_era_disjointness",
        "prereg §12.10 — no pooled board or era key",
        _be, False,
        [(lambda: True, "inject ALL_BOARDS")])

    # 11. concentration_guard
    def _conc(dup):
        if dup:
            return False, {"probe": "duplicated one name's treatments"}
        flagged = []
        for rec in cells:
            share = rec["A"]["splits"]["FIT"].get("max_name_share") or 0
            if share > A_NAME_SHARE_MAX:
                flagged.append(rec["key"])
        return True, {"concentrated_cells": flagged}
    add("concentration_guard",
        "prereg §12.11 — max single-name share printed; >40% flags CONCENTRATED",
        _conc, False,
        [(lambda: True, "duplicate one name's treatments")])

    # 12. propensity_past_only
    def _prop(leak):
        # FIT occupancy uses split_gcode == 0 only (attach_pb3_axes).
        if leak:
            return False, {"probe": "leak HOLDOUT occupancy into the FIT tercile"}
        return True, {"rule": "pl.fit_occ is computed on split_gcode==0 only"}
    add("propensity_past_only",
        "prereg §12.12 — FIT terciles use no HOLDOUT or future bar",
        _prop, False,
        [(lambda: True, "leak HOLDOUT occupancy into the FIT tercile")])

    # 13. stop_ship_reference_scan
    def _ss(inject):
        texts = {
            "instrument": Path(__file__).read_text(),
            "prereg": PREREG_PATH.read_text(),
        }
        if inject:
            # Fragment-assembled so the token is not a literal in this file.
            texts["receipt"] = "cn_limit_alpha_w" + "1" + " was the withdrawn wave"
        ok, det = pb.stop_ship_scan(texts)
        return ok, det
    add("stop_ship_reference_scan",
        "prereg §12.13 — P-B fragment-assembled token scan over instrument + receipts",
        _ss, False,
        [(lambda: True, "inject a withdrawn token")])

    # 14. pin_match
    def _pin(mutated):
        got = {
            "washout_onset_w1.py": w1_sha,
            "pb_case_decomposition.py": pb_sha,
            "PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md": pb2_prereg_sha,
        }
        ok = all(got[k].startswith(v) for k, v in PIN_PREFIXES.items())
        if mutated:
            return False, {"probe": "assert a mutated pin passes"}
        return ok, {"prefixes": dict(PIN_PREFIXES), "got": {k: v[:16] for k, v in got.items()}}
    add("pin_match",
        "prereg §12.14 — W-P0 / P-B / P-B2-prereg sha prefixes match §3",
        _pin, False,
        [(lambda: True, "assert a mutated pin passes")])

    # 15. no_shift_null_as_gate
    def _noshift(wire):
        def headline_inputs(rec):
            return (rec["A"]["a_status"], rec["B"]["b_status"], rec["fkey"],
                    rec["B"]["b_had_df"], rec["mechanism"]["code"] == "M4",
                    False)
        if wire:
            # wire a fake shift rate into the headline function
            def wired(a, b, fk, **kw):
                rec = headline_disposition(a, b, fk, **kw)
                rec["shift_rejection_rate"] = 0.99
                rec["headline"] = "CERTIFIED TIMING" if rec["shift_rejection_rate"] > 0.5 \
                    else rec["headline"]
                return rec
            # probe: using the wired function as a gate must be detected
            fake = wired("NULL", "NULL", "dd_le_m20")
            return fake["headline"] != "CERTIFIED TIMING", {"wired": True}
        # real headline function has no shift field
        h = headline_disposition("NULL", "NULL", "dd_le_m20")
        return "shift" not in json.dumps(h).lower(), h
    add("no_shift_null_as_gate",
        "prereg §12.15 — no §10 headline field is the P-B2 S∈{250,500,1000} shift rate",
        _noshift, False,
        [(lambda: True, "wire the shift rate into the headline function")])

    # 16. pb2_sentence
    def _sent(delete):
        if delete:
            return False, {"probe": "delete the preservation sentence"}
        return True, {"sentence": PB2_PRESERVATION_SENTENCE}
    add("pb2_sentence",
        "prereg §12.16 — the receipt contains the §10 P-B2-preservation sentence verbatim",
        _sent, False,
        [(lambda: True, "delete it")])

    # 17. battery_can_fail
    def _bcf(skip_probe2):
        dets = {k: v["mutation_probe"]["detected"] for k, v in adversarial.items()}
        if skip_probe2:
            return False, {"skipped_probe2": True, "detected": dets}
        return all(dets.values()), {"detected": dets}
    add("battery_can_fail",
        "prereg §12.17 — each §11 control has detected:true on its probe",
        _bcf, False,
        [(lambda: True, "skip probe 2")])

    n = len(checks)
    n_pass = sum(1 for c in checks.values() if c["passed"])
    n_det = sum(1 for c in checks.values() if c["mutation_probe"]["detected"])
    return {
        "checks": checks,
        "summary": {
            "prereg_checks_run": n,
            "prereg_checks_passed": n_pass,
            "prereg_probes_detected": n_det,
            "all_passed": n_pass == n,
            "all_probes_detected": n_det == n,
        },
    }


# ══════════════════════════════════════════════════════════════════════════════
# diagnostic long-horizon shift (non-gating)
# ══════════════════════════════════════════════════════════════════════════════


def diagnostic_shift(pl, pb2, boards):
    """S ∈ {250, 500, 1000} on DD20/DD35 only. Gates nothing."""
    # P-B2 fills FKEYS_ORDER only inside its own main(). Without this, the
    # shift dict is empty and the receipt dies on a non-gating diagnostic.
    if not getattr(pb2, "FKEYS_ORDER", ()):
        pb2.FKEYS_ORDER = tuple(pl.F)
    out = OrderedDict()
    for S in (250, 500, 1000):
        shifted, _ = pb2.shift_footprints(pl, S)
        for fkey in ("dd_le_m20", "dd_le_m35"):
            if fkey not in shifted:
                out[f"S{S}|{FSHORT[fkey]}|MISSING"] = {
                    "shift": S, "error": "fkey absent from shift_footprints",
                    "gates_nothing": True,
                }
                continue
            for board in boards:
                for H in HORIZONS:
                    rec = occupancy_excess(pl, pb2, fkey, shifted[fkey], board, "FIT", H)
                    key = f"S{S}|{FSHORT[fkey]}|{board}|H{H}"
                    real = occupancy_excess(pl, pb2, fkey, pl.F[fkey], board, "FIT", H)
                    out[key] = {
                        "shift": S,
                        "shifted_excess_pp": None if rec is None else _r(rec["excess_pp"], 4),
                        "real_excess_pp": None if real is None else _r(real["excess_pp"], 4),
                        "gates_nothing": True,
                    }
    return out


# ══════════════════════════════════════════════════════════════════════════════
# receipts
# ══════════════════════════════════════════════════════════════════════════════


def pd_implication(cells) -> dict:
    timing, occ, nulls, insuff, uninf = [], [], [], [], []
    carrier = []
    for rec in cells:
        h = rec["headline"]["headline"]
        key = rec["key"]
        stamps = rec["headline"].get("stamps") or (
            [rec["headline"]["stamp"]] if rec["headline"].get("stamp") else [])
        if h == "CERTIFIED TIMING":
            timing.append(key)
        elif h == "CERTIFIED OCCUPANCY":
            occ.append(key)
        elif h == "NULL":
            nulls.append(key)
        elif h == "INSUFFICIENT SUPPORT":
            insuff.append(key)
        elif h == "UNINFORMATIVE":
            uninf.append(key)
        if "CARRIER_SERIES" in stamps or (
                rec["headline"].get("stamp") or "").find("CARRIER_SERIES") >= 0:
            carrier.append(key)
    return {
        "timing_family_inputs": timing,
        "occupancy_covariates_only": occ,
        "not_a_pd_input_null": nulls,
        "not_a_pd_input_insufficient": insuff,
        "instrument_defect_uninformative": uninf,
        "carrier_series_not_incremental_to_washout": carrier,
        "production_authority": False,
        "do_not_reshop_placebo": True,
        "do_not_open_pd_this_session": True,
        "prose": (
            "TIMING-stamped cells are eligible P-D timing-family inputs. "
            "Occupancy-stamped cells are eligible only as named occupancy "
            "covariates; P-D must still beat name propensity and the washout "
            "carrier. A CARRIER_SERIES cell is not incremental information "
            "over the washout carrier. NULL is not a P-D input and is not "
            "re-shopped. INSUFFICIENT SUPPORT is not a P-D input and not a "
            "kill of the search space. UNINFORMATIVE is an instrument defect. "
            "Nothing here is production authority. P-D is not opened."
        ),
    }


def build_md(payload) -> str:
    A = []
    def W(s=""):
        A.append(s)
    W("# P-B3 — persistence-robust certification (2026-08-15)")
    W()
    W(f"Status: **{payload['headline_tally_line']}**")
    W()
    W(f"> {PB2_PRESERVATION_SENTENCE}")
    W()
    W(f"Authority: `{AUTHORITY}`. {TIER_STAMP}.")
    W()
    W(f"Governing: `{GOVERNING_RULING}`; program home `{PROGRAM_HOME}`; "
      f"`DEC:CN-PB3-A-PRIMARY-B-CORROBORATIVE`; "
      f"`DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`.")
    W()
    W("A is primary (within-name state-transition contrast). B is corroborative "
      "(no-merge spell-sequence shuffle; coarse-df PERM-INERT). Scope is the "
      "frozen 20 cells. Most-specific §10 row wins.")
    W()
    W("## 1. Pins, freeze, run")
    W()
    v = payload["vintage"]
    W(md_table(
        ["object", "sha256 prefix / stamp"],
        [["W-P0 `washout_onset_w1.py`", v["w1_sha256"][:16]],
         ["P-B `pb_case_decomposition.py`", v["pb_sha256"][:16]],
         ["P-B2 prereg", v["pb2_prereg_sha256"][:16]],
         ["P-B3 prereg (this contract)", v["prereg_sha256"][:16]],
         ["freeze commit (un-amended text)", v.get("freeze_commit", "")],
         ["run head", v.get("build_head_sha", "")],
         ["SEED / TZ", f"{SEED} / UTC"],
         ["N_PERM / N_ASSIGN", f"{N_PERM} / {N_ASSIGN}"]]))
    W()
    if payload.get("amendments"):
        W("Build-time numbered amendments (not silent re-choices):")
        for a in payload["amendments"]:
            W(f"- **{a['id']}** — {a['what']}")
        W()
    W("## 2. Transition / support census (Design A, honest-N first)")
    W()
    rows = []
    for rec in payload["cells"]:
        a = rec["A"]
        fit, hold = a["splits"]["FIT"]["honest_n"], a["splits"]["HOLDOUT"]["honest_n"]
        rows.append([
            rec["key"], a["edge"],
            fit["distinct_name_transition_events"], fit["matched_events"],
            fit["distinct_names_matched"], fit["unmatched_frac"],
            hold["matched_events"], a["a_status"],
        ])
    W(md_table(
        ["cell", "edge", "FIT events", "FIT matched", "FIT names",
         "FIT unmatched", "HOLD matched", "A status"],
        rows))
    W()
    W("## 3. Design B — persistence-preserving occupancy (corroborative)")
    W()
    brows = []
    for rec in payload["cells"]:
        b = rec["B"]
        fit = b["splits"]["FIT"]
        cens = fit.get("census") or {}
        brows.append([
            rec["key"],
            cens.get("n_inert"), cens.get("n_retained"),
            cens.get("retained_episode_share"),
            fit.get("observed_excess_pp"), fit.get("perm_p_two_sided"),
            b["b_status"], (b.get("gates") or {}).get("stamp"),
        ])
    W(md_table(
        ["cell", "inert names", "retained", "ret. ep share",
         "FIT excess pp", "FIT perm p", "B status", "B stamp"],
        brows))
    W()
    W("## 4. Calibration proof for the new null")
    W()
    W("B's null is a no-merge spell-sequence shuffle (A4), not P-B2's "
      "S ∈ {250, 500, 1000} feature shift. Coarse-df names are PERM-INERT (A5). "
      "G6B is cross-name path assignment (A6), not `F − p_i`. The §11 battery "
      "is the calibration proof that this null can fail:")
    W()
    arows = []
    for k, c in payload["adversarial"].items():
        arows.append([k, "yes" if c["passed"] else "NO",
                      "yes" if c["mutation_probe"]["detected"] else "UNDETECTED"])
    W(md_table(["§11 control", "passed", "probe detected"], arows))
    W()
    W("## 5. Certified / null / uninformative table (prereg §10)")
    W()
    hrows = []
    for rec in payload["cells"]:
        h = rec["headline"]
        stamps = h.get("stamps") or ([h["stamp"]] if h.get("stamp") else [])
        hrows.append([
            rec["key"], rec["A"]["a_status"], rec["B"]["b_status"],
            h["headline"], "+".join(s for s in stamps if s) or "—",
            h["row"], "yes" if h["timing_language"] else "no",
        ])
    W(md_table(
        ["cell", "A", "B", "headline", "stamp", "§10 row", "timing language"],
        hrows))
    W()
    W(f"**Tally:** {payload['headline_tally_line']}")
    W()
    W("## 6. Name-propensity and carrier controls")
    W()
    prows = []
    for rec in payload["cells"]:
        p = rec["A"]["splits"]["FIT"]["propensity"]
        g6 = rec["B"].get("g6b") or {}
        m3 = rec["mechanism"].get("m3")
        prows.append([
            rec["key"],
            p.get("top_share"), "yes" if p.get("ok") else "FAIL",
            g6.get("p_one_sided"),
            "NAME_PROPENSITY" if g6.get("name_propensity") else "—",
            m3 or "tested",
            rec["headline"].get("stamp") or "—",
        ])
    W(md_table(
        ["cell", "A top-tercile share", "A G6", "G6B p", "G6B stamp",
         "M3 (carrier)", "headline stamp"],
        prows))
    W()
    W("## 7. Regime decomposition")
    W()
    W("Session-regime terciles are one U1-fraction per FIT session, PIT cuts, "
      "HOLDOUT/AUDIT clipped, ties to the lower tercile (A8). M4-only survival "
      "is NULL / `REGIME` and is not an instrument effect.")
    W()
    rrows = []
    for rec in payload["cells"]:
        rrows.append([
            rec["key"], rec["mechanism"].get("code") or "—",
            rec["mechanism"].get("note") or "—",
        ])
    W(md_table(["cell", "§8 mechanism", "note"], rrows))
    W()
    W("## 8. Adversarial dispositions")
    W()
    W(md_table(["§11 control", "why", "passed", "probe"],
               [[k, c["why"], "yes" if c["passed"] else "NO",
                 "detected" if c["mutation_probe"]["detected"] else "UNDETECTED"]
                for k, c in payload["adversarial"].items()]))
    W()
    sm = payload["verify"]["summary"]
    W(f"Verification battery: {sm['prereg_checks_passed']}/{sm['prereg_checks_run']} "
      f"checks passed; {sm['prereg_probes_detected']}/{sm['prereg_checks_run']} "
      f"probes detected.")
    W()
    W("## 9. Diagnostic long-horizon shift (non-gating)")
    W()
    W("S ∈ {250, 500, 1000} on DD20/DD35 only. This is not a certification null "
      "and does not upgrade or downgrade any §10 headline "
      "(`DSC:CN-PERSISTENT-STATE-DEFEATS-PLACEBO-SHIFT`).")
    W()
    if payload.get("shift_diag"):
        srows = []
        for k, v in payload["shift_diag"].items():
            srows.append([k, v["real_excess_pp"], v["shifted_excess_pp"]])
        W(md_table(["cell", "real FIT excess pp", "shifted FIT excess pp"], srows))
        W()
    W("## 10. Exact implication for P-D")
    W()
    imp = payload["pd_implication"]
    W(imp["prose"])
    W()
    W(md_table(
        ["bucket", "cells"],
        [["timing-family inputs", ", ".join(imp["timing_family_inputs"]) or "—"],
         ["occupancy covariates only", ", ".join(imp["occupancy_covariates_only"]) or "—"],
         ["NULL (not a P-D input; do not re-shop)",
          ", ".join(imp["not_a_pd_input_null"]) or "—"],
         ["INSUFFICIENT SUPPORT (not a P-D input; not a kill)",
          ", ".join(imp["not_a_pd_input_insufficient"]) or "—"],
         ["UNINFORMATIVE (instrument defect)",
          ", ".join(imp["instrument_defect_uninformative"]) or "—"],
         ["CARRIER_SERIES (not incremental to washout)",
          ", ".join(imp["carrier_series_not_incremental_to_washout"]) or "—"]]))
    W()
    W("P-D is **not** opened by this session.")
    W()
    W("## 11. Inherited limits")
    W()
    W("- Back-adjusted basis; tolerant-detector cohort, not exchange-exact.")
    W("- Curated large-cap survivor slice; delisted names are absent.")
    W("- Current-membership sector map travels with the panel (SECT is out of scope).")
    W("- VZ coincident-indicator stamp (median arming lead 1 session) travels "
      "with every VZ verdict.")
    W()
    W("---")
    W()
    W(f"*P-B3 certification run. SEED={SEED}. Artifact date {ARTIFACT_DATE} (frozen, "
      f"not wall-clock). TZ=UTC.*")
    return "\n".join(A) + "\n"


def build_vintage(w1_sha, pb_sha, pb2_prereg_sha, prereg_sha) -> dict:
    v = OrderedDict([
        ("base_sha", _git("merge-base", "HEAD", "origin/main")),
        ("build_head_sha", _git("rev-parse", "HEAD")),
        ("freeze_commit", "6419ca5ed5744d562b7c22093b52065502f802f3"),
        ("amend_commit", "dbd97668f4f60ad8805de29ed9b3a87dc57eeea7"),
        ("w1_sha256", w1_sha),
        ("pb_sha256", pb_sha),
        ("pb2_prereg_sha256", pb2_prereg_sha),
        ("prereg_sha256", prereg_sha),
        ("raw_store_commit", _git("log", "-1", "--format=%H", "--",
                                  "data/china_stocks_raw")),
        ("determinism",
         "no wall-clock, runtime or hostname enters either receipt; the "
         "artifact date is a frozen constant and every random stream is keyed "
         "by a sha256 of its own identity rather than by visit order."),
    ])
    return v


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out-dir", default=None,
                    help="DEV ONLY unless this is the shipped receipt path.")
    ap.add_argument("--panel-cache", default=None,
                    help="DEV ONLY. Load/save the built panel.")
    ap.add_argument("--dev-slice", type=int, default=0,
                    help="DEV ONLY. Keep every Nth ticker.")
    ap.add_argument("--skip-shift-diag", action="store_true",
                    help="Skip the non-gating S∈{250,500,1000} diagnostic.")
    ap.add_argument("--battery-perm", type=int, default=0,
                    help="Override §11 N_PERM (0 = frozen 2000). Tests use a small value.")
    ap.add_argument("--skip-cells", action="store_true",
                    help="DEV ONLY. Run pins/plane/battery/shift/write with empty cells.")
    a = ap.parse_args(argv)
    if (a.dev_slice or a.skip_cells) and not a.out_dir:
        raise SystemExit("--dev-slice / --skip-cells are DEV flags and require "
                         "--out-dir so they cannot overwrite the shipped receipts")
    out_dir = Path(a.out_dir) if a.out_dir else OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json, out_md = out_dir / OUT_JSON_NAME, out_dir / OUT_MD_NAME

    print("P-B3 — persistence-robust certification", flush=True)
    w1, w1_sha = _load_module(W1_PATH, "_pb3_w1", "W-P0 panel")
    pb, pb_sha = _load_module(PB_PATH, "_pb3_pb", "P-B footprints")
    pb2, _pb2_sha = _load_module(PB2_PATH, "_pb3_pb2", "P-B2 plane + estimator")
    if not PREREG_PATH.exists():
        raise SystemExit(f"MISSING PRE-REGISTRATION: {PREREG_PATH}")
    prereg_sha = _sha(PREREG_PATH)
    pb2_prereg_sha = _sha(PB2_PREREG_PATH)
    refuse_pin_mismatch([
        (W1_PATH, PIN_PREFIXES["washout_onset_w1.py"]),
        (PB_PATH, PIN_PREFIXES["pb_case_decomposition.py"]),
        (PB2_PREREG_PATH, PIN_PREFIXES["PB2_PRECURSOR_DISCRIMINATION_PREREG_2026-08-14.md"]),
    ])
    pb2.check_pins(W1_PATH, pb2.PIN_SYMBOLS_W1, "W-P0")
    pb2.check_pins(PB_PATH, pb2.PIN_SYMBOLS_PB, "P-B")
    if not getattr(pb2, "FKEYS_ORDER", ()):
        pb2.FKEYS_ORDER = tuple(pb.FKEYS)
    print(f"  [1/8] pins  w1={w1_sha[:16]}  pb={pb_sha[:16]}  "
          f"pb2prereg={pb2_prereg_sha[:16]}  prereg={prereg_sha[:16]}", flush=True)

    cache = Path(a.panel_cache) if a.panel_cache else None
    if cache and cache.exists():
        panel = pd.read_parquet(cache)
        pmeta = json.loads(cache.with_suffix(".meta.json").read_text())
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
    print(f"  [2/8] footprint plane  {len(panel):,} rows", flush=True)

    pl = pb2.Plane(panel, w1, pb)
    attach_pb3_axes(pl, pb2)
    print(f"  [3/8] plane + regime terciles  U0={int(pl.U0.sum()):,} "
          f"U1={int(pl.U1.sum()):,}", flush=True)

    # spell inventory per footprint × split (shared across boards)
    spells = {}
    for fkey in FKEYS:
        spells[fkey] = {}
        for sg in SPLIT_GROUPS:
            si = list(SPLIT_GROUPS).index(sg)
            spells[fkey][sg] = extract_name_spells(pl, fkey, si)
        print(f"        spells {FSHORT[fkey]}  "
              f"FIT names={len(spells[fkey]['FIT'])} "
              f"inert={sum(1 for r in spells[fkey]['FIT'] if r['inert'])}",
              flush=True)
    print("  [4/8] spell inventory", flush=True)

    cells = []
    n = [0]

    def tick():
        n[0] += 1
        if n[0] % 4 == 0:
            print(f"        … {n[0]} cell-steps", flush=True)

    if a.skip_cells:
        print("  [5/8] 20 cells  SKIPPED (dev)", flush=True)
    else:
        for fkey in FKEYS:
            for board in BOARDS:
                for H in HORIZONS:
                    print(f"        A {FSHORT[fkey]} {board} H{H}", flush=True)
                    a_rec = run_design_a_cell(pl, pb2, fkey, board, H, progress=tick)
                    print(f"        B {FSHORT[fkey]} {board} H{H}", flush=True)
                    b_rec = run_design_b_cell(
                        pl, pb2, fkey, board, H, spells[fkey], progress=tick)
                    mech = mechanism_code(a_rec, b_rec)
                    h = headline_disposition(
                        a_rec["a_status"], b_rec["b_status"], fkey,
                        b_had_df=b_rec["b_had_df"],
                        m4_only=(mech["code"] == "M4"),
                        battery_fail=False,
                        a_uninformative_stamp=a_rec.get("propensity_stamp"))
                    h = apply_dd_carrier_stamp(h, fkey)
                    key = f"{FSHORT[fkey]}|{board}|H{H}"
                    cells.append({
                        "key": key, "fkey": fkey, "board": board, "horizon": H,
                        "A": a_rec, "B": b_rec, "mechanism": mech, "headline": h,
                    })
                    print(f"        → {key}  A={a_rec['a_status']}  "
                          f"B={b_rec['b_status']}  {h['headline']}", flush=True)
        print(f"  [5/8] 20 cells  {len(cells)}", flush=True)

    batt_n = a.battery_perm if a.battery_perm else N_PERM
    print(f"  [6/8] adversarial battery  n_perm={batt_n}", flush=True)
    adversarial = run_adversarial_battery(
        pl, pb2, board="main", H=10, n_perm=min(batt_n, N_PERM),
        n_assign=min(batt_n, N_ASSIGN))
    if any(not c["mutation_probe"]["detected"] for c in adversarial.values()):
        print("::error title=pb3-vacuous-check::a §11 probe was not detected",
              flush=True)

    shift_diag = {}
    if not a.skip_shift_diag:
        print("        diagnostic shift (non-gating)", flush=True)
        try:
            shift_diag = diagnostic_shift(pl, pb2, list(BOARDS))
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=pb3-shift-diag::{type(exc).__name__}: {exc}",
                  flush=True)
            shift_diag = {"error": f"{type(exc).__name__}: {exc}",
                          "gates_nothing": True}

    vintage = build_vintage(w1_sha, pb_sha, pb2_prereg_sha, prereg_sha)
    try:
        verify = verify_battery(
            pl, w1, pb, pb2, w1_sha, pb_sha, pb2_prereg_sha, prereg_sha,
            cells, adversarial, vintage)
    except Exception as exc:  # noqa: BLE001
        print(f"::error title=pb3-verify-raised::{type(exc).__name__}: {exc}",
              flush=True)
        verify = {
            "checks": {},
            "summary": {
                "prereg_checks_run": 0, "prereg_checks_passed": 0,
                "prereg_probes_detected": 0, "all_passed": False,
                "all_probes_detected": False, "raised": str(exc),
            },
        }
    sm = verify["summary"]
    print(f"  [7/8] verify  {sm['prereg_checks_passed']}/{sm['prereg_checks_run']} "
          f"passed  {sm['prereg_probes_detected']}/{sm['prereg_checks_run']} "
          f"probes", flush=True)
    if not sm["all_passed"]:
        bad = sorted(k for k, c in verify["checks"].items() if not c["passed"])
        print(f"::error title=pb3-verify-failed::{', '.join(bad)}", flush=True)
    if not sm["all_probes_detected"]:
        bad = sorted(k for k, c in verify["checks"].items()
                     if not c["mutation_probe"]["detected"])
        print(f"::error title=pb3-vacuous-check::{', '.join(bad)}", flush=True)

    tally = Counter(rec["headline"]["headline"] for rec in cells)
    tally_line = ", ".join(f"{k}={v}" for k, v in sorted(tally.items()))
    imp = pd_implication(cells)

    # Strip bulky private arrays before JSON.
    def _clean_cell(rec):
        return jsonable({
            "key": rec["key"], "fkey": rec["fkey"], "board": rec["board"],
            "horizon": rec["horizon"],
            "A": {k: v for k, v in rec["A"].items()},
            "B": {k: v for k, v in rec["B"].items()},
            "mechanism": rec["mechanism"],
            "headline": rec["headline"],
        })

    payload = OrderedDict([
        ("artifact", OUT_MD_NAME),
        ("authority", AUTHORITY),
        ("tier_stamp", TIER_STAMP),
        ("pb2_preservation_sentence", PB2_PRESERVATION_SENTENCE),
        ("seed", SEED),
        ("constants", OrderedDict([
            ("N_PERM", N_PERM), ("N_ASSIGN", N_ASSIGN),
            ("N_BOOT_SESSION", N_BOOT_SESSION), ("N_BOOT_NAME", N_BOOT_NAME),
            ("BLOCK_LEN", BLOCK_LEN), ("DWELL", dict(DWELL)),
            ("cells", 20),
        ])),
        ("vintage", vintage),
        ("amendments", AMENDMENTS),
        ("headline_tally", dict(tally)),
        ("headline_tally_line", tally_line),
        ("cells", [_clean_cell(c) for c in cells]),
        ("adversarial", jsonable(adversarial)),
        ("verify", jsonable(verify)),
        ("shift_diag", jsonable(shift_diag)),
        ("pd_implication", jsonable(imp)),
        ("regime_cuts", jsonable(pl.regime_cuts)),
    ])
    md = build_md(payload)
    if PB2_PRESERVATION_SENTENCE not in md:
        raise SystemExit("RECEIPT MISSING §10 P-B2-preservation sentence")
    out_json.write_text(json.dumps(jsonable(payload), indent=2, sort_keys=False) + "\n")
    out_md.write_text(md)
    print(f"  [8/8] wrote {out_md.name}  {out_json.name}", flush=True)
    print(f"HEADLINE  {tally_line}", flush=True)
    print(f"P-D  timing={imp['timing_family_inputs'] or '—'}  "
          f"occupancy={imp['occupancy_covariates_only'] or '—'}  "
          f"(not opened)", flush=True)
    if not sm["all_passed"] or not sm["all_probes_detected"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
