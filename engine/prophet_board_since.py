"""Current continuous published-board membership start (`board_since` / `added_date`).

Display-tier only. Reads existing published board fossils (never a new ledger,
identity system, or authority) and stamps an in-memory `added_date` field onto
candidate row dicts. Truth-under-uncertainty: unknown/unprovable membership age
is always None, never a fallback to signal.asof / board as_of / build date /
wall clock / candidate_episode.opened_at.

LEFT-CENSORING (the defect a prior draft shipped, #6687): if the walk-back
reaches the OLDEST observation in a market's recorded history and the candidate
is present in it, that is NOT proof the streak started there — the history may
simply not reach far enough back. `current_continuous_membership_start` returns
None in that case unless the caller asserts `starts_at_inception=True` for a
market whose recorded history is independently known to start at the board's
actual launch. Every call site in this module passes `starts_at_inception=False`
today; see the per-market adapter docstrings for the evidence.

MEMBERSHIP vs DISPLAY (adjudicated 2026-09-01, REQUEST_REPAIR on the same
carrier): a name's presence in the OBSERVATION series each adapter builds —
what sustains or resets tenure — is a strictly wider set than the pv_card
(chip) surface. MEMBERSHIP = presence in the published board fossil under any
LIVE, name-visible lane/group/definition — every lane whose names are
actually rendered somewhere on the public board page (card, table row, or
link grid), excluding only research/shadow cohorts whose names are never
shown. DISPLAY = the narrower pv_card lane(s) that actually receive the
`added_date` chip. Each adapter section below now names both sets explicitly
(`*_MEMBERSHIP_*` feeds the observation history + today's current-ids fold;
`*_DISPLAY_*` / `*_CURRENT_LANES` still gates which rows get stamped) so a
name moving between two visible lanes (e.g. US buy<->watch, HK/CA
entry_open<->watch) is represented as continued presence in the SAME
observation set and does not reset the streak — only a published observation
that omits the name outright resets it (`current_continuous_membership_start`
docstring above).
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import AbstractSet, Any, Iterable, Mapping, Sequence

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REPO_ROOT = Path(__file__).resolve().parents[1]

Observation = tuple[str, frozenset[str]]
MembershipStart = tuple[str, str]  # (iso_date, basis)


# ─────────────────────────── ISO helpers (salvaged AS-IS) ──────────────────────────

def is_iso_date(val: Any) -> bool:
    return isinstance(val, str) and bool(_ISO.fullmatch(val))


def _iso_from_value(val: Any) -> str | None:
    if val is None:
        return None
    if is_iso_date(val):
        return val
    text = str(val).strip()
    if not text or text in ("nan", "NaT", "None"):
        return None
    head = text[:10]
    return head if is_iso_date(head) else None


def _clean_id(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    if not s or s in ("nan", "None", "NaT"):
        return None
    return s


# ───────────────────── collapse / identities (salvaged AS-IS) ──────────────────────

def collapse_published_observations(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
) -> list[Observation]:
    """Last snapshot per ISO date wins; dates sort ascending; missing dates stay omitted."""
    by_date: dict[str, frozenset[str]] = {}
    for item in observations or ():
        if not item or len(item) != 2:
            continue
        date, ids = item
        iso = _iso_from_value(date)
        if not iso:
            continue
        cleaned = {c for c in (_clean_id(x) for x in (ids or ())) if c}
        by_date[iso] = frozenset(cleaned)
    return [(d, by_date[d]) for d in sorted(by_date)]


def identities_in_lanes(
    artifact: Mapping[str, Any] | None,
    lanes: Sequence[str],
    identity_key: str = "ticker",
) -> set[str]:
    ids: set[str] = set()
    if not artifact:
        return ids
    for lane in lanes:
        for row in artifact.get(lane) or []:
            if not isinstance(row, dict):
                continue
            ident = _clean_id(row.get(identity_key))
            if ident:
                ids.add(ident)
    return ids


# ───────────────────────────── core resolver (REWRITTEN) ───────────────────────────

def with_current_board(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    current_as_of: Any,
    current_ids: Iterable[Any] | None,
) -> list[Observation]:
    """Fold today's live board onto the historical fossil series.

    Appends a (current_as_of, current_ids) observation ONLY when `current_as_of`
    is a valid ISO date strictly greater than the newest fossil date already in
    `observations`. If `current_as_of` is missing/invalid, or is at-or-before the
    newest fossil date, `observations` is returned unchanged (collapsed) — the
    fossil is canonical. This is what makes a same-session rebuild (same as_of,
    same or a later call) a no-op rather than an overwrite, and what stops a
    stale as_of from clobbering a newer fossil someone else already wrote.
    """
    obs = collapse_published_observations(observations)
    iso = _iso_from_value(current_as_of)
    if not iso:
        return obs
    if obs and iso <= obs[-1][0]:
        return obs
    cleaned_ids = {c for c in (_clean_id(x) for x in (current_ids or ())) if c}
    return collapse_published_observations(list(observations or ()) + [(iso, cleaned_ids)])


def current_continuous_membership_start(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    identity: Any,
    starts_at_inception: bool = False,
) -> MembershipStart | None:
    """Earliest date of the current uninterrupted published-board presence streak.

    Returns `(iso_date, basis)` or None. `basis` is:
      - "absence_proof": the walk-back found a published observation that omits
        the identity, so the streak provably began the observation right after it.
      - "inception_proof": the walk-back reached the OLDEST recorded observation
        with the identity still present, and the caller has asserted (via
        `starts_at_inception=True`) that this market's history starts at the
        board's actual launch — so "present at the oldest observation" IS proof
        the streak began there.

    Left-censoring guard: when the walk-back reaches the oldest observation with
    the identity present and `starts_at_inception` is False (the default), the
    result is None — history that does not reach the board's true origin cannot
    prove a start date, so we refuse to guess one.

    A published observation that OMITS the identity resets the streak. An
    observation simply ABSENT from `observations` (a missing whole-board publish,
    a weekend, a holiday) does not — the walk only looks at observations that
    actually exist.
    """
    ident = _clean_id(identity)
    if not ident:
        return None
    obs = collapse_published_observations(observations)
    if not obs:
        return None
    last_date, last_ids = obs[-1]
    if ident not in last_ids:
        return None
    if len(obs) == 1:
        return (last_date, "inception_proof") if starts_at_inception else None
    streak_start = last_date
    idx = len(obs) - 2
    hit_absence = False
    while idx >= 0:
        date, ids = obs[idx]
        if ident in ids:
            streak_start = date
            idx -= 1
            continue
        hit_absence = True
        break
    if hit_absence:
        return (streak_start, "absence_proof")
    # Walked back through every recorded observation without ever finding an
    # absence — present at the oldest one. Left-censored unless the caller has
    # proven this market's history reaches the board's actual inception.
    return (streak_start, "inception_proof") if starts_at_inception else None


# ─────────────────────────────── US adapter ─────────────────────────────────
# CARD/DISPLAY lane trace (2026-09-01): templates/_us_board_cards.html.j2 is
# included from exactly two places — dashboard.html.j2:16649 with
# items=_render_list.items (built solely from `_board = _su.buy`, both the
# legacy lane-partition path and the priority stage-partition path), and
# scripts/build_site.py's `_write_us_payload` (items from
# `_us_board_group_items(locked_rows, ...)` where `locked_rows` is documented
# as "the withheld remainder of `buy`"). So the only US pv_card (chip) lane is
# `buy` — this is the DISPLAY surface, unchanged by the membership fix below.
US_DISPLAY_LANES = US_VISIBLE_LANES = ("buy",)

# MEMBERSHIP lane trace (2026-09-01, REQUEST_REPAIR — membership vs display are
# two different sets; a display-only walk under-counted the market's own
# published-board surfaces and reset tenure on buy<->watch moves). Evidence
# that watch/leaders/laggards/ran each reach the reader on dashboard.html.j2,
# even though none of them render through pv_card:
#   - `leaders`: templates/_us_leader_rows.html.j2 — a real <tr> table (rank,
#     ticker, name, sector, alpha…) rendered both in the free shell and via
#     scripts/build_site.py._render_us_panel_payload's "leaders_html" for the
#     locked remainder. Ticker + company name are always printed.
#   - `ran`: templates/_us_ran_rows.html.j2 (.pbr-l "recently fired" strip) —
#     same shape, ticker + name always printed, plus a "leaders_html"-style
#     sibling render for the locked remainder ("ran_html").
#   - `watch` + `laggards`: dashboard.html.j2:16029-16059 builds the `#plv-names`
#     JSON island — "the near-decision population the pack arms from — buy u
#     watch u leaders u laggards" — precisely so the live #prophet-live strip
#     (build_prophet_live_pack.py / live/prophet_live.json) can print a real
#     company name, not a bare ticker, the moment one of THOSE names crosses a
#     level intraday. build_site.py:5557-5573 independently confirms the same
#     union for the gated-tier payload ("plv_names"), noting watch/laggards are
#     "the two populations that have no panel here at all" (no dedicated table)
#     — i.e. they reach the reader ONLY through this strip, never through a
#     locked panel, but they DO reach the reader. This is the frozen-spec test
#     ("names actually rendered somewhere on the public board page") — card or
#     not.
#   - `donor` stays EXCLUDED: it never appears in the `#plv-names` union, the
#     leaders/ran partials, or any other US template (grep: zero occurrences of
#     doc.get('donor') / su.get('donor') / .donor outside research/telemetry
#     code) — never rendered as a name to a reader, so it is research-only.
US_MEMBERSHIP_LANES = ("buy", "watch", "leaders", "laggards", "ran")

# starts_at_inception=False — PROVEN false: data/us_board_ledger/retro_grades.parquet
# carries as_of back to 2026-06-15 (measured), before snapshots.jsonl's own fossil
# start of 2026-06-30 — board activity predates the ledger this adapter reads.
US_STARTS_AT_INCEPTION = False

_us_obs_cache_lock = threading.Lock()
_us_obs_cache: dict[tuple[str, float, int], list[Observation]] = {}


def observations_from_us_snapshots_jsonl(
    path: Path, visible_lanes: Sequence[str] = US_MEMBERSHIP_LANES,
) -> list[Observation]:
    """Stream `data/us_board_ledger/snapshots.jsonl` line-by-line (never a whole-file
    read — the file is ~33MB). Memoized per-process keyed by (path, mtime, size) so a
    second call in the same build (the two _attach_board_display_chips call sites)
    does not re-parse the file."""
    try:
        st = path.stat()
    except OSError:
        return []
    key = (str(path), st.st_mtime, st.st_size)
    with _us_obs_cache_lock:
        cached = _us_obs_cache.get(key)
    if cached is not None:
        return cached
    by_date: dict[str, set[str]] = {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    snap = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not isinstance(snap, dict):
                    continue
                iso = _iso_from_value(snap.get("as_of"))
                if not iso:
                    continue
                ids: set[str] = set()
                for lane in visible_lanes:
                    for row in snap.get(lane) or []:
                        if isinstance(row, dict):
                            tk = _clean_id(row.get("ticker"))
                            if tk:
                                ids.add(tk)
                by_date.setdefault(iso, set()).update(ids)
    except OSError:
        return []
    result = [(d, frozenset(by_date[d])) for d in sorted(by_date)]
    with _us_obs_cache_lock:
        _us_obs_cache[key] = result
    return result


def stamp_us_board_since(
    artifact: dict[str, Any] | None, *, data_dir: Path | None = None,
) -> dict[str, Any] | None:
    if not artifact:
        return artifact
    data = Path(data_dir) if data_dir is not None else _REPO_ROOT / "data"
    hist = observations_from_us_snapshots_jsonl(data / "us_board_ledger" / "snapshots.jsonl")
    # MEMBERSHIP (sustains tenure) uses the wider visible-lane set; DISPLAY (which
    # rows get a chip, below) stays the narrower pv_card-only lane.
    current_ids = identities_in_lanes(artifact, US_MEMBERSHIP_LANES)
    obs = with_current_board(hist, artifact.get("as_of"), current_ids)
    for lane in US_DISPLAY_LANES:
        rows = artifact.get(lane)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ident = _clean_id(row.get("ticker"))
            if not ident:
                row["added_date"] = None
                continue
            start = current_continuous_membership_start(
                obs, ident, starts_at_inception=US_STARTS_AT_INCEPTION)
            row["added_date"] = start[0] if start else None
    return artifact


def stamp_us_board_since_fail_open(
    artifact: dict[str, Any] | None, *, data_dir: Path | None = None, log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        return stamp_us_board_since(artifact, data_dir=data_dir)
    except Exception as exc:  # noqa: BLE001 — additive display field, never fatal
        if log is not None:
            log.warning("us board_since stamp failed (%s)", exc)
        return artifact


# ─────────────────────────────── CN adapter ─────────────────────────────────
# DISPLAY identity trace (2026-09-01): templates/china.html.j2 has exactly two
# pv_card call sites. ENTRY/featured (~L3605) iterates `_mrg`, built from
# `_entry_rows` (setups.buy filtered to stage=='ENTRY', OR the whole of
# setups.buy when neither ENTRY nor RAN_LATE rows exist — the pre-W1
# backward-compat fallback) UNION `setups.more_actionable`. RAN/LATE (~L3709)
# iterates `_ran_late_rows` (setups.buy filtered to stage=='RAN_LATE').
# `setups.late_or_unfillable` is counted in the facet-bar chip but never
# iterated for a card — excluded. This is the DISPLAY (chip) surface only,
# unchanged by the membership fix below.
CN_CURRENT_LANES = ("buy", "more_actionable")

# starts_at_inception=False — PROVEN false: board_definition=='legacy' rows
# (1,082 of them, null lane, pre-v2 era) precede the first non-legacy date and
# are non-authoritative for presence/absence, so the usable (non-legacy)
# history itself starts mid-stream, not at any provable board inception.
CN_STARTS_AT_INCEPTION = False


def observations_from_cn_frame(
    df: Any, watch_definitions: AbstractSet[str] | None = None,
) -> list[Observation]:
    """Adapter over data/china_standout_track/board.parquet. Excludes rows whose
    `board_definition` is a watch/shadow cohort (never sustains tenure) AND rows
    whose `board_definition` == 'legacy' (1,082 rows, null lane, pre-v2 era —
    non-authoritative for presence AND absence; observations begin at the first
    non-legacy date).

    MEMBERSHIP TRACE (2026-09-01, REQUEST_REPAIR): `board_definition` is the
    ONLY filter here, and that is deliberate, not an oversight. Traced
    scripts/build_china_library.py (append_board call sites ~L4280-4315) and
    engine/china_board_rank.py._partition: only `wide["buy"]` — which IS
    `_board_lanes["featured"]`, i.e. the SAME rows `china.html.j2` cards as the
    entry/featured shelf — plus the explicit reversal_watch / v2-shadow /
    v3-shadow / continuation_watch cohorts (all in WATCH_DEFINITIONS, already
    excluded above) ever reach `china_standout_track.append_board`. The other
    three lanes `_partition` computes (`more_actionable`, `late_or_unfillable`,
    `forming`) are NEVER appended to board.parquet — measured on the live
    fossil: its `lane` column holds exactly three values (`featured`,
    `reversal_watch`, null/`legacy`), never `more_actionable` or
    `late_or_unfillable`. So "every live-definition row in the fossil" and
    "the featured/carded shelf" are the SAME set today, by construction of the
    upstream persistence layer (out of this module's scope to change) — a
    `late_or_unfillable` demotion is a display partition of a row that was
    simply never fossil-tracked to begin with, so it structurally cannot
    "remove" a membership the fossil never granted it. `cn_current_visible_ids`
    below reconciles the CURRENT-day read to this same fossil truth."""
    if df is None or getattr(df, "empty", False):
        return []
    cols = set(getattr(df, "columns", ()))
    if "date" not in cols or "ticker" not in cols:
        return []
    watch = frozenset(str(x) for x in (watch_definitions or ()))
    live = df
    if "board_definition" in cols:
        bd = df["board_definition"].astype(str)
        live = df[~bd.isin(watch) & (bd != "legacy")]
    by_date: dict[str, set[str]] = {}
    for date_val, grp in live.groupby("date", sort=False):
        iso = _iso_from_value(date_val)
        if not iso:
            continue
        tickers = {c for c in (_clean_id(t) for t in grp["ticker"].tolist()) if c}
        by_date.setdefault(iso, set()).update(tickers)
    return [(d, frozenset(by_date[d])) for d in sorted(by_date)]


def cn_current_visible_ids(artifact: Mapping[str, Any] | None) -> set[str]:
    """Ticker set TONIGHT's build writes (or would write) to board.parquet under
    its live board_definition — i.e. all of `artifact["buy"]` (the "featured"
    lane; see the fossil trace above), regardless of the `stage` a card
    happens to display it under (ENTRY vs RAN_LATE is a template-only
    partition of the SAME lane and must never gate membership).

    NOT the same set as the template's pv_card partition: `more_actionable`
    cards render today (china.html.j2 `_more_lane`) but are never persisted to
    the fossil (see the trace above), so a more_actionable-only ticker
    correctly gets no membership contribution here — `added_date` resolves to
    None for it, which is the honest "unprovable" answer, not a bug. This
    function is therefore DELIBERATELY NOT a superset of every card-rendered
    id; it is the fossil-write set, which the ADJUDICATED RULE (top of this
    module) defines membership against."""
    if not artifact:
        return set()
    buy = artifact.get("buy") or []
    return {tk for r in buy if isinstance(r, dict) and (tk := _clean_id(r.get("ticker")))}


def _cn_card_rendered_ids_for_test(artifact: Mapping[str, Any] | None) -> set[str]:
    """TEST-ONLY mirror of china.html.j2's pv_card partition (entry_rows u
    ran_late_rows u more_lane) — kept out of the adapter's own public surface
    (cn_current_visible_ids is fossil-truth, not display-truth; see its
    docstring) but retained so tests can assert the DISPLAY set independently
    without re-deriving the template partition inline."""
    if not artifact:
        return set()
    buy = artifact.get("buy") or []
    buy = [r for r in buy if isinstance(r, dict)]
    entry_rows = [r for r in buy if r.get("stage") == "ENTRY"]
    ran_late_rows = [r for r in buy if r.get("stage") == "RAN_LATE"]
    if not entry_rows and not ran_late_rows and buy:
        entry_rows = buy  # pre-W1 backward-compat: whole board is the entry shelf
    more_lane = [r for r in (artifact.get("more_actionable") or []) if isinstance(r, dict)]
    ids: set[str] = set()
    for row in entry_rows + ran_late_rows + more_lane:
        tk = _clean_id(row.get("ticker"))
        if tk:
            ids.add(tk)
    return ids


def stamp_cn_board_since(
    artifact: dict[str, Any] | None, *,
    data_dir: Path | None = None,
    watch_definitions: AbstractSet[str] | None = None,
) -> dict[str, Any] | None:
    if not artifact:
        return artifact
    data = Path(data_dir) if data_dir is not None else _REPO_ROOT / "data"
    path = data / "china_standout_track" / "board.parquet"
    hist: list[Observation] = []
    if path.exists():
        import pandas as pd  # noqa: PLC0415 — optional adapter dep
        hist = observations_from_cn_frame(pd.read_parquet(path), watch_definitions)
    current_ids = cn_current_visible_ids(artifact)
    obs = with_current_board(hist, artifact.get("as_of"), current_ids)
    for lane in CN_CURRENT_LANES:
        rows = artifact.get(lane)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ident = _clean_id(row.get("ticker"))
            if not ident:
                row["added_date"] = None
                continue
            start = current_continuous_membership_start(
                obs, ident, starts_at_inception=CN_STARTS_AT_INCEPTION)
            row["added_date"] = start[0] if start else None
    return artifact


def stamp_cn_board_since_fail_open(
    artifact: dict[str, Any] | None, *,
    data_dir: Path | None = None,
    watch_definitions: AbstractSet[str] | None = None,
    log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        return stamp_cn_board_since(artifact, data_dir=data_dir, watch_definitions=watch_definitions)
    except Exception as exc:  # noqa: BLE001 — additive display field, never fatal
        if log is not None:
            log.warning("cn board_since stamp failed (%s)", exc)
        return artifact


# ─────────────────────────────── HK / CA adapter ─────────────────────────────
# DISPLAY-group trace (2026-09-01): hk.html.j2's pv_card loop
# (`_render_list.items if _hsg.any else _hkb`) is built entirely from
# `_hkb = setups.buy` — `setups.watch` is rendered separately as a plain
# `<a>` anchor grid ("watch-strip"), never through pv_card (grep: zero
# `pv_card(` near that block). canada.html.j2 is the same shape: pv_card loop
# is `for s in setups.buy`; `setups.watch` is its own anchor-only watch-strip.
# So the only CARDED (chip) group is the one that ends up inside `setups.buy`,
# which corresponds to the board_ledger parquet's `entry_open` / `setting_up`
# groups. HK_CA_DISPLAY_LANES / HK_CA_CURRENT_LANES stay `("buy",)` — the chip
# still only ever shows on a carded row, unchanged by the membership fix below.
HK_CA_DISPLAY_LANES = HK_CA_CURRENT_LANES = ("buy",)

# MEMBERSHIP-group trace (2026-09-01, REQUEST_REPAIR): `watch` renders as a
# visible anchor grid of names ("watch-strip") on BOTH hk.html.j2 and
# canada.html.j2 — visible names sustain tenure per the ADJUDICATED RULE
# (top of this module) even when they never earn a pv_card. And unlike CN's
# more_actionable/late_or_unfillable (never fossil-persisted, see the CN
# adapter above), HK/CA's `watch` group genuinely IS written to the fossil:
# scripts/build_hk_library.py._board_ledger_calls(buys, watch, ...) builds
# `calls = buys + watch` (its own docstring: "buy + watch, and nothing
# else... leaders / ran / vetoed" are the ones deliberately excluded), fed to
# `engine.board_ledger.append_board`. Measured on the live fossil: `group`
# actually holds `watch` rows today (HK: 321, CA: 248), alongside
# `entry_open` / `setting_up`. So including `watch` in the membership read is
# not merely visible-but-unrecorded (the earlier US-donor / CN-more_actionable
# case) — it is visible AND already fossil-tracked; the prior exclusion here
# was the display/membership conflation the mission packet exists to correct.
HK_CA_VISIBLE_GROUPS = frozenset({"entry_open", "setting_up", "watch"})
# `identities_in_lanes(artifact, HK_CA_MEMBERSHIP_LANES)` reads the CURRENT
# (today's) board for the same reason — the artifact carries `watch` as its
# own top-level key (confirmed: hk_standouts.json / canada_standouts.json both
# ship a `watch` list alongside `buy`), so folding it into today's observation
# keeps the live read consistent with the parquet history it will join.
HK_CA_MEMBERSHIP_LANES = ("buy", "watch")

# starts_at_inception left False in code for BOTH markets — undetermined, see
# git receipts gathered in the worker's RETURN (engine/hk_board_rank.py wasn't
# created until 2026-08-03 ("resurrection" of an earlier mechanism), and the
# HK/CA "standouts" board concept itself predates data/board_ledger/*.parquet
# by ~2-3 weeks (PR #81/#113, 2026-06-15) even though each parquet's first git
# commit holds exactly one date's worth of rows with no apparent backfill.
# Principal adjudicates; this worker does not flip either flag.
HK_CA_STARTS_AT_INCEPTION = False


def observations_from_board_ledger_frame(
    df: Any, visible_groups: AbstractSet[str] = HK_CA_VISIBLE_GROUPS,
) -> list[Observation]:
    """Adapter over data/board_ledger/{hk,ca}_board.parquet (columns
    ticker/date/group)."""
    if df is None or getattr(df, "empty", False):
        return []
    cols = set(getattr(df, "columns", ()))
    if "date" not in cols or "ticker" not in cols:
        return []
    vis = df
    if "group" in cols:
        vg = frozenset(str(x) for x in (visible_groups or ()))
        vis = df[df["group"].astype(str).isin(vg)]
    by_date: dict[str, set[str]] = {}
    for date_val, grp in vis.groupby("date", sort=False):
        iso = _iso_from_value(date_val)
        if not iso:
            continue
        tickers = {c for c in (_clean_id(t) for t in grp["ticker"].tolist()) if c}
        by_date.setdefault(iso, set()).update(tickers)
    return [(d, frozenset(by_date[d])) for d in sorted(by_date)]


def stamp_hkca_board_since(
    market: str, artifact: dict[str, Any] | None, *, data_dir: Path | None = None,
) -> dict[str, Any] | None:
    if not artifact:
        return artifact
    market_key = (market or "").lower()
    if market_key not in ("hk", "ca"):
        return artifact
    data = Path(data_dir) if data_dir is not None else _REPO_ROOT / "data"
    fname = "hk_board.parquet" if market_key == "hk" else "ca_board.parquet"
    path = data / "board_ledger" / fname
    hist: list[Observation] = []
    if path.exists():
        import pandas as pd  # noqa: PLC0415 — optional adapter dep
        hist = observations_from_board_ledger_frame(pd.read_parquet(path))
    # MEMBERSHIP (sustains tenure) folds in `watch`; DISPLAY (which rows get a
    # chip, below) stays the narrower pv_card-only `buy` lane.
    current_ids = identities_in_lanes(artifact, HK_CA_MEMBERSHIP_LANES)
    obs = with_current_board(hist, artifact.get("as_of"), current_ids)
    for lane in HK_CA_DISPLAY_LANES:
        rows = artifact.get(lane)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            ident = _clean_id(row.get("ticker"))
            if not ident:
                row["added_date"] = None
                continue
            start = current_continuous_membership_start(
                obs, ident, starts_at_inception=HK_CA_STARTS_AT_INCEPTION)
            row["added_date"] = start[0] if start else None
    return artifact


def stamp_hkca_board_since_fail_open(
    market: str, artifact: dict[str, Any] | None, *,
    data_dir: Path | None = None, log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        return stamp_hkca_board_since(market, artifact, data_dir=data_dir)
    except Exception as exc:  # noqa: BLE001 — additive display field, never fatal
        if log is not None:
            log.warning("%s board_since stamp failed (%s)", market, exc)
        return artifact


# ─────────────────────────────── Intl adapter ────────────────────────────────
# Carry-forward stamping ONLY — no history scan, no git subprocess (the git-log
# approach in a prior draft is structurally dead on the render lane: worktrees
# here are blobless/partial clones and a render-time `git show` over 40 commits
# is exactly the kind of git-in-the-build-path this program forbids).
#
# Visible-lane trace (2026-09-01): intl.html.j2 has exactly ONE pv_card call
# site, iterating `buys = setups.buy`. REQUEST_REPAIR re-check: grepped
# intl.html.j2 for `laggards` (the membership-vs-display question raised for
# US/CN/HK/CA) — zero occurrences of `setups.laggards` / `.get('laggards')` /
# any other reference to a laggards list anywhere in the template. Whatever
# `laggards` key the intl artifact may carry is never rendered as a name to a
# reader here, so it stays excluded — membership is `buy` only, unchanged.
INTL_VISIBLE_LANES = ("buy",)


def stamp_intl_board_since(
    artifact: dict[str, Any] | None, *, prior_artifact: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    """Carry-forward stamp for the Intl board. `prior_artifact` MUST be read by the
    caller from the committed site/factordata/intl_setups.json BEFORE this build
    overwrites it — this function does no I/O itself.

    Rules (frozen spec):
      - prior unreadable/malformed -> every added_date=None (fail-open).
      - present in prior with a valid ISO prior added_date -> carry it, unconditionally.
      - absent from prior, prior as_of and current as_of both valid ISO and
        current as_of > prior as_of -> added_date = current as_of (a genuinely new
        name, minted on the session it first appeared).
      - current as_of == prior as_of, or either is missing/invalid -> carry only,
        mint nothing (today: setups.as_of IS null upstream, so this ships all-None
        until the artifact carries a real session date — expected and correct).
    """
    if not artifact:
        return artifact
    lanes = INTL_VISIBLE_LANES
    prior_valid = isinstance(prior_artifact, Mapping)
    prior_as_of = _iso_from_value(prior_artifact.get("as_of")) if prior_valid else None
    current_as_of = _iso_from_value(artifact.get("as_of"))
    prior_since: dict[str, str] = {}
    prior_tickers: set[str] = set()
    if prior_valid:
        for lane in lanes:
            for row in (prior_artifact.get(lane) or []):
                if not isinstance(row, dict):
                    continue
                tk = _clean_id(row.get("ticker"))
                if not tk:
                    continue
                prior_tickers.add(tk)
                since = row.get("added_date")
                if is_iso_date(since):
                    prior_since[tk] = since
    can_mint = bool(prior_valid and prior_as_of and current_as_of and current_as_of > prior_as_of)
    for lane in lanes:
        rows = artifact.get(lane)
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            tk = _clean_id(row.get("ticker"))
            if not tk or not prior_valid:
                row["added_date"] = None
                continue
            if tk in prior_since:
                row["added_date"] = prior_since[tk]
            elif tk not in prior_tickers and can_mint:
                row["added_date"] = current_as_of
            else:
                row["added_date"] = None
    return artifact


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return blob if isinstance(blob, dict) else None


def stamp_intl_board_since_fail_open(
    artifact: dict[str, Any] | None, *,
    prior_artifact: Mapping[str, Any] | None = None,
    repo_root: Path | None = None,
    log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        if prior_artifact is None:
            root = repo_root or _REPO_ROOT
            prior_artifact = _read_json(root / "site" / "factordata" / "intl_setups.json")
        return stamp_intl_board_since(artifact, prior_artifact=prior_artifact)
    except Exception as exc:  # noqa: BLE001 — additive display field, never fatal
        if log is not None:
            log.warning("intl board_since stamp failed (%s)", exc)
        return artifact
