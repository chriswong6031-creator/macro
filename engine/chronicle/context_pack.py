"""engine.chronicle.context_pack — the one pack() symbol every consumer binds
(masterplan §2.4). Deterministic assembly over data/chronicle/events.jsonl.

No LLM calls. ``narratives`` is always ``[]`` at W0 (the LLM narrative/prose
layer is a W1 deliverable). Every returned line carries a source_ref (and a
site_url when the source event has one). Budget respected via per-tier reserve
fractions: long 20% / medium 30% / short 50% of token_budget when all three
horizons are requested; unused reserve spills DOWN the long -> medium -> short
chain (a sparse long tier hands its leftover to medium, which hands its
leftover to short). When fewer than three horizons are requested, the same
20/30/50 relative weights are renormalized over just the requested tiers so
the fractions still sum to 1.0. Token estimate = chars / 4 throughout.

``as_of`` is a HARD RIGHT EDGE by default (B3): only events with
``date <= as_of`` are ever considered, so a point-in-time query (e.g. a
vault-W6 ``as_of`` join) can never see a future event. ``window`` controls how
far BACK from as_of to look (default 7 days). Looking forward of as_of is an
explicit opt-in via ``window_forward`` — the only sanctioned use is the §0
gate-3(c) "3-months-ago, ±1w" narrative-backdrop query, which is NOT a
point-in-time join and must ask for the future window by name.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger(__name__)

_RESERVE_FRACTIONS = {"long": 0.20, "medium": 0.30, "short": 0.50}
_TIER_ORDER = ("long", "medium", "short")  # spill-down order


def _repo_root(root=None) -> Path:
    if root is not None:
        return Path(root)
    return Path(__file__).resolve().parent.parent.parent


def _load_events(repo: Path) -> list[dict]:
    path = repo / "data" / "chronicle" / "events.jsonl"
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:  # noqa: BLE001
                continue
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.context_pack: events load failed: %s", exc)
        return []
    return out


def _parse_window(window) -> timedelta:
    if isinstance(window, timedelta):
        return window
    s = str(window).strip().lower()
    try:
        if s.endswith("d"):
            return timedelta(days=float(s[:-1]))
        if s.endswith("w"):
            return timedelta(weeks=float(s[:-1]))
        if s.endswith("m"):
            return timedelta(days=float(s[:-1]) * 30)
        if s.endswith("y"):
            return timedelta(days=float(s[:-1]) * 365)
        return timedelta(days=float(s))
    except Exception:  # noqa: BLE001
        return timedelta(days=7)


def _matches_topics(ev: dict, topics: list) -> bool:
    """M7: word-boundary title match + exact-set theme match — a bare
    substring search (the pre-fix behaviour) false-positives heavily (e.g. a
    topic token that happens to be a substring of an unrelated word)."""
    title = str(ev.get("title") or "").lower()
    themes = {str(t).strip().lower() for t in (ev.get("themes") or []) if str(t or "").strip()}
    for t in topics:
        tok = str(t or "").strip().lower()
        if not tok:
            continue
        if tok in themes:
            return True
        if re.search(rf"\b{re.escape(tok)}\b", title):
            return True
    return False


def _matches_tickers(ev: dict, tickers: list) -> bool:
    want = {str(t).upper() for t in tickers if str(t or "").strip()}
    have = {str(t).upper() for t in (ev.get("tickers") or [])}
    return bool(want & have)


def _date_ordinal(d: str | None) -> int:
    if not d:
        return 0
    try:
        return datetime.strptime(d[:10], "%Y-%m-%d").toordinal()
    except Exception:  # noqa: BLE001
        return 0


def _render_line(ev: dict) -> str:
    """M4: pack() is the API every consumer binds — a date+title-only line is
    contentless for sources whose titles are generic (earnings, macro_release
    before a source is joined). Render facts into the line text so the real
    numbers travel with it; cost is naturally accounted against the tier
    budget since this text IS what gets measured/charged below."""
    base = f"[{ev.get('date') or ''}] {ev.get('title') or ''}"
    facts = ev.get("facts") or []
    if facts:
        base += " — " + "; ".join(facts)
    return base


def pack(
    topics=None,
    tickers=None,
    horizons=("short", "medium"),
    token_budget=3000,
    as_of=None,
    window=None,
    window_forward=None,
    root=None,
) -> dict:
    """Deterministic context assembly (masterplan §2.4 exact public symbol).

    ``root`` is a test-injection point (tmp_path fixture roots — every function
    in this engine takes root, per house convention); it is appended last with
    a default so it does not disturb the documented positional/keyword shape of
    the other parameters, which match the masterplan signature exactly.
    ``window_forward`` is a B3 addition (opt-in only, see module docstring).

    Returns {"lines": [{"text","source_ref","site_url","source_url",
             "receipt"}], "narratives": [],
             "coverage": {"start","end","note"}, "budget_used": int}.

    Never raises: a malformed as_of degrades to the empty-with-reason contract
    (M11) rather than propagating a strptime ValueError out of the one API
    every consumer binds.
    """
    repo = _repo_root(root)
    events = _load_events(repo)

    all_dates = sorted({e.get("date") for e in events if e.get("date")})
    store_start = all_dates[0] if all_dates else None
    store_end = all_dates[-1] if all_dates else None

    candidates = events
    if topics:
        topics_list = list(topics)
        candidates = [e for e in candidates if _matches_topics(e, topics_list)]
    if tickers:
        tickers_list = list(tickers)
        candidates = [e for e in candidates if _matches_tickers(e, tickers_list)]

    date_note = None
    if as_of:
        as_of_str = str(as_of)[:10]
        try:
            as_of_date = datetime.strptime(as_of_str, "%Y-%m-%d").date()
        except Exception as exc:  # noqa: BLE001 — M11: never raise out of pack()
            return {
                "lines": [],
                "narratives": [],
                "coverage": {"start": store_start, "end": store_end,
                             "note": f"malformed as_of {as_of_str!r} ({exc}) — no query performed"},
                "budget_used": 0,
            }
        win_back = _parse_window(window) if window is not None else timedelta(days=7)
        lo = (as_of_date - win_back).isoformat()
        if window_forward is not None:
            hi = (as_of_date + _parse_window(window_forward)).isoformat()
        else:
            hi = as_of_str  # B3: hard right edge by default — never leak future events
        candidates = [e for e in candidates if e.get("date") and lo <= e["date"] <= hi]
        if not candidates:
            if store_start is None:
                date_note = "chronicle store is empty — no events have accrued yet"
            elif as_of_str < store_start:
                date_note = (f"chronicle coverage begins {store_start}; requested window "
                              f"({lo}..{hi}) predates it")
            else:
                date_note = (f"no events in window {lo}..{hi}; chronicle coverage is "
                              f"{store_start}..{store_end}")

    horizons_req = [h for h in _TIER_ORDER if h in (horizons or ())]
    if not horizons_req:
        horizons_req = list(_TIER_ORDER)

    total_weight = sum(_RESERVE_FRACTIONS[h] for h in horizons_req)
    tier_budget = {h: (token_budget * _RESERVE_FRACTIONS[h] / total_weight) for h in horizons_req}

    by_tier: dict[str, list[dict]] = {h: [] for h in horizons_req}
    for e in candidates:
        h = e.get("horizon_hint")
        if h in by_tier:
            by_tier[h].append(e)
    for h in by_tier:
        by_tier[h].sort(key=lambda e: (-(e.get("weight_hint") or 0), -_date_ordinal(e.get("date"))))

    lines: list[dict] = []
    leftover = 0.0
    evicted_total = 0
    for h in _TIER_ORDER:  # spill order: long -> medium -> short
        if h not in tier_budget:
            continue
        budget_h = tier_budget[h] + leftover
        used_h = 0.0
        emitted_h = 0
        for e in by_tier.get(h, []):
            text = _render_line(e)
            cost = len(text) / 4.0
            if used_h + cost > budget_h:
                break  # greedy-by-priority: stop this tier once it can't fit the next item
            lines.append({
                "text": text,
                "source_ref": e.get("source_ref"),
                "site_url": (e.get("links") or {}).get("site"),
                "source_url": (e.get("links") or {}).get("source"),
                "receipt": (e.get("links") or {}).get("receipt"),
            })
            used_h += cost
            emitted_h += 1
        # m5: count what didn't make it into `lines` for this tier so the
        # eviction is disclosed, not silently dropped (rollups already
        # disclose trimming — pack() must too).
        evicted_total += len(by_tier.get(h, [])) - emitted_h
        leftover = max(0.0, budget_h - used_h)

    budget_used = int(sum(len(l["text"]) / 4.0 for l in lines))

    coverage_note = date_note or (
        f"chronicle coverage {store_start}..{store_end}" if store_start else
        "chronicle store is empty — no events have accrued yet"
    )
    # Honest-null law: an empty result because a FILTER matched nothing must say
    # so. Reporting only the coverage window implies the store was the limit,
    # which reads as "we have no history here" when the truth is "your topic
    # matched no event". Name the filter and the store size instead.
    if not lines and not date_note and store_start:
        _filters = []
        if topics:
            _filters.append(f"topics={sorted(topics)}")
        if tickers:
            _filters.append(f"tickers={sorted(tickers)}")
        if _filters:
            coverage_note = (
                f"0 of {len(events)} stored event(s) matched {' + '.join(_filters)}; "
                f"chronicle coverage {store_start}..{store_end}. Note: themes are "
                f"populated only where the source carries them (the research-vault "
                f"catalog ships empty tags/tickers today), so topic matching falls "
                f"back to whole-word title matching for vault events."
            )
    if evicted_total:
        coverage_note += f"; {evicted_total} matching event(s) omitted to fit the {token_budget}-token budget"

    return {
        "lines": lines,
        "narratives": [],
        "coverage": {"start": store_start, "end": store_end, "note": coverage_note},
        "budget_used": budget_used,
    }
