"""engine/cycle_pattern/imce_prospective.py — IMCE A5B registered prospective forward capture.

Append-only, decision-time observation ledger for the registered
``rf.cycle_pattern.imce_phase_v0`` / ``imce_sync_v0`` trial families
(registered_contract_hash ``05b43f9119fd1fd357d3994bd652abbc3cdff3d8``, A4
registration, PR #6244). After activation, a qualifying DHI/PHM/KBH/TOL
earnings event produces ONE immutable decision-time packet capturing:

  * ``M_t`` — the ``order_softness`` mechanism-local state, constructed
    EXACTLY per ``research/imce/IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md``
    (sign-only per-issuer lookup table §2, ≥2-contributor pooling floor §3.1,
    4/4→cohort / 2-3→named_subset / <2→NOT_RECONSTRUCTABLE label rule).
  * ``R_t`` — a PIT-safe price-technical leg (MACD histogram classic
    12/26/9 over the biweekly close series), frozen at the event's own
    decision cutoff, never at nightly build time.
  * ``C_t`` — rights-safe owner-source macro context (Treasury CMT under
    GO_LIMITED; PMMS/FRED/ALFRED/NAR are held/excluded, never persisted).

THIS DATASET IS NOT CANONICAL EVENT/DOCUMENT/ACCOUNTING TRUTH. It is the
registered experiment's own DERIVED evidence store — a bounded, dataset-local
ledger, not a new generic forward-log or trial-ledger primitive. It contains
ZERO outcome fields (no forward return, drawdown, Brier, hit-rate, or
p-value of any kind) — this module can only ever compute decision-time
state, never a graded result. Authority is context_only everywhere; nothing
here ranks, sizes, gates, or feeds Prophet/Radar/screener/recommendation.

Primitive-inspection verdict (re-derived, not merely restated, from reading
each module's own docstring/keying logic before writing this one):

  * ``engine/cycle_forward_log.py`` — keep-FIRST per ``(date, id)``. Wrong
    keying for a per-event, per-decision-cutoff observation ledger (a single
    calendar date can carry more than one issuer's decision cutoff, and this
    dataset's identity is event-keyed, not date-keyed) — NOT reused.
  * ``engine/trial_ledger.py`` — a multiple-testing REGISTRATION registry
    (dedup-by-config-hash trial count for the Deflated Sharpe gate), not an
    observation ledger of any kind — NOT reused.
  * ``engine/neuralweb/market_memory_forward_store.py`` — explicitly a
    "temp-only immutable ledger for SYNTHETIC Market Memory forward
    contracts" with "no default root, environment-variable lookup, command
    line, scheduler, service, API, or production call site" — excluded by
    its own docstring from any production use — NOT reused.

Row kinds (append-only JSONL, one JSON object per line, never rewritten):

  * ``activation``  — exactly one row; stamps ``activation_started_at`` the
    first time a production nightly run succeeds; idempotent (never
    re-stamped on a later run).
  * ``observation``  — one immutable decision-time packet per
    ``(event_id, decision_cutoff)`` key (first-observation-wins; an
    exact-duplicate rerun is a no-op, never a second row).
  * ``correction``   — a linked supersession record referencing the
    superseded ``observation_id`` when a source correction (a new workspace
    revision for the same event) is observed. The original packet is NEVER
    rewritten.

Activation law (strict reading, frozen by the commissioning directive): no
source event whose ``source_available_at`` predates ``activation_started_at``
may enter the prospective cohort. This binds CONTRIBUTING issuer states too,
not only the triggering event — a pre-activation snapshot may never supply a
pooled-cohort contributor state; it is recorded as a typed absence
(``activation_law: "pre_activation_excluded"``) instead.

Reconstruction/temp mode: every write function accepts an explicit
non-default output path and REFUSES to touch the production path in that
mode (``reconstruction=True``); the inverse is also enforced — a
non-reconstruction (production) call may ONLY target the production path.
Tests therefore cannot physically append to the production ledger.
"""
from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Identity / schema constants
# ---------------------------------------------------------------------------

SCHEMA = "imce.prospective_observation.v1"
REGISTERED_CONTRACT_HASH = "05b43f9119fd1fd357d3994bd652abbc3cdff3d8"
CONSTRUCTION_DOC = "research/imce/IMCE_A4P_ORDER_SOFTNESS_STATE_CONSTRUCTION_V1.md"

