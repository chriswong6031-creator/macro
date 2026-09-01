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

    S4 FIX (2026-09-01 repair round): `observations` is materialized to a list
    ONCE, up front. The old code called `collapse_published_observations(observations)`
    first (which fully consumes an iterator) and THEN, further down, re-read the
    same `observations` argument a second time via `list(observations or ())` —
    a generator/iterator input is exhausted by the first pass, so the second read
    silently returned `[]` and every fossil date before today was dropped from the
    result. A list is a safe no-op to re-materialize; a generator is not.
    """
    observations = list(observations or ())
    obs = collapse_published_observations(observations)
    iso = _iso_from_value(current_as_of)
    if not iso:
        return obs
    if obs and iso <= obs[-1][0]:
        return obs
    cleaned_ids = {c for c in (_clean_id(x) for x in (current_ids or ())) if c}
    return collapse_published_observations(observations + [(iso, cleaned_ids)])


def current_continuous_membership_start(
    observations: Iterable[tuple[Any, Iterable[Any]]] | None,
    identity: Any,
    starts_at_inception: bool = False,
    full_coverage_since: str | None = None,
    requires_full_coverage: bool = False,
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

    SOUNDNESS FLOOR (M1/M2, 2026-09-01 repair round): `requires_full_coverage=True`
    opts a market into floor-gated absence proofs — the DEFAULT (False) is fully
    backward compatible and ignores `full_coverage_since` entirely, so every
    existing caller (US, HK/CA before their own floor lands, and the plain
    resolver-core tests) is unaffected. When opted in, `full_coverage_since`
    names the earliest ISO date at which a market's fossil is known to cover
    EVERY name-visible lane/group (see the per-market `*_full_coverage_since`
    helpers below). An observation dated BEFORE that floor may have been
    recorded while one or more name-visible lanes were not yet persisted at
    all — an identity "absent" from such an observation could simply be present
    in an unfossiled lane nothing recorded, which makes that absence
    UNPROVABLE, not proof of a reset. So, under `requires_full_coverage=True`,
    an absence-proof whose anchoring absence observation predates the floor (or
    whose market has no floor established yet at all — `full_coverage_since is
    None` counts as "never sound", not "no restriction") resolves to None
    rather than being trusted. This never affects "present" evidence (a name
    found in even a narrower historical lane set is still genuinely present) or
    the `starts_at_inception` left-censoring path, which is already
    None-by-default for every market that would need a floor.
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
    absence_date: str | None = None
    while idx >= 0:
        date, ids = obs[idx]
        if ident in ids:
            streak_start = date
            idx -= 1
            continue
        hit_absence = True
        absence_date = date
        break
    if hit_absence:
        if requires_full_coverage and (
            full_coverage_since is None or (absence_date or "") < full_coverage_since
        ):
            return None  # unsound: absence predates (or floor never reached) full coverage
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
    does not re-parse the file.

    S3 FIX (2026-09-01 repair round): each JSONL line is a WHOLE-BOARD snapshot,
    not an incremental per-name update — so when two lines share the same `as_of`
    date, the LAST line published for that date is the entire truth for that date
    and must REPLACE any earlier same-date line, never be unioned with it. The old
    code called `by_date.setdefault(iso, set()).update(ids)`, which merged a later
    same-date snapshot's ids into the earlier one — a name the later (correct,
    final) snapshot had already dropped would incorrectly keep sustaining tenure
    forever because the earlier line's copy of it never got removed from the
    unioned set."""
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
                # Last line per ISO date wins (replace, not union) — see the S3
                # docstring note above.
                by_date[iso] = ids
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

