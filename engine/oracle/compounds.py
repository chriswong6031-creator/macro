"""Oracle Research Factory — Compound registry loader + rule evaluator.

W-B1 CAUSALITY FIREWALL
-----------------------
The grammar here is intentionally SMALL.  The evaluator joins ALL features
as-of day t (strictly <= t) and returns entry dates per node.  This
construction makes it structurally impossible to introduce look-ahead — a
cheap model (ChatGPT/Haiku) contributes a compound by writing a declarative
spec, never code, and the correctness guarantee rides in the evaluator, not
the spec author.

RULE GRAMMAR (exhaustive)
--------------------------
A rule is one of:

  Panel condition (tests a column value on the entry node at day t):
    {"col": <str>, "op": <op>, "value": <float>}
    {"col": <str>, "op": <op>, "value_col": <str>}   # compare to another column

  Episode event (tests whether an episode matching criteria fired on or before t):
    {"episode_event": {
        "direction": "in" | "out",
        "tier": "onset" | "confirmed" | "undeniable",
        "complex_scope": "same" | "opposite" | "any",
        "within_sessions": <int>,
        "min_count": <int>     # optional, default 1
    }}

  Logical combinator:
    {"all": [<rule>, ...]}    # AND
    {"any": [<rule>, ...]}    # OR

  Sequence (v1.2.0+):
    {"sequence": {
        "first": <rule>,            # any v1 rule incl. episode_event/all/any
        "then": <rule>,             # evaluated at day t
        "within_sessions": <int>    # lookback window N; first must fire in
                                    # [t-N, t-1] (strictly before t)
    }}
    CAUSALITY LAW: first fires strictly BEFORE t (never on t itself).
    NESTING LAW: sequence-inside-sequence is REJECTED at validation.
    Both legs are causal on the node's own rows.

Operators (op):
  gt, lt, ge, le — numeric comparison
  crossed_above, crossed_below — today's value crossed vs yesterday's value;
      uses value_col if present, otherwise a scalar value

Top-level compound fields:
  cooldown_sessions: <int>  — after a fire on a node, suppress that node's
      fires for the next N sessions (deterministic left-to-right scan).
      Applied inside get_entry_dates so all consumers (screens, gauntlets,
      ledgers) inherit it.

Unknown column → compound gets status "blocked_missing_column"; evaluator
never raises — always returns an empty Series.

Unknown operator → ValueError raised loudly at rule parse time, not silently
swallowed.  The grammar is the contract; extending it requires editing this
file explicitly.

GRAMMAR VERSION
---------------
GRAMMAR_VERSION must be bumped on ANY change to evaluator semantics.
The version is included in the params-hash used for trial_ledger AND
live_ledger keep-first keys so that a semantics change forces a new row
instead of silently inheriting results from the old semantics.

Version history:
  1.0.0  — initial grammar (6 comparators + episode_event; breadth counted by
            row-count, not distinct nodes)
  1.1.0  — W-B4 fix: breadth semantics corrected to nunique (distinct nodes)
            in _eval_episode_event; old keep-first rows under 1.0.0 stand as
            counted historical trials — append, never rewrite.
  1.2.0  — W3 grammar: sequence rule (causal ordered pair with strict-before
            lookback) + cooldown_sessions top-level suppression.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Grammar version — bump on ANY change to evaluator semantics.
#: Included in the params-hash for trial_ledger AND live_ledger keep-first
#: keys so that a semantics change forces a new row rather than silently
#: inheriting results from the prior evaluator.
#:
#: Version history:
#:   1.0.0 — initial release (breadth counted by row-count, not distinct nodes)
#:   1.1.0 — breadth semantics corrected to nunique (distinct nodes) in
#:            _eval_episode_event; this was the A2 distinct-node semantics fix.
#:   1.2.0 — W3: sequence rule (causal ordered pair, strict-before lookback) +
#:            cooldown_sessions top-level suppression in get_entry_dates.
GRAMMAR_VERSION: str = "1.2.0"

#: Valid operators.  Additions require an explicit code change (the firewall).
VALID_OPS: frozenset[str] = frozenset(
    ["gt", "lt", "ge", "le", "crossed_above", "crossed_below"]
)

#: Compound status transitions
STATUS_EXPLORATORY = "exploratory"
STATUS_SCREENED = "screened"
STATUS_ACCRUING = "accruing"
STATUS_PROMOTED = "promoted"
STATUS_REFUTED = "refuted"
STATUS_BLOCKED = "blocked_missing_column"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def load_registry(compounds_dir: Path) -> list[dict]:
    """Load all compounds from registry.jsonl.  Returns list of dicts."""
    p = compounds_dir / "registry.jsonl"
    if not p.exists():
        log.warning("registry.jsonl not found at %s", p)
        return []
    rows = []
    for lineno, line in enumerate(p.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as e:
            log.error("registry.jsonl line %d parse error: %s", lineno, e)
    return rows


def load_compound(compounds_dir: Path, compound_id: str) -> dict | None:
    """Load a single compound by id from the registry."""
    for row in load_registry(compounds_dir):
        if row.get("id") == compound_id:
            return row
    return None


def save_registry(compounds_dir: Path, rows: list[dict]) -> None:
    """Overwrite registry.jsonl with the given list."""
    compounds_dir.mkdir(parents=True, exist_ok=True)
    p = compounds_dir / "registry.jsonl"
    lines = [json.dumps(row, separators=(",", ":"), default=str) for row in rows]
    p.write_text("\n".join(lines) + "\n")


def update_compound_status(
    compounds_dir: Path,
    compound_id: str,
    new_status: str,
    **extra_fields: Any,
) -> None:
    """Update a compound's status (and any extra fields) in-place."""
    rows = load_registry(compounds_dir)
    for row in rows:
        if row.get("id") == compound_id:
            row["status"] = new_status
            row.update(extra_fields)
            break
    save_registry(compounds_dir, rows)