#: Prospective nominal pooled roster — the PROSPECTIVE arm retains the genuine
#: four-issuer cohort basis (construction doc §1a/§3.1); LEN is excluded
#: (no cancellation denominator, ever) and NVR is held out as its own
#: stratum, never pooled (contract §2 NVR bullet, AG13) — unchanged by A5B.
ROSTER: tuple[str, ...] = ("DHI", "PHM", "KBH", "TOL")

ROW_KIND_ACTIVATION = "activation"
ROW_KIND_OBSERVATION = "observation"
ROW_KIND_CORRECTION = "correction"
ROW_KINDS = frozenset({ROW_KIND_ACTIVATION, ROW_KIND_OBSERVATION, ROW_KIND_CORRECTION})

AUTHORITY = "context_only"
PROPHET_FLAGS = {
    "may_rank": False,
    "may_size": False,
    "may_gate": False,
    "prophet_authority": False,
}

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
PRODUCTION_PATH = _REPO_ROOT / "data" / "cycle_pattern" / "imce_prospective_observation_v1.jsonl"

# ---------------------------------------------------------------------------
# M_t — the six frozen source facts (construction doc §1/§1b)
# ---------------------------------------------------------------------------

FACT_IDS: tuple[str, ...] = (
    "fact_net_orders_current",
    "fact_net_orders_prior_year",
    "fact_cancellation_rate_current",
    "fact_cancellation_rate_prior_year",
    "fact_cancellation_rate_denominator",
)
TOL_SENSITIVITY_FACT_ID = "fact_cancellation_rate_beginning_backlog_sensitivity"

# Sign-only per-issuer lookup table (construction doc §2). Any combination
# not present here (either sign missing) resolves to NOT_RECONSTRUCTABLE in
# order_softness_state() below — never fitted, never a magnitude threshold.
_ORDER_SOFTNESS_TABLE: dict[tuple[str, str], str] = {
    ("+", "-"): "TIGHTENING", ("+", "0"): "TIGHTENING",
    ("-", "+"): "SOFTENING", ("-", "0"): "SOFTENING",
    ("+", "+"): "MIXED", ("-", "-"): "MIXED",
    ("0", "+"): "MIXED", ("0", "-"): "MIXED", ("0", "0"): "MIXED",
}

# ---------------------------------------------------------------------------
# Outcome-field blacklist (frozen spec item 9) — no schema, present or future,
# may carry any of these tokens (or their listed synonyms) anywhere.
# ---------------------------------------------------------------------------

FORBIDDEN_OUTCOME_TOKENS: frozenset[str] = frozenset({
    "forward_return", "fwd_return", "return_fwd", "excess_return", "realized_return",
    "drawdown", "max_drawdown", "mdd", "maxdd",
    "brier", "brier_score",
    "hit_rate", "hitrate", "win_rate", "winrate",
    "p_value", "pvalue", "p_val",
    "sharpe", "sharpe_ratio", "information_ratio", "alpha",
})


class ProspectiveLedgerError(RuntimeError):
    """A write violated the reconstruction/production path law or the
    outcome-field blacklist."""


def _now_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_iso(value: object) -> datetime:
    """Public: parse an ISO-8601 timestamp (any offset, 'Z' or otherwise)
    into a UTC-aware datetime. The nightly builder uses this directly rather
    than a private module member."""
    text = str(value or "").strip()
    if not text:
        raise ProspectiveLedgerError(f"not a timestamp: {value!r}")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


# Back-compat internal alias (module-local use only).
_parse_iso = parse_iso


# ---------------------------------------------------------------------------
# Outcome-field blacklist enforcement
# ---------------------------------------------------------------------------

def _walk_forbidden(obj: Any, path: str = "$") -> str | None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            key_norm = str(k).strip().lower()
            if key_norm in FORBIDDEN_OUTCOME_TOKENS:
                return f"{path}.{k}"
            hit = _walk_forbidden(v, f"{path}.{k}")
            if hit:
                return hit
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hit = _walk_forbidden(item, f"{path}[{i}]")
            if hit:
                return hit
    return None


def assert_no_outcome_fields(packet: dict) -> None:
    """Raise ProspectiveLedgerError if any forbidden outcome token appears
    anywhere in *packet* (recursively, key-name match only)."""
    hit = _walk_forbidden(packet)
    if hit:
        raise ProspectiveLedgerError(
            f"forbidden outcome field present in packet at {hit} — IMCE A5B "
            f"computes decision-time state only, never a graded outcome"
        )


