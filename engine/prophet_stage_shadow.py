"""engine/prophet_stage_shadow.py — the live-Prophet × Stage forward-shadow.

This is the DEFINITIVE on-Prophet test the pre-registered backtest
(``research/PROPHET_STAGE_FUSION_PREREG.md`` §6) left open. The 2022-26 backtest
(``engine/prophet_stage_fusion.py``) was a MECHANISM test on the T1-T4 confluence
cascade as a PIT-replayable *proxy* for a Prophet-family timing entry — Prophet
itself has no backtestable history. This module tags Prophet's ACTUAL entries from
go-live with their stage-at-entry + last earnings-call context, then grades each
one at maturity, so the real on-Prophet answer accrues (the first 126-bar cohort
matures ~2026-12).

PURE ACCRUAL + MEASUREMENT. This module NEVER gates, ranks, or alters any Prophet
decision — every artifact it writes is display / shadow tier. The fusion
win-rate-gate construction is KILLED per ``research/DO_NOT_REBUILD.md``; this
shadow is a measurement, not a gate. A null here NEVER blocks or changes Prophet.

REUSE (measured identically to the backtest — nothing reinvented). R0-C moved the
shared point-in-time primitives into ``engine/prophet_stage_inputs.py``; the backtest
harness re-exports them, so this module reads the SAME code without importing a
research harness into a nightly production lane:
  * stage-at-entry  -> ``prophet_stage_inputs.stage_at_entry`` (PIT close[:entry]
      truncation → weinstein_stage.classify) and ``load_ticker_prices`` /
      ``load_bench_close``.
  * EC join         -> ``prophet_stage_inputs.load_ec_table`` / ``ec_index`` /
      ``ec_sent_at_entry`` (earnings_calls.parquet, most-recent call STRICTLY before
      entry).
  * grading         -> ``grading.terminal_state`` (clean15_126 & clean8_21) +
      ``grading.forward_metrics`` (21/63/126). Win = ``CLEAN_LIFTOFF``.

EC SOURCE STARVATION (R0-C — read before grading ``median_tilt``). The EC join's
backing parquet is a local-only EquityDesk backfill: gitignored, never committed, and
absent on every CI/deploy host. Where it is absent, every ``last_ec`` tag is null, the
Stage-2 ∩ EC cohort is empty, and ``median_tilt`` is computed on ZERO EC-tagged
entries. The hold-leash's §4 auto-demote clause reads exactly that cohort's count, so a
starved join does not merely weaken the measurement — it makes the clause unreachable,
and the promoted tilt can never be graded or self-demoted. ``median_tilt.ec_coverage``
and the summary's ``ec_source`` block state this explicitly so a starved sample is
never read as a real ≤0 tilt.

FORWARD LEDGER (house law): ``data/prophet_stage_shadow/ledger.jsonl`` is a
forward ledger; NIGHTLY IS THE SOLE ADVANCER of its grades. The grade advance is
gated on ``engine.ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly) —
the same sentinel every other forward ledger uses. A non-nightly run TAGS entries
(PIT-fixed, idempotent) but does NOT advance grades. The tag itself is PIT-fixed at
entry. A later canonical clock correction never mutates that raw historical row:
``revisions.jsonl`` receives an append-only full-row retag, and every reader applies
that overlay plus current Prophet quarantine before grading, summary splits, or tilt.
"""
from __future__ import annotations

import json
import hashlib
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from engine import confluence_tiers, grading, prophet_stage_inputs as psi
from engine.ledger_lane import nightly_advance_enabled

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Schema / constants                                                           #
# --------------------------------------------------------------------------- #
LEDGER_SCHEMA = "prophet_stage_shadow.ledger/v1"
REVISION_SCHEMA = "prophet_stage_shadow.revision/v1"
SUMMARY_SCHEMA = "prophet_stage_shadow.v1"

# Grading parameterizations — the SAME two rulers the backtest uses (reused verbatim
# from prophet_stage_inputs, which the backtest re-exports, so the shadow is graded
# identically to the mechanism test without importing the research harness).
PARAM_CLEAN15_126 = psi.PARAM_CLEAN15_126   # liftoff 1.15, horizon 126 (positional)
PARAM_CLEAN8_21 = psi.PARAM_CLEAN8_21        # liftoff 1.08, horizon 21  (rotational)
FWD_HORIZONS = psi.FWD_HORIZONS              # (21, 63, 126)

# The longest horizon that must have elapsed (+ fill) before a horizon can grade.
FRESH_WEEKS_MAX = psi.FRESH_WEEKS_MAX        # fresh Stage-2 = weeks_in_stage <= 10
STAGE2 = psi.STAGE2