# ---------------------------------------------------------------------------
# Rule grammar validation
# ---------------------------------------------------------------------------

def _validate_op(op: str) -> None:
    if op not in VALID_OPS:
        raise ValueError(
            f"Unknown op '{op}'. Valid ops: {sorted(VALID_OPS)}. "
            "The grammar is the causality firewall — add a new op to VALID_OPS "
            "only with an explicit code review."
        )


def validate_rule(rule: dict, _inside_sequence: bool = False) -> None:
    """Validate a rule dict against the grammar.  Raises ValueError on unknown ops.

    _inside_sequence: internal flag — callers should NOT pass this.
    Sequence-inside-sequence is REJECTED loudly (v1.2 nesting law).
    """
    if "all" in rule:
        for sub in rule["all"]:
            validate_rule(sub, _inside_sequence=_inside_sequence)
    elif "any" in rule:
        for sub in rule["any"]:
            validate_rule(sub, _inside_sequence=_inside_sequence)
    elif "sequence" in rule:
        if _inside_sequence:
            raise ValueError(
                "sequence-inside-sequence is REJECTED (v1.2 nesting law). "
                "The 'first' and 'then' legs of a sequence must be v1 rules "
                "(col/episode_event/all/any), never another sequence."
            )
        seq = rule["sequence"]
        for k in ("first", "then", "within_sessions"):
            if k not in seq:
                raise ValueError(f"sequence missing required key '{k}'")
        if not isinstance(seq["within_sessions"], int) or seq["within_sessions"] < 1:
            raise ValueError(
                f"sequence.within_sessions must be a positive integer, "
                f"got: {seq['within_sessions']!r}"
            )
        # Validate legs with _inside_sequence=True so nesting is caught
        validate_rule(seq["first"], _inside_sequence=True)
        validate_rule(seq["then"], _inside_sequence=True)
    elif "episode_event" in rule:
        ev = rule["episode_event"]
        for k in ("direction", "tier", "complex_scope", "within_sessions"):
            if k not in ev:
                raise ValueError(f"episode_event missing required key '{k}'")
    elif "col" in rule:
        _validate_op(rule["op"])
    else:
        raise ValueError(f"Unrecognised rule shape: {rule}")


# ---------------------------------------------------------------------------
# Complex membership helpers
# ---------------------------------------------------------------------------

def _build_complex_index(rotation_groups: dict) -> dict[str, str]:
    """Return a mapping node -> complex_id.

    rotation_groups is the parsed rotation_groups.json dict.
    Also incorporates COMPLEX_ETF_MAP from engine.oracle.graph so that tier-s
    ETF nodes (XLK, XLV, etc.) are correctly mapped to their complexes.
    """
    node_to_complex: dict[str, str] = {}
    for c in rotation_groups.get("complexes", []):
        cid = c["id"]
        for member in c.get("members", []):
            node_to_complex[member] = cid

    # Also add tier-s ETF nodes via COMPLEX_ETF_MAP (ETFs not in rotation_groups.members)
    try:
        from engine.oracle.graph import COMPLEX_ETF_MAP
        for complex_id, etf_list in COMPLEX_ETF_MAP.items():
            for etf in etf_list:
                if etf not in node_to_complex:
                    node_to_complex[etf] = complex_id
    except ImportError:
        pass  # graph module unavailable — degrade gracefully

    return node_to_complex