# ---------------------------------------------------------------------------
# Path law — reconstruction mode may never touch the production path; a
# production (non-reconstruction) write may ONLY target the production path.
# ---------------------------------------------------------------------------

def _validate_write_path(path: Path, *, reconstruction: bool) -> Path:
    resolved = Path(path).resolve()
    prod = PRODUCTION_PATH.resolve()
    if reconstruction:
        if resolved == prod:
            raise ProspectiveLedgerError(
                "reconstruction mode may never write the production prospective "
                f"ledger path ({PRODUCTION_PATH}); pass an explicit temp path"
            )
    else:
        if resolved != prod:
            raise ProspectiveLedgerError(
                "a production (non-reconstruction) write must target the "
                f"production path ({PRODUCTION_PATH}); pass reconstruction=True "
                "with an explicit temp path for a test/reconstruction write"
            )
    return resolved


def _append_line(row: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def load_rows(path: Path | None = None) -> list[dict]:
    """Return every row (all kinds) from the ledger, in file order.

    Returns [] if the file does not exist yet (first-publish, not a failure).
    """
    p = Path(path) if path is not None else PRODUCTION_PATH
    if not p.exists():
        return []
    rows: list[dict] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                log.warning("imce_prospective_observation_v1.jsonl line %d parse error: %s", lineno, exc)
    return rows


def activation_row(path: Path | None = None) -> dict | None:
    for row in load_rows(path):
        if row.get("row_kind") == ROW_KIND_ACTIVATION:
            return row
    return None


def _observation_rows(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("row_kind") == ROW_KIND_OBSERVATION]


def find_observation(event_id: str, decision_cutoff: str, path: Path | None = None) -> dict | None:
    for row in _observation_rows(load_rows(path)):
        if row.get("trigger", {}).get("event_id") == event_id and row.get("trigger", {}).get("decision_cutoff") == decision_cutoff:
            return row
    return None


def find_observation_by_id(observation_id: str, path: Path | None = None) -> dict | None:
    for row in _observation_rows(load_rows(path)):
        if row.get("observation_id") == observation_id:
            return row
    return None


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def ensure_activation(
    *, path: Path | None = None, reconstruction: bool = False, now: datetime | None = None,
) -> dict:
    """Idempotent: returns the existing activation row unchanged if one
    already exists (NEVER re-stamped); otherwise appends and returns a new
    one stamped with *now* (default: current UTC time)."""
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    existing = activation_row(target)
    if existing is not None:
        return existing
    ts = _now_iso(now)
    row = {
        "schema": SCHEMA,
        "row_kind": ROW_KIND_ACTIVATION,
        "activation_started_at": ts,
        "registered_contract_hash": REGISTERED_CONTRACT_HASH,
        "roster": list(ROSTER),
        "created_at": ts,
    }
    _append_line(row, target)
    return row


# ---------------------------------------------------------------------------
# Observation identity (content-address, LOCAL to this dataset)
# ---------------------------------------------------------------------------

def compute_observation_id(packet: dict, *, prefix: str = "obs") -> str:
    body = {k: v for k, v in packet.items() if k not in ("observation_id", "created_at", "row_kind", "schema")}
    canon = json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    digest = sha256(canon.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:32]}"


def append_observation(
    packet: dict, *, path: Path | None = None, reconstruction: bool = False,
) -> tuple[dict, bool]:
    """Append one observation packet. First-observation-wins per
    ``(event_id, decision_cutoff)``: an exact-duplicate rerun is a no-op
    (returns the existing row, appended=False), never a second line.

    *packet* must already carry a ``trigger`` block with ``event_id`` and
    ``decision_cutoff``. Raises ProspectiveLedgerError if any forbidden
    outcome field is present anywhere in the packet.
    """
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    assert_no_outcome_fields(packet)
    trigger = packet.get("trigger") or {}
    event_id = trigger.get("event_id")
    decision_cutoff = trigger.get("decision_cutoff")
    if not event_id or not decision_cutoff:
        raise ProspectiveLedgerError("packet.trigger.event_id and .decision_cutoff are required")

    dup = find_observation(event_id, decision_cutoff, target)
    if dup is not None:
        return dup, False

    row = dict(packet)
    row["schema"] = SCHEMA
    row["row_kind"] = ROW_KIND_OBSERVATION
    row["registered_contract_hash"] = REGISTERED_CONTRACT_HASH
    row.setdefault("authority", AUTHORITY)
    row.setdefault("prophet_flags", dict(PROPHET_FLAGS))
    row.setdefault("created_at", _now_iso())
    row["observation_id"] = compute_observation_id(row)
    _append_line(row, target)
    return row, True


