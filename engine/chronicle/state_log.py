"""engine.chronicle.state_log — forward-capture ledger + regime-flip
derivation (W0 adapter 5: regime_flip. risk_band lives in adapters.py — B6
correction: it reads the real committed ``data/risk_radar/forward_log.jsonl``
history directly, not this module, see adapters.py's module docstring).

``data/chronicle/state_log.jsonl`` is a FORWARD LEDGER: nightly is the sole
advancer (house law — "nightly is the sole advancer of forward ledgers";
intraday lanes discard writes), same class as every other forward ledger in
this repo (prophet ledger, release_forecast forward ledger, ...). It is NOT
retroactively derivable, so ``--rebuild`` reads it but never deletes or
rewrites it (masterplan §0 gate 1 exemption). The write path
(:func:`append_row_if_new`) is gated on ``COLLECT_LANE=nightly`` (B2 — same
idiom as engine.index_leadership_track._nightly_lane /
engine.mag7_regime._append_cohort_flow_ledger): off-lane calls no-op with an
honest gap note rather than advancing the ledger.

Row shape (chronicle.state_log/v1, one line per nightly capture)::

    {"date": "2026-07-24", "captured_at": "2026-07-25T03:41:12Z",
     "regimes": {"us": {"quad": "Q1", "quad_name": "Goldilocks", "cycle_tag": "mid"},
                 "china": {...}, "hk": {...}, "canada": {...}},
     "risk": {"intl": "strained"}}

``date`` is the SOURCE as-of (M1 — §2.1 requires source-native ts/date, not
ingest time): ``global_regimes["us"]["date"]`` when present (the reference
market throughout this module), falling back to world_state's own
``as_of``/``produced_at``, and only to the wall clock as a last resort so a
row is never left dateless. ``captured_at`` is the separate ingest stamp
(always wall-clock — when this process actually ran). Keying date this way
also fixes a real bug: the nightly can straddle UTC midnight, so comparing
the idempotency guard against the WALL clock could discard a genuine second
capture on the rare night two runs land on the same UTC calendar date; the
guard now compares the row's SOURCE date instead (see
:func:`append_row_if_new`).

Risk field: world_state's ``context_risk`` block carries no stable
categorical label (only continuous stats plus a ``regime_context`` sub-dict
that only duplicates the top-level regime), so no "us" risk key is populated
here: an honest gap, not a fabricated bucket. ``intl_risk`` DOES carry a
stable categorical field, ``em_stress_state`` (observed sample value:
"strained"), captured as ``risk["intl"]`` for informational/diagnostic parity
with world_state (surfaced in the admin Chronicle inspector) — but it is NOT
the risk_band event source; that source is the real committed
``data/risk_radar/forward_log.jsonl`` ledger (adapters.adapt_risk_band),
which — unlike this capture-as-you-go ledger — already has genuine dated
history to derive flips from. ``two_tier_state`` ("contained") is a second
stable label in the same intl_risk block, left uncaptured at W0.

``regime_us_transition`` (the world_state ``regime.transition_state`` label,
e.g. CONFIRMED/TRANSITIONING) is deliberately NOT captured here (m11): it was
written every night but never read by any derivation — a silent no-op field.
W0 models exactly one flip class from this ledger (quad_name changes via
:func:`derive_flip_events`); the confirmed/transitioning sub-state is not
promoted to its own event type. Revisit if a consumer needs it.

Flip derivation: a quad_name change for a market, compared against the LAST
row that actually carried a label for that market (carry-forward — M2: a gap
night where the market is briefly absent, e.g. a cancelled engine run, DEFERS
the comparison instead of resetting it and silently losing the flip), emits a
deterministic ``regime_flip`` event (weight 3). Regime flips accrue
forward-only from the W0 run date (masterplan §0 gate 2) — there is no
historical backfill here; that is W4 git-archaeology.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from . import schema

log = logging.getLogger(__name__)

STATE_LOG_REL = Path("data") / "chronicle" / "state_log.jsonl"

_MARKETS: tuple[str, ...] = ("us", "china", "hk", "canada")


def _nightly_lane() -> bool:
    """COLLECT_LANE gate (B2) — house law: nightly is the sole advancer of
    data/ forward ledgers. Same sentinel + idiom as
    engine.index_leadership_track._nightly_lane / engine.mag7_regime's
    cohort-flow ledger gate; US_LANE accepted as the legacy alias."""
    val = os.environ.get("COLLECT_LANE", "") or os.environ.get("US_LANE", "")
    return val.lower() == "nightly"


def read_state_log(repo: Path) -> list[dict]:
    """Read all existing state_log rows, oldest-first, deduped by date (m6:
    keep the row with the latest captured_at) so a duplicate-date pair — a
    retried nightly, a hand-edited ledger — can never fabricate a spurious
    flip pair when :func:`derive_flip_events` compares consecutive rows.
    Fail-soft: [] on any error."""
    path = repo / STATE_LOG_REL
    if not path.exists():
        return []
    rows: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(row, dict) and row.get("date"):
                rows.append(row)
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.state_log: read failed: %s", exc)
        return []

    by_date: dict[str, dict] = {}
    for row in rows:
        d = str(row.get("date"))
        prev = by_date.get(d)
        if prev is None or str(row.get("captured_at") or "") >= str(prev.get("captured_at") or ""):
            by_date[d] = row
    return sorted(by_date.values(), key=lambda r: str(r.get("date") or ""))


def _row_date(ws: dict, us_date: str | None, now: datetime) -> str:
    """Source-native as-of for tonight's row (M1). Preference order: the US
    market's global_regimes date (the reference market throughout this
    module), then world_state's own as_of/produced_at (whole-snapshot
    fallback), then the wall clock as a last resort so a row is never left
    dateless."""
    if isinstance(us_date, str) and us_date.strip():
        return us_date.strip()[:10]
    for key in ("as_of", "produced_at"):
        v = ws.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:10]
    return now.strftime("%Y-%m-%d")


def capture_row(repo: Path, now: datetime | None = None) -> tuple[dict | None, str | None]:
    """Build tonight's state_log row from data/neuralweb/world_state.json.

    Returns (row, gap_note). row is None when world_state.json is absent or
    unreadable (fail-soft — that night's capture is simply skipped; no
    fabricated row is ever written).
    """
    now = now or datetime.now(timezone.utc)
    ws_rel = Path("data") / "neuralweb" / "world_state.json"
    ws_path = repo / ws_rel
    if not ws_path.exists():
        return None, f"{ws_rel} absent — state_log capture skipped"
    try:
        ws = json.loads(ws_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"{ws_rel} unreadable: {exc}"
    if not isinstance(ws, dict):
        return None, f"{ws_rel} did not parse to a dict"

    global_regimes = ws.get("global_regimes") or {}
    intl_risk = ws.get("intl_risk") or {}

    regimes: dict[str, dict] = {}
    for market in _MARKETS:
        mr = global_regimes.get(market)
        if isinstance(mr, dict) and mr.get("quad"):
            regimes[market] = {
                "quad": mr.get("quad"),
                "quad_name": mr.get("quad_name"),
                "cycle_tag": mr.get("cycle_tag"),
            }

    risk: dict[str, str] = {}
    em_state = intl_risk.get("em_stress_state") if isinstance(intl_risk, dict) else None
    if isinstance(em_state, str) and em_state.strip():
        risk["intl"] = em_state.strip()

    us_mr = global_regimes.get("us")
    us_date = us_mr.get("date") if isinstance(us_mr, dict) and isinstance(us_mr.get("date"), str) else None
    row_date = _row_date(ws, us_date, now)

    row = {
        "date": row_date,
        "captured_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "regimes": regimes,
        "risk": risk,
    }
    return row, None


def append_row_if_new(
    repo: Path, now: datetime | None = None
) -> tuple[bool, str | None, str]:
    """Append tonight's capture row unless one already exists for the SAME
    SOURCE as-of (M1 — not the wall-clock calendar date: a nightly run that
    straddles UTC midnight must not discard a genuine new capture, nor should
    two runs that happen to share a source as-of double-append).

    Gated on COLLECT_LANE=nightly (B2): off-lane calls no-op with an honest
    gap note. Returns ``(appended, gap_note, reason)``.

    ``reason`` (M13) names WHICH no-op happened, because ``appended=False``
    alone is ambiguous in the one place operators actually read it — the
    nightly's ``chronicle_governor:`` line. Two of these outcomes are benign
    and two are defects, and they were previously indistinguishable there:

    * ``appended``        — a row was written.
    * ``duplicate_as_of`` — BENIGN: this source as-of is already captured, so
      there is nothing new to record. Carries no gap note precisely because it
      is not a gap; a run of these just means world_state's as-of has not moved.
    * ``lane_gate``       — DEFECT in a nightly: COLLECT_LANE was not ``nightly``,
      so the forward ledger is not advancing at all.
    * ``no_capture``      — DEFECT: world_state was missing/unreadable (gap note
      carries the detail).
    * ``write_failed``    — DEFECT: the append itself raised.

    Callers must not infer the benign case from ``(False, None)``: that coupling
    is what made the distinction invisible in the first place.
    """
    now = now or datetime.now(timezone.utc)
    if not _nightly_lane():
        return False, "state_log append skipped — COLLECT_LANE != nightly (lane gate)", "lane_gate"

    row, gap = capture_row(repo, now=now)
    if row is None:
        return False, gap, "no_capture"

    existing = read_state_log(repo)
    if any(r.get("date") == row.get("date") for r in existing):
        # idempotent: this source as-of already captured. Deliberately NOT a gap
        # note — nothing is missing, so the manifest must not claim a gap.
        return False, None, "duplicate_as_of"

    path = repo / STATE_LOG_REL
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(row, ensure_ascii=False, separators=(",", ":"))
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        return True, None, "appended"
    except Exception as exc:  # noqa: BLE001
        log.warning("chronicle.state_log: append failed: %s", exc)
        return False, f"state_log append failed: {exc}", "write_failed"


def derive_flip_events(rows: list[dict]) -> list[dict]:
    """Deterministic regime_flip events from state_log rows.

    Each market's label is compared against the LAST row that actually
    carried a label for that market (carry-forward), not strictly the
    immediately-preceding row — so a gap night (market absent, e.g. a
    cancelled engine run) DEFERS the comparison rather than resetting it and
    silently losing the flip (M2). The very first row a market appears in
    never emits (baseline only); rows lacking a date are skipped.
    """
    events: list[dict] = []
    rows = sorted(rows, key=lambda r: str(r.get("date") or ""))

    last_regime: dict[str, dict] = {}
    for cur in rows:
        cur_date = str(cur.get("date") or "")
        if not cur_date:
            continue
        cur_regimes = cur.get("regimes") or {}
        for market in _MARKETS:
            c = cur_regimes.get(market) or {}
            c_name = c.get("quad_name")
            if not c_name:
                continue  # market absent this row (gap night) -- leave last-known untouched
            prev = last_regime.get(market)
            if prev is not None:
                p_name = prev.get("quad_name")
                if p_name and p_name != c_name:
                    source_ref = f"state_log#{cur_date}#regime_{market}"
                    title = f"{market.upper()} regime: {prev.get('quad')} {p_name} → {c.get('quad')} {c_name}"
                    try:
                        events.append(schema.new_event(
                            id=schema.make_id("regime_flip", source_ref, cur_date),
                            ts=f"{cur_date}T00:00:00Z",
                            date=cur_date,
                            source="regime_flip",
                            source_ref=source_ref,
                            kind="state_flip",
                            title=title,
                            facts=[f"{p_name} → {c_name}"],
                            tickers=[],
                            themes=["regime", market],
                            weight_hint=3,
                            links=schema.make_links(),
                        ))
                    except Exception as exc:  # noqa: BLE001
                        log.warning("chronicle.state_log: regime_flip event build failed: %s", exc)
            last_regime[market] = {"quad": c.get("quad"), "quad_name": c_name}

    return events