def _build_complex_risk_sign(rotation_groups: dict) -> dict[str, str]:
    """Return complex_id -> risk_sign."""
    return {c["id"]: c.get("risk_sign", "mixed")
            for c in rotation_groups.get("complexes", [])}


def _get_opposite_complex_ids(
    node_complex_id: str,
    complex_risk_sign: dict[str, str],
) -> list[str]:
    """Return complex ids with opposite risk_sign to node_complex_id."""
    my_sign = complex_risk_sign.get(node_complex_id, "mixed")
    if my_sign == "mixed":
        # mixed has no clear opposite — return all non-mixed
        return [cid for cid, sign in complex_risk_sign.items()
                if sign != "mixed" and cid != node_complex_id]
    opposite_sign = "risk_off" if my_sign == "risk_on" else "risk_on"
    return [cid for cid, sign in complex_risk_sign.items()
            if sign == opposite_sign]


# ---------------------------------------------------------------------------
# Panel condition evaluator
# ---------------------------------------------------------------------------

def _eval_panel_condition(
    rule: dict,
    panel_node: pd.DataFrame,
    missing_cols: set[str],
) -> pd.Series:
    """Evaluate a single panel condition rule over a node's panel slice.

    Returns a boolean Series indexed by date.
    Unknown column → adds to missing_cols, returns all-False.
    """
    col = rule["col"]
    op = rule["op"]

    # Check both col and value_col existence
    required_cols = [col]
    if "value_col" in rule:
        required_cols.append(rule["value_col"])

    for c in required_cols:
        if c not in panel_node.columns:
            missing_cols.add(c)
            return pd.Series(False, index=panel_node.index)

    series = panel_node[col]

    if "value_col" in rule:
        ref = panel_node[rule["value_col"]]
    else:
        ref = float(rule["value"])

    if op == "gt":
        return series > ref
    elif op == "lt":
        return series < ref
    elif op == "ge":
        return series >= ref
    elif op == "le":
        return series <= ref
    elif op == "crossed_above":
        # Today > ref AND yesterday <= ref (strictly, as-of t)
        if isinstance(ref, float):
            ref_s = pd.Series(ref, index=series.index)
        else:
            ref_s = ref
        prev = series.shift(1)
        prev_ref = ref_s.shift(1)
        return (series > ref_s) & (prev <= prev_ref)
    elif op == "crossed_below":
        if isinstance(ref, float):
            ref_s = pd.Series(ref, index=series.index)
        else:
            ref_s = ref
        prev = series.shift(1)
        prev_ref = ref_s.shift(1)
        return (series < ref_s) & (prev >= prev_ref)
    else:
        # Should never reach here after validate_rule, but be safe
        raise ValueError(f"Unknown op: {op}")


# ---------------------------------------------------------------------------
# Episode event evaluator
# ---------------------------------------------------------------------------