def append_correction(
    *,
    superseded_observation_id: str,
    corrected_packet: dict,
    reason: str,
    path: Path | None = None,
    reconstruction: bool = False,
) -> dict:
    """Append a correction row linked to *superseded_observation_id*.

    The original observation row is NEVER rewritten — this only appends a
    new, separately-identified row. Raises if the superseded id is not a
    known observation in this ledger, or if the corrected packet carries a
    forbidden outcome field.
    """
    target = _validate_write_path(Path(path) if path is not None else PRODUCTION_PATH, reconstruction=reconstruction)
    assert_no_outcome_fields(corrected_packet)
    if find_observation_by_id(superseded_observation_id, target) is None:
        raise ProspectiveLedgerError(
            f"correction references unknown observation_id {superseded_observation_id!r} "
            f"in {target}"
        )
    row = dict(corrected_packet)
    row["schema"] = SCHEMA
    row["row_kind"] = ROW_KIND_CORRECTION
    row["registered_contract_hash"] = REGISTERED_CONTRACT_HASH
    row["supersedes_observation_id"] = superseded_observation_id
    row["correction_reason"] = str(reason or "").strip()
    row.setdefault("authority", AUTHORITY)
    row.setdefault("prophet_flags", dict(PROPHET_FLAGS))
    row.setdefault("created_at", _now_iso())
    row["observation_id"] = compute_observation_id(row)
    _append_line(row, target)
    return row


# ---------------------------------------------------------------------------
# M_t — per-issuer state + pooling (construction doc §2/§3.1, verbatim)
# ---------------------------------------------------------------------------

def _fact_by_id(workspace: dict, fact_id: str) -> dict | None:
    for f in workspace.get("facts") or []:
        if isinstance(f, dict) and f.get("fact_id") == fact_id:
            return f
    return None


def _fact_value(fact: dict | None) -> tuple[Any, str | None]:
    """(value, absence_reason). absence_reason is None iff a value is present."""
    if fact is None:
        return None, "fact_absent_from_workspace"
    if fact.get("typed_absence"):
        absence = fact["typed_absence"]
        reason = absence.get("reason") if isinstance(absence, dict) else "typed_absence"
        return None, str(reason or "typed_absence")
    return fact.get("value"), None


def yoy_sign(current: object, prior: object) -> str | None:
    """Sign of (current - prior): '+' / '-' / '0', or None if either input
    is missing/non-numeric. Never a magnitude threshold — sign only."""
    if current is None or prior is None:
        return None
    try:
        delta = float(current) - float(prior)
    except (TypeError, ValueError):
        return None
    if delta > 0:
        return "+"
    if delta < 0:
        return "-"
    return "0"


def order_softness_state(d_orders: str | None, d_cancel: str | None) -> str:
    """Construction doc §2 lookup table, verbatim. NOT_RECONSTRUCTABLE
    whenever either sign is missing."""
    if d_orders is None or d_cancel is None:
        return "NOT_RECONSTRUCTABLE"
    return _ORDER_SOFTNESS_TABLE.get((d_orders, d_cancel), "NOT_RECONSTRUCTABLE")


def _tol_sensitivity(workspace: dict) -> dict:
    """Construction doc §1b mandatory diagnostic. A5A's source plane
    extracts only the CURRENT-period beginning-quarter-backlog sensitivity
    fact (no prior-year comparator under that basis) — so the sensitivity
    YoY sign is honestly NOT_RECONSTRUCTABLE pending that extraction; this
    is a source-coverage gap, never an invented or imputed comparator."""
    fact = _fact_by_id(workspace, TOL_SENSITIVITY_FACT_ID)
    value, absence_reason = _fact_value(fact)
    basis = fact.get("basis") if isinstance(fact, dict) else None
    return {
        "fact_id": TOL_SENSITIVITY_FACT_ID,
        "current_value": value,
        "current_absence_reason": absence_reason,
        "basis": basis,
        "prior_year_value": None,
        "prior_year_absence_reason": (
            "not_extracted_by_source_plane — A5A's issuer_profiles.py extracts only "
            "the current-period beginning-quarter-backlog sensitivity fact; no "
            "prior-year comparator under this basis exists in the workspace, so a "
            "sensitivity-basis YoY sign is never imputed"
        ),
        "d_cancel_sensitivity": None,
        "order_softness_sensitivity_basis": "NOT_RECONSTRUCTABLE",
        "agreement_with_primary_basis": None,
    }


