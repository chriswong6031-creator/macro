"""engine/levels_trust_index.py — per-ticker reliability leaderboard for the levels board.

Voltick Gamma-Levels program, WP-C2. Aggregates the WP-C1 grades ledger into a per-ticker
"Trust Index": how reliably each ticker's named levels have described what price actually
did next — did the Keystone draw price, did the walls contain the close, did the
expected-move band hold. A ticker that ignores its levels ranks LOW, on purpose. Worst
names are shown, not hidden; tickers with too few graded sessions are held out until they
have a real base to stand on.

DISPLAY-TIER: descriptive historical reliability of structural levels — not a prediction,
not a win rate, and never a buy-or-sell ranking. Positioning, not prophecy.

PURE: no I/O. The builder (scripts/build_levels_trust_index.py) reads the grades parquet,
reduces it to one board-level record per (root, session_date), and calls compute_trust_index
here.
"""
from __future__ import annotations

from typing import Any

SCHEMA = "levels_trust_index.v1"

# A ticker joins the ranking only once it has a real base of graded sessions.
MIN_SESSIONS = 8


def _rate(k: int, n: int) -> float | None:
    return round(k / n, 4) if n > 0 else None


def _pct(rate: float | None) -> float:
    return 0.0 if rate is None else rate


def compute_trust_index(board_records: list[dict], ci_fn=None, min_sessions: int = MIN_SESSIONS) -> dict:
    """Build the ``levels_trust_index.v1`` payload from board-level grade records.

    board_records: one dict per graded board, keys: root, session_date, wall_contained
    (bool|None), band_contained (bool|None), anchor_drew (bool|None). Only records that were
    actually graded (a real next-session bar) should be passed in.

    ci_fn(k, n) -> (lo, hi) | None  (pass engine.grading_stats.wilson_ci).

    Returns a ranked list (highest trust first) + a held-out list (fewer than min_sessions
    graded), each carrying the three component rates, the composite, N, and a Wilson CI on
    the composite's pooled component hits. The composite mirrors the reference product's
    read: mean of (Keystone drew, band held, closed inside the walls).
    """
    by_root: dict[str, list[dict]] = {}
    for r in board_records:
        root = r.get("root")
        if not root:
            continue
        by_root.setdefault(str(root).upper(), []).append(r)

    ranked: list[dict] = []
    banking: list[dict] = []
    for root, recs in by_root.items():
        n = len(recs)
        anc = [r for r in recs if r.get("anchor_drew") is not None]
        wal = [r for r in recs if r.get("wall_contained") is not None]
        ban = [r for r in recs if r.get("band_contained") is not None]
        anc_k = sum(1 for r in anc if r["anchor_drew"])
        wal_k = sum(1 for r in wal if r["wall_contained"])
        ban_k = sum(1 for r in ban if r["band_contained"])
        anc_rate = _rate(anc_k, len(anc))
        wal_rate = _rate(wal_k, len(wal))
        ban_rate = _rate(ban_k, len(ban))
        # composite = mean of the three available component rates (skip components with no data)
        comps = [x for x in (anc_rate, wal_rate, ban_rate) if x is not None]
        composite = round(sum(comps) / len(comps), 4) if comps else None
        # a pooled Wilson CI over all component trials, so a low-N ticker reads honestly wide
        pooled_k = anc_k + wal_k + ban_k
        pooled_n = len(anc) + len(wal) + len(ban)
        ci = None
        if ci_fn is not None and pooled_n > 0:
            c = ci_fn(pooled_k, pooled_n)
            ci = [round(c[0], 4), round(c[1], 4)] if c else None

        entry = {
            "root": root,
            "sessions": n,
            "anchor_drew": {"rate": anc_rate, "n": len(anc), "misses": len(anc) - anc_k},
            "walls_contained": {"rate": wal_rate, "n": len(wal), "misses": len(wal) - wal_k},
            "band_contained": {"rate": ban_rate, "n": len(ban), "misses": len(ban) - ban_k},
            "composite": composite,
            "composite_ci": ci,
            "read": (f"Keystone reached {_fmt(anc_rate)} · band held {_fmt(ban_rate)} · "
                     f"closed in walls {_fmt(wal_rate)}"),
        }
        if n >= min_sessions:
            ranked.append(entry)
        else:
            banking.append(entry)

    # highest composite first; ties broken by more sessions (more evidence ranks higher)
    ranked.sort(key=lambda e: (_pct(e["composite"]), e["sessions"]), reverse=True)
    banking.sort(key=lambda e: e["sessions"], reverse=True)
    for i, e in enumerate(ranked, 1):
        e["rank"] = i

    least = None
    if ranked:
        lo = min(ranked, key=lambda e: _pct(e["composite"]))
        least = {"root": lo["root"], "composite": lo["composite"], "sessions": lo["sessions"]}

    return {
        "schema": SCHEMA,
        "n_ranked": len(ranked),
        "n_banking": len(banking),
        "min_sessions": min_sessions,
        "ranked": ranked,
        "banking": banking,   # fewer than min_sessions graded — not yet ranked
        "least_reliable": least,
        "disclaimer": ("Descriptive historical reliability of structural levels, pooled per "
                       "ticker from graded sessions — not a prediction, not a win rate, and "
                       "never a buy or sell ranking. Positioning, not prophecy. Misses shown."),
    }


def _fmt(rate: float | None) -> str:
    return "—" if rate is None else f"{rate:.0%}"