def _eval_episode_event(
    rule_ev: dict,
    node: str,
    date: pd.Timestamp,
    episodes_df: pd.DataFrame,
    node_to_complex: dict[str, str],
    complex_risk_sign: dict[str, str],
    within_sessions: int,
    min_count: int,
    panel_dates: pd.DatetimeIndex,
) -> bool:
    """Return True if the episode_event condition is satisfied AS-OF `date`.

    Causal: only episodes with onset_date <= date are considered.
    """
    direction = rule_ev["direction"]
    tier = rule_ev["tier"]
    scope = rule_ev.get("complex_scope", "any")

    # Determine the lookback window: `within_sessions` TRADING days before date
    # We use panel_dates to count sessions causally
    pos = panel_dates.searchsorted(date, side="right") - 1
    start_pos = max(0, pos - within_sessions)
    window_start = panel_dates[start_pos] if start_pos >= 0 else panel_dates[0]

    # Filter episodes: direction, tier, and onset in window (strictly <= date)
    mask = (
        (episodes_df["direction"] == direction)
        & (episodes_df["onset_date"] >= window_start)
        & (episodes_df["onset_date"] <= date)
    )

    # Tier filtering: "onset" means any episode (onset is the earliest tier);
    # "confirmed" means onset_date is not enough — we need confirmed_date <= date;
    # "undeniable" means undeniable_date <= date.
    if tier == "confirmed":
        if "confirmed_date" in episodes_df.columns:
            mask &= episodes_df["confirmed_date"].notna() & (episodes_df["confirmed_date"] <= date)
    elif tier == "undeniable":
        if "undeniable_date" in episodes_df.columns:
            mask &= episodes_df["undeniable_date"].notna() & (episodes_df["undeniable_date"] <= date)
    # "onset" tier: no additional filter needed

    candidate_eps = episodes_df[mask]

    if candidate_eps.empty:
        return False

    # Scope filtering
    if scope == "any":
        matching = candidate_eps
    elif scope == "same":
        # Same complex as the entry node
        my_complex = node_to_complex.get(node)
        if my_complex is None:
            # Node not in any complex — can't satisfy same-complex scope
            return False
        matching = candidate_eps[
            candidate_eps["node"].map(node_to_complex).eq(my_complex)
        ]
    elif scope == "opposite":
        # Opposite complex: different risk_sign per rotation_groups risk_sign
        my_complex = node_to_complex.get(node)
        if my_complex is None:
            return False
        opp_complexes = set(_get_opposite_complex_ids(my_complex, complex_risk_sign))
        if not opp_complexes:
            return False
        matching = candidate_eps[
            candidate_eps["node"].map(node_to_complex).isin(opp_complexes)
        ]
    else:
        matching = candidate_eps

    # BREADTH = DISTINCT NODES (review fix on #1285): an episode COUNT would let
    # one re-firing subsector satisfy a "cascade breadth >= 3" gate — the library's
    # A2 semantics are distinct same-complex nodes.
    return int(matching["node"].nunique()) >= min_count


# ---------------------------------------------------------------------------
# Sequence evaluator helper
# ---------------------------------------------------------------------------

def _eval_sequence(
    seq: dict,
    node: str,
    panel_node: pd.DataFrame,
    episodes_df: pd.DataFrame,
    node_to_complex: dict[str, str],
    complex_risk_sign: dict[str, str],
    missing_cols: set[str],
) -> pd.Series:
    """Evaluate a sequence rule over all dates in panel_node.

    Fires at t iff:
      - `then` is true at t, AND
      - `first` was true on at least one day s in [t-N, t-1]  (strictly before t)

    CAUSALITY LAW: first lookback never includes t.

    Returns a boolean Series indexed by date.
    """
    panel_dates = panel_node.index
    within_sessions = int(seq["within_sessions"])

    # Evaluate both legs over the full panel
    first_mask = evaluate_rule(
        seq["first"], node, panel_node, episodes_df,
        node_to_complex, complex_risk_sign, missing_cols,
    )
    then_mask = evaluate_rule(
        seq["then"], node, panel_node, episodes_df,
        node_to_complex, complex_risk_sign, missing_cols,
    )

    result = pd.Series(False, index=panel_dates)

    # For each day t where then_mask is True, check if first fired in [t-N, t-1]
    then_true_positions = then_mask.values.nonzero()[0]
    first_values = first_mask.values  # numpy array for fast slicing

    for pos in then_true_positions:
        # Lookback window: positions [pos-within_sessions, pos-1] (strictly before pos)
        lo = max(0, pos - within_sessions)
        hi = pos  # exclusive — does NOT include pos (strict before)
        if lo >= hi:
            # No positions strictly before t in the window (t is the first row)
            continue
        if first_values[lo:hi].any():
            result.iloc[pos] = True

    return result


# ---------------------------------------------------------------------------
# Main rule evaluator
# ---------------------------------------------------------------------------

