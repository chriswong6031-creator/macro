"""engine.flow_observatory.workflow — W6 research workflow (frozen
``research/flow_observatory/W6_SPEC.md``): per-group history drawer, group compare,
prior episodes, Terminal deep links, and the watch-store integration decision.

Pure — every function here takes its inputs explicitly (a flow series, ledger rows,
the pre-computed causal series, a lens tag) and returns a plain dict/list; no I/O and
no re-fetching from disk. ``scripts/build_flow_velocity.py`` is the only caller that
touches disk (the flow panel, membership stores, the observations ledger) and wires
these functions' output into ``site/flowdata/desk.json``.

Replay honesty (spec §0.2): every number here comes from :func:`compute_full_series`,
which is a THIN wrapper over ``engine.flow_velocity.kinetics_series`` — the SAME
rolling/causal transform the live board itself uses, just read at every prior session
instead of only the last one (see that function's own docstring: a rolling/trailing
transform is already point-in-time at every one of its own output rows, so slicing its
history is a genuine causal replay, not a second computation that could quietly
diverge from what the desk actually publishes). Nothing here ever originates a signal;
this module only presents history/comparison/episode CONTEXT for a display that is
already display-only (masterplan §13 no-fused-composite boundary).
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from engine import flow_velocity as _fv
from engine.flow_observatory import history as fo_history

# ── frozen constants (spec §1-§4) ───────────────────────────────────────────────────
HISTORY_SESSIONS = 60
EPISODE_STORE_DEPTH = 250
EPISODE_TRAILING_EXCLUDE = 5
EPISODE_FORWARD_WINDOW = 10
EPISODE_COUNT = 3

# spec §1 REQUIRED pinned caption. `{ledger_start}` is filled with the entity's own
# first ledger session when the ledger holds at least one row for it; a THIN-LEDGER
# bootstrap (entity never yet observed) has no ledger_start to slot in — the frozen
# template presumes a start date exists, so that edge (spec §0.2 "thin-ledger bootstrap
# renders honest accruing states") gets an honest second sentence instead of a
# grammatically-broken fill (see :data:`NO_LEDGER_SENTENCE_EN`/`_ZH`). The first
# sentence — the part that is unconditionally true regardless of ledger depth — is
# NEVER altered.
REPLAY_CAPTION_LEAD_EN = "Replayed under today's method — not what was published historically."
REPLAY_CAPTION_LEAD_ZH = "按当前方法回放——非历史发布值。"
REPLAY_CAPTION_TAIL_EN = "Published record accrues from {ledger_start}."
REPLAY_CAPTION_TAIL_ZH = "发布记录自{ledger_start}起累积。"
NO_LEDGER_SENTENCE_EN = "No published record yet — this desk's ledger is still accruing."
NO_LEDGER_SENTENCE_ZH = "尚无发布记录——本看板的台账仍在累积中。"

# spec §3 pinned episode caption + outcome vocabulary (descriptive-only, no returns,
# no predictive claim — spec §5 test 7).
EPISODE_NOTE_EN = "similar setups, not forecasts"
EPISODE_NOTE_ZH = "相似情形，非预测"
_PRESSURE_WORDS = {"rose": ("rose", "回升"), "faded": ("faded", "回落"), "held": ("held", "持平")}
_ABS_WORDS = {"improved": ("improved", "改善"), "worsened": ("worsened", "恶化"), "held": ("held", "持平")}
_OUTCOME_EN = "over the next 10 sessions, pressure {pressure} and absolute flow {absf}"
_OUTCOME_ZH = "此后10个交易日，压力{pressure}，绝对流向{absf}"
# de-minimis band for the forward-outcome words — a move smaller than this (same units
# as the underlying series: sigma for pressure/rel, pct-rate for abs) reports "held"
# rather than manufacturing a direction out of noise. Not spec-pinned; a builder
# judgment call, recorded in the PR body (mirrors the existing 0.1pp abs neutral band
# `engine.flow_observatory.contract` already uses elsewhere in this program).
OUTCOME_EPS_REL = 0.1
OUTCOME_EPS_ABS = 0.1

# spec §2 cross-lens refusal (content pinned — "different denominators/universes" —
# exact wording is a builder choice, not a literal frozen string).
COMPARE_REFUSAL_REASON = "cross_lens"
COMPARE_REFUSAL_EN = ("Themes and official sectors can't be compared directly — "
                      "different denominators and universes.")
COMPARE_REFUSAL_ZH = "主题与官方行业口径不同（分母与样本范围不同），无法直接比较。"

# spec §4 Terminal link contract — reused EXACTLY from the existing per-name link
# (templates/flow_velocity.html.j2's `nameln` macro / templates/portfolio.js /
# templates/canada.html.j2 / templates/china.html.j2 all share this query-string
# shape: https://app.mastermind-x.com/terminal?sym=<TICKER>&from=macro).
TERMINAL_URL_TMPL = "https://app.mastermind-x.com/terminal?sym={ticker}&from=macro"

# spec §4 watch-store decision (see module docstring section below + PR body): the
# EXISTING client watch stores (templates/watchstore.js's Supabase-synced `WatchStore`,
# templates/watchlist.js's anonymous `WL`) are both a SINGLE account/device-level
# ticker list wired to live stock-quote fetches (window.SD) and consumed by the
# Watchlist product page, which renders every entry as a priced instrument row.
# Neither exposes a namespaced/typed key space — `symbolAdd`/`WL.add` accept an
# unvalidated string, but writing a non-ticker key ("flowgroup:theme:tech") into that
# SAME shared list would silently corrupt the Watchlist page's own display (a
# quote-less row for a symbol that will never resolve) rather than extend the store's
# key namespace — exactly the fork/corruption class spec §4 says to avoid ("if it does
# NOT [allow arbitrary keys], record the limitation and ship without watches rather
# than forking the store"). Recorded here rather than built.
WATCH_AVAILABLE = False
WATCH_LIMITATION_REASON = "watchstore_is_a_single_priced_ticker_list"
WATCH_LIMITATION_EN = (
    "Watching themes/sectors isn't available yet. The existing watch store "
    "(templates/watchstore.js / watchlist.js) is one account-level list of real stock "
    "tickers wired to live price quotes and shared with the Watchlist page — writing a "
    "non-ticker group key into it would corrupt that page rather than extend the "
    "store. Recorded as a dependency for the watchlist-sentinel owner, not built here.")
WATCH_LIMITATION_ZH = (
    "暂不支持关注主题/行业。现有关注列表（templates/watchstore.js / watchlist.js）是与"
    "实时报价绑定、并与关注列表页共用的单一账户级真实股票代码列表——写入非股票代码的"
    "分组键会污染该页面，而非扩展该存储。已记录为关注列表哨兵负责人的依赖项，本迭代不"
    "实现。")
ALERT_DEPENDENCY_NOTE = ("flow-state onset alerts belong to the watchlist-sentinel "
                          "owner; not built here.")

_BANNED_PREDICTIVE_WORDS = ("will", "target", "expect", "将", "目标", "预期")


# ── §1 replay history ───────────────────────────────────────────────────────────────
def compute_full_series(flow: pd.Series, cfg: dict, vin: float, vout: float) -> pd.DataFrame | None:
    """The full causal replay series for one group's flow — a thin pass-through to
    :func:`engine.flow_velocity.kinetics_series` (kept as its own function so callers
    that need it for BOTH :func:`history_panel` and :func:`select_episodes` compute it
    exactly once)."""
    return _fv.kinetics_series(flow, cfg, vin=vin, vout=vout)


def _direction(state_en: str | None) -> str | None:
    """"above norm, ..." -> up (up-tint band); "below norm, ..." -> down; neutral/no-data/
    None -> no band (spec §1: "background tint bands ... where the replayed state is
    non-neutral")."""
    if not state_en:
        return None
    if state_en.startswith("above norm"):
        return "up"
    if state_en.startswith("below norm"):
        return "down"
    return None


def _contiguous_runs(flags: list[Any]) -> list[tuple[int, int, Any]]:
    """``[(start, end, value)]`` inclusive-index runs of consecutive equal, truthy
    ``flags`` entries — the shared primitive behind both state bands and the
    published-record segments below (a group's ledger coverage need not be one single
    trailing run if a session was ever missing from the ledger, so this is written
    generically rather than assuming contiguity)."""
    runs: list[tuple[int, int, Any]] = []
    i, n = 0, len(flags)
    while i < n:
        v = flags[i]
        if not v:
            i += 1
            continue
        j = i
        while j + 1 < n and flags[j + 1] == v:
            j += 1
        runs.append((i, j, v))
        i = j + 1
    return runs


def _pct_geometry(start: int, end: int, n: int) -> dict[str, float]:
    """Pure index -> percentage-of-width geometry for a [start, end] inclusive run
    over an axis of ``n`` sessions — DATA-dependent positioning only; the governed
    stylesheet (templates/flow_velocity.html.j2's CSS, TP-0) owns every color/alpha/
    hatch material decision, never this module."""
    if n <= 0:
        return {"left_pct": 0.0, "width_pct": 0.0}
    left = 100.0 * start / n
    width = 100.0 * (end - start + 1) / n
    return {"left_pct": round(left, 2), "width_pct": round(width, 2)}


def _state_bands(state_series: list[str | None]) -> list[dict[str, Any]]:
    """Contiguous ``{start, end, direction, left_pct, width_pct}`` runs (inclusive
    indices into the SAME `sessions` list, plus pure geometry for the tint overlay) of
    non-neutral states — spec §1 "state bands ... where the replayed state is
    non-neutral"."""
    n = len(state_series)
    dirs = [_direction(s) for s in state_series]
    return [{"start": s, "end": e, "direction": d, **_pct_geometry(s, e, n)}
           for s, e, d in _contiguous_runs(dirs)]


def _published_segments(published_idx: list[int], n: int) -> list[dict[str, Any]]:
    """Contiguous ``{start, end, left_pct, width_pct}`` runs of ledger-covered
    sessions — spec §1 "sessions covered by real ledger rows get a thin baseline tick
    row" (never assumed to be one single trailing run — a session absent from the
    ledger for any reason must not stretch the tick across a gap it doesn't cover)."""
    flags = [False] * n
    for i in published_idx:
        if 0 <= i < n:
            flags[i] = True
    return [{"start": s, "end": e, **_pct_geometry(s, e, n)}
           for s, e, _ in _contiguous_runs(flags)]


def _round(v: Any, nd: int) -> float | None:
    return round(float(v), nd) if v is not None and pd.notna(v) else None


def history_panel(full: pd.DataFrame | None, ledger_rows: list[dict[str, Any]] | None,
                  entity_kind: str, entity_id: str,
                  n: int = HISTORY_SESSIONS) -> dict[str, Any] | None:
    """The spec §1 history-drawer payload for one group: the tail-``n`` session axis,
    the abs-rate/relative-pressure series (+ server-side spark polylines, the existing
    ``_spark`` idiom — no new chart machinery), state bands, ledger revision markers,
    the published-vs-replay split, and the pinned replay caption.

    ``None`` when the group's flow history is too short to compute at all (spec §0.2:
    "nothing fabricated, nothing blank-broken" — the caller renders an honest
    accruing/insufficient state instead of this panel).
    """
    if full is None or full.empty:
        return None
    tail = full.tail(n)
    sessions = [d.strftime("%Y-%m-%d") for d in tail.index]  # source-effective sessions
    abs_series = [_round(v, 1) for v in tail["abs_rate"]]
    rel_series = [_round(v, 2) for v in tail["vel"]]
    state_series = [(en if pd.notna(v) else None)
                    for en, v in zip(tail["state_en"], tail["vel"])]

    ledger_rows = ledger_rows or []
    erows = fo_history.entity_rows(ledger_rows, entity_kind, entity_id)
    by_session = {r["effective_session"]: r for r in erows}
    ledger_start = min(by_session) if by_session else None

    revision_markers = [i for i, s in enumerate(sessions)
                        if int((by_session.get(s) or {}).get("revision_id") or 0) > 0]
    published_idx = [i for i, s in enumerate(sessions) if s in by_session]

    if ledger_start:
        caption_en = f"{REPLAY_CAPTION_LEAD_EN} {REPLAY_CAPTION_TAIL_EN.format(ledger_start=ledger_start)}"
        caption_zh = f"{REPLAY_CAPTION_LEAD_ZH}{REPLAY_CAPTION_TAIL_ZH.format(ledger_start=ledger_start)}"
    else:
        caption_en = f"{REPLAY_CAPTION_LEAD_EN} {NO_LEDGER_SENTENCE_EN}"
        caption_zh = f"{REPLAY_CAPTION_LEAD_ZH}{NO_LEDGER_SENTENCE_ZH}"

    n_sess = len(sessions)
    return {
        "entity_kind": entity_kind, "entity_id": entity_id,
        "sessions": sessions, "abs_series": abs_series, "rel_series": rel_series,
        "state_series": state_series,
        "spark_abs": _fv.spark(abs_series), "spark_rel": _fv.spark(rel_series),
        "bands": _state_bands(state_series),
        "revision_markers": revision_markers,
        "revision_marker_pct": [round(100.0 * (i + 0.5) / n_sess, 2) for i in revision_markers] if n_sess else [],
        "published_idx": published_idx,
        "published_segments": _published_segments(published_idx, n_sess),
        "ledger_start": ledger_start,
        "caption_en": caption_en, "caption_zh": caption_zh,
    }


def align_histories(a: dict[str, Any], b: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """§2 compare: trim two :func:`history_panel` payloads to their COMMON session
    axis (order-preserving) so a side-by-side render never silently mis-aligns two
    series of slightly different depth."""
    common = set(a["sessions"]) & set(b["sessions"])

    def _trim(h: dict[str, Any]) -> dict[str, Any]:
        keep = [i for i, s in enumerate(h["sessions"]) if s in common]
        keep_set = set(keep)
        n_new = len(keep)
        new_rev = [keep.index(i) for i in h["revision_markers"] if i in keep_set]
        new_pub = [keep.index(i) for i in h["published_idx"] if i in keep_set]
        return {
            **h,
            "sessions": [h["sessions"][i] for i in keep],
            "abs_series": [h["abs_series"][i] for i in keep],
            "rel_series": [h["rel_series"][i] for i in keep],
            "state_series": [h["state_series"][i] for i in keep],
            "revision_markers": new_rev,
            "revision_marker_pct": [round(100.0 * (i + 0.5) / n_new, 2) for i in new_rev] if n_new else [],
            "published_idx": new_pub,
            "published_segments": _published_segments(new_pub, n_new),
            "bands": _state_bands([h["state_series"][i] for i in keep]),
        }
    return _trim(a), _trim(b)


# ── §2 compare ───────────────────────────────────────────────────────────────────────
def compare_groups(a_kind: str, a_id: str, a_row: dict[str, Any],
                   b_kind: str, b_id: str, b_row: dict[str, Any]) -> dict[str, Any]:
    """The §2 compare stat table, or the pinned cross-lens refusal. Same-lens only
    (theme<->theme, sector<->sector) — ``a_row``/``b_row`` are the group's own board
    row (already carries abs/rel/quadrant/coverage/concentration; no re-computation)."""
    if a_kind != b_kind:
        return {"available": False, "reason": COMPARE_REFUSAL_REASON,
               "reason_en": COMPARE_REFUSAL_EN, "reason_zh": COMPARE_REFUSAL_ZH}

    def _stat(kind: str, gid: str, row: dict[str, Any]) -> dict[str, Any]:
        conc = row.get("concentration") or {}
        top1 = conc.get("top1") or {}
        return {
            "kind": kind, "id": gid, "name": row.get("name"), "name_zh": row.get("name_zh"),
            "abs_value": (row.get("abs") or {}).get("value"),
            "rel_value": row.get("vel"), "quadrant": row.get("quadrant"),
            "coverage_pct": row.get("coverage_pct"),
            "top_contributor_ticker": top1.get("ticker"), "top_contributor_name": top1.get("name"),
        }
    return {"available": True, "a": _stat(a_kind, a_id, a_row), "b": _stat(b_kind, b_id, b_row)}


# ── §3 prior episodes ────────────────────────────────────────────────────────────────
def select_episodes(full: pd.DataFrame | None, *, k: int = EPISODE_COUNT,
                    trailing_exclude: int = EPISODE_TRAILING_EXCLUDE,
                    forward_window: int = EPISODE_FORWARD_WINDOW,
                    store_depth: int = EPISODE_STORE_DEPTH) -> list[dict[str, Any]]:
    """The spec §3 "3 nearest historical sessions" for the group's CURRENT (last) row —
    L2 distance on the pair (rel_pressure, abs_rate) z-scored over the extended window
    (store depth, max ``store_depth`` sessions), excluding the trailing
    ``trailing_exclude`` sessions (no self-match) AND any candidate whose own
    ``forward_window``-session forward summary would cross the current session (no
    future leakage — spec §3 test).

    Descriptive-only summaries (spec §5 test 7: no %-return strings, no predictive
    words) — never a return figure, never "will"/"target"/"expect".
    """
    if full is None or len(full) < (trailing_exclude + forward_window + 5):
        return []
    pool = full.tail(store_depth)
    n = len(pool)
    current_idx = n - 1
    rel = pool["vel"].to_numpy(dtype=float)
    absr = pool["abs_rate"].to_numpy(dtype=float)

    def _z(arr):
        mask = ~pd.isna(arr)
        if mask.sum() < 5:
            return None
        mu, sd = arr[mask].mean(), arr[mask].std(ddof=0)
        if not sd or pd.isna(sd):
            return None
        return (arr - mu) / sd

    z_rel, z_abs = _z(rel), _z(absr)
    if z_rel is None or z_abs is None or pd.isna(z_rel[current_idx]) or pd.isna(z_abs[current_idx]):
        return []
    cur = (z_rel[current_idx], z_abs[current_idx])

    candidates = []
    for c in range(n):
        if c >= current_idx - trailing_exclude:          # trailing-5 self-match exclusion
            continue
        if (c + forward_window) >= current_idx:           # no-future-leakage
            continue
        if pd.isna(z_rel[c]) or pd.isna(z_abs[c]) or pd.isna(rel[c + forward_window]) \
                or pd.isna(absr[c + forward_window]):
            continue
        dist = ((z_rel[c] - cur[0]) ** 2 + (z_abs[c] - cur[1]) ** 2) ** 0.5
        candidates.append((dist, c))
    candidates.sort(key=lambda t: (t[0], -t[1]))

    out = []
    for dist, c in candidates[:k]:
        rel_delta = rel[c + forward_window] - rel[c]
        abs_delta = absr[c + forward_window] - absr[c]
        p_word = "rose" if rel_delta > OUTCOME_EPS_REL else ("faded" if rel_delta < -OUTCOME_EPS_REL else "held")
        a_word = "improved" if abs_delta > OUTCOME_EPS_ABS else ("worsened" if abs_delta < -OUTCOME_EPS_ABS else "held")
        p_en, p_zh = _PRESSURE_WORDS[p_word]
        a_en, a_zh = _ABS_WORDS[a_word]
        out.append({
            "session": pool.index[c].strftime("%Y-%m-%d"),
            "rel_value": _round(rel[c], 2), "abs_value": _round(absr[c], 1),
            "distance": round(float(dist), 3),
            "outcome_en": _OUTCOME_EN.format(pressure=p_en, absf=a_en),
            "outcome_zh": _OUTCOME_ZH.format(pressure=p_zh, absf=a_zh),
        })
    return out


def has_banned_predictive_language(text: str) -> bool:
    """Spec §5 test 7 guard: no %-return strings, no predictive words. Exposed so the
    test suite (and, if useful, a future runtime assertion) can check ANY
    episode-summary text against the SAME banned-vocabulary list, once."""
    if "%" in text:
        return True
    low = text.lower()
    return any(w.lower() in low or w in text for w in _BANNED_PREDICTIVE_WORDS)


# ── §4 Terminal links ────────────────────────────────────────────────────────────────
def terminal_link(ticker: str | None, known_tickers: "set[str] | None" = None) -> str | None:
    """The EXISTING ticker-identity contract
    (``https://app.mastermind-x.com/terminal?sym=<TICKER>&from=macro`` — verified
    against ``templates/flow_velocity.html.j2``'s own ``nameln`` macro,
    ``templates/portfolio.js``, ``templates/canada.html.j2``, ``templates/china.html.j2``
    — never a new URL scheme). ``None`` (unlinked, no dead link) when ``ticker`` is
    falsy or absent from ``known_tickers`` (the desk's own covered/scored universe —
    the closest available proxy for "has a Terminal page" this desk can check, since
    Terminal itself is a separate live app with no static per-ticker page inventory
    here)."""
    if not ticker:
        return None
    if known_tickers is not None and ticker not in known_tickers:
        return None
    return TERMINAL_URL_TMPL.format(ticker=ticker)
