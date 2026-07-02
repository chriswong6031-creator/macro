"""Badge passport — the shared honest-provenance marker for any displayed conviction/score.

Audit #41: the Calibration Hub, desk cards and foresight scores render precise-looking
conviction badges and 0-100 numbers whose measured basis is n=0, an unfitted magic-number
table, or a frozen self-certifying gate — indistinguishable from an EARNED number. A trader
can't tell a validated conviction from a hand-set prior or a decayed certification.

This module is the ONE place that decision provenance is turned into a badge, so every
surface (US desk cards, alt-data tier, foresight score, anticipation gate) renders the SAME
honest state instead of each page patching it (or not). It is a shared render helper + the
substrate for the build check (scripts/check_badge_passport.py), not a per-page fix.

THE PASSPORT STATES (one of):
  * ``measured``  — a spine-backed track record with n>0 matured outcomes; carries the real n.
  * ``accruing``  — the ledger exists but has n=0 matured outcomes yet (time-gated). The badge
                    says so ("accruing · n=0"); the number is an explicit PRIOR, not earned.
  * ``unfitted``  — the number is a hardcoded/heuristic table with no IC fit (foresight #41).
  * ``stale``     — a frozen self-certifying artifact past its expected refresh cadence.
  * ``prior``     — a deliberate hand-set prior (honest by design, e.g. a cold desk lean).

The helper returns a compact dict the templates render as a small chip next to the value, and
a one-liner ``passport_text`` for plain contexts. Deterministic, degrade-never-raise.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

log = logging.getLogger(__name__)

__all__ = ["passport", "passport_from_spine", "passport_text", "STATES", "is_earned"]

STATES = ("measured", "accruing", "unfitted", "stale", "prior")

_LABEL = {
    "measured": ("measured", "已验证"),
    "accruing": ("accruing · n=0", "累积中 · n=0"),
    "unfitted": ("unfitted", "未拟合"),
    "stale":    ("stale", "已过期"),
    "prior":    ("prior", "先验"),
}
# earned == the number reflects a real forward track record. Everything else is honest-but-
# not-yet-validated; UI should visually distinguish (muted chip) so a prior can't read as edge.
_EARNED = {"measured"}


def is_earned(state: str) -> bool:
    return state in _EARNED


def passport(state: str, *, n: int | None = None, hit_rate: float | None = None,
             detail: str = "", last_validated: str | None = None,
             expected_max_age_days: int | None = None) -> dict:
    """Build a passport chip. ``state`` must be one of STATES (an unknown state degrades to
    'prior' — the conservative honest default, never a crash). ``n`` is the matured-outcome
    count (shown for 'measured'/'accruing'); ``hit_rate`` the real forward hit-rate for a
    measured badge. Returns::

        {"state", "earned", "label_en", "label_zh", "n", "hit_rate", "detail", "tooltip_en"}
    """
    st = state if state in STATES else "prior"
    en, zh = _LABEL[st]
    if st == "accruing" and n is not None:
        en = f"accruing · n={n}"; zh = f"累积中 · n={n}"
    elif st == "measured" and n is not None:
        en = f"measured · n={n}"; zh = f"已验证 · n={n}"
    tip = {
        "measured": "Earned from a matured forward track record (spine-graded).",
        "accruing": "The ledger has not matured (n=0). This is a PRIOR, not an earned weight.",
        "unfitted": "A heuristic/hand-set number with no forward IC fit — display only.",
        "stale":    "A frozen self-certifying artifact past its expected refresh cadence.",
        "prior":    "A deliberate hand-set prior — honest by design, not a measured edge.",
    }[st]
    return {
        "state": st, "earned": is_earned(st),
        "label_en": en, "label_zh": zh,
        "n": n, "hit_rate": hit_rate, "detail": detail,
        "last_validated": last_validated,
        "expected_max_age_days": expected_max_age_days,
        "tooltip_en": tip,
    }


def passport_from_spine(engine: str, *, family: str | None = None, horizon: int | None = None,
                        root=None) -> dict:
    """Derive the passport state directly from the outcome spine's measured IC for an emitter.
    n>0 matured → 'measured' (with the real n + hit-rate); n==0 → 'accruing'. This is the path
    a spine-backed surface (desk cards, alt-data tier, US board) uses so the badge state is
    never hand-maintained. Degrade-never-raise: a spine read failure → 'accruing'."""
    try:
        from engine import spine
        m = spine.measured_ic(root=root, engine=engine, family=family, horizon=horizon)
        n = int(m.get("n") or 0)
        if n > 0:
            return passport("measured", n=n, hit_rate=m.get("hit_rate"))
        return passport("accruing", n=0)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("passport_from_spine(%s) failed: %s", engine, e)
        return passport("accruing", n=0)


def passport_text(p: dict) -> str:
    """One-line plain rendering for non-HTML contexts (markdown briefings, logs)."""
    bits = [p.get("label_en", p.get("state", "prior"))]
    if p.get("state") == "measured" and p.get("hit_rate") is not None:
        bits.append(f"hit {p['hit_rate']:.0%}")
    if p.get("detail"):
        bits.append(p["detail"])
    return " · ".join(bits)


def freshness_state(last_validated: str | None, expected_max_age_days: int | None,
                    today: date | None = None) -> str:
    """'stale' if a self-certifying artifact is past its expected refresh cadence, else
    'measured'. For the anticipation-gate / foresight case (#41): a frozen 'Phase-0 measured'
    badge must flip to 'stale' once it exceeds its cadence — it can't self-certify forever."""
    if not last_validated or expected_max_age_days is None:
        return "unfitted"
    try:
        lv = datetime.fromisoformat(str(last_validated).replace("Z", "+00:00")).date()
        ref = today or datetime.now(timezone.utc).date()
        return "stale" if (ref - lv).days > expected_max_age_days else "measured"
    except Exception:  # noqa: BLE001
        return "unfitted"
