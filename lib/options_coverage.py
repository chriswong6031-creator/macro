"""ONE coverage object for the options family (OIP R8).

THE PROBLEM.  Four builders in this family each answer "how much of the universe did we
actually see?" in a different, non-comparable shape:

  build_options_command   covered / universe / coverage_pct / quality_en / quality_zh
  build_gex_board         {group: {covered, total}} + a "__all__" roll-up
  build_options_screener  n_names / n_young / n_mature / n_skew / n_ivspread / n_relvol
  build_flow_desk         a STRING — "353 names · EOD · direction approx"

So no surface can put two of them side by side, no audit can compare them, and the
flow desk's number cannot be read by a machine at all.  R8 defines the shape once.

CONTRACT
  * ADDITIVE ONLY.  Emitted under the key ``coverage_v1`` ALONGSIDE every existing
    field.  Nothing is removed or renamed — the four builders' current keys are load-
    bearing for pages that ship today, and no surface consumes this object yet.
    Surfaces adopt it in later OIP waves.
  * DISPLAY-TIER.  A coverage count never ranks, sizes, or gates anything.
  * PLAIN WORDS, BILINGUAL.  Every name is an EN/ZH pair of ordinary words — no store
    paths, no slugs, no enums, no "n=".  ``key`` is machine-only and must never be
    rendered; surfaces render ``name_en`` / ``name_zh``.
  * HONEST NULLS.  An uncountable universe is ``n: None``, never 0, and
    ``coverage_pct`` is None rather than a fabricated 100%.  ``sessions_behind`` is
    computed from the exchange calendar (``lib.nyse_calendar``), never wall-clock days,
    so a Monday morning does not report every store as a session staler than it is.

SHAPE (schema ``options_coverage.v1``)

    {
      "schema": "options_coverage.v1",
      "universe": {"name_en": "US options universe", "name_zh": "美股期权范围",
                   "n": 403},
      "covered": 370,
      "coverage_pct": 91.8,          # None when either side is unknown
      "asof": "2026-07-28",          # the session this coverage was counted at
      "sessions_behind": 1,          # of `asof`, from the NYSE calendar; None if unknown
      "sources": [                   # per-source freshness, one row per input store
        {"key": "flow_desk", "name_en": "Options tape", "name_zh": "期权成交",
         "asof": "2026-07-28", "n": 353, "sessions_behind": 1}
      ]
    }
"""
from __future__ import annotations

SCHEMA = "options_coverage.v1"


def _as_asof(v) -> str | None:
    """A date string, or None.  `str(pd.NaT)` is the literal "NaT" and `str(nan)` is
    "nan" — publishing either as an as-of stamp is worse than publishing nothing."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nat", "nan", "none", "<na>"):
        return None
    return s


def _sessions_behind(asof) -> int | None:
    """Completed sessions missing behind ``asof``, or None when it cannot be judged.

    Calendar-derived, never a wall-clock day count — a store holding Friday's close is
    0 sessions behind on Saturday, Sunday AND Monday morning.
    """
    if not asof:
        return None
    try:
        import pandas as pd

        from lib import nyse_calendar

        return int(nyse_calendar.sessions_behind(pd.Timestamp(str(asof)).date()))
    except Exception:  # noqa: BLE001
        return None


def _as_int(v) -> int | None:
    """int(v) or None.  NEVER raises — `int(float("nan"))` raises ValueError, which would
    break this module's "never raises" contract the first time a count arrived as NaN from
    a pandas aggregation (minor 4, review 2026-07-29).  Booleans are rejected because
    `isinstance(True, int)` is True and a flag is not a count."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):   # NaN / +-inf
        return None
    return int(f)


def source(key: str, name_en: str, name_zh: str, *,
           asof=None, n: int | None = None) -> dict:
    """One input store's freshness row.

    ``key`` is machine-only (never rendered).  ``name_en`` / ``name_zh`` are the plain
    words a surface prints.  ``asof`` is the store's own session stamp; ``n`` the number
    of names it covered.  Both may be None — an unknown is printed as unknown.
    """
    return {
        "key": str(key),
        "name_en": str(name_en),
        "name_zh": str(name_zh),
        "asof": _as_asof(asof),
        "n": _as_int(n),
        "sessions_behind": _sessions_behind(asof),
    }


def coverage_object(*, universe_name_en: str, universe_name_zh: str,
                    universe_n: int | None, covered_n: int | None,
                    asof=None, sources: list[dict] | None = None) -> dict:
    """Build the shared coverage object.  Never raises; unknowns stay None.

    ``covered_n`` is clamped to ``universe_n`` when both are known — a coverage share
    above 100% is a counting bug, and publishing it as ">100%" is worse than clamping
    and letting the two raw counts stand for inspection.
    """
    uni = _as_int(universe_n)
    cov = _as_int(covered_n)
    pct = None
    if uni is not None and cov is not None and uni > 0:
        pct = round(min(cov, uni) / uni * 100.0, 1)
    return {
        "schema": SCHEMA,
        "universe": {
            "name_en": str(universe_name_en),
            "name_zh": str(universe_name_zh),
            "n": uni,
        },
        "covered": cov,
        "coverage_pct": pct,
        "asof": _as_asof(asof),
        "sessions_behind": _sessions_behind(asof),
        "sources": list(sources or []),
    }