# MEMBERSHIP TRACE UPDATE (M1/M2, 2026-09-01 repair round — supersedes the
# "never fossil-tracked" trace on `observations_from_cn_frame` below):
# scripts/build_china_library.py now appends `wide["more_actionable"]` to
# board.parquet too, under a distinct `<live_definition>_more_actionable`
# board_definition (never in china_standout_track.WATCH_DEFINITIONS, so
# `observations_from_cn_frame`'s existing watch/legacy filter naturally
# includes it) and a distinct row-level `lane="more_actionable"`. It is
# persisted going FORWARD ONLY, starting the night this ships — there is no
# backfill of historical more_actionable membership, hence the soundness floor
# below (`cn_full_coverage_since`): any absence observed before that lane
# first appears in the fossil is unprovable, not proof of a reset.
CN_MEMBERSHIP_LANES = ("buy", "more_actionable")

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

    MEMBERSHIP TRACE (2026-09-01, REQUEST_REPAIR; UPDATED same day, M1/M2
    repair round): `board_definition` is the ONLY filter here, and that is
    deliberate, not an oversight — it is also now sufficient to include
    more_actionable rows. Traced scripts/build_china_library.py (append_board
    call sites ~L4268-4320) and engine/china_board_rank.py._partition:
    `wide["buy"]` (== `_board_lanes["featured"]`, the entry/featured shelf) is
    appended under the LIVE headline board_definition; `wide["more_actionable"]`
    is now ALSO appended (M1/M2 fix), under a distinct
    `<live_definition>_more_actionable` board_definition that is deliberately
    never added to china_standout_track.WATCH_DEFINITIONS — so this filter
    (which excludes only WATCH_DEFINITIONS + 'legacy') naturally keeps it IN
    the observation series. The explicit reversal_watch / v2-shadow /
    v3-shadow / continuation_watch cohorts remain excluded via
    WATCH_DEFINITIONS as before. `late_or_unfillable` / `forming` are still
    NEVER appended (china.html.j2's facet bar counts `late_or_unfillable` but
    never pv_cards it — display-only, no membership claim to make). Forward-only:
    more_actionable rows exist in the fossil starting the night this ships, not
    retroactively — see `cn_full_coverage_since` for the soundness floor this
    requires. `cn_current_visible_ids` below reconciles the CURRENT-day read to
    this same (now wider) fossil truth."""
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


def cn_full_coverage_since(df: Any) -> str | None:
    """M1/M2 (2026-09-01 repair round): earliest ISO date at which CN's fossil
    covers EVERY name-visible lane — i.e. the first date a more_actionable-tagged
    (`board_definition` ending in `_more_actionable`) row appears in
    board.parquet. Before this date, the fossil only ever recorded the featured
    (buy) lane, so an absence derived from an observation that old cannot
    distinguish "genuinely absent from every name-visible lane" from "present
    via more_actionable, which nothing recorded yet" — see
    `current_continuous_membership_start`'s SOUNDNESS FLOOR section. Returns
    None if no more_actionable row has ever been written (no sound absence
    proofs are possible yet for this market)."""
    if df is None or getattr(df, "empty", False):
        return None
    cols = set(getattr(df, "columns", ()))
    if "date" not in cols or "board_definition" not in cols:
        return None
    bd = df["board_definition"].astype(str)
    mask = bd.str.endswith("_more_actionable")
    if not mask.any():
        return None
    isos = sorted({iso for iso in (_iso_from_value(v) for v in df.loc[mask, "date"]) if iso})
    return isos[0] if isos else None


def cn_current_visible_ids(artifact: Mapping[str, Any] | None) -> set[str]:
    """Ticker set TONIGHT's build writes (or would write) to board.parquet under
    its live board_definition — `artifact["buy"]` (the "featured" lane) UNION
    `artifact["more_actionable"]` (M1/M2, 2026-09-01 repair round — both lanes
    are now fossil-written, see the trace above), regardless of the `stage` a
    card happens to display a buy row under (ENTRY vs RAN_LATE is a
    template-only partition of the SAME lane and must never gate membership).

    This IS now a superset of every card-rendered id for CN (buy's stage
    partition union more_actionable == exactly `_cn_card_rendered_ids_for_test`'s
    partition) — the historical "membership is narrower than display" gap this
    function used to encode for more_actionable is closed for TODAY's read;
    only pre-floor HISTORY (dates before `cn_full_coverage_since`) still cannot
    prove an absence soundly."""
    if not artifact:
        return set()
    buy = artifact.get("buy") or []
    more = artifact.get("more_actionable") or []
    ids: set[str] = set()
    for row in (buy if isinstance(buy, list) else []) + (more if isinstance(more, list) else []):
        if isinstance(row, dict) and (tk := _clean_id(row.get("ticker"))):
            ids.add(tk)
    return ids


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
    floor: str | None = None
    if path.exists():
        import pandas as pd  # noqa: PLC0415 — optional adapter dep
        _df = pd.read_parquet(path)
        hist = observations_from_cn_frame(_df, watch_definitions)
        floor = cn_full_coverage_since(_df)
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
                obs, ident, starts_at_inception=CN_STARTS_AT_INCEPTION,
                full_coverage_since=floor, requires_full_coverage=True)
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

# SOUNDNESS FLOOR PER MARKET (M1/M2, 2026-09-01 repair round) — HK and CA are
# NOT symmetric here, confirmed by census:
#
#   HK: hk.html.j2's "🏃 Market leaders" table (`_hk_ldrs`, fed by
#   `hk_board_rank.build_leaders_rows` in scripts/build_hk_library.py) is
#   genuinely name-visible (ticker + sector + a real forward-ranked table) AND
#   is a DIFFERENT, disjoint ticker set from buy/watch (`exclude=_claimed`
#   removes every buy/watch/laggard ticker before it is built) — a
#   demote-to-leaders-then-return move is exactly the under-recording M1/M2
#   exists to fix. It is deliberately NOT persisted to hk_board.parquet:
#   scripts/build_hk_library.py._board_ledger_calls's own docstring records a
#   2026-08-03 adversarial-review finding that appending leaders/ran/vetoed
#   rows there corrupted `board_ledger`'s Spearman rank-IC (board_pos is
#   assigned by LIST POSITION, and `board_ledger.scorecard`'s `ic_frame`
#   filters only by `board_definition`, never by `group` — confirmed by
#   reading engine/board_ledger.py directly, no group-based IC exclusion
#   exists) — the same docstring states the safe fix needs "its own book...
#   chartered as a §8-class follow-up", i.e. a NEW store, which this
#   program's own scope forbids ("no new store"). engine/board_ledger.py is
#   also rank/signal-authority code this program does not own or touch.
#   Consequence, stated plainly per the frozen spec: HK's `hk_full_coverage_
#   since` is permanently None until a dedicated follow-up safely persists
#   leaders coverage, so `stamp_hkca_board_since` runs HK with
#   `requires_full_coverage=True` — every absence-anchored HK candidate ships
#   `added_date=None` (honest "unprovable", not silently wrong) rather than a
#   confidently wrong date. HK's "Recently fired" (`ran`) strip is the same
#   shape but is a non-issue in PRACTICE today: hk.html.j2's own template
#   comment records "no `ran` array (every artifact today)" — it never
#   actually renders a row, so there is nothing live to under-record; the
#   same floor already covers it if it ever ships real rows.
#
#   CA: census of canada.html.j2 and scripts/build_canada.py/
#   build_canada_library.py found NO leaders or ran strip tied to `setups` at
#   all — canada.html.j2's pv_card loop is `setups.buy` and its only other
#   name-visible group is `setups.watch` (the anchor-grid watch-strip),
#   exactly the two lanes HK_CA_MEMBERSHIP_LANES / HK_CA_VISIBLE_GROUPS
#   already cover and hk_board.parquet's HK-only leaders lane above does not
#   apply. CA's fossil already covers every name-visible lane, so CA runs
#   with `requires_full_coverage=False` (unchanged, unaffected) — absence
#   proofs stay valid throughout, exactly like US.
HK_CA_REQUIRES_FULL_COVERAGE = {"hk": True, "ca": False}


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
            # M1/M2: only HK opts into the soundness floor (see
            # HK_CA_REQUIRES_FULL_COVERAGE docstring above) — CA's fossil
            # already covers every name-visible lane, so it is unaffected.
            # HK's floor never becomes non-None under this program's scope
            # (leaders is not persisted, by deliberate rank-authority
            # decision), so every HK absence-anchored result ships None.
            start = current_continuous_membership_start(
                obs, ident, starts_at_inception=HK_CA_STARTS_AT_INCEPTION,
                full_coverage_since=None,
                requires_full_coverage=HK_CA_REQUIRES_FULL_COVERAGE.get(market_key, False))
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

    S2 (2026-09-01 repair round): `prior_valid` gates on the prior artifact being
    a genuinely PARSEABLE mapping (i.e. `_read_json` succeeded) — nothing more.
    A parseable prior whose own `as_of` is missing/invalid still lets every
    ticker's existing ISO `added_date` CARRY forward unconditionally below (the
    `tk in prior_since` branch never checks `prior_as_of`/`current_as_of`); as_of
    validity gates ONLY whether a brand-new (never-seen) ticker may be MINTED a
    fresh date (`can_mint`). Residual loss window, stated honestly: the ONLY case
    that loses previously-recorded dates is a genuine parse/IO failure of the
    prior artifact itself (missing file, corrupt JSON, or non-dict payload) —
    every row then reads `prior_valid=False` and every added_date resolves to
    None for that one build, even for tickers that had a perfectly good prior
    date. There is no persistent ledger to recover a skipped night from; the next
    successful read carries forward from whatever is on disk at that time.
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


def _configured_site_dir(repo_root: Path | None = None) -> Path:
    """S1 (2026-09-01 repair round): single source of truth for the site output
    directory, matching the writer's own resolution (`config.ROOT /
    config.load()["storage"]["site_dir"]`, e.g. scripts/build_intl_library.py:312)
    instead of a hard-coded `"site"` literal that could silently diverge from a
    deployment's actual configured site_dir.

    An explicit `repo_root` is a caller override (tests isolating against a
    tmp_path fixture) and takes priority over `lib.config` — it must never fall
    through to the real project's live configured site_dir, which would read a
    real committed artifact instead of the test's isolated fixture. Only the
    caller-omits-both-`site_dir`-and-`repo_root` production path consults
    `lib.config`; if THAT import itself fails (e.g. a bare unit-test import with
    no repo config on the path), fall back to `<_REPO_ROOT>/site` — never fatal,
    this is a display-only read."""
    if repo_root is not None:
        return Path(repo_root) / "site"
    try:
        from lib import config as _config  # noqa: PLC0415

        return Path(_config.ROOT) / _config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001 — best-effort default, see docstring
        return _REPO_ROOT / "site"


def stamp_intl_board_since_fail_open(
    artifact: dict[str, Any] | None, *,
    prior_artifact: Mapping[str, Any] | None = None,
    site_dir: Path | None = None,
    repo_root: Path | None = None,
    log: Any | None = None,
) -> dict[str, Any] | None:
    try:
        if prior_artifact is None:
            sd = Path(site_dir) if site_dir is not None else _configured_site_dir(repo_root)
            prior_artifact = _read_json(sd / "factordata" / "intl_setups.json")
        return stamp_intl_board_since(artifact, prior_artifact=prior_artifact)
    except Exception as exc:  # noqa: BLE001 — additive display field, never fatal
        if log is not None:
            log.warning("intl board_since stamp failed (%s)", exc)
        return artifact
