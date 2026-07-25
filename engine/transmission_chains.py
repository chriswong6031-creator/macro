"""Transmission CHAINS — the display-only staged-cascade episode tracker (TXI W1).

A LEAF module: it imports nothing from the scoring core (regime/axes/conditions' scored
logic) and nothing in the scoring path imports it — the same discipline as
``rate_inflation_transmission``. It compiles the versioned chain library in
``knowledge/transmission/*.yaml`` (TXI-R1) into deterministic episode trackers and
evaluates their current state from artifacts already on disk: the parquet series store
(``lib.store``) and the ``latest.json`` snapshots that build_transmission / build_forex /
the regime engine write. It emits two artifacts:

  * ``data/transmission/chain_episodes.jsonl`` — an append-only FORWARD LEDGER of state
    transitions (nightly-advanced only; ledger law).
  * ``data/transmission/chain_state.json`` — ``transmission_chains.v1``: the current
    per-chain state, hop confirmations with value receipts, tier, and the W2/W3 fields
    declared now for forward-compatibility (``blast`` filled in W2, ``base_rates`` in W3).

DISCIPLINE — display / LLM-context ONLY, NEVER scored (masterplan §4; DNR row 45 / TXI
Article 1/2). A chain state is a WATCH item with (eventually) printed conditional base
rates; it NEVER emits an alpha score, gates a trade, sizes anything, or escalates an
alert. There is no LLM anywhere in this module — only compiled deterministic detectors
(observable thresholds on collected series) can raise a chain stage; the word "validated"
never appears in emitted text. Every emitted dict carries ``display_only=True``.

FAIL-LOUD AT LOAD, FAIL-OPEN AT RUNTIME: a malformed / schema-violating chain file raises
at ``load_chains()`` (so a bad edit reds CI), but a chain whose file loaded yet cannot be
evaluated (a missing artifact, an unresolvable node) is logged and SKIPPED — it never
crashes the nightly. The runner is additive and never fatal.

The episode STATE MACHINE (TXI-R2):
    dormant -> arming -> propagating(hop k) -> expressed | failed | expired
  * arming            node 0's test is TRUE
  * propagating(k)    hops 1..k confirmed, each within its lag window of the prior confirm
  * expressed         the terminal hop confirmed
  * expired           a hop's lag window closed with its target still false
  * failed            a declared (structured) falsifier fired on the armed episode
Same-``asof`` re-evaluation is IDEMPOTENT: no duplicate ledger line, identical state.
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)

SCHEMA_ID = "transmission_chains.v1"
ROOT = Path(__file__).resolve().parents[1]
_KNOWLEDGE_DIRNAME = ("knowledge", "transmission")

# bilingual state labels (masterplan: keep user-facing strings bilingual-ready)
STATE_LABELS: dict[str, dict[str, str]] = {
    "dormant":     {"en": "Dormant", "zh": "休眠"},
    "arming":      {"en": "Arming", "zh": "触发中"},
    "propagating": {"en": "Propagating", "zh": "传导中"},
    "expressed":   {"en": "Expressed", "zh": "已兑现"},
    "failed":      {"en": "Failed", "zh": "已证伪"},
    "expired":     {"en": "Expired", "zh": "已过期"},
}

_VALID_TIERS = {"hypothesis", "probe", "calibrated"}
_VALID_OPS = {"gt", "gte", "lt", "lte", "eq", "ne", "is_true", "is_false", "in", "in_contains"}
_VALID_METRICS = {"ret", "ret_bp", "ma_slope", "rs", "ratio_ret"}


# --------------------------------------------------------------------------- #
# schema validation (fail-loud at load)
# --------------------------------------------------------------------------- #
class ChainSchemaError(ValueError):
    """A chain YAML violates the TXI-R1 schema — raised at load so CI reds."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise ChainSchemaError(msg)


