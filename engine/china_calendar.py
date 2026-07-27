"""China/HK forward event calendar — AGGREGATOR · DISPLAY-TIER · CONTEXT-ONLY · LEAF.

One structured forward calendar for the China/HK planes, assembled from organs that
already exist. It ENCODES NOTHING of its own about release cadence: the PMI/CPI/PPI/
CREDIT/TRADE/ACTIVITY/GDP/LPR/MLF/FXRES rules live in ``engine.china_event_calendar``
and the HK/US ones in ``engine.hk_event_calendar``; both are imported and re-shaped
here. Re-encoding a release rule in this module would create a second, silently
diverging schedule — the whole reason this organ aggregates instead of computing.

Three source classes, per CNH-R12 ("calendar is data + rules, not vibes"):
  • ``rule``   — algorithmic entries (LPR 20th, NBS release days, HKMA cadences).
  • ``feed``   — announced ad-hoc entries read from a MONITORED STORE: the PBoC OMO
                 bulletin tape (data/china_omo/operations.parquet) and the A-share
                 reporting calendar (data/china_earnings/calendar.parquet).
  • ``static`` — political rhythm (Two Sessions, Politburo economic meetings, CEWC)
                 and the CY-tabled irregular releases. Refreshed MANUALLY.
Every row carries its class, so a reader can always tell an announced date from a
guessed one; ``approx=True`` marks the windows whose exact day is not yet published.

AUTHORITY (hard): every payload carries ``authority {tier: "context_only",
may_rank: false}``. RIC-R3 forbids calendar/event-window-gated risk legs outright —
a calendar row may NEVER gate, size, dampen or feed a risk or state channel. This
module therefore imports nothing from the scored core and nothing in the scored core
may import it; the test suite pins that both ways.

DEGRADE: a missing/unreadable store is a ``data_gaps`` line, never an exception and
never a silent zero. Every public function returns plain-Python data and never raises
into the build.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

log = logging.getLogger(__name__)

SCHEMA = "china_calendar.v1"
DEFAULT_HORIZON_DAYS = 45

# The one authority stamp. Read by any consumer that needs to prove the artifact is
# not rankable; asserted by the schema-pin test.
AUTHORITY: dict = {"tier": "context_only", "may_rank": False}

# source_class priority when two organs describe the SAME (date, etype, region):
# an announced operation beats a computed rule beats a static guess.
_CLASS_PRIORITY = {"feed": 0, "rule": 1, "static": 2}

# The engines emit source="computed" for date-arithmetic rows and source="static" for
# rows read off their CY tables. Anything else is treated as static (safe direction:
# an unknown provenance is never promoted to "rule").
_ENGINE_CLASS = {"computed": "rule", "static": "static"}

# engine importance ("high"/"med") -> the calendar's display impact enum.
_IMPACT = {"high": "high", "med": "medium", "medium": "medium", "low": "low"}

_OMO_FEED_KINDS = ("reverse_repo_preannounce", "outright_repo_tender", "mlf_tender")

# A feed MLF tender within +/- this many days of the rule-generated MLF row means the
# rule row is a GUESS at the same operation the bulletin already announced.
_MLF_SUPPRESS_DAYS = 10

# Share of the covered universe that must report inside a month before it counts as an
# earnings-season WINDOW rather than a scatter of individual results.
_EARNINGS_DENSITY = 0.20


# --------------------------------------------------------------------------- #
# static political rhythm (CNH-R12) — MANUALLY REFRESHED
# --------------------------------------------------------------------------- #
# These are the recurring political windows, not published dates: the exact opening
# day of a Politburo economic meeting is announced days ahead at most, so every row
# here is approx=True and carries a window rather than a point. REFRESH THIS TABLE BY
# HAND each December for the next calendar year (the two-year runway below means a
# missed refresh shows up as an empty far horizon, and assemble_calendar() prints a
# data_gaps line the moment the horizon runs past the last tabled year).
_POLITICAL_YEARS = (2026, 2027)
_POLITICAL_WINDOWS: tuple[dict, ...] = (
    {"etype": "two_sessions", "start": (3, 3), "end": (3, 12), "impact": "high",
     "label_en": "Two Sessions (NPC + CPPCC) window — growth target, budget, policy tone",
     "label_zh": "全国两会窗口（人大＋政协）：增长目标、预算与政策基调"},
    {"etype": "politburo_econ", "start": (4, 20), "end": (4, 30), "impact": "high",
     "label_en": "Politburo economic meeting window (late April)",
     "label_zh": "中央政治局会议（经济）窗口（4月下旬）"},
    {"etype": "politburo_econ", "start": (7, 20), "end": (7, 31), "impact": "high",
     "label_en": "Politburo economic meeting window (late July)",
     "label_zh": "中央政治局会议（经济）窗口（7月下旬）"},
    # The Oct-Dec leg is deliberately ONE long window: the autumn plenum and the
    # year-end Politburo session both land inside it and neither is scheduled publicly.
    {"etype": "politburo_econ", "start": (10, 20), "end": (12, 15), "impact": "medium",
     "label_en": "Politburo / plenum window (autumn to year-end)",
     "label_zh": "中央政治局会议／全会窗口（秋季至年末）"},
    {"etype": "cewc", "start": (12, 10), "end": (12, 20), "impact": "high",
     "label_en": "Central Economic Work Conference (CEWC) window — next-year policy line",
     "label_zh": "中央经济工作会议窗口：定调次年政策"},
)

# A-share report periods (the `period` column is YYYYMMDD of the reporting period end).
_PERIOD_LABEL = {
    "0331": ("Q1 results", "一季报"),
    "0630": ("interim results", "中报"),
    "0930": ("Q3 results", "三季报"),
    "1231": ("annual results", "年报"),
}


# --------------------------------------------------------------------------- #
# pure helpers
# --------------------------------------------------------------------------- #
def _iso(d: date) -> str:
    return d.isoformat()


def _entry(*, d: date, etype: str, label_en: str, label_zh: str, region: str,
           impact: str, source_class: str, source: str,
           window_end: date | None = None, approx: bool = False) -> dict:
    """The ONE entry constructor. Every field of the v1 row shape is set here, so a
    schema drift is a one-line change and the schema-pin test has a single target."""
    return {
        "date": _iso(d),
        "window_end": _iso(window_end) if window_end else None,
        "etype": etype,
        "label_en": label_en,
        "label_zh": label_zh,
        "region": region,
        "impact": _IMPACT.get(impact, "medium"),
        "source_class": source_class,
        "source": source,
        "approx": bool(approx),
    }


def _amount_labels(amount_bn) -> tuple[str, str]:
    """(EN, ZH) rendering of an OMO amount. Returns ("", "") when the value is absent.

    ``amount_bn`` is the bulletin's own 亿元 figure VERBATIM — 3255 means 3255亿元.
    亿 = 1e8, so the EN side divides by 10 to reach RMB billions (3255亿元 = RMB
    325.5bn). The ZH side keeps the native unit, because that is how the PBoC states
    it and how a Chinese reader expects to see it. PURE.
    """
    try:
        v = float(amount_bn)
    except (TypeError, ValueError):
        return "", ""
    if v != v or v <= 0:          # NaN or non-positive -> no amount was published
        return "", ""
    rmb_bn = v / 10.0
    en = f"RMB {rmb_bn:,.0f}bn" if abs(rmb_bn - round(rmb_bn)) < 1e-9 else f"RMB {rmb_bn:,.1f}bn"
    zh = f"{v:,.0f}亿元" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}亿元"
    return en, zh


def _rate_labels(rate_pct) -> tuple[str, str]:
    """(EN, ZH) rendering of an operation rate, or ("", "") when none was stated."""
    try:
        r = float(rate_pct)
    except (TypeError, ValueError):
        return "", ""
    if r != r:
        return "", ""
    return f"at {r:.2f}%", f"利率{r:.2f}%"


def _to_date(value) -> date | None:
    """Parse an ISO-ish date out of a store cell. Never raises. PURE."""
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    s = str(value).strip()
    if not s or s.lower() in ("nat", "nan", "none"):
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def resolve_asof(asof: date | None = None) -> date:
    """Explicit asof (testing) -> the China regime's last classified day -> wall clock.

    Delegates to engine.china_event_calendar so the calendar shares ONE as-of basis
    with the events it aggregates (a second resolver would desync the window filter).
    """
    if asof is not None:
        return asof
    try:
        from engine.china_event_calendar import resolve_asof as _cn_resolve
        return _cn_resolve(None)
    except Exception as e:  # noqa: BLE001 — degrade to the wall clock
        log.debug("china_calendar: asof resolution degraded (%s)", e)
        return date.today()


# --------------------------------------------------------------------------- #
# leg 1/2 — the rule + CY-table engines (imported, never re-encoded)
# --------------------------------------------------------------------------- #
def _engine_entries(asof: date, horizon_days: int) -> tuple[list[dict], list[str]]:
    """CN + HK engine events, re-shaped into calendar rows. Degrades per engine."""
    out: list[dict] = []
    gaps: list[str] = []

    try:
        from engine.china_event_calendar import china_macro_events
        for ev in china_macro_events(asof, horizon_days):
            d = _to_date(ev.get("date"))
            if d is None:
                continue
            out.append(_entry(
                d=d, etype=str(ev.get("type") or "").upper(),
                label_en=str(ev.get("name_en") or ev.get("type") or ""),
                label_zh=str(ev.get("name_zh") or ev.get("type") or ""),
                region="cn", impact=str(ev.get("importance") or "med"),
                source_class=_ENGINE_CLASS.get(str(ev.get("source")), "static"),
                source="engine.china_event_calendar",
                # a WINDOW-OPEN row (CREDIT/TRADE) and the MLF ~15th rule are
                # approximations of an unpublished day; the tabled/arithmetic release
                # days are not.
                approx=str(ev.get("type")) in ("CREDIT", "TRADE", "MLF", "FXRES")))
    except Exception as e:  # noqa: BLE001
        log.warning("china_calendar: CN event engine unavailable (%s)", e)
        gaps.append("engine.china_event_calendar unavailable — no CN rule/static rows "
                    "in this build")

    try:
        from engine.hk_event_calendar import hk_macro_events
        for ev in hk_macro_events(asof, horizon_days):
            # hk_macro_events RE-EXPORTS the CN high-impact prints as region "CN" with
            # a CN_ prefix. Those are the very rows the CN leg above already emitted,
            # so they are dropped here rather than deduped downstream (the CN_ prefix
            # would defeat the (date, etype, region) key and ship every CN print twice).
            if str(ev.get("region") or "").upper() == "CN":
                continue
            d = _to_date(ev.get("date"))
            if d is None:
                continue
            out.append(_entry(
                d=d, etype=str(ev.get("type") or "").upper(),
                label_en=str(ev.get("name_en") or ev.get("type") or ""),
                label_zh=str(ev.get("name_zh") or ev.get("type") or ""),
                # US prints (FOMC / CPI / payrolls) ride the HK calendar because the
                # peg imports them; the row shape carries two regions only, so they
                # are HK rows whose etype still says US_*.
                region="hk", impact=str(ev.get("importance") or "med"),
                source_class=_ENGINE_CLASS.get(str(ev.get("source")), "static"),
                source="engine.hk_event_calendar",
                approx=str(ev.get("type")) in ("HK_TRADE", "HK_RETAIL")))
    except Exception as e:  # noqa: BLE001
        log.warning("china_calendar: HK event engine unavailable (%s)", e)
        gaps.append("engine.hk_event_calendar unavailable — no HK/US rule/static rows "
                    "in this build")

    return out, gaps


# --------------------------------------------------------------------------- #
# leg 3 — announced PBoC operations (feed)
# --------------------------------------------------------------------------- #
def _data_root() -> Path:
    from lib import config
    return config.data_dir()


def omo_store_path() -> Path:
    """data/china_omo/operations.parquet. Split out so tests can point it at a tmp
    store without monkeypatching lib.config for the whole process."""
    return _data_root() / "china_omo" / "operations.parquet"


def earnings_store_path() -> Path:
    """data/china_earnings/calendar.parquet (see omo_store_path for why this exists)."""
    return _data_root() / "china_earnings" / "calendar.parquet"


_OMO_LABELS = {
    "reverse_repo_preannounce": ("PBoC reverse repo (pre-announced)", "央行逆回购操作（预告）"),
    "outright_repo_tender": ("PBoC outright reverse repo tender", "央行买断式逆回购操作"),
    "mlf_tender": ("PBoC MLF tender", "央行中期借贷便利（MLF）操作"),
}


def _omo_entries(asof: date, end: date) -> tuple[list[dict], list[str]]:
    """Announced-but-not-yet-executed PBoC operations from the OMO bulletin tape.

    Read directly from the parquet rather than through collectors.china_omo: that
    module imports collectors.base, which imports ``requests``, and a display-tier
    builder must not acquire a network dependency it never uses (in a minimal-deps
    lane the import would fail and blank the whole feed leg silently).
    """
    gaps: list[str] = []
    path = omo_store_path()
    if not path.exists():
        gaps.append("china_omo store unavailable (data/china_omo/operations.parquet "
                    "absent) — no announced PBoC operations in this calendar")
        return [], gaps
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("china_calendar: OMO store unreadable (%s)", e)
        gaps.append("china_omo store unavailable (operations.parquet present but "
                    "UNREADABLE) — no announced PBoC operations in this calendar")
        return [], gaps

    missing = [c for c in ("op_date", "kind") if c not in df.columns]
    if missing:
        gaps.append(f"china_omo store unavailable (schema drift: missing {missing}) — "
                    "no announced PBoC operations in this calendar")
        return [], gaps

    out: list[dict] = []
    for row in df.to_dict("records"):
        kind = str(row.get("kind") or "")
        if kind not in _OMO_FEED_KINDS:
            continue
        d = _to_date(row.get("op_date"))
        if d is None or d < asof or d > end:
            continue
        head_en, head_zh = _OMO_LABELS[kind]
        tenor = str(row.get("tenor_label") or "").strip()
        amt_en, amt_zh = _amount_labels(row.get("amount_bn"))
        rate_en, rate_zh = _rate_labels(row.get("rate_pct"))
        bits_en = [head_en] + [b for b in (tenor, amt_en, rate_en) if b]
        bits_zh = [head_zh] + [b for b in (tenor, amt_zh, rate_zh) if b]
        out.append(_entry(
            d=d, etype="omo_" + kind,
            # the tenor is quoted in Chinese on both sides on purpose: "7天" is the
            # bulletin's own term and translating it invents a tenor the PBoC did not
            # state. Amount/rate ARE translated (see _amount_labels).
            label_en=" — ".join([bits_en[0], ", ".join(bits_en[1:])]) if len(bits_en) > 1 else bits_en[0],
            label_zh="：".join([bits_zh[0], "，".join(bits_zh[1:])]) if len(bits_zh) > 1 else bits_zh[0],
            region="cn", impact="high" if kind == "mlf_tender" else "medium",
            source_class="feed", source="china_omo.operations",
            window_end=_to_date(row.get("maturity_date")),
            approx=False))
    if not out:
        gaps.append("china_omo store holds no announced operation inside the horizon "
                    "(the tape is present; the PBoC simply has nothing pending)")
    return out, gaps


def _suppress_ruled_mlf(entries: list[dict]) -> tuple[list[dict], list[str]]:
    """Announced beats guessed: drop the rule-generated MLF row when a FEED mlf_tender
    describes the same operation (within +/- _MLF_SUPPRESS_DAYS). Pure.

    The CN engine puts MLF on the ~15th by arithmetic; when the PBoC has already
    published the tender the exact date is known, and shipping both would show the
    user two MLF operations in one month.
    """
    feed_days = [date.fromisoformat(e["date"]) for e in entries
                 if e["source_class"] == "feed" and e["etype"] == "omo_mlf_tender"]
    if not feed_days:
        return entries, []
    kept, notes = [], []
    for e in entries:
        if e["etype"] == "MLF" and e["source_class"] in ("rule", "static"):
            d = date.fromisoformat(e["date"])
            near = [f for f in feed_days if abs((f - d).days) <= _MLF_SUPPRESS_DAYS]
            if near:
                notes.append(
                    f"MLF rule row {e['date']} suppressed — the PBoC has ANNOUNCED an "
                    f"MLF tender on {near[0].isoformat()} (feed beats rule; the ~15th "
                    f"arithmetic row would double-count the same operation)")
                continue
        kept.append(e)
    return kept, notes


# --------------------------------------------------------------------------- #
# leg 4 — political rhythm (static)
# --------------------------------------------------------------------------- #
def _political_entries(asof: date, end: date) -> tuple[list[dict], list[str]]:
    out: list[dict] = []
    for year in _POLITICAL_YEARS:
        for w in _POLITICAL_WINDOWS:
            try:
                start = date(year, *w["start"])
                w_end = date(year, *w["end"])
            except ValueError:                      # pragma: no cover — table typo guard
                continue
            # in-horizon if the WINDOW intersects [asof, end] — a window we are already
            # inside is the most decision-relevant row on the page.
            if w_end < asof or start > end:
                continue
            out.append(_entry(
                d=start, etype=w["etype"], label_en=w["label_en"],
                label_zh=w["label_zh"], region="cn", impact=w["impact"],
                source_class="static", source="china_calendar.political_windows",
                window_end=w_end, approx=True))
    gaps: list[str] = []
    if end.year > max(_POLITICAL_YEARS):
        gaps.append(
            f"political-window table covers CY{min(_POLITICAL_YEARS)}-"
            f"CY{max(_POLITICAL_YEARS)} only; the horizon reaches {end.isoformat()} — "
            "refresh _POLITICAL_WINDOWS in engine/china_calendar.py")
    return out, gaps


# --------------------------------------------------------------------------- #
# leg 5 — A-share reporting season (feed)
# --------------------------------------------------------------------------- #
def _earnings_entries(asof: date, end: date) -> tuple[list[dict], list[str]]:
    """One window per month in which >20% of the covered universe reports.

    Individual results are not calendar rows (5,000 of them would drown the artifact);
    the SEASON is. The density is stated in the label so the reader can see how much
    of the board the window actually covers.
    """
    gaps: list[str] = []
    path = earnings_store_path()
    if not path.exists():
        gaps.append("china_earnings store unavailable (data/china_earnings/"
                    "calendar.parquet absent) — no reporting-season windows")
        return [], gaps
    try:
        import pandas as pd
        df = pd.read_parquet(path)
    except Exception as e:  # noqa: BLE001
        log.warning("china_calendar: earnings store unreadable (%s)", e)
        gaps.append("china_earnings store unavailable (calendar.parquet present but "
                    "UNREADABLE) — no reporting-season windows")
        return [], gaps

    if "next_date" not in df.columns or df.empty:
        gaps.append("china_earnings store unavailable (no next_date column / empty) — "
                    "no reporting-season windows")
        return [], gaps

    universe = len(df)
    buckets: dict[tuple[int, int], list[tuple[date, str]]] = {}
    for row in df.to_dict("records"):
        d = _to_date(row.get("next_date"))
        if d is None or d < asof or d > end:
            continue
        buckets.setdefault((d.year, d.month), []).append(
            (d, str(row.get("period") or "")))

    out: list[dict] = []
    for (y, m), hits in sorted(buckets.items()):
        share = len(hits) / universe if universe else 0.0
        if share <= _EARNINGS_DENSITY:
            continue
        days = sorted(h[0] for h in hits)
        periods = [h[1][4:8] for h in hits if len(h[1]) == 8]
        modal = max(set(periods), key=periods.count) if periods else ""
        kind_en, kind_zh = _PERIOD_LABEL.get(modal, ("results", "定期报告"))
        pct = round(share * 100)
        out.append(_entry(
            d=days[0], etype="earnings_season", region="cn",
            label_en=(f"A-share {kind_en} season — {pct}% of the covered board "
                      f"reports in {y}-{m:02d}"),
            label_zh=f"A股{kind_zh}密集披露期：{y}年{m}月约{pct}%的覆盖名单披露",
            impact="high" if share >= 0.5 else "medium",
            source_class="feed", source="china_earnings.calendar",
            window_end=days[-1], approx=False))
    if not out and universe:
        gaps.append("china_earnings store holds no month above the 20% reporting-"
                    "density gate inside the horizon")
    return out, gaps


# --------------------------------------------------------------------------- #
# public: the assembled calendar
# --------------------------------------------------------------------------- #
def _dedup(entries: list[dict]) -> list[dict]:
    """Keep ONE row per (date, etype, region), preferring feed > rule > static."""
    best: dict[tuple[str, str, str], dict] = {}
    for e in entries:
        key = (e["date"], e["etype"], e["region"])
        cur = best.get(key)
        if cur is None or _CLASS_PRIORITY.get(e["source_class"], 9) < \
                _CLASS_PRIORITY.get(cur["source_class"], 9):
            best[key] = e
    return list(best.values())


def assemble_calendar(asof: date | None = None,
                      horizon_days: int = DEFAULT_HORIZON_DAYS) -> dict:
    """The full forward China/HK calendar payload. NEVER raises; degrades to gaps.

    `asof` is injectable for testing; default shares the CN engine's as-of basis.
    """
    try:
        today = resolve_asof(asof)
        horizon_days = int(horizon_days or DEFAULT_HORIZON_DAYS)
        end = today + timedelta(days=horizon_days)

        entries: list[dict] = []
        gaps: list[str] = []
        for leg in (_engine_entries(today, horizon_days),
                    _omo_entries(today, end),
                    _political_entries(today, end),
                    _earnings_entries(today, end)):
            rows, leg_gaps = leg
            entries.extend(rows)
            gaps.extend(leg_gaps)

        entries, notes = _suppress_ruled_mlf(entries)
        gaps.extend(notes)
        entries = _dedup(entries)
        entries.sort(key=lambda e: (e["date"], e["region"], e["etype"]))

        return {
            "schema": SCHEMA,
            "asof": today.isoformat(),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "horizon_days": horizon_days,
            "entries": entries,
            "data_gaps": gaps,
            "authority": dict(AUTHORITY),
        }
    except Exception as e:  # noqa: BLE001 — a calendar must never break a build
        log.error("china_calendar.assemble_calendar failed (%s)", e)
        return {
            "schema": SCHEMA,
            "asof": (asof or date.today()).isoformat(),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "horizon_days": int(horizon_days or DEFAULT_HORIZON_DAYS),
            "entries": [],
            "data_gaps": [f"calendar assembly failed ({type(e).__name__}) — "
                          "empty calendar shipped rather than a broken build"],
            "authority": dict(AUTHORITY),
        }