def per_issuer_state(
    ticker: str,
    workspace: dict | None,
    *,
    activation_started_at: str,
    as_of_cutoff: str,
) -> dict:
    """Pure. *workspace* is the most recent published event_workspace for
    *ticker* known at/before *as_of_cutoff* (or None if no such snapshot
    exists at all). Enforces the activation law and the PIT-knowability
    bound (a contributor's own source_available_at may never be later than
    the triggering event's own decision cutoff)."""
    base = {"ticker": ticker, "facts": {}, "d_orders": None, "d_cancel": None,
            "order_softness": "NOT_RECONSTRUCTABLE", "as_of_event_id": None,
            "as_of_decision_cutoff": None}

    if workspace is None:
        return {**base, "contributor_eligible": False, "activation_law": "no_snapshot_available"}

    src_avail = (workspace.get("lifecycle") or {}).get("source_available_at")
    event_id = workspace.get("event_id")
    if not src_avail:
        return {**base, "contributor_eligible": False, "activation_law": "no_source_available_at",
                "as_of_event_id": event_id}

    src_dt = _parse_iso(src_avail)
    if src_dt < _parse_iso(activation_started_at):
        return {**base, "contributor_eligible": False, "activation_law": "pre_activation_excluded",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail}
    if src_dt > _parse_iso(as_of_cutoff):
        return {**base, "contributor_eligible": False, "activation_law": "future_relative_to_trigger_excluded",
                "as_of_event_id": event_id, "as_of_decision_cutoff": src_avail}

    facts_out: dict[str, dict] = {}
    for fid in FACT_IDS:
        value, absence_reason = _fact_value(_fact_by_id(workspace, fid))
        facts_out[fid] = {"value": value, "absence_reason": absence_reason}

    d_orders = yoy_sign(
        facts_out["fact_net_orders_current"]["value"],
        facts_out["fact_net_orders_prior_year"]["value"],
    )
    d_cancel = yoy_sign(
        facts_out["fact_cancellation_rate_current"]["value"],
        facts_out["fact_cancellation_rate_prior_year"]["value"],
    )
    state = order_softness_state(d_orders, d_cancel)

    result = {
        "ticker": ticker,
        "contributor_eligible": True,
        "activation_law": "post_activation",
        "as_of_event_id": event_id,
        "as_of_decision_cutoff": src_avail,
        "facts": facts_out,
        "d_orders": d_orders,
        "d_cancel": d_cancel,
        "order_softness": state,
    }
    if ticker.upper() == "TOL":
        result["sensitivity"] = _tol_sensitivity(workspace)
    return result


def pool_cohort_state(per_issuer: dict[str, dict]) -> dict:
    """Construction doc §3.1, verbatim: ≥2-contributor floor, modal state
    with any tie (two-way or three-way) typed MIXED, label by contributor
    count (4/4 cohort, 2-3 named_subset + exact names, <2 NOT_RECONSTRUCTABLE)."""
    contributing = {
        t: v["order_softness"] for t, v in per_issuer.items()
        if v.get("order_softness") != "NOT_RECONSTRUCTABLE"
    }
    n = len(contributing)
    if n < 2:
        return {
            "label": "NOT_RECONSTRUCTABLE", "pooled_state": "NOT_RECONSTRUCTABLE",
            "named_subset_basis": None, "contributors": sorted(contributing), "n_contributors": n,
        }
    counts = Counter(contributing.values())
    top = max(counts.values())
    modal = sorted(s for s, c in counts.items() if c == top)
    pooled_state = "MIXED" if len(modal) > 1 else modal[0]
    label = "cohort" if n == len(ROSTER) else "named_subset"
    return {
        "label": label,
        "pooled_state": pooled_state,
        "named_subset_basis": sorted(contributing) if label == "named_subset" else None,
        "contributors": sorted(contributing),
        "n_contributors": n,
    }


# ---------------------------------------------------------------------------
# R_t — PIT-safe price-technical leg (frozen spec item 7)
# ---------------------------------------------------------------------------