def _validate_test(t: Any, where: str) -> None:
    """Validate one node/falsifier test dict against the whitelisted grammar."""
    _require(isinstance(t, dict), f"{where}: test must be a dict, got {type(t).__name__}")
    # combinators
    if "all" in t or "any" in t:
        key = "all" if "all" in t else "any"
        _require(isinstance(t[key], list) and t[key], f"{where}: '{key}' must be a non-empty list")
        for i, sub in enumerate(t[key]):
            _validate_test(sub, f"{where}.{key}[{i}]")
        return
    op = t.get("op")
    _require(op in _VALID_OPS, f"{where}: unknown/absent op {op!r} (allowed: {sorted(_VALID_OPS)})")
    is_unary = op in ("is_true", "is_false")
    if not is_unary:
        _require("value" in t, f"{where}: op {op!r} requires a 'value'")
    # a test is EITHER a series metric (store adapter) OR a path lookup (state adapter)
    has_series = "series" in t
    has_path = "path" in t
    _require(has_series ^ has_path, f"{where}: test needs exactly one of 'series' or 'path'")
    if has_series:
        metric = t.get("metric")
        _require(metric in _VALID_METRICS, f"{where}: unknown/absent metric {metric!r} (allowed: {sorted(_VALID_METRICS)})")
        # a 'vs' companion series is ONLY meaningful for rs; a 'ratio' ONLY for ratio_ret.
        # Reject the stray key so a metric-name typo (e.g. metric:ret + ratio:LQD) can't
        # silently compute the wrong thing.
        _require(("vs" in t) == (metric == "rs"),
                 f"{where}: 'vs' is required for metric 'rs' and forbidden otherwise")
        _require(("ratio" in t) == (metric == "ratio_ret"),
                 f"{where}: 'ratio' is required for metric 'ratio_ret' and forbidden otherwise")
        _require("window" in t, f"{where}: series metric requires a 'window'")


def validate_chain(chain: dict, filename: str) -> None:
    """Full structural validation of one loaded chain dict. Raises ChainSchemaError."""
    _require(isinstance(chain, dict), f"{filename}: top-level YAML must be a mapping")
    slug = chain.get("chain")
    _require(isinstance(slug, str) and slug, f"{filename}: 'chain' (slug) required")
    stem = Path(filename).stem
    _require(slug == stem, f"{filename}: 'chain' slug {slug!r} must equal filename stem {stem!r}")
    _require(isinstance(chain.get("rev"), int), f"{filename}: 'rev' must be an int")
    _require(chain.get("tier") in _VALID_TIERS, f"{filename}: 'tier' must be one of {sorted(_VALID_TIERS)}")

    nodes = chain.get("nodes")
    _require(isinstance(nodes, dict) and nodes, f"{filename}: 'nodes' must be a non-empty mapping")
    for nid, node in nodes.items():
        _require(isinstance(node, dict), f"{filename}: node {nid!r} must be a mapping")
        _require(isinstance(node.get("src"), str), f"{filename}: node {nid!r} needs a 'src' adapter")
        _require("test" in node, f"{filename}: node {nid!r} needs a 'test'")
        _validate_test(node["test"], f"{filename}:node[{nid}]")

    hops = chain.get("hops")
    _require(isinstance(hops, list) and hops, f"{filename}: 'hops' must be a non-empty list")
    for i, hop in enumerate(hops):
        _require(isinstance(hop, dict), f"{filename}: hop {i} must be a mapping")
        for k in ("from", "to"):
            _require(hop.get(k) in nodes, f"{filename}: hop {i} '{k}'={hop.get(k)!r} not a declared node")
        lag = hop.get("lag_d")
        _require(isinstance(lag, list) and len(lag) == 2 and all(isinstance(x, (int, float)) for x in lag),
                 f"{filename}: hop {i} 'lag_d' must be [lo, hi] numbers")
        _require(lag[0] <= lag[1], f"{filename}: hop {i} lag_d lo>hi")
    # hops must form the ordered path node0->node1->...: hop k's 'from' == hop k-1's 'to'
    for i in range(1, len(hops)):
        _require(hops[i]["from"] == hops[i - 1]["to"],
                 f"{filename}: hop {i} 'from' must equal hop {i-1} 'to' (chain must be a simple path)")
    node_ids = list(nodes.keys())
    _require(hops[0]["from"] == node_ids[0],
             f"{filename}: hop 0 'from' must be the first declared node {node_ids[0]!r}")

    fals = chain.get("falsifiers", [])
    _require(isinstance(fals, list), f"{filename}: 'falsifiers' must be a list")
    for i, fx in enumerate(fals):
        if isinstance(fx, dict) and "when" in fx:
            _validate_test(fx["when"], f"{filename}:falsifier[{i}].when")
    screens = chain.get("exposure_screens", {})
    _require(isinstance(screens, dict), f"{filename}: 'exposure_screens' must be a mapping")


