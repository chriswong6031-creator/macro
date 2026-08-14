"""Blind evaluation arm and sealed calibration partition (registration §3/§4).

**Draw order is the whole point.** The sequence is

    universe snapshot -> pilot cohort fixed -> BLIND ARM drawn -> CALIBRATION
    partition drawn -> manifest hashes written -> ONLY THEN constants calibrated

and it is enforced mechanically, not by convention: ``scripts/stock_identity_calibrate.py``
refuses to start without a written manifest and asserts every symbol it reads is
calibration-eligible. A constant chosen before the partition sealed would be a
constant chosen on the grading data, which is precisely the ~110-constant problem
the sealed partition exists to close (masterplan review finding 4).

Two different objects, deliberately not called the same thing (§16.2 ruling):

* **blind evaluation arm** — untouched by *all* constant-setting, feature-selection
  and design decisions. In W1 its members appear ONLY in this manifest's membership
  list and as anonymous denominators in cross-sectional ranks. No per-name blind row
  exists in any W1 artifact, and the census states how many names it excluded.
* **sealed calibration partition (SI-SEALED-CAL-P1)** — may set/freeze constants
  exactly once, and is thereafter excluded from confirmatory grading.

Everything below is a pure function of (the committed universe snapshot, the three
verbatim seed strings). Re-running reproduces identical lists and identical hashes;
that is test-enforced rather than asserted.

Provisionality (binding, §3): the final blind-arm size is set by the PR-5 power
simulation, which may only *prefix-shrink* within the recorded draw order or
*extend* from the clean pool. Names are never swapped or hand-picked — which is
why the full per-stratum draw order is persisted here, not just the chosen prefix.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import pandas as pd

from engine.stock_identity.authority import authority_block

log = logging.getLogger(__name__)

# --- seed strings: verbatim from registration §3/§4/§2. Never edit. -----------
SEED_STRING_BLIND = "stock-identity-blind-arm-v1"
SEED_STRING_CALIBRATION = "stock-identity-sealed-calibration-partition-v1"
SEED_STRING_DEAD = "stock-identity-pilot-dead-names-v1"

PARTITION_NAME = "SI-SEALED-CAL-P1"
CALIBRATION_FRACTION = 0.30
BLIND_PER_STRATUM = 3
BLIND_MIN_SESSIONS = 504
UNKNOWN = "UNKNOWN"


def seed_from(text: str) -> int:
    """``int(sha256(text).hexdigest()[:16], 16)`` — the registration's own formula."""
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], 16)


SEED_BLIND = seed_from(SEED_STRING_BLIND)
SEED_CALIBRATION = seed_from(SEED_STRING_CALIBRATION)
SEED_DEAD = seed_from(SEED_STRING_DEAD)


def sha256_of_symbols(symbols: Iterable[str]) -> str:
    """SHA256 over the sorted, newline-joined symbol list."""
    payload = "\n".join(sorted(symbols)) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def universe_sha256(snapshot: pd.DataFrame) -> str:
    """SHA256 over the canonical sorted ``symbol,plane`` CSV (registration §1)."""
    rows = sorted(
        f"{r.symbol},{r.price_plane_id}"
        for r in snapshot[["symbol", "price_plane_id"]].itertuples(index=False)
    )
    payload = "\n".join(rows) + "\n"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def partition_procedure_sha256(registration_path: str | Path) -> tuple[str, str]:
    """SHA256 over registration §4's text block (returns the hash and the text).

    Hashing the *procedure prose*, not just the drawn names, is what makes "the
    partition was sealed under these rules" checkable later: an edit to §4 after
    sealing changes this hash and the mismatch is visible.
    """
    text = Path(registration_path).read_text(encoding="utf-8")
    m = re.search(r"^## §4\..*?(?=^## §5\.)", text, flags=re.S | re.M)
    if not m:
        raise ValueError("registration §4 block not found — cannot hash the procedure")
    block = m.group(0).rstrip() + "\n"
    return hashlib.sha256(block.encode("utf-8")).hexdigest(), block


# ---------------------------------------------------------------------------
# stratification (registration §10)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Stratum:
    cap: str
    sector: str
    vol: str

    @property
    def key(self) -> str:
        return f"{self.cap}|{self.sector}|{self.vol}"


def _tercile_labels(values: pd.Series, prefix: str) -> pd.Series:
    """Terciles by rank, with an explicit ``UNKNOWN`` for missing rather than a
    silent third bucket. Ranking (not raw cuts) keeps the split stable against the
    heavy right tail of dollar volume."""
    s = pd.to_numeric(values, errors="coerce")
    out = pd.Series(UNKNOWN, index=values.index, dtype=object)
    ok = s.notna()
    if int(ok.sum()) >= 3:
        r = s[ok].rank(pct=True, method="first")
        lab = pd.cut(
            r, bins=[0, 1 / 3, 2 / 3, 1.0], labels=[f"{prefix}1", f"{prefix}2", f"{prefix}3"],
            include_lowest=True,
        )
        out.loc[ok] = lab.astype(str)
    return out