#: House price-plane precedence (engine/stock_identity/plane.py §1). NO
#: fallback across planes: a symbol not on its assigned plane is a typed
#: absence, never a second store lookup.
PRICE_CONSTRUCTION_VERSION = "imce_prospective.r_t.macd_hist_12_26_9.biweekly_epoch2000.v1"


def _bar_admissible(bar_date, decision_cutoff: datetime) -> bool:
    """A daily bar is fully knowable once its own session has CLOSED —
    reuses the house DST-aware session-close computation
    (engine.session_digest.session_window_et); never a hand-rolled UTC
    offset constant."""
    from engine.session_digest import session_window_et  # local import: keeps this module's import graph flat

    d = bar_date.date() if hasattr(bar_date, "date") else bar_date
    try:
        _, close_et = session_window_et(d)
    except Exception:  # noqa: BLE001 — an unparseable/non-session date is simply inadmissible
        return False
    return close_et.astimezone(timezone.utc) <= decision_cutoff


def price_leg_for_ticker(ticker: str, decision_cutoff: datetime, *, repo_root: Path | None = None) -> dict:
    """One R_t leg: PIT-bounded MACD-histogram sign on the biweekly close
    series, or a typed absence. NO fallback across price stores — the
    ticker's single house-canonical plane (or none) is the only read."""
    import pandas as pd

    from engine.htf_durability import _biweekly_close
    from engine.stock_identity.plane import PLANE_DIRS, primary_planes
    from engine.technicals import macd_hist

    root = Path(repo_root) if repo_root is not None else _REPO_ROOT
    leg: dict[str, Any] = {
        "ticker": ticker, "price_plane_id": None, "adjustment_basis": None,
        "last_admissible_bar": None, "construction_version": PRICE_CONSTRUCTION_VERSION,
        "sign": None, "macd_hist_value": None, "typed_absence": None,
    }

    planes = primary_planes(root)
    plane_id = planes.get(ticker.upper())
    if plane_id is None:
        leg["typed_absence"] = {
            "reason": "no_price_plane_holds_ticker",
            "detail": f"{ticker} is not present on any house price plane ({', '.join(PLANE_DIRS)})",
        }
        return leg

    leg["price_plane_id"] = plane_id
    leg["adjustment_basis"] = (
        f"as published by plane {plane_id!r} (engine/stock_identity/plane.py §1 precedence); "
        "no separate total-return-adjustment claim made beyond the plane's own convention"
    )

    path = root / PLANE_DIRS[plane_id] / f"{ticker.upper()}.parquet"
    if not path.exists():
        leg["typed_absence"] = {"reason": "plane_file_missing", "detail": str(path)}
        return leg

    try:
        df = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        leg["typed_absence"] = {"reason": "plane_file_unreadable", "detail": str(exc)}
        return leg

    if "close" not in df.columns or df.empty:
        leg["typed_absence"] = {"reason": "plane_file_no_close_column_or_empty", "detail": str(path)}
        return leg

    cutoff = decision_cutoff if decision_cutoff.tzinfo else decision_cutoff.replace(tzinfo=timezone.utc)
    admissible_mask = [_bar_admissible(ts, cutoff) for ts in df.index]
    if not any(admissible_mask):
        leg["typed_absence"] = {
            "reason": "no_admissible_bar_before_cutoff",
            "detail": f"earliest bar {df.index.min()} postdates decision_cutoff {decision_cutoff.isoformat()}",
        }
        return leg

    bounded_close = df.loc[admissible_mask, "close"].astype(float)
    leg["last_admissible_bar"] = str(bounded_close.index.max())

    biweekly = _biweekly_close(bounded_close)
    hist = macd_hist(biweekly).dropna()
    if hist.empty:
        leg["typed_absence"] = {
            "reason": "insufficient_biweekly_history_for_macd",
            "detail": f"{len(bounded_close)} admissible daily bars produced {len(biweekly)} biweekly bars",
        }
        return leg

    last_val = float(hist.iloc[-1])
    leg["macd_hist_value"] = last_val
    leg["sign"] = "+" if last_val > 0 else ("-" if last_val < 0 else "0")
    return leg


# ---------------------------------------------------------------------------
# C_t — rights-safe owner-source macro context (frozen spec item 8)
# ---------------------------------------------------------------------------

