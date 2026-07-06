"""OTA W7 — Qualitative Filter Registry + PIT Stamping + Accrual.

Single-writer module (oracle_nightly.py Step 17).  No LLM anywhere in this path.
All stamps are deterministic predicates over committed PIT artifacts.

Laws enforced:
  - Lane law: Q1/Q2/Q3 field validation at load time (loud error for unknown lane)
  - Budget: max 5 active filters per quarter; adding a 6th requires retiring one
  - Retire-to-add: status flip only, never delete; registry is append-only
  - Keep-first: stamps written once per (window_key, filter_id); never overwritten
  - Null-honest: missing source artifact → value=null, loud WARNING, never false
  - "validated" is banned from accrual output (loud AssertionError if present)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("oracle_qual_filters")

# ─── Constants ──────────────────────────────────────────────────────────────

REGISTRY_PATH = "oracle/qual_filters/registry.jsonl"
STAMPS_PATH   = "oracle/qual_filter_stamps.jsonl"
ACCRUAL_PATH  = "oracle/qual_filter_accrual.json"

VALID_LANES   = {"Q1", "Q2", "Q3"}
MAX_ACTIVE    = 5          # budget cap per quarter
_REQUIRED_FIELDS = {"id", "lane", "description_en", "description_zh",
                    "source_artifact", "predicate", "registered_at",
                    "registered_by", "status", "fdr_family"}
_BANNED_IN_ACCRUAL = ("validated",)

# ─── Registry ────────────────────────────────────────────────────────────────

def load_registry(data_dir: Path) -> list[dict]:
    """Load and validate registry.jsonl.  Loud on schema violations.

    Returns only rows that pass validation — malformed rows are annotated
    but do not abort the pipeline (loud-error pattern).
    """
    reg_path = data_dir / REGISTRY_PATH
    if not reg_path.exists():
        log.warning("qual_filters: registry not found at %s", reg_path)
        return []

    rows: list[dict] = []
    for i, line in enumerate(reg_path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as e:
            _annotate(f"qual_filters: registry line {i} is not valid JSON: {e}")
            continue

        # Lane law
        lane = row.get("lane", "")
        if lane not in VALID_LANES:
            _annotate(
                f"qual_filters: registry row {i} id={row.get('id')!r} "
                f"has unknown lane {lane!r} — VALID_LANES={VALID_LANES}"
            )
            continue

        # Required fields
        missing = _REQUIRED_FIELDS - set(row)
        if missing:
            _annotate(
                f"qual_filters: registry row {i} id={row.get('id')!r} "
                f"missing required fields {sorted(missing)}"
            )
            continue

        rows.append(row)

    # Budget check (active only)
    active = [r for r in rows if r.get("status") == "accruing"]
    if len(active) > MAX_ACTIVE:
        _annotate(
            f"qual_filters: {len(active)} active filters exceed budget cap "
            f"of {MAX_ACTIVE}; retire one before adding another"
        )
        # Still return all rows — the nightly should not silently drop them;
        # operator action is required.

    return rows


def active_filters(registry: list[dict]) -> list[dict]:
    """Return only accruing rows."""
    return [r for r in registry if r.get("status") == "accruing"]


# ─── Stamp evaluators ────────────────────────────────────────────────────────

def _eval_q2_riskoff(
    filt: dict, fire_date: str, data_dir: Path
) -> bool | None:
    """F-Q2-RISKOFF: market_state verdict != RISK_OFF at window open."""
    # source_artifact is repo-relative; data_dir is the data/ subdirectory
    art_path = data_dir.parent / filt["source_artifact"]
    if not art_path.exists():
        log.warning(
            "qual_filters: F-Q2-RISKOFF source_artifact missing: %s — stamp=null",
            art_path,
        )
        return None

    try:
        ms = json.loads(art_path.read_text())
        verdict = ms.get("verdict")
        if verdict is None:
            log.warning("qual_filters: F-Q2-RISKOFF: verdict field absent — stamp=null")
            return None
        pred = filt["predicate"]
        # op="ne" value="RISK_OFF"
        if pred.get("op") == "ne":
            return verdict != pred.get("value")
        _annotate(f"qual_filters: F-Q2-RISKOFF unknown op {pred.get('op')!r}")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("qual_filters: F-Q2-RISKOFF eval error: %s — stamp=null", exc)
        return None


def _eval_q2_highvix(
    filt: dict, node: str, fire_date: str, data_dir: Path
) -> bool | None:
    """F-Q2-HIGHVIX: panel_s vix_pctile >= 0.6 for the armed node at fire_date."""
    # source_artifact is repo-relative; data_dir is the data/ subdirectory
    art_path = data_dir.parent / filt["source_artifact"]
    if not art_path.exists():
        log.warning(
            "qual_filters: F-Q2-HIGHVIX source_artifact missing: %s — stamp=null",
            art_path,
        )
        return None

    try:
        import pandas as _pd
        panel = _pd.read_parquet(art_path)
        col = filt["predicate"]["field"]  # "vix_pctile"
        if col not in panel.columns:
            log.warning("qual_filters: F-Q2-HIGHVIX column %r absent — stamp=null", col)
            return None

        # Look up the node + fire_date row
        try:
            node_panel = panel.xs(node, level="node")
        except KeyError:
            log.warning(
                "qual_filters: F-Q2-HIGHVIX node %r not in panel — stamp=null", node
            )
            return None

        fire_ts = _pd.Timestamp(fire_date)
        # Use the most recent row on or before fire_date (PIT)
        node_sorted = node_panel.sort_index()
        available = node_sorted[node_sorted.index <= fire_ts]
        if available.empty:
            log.warning(
                "qual_filters: F-Q2-HIGHVIX no panel row for node=%s fire_date=%s — stamp=null",
                node, fire_date,
            )
            return None

        val = available[col].iloc[-1]
        if val is None or (hasattr(val, "__class__") and str(type(val).__name__) == "float"
                           and str(val) == "nan"):
            log.warning(
                "qual_filters: F-Q2-HIGHVIX vix_pctile is NaN for node=%s fire_date=%s — stamp=null",
                node, fire_date,
            )
            return None

        pred = filt["predicate"]
        threshold = float(pred.get("value", 0.6))
        if pred.get("op") == "ge":
            return float(val) >= threshold
        _annotate(f"qual_filters: F-Q2-HIGHVIX unknown op {pred.get('op')!r}")
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("qual_filters: F-Q2-HIGHVIX eval error: %s — stamp=null", exc)
        return None


def _eval_q3_tape(
    filt: dict, node: str, fire_date: str, data_dir: Path,
    all_dates_list: list[str],
) -> bool | None:
    """F-Q3-TAPE: operator tape touch on armed node within +/-3 sessions.

    True if any operator_tape row (non-schema_note) has:
      - node in row.nodes[]
      - row.pit_stamp within ±3 trading sessions of fire_date
      - row.direction == "in" (armed context is a potential recovery, not out)

    Returns None when the source artifact is missing (null-honest).
    """
    # source_artifact is repo-relative; data_dir is the data/ subdirectory
    tape_path = data_dir.parent / filt["source_artifact"]
    if not tape_path.exists():
        log.warning(
            "qual_filters: F-Q3-TAPE source_artifact missing: %s — stamp=null",
            tape_path,
        )
        return None

    try:
        within = int(filt["predicate"].get("within_sessions", 3))

        # Locate fire_date position in the session calendar
        date_to_pos: dict[str, int] = {d: i for i, d in enumerate(all_dates_list)}
        fire_pos = date_to_pos.get(fire_date)
        if fire_pos is None:
            log.warning(
                "qual_filters: F-Q3-TAPE fire_date %s not in session calendar — stamp=null",
                fire_date,
            )
            return None

        lo_pos = max(0, fire_pos - within)
        hi_pos = min(len(all_dates_list) - 1, fire_pos + within)
        lo_date = all_dates_list[lo_pos]
        hi_date = all_dates_list[hi_pos]

        for line in tape_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Skip schema_note header row
            if row.get("type") == "schema_note":
                continue

            # Node match
            row_nodes = row.get("nodes") or []
            if node not in row_nodes:
                continue

            # Direction match — tape "in" = operator flagged this sector as
            # a potential entry context (matches armed window's recovery framing)
            if row.get("direction") != "in":
                continue

            # pit_stamp within window (date string prefix compare is safe for ISO)
            pit = (row.get("pit_stamp") or "")[:10]  # date portion only
            if lo_date <= pit <= hi_date:
                return True

        return False

    except Exception as exc:  # noqa: BLE001
        log.warning("qual_filters: F-Q3-TAPE eval error: %s — stamp=null", exc)
        return None


# ─── Per-filter dispatcher ───────────────────────────────────────────────────

def evaluate_filter(
    filt: dict,
    node: str,
    fire_date: str,
    data_dir: Path,
    all_dates_list: list[str],
) -> bool | None:
    """Dispatch to the correct evaluator by filter id.

    Unknown ids return null with a loud warning (forward-compatible).
    """
    fid = filt.get("id", "")
    if fid == "F-Q2-RISKOFF":
        return _eval_q2_riskoff(filt, fire_date, data_dir)
    elif fid == "F-Q2-HIGHVIX":
        return _eval_q2_highvix(filt, node, fire_date, data_dir)
    elif fid == "F-Q3-TAPE":
        return _eval_q3_tape(filt, node, fire_date, data_dir, all_dates_list)
    else:
        log.warning(
            "qual_filters: no evaluator for filter id %r — stamp=null "
            "(add an evaluator branch in engine/oracle/qual_filters.py)",
            fid,
        )
        return None


# ─── Stamping ─────────────────────────────────────────────────────────────────

def stamp_window_open(
    armed: list[dict],
    panel_asof: str,
    data_dir: Path,
    all_dates_list: list[str],
    dry_run: bool = False,
) -> int:
    """Write qual_filter_stamps.jsonl rows for each window_open × active filter.

    Keep-first: (window_key::filter_id) never overwritten.
    Returns count of new stamp rows written.

    Called immediately after the turn desk window_open rows are known (inside
    the same nightly Step 17) so the PIT is guaranteed: we read the committed
    artifacts for tonight's run.
    """
    registry = load_registry(data_dir)
    filters  = active_filters(registry)
    if not filters:
        log.info("qual_filters: no active filters — nothing to stamp")
        return 0

    stamps_path = data_dir / STAMPS_PATH
    stamps_path.parent.mkdir(parents=True, exist_ok=True)

    # Load existing stamp keys (keep-first)
    existing_keys: set[str] = set()
    if stamps_path.exists():
        for line in stamps_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                k = r.get("key")
                if k:
                    existing_keys.add(k)
            except json.JSONDecodeError:
                pass

    now_utc = datetime.now(timezone.utc).isoformat()
    new_rows: list[dict] = []

    for armed_entry in armed:
        node = armed_entry["node"]
        for fire_date in armed_entry.get("fire_dates", []):
            window_key = f"{node}::a15::{fire_date}"
            for filt in filters:
                fid   = filt["id"]
                skey  = f"{window_key}::{fid}"
                if skey in existing_keys:
                    continue  # keep-first

                value = evaluate_filter(
                    filt, node, fire_date, data_dir, all_dates_list
                )
                if value is None:
                    log.warning(
                        "qual_filters: stamp NULL — window_key=%s filter_id=%s "
                        "(source unavailable or eval error)",
                        window_key, fid,
                    )

                new_rows.append({
                    "key":         skey,
                    "window_key":  window_key,
                    "filter_id":   fid,
                    "value":       value,
                    "stamped_asof": panel_asof,
                    "registered_at": now_utc,
                })
                existing_keys.add(skey)

    if new_rows and not dry_run:
        with open(stamps_path, "a") as fh:
            for row in new_rows:
                fh.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    log.info("qual_filters: %d new stamp rows (dry_run=%s)", len(new_rows), dry_run)
    return len(new_rows)


# ─── Accrual report ──────────────────────────────────────────────────────────

def build_accrual_report(data_dir: Path) -> dict:
    """Compute per-filter conditional WR21 (true vs false) on matured windows.

    Reads:
      - data/oracle/qual_filter_stamps.jsonl  (stamps)
      - data/oracle/turn_desk_ledger.jsonl    (graded window_open rows)

    Returns DESCRIPTIVE accrual dict.  "validated" is banned in the output.
    """
    stamps_path  = data_dir / STAMPS_PATH
    ledger_path  = data_dir / "oracle" / "turn_desk_ledger.jsonl"

    # ── Load graded window_open rows from turn_desk_ledger ──────────────────
    graded_windows: dict[str, dict] = {}  # window_key -> ledger row
    if ledger_path.exists():
        for line in ledger_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("kind") == "window_open" and row.get("outcome_mature") is True:
                wkey = row.get("key")
                if wkey:
                    graded_windows[wkey] = row

    # ── Load stamps ──────────────────────────────────────────────────────────
    stamps_by_filter: dict[str, list[dict]] = {}
    if stamps_path.exists():
        for line in stamps_path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            fid = row.get("filter_id")
            if fid:
                stamps_by_filter.setdefault(fid, []).append(row)

    registry = load_registry(data_dir)

    per_filter: dict[str, Any] = {}
    for filt in registry:
        fid = filt["id"]
        stamps = stamps_by_filter.get(fid, [])

        # Join stamps to graded windows
        true_wins: list[float]  = []
        false_wins: list[float] = []

        for stamp in stamps:
            wkey  = stamp.get("window_key")
            value = stamp.get("value")
            if value is None:
                continue  # null-honest: skip nulls in conditional stats
            gw = graded_windows.get(wkey)
            if gw is None:
                continue  # not yet matured

            fwd = gw.get("fwd_ret_21")
            if fwd is None:
                continue  # graded but no return (e.g. member fire vs window_open)

            win = 1 if float(fwd) > 0 else 0
            if value is True:
                true_wins.append(win)
            elif value is False:
                false_wins.append(win)

        def _wr_block(wins: list[float]) -> dict:
            n = len(wins)
            if n == 0:
                return {"n": 0, "wr21": None, "wilson_lb": None, "wilson_ub": None}
            p = sum(wins) / n
            # Wilson score interval (95%)
            z = 1.96
            denom = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denom
            margin = z * (p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5 / denom
            return {
                "n": n,
                "wr21": round(p, 4),
                "wilson_lb": round(max(0.0, center - margin), 4),
                "wilson_ub": round(min(1.0, center + margin), 4),
            }

        n_true = len(true_wins)
        entry = {
            "filter_id":         fid,
            "lane":              filt["lane"],
            "description_en":    filt["description_en"],
            "status":            filt["status"],
            "filter_true":       _wr_block(true_wins),
            "filter_false":      _wr_block(false_wins),
            "note":              (
                "Descriptive conditional WR21: windows where filter was true vs false. "
                "Null stamps excluded. Display-only — no ranking or gating authority."
            ),
        }
        if n_true >= 15:
            entry["re_evaluation_eligible"] = (
                f"re-evaluation eligible (registration ota_qual family; "
                f"n_true={n_true} >= 15)"
            )

        per_filter[fid] = entry

    report = {
        "schema":           "qual_filter_accrual.v1",
        "produced_at":      datetime.now(timezone.utc).isoformat(),
        "n_graded_windows": len(graded_windows),
        "per_filter":       per_filter,
        "note":             (
            "Qualitative filter accrual — DESCRIPTIVE conditional win-rates. "
            "Display-only under OTA W7 hard law: no filter may gate, rank, or "
            "score any surface. Re-evaluation is a Fable/operator event."
        ),
    }

    # Banned-word check — loud AssertionError if "validated" appears
    raw = json.dumps(report)
    for banned in _BANNED_IN_ACCRUAL:
        assert banned not in raw, (
            f"qual_filters: accrual report contains banned word {banned!r} — "
            f"edit the note strings to remove it"
        )

    return report


def write_accrual_report(report: dict, data_dir: Path, dry_run: bool = False) -> None:
    """Write qual_filter_accrual.json."""
    if dry_run:
        log.info("qual_filters: DRY-RUN would write %s", ACCRUAL_PATH)
        return
    out = data_dir / ACCRUAL_PATH
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, separators=(",", ":"), default=str))
    log.info("qual_filters: accrual report written → %s", out)


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _annotate(msg: str) -> None:
    """GitHub Actions ::error:: annotation + log."""
    print(f"::error::{msg}", flush=True)
    log.error(msg)