def evaluate_rule(
    rule: dict,
    node: str,
    panel_node: pd.DataFrame,
    episodes_df: pd.DataFrame,
    node_to_complex: dict[str, str],
    complex_risk_sign: dict[str, str],
    missing_cols: set[str],
) -> pd.Series:
    """Evaluate a rule over all dates in panel_node for a given node.

    Returns a boolean Series indexed by date.
    Causal: all joins use only data as-of t.
    """
    panel_dates = panel_node.index

    if "all" in rule:
        result = pd.Series(True, index=panel_dates)
        for sub in rule["all"]:
            result &= evaluate_rule(
                sub, node, panel_node, episodes_df,
                node_to_complex, complex_risk_sign, missing_cols,
            )
        return result

    elif "any" in rule:
        result = pd.Series(False, index=panel_dates)
        for sub in rule["any"]:
            result |= evaluate_rule(
                sub, node, panel_node, episodes_df,
                node_to_complex, complex_risk_sign, missing_cols,
            )
        return result

    elif "sequence" in rule:
        return _eval_sequence(
            rule["sequence"], node, panel_node, episodes_df,
            node_to_complex, complex_risk_sign, missing_cols,
        )

    elif "episode_event" in rule:
        ev = rule["episode_event"]
        within_sessions = int(ev.get("within_sessions", 15))
        min_count = int(ev.get("min_count", 1))

        # Vectorised over dates: compute day-by-day
        # This is O(dates × episodes) but episodes_df is small (hundreds)
        results = pd.Series(False, index=panel_dates)
        for i, date in enumerate(panel_dates):
            results.iloc[i] = _eval_episode_event(
                ev, node, date, episodes_df,
                node_to_complex, complex_risk_sign,
                within_sessions, min_count, panel_dates,
            )
        return results

    elif "col" in rule:
        return _eval_panel_condition(rule, panel_node, missing_cols)

    else:
        # Unknown shape — treat as blocked
        log.error("evaluate_rule: unrecognised rule shape: %s", rule)
        return pd.Series(False, index=panel_dates)


# ---------------------------------------------------------------------------
# Entry date computation
# ---------------------------------------------------------------------------

def get_entry_dates(
    compound: dict,
    panel: pd.DataFrame,
    episodes_df: pd.DataFrame,
    rotation_groups: dict,
) -> dict[str, pd.DatetimeIndex]:
    """Compute entry dates for each node in the compound's universe.

    Entry is triggered on day t; position taken at NEXT daily close (t+1).
    Causal by construction — rule evaluation is strictly as-of t.

    Returns dict node -> DatetimeIndex of entry trigger dates.
    Returns {} on any rule validation failure or missing column block.

    If any required column is absent, returns {} and the compound should be
    marked blocked_missing_column by the caller.
    """
    node_to_complex = _build_complex_index(rotation_groups)
    complex_risk_sign = _build_complex_risk_sign(rotation_groups)

    # Validate rule grammar up front
    entry_rule = compound.get("entry_rule")
    condition_rule = compound.get("condition_rule")

    try:
        if entry_rule:
            validate_rule(entry_rule)
        if condition_rule:
            validate_rule(condition_rule)
    except ValueError as e:
        log.error("Compound %s rule validation error: %s", compound.get("id"), e)
        raise

    universe = compound.get("universe", {})
    tier = universe.get("tier", "s")
    nodes_filter = universe.get("nodes")  # optional explicit node list

    # Filter panel to the compound's universe tier
    # panel has MultiIndex (node, date); tier is embedded in tier_tag if present
    # For now we rely on the caller passing the right tier's panel.
    # Get all nodes in this panel.
    if panel.empty:
        return {}

    all_nodes = panel.index.get_level_values("node").unique().tolist()
    if nodes_filter:
        all_nodes = [n for n in all_nodes if n in nodes_filter]

    result: dict[str, pd.DatetimeIndex] = {}

    for node in all_nodes:
        try:
            node_panel = panel.xs(node, level="node")
        except KeyError:
            continue

        if node_panel.empty:
            continue

        missing_cols: set[str] = set()

        # Evaluate entry rule
        if entry_rule:
            entry_mask = evaluate_rule(
                entry_rule, node, node_panel, episodes_df,
                node_to_complex, complex_risk_sign, missing_cols,
            )
        else:
            entry_mask = pd.Series(True, index=node_panel.index)

        # Evaluate condition rule (applied as additional AND filter)
        if condition_rule:
            cond_mask = evaluate_rule(
                condition_rule, node, node_panel, episodes_df,
                node_to_complex, complex_risk_sign, missing_cols,
            )
            entry_mask = entry_mask & cond_mask

        if missing_cols:
            # Signal blocked — caller should mark compound blocked_missing_column
            log.warning(
                "Compound %s node %s: missing columns %s — blocked",
                compound.get("id"), node, missing_cols,
            )
            # Return special sentinel
            return {"__blocked__": missing_cols}

        entry_dates = node_panel.index[entry_mask]
        if len(entry_dates) > 0:
            result[node] = entry_dates

    # Apply cooldown_sessions: after a kept fire on a node, suppress that
    # node's fires for the next N sessions.  Deterministic left-to-right scan.
    cooldown_n = compound.get("cooldown_sessions")
    if cooldown_n and isinstance(cooldown_n, int) and cooldown_n > 0:
        # Build per-node trading-session index from the panel so cooldown counts
        # actual panel sessions, not Mon–Fri calendar business days (which include
        # market holidays that are NOT trading sessions — fixing bdate_range bug).
        node_date_indices: dict[str, pd.DatetimeIndex] = {}
        for _node in result:
            if _node == "__blocked__":
                continue
            try:
                node_date_indices[_node] = panel.xs(_node, level="node").index
            except KeyError:
                node_date_indices[_node] = pd.DatetimeIndex([])
        result = _apply_cooldown(result, cooldown_n, node_date_indices)

    return result