def context_legs(*, now: datetime | None = None) -> dict:
    """Every leg records source/value-or-typed-absence/pit_class/timestamps.
    No FRED/ALFRED (not even a fetch). No NAR series. PMMS is HELD — never
    persisted. Treasury CMT is persistable under GO_LIMITED but this wave
    ships no in-repo first-party Treasury Daily Par Yield Curve fetcher/
    store — captured as an honest typed absence, never an invented value.
    Every captured field the registered contract does not name as a model
    feature is context_only — capture never grants statistical use."""
    obs_ts = _now_iso(now)
    return {
        "treasury_cmt": {
            "source": "US Treasury Daily Treasury Par Yield Curve",
            "rights_disposition": "GO_LIMITED",
            "value": None,
            "typed_absence": {
                "reason": "no_in_repo_first_party_fetcher_or_store",
                "detail": (
                    "GO_LIMITED authorizes persistence of Treasury-published Daily "
                    "Treasury Par Yield Curve values with first-party provenance, "
                    "retrieval timestamp, and methodology reference, but no such "
                    "fetcher/store exists in this repo yet — building one is new "
                    "collector infrastructure outside this wave's scope; captured "
                    "honestly as absent rather than invented"
                ),
            },
            "pit_class": None,
            "source_timestamp": None,
            "observation_timestamp": obs_ts,
            "context_only": True,
        },
        "pmms": {
            "status": "held", "persisted": False, "value": None,
            "reason": "pit_pure_archive_but_redistribution_commercial_exploitation_terms_ambiguous",
            "observation_timestamp": obs_ts,
        },
        "fred_alfred": {"status": "excluded_categorically", "fetched": False, "observation_timestamp": obs_ts},
        "nar_series": {"may_be_stored": False, "value": None, "observation_timestamp": obs_ts},
    }


# ---------------------------------------------------------------------------
# Packet assembly
# ---------------------------------------------------------------------------

def build_observation_packet(
    *,
    trigger_ticker: str,
    trigger_workspace: dict,
    issuer_workspaces: dict[str, dict | None],
    activation_started_at: str,
    now: datetime | None = None,
) -> dict:
    """Assemble one full decision-time observation packet.

    *issuer_workspaces* maps EVERY roster ticker (including the trigger) to
    the most recent published event_workspace known at/before the trigger's
    own decision cutoff (or None if no snapshot is available for that
    issuer yet) — the caller (the nightly builder) owns candidate discovery
    and PIT-bounded selection; this function is pure given that mapping.
    """
    lifecycle = trigger_workspace.get("lifecycle") or {}
    decision_cutoff = lifecycle.get("source_available_at")
    if not decision_cutoff:
        raise ProspectiveLedgerError("trigger_workspace.lifecycle.source_available_at is required")

    issuer = trigger_workspace.get("issuer") or {}
    listings = issuer.get("listings") or []
    primary_listing = next((l for l in listings if l.get("is_primary")), (listings[0] if listings else {}))

    sources = trigger_workspace.get("sources") or []
    release_source = next((s for s in sources if s.get("kind") == "issuer_release"), {})
    filing_key = release_source.get("filing_key") or {}

    per_issuer: dict[str, dict] = {}
    for ticker in ROSTER:
        ws = issuer_workspaces.get(ticker)
        per_issuer[ticker] = per_issuer_state(
            ticker, ws, activation_started_at=activation_started_at, as_of_cutoff=decision_cutoff,
        )

    m_t = {
        "construction_doc": CONSTRUCTION_DOC,
        "roster": list(ROSTER),
        "per_issuer": per_issuer,
        **pool_cohort_state(per_issuer),
    }

    r_t = {
        "construction_version": PRICE_CONSTRUCTION_VERSION,
        "legs": {
            ticker: price_leg_for_ticker(ticker, _parse_iso(decision_cutoff))
            for ticker in ROSTER
        },
    }

    packet = {
        "trigger": {
            "ticker": trigger_ticker,
            "company_id": issuer.get("company_id"),
            "security_id": primary_listing.get("security_id"),
            "event_id": trigger_workspace.get("event_id"),
            "fiscal_period": trigger_workspace.get("fiscal_period"),
            "event_workspace_generation_id": trigger_workspace.get("generation_id"),
            "source_document_sha256": release_source.get("source_sha256"),
            "source_accession": filing_key.get("accession"),
            "decision_cutoff": decision_cutoff,
        },
        "activation_started_at": activation_started_at,
        "m_t": m_t,
        "r_t": r_t,
        "c_t": context_legs(now=now),
        "authority": AUTHORITY,
        "prophet_flags": dict(PROPHET_FLAGS),
    }
    return packet