def load_sector_map(repo_root: str | Path) -> dict[str, str]:
    """symbol -> GICS sector from ``data/breadth/ticker_sectors.parquet``.

    That table (1,515 names across gics_sp500/sp400/sp600 plus a small sic_mapped
    tail) is the widest tracked sector source in the repo; ``constituents.parquet``
    is a 503-name subset of it. Names outside it land in the ``UNKNOWN`` stratum —
    never dropped, because dropping unlabeled names is how a "random" arm quietly
    becomes an S&P-500 arm.
    """
    p = Path(repo_root) / "data" / "breadth" / "ticker_sectors.parquet"
    if not p.exists():
        return {}
    df = pd.read_parquet(p)
    if "ticker" not in df.columns or "sector" not in df.columns:
        return {}
    return {
        str(t): (str(s) if isinstance(s, str) and s else UNKNOWN)
        for t, s in zip(df["ticker"], df["sector"])
    }


def build_strata(
    snapshot: pd.DataFrame,
    *,
    adv_252: pd.Series,
    realized_vol_252: pd.Series,
    sector_map: dict[str, str],
) -> pd.DataFrame:
    """Attach ``cap_bucket``/``sector``/``vol_tercile``/``stratum`` to the snapshot.

    Cap is a **proxy**: no per-name market-cap store is tracked, so the trailing-252d
    dollar-ADV tercile stands in, and it is labeled a proxy on every artifact that
    carries it. A screener cap figure exists for part of the universe only, so using
    it as the stratifier would stratify by *index membership* — the exact
    survivorship contamination the arm is supposed to avoid.
    """
    out = snapshot.copy()
    out["sector"] = [sector_map.get(s, UNKNOWN) for s in out["symbol"]]
    out["cap_bucket"] = _tercile_labels(
        adv_252.reindex(out["symbol"]).reset_index(drop=True), "adv"
    ).to_numpy()
    out["vol_tercile"] = _tercile_labels(
        realized_vol_252.reindex(out["symbol"]).reset_index(drop=True), "vol"
    ).to_numpy()
    out["stratum"] = [
        Stratum(c, s, v).key
        for c, s, v in zip(out["cap_bucket"], out["sector"], out["vol_tercile"])
    ]
    return out


# ---------------------------------------------------------------------------
# the draws
# ---------------------------------------------------------------------------
def draw_blind_arm(
    strata_frame: pd.DataFrame,
    *,
    pilot: Sequence[str],
    per_stratum: int = BLIND_PER_STRATUM,
    min_sessions: int = BLIND_MIN_SESSIONS,
    seed: int = SEED_BLIND,
) -> dict[str, Any]:
    """Stratified seeded draw. Returns members plus the FULL per-stratum order.

    Eligible pool = universe - pilot - unresolved reused-ticker splice flags -
    names with fewer than ``min_sessions`` sessions (registration §3).
    """
    pilot_set = set(pilot)
    elig = strata_frame[
        (~strata_frame["symbol"].isin(pilot_set))
        & (strata_frame["n_rows"] >= min_sessions)
        & (strata_frame["blind_eligible"])
    ].copy()

    rng = np.random.default_rng(seed)
    order: dict[str, list[str]] = {}
    members: list[str] = []
    for key in sorted(elig["stratum"].unique()):
        names = sorted(elig.loc[elig["stratum"] == key, "symbol"].tolist())
        if not names:
            continue
        perm = rng.permutation(len(names))
        shuffled = [names[i] for i in perm]
        order[key] = shuffled
        members.extend(shuffled[:per_stratum])

    members = sorted(set(members))
    return {
        "seed_string": SEED_STRING_BLIND,
        "seed": seed,
        "per_stratum": per_stratum,
        "min_sessions": min_sessions,
        "eligible_pool_size": int(len(elig)),
        "n_strata_non_empty": len(order),
        "draw_order_by_stratum": order,
        "members": members,
        "blind_sha256": sha256_of_symbols(members),
    }


def draw_calibration_partition(
    strata_frame: pd.DataFrame,
    *,
    pilot: Sequence[str],
    blind: Sequence[str],
    fraction: float = CALIBRATION_FRACTION,
    seed: int = SEED_CALIBRATION,
) -> dict[str, Any]:
    """Simple seeded draw of ``floor(fraction * |pool|)`` from universe - pilot - blind.

    Drawn AFTER the blind arm and BEFORE any constant is chosen. Pilot/exemplar and
    blind names contribute nothing to calibration under any clause.
    """
    excluded = set(pilot) | set(blind)
    pool = sorted(strata_frame.loc[~strata_frame["symbol"].isin(excluded), "symbol"].tolist())
    n = int(np.floor(fraction * len(pool)))
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(pool))
    shuffled = [pool[i] for i in perm]
    members = sorted(shuffled[:n])
    return {
        "name": PARTITION_NAME,
        "seed_string": SEED_STRING_CALIBRATION,
        "seed": seed,
        "fraction": fraction,
        "pool_size": len(pool),
        "n_drawn": n,
        "draw_order": shuffled,
        "members": members,
        "calibration_sha256": sha256_of_symbols(members),
    }