ACCRUAL_DISCLAIMER = (
    "accruing — first 126-day cohort matures ~2026-12; n is tiny until then; NOT "
    "yet decisive. The 2022-26 backtest on the T-cascade confluence proxy found no "
    "CI-clean win-rate edge (a quality right-shift only) — this forward-shadow is the "
    "definitive on-Prophet check, tagging Prophet's ACTUAL entries from go-live. "
    "Display / shadow tier only: it NEVER gates, ranks, or alters any Prophet decision."
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _shadow_dir(root: Path) -> Path:
    return Path(root) / "prophet_stage_shadow"


def ledger_path(root: Path) -> Path:
    return _shadow_dir(root) / "ledger.jsonl"


def summary_path(root: Path) -> Path:
    return _shadow_dir(root) / "summary.json"


def revisions_path(root: Path) -> Path:
    """Append-only effective-row overlays; raw PIT rows are never rewritten for
    a later canonical clock correction."""
    return _shadow_dir(root) / "revisions.jsonl"


# --------------------------------------------------------------------------- #
# Prophet entry enumeration — the canonical (asset, signal_date, id) list.     #
# --------------------------------------------------------------------------- #
def _clean_ec(v: float | None) -> float | None:
    return float(v) if (v is not None and pd.notna(v)) else None


def collect_prophet_entries(site_root: Path, data_root: Path) -> list[dict[str, Any]]:
    """Every Prophet entry (active + closed), de-duplicated by plan id.

    Sources (union, keyed by plan id — id = ``<TICKER>-<DIR>-<YYYYMMDD>``):
      * effective plan projection       — immutable plans + append-only corrections
      * ``site/prophet/index.json``      — active, already-corrected plans
      * effective ledger projection     — immutable ledger + append-only corrections

    Returns [{id, asset, signal_date, direction, source}]. The id is PIT-stable
    (never re-issued), so it is the idempotency key for the shadow ledger. Fail-open:
    an unreadable source is skipped with a warning, never raised.
    """
    site_root = Path(site_root)
    data_root = Path(data_root)
    entries: dict[str, dict[str, Any]] = {}
    excluded_ids: set[str] = set()

    def _add(pid: Any, asset: Any, signal_date: Any, direction: Any, source: str) -> None:
        if not pid or not asset or not signal_date:
            return
        pid = str(pid)
        if pid in excluded_ids:
            return
        if pid in entries:
            return  # keep-first (plans dir → index → ledger); id is PIT-stable
        entries[pid] = {
            "id": pid,
            "asset": str(asset),
            "signal_date": str(signal_date),
            "direction": str(direction or "BULL"),
            "source": source,
        }

    # Load BOTH canonical projections before reading the already-rendered index.
    # Otherwise a newly quarantined id skipped by the plan reader can sneak straight
    # back in through index.json's union leg.
    repo_root = site_root.parent
    plan_projection = None
    ledger_projection = None
    try:
        from engine.prophet_integrity import load_effective_plans  # noqa: PLC0415

        plan_projection = load_effective_plans(repo_root)
        excluded_ids.update(plan_projection.quarantined_ids)
    except Exception as e:  # noqa: BLE001 — shadow lane remains fail-open
        log.warning("prophet_stage_shadow: effective plan projection unavailable (%s)", e)
    try:
        from engine.prophet_integrity import load_effective_ledger  # noqa: PLC0415

        ledger_projection = load_effective_ledger(repo_root)
        excluded_ids.update(ledger_projection.quarantined_ids)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: effective ledger projection unavailable (%s)", e)

    # The shadow grades stage-at-ENTRY, not base formation or marker knowability.
    # Read the canonical correction projection first so raw legacy dates cannot win
    # through keep-first ordering. Quarantined plans never enter a forward cohort.
    if plan_projection is not None:
        for plan_id, d in plan_projection.plans.items():
            _add(
                d.get("id"), d.get("asset"),
                d.get("price_basis_date") or d.get("entry_date") or d.get("asof")
                or d.get("signal_date") or d.get("_signal_date"),
                d.get("direction"), "effective_plan",
            )

    # 2. active index entries
    idx_path = site_root / "prophet" / "index.json"
    if idx_path.exists():
        try:
            idx = json.loads(idx_path.read_text(encoding="utf-8"))
            for p in idx.get("plans", []) or []:
                _add(p.get("id"), p.get("asset"),
                     p.get("price_basis_date") or p.get("entry_date")
                     or p.get("recorded_at") or p.get("plan_asof")
                     or p.get("signal_date") or p.get("_signal_date"),
                     p.get("direction"), "index")
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: unreadable index.json (%s)", e)

    # 3. closed ledger rows
    if ledger_projection is not None:
        for r in ledger_projection.rows:
            _add(
                r.get("id"), r.get("asset"),
                r.get("price_basis_date") or r.get("entry_date")
                or r.get("recorded_at") or r.get("signal_date"),
                r.get("direction"), "effective_ledger",
            )
    return list(entries.values())


# --------------------------------------------------------------------------- #
# Ledger I/O + deterministic effective projection.                            #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ShadowLedgerProjection:
    """Effective shadow view without mutating any historical PIT tag row."""

    rows: dict[str, dict[str, Any]]
    raw_count: int
    revision_count: int
    quarantined_ids: frozenset[str]
    clock_mismatch_ids: frozenset[str]
    authority_error: str | None = None


def projection_membership_gaps(
    expected_entries: list[dict[str, Any]],
    projection: ShadowLedgerProjection,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return missing and orphan effective IDs for the lossless cohort contract.

    ``collect_prophet_entries`` has already removed canonical quarantines, so exact
    equality is required before raw/revision/summary bytes may publish atomically.
    """
    expected_ids = {str(entry.get("id") or "") for entry in expected_entries}
    expected_ids.discard("")
    effective_ids = set(projection.rows)
    return (
        frozenset(expected_ids - effective_ids),
        frozenset(effective_ids - expected_ids),
    )


def _entry_clock(row: dict[str, Any]) -> str | None:
    value = (
        row.get("price_basis_date")
        or row.get("entry_date")
        or row.get("recorded_at")
        or row.get("plan_asof")
        or row.get("asof")
        or row.get("signal_date")
        or row.get("_signal_date")
    )
    return str(value) if value else None


def _load_raw_ledger(root: Path) -> dict[str, dict[str, Any]]:
    """Raw immutable-at-entry rows, first-write-wins by plan id."""
    p = ledger_path(root)
    out: dict[str, dict[str, Any]] = {}
    if not p.exists():
        return out
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                r = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            pid = r.get("id")
            if pid:
                # Raw PIT evidence is append-only. A duplicate can only be a
                # damaged/manual replay; it cannot supersede the first observed row.
                out.setdefault(str(pid), r)
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: ledger read failed (%s)", e)
    return out


def _load_revisions(root: Path) -> tuple[dict[str, dict[str, Any]], frozenset[str]]:
    """Load append-only full-row overlays, keeping the last event for each id.

    A malformed event is ignored loudly. That fails closed for a clock migration:
    the old raw row still mismatches the canonical clock and is excluded below.
    """
    path = revisions_path(root)
    latest: dict[str, dict[str, Any]] = {}
    event_ids: set[str] = set()
    if not path.exists():
        return latest, frozenset()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        log.warning("prophet_stage_shadow: revisions unreadable (%s)", exc)
        return latest, frozenset()
    for lineno, line in enumerate(lines, start=1):
        text = line.strip()
        if not text or text.startswith("#"):
            continue
        try:
            event = json.loads(text)
            event_id = str(event["id"])
            pid = str(event["corrects_id"])
            row = event["row"]
            if event.get("schema") != REVISION_SCHEMA or not isinstance(row, dict):
                raise ValueError("unknown schema or non-object row")
            if str(row.get("id") or "") != pid:
                raise ValueError("row id does not match corrects_id")
            if event_id in event_ids:
                continue
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            log.warning(
                "prophet_stage_shadow: invalid revision line %d (%s) — ignored",
                lineno,
                exc,
            )
            continue
        event_ids.add(event_id)
        latest[pid] = event
    return latest, frozenset(event_ids)


def _append_revision(
    root: Path,
    row: dict[str, Any],
    *,
    kind: str,
    asof: str,
    basis: str,
) -> bool:
    """Append one idempotent full-row overlay; never rewrite the raw ledger."""
    core = {
        "schema": REVISION_SCHEMA,
        "corrects_id": str(row["id"]),
        "kind": kind,
        "effective_signal_date": str(row.get("signal_date") or ""),
        "recorded_asof": asof,
        "basis": basis,
        "row": row,
    }
    canonical = json.dumps(core, sort_keys=True, separators=(",", ":"), default=str)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    event = {"id": f"{row['id']}:{kind}:{digest[:24]}", **core}
    _, existing_ids = _load_revisions(root)
    if event["id"] in existing_ids:
        return False
    directory = _shadow_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    with revisions_path(root).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, default=str, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return True


def _canonical_shadow_authority(
    root: Path,
) -> tuple[dict[str, str], frozenset[str]]:
    """Canonical clock/quarantine view shared with Prophet management and grading."""
    from engine.prophet_integrity import load_effective_ledger, load_effective_plans

    repo_root = Path(root).parent
    plans = load_effective_plans(repo_root)
    ledger = load_effective_ledger(repo_root)
    clocks: dict[str, str] = {}
    for pid, row in plans.plans.items():
        clock = _entry_clock(row)
        if clock:
            clocks[str(pid)] = clock
    for row in ledger.rows:
        pid = str(row.get("id") or "")
        clock = _entry_clock(row)
        if pid and clock and pid not in clocks:
            clocks[pid] = clock
    quarantined = frozenset(
        set(plans.quarantined_ids) | set(ledger.quarantined_ids)
    )
    return clocks, quarantined


def _project_shadow_ledger(root: Path) -> ShadowLedgerProjection:
    raw = _load_raw_ledger(root)
    revisions, _ = _load_revisions(root)
    current = {pid: dict(row) for pid, row in raw.items()}
    for pid, event in revisions.items():
        current[pid] = dict(event["row"])
    try:
        clocks, quarantined = _canonical_shadow_authority(root)
    except Exception as exc:  # fail closed: no stale row reaches grade/summary/tilt
        detail = str(exc)
        log.warning(
            "prophet_stage_shadow: canonical authority unavailable (%s) — "
            "effective shadow projection withheld",
            detail,
        )
        return ShadowLedgerProjection(
            rows={},
            raw_count=len(raw),
            revision_count=len(revisions),
            quarantined_ids=frozenset(),
            clock_mismatch_ids=frozenset(current),
            authority_error=detail,
        )

    effective: dict[str, dict[str, Any]] = {}
    mismatches: set[str] = set()
    for pid, row in current.items():
        if pid in quarantined:
            continue
        canonical_clock = clocks.get(pid)
        if canonical_clock and str(row.get("signal_date") or "") != canonical_clock:
            mismatches.add(pid)
            continue
        effective[pid] = row
    return ShadowLedgerProjection(
        rows=effective,
        raw_count=len(raw),
        revision_count=len(revisions),
        quarantined_ids=frozenset(pid for pid in current if pid in quarantined),
        clock_mismatch_ids=frozenset(mismatches),
    )


def _load_ledger(root: Path) -> dict[str, dict[str, Any]]:
    """Effective corrected, quarantine-filtered shadow rows."""
    return _project_shadow_ledger(Path(root)).rows


def _append_raw_rows(root: Path, rows: list[dict[str, Any]]) -> int:
    """Append new PIT rows durably; never rewrite existing historical evidence."""
    existing_ids = set(_load_raw_ledger(root))
    appendable: list[dict[str, Any]] = []
    for row in rows:
        pid = str(row.get("id") or "")
        if not pid or pid in existing_ids:
            continue
        existing_ids.add(pid)
        appendable.append(row)
    if not appendable:
        return 0
    d = _shadow_dir(root)
    d.mkdir(parents=True, exist_ok=True)
    p = ledger_path(root)
    existed = p.exists() and p.stat().st_size > 0
    with p.open("a", encoding="utf-8") as handle:
        if not existed:
            handle.write(
                "# prophet_stage_shadow forward ledger — schema " + LEDGER_SCHEMA + "\n"
                "# One immutable row per Prophet entry: PIT stage-at-entry + last-EC tag.\n"
                "# Corrected clocks and grade advances append to revisions.jsonl; raw rows never rewrite.\n"
                "# Display/shadow tier — NEVER gates/ranks/alters Prophet. Nightly is the sole grade advancer.\n"
            )
        for row in sorted(appendable, key=lambda value: str(value.get("id") or "")):
            handle.write(json.dumps(row, default=str, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return len(appendable)


def _write_ledger(root: Path, rows: dict[str, dict[str, Any]]) -> None:
    """One-shot fixture/bootstrap writer retained for research/test callers.

    Production tagging never calls this helper. Refuse an existing raw ledger so
    the compatibility seam cannot become a historical rewrite path.
    """
    path = ledger_path(root)
    if path.exists() and path.stat().st_size:
        raise RuntimeError("raw Prophet Stage-shadow ledger already exists; rewrite refused")
    _append_raw_rows(root, list(rows.values()))


# --------------------------------------------------------------------------- #
# Tagging — PIT stage + last-EC at each entry's signal_date (idempotent).      #
# --------------------------------------------------------------------------- #
def _tag_one(entry: dict[str, Any], data_root: Path, bench: pd.Series | None,
             ec_by_ticker: dict[str, pd.DataFrame]) -> dict[str, Any]:
    """Compute the PIT tag for one Prophet entry. Fail-open: a missing OHLCV/EC never
    crashes — it records nulls + a ``tag_reason``. The stage is read via the audited
    truncating ``prophet_stage_fusion.stage_at_entry`` (close sliced to <= signal_date),
    so no post-entry price can leak into the tag."""
    asset = entry["asset"]
    sig = entry["signal_date"]
    row: dict[str, Any] = {
        "schema": LEDGER_SCHEMA,
        "id": entry["id"],
        "asset": asset,
        "signal_date": sig,
        "direction": entry.get("direction", "BULL"),
        "source": entry.get("source"),
        # tag fields (PIT-fixed at entry)
        "stage_at_entry": None,
        "weeks_in_stage": None,
        "fresh": None,
        "stage_detailed": None,
        "last_ec": None,
        "t_tier_at_entry": None,
        "tagged_asof": None,
        "tag_reason": None,
        # grade fields (nightly-advanced; null until matured)
        "graded": False,
        "graded_asof": None,
        "terminal_state_clean15_126": None,
        "terminal_state_clean8_21": None,
        "fwd": {},
    }

    close, vol = psi.load_ticker_prices(asset, Path(data_root))
    if close is None or close.empty:
        row["tag_reason"] = "no OHLCV in baskets/ohlcv or data/stocks — tagged null"
        return row

    # PIT stage (truncating classify — the look-ahead guard).
    try:
        st, wis, nwk = psi.stage_at_entry(close, vol, bench, sig)
    except Exception as e:  # noqa: BLE001
        row["tag_reason"] = f"stage classify failed ({e}) — tagged null"
        return row

    # weinstein classify gives fresh + stage_detailed too; re-derive via the truncated
    # classify for the richer fields (same PIT slice as stage_at_entry).
    fresh = None
    stage_detailed = None
    try:
        ed = pd.Timestamp(sig)
        c = close[close.index <= ed]
        v = vol[vol.index <= ed] if vol is not None and len(vol) else None
        b = bench[bench.index <= ed] if bench is not None and len(bench) else bench
        from engine import weinstein_stage
        res = weinstein_stage.classify(c, v, b)
        fresh = bool(res.get("fresh", False))
        stage_detailed = res.get("stage_detailed")
    except Exception as e:  # noqa: BLE001
        log.debug("prophet_stage_shadow: fresh/detailed lookup failed for %s (%s)", asset, e)

    # last EC strictly before entry.
    ec_val = psi.ec_sent_at_entry(ec_by_ticker, asset, sig)
    last_ec = None
    if ec_val is not None:
        g = ec_by_ticker.get(str(asset))
        call_date = None
        if g is not None and not g.empty:
            prior = g[g["call_date"] < pd.Timestamp(sig)]
            if not prior.empty:
                call_date = str(prior["call_date"].iloc[-1].date())
        last_ec = {"sent": ec_val, "call_date": call_date}

    # T-tier at entry (if the confluence cascade classifies it) — informational.
    t_tier = None
    try:
        stream = confluence_tiers.tier_stream(close[close.index <= pd.Timestamp(sig)])
        if stream is not None and not stream.empty and "tier" in stream.columns:
            prior = stream[stream.index <= pd.Timestamp(sig)]
            if not prior.empty:
                t_tier = prior["tier"].iloc[-1]
    except Exception as e:  # noqa: BLE001
        log.debug("prophet_stage_shadow: t-tier lookup failed for %s (%s)", asset, e)

    row.update({
        "stage_at_entry": int(st) if st else 0,
        "weeks_in_stage": int(wis),
        "fresh": fresh,
        "stage_detailed": stage_detailed,
        "last_ec": last_ec,
        "t_tier_at_entry": t_tier,
        "tag_reason": "ok" if st else "too-young / unstageable at entry — stage=0",
    })
    return row


def tag_entries(root: str | Path | None = None, *, site_root: str | Path | None = None,
                ec_path: str | Path | None = None, asof: str | None = None) -> dict[str, Any]:
    """UPSERT a PIT tag for every Prophet entry into the shadow ledger, keyed by plan id.

    The tag is PIT-FIXED at the effective entry clock (stage + last-EC), so an
    ordinary re-run never changes it. If the canonical append-only Prophet correction
    ledger later proves that clock wrong, the raw tag remains untouched and one
    idempotent full-row retag is appended to revisions.jsonl. New entries are written
    normally. Fail-open per entry: missing OHLCV/EC records nulls + a reason, never a
    crash. Runs in ANY lane (tagging is not a ledger *advance*; grading is).

    Returns a summary dict {n_entries, n_tagged_now, n_already, n_null}.
    """
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    site_root = Path(site_root) if site_root is not None else (_repo_root() / "site")
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    entries = collect_prophet_entries(site_root, data_root)
    raw = _load_raw_ledger(data_root)
    projection = _project_shadow_ledger(data_root)
    existing = projection.rows

    bench = psi.load_bench_close(data_root)
    ec_df, ec_source = psi.load_ec_table_with_source(ec_path)
    ec_by_ticker = psi.ec_index(ec_df)
    if ec_source.get("state") != psi.EC_SOURCE_AVAILABLE:
        # R0-C: the join that feeds median_tilt (and therefore the hold-leash's §4
        # auto-demote floor) has no source here. Every tag written in this run will
        # carry last_ec=null, so the Stage-2 ∩ earnings cohort stays empty by absence.
        # "::" MUST start the line — a logger's prefix would silently drop the annotation.
        print("::warning:: prophet_stage_shadow: earnings-call source unavailable "
              f"({ec_source.get('path')}) — {ec_source.get('reason')}; entries tagged in "
              "this run carry no earnings reading, so median_tilt accrues an EMPTY "
              "Stage-2 ∩ earnings cohort and the hold-leash demote floor stays unreachable",
              flush=True)

    n_tagged_now = 0
    n_clock_retagged = 0
    n_null = 0
    new_raw_rows: list[dict[str, Any]] = []
    for entry in entries:
        pid = entry["id"]
        if pid in existing:
            continue  # idempotent — the tag is PIT-fixed; never re-tag
        row = _tag_one(entry, data_root, bench, ec_by_ticker)
        row["tagged_asof"] = asof
        if row.get("stage_at_entry") in (None, 0) and row.get("tag_reason", "").startswith("no OHLCV"):
            n_null += 1
        if projection.authority_error is None and pid in projection.clock_mismatch_ids:
            # The raw PIT tag remains an immutable historical record of the old
            # clock. A full corrected-clock row is appended as an overlay; all
            # readers use the effective projection and the stale raw tag can no
            # longer grade, summarize, or feed median_tilt.
            if _append_revision(
                data_root,
                row,
                kind="clock_retag",
                asof=asof,
                basis="canonical Prophet price clock changed; PIT tag recomputed",
            ):
                n_clock_retagged += 1
                n_tagged_now += 1
        elif pid not in raw:
            raw[pid] = row
            new_raw_rows.append(row)
            n_tagged_now += 1

    _append_raw_rows(data_root, new_raw_rows)

    final_projection = _project_shadow_ledger(data_root)

    return {
        "n_entries": len(entries),
        "n_tagged_now": n_tagged_now,
        "n_already": len(entries) - n_tagged_now,
        "n_clock_retagged": n_clock_retagged,
        "n_null": n_null,
        "n_ledger": len(final_projection.rows),
        "n_quarantined_excluded": len(final_projection.quarantined_ids),
        "n_clock_mismatch_excluded": len(final_projection.clock_mismatch_ids),
        # R0-C: whether this run's EC join had a source at all (starved vs honest null).
        "ec_source": ec_source,
    }


# --------------------------------------------------------------------------- #
# Grading — nightly-gated advance of matured entries.                          #
# --------------------------------------------------------------------------- #
def _horizon_elapsed(close: pd.Series, signal_date, horizon: int) -> bool:
    """True when ``horizon`` forward bars (after the next-bar fill) exist for the entry —
    i.e. the terminal_state/forward_metrics for that horizon can resolve, not freeze."""
    fill = grading.fill_index(close, signal_date)
    if fill is None:
        return False
    return (len(close) - 1 - fill) >= horizon


def _grade_one(row: dict[str, Any], data_root: Path) -> bool:
    """Grade one tagged entry through the SAME rulers the backtest uses, in-place.

    Only writes a terminal_state / fwd metric once its horizon has elapsed AND forward
    prices exist (frozen-until-matured — a not-yet-matured horizon stays null and is
    re-checked on a later nightly). Returns True if any grade field changed. Fail-open."""
    asset = row["asset"]
    sig = row["signal_date"]
    changed = False
    close, _ = psi.load_ticker_prices(asset, Path(data_root))
    if close is None or close.empty:
        # delisted / absent: try the dead-name-resolved grading series (survivorship).
        try:
            close = grading.resolve_series(asset, None)
        except Exception:  # noqa: BLE001
            close = None
        if close is None or close.empty:
            return False
    else:
        try:
            close = grading.resolve_series(asset, close)
        except Exception:  # noqa: BLE001
            pass

    # clean15_126 terminal state (only when the 126-bar horizon has elapsed).
    if row.get("terminal_state_clean15_126") is None and _horizon_elapsed(close, sig, 126):
        try:
            ts = grading.terminal_state(close, sig, **PARAM_CLEAN15_126)
            if ts.get("state") is not None:
                row["terminal_state_clean15_126"] = ts.get("state")
                changed = True
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade clean15_126 %s failed (%s)", asset, e)

    # clean8_21 terminal state (only when the 21-bar horizon has elapsed).
    if row.get("terminal_state_clean8_21") is None and _horizon_elapsed(close, sig, 21):
        try:
            ts = grading.terminal_state(close, sig, **PARAM_CLEAN8_21)
            if ts.get("state") is not None:
                row["terminal_state_clean8_21"] = ts.get("state")
                changed = True
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade clean8_21 %s failed (%s)", asset, e)

    # forward metrics per horizon (fill in each horizon as it matures).
    try:
        fwd = grading.forward_metrics(close, sig, horizons=FWD_HORIZONS)
        cur = row.get("fwd") or {}
        for h in FWD_HORIZONS:
            for k in (f"fwd_ret_{h}", f"fwd_mdd_{h}", f"fwd_mfe_{h}"):
                val = fwd.get(k)
                if val is not None and cur.get(k) is None:
                    cur[k] = val
                    changed = True
        row["fwd"] = cur
    except Exception as e:  # noqa: BLE001
        log.warning("prophet_stage_shadow: forward_metrics %s failed (%s)", asset, e)

    if changed:
        row["graded"] = any(row.get(k) is not None for k in
                            ("terminal_state_clean15_126", "terminal_state_clean8_21")) or bool(row.get("fwd"))
    return changed


def grade_matured(root: str | Path | None = None, *, asof: str | None = None,
                  force: bool = False) -> dict[str, Any]:
    """Advance grades for tagged entries whose horizons have elapsed AND forward prices
    exist. NIGHTLY IS THE SOLE ADVANCER (house law): gated on
    ``ledger_lane.nightly_advance_enabled()`` (COLLECT_LANE=nightly). A non-nightly run
    is a no-op for grades (``force=True`` bypasses the gate for tests only).

    Idempotent: a horizon already graded is never re-graded; not-yet-matured horizons
    stay null and are re-checked on a later nightly. Grade advances are append-only
    full-row revisions, so neither a corrected clock nor a new grade rewrites raw PIT
    evidence. Fail-open per entry.

    Returns {advanced, gate_open, n_ledger}.
    """
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    if not (force or nightly_advance_enabled()):
        log.info("prophet_stage_shadow: grade_matured skipped (COLLECT_LANE != nightly — "
                 "nightly is the sole grade advancer)")
        return {"advanced": 0, "gate_open": False, "n_ledger": len(_load_ledger(data_root))}

    projection = _project_shadow_ledger(data_root)
    rows = projection.rows
    advanced = 0
    for pid, row in rows.items():
        try:
            if _grade_one(row, data_root):
                row["graded_asof"] = asof
                if _append_revision(
                    data_root,
                    row,
                    kind="grade_advance",
                    asof=asof,
                    basis="nightly matured-horizon grade advance",
                ):
                    advanced += 1
        except Exception as e:  # noqa: BLE001
            log.warning("prophet_stage_shadow: grade_one %s failed (%s)", pid, e)

    final_projection = _project_shadow_ledger(data_root)
    return {
        "advanced": advanced,
        "gate_open": True,
        "n_ledger": len(final_projection.rows),
        "n_quarantined_excluded": len(final_projection.quarantined_ids),
        "n_clock_mismatch_excluded": len(final_projection.clock_mismatch_ids),
    }


# --------------------------------------------------------------------------- #
# Summarize — the accruing comparison (display-only; nulls printed).           #
# --------------------------------------------------------------------------- #
def _win_split(rows: list[dict[str, Any]], param_field: str) -> dict[str, Any]:
    """CLEAN_LIFTOFF win split over the matured subset for one ruler field.

    Returns {n_matured, n_win, win_rate} — win_rate is None until any entry matures
    (nulls printed, never a fabricated 0.0 rate on n=0)."""
    matured = [r for r in rows if r.get(param_field) is not None]
    n = len(matured)
    wins = sum(1 for r in matured if r.get(param_field) == grading.TerminalState.CLEAN_LIFTOFF)
    return {
        "n_matured": n,
        "n_win": wins,
        "win_rate": (wins / n) if n else None,
    }


def _median_tilt(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """PSQ-TILT W1 §4 measurement — median fwd_ret_126 for the Stage-2 ∩ EC-positive
    subset vs the rest, over the matured-126 subset. This is a MEASUREMENT block the
    self-demoting tilt reads (engine/prophet_bridge._stage_tilt_demoted); it NEVER
    gates, ranks, or alters a Prophet pick. Nulls until cohorts mature (n tiny until
    ~2026-12). No trading verbs; no 'validated'.

    stage2_ec = stage_at_entry == STAGE2 AND last_ec.sent >= EC_SENT_GATE.
    diff = median(stage2_ec) - median(rest) (null when either side is unmatured).

    ``ec_coverage`` (R0-C) is the starvation disclosure: how many ledger rows carry ANY
    earnings-call tag at all. When it is zero the stage2_ec cohort is empty BY SOURCE
    ABSENCE, not because Stage-2 ∩ EC entries did not occur — an empty-sample null that
    must never be read as a real ≤0 tilt. It is disclosure only: no count here changes
    a median, a diff, or a pick.

    RECONSTRUCTED ROWS ARE EXCLUDED (§0.6e, research/PROPHET_OUTAGE_BACKFILL_2026_08.md).
    Unlike the surrounding display splits, this block's output is READ BACK into live
    geometry: ``_stage_tilt_demoted`` consumes ``median_tilt`` and the answer reaches
    ``plan_horizon_days`` on plans originating tonight. A cohort statistic is the one
    place a backfilled row stops being display-tier and starts steering live picks, so
    the 2026-08-09 replay's rows are dropped here even though they are graded on real
    bars — their SELECTION was reconstructed, and a leash derived partly from
    reconstructed selection is not the leash the live rule earned.
    """
    from engine.prophet_bridge import is_reconstructed  # noqa: PLC0415

    rows = [r for r in rows if not is_reconstructed(r)]
    matured = [r for r in rows if (r.get("fwd") or {}).get("fwd_ret_126") is not None]

    def _ec_sent(r: dict[str, Any]) -> Any:
        return (r.get("last_ec") or {}).get("sent")

    def _is_stage2_ec(r: dict[str, Any]) -> bool:
        sent = _ec_sent(r)
        return (
            r.get("stage_at_entry") == STAGE2
            and sent is not None
            and sent >= psi.EC_SENT_GATE
        )

    s2ec = [r for r in matured if _is_stage2_ec(r)]
    rest = [r for r in matured if not _is_stage2_ec(r)]

    def _median(subset: list[dict[str, Any]]) -> float | None:
        vals = [float((r.get("fwd") or {})["fwd_ret_126"]) for r in subset]
        return float(pd.Series(vals).median()) if vals else None

    med_s2ec = _median(s2ec)
    med_rest = _median(rest)
    diff = (med_s2ec - med_rest) if (med_s2ec is not None and med_rest is not None) else None

    n_rows_with_ec = sum(1 for r in rows if _ec_sent(r) is not None)
    n_matured_with_ec = sum(1 for r in matured if _ec_sent(r) is not None)
    ec_join_state = (
        psi.EC_SOURCE_AVAILABLE if n_rows_with_ec else psi.EC_SOURCE_UNAVAILABLE
    )
    if n_rows_with_ec:
        coverage_note = (
            f"{n_rows_with_ec} of {len(rows)} tagged entries carry an earnings-call "
            "reading; the cohort split below is measured on real tags."
        )
    else:
        coverage_note = (
            "NO tagged entry carries an earnings-call reading — the earnings-call "
            "source is absent on the host that tagged this ledger, so the Stage-2 ∩ "
            "earnings cohort is empty by source absence, not by outcome. Every number "
            "in this block is an empty-sample null, NOT a measured result, and the "
            "hold-leash's demote floor cannot be reached while this stays zero."
        )

    return {
        "median_fwd_ret_126": {"stage2_ec": med_s2ec, "rest": med_rest},
        "diff": diff,
        "n_matured_126": {"stage2_ec": len(s2ec), "rest": len(rest)},
        "ec_coverage": {
            "state": ec_join_state,
            "n_rows_with_ec": n_rows_with_ec,
            "n_rows": len(rows),
            "n_matured_126_with_ec": n_matured_with_ec,
            "note": coverage_note,
        },
        "note": (
            "median fwd_ret_126 split for the Stage-2 ∩ EC-positive cohort vs the "
            "rest, over matured-126 entries. MEASUREMENT ONLY — the hold-leash reads "
            "diff/n to self-demote; this layer never gates, ranks, or alters a pick. "
            "diff/medians are null until both sides mature (~2026-12). Read "
            "ec_coverage first: with no earnings-call tags the split is an empty "
            "sample, not a result."
        ),
    }


def summarize(root: str | Path | None = None, *, asof: str | None = None) -> dict[str, Any]:
    """Emit ``data/prophet_stage_shadow/summary.json`` — the accruing Stage-2-vs-rest
    comparison ON ACTUAL PROPHET ENTRIES, with an honest accrual disclaimer.

    is_context_only + display_only. Prints nulls (no fabricated rate on n=0), no
    'validated', no trading verbs. Returns the summary dict (also written to disk)."""
    from lib import config
    data_root = Path(root) if root is not None else config.data_dir()
    asof = asof or pd.Timestamp.now("UTC").date().isoformat()

    projection = _project_shadow_ledger(data_root)
    rows = list(projection.rows.values())
    n_entries = len(rows)
    n_tagged = sum(1 for r in rows if r.get("stage_at_entry") not in (None,))
    n_stageable = [r for r in rows if r.get("stage_at_entry")]  # stage in 1..4 (nonzero)

    # partitions ON PROPHET ENTRIES.
    stage2 = [r for r in n_stageable if r.get("stage_at_entry") == STAGE2]
    rest = [r for r in n_stageable if r.get("stage_at_entry") != STAGE2]
    fresh_stage2 = [r for r in stage2 if r.get("fresh")]
    pos_ec = [r for r in n_stageable
              if (r.get("last_ec") or {}).get("sent") is not None
              and (r.get("last_ec") or {}).get("sent") >= psi.EC_SENT_GATE]

    # per-horizon maturity counts (how many entries have each horizon graded).
    n_matured = {}
    for h in FWD_HORIZONS:
        n_matured[str(h)] = sum(
            1 for r in rows if (r.get("fwd") or {}).get(f"fwd_ret_{h}") is not None)
    n_matured["clean15_126"] = sum(
        1 for r in rows if r.get("terminal_state_clean15_126") is not None)
    n_matured["clean8_21"] = sum(
        1 for r in rows if r.get("terminal_state_clean8_21") is not None)

    def _both_params(subset: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "n": len(subset),
            "clean15_126": _win_split(subset, "terminal_state_clean15_126"),
            "clean8_21": _win_split(subset, "terminal_state_clean8_21"),
        }

    summary = {
        "schema": SUMMARY_SCHEMA,
        "is_context_only": True,
        "display_only": True,
        "authority_tier": "display",
        "generated_asof": asof,
        "generated_utc": pd.Timestamp.now("UTC").isoformat(),
        "spec": "research/PROPHET_STAGE_FUSION_PREREG.md",
        "accrual_disclaimer": ACCRUAL_DISCLAIMER,
        "n_entries": n_entries,
        "n_tagged": n_tagged,
        "n_stageable": len(n_stageable),
        "n_matured": n_matured,
        "integrity_projection": {
            "raw_rows": projection.raw_count,
            "revision_rows": projection.revision_count,
            "effective_rows": len(rows),
            "quarantined_excluded": len(projection.quarantined_ids),
            "quarantined_ids": sorted(projection.quarantined_ids),
            "clock_mismatch_excluded": len(projection.clock_mismatch_ids),
            "clock_mismatch_ids": sorted(projection.clock_mismatch_ids),
            "authority_error": projection.authority_error,
            "basis": (
                "append-only shadow revisions overlay immutable raw PIT tags; "
                "canonical Prophet clocks and current quarantine are applied before "
                "grading, every summary split, and median_tilt"
            ),
        },
        # R0-C: whether an earnings-call source exists on THIS host at summarize time.
        # Disclosure only — nothing below reads it.
        "ec_source": psi.resolve_ec_source(),
        "split": {
            "stage2": _both_params(stage2),
            "rest": _both_params(rest),
            "fresh_stage2": _both_params(fresh_stage2),
            "positive_ec": _both_params(pos_ec),
        },
        # PSQ-TILT W1 §4: the median-fwd126 measurement the hold-leash self-demotes on.
        "median_tilt": _median_tilt(rows),
        "note": (
            "The Stage-2-vs-rest / fresh-Stage-2 / positive-EC outcome split on ACTUAL "
            "Prophet entries. win = CLEAN_LIFTOFF (same ruler as the backtest). win_rate "
            "is null until an entry matures — nulls printed, not hidden. This layer is "
            "context/measurement only: it NEVER gates, ranks, or alters any Prophet "
            "decision (the fusion win-rate-gate is killed per DO_NOT_REBUILD)."
        ),
    }

    d = _shadow_dir(data_root)
    d.mkdir(parents=True, exist_ok=True)
    p = summary_path(data_root)
    fd, tmp = tempfile.mkstemp(dir=str(d), prefix=".summary.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return summary