def _apply_cooldown(
    entries: dict[str, pd.DatetimeIndex],
    cooldown_sessions: int,
    node_date_indices: dict[str, pd.DatetimeIndex],
) -> dict[str, pd.DatetimeIndex]:
    """Apply per-node cooldown suppression to an entry-dates dict.

    After a kept fire on a node, suppresses that node's subsequent fires
    within cooldown_sessions TRADING SESSIONS (positional gap within the node's
    own panel date index), left-to-right.

    node_date_indices: mapping node -> sorted DatetimeIndex of all trading dates
    for that node in the panel.  Used to count actual sessions rather than
    Mon–Fri calendar business days (which include market holidays).

    Returns a new dict with the same keys but filtered DatetimeIndex values.
    """
    result: dict[str, pd.DatetimeIndex] = {}
    for node, dates in entries.items():
        if node == "__blocked__":
            result[node] = dates
            continue
        sorted_dates = dates.sort_values()
        kept: list[pd.Timestamp] = []
        last_fire: pd.Timestamp | None = None
        last_fire_pos: int = -1
        panel_dates = node_date_indices.get(node, pd.DatetimeIndex([]))
        for d in sorted_dates:
            if last_fire is None:
                kept.append(d)
                last_fire = d
                last_fire_pos = int(panel_dates.searchsorted(d, side="left"))
            else:
                # Count sessions between last_fire and d using positional gap
                # within the node's own panel (actual trading sessions, no holidays).
                d_pos = int(panel_dates.searchsorted(d, side="left"))
                sessions_gap = d_pos - last_fire_pos
                if sessions_gap >= cooldown_sessions:
                    kept.append(d)
                    last_fire = d
                    last_fire_pos = d_pos
                # else: suppressed
        if kept:
            result[node] = pd.DatetimeIndex(kept)
    return result


# ---------------------------------------------------------------------------
# Derived column builder (for D1's tlt_vol columns)
# ---------------------------------------------------------------------------

def augment_panel_with_derived(panel: pd.DataFrame) -> pd.DataFrame:
    """Add compound-required derived columns not present in the base panel.

    Currently adds:
      tlt_vol_20d      — 20-day rolling std of tlt_ret_10d
      tlt_vol_60d_mean — 60-day rolling mean of tlt_vol_20d

    These are CAUSAL (rolling windows look only backward).
    Operates in-place and returns the panel.
    """
    if "tlt_ret_10d" not in panel.columns:
        return panel

    # Compute per-node (multi-index aware)
    if isinstance(panel.index, pd.MultiIndex):
        nodes = panel.index.get_level_values("node").unique()
        vol_20d_parts = []
        vol_60d_mean_parts = []
        for node in nodes:
            s = panel.loc[node, "tlt_ret_10d"] if node in panel.index.get_level_values("node") else None
            if s is None or (hasattr(s, "empty") and s.empty):
                continue
            v20 = s.rolling(20, min_periods=10).std()
            v60 = v20.rolling(60, min_periods=30).mean()
            vol_20d_parts.append(pd.Series(v20.values, index=pd.MultiIndex.from_tuples(
                [(node, d) for d in v20.index], names=["node", "date"])))
            vol_60d_mean_parts.append(pd.Series(v60.values, index=pd.MultiIndex.from_tuples(
                [(node, d) for d in v60.index], names=["node", "date"])))

        if vol_20d_parts:
            panel["tlt_vol_20d"] = pd.concat(vol_20d_parts)
        if vol_60d_mean_parts:
            panel["tlt_vol_60d_mean"] = pd.concat(vol_60d_mean_parts)
    else:
        # Flat index (single node slice)
        s = panel["tlt_ret_10d"]
        panel["tlt_vol_20d"] = s.rolling(20, min_periods=10).std()
        panel["tlt_vol_60d_mean"] = panel["tlt_vol_20d"].rolling(60, min_periods=30).mean()

    return panel