def draw_dead_names(
    pool: Sequence[str], *, need: int, ledger_first: Sequence[str] = (), seed: int = SEED_DEAD
) -> dict[str, Any]:
    """Ledger rows first, then a seeded draw from the ceased-tape pool until ``need``.

    Registration §2's logged substitution: ``config/delisted_symbols.yml`` holds two
    rows, and neither is on an allowed plane, so the §13 dead-name requirement is met
    from the tape-end proxy pool with the substitution recorded rather than quietly
    lowering the floor to two.
    """
    chosen = [s for s in ledger_first]
    remaining = sorted(set(pool) - set(chosen))
    rng = np.random.default_rng(seed)
    perm = rng.permutation(len(remaining))
    order = [remaining[i] for i in perm]
    for s in order:
        if len(chosen) >= need:
            break
        chosen.append(s)
    return {
        "seed_string": SEED_STRING_DEAD,
        "seed": seed,
        "need": need,
        "ledger_first": list(ledger_first),
        "pool_size": len(pool),
        "draw_order": order,
        "members": chosen,
    }


# ---------------------------------------------------------------------------
# manifest
# ---------------------------------------------------------------------------
def build_manifest(
    *,
    asof: pd.Timestamp,
    snapshot: pd.DataFrame,
    pilot: Sequence[str],
    pilot_receipts: dict[str, Any],
    blind: dict[str, Any],
    calibration: dict[str, Any],
    procedure_hash: str,
    fingerprint_spec_hash: str,
    strata_summary: dict[str, Any],
) -> dict[str, Any]:
    """The committed partition manifest. Hashes here are the sealing act."""
    manifest = {
        "schema": "stock_identity.partition_manifest.v1",
        "registration": "research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md",
        "asof": str(pd.Timestamp(asof).date()),
        "draw_order_enforced": [
            "universe_snapshot",
            "pilot_cohort_fixed",
            "blind_arm_drawn",
            "calibration_partition_drawn",
            "manifest_hashes_written",
            "constants_calibrated",
        ],
        "universe": {
            "n_names": int(len(snapshot)),
            "n_by_plane": {
                str(k): int(v) for k, v in snapshot["price_plane_id"].value_counts().items()
            },
            "universe_sha256": universe_sha256(snapshot),
        },
        "pilot": {
            "n_names": len(pilot),
            "members": sorted(pilot),
            "receipts": pilot_receipts,
            "note": (
                "design-touched; excluded from the blind arm AND from the calibration "
                "partition. Membership choice is never evidence."
            ),
        },
        "blind_arm": {
            **{k: v for k, v in blind.items() if k != "draw_order_by_stratum"},
            "draw_order_by_stratum": blind["draw_order_by_stratum"],
            "w1_visibility": (
                "membership list only. No per-name blind row exists in any W1 artifact; "
                "blind names appear downstream solely as anonymous members of "
                "cross-sectional rank denominators."
            ),
            "provisionality": (
                "final size is set by the §8.5 power simulation at PR-5, which may only "
                "prefix-shrink within the recorded draw order or extend from the clean "
                "pool with the documented continuation seed. Never swapped, never hand-picked."
            ),
        },
        "calibration_partition": {
            **{k: v for k, v in calibration.items() if k != "draw_order"},
            "draw_order": calibration["draw_order"],
            "recent_history_guard": (
                "constant-setting receipts read calibration data only through "
                "asof - 126 trading days"
            ),
            "fit_test_boundary": "2020-01-01",
            "sealing": (
                "may set/freeze constants exactly once per constant family and is "
                "thereafter excluded from confirmatory grading"
            ),
        },
        "strata": strata_summary,
        "partition_procedure_sha256": procedure_hash,
        "fingerprint_spec_hash": fingerprint_spec_hash,
        "seeds": {
            SEED_STRING_BLIND: SEED_BLIND,
            SEED_STRING_CALIBRATION: SEED_CALIBRATION,
            SEED_STRING_DEAD: SEED_DEAD,
        },
        "authority": authority_block(),
    }
    return manifest


def check_disjoint(pilot: Iterable[str], blind: Iterable[str], calibration: Iterable[str]) -> None:
    """Raise if any two of the three sets intersect. Called at write time, not only
    in tests — a partition that overlaps is not a partition."""
    p, b, c = set(pilot), set(blind), set(calibration)
    for a_name, a, b_name, bb in (
        ("pilot", p, "blind", b),
        ("pilot", p, "calibration", c),
        ("blind", b, "calibration", c),
    ):
        overlap = a & bb
        if overlap:
            raise ValueError(
                f"{a_name} and {b_name} overlap on {sorted(overlap)[:10]} "
                f"({len(overlap)} names) — the draw is invalid"
            )


def load_manifest(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def calibration_members(manifest: dict[str, Any]) -> list[str]:
    return list(manifest["calibration_partition"]["members"])


def blind_members(manifest: dict[str, Any]) -> list[str]:
    return list(manifest["blind_arm"]["members"])