def load_chains(root: Path | None = None, *, include_killed: bool = False,
                strict: bool = False) -> list[dict]:
    """Load + validate every chain YAML in knowledge/transmission/.

    RUNTIME (default, strict=False): a malformed or schema-violating file is LOGGED and
    SKIPPED — one bad chain edit never crashes the nightly (fail-open, ledger-law safe).
    STRICT (strict=True): the first bad file RAISES ChainSchemaError — the CI validator
    uses this so a bad edit reds the PR. Killed chains (knowledge/transmission/killed/)
    are excluded unless include_killed.
    """
    import yaml
    base = (Path(root) if root else ROOT).joinpath(*_KNOWLEDGE_DIRNAME)
    if not base.exists():
        log.warning("transmission knowledge dir absent: %s", base)
        return []
    out: list[dict] = []
    for path in sorted(base.glob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
            if not isinstance(data, dict):
                raise ChainSchemaError(f"{path.name}: top-level YAML must be a mapping")
            validate_chain(data, path.name)
        except (yaml.YAMLError, ChainSchemaError) as e:
            if strict:
                raise ChainSchemaError(f"{path.name}: {e}") from e
            log.error("skipping malformed/invalid chain file %s: %s", path.name, e)
            continue
        data["_filename"] = path.name
        out.append(data)
    if include_killed:
        kdir = base / "killed"
        if kdir.exists():
            for path in sorted(kdir.glob("*.yaml")):
                try:
                    data = yaml.safe_load(path.read_text())
                except yaml.YAMLError as e:  # noqa: BLE001
                    log.error("skipping malformed killed chain %s: %s", path.name, e)
                    continue
                data["_filename"] = f"killed/{path.name}"
                data["_killed"] = True
                out.append(data)
    return out


# --------------------------------------------------------------------------- #
# SOURCE ADAPTERS — named readers for the artifacts the seeds bind to. Each is a small
# callable; a MISSING adapter or a missing series/path makes a node UNRESOLVABLE (the
# chain can't arm), which the validator surfaces — NOT silently False.
# --------------------------------------------------------------------------- #
class _Unresolvable(Exception):
    """A node's observable can't be read from disk (missing series/field/adapter)."""


class _SeriesAdapter:
    """Reads a price/level series parquet from ``<data_dir>/<group>/<name>.parquet`` — the
    same on-disk layout as lib.store, but ROOT-AWARE so ``run(root=X)`` is fully hermetic
    (no hidden dependency on config.data_dir()). Missing/empty series → _Unresolvable."""

    def __init__(self, data_dir: Path, group: str):
        self.data_dir = data_dir
        self.group = group

    def _path(self, name: str) -> Path:
        safe = name.replace("^", "_").replace("=", "_").replace("/", "_").replace(" ", "_")
        return self.data_dir / self.group / f"{safe}.parquet"

    def series(self, name: str) -> pd.Series:
        p = self._path(name)
        if not p.exists():
            raise _Unresolvable(f"{self.group}/{name} series absent")
        df = pd.read_parquet(p)
        if df is None or df.empty:
            raise _Unresolvable(f"{self.group}/{name} series empty")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        col = "close" if "close" in df.columns else df.columns[0]
        s = df[col].dropna()
        if s.empty:
            raise _Unresolvable(f"{self.group}/{name} series all-NaN")
        return s


class _StateAdapter:
    """Reads a dotted field path out of a latest.json snapshot on disk."""

    def __init__(self, data_dir: Path, rel: str):
        self.path = data_dir / rel
        self._cache: dict | None = None
        self._loaded = False

    def _doc(self) -> dict:
        if not self._loaded:
            self._loaded = True
            try:
                self._cache = json.loads(self.path.read_text()) if self.path.exists() else None
            except Exception as e:  # noqa: BLE001 — corrupt artifact = unresolvable, not fatal
                log.warning("state artifact unreadable %s: %s", self.path, e)
                self._cache = None
        if self._cache is None:
            raise _Unresolvable(f"state artifact absent/corrupt: {self.path}")
        return self._cache

    def get(self, dotted: str) -> Any:
        doc: Any = self._doc()
        for part in dotted.split("."):
            if not isinstance(doc, dict) or part not in doc:
                raise _Unresolvable(f"path {dotted!r} missing in {self.path.name}")
            doc = doc[part]
        return doc

    def asof(self) -> str | None:
        try:
            doc = self._doc()
        except _Unresolvable:
            return None
        return doc.get("asof") or doc.get("date")


def build_adapters(data_dir: Path) -> dict[str, Any]:
    """The source-adapter registry the four seeds use. Keyed by the YAML node.src value."""
    return {
        "yahoo": _SeriesAdapter(data_dir, "yahoo"),
        "commodity": _SeriesAdapter(data_dir, "commodity"),
        "fred": _SeriesAdapter(data_dir, "fred"),   # FRED series cache (e.g. T10YIE breakeven)
        "transmission_state": _StateAdapter(data_dir, "transmission/latest.json"),
        "regime_state": _StateAdapter(data_dir, "regime/latest.json"),
        "forex_state": _StateAdapter(data_dir, "forex/latest.json"),
    }


# --------------------------------------------------------------------------- #
# TEST EVALUATION — whitelisted ops/metrics, NO eval. Returns (bool, receipt).
# Raises _Unresolvable when the underlying observable can't be read.
# --------------------------------------------------------------------------- #
def _series_metric(adapter: _SeriesAdapter, t: dict) -> tuple[float, dict]:
    """Compute the numeric value of a series-metric test → (value, receipt)."""
    metric = t["metric"]
    window = int(t["window"])
    s = adapter.series(t["series"])
    if metric == "rs":
        o = adapter.series(t["series"])
        v = adapter.series(t["vs"])
        if len(o) <= window or len(v) <= window:
            raise _Unresolvable(f"rs window {window} exceeds history for {t['series']}/{t['vs']}")
        own = o.iloc[-1] / o.iloc[-1 - window] - 1.0
        oth = v.iloc[-1] / v.iloc[-1 - window] - 1.0
        val = float((own - oth) * 100.0)  # RS in percentage points
        return val, {"series": t["series"], "vs": t["vs"], "metric": "rs_pp",
                     "window": window, "value": round(val, 3)}
    if metric == "ratio_ret":
        num = adapter.series(t["series"])
        den = adapter.series(t["ratio"])
        ratio = (num / den).dropna()
        if len(ratio) <= window:
            raise _Unresolvable(f"ratio_ret window {window} exceeds history")
        val = float((ratio.iloc[-1] / ratio.iloc[-1 - window] - 1.0) * 100.0)  # pct
        return val, {"series": f"{t['series']}/{t['ratio']}", "metric": "ratio_ret_pct",
                     "window": window, "value": round(val, 3)}
    if len(s) <= window:
        raise _Unresolvable(f"window {window} exceeds history for {t['series']}")
    if metric == "ret":
        val = float((s.iloc[-1] / s.iloc[-1 - window] - 1.0) * 100.0)  # pct
        return val, {"series": t["series"], "metric": "ret_pct", "window": window, "value": round(val, 3)}
    if metric == "ret_bp":
        # absolute change of a level series in basis points (series stored in % → ×100)
        val = float((s.iloc[-1] - s.iloc[-1 - window]) * 100.0)
        return val, {"series": t["series"], "metric": "ret_bp", "window": window, "value": round(val, 1)}
    if metric == "ma_slope":
        lookback = int(t.get("lookback", 5))
        ma = s.rolling(window).mean().dropna()
        if len(ma) <= lookback:
            raise _Unresolvable(f"ma_slope lookback {lookback} exceeds MA history for {t['series']}")
        val = float(ma.iloc[-1] - ma.iloc[-1 - lookback])
        return val, {"series": t["series"], "metric": f"ma{window}_slope{lookback}", "value": round(val, 4)}
    raise ChainSchemaError(f"unhandled metric {metric!r}")  # pragma: no cover (validated at load)


def _apply_op(op: str, lhs: Any, value: Any) -> bool:
    if op == "is_true":
        return lhs is True
    if op == "is_false":
        return lhs is False
    if op == "in":
        return lhs in value
    if op == "in_contains":
        # lhs is a container (list/str); value is the needle
        return value in lhs if lhs is not None else False
    if op == "eq":
        return lhs == value
    if op == "ne":
        return lhs != value
    # numeric comparisons — lhs must be a number
    if lhs is None:
        raise _Unresolvable(f"numeric op {op} on a null value")
    try:
        x = float(lhs)
        y = float(value)
    except (TypeError, ValueError) as e:
        raise _Unresolvable(f"numeric op {op} on non-numeric {lhs!r}/{value!r}") from e
    return {"gt": x > y, "gte": x >= y, "lt": x < y, "lte": x <= y}[op]


def eval_test(t: dict, adapters: dict[str, Any], src: str) -> tuple[bool, list[dict]]:
    """Evaluate a (possibly nested) test → (bool, [receipts]). Raises _Unresolvable if
    any leaf observable can't be read (so the caller marks the node unresolvable)."""
    if "all" in t:
        results = [eval_test(sub, adapters, src) for sub in t["all"]]
        return all(r[0] for r in results), [rr for r in results for rr in r[1]]
    if "any" in t:
        results = [eval_test(sub, adapters, src) for sub in t["any"]]
        return any(r[0] for r in results), [rr for r in results for rr in r[1]]
    adapter = adapters.get(src)
    if adapter is None:
        raise _Unresolvable(f"no source adapter registered for src={src!r}")
    op = t["op"]
    if "series" in t:
        # duck-typed: a series adapter exposes .series(name); a state adapter does not.
        if not hasattr(adapter, "series"):
            raise _Unresolvable(f"src {src!r} does not provide a series() for a series test")
        val, receipt = _series_metric(adapter, t)
        passed = _apply_op(op, val, t.get("value"))
        receipt = {**receipt, "op": op, "threshold": t.get("value"), "passed": passed}
        return passed, [receipt]
    # path test on a state adapter (duck-typed: exposes .get(dotted))
    if not hasattr(adapter, "get"):
        raise _Unresolvable(f"src {src!r} does not provide a get() for a path test")
    raw = adapter.get(t["path"])
    passed = _apply_op(op, raw, t.get("value"))
    return passed, [{"path": t["path"], "op": op, "threshold": t.get("value"),
                     "value": raw, "passed": passed}]


def eval_node(chain: dict, node_id: str, adapters: dict[str, Any]) -> dict:
    """Evaluate one node → {id, resolved, confirmed, receipts, [unresolved_reason]}."""
    node = chain["nodes"][node_id]
    src = node["src"]
    try:
        passed, receipts = eval_test(node["test"], adapters, src)
        return {"id": node_id, "resolved": True, "confirmed": bool(passed), "receipts": receipts}
    except _Unresolvable as e:
        return {"id": node_id, "resolved": False, "confirmed": False,
                "receipts": [], "unresolved_reason": str(e)}


# --------------------------------------------------------------------------- #
# EPISODE STATE MACHINE (TXI-R2) — TEMPORAL. Advanced nightly; each episode's per-hop
# confirmation dates are threaded through the forward ledger so lag-window EXPIRY is a
# real elapsed-time property, not a same-tape guess.
# --------------------------------------------------------------------------- #
_TERMINAL_STATES = {"expressed", "failed", "expired"}


def _parse_asof(s: str) -> date:
    return datetime.strptime(str(s)[:10], "%Y-%m-%d").date()


def _latest_open_episode(prior: list[dict]) -> dict | None:
    """From this chain's prior ledger rows (chronological), reconstruct the most recent
    OPEN (non-terminal) episode: its arm date, per-hop confirm dates, and last state.
    Returns None if there is no open episode (all terminal, or none yet)."""
    # group rows by episode_id, keep insertion order
    episodes: dict[str, list[dict]] = {}
    for r in prior:
        episodes.setdefault(r.get("episode_id", ""), []).append(r)
    # the last episode whose latest transition is non-terminal
    for eid in reversed(list(episodes.keys())):
        rows = episodes[eid]
        last = rows[-1]
        if last.get("transition") in _TERMINAL_STATES:
            continue
        # reconstruct hop-confirm dates from the rows (arming = hop 0 arm date)
        arm_date = None
        hop_dates: dict[int, str] = {}
        for r in rows:
            tr = r.get("transition")
            if tr == "arming":
                arm_date = r.get("asof")
            elif tr == "propagating":
                hop_dates[int(r.get("hop", 0))] = r.get("asof")
        return {"episode_id": eid, "arm_date": arm_date, "hop_dates": hop_dates,
                "last_state": last.get("transition"), "last_hop": int(last.get("hop", 0))}
    return None


def evaluate_chain(chain: dict, adapters: dict[str, Any], asof: str,
                   prior: list[dict] | None = None) -> dict:
    """Advance a chain's episode state to `asof`, given its `prior` ledger rows (this
    chain's rows only). Returns the per-chain state dict for chain_state.json PLUS the
    NEW transition(s) to append (empty when the state is unchanged — that is what makes a
    same-`asof` re-run idempotent).

    Temporal semantics (TXI-R2):
      * dormant → arming        node 0 confirms on `asof` (opens an episode keyed on asof)
      * propagating(k)→(k+1)    node k+1 confirms within lag_hi(hop k+1) days of hop k's
                                confirm date → advance (expressed if terminal)
      * → expired               lag_hi window closed with node k+1 still unconfirmed
      * → failed                a declared structured falsifier fires while armed
    A terminal episode ends; a later node-0 confirm opens a NEW episode.
    """
    prior = prior or []
    node_ids = list(chain["nodes"].keys())
    hops = chain["hops"]
    tier = chain.get("tier", "hypothesis")
    rev = chain.get("rev", 0)
    slug = chain["chain"]
    asof_d = _parse_asof(asof)

    node_states = [eval_node(chain, nid, adapters) for nid in node_ids]
    unresolved = [ns for ns in node_states if not ns["resolved"]]
    armable = not unresolved   # any unresolvable node ⇒ chain can't arm (masterplan §4)

    open_ep = _latest_open_episode(prior)
    new_transitions: list[dict] = []

    def _receipts_map() -> dict:
        return {ns["id"]: ns["receipts"] for ns in node_states if ns["resolved"]}

    # ------- structured-falsifier check (only while armed, and only once the pending
    # hop's MINIMUM lag has elapsed — a "passthrough absent" falsifier cannot fire before
    # the passthrough has had time to happen; this also keeps a same-asof re-run idempotent
    # since the arming day has elapsed=0 < lag_lo). -------
    def _falsifier_fires(elapsed_days: int, min_lag: float) -> dict | None:
        if elapsed_days < min_lag:
            return None
        for i, fx in enumerate(chain.get("falsifiers", [])):
            if isinstance(fx, dict) and "when" in fx:
                try:
                    passed, receipts = eval_test(fx["when"], adapters, _falsifier_src(chain, fx))
                except _Unresolvable:
                    continue  # fail-open: unevaluable falsifier is skipped
                if passed:
                    return {"index": i, "note": fx.get("note", ""), "receipts": receipts}
        return None

    # current state defaults
    state = "dormant"
    hop_k = 0
    fired_falsifier: dict | None = None
    arm_date = open_ep["arm_date"] if open_ep else None
    hop_dates = dict(open_ep["hop_dates"]) if open_ep else {}
    episode_id = open_ep["episode_id"] if open_ep else _episode_id(slug, rev, asof)

    if not armable:
        # unresolvable ⇒ dormant; an open episode is left as-is (can't advance/expire it
        # without its observables). No new transition.
        state, hop_k = "dormant", 0
    elif open_ep is None:
        # no open episode → can only ARM (needs node 0 true now)
        if node_states[0]["confirmed"]:
            state, hop_k = "arming", 0
            arm_date, episode_id = asof, _episode_id(slug, rev, asof)
            hop_dates = {}
            new_transitions.append(_mk_transition(slug, rev, episode_id, "arming", 0, asof, _receipts_map()))
        else:
            state, hop_k = "dormant", 0
    else:
        # an episode is open — try to advance it, expire it, or fail it.
        last_hop = open_ep["last_hop"]
        # the NEXT hop to confirm is hop index = last_hop (0-based over `hops`).
        # (arming = 0 confirmed hops → next hop is hops[0]; propagating(k) → next hops[k].)
        nxt = last_hop
        if nxt < len(hops):
            hop = hops[nxt]
            lag_lo, lag_hi = hop.get("lag_d", [0, 0])
            prior_confirm = arm_date if nxt == 0 else hop_dates.get(nxt, arm_date)
            elapsed = (asof_d - _parse_asof(prior_confirm)).days if prior_confirm else 0
        else:
            lag_lo = lag_hi = 0
            elapsed = 0
        # a falsifier fires ⇒ failed (terminal) — gated on the pending hop's minimum lag
        fired_falsifier = _falsifier_fires(elapsed, lag_lo)
        if fired_falsifier is not None:
            state, hop_k = "failed", last_hop
            new_transitions.append(_mk_transition(slug, rev, episode_id, "failed", last_hop, asof,
                                                   _receipts_map(), extra={"falsifier": fired_falsifier}))
        else:
            if nxt >= len(hops):
                # already at terminal count but not marked terminal — treat as expressed
                state, hop_k = "expressed", len(hops)
                new_transitions.append(_mk_transition(slug, rev, episode_id, "expressed", len(hops), asof, _receipts_map()))
            else:
                target_ns = node_states[nxt + 1]
                if target_ns["confirmed"]:
                    # confirm iff within the lag window
                    if elapsed <= lag_hi:
                        confirmed_hops = nxt + 1
                        hop_dates[confirmed_hops] = asof
                        if confirmed_hops >= len(hops):
                            state, hop_k = "expressed", len(hops)
                            new_transitions.append(_mk_transition(slug, rev, episode_id, "expressed", len(hops), asof, _receipts_map()))
                        else:
                            state, hop_k = "propagating", confirmed_hops
                            new_transitions.append(_mk_transition(slug, rev, episode_id, "propagating", confirmed_hops, asof, _receipts_map()))
                    else:
                        # confirmed but too late → the window already expired
                        state, hop_k = "expired", last_hop
                        new_transitions.append(_mk_transition(slug, rev, episode_id, "expired", last_hop, asof, _receipts_map()))
                else:
                    if elapsed > lag_hi:
                        state, hop_k = "expired", last_hop
                        new_transitions.append(_mk_transition(slug, rev, episode_id, "expired", last_hop, asof, _receipts_map()))
                    else:
                        # still waiting inside the window — hold current state, NO new row
                        state = "arming" if last_hop == 0 else "propagating"
                        hop_k = last_hop

    # per-hop confirmation view for chain_state.json (uses the reconstructed hop_dates)
    hop_view = []
    for i, hop in enumerate(hops):
        confirmed = (i + 1) in hop_dates or (state == "expressed" and (i + 1) <= len(hops))
        target_ns = node_states[i + 1] if (i + 1) < len(node_states) else {"receipts": []}
        hop_view.append({
            "id": f"{hop['from']}->{hop['to']}",
            "from": hop["from"], "to": hop["to"],
            "lag_d": hop.get("lag_d"),
            "confirmed": bool(confirmed),
            "asof": hop_dates.get(i + 1),
            "value_receipt": target_ns.get("receipts", []),
        })

    per_chain = {
        "chain": slug,
        "rev": rev,
        "tier": tier,
        "title": chain.get("title", {"en": slug, "zh": slug}),
        "state": state,
        "state_label": STATE_LABELS.get(state, STATE_LABELS["dormant"]),
        "hop": hop_k,
        "n_hops": len(hops),
        "armable": armable,
        "episode_id": episode_id if state != "dormant" else None,
        "hops": hop_view,
        "nodes": [{"id": ns["id"], "resolved": ns["resolved"], "confirmed": ns["confirmed"],
                   "receipts": ns["receipts"],
                   **({"unresolved_reason": ns["unresolved_reason"]} if not ns["resolved"] else {})}
                  for ns in node_states],
        "falsifier_fired": fired_falsifier,
        "base_rates": None,          # W3 fills — "untested" until the episode miner runs
        "blast": [],                 # W2 fills — per-name blast-radius flags
        "display_only": True,
    }
    if unresolved:
        per_chain["unresolved_nodes"] = [{"id": ns["id"], "reason": ns["unresolved_reason"]}
                                         for ns in unresolved]
    return {"per_chain": per_chain, "transitions": new_transitions}


def _mk_transition(slug: str, rev: int, episode_id: str, transition: str, hop: int,
                   asof: str, receipts: dict, extra: dict | None = None) -> dict:
    row = {"chain": slug, "rev": rev, "episode_id": episode_id, "transition": transition,
           "hop": hop, "asof": asof, "receipts": receipts}
    if extra:
        row.update(extra)
    return row


def _falsifier_src(chain: dict, fx: dict) -> str:
    """A structured falsifier's 'when' test needs a source adapter. Explicit fx['src']
    wins; otherwise default to the adapter of the node whose id matches the falsifier's
    series/path, else the chain's terminal node's src (falsifiers typically test the
    terminal leg). Series tests fall back to 'yahoo'."""
    if fx.get("src"):
        return fx["src"]
    # default: the terminal node's adapter (most falsifiers re-test the last leg)
    term_id = list(chain["nodes"].keys())[-1]
    return chain["nodes"][term_id].get("src", "yahoo")


def _episode_id(chain_slug: str, rev: int, asof: str) -> str:
    return f"{chain_slug}@r{rev}:{asof}"


# --------------------------------------------------------------------------- #
# LEDGER (forward, append-only, idempotent per (chain, rev, asof, transition))
# --------------------------------------------------------------------------- #
def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            log.warning("skipping malformed chain_episodes line: %s", line[:120])
    return rows


def _ledger_key(r: dict) -> tuple:
    return (r.get("chain"), r.get("rev"), r.get("episode_id"), r.get("transition"),
            r.get("hop"), r.get("asof"))


def _append_transitions(path: Path, transitions: list[dict]) -> int:
    """Append only transitions not already present (keyed on chain, rev, episode_id,
    transition, hop, asof). Returns count appended. IDEMPOTENT: a same-asof re-run of an
    unchanged state produces no new rows, and even a duplicate identical transition dedups.
    """
    existing = _read_ledger(path)
    seen = {_ledger_key(r) for r in existing}
    fresh = [t for t in transitions if _ledger_key(t) not in seen]
    if not fresh:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for t in fresh:
            fh.write(json.dumps(t, ensure_ascii=False, default=str) + "\n")
    return len(fresh)


# --------------------------------------------------------------------------- #
# top-level build
# --------------------------------------------------------------------------- #
def _resolve_asof(adapters: dict[str, Any]) -> str:
    """The snapshot asof — take the transmission state's asof if present, else regime's,
    else today (UTC). Ledger keys on this; a same-nightly re-run reuses the same asof."""
    for key in ("transmission_state", "regime_state", "forex_state"):
        a = adapters.get(key)
        if isinstance(a, _StateAdapter):
            got = a.asof()
            if got:
                return str(got)
    return date.today().isoformat()


CAVEATS = [
    {"en": "Display-only context — never scored, never a call. A chain state is a WATCH item; "
           "it never gates, sizes, ranks, or escalates anything (masterplan §4).",
     "zh": "仅供展示的上下文——从不计入评分，从不作为交易指令。链状态是观察项；不做任何门控、仓位、排名或升级。"},
    {"en": "Per-hop base rates are UNTESTED in W1 (base_rates=null) — the episode miner and the "
           "forward ledger fill them in W3. A propagating chain is not a forecast.",
     "zh": "W1中各跳的基础发生率尚未检验（base_rates=null）——由W3的回溯挖掘与前瞻账本填充。传导中的链并非预测。"},
    {"en": "Per-name blast radius (blast=[]) is resolved in W2 — W1 tracks the cascade state only.",
     "zh": "个股层面的传导范围（blast=[]）在W2解析——W1仅追踪级联状态。"},
]


def build_chain_state(chains: list[dict], adapters: dict[str, Any], asof: str,
                      ledger_rows: list[dict] | None = None) -> tuple[dict, list[dict]]:
    """Evaluate every chain → (chain_state.json dict, all NEW transitions to append).
    `ledger_rows` is the existing chain_episodes.jsonl content; each chain is advanced
    from its own prior rows (temporal state machine). A chain that raises during
    evaluation is logged and SKIPPED (fail-open)."""
    ledger_rows = ledger_rows or []
    by_chain: dict[str, list[dict]] = {}
    for r in ledger_rows:
        by_chain.setdefault(r.get("chain"), []).append(r)
    per_chains: list[dict] = []
    all_transitions: list[dict] = []
    for chain in chains:
        if chain.get("_killed"):
            continue
        try:
            res = evaluate_chain(chain, adapters, asof, prior=by_chain.get(chain.get("chain"), []))
        except Exception as e:  # noqa: BLE001 — one bad chain never crashes the nightly
            log.error("chain %s failed to evaluate (skipped): %s", chain.get("chain"), e)
            continue
        per_chains.append(res["per_chain"])
        all_transitions.extend(res["transitions"])
    state = {
        "schema": SCHEMA_ID,
        "asof": asof,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "chains": per_chains,
        "caveats": CAVEATS,
        "display_only": True,
    }
    return state, all_transitions


def run(root: Path | None = None, *, write: bool = True) -> dict:
    """Load the chain library, evaluate current state from artifacts, and (if write) emit
    chain_state.json + append chain_episodes.jsonl. Returns the chain_state dict.

    ADDITIVE / FAIL-OPEN: absent upstream artifacts leave chains unresolvable (dormant),
    never raising. `write=False` is the dry-run path (used by the runner's --dry-run and
    by tests, which pass a tmp root so no data/ write escapes)."""
    base = Path(root) if root else ROOT
    data_dir = base / "data"
    chains = load_chains(base)  # FAIL-LOUD: a malformed file raises here
    adapters = build_adapters(data_dir)
    asof = _resolve_asof(adapters)
    ledger_path = data_dir / "transmission" / "chain_episodes.jsonl"
    ledger_rows = _read_ledger(ledger_path)   # advance episodes from their history
    state, transitions = build_chain_state(chains, adapters, asof, ledger_rows)
    if write:
        outdir = data_dir / "transmission"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "chain_state.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False, default=str))
        n = _append_transitions(ledger_path, transitions)
        log.info("transmission_chains: %d chains, asof=%s, %d new ledger transition(s)",
                 len(state["chains"]), asof, n)
    return state
