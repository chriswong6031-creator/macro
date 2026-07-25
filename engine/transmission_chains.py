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
    per-chain state, hop confirmations with value receipts, tier, the per-name blast radius
    (``blast`` — W2: armed chains resolve WHICH NAMES are downstream via which named channel,
    each channel carrying its universe count + percentile cuts + full ticker array + an
    unevaluable bucket), and ``base_rates`` (W3).

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

# YAML-declarable tiers (what a chain file may set). `calibrated_context` is NOT declarable —
# it is a RUNTIME DISPLAY tier the compiler assigns when the W3 miner has measured ≥1 hop
# (see `_merge_calibration`); it is still display-only, still no authority (that stays gauntlet-
# gated). Keeping it out of `_VALID_TIERS` means a file cannot self-declare "calibrated_context".
_VALID_TIERS = {"hypothesis", "probe", "calibrated"}
# the runtime display tier the compiler promotes a hypothesis chain to once the calibration
# artifact carries a real (n>=floor) base rate for ≥1 of its hops. Display-only; never authority.
CALIBRATED_CONTEXT_TIER = "calibrated_context"
_VALID_OPS = {"gt", "gte", "lt", "lte", "eq", "ne", "is_true", "is_false", "in", "in_contains"}
_VALID_METRICS = {"ret", "ret_bp", "ma_slope", "rs", "ratio_ret"}

# W2 — exposure-screen mini-form ops (TXI-R1 extension). A screen clause is a structured,
# deterministic dict `{path, op, value}` read against the per-ticker substrate JSON — NO
# string eval (masterplan §scoping.1). `pctile_gte`/`pctile_lte` cut on the universe
# percentile of the field (computed over the evaluable universe at resolve time; the numeric
# cut is printed in the emit). `exists` is a unary presence test. The `<,<=,>,>=,==,!=`
# spellings are the operator's mini-form; they map onto the same comparators as the node
# grammar's gt/lt/... — a screen clause and a node test share the `_apply_op` engine.
_SCREEN_OP_ALIASES = {"<": "lt", "<=": "lte", ">": "gt", ">=": "gte", "==": "eq", "!=": "ne"}
_SCREEN_UNARY_OPS = {"exists"}
_SCREEN_PCTILE_OPS = {"pctile_gte", "pctile_lte"}
# the full whitelisted screen-op surface (spellings the YAML may use)
_VALID_SCREEN_OPS = (set(_SCREEN_OP_ALIASES) | {"in"} | _SCREEN_UNARY_OPS | _SCREEN_PCTILE_OPS)


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


def _validate_screen_clause(c: Any, where: str) -> None:
    """Validate one exposure-screen clause `{path, op, value}` (W2 mini-form)."""
    _require(isinstance(c, dict), f"{where}: screen clause must be a dict, got {type(c).__name__}")
    _require(isinstance(c.get("path"), str) and c["path"],
             f"{where}: screen clause needs a string 'path'")
    op = c.get("op")
    _require(op in _VALID_SCREEN_OPS,
             f"{where}: unknown/absent screen op {op!r} (allowed: {sorted(_VALID_SCREEN_OPS)})")
    if op in _SCREEN_UNARY_OPS:
        return  # `exists` takes no value
    _require("value" in c, f"{where}: screen op {op!r} requires a 'value'")
    if op in _SCREEN_PCTILE_OPS:
        v = c["value"]
        _require(isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0,
                 f"{where}: {op} 'value' must be a fraction in [0,1], got {v!r}")


def _validate_screen(screen: Any, where: str) -> None:
    """Validate one exposure_screens entry: a bilingual label + exactly one `all`/`any`
    list of clauses (the structured mini-form). A prose-only legacy screen (no all/any) is
    tolerated as UNRESOLVED-in-W2 (documentary) — but if the structured form is present it
    must be well-formed."""
    _require(isinstance(screen, dict), f"{where}: screen must be a mapping")
    if "label" in screen:
        lbl = screen["label"]
        _require(isinstance(lbl, dict) and "en" in lbl and "zh" in lbl,
                 f"{where}: screen 'label' must be a bilingual {{en, zh}} mapping")
    has_all = "all" in screen
    has_any = "any" in screen
    if not (has_all or has_any):
        return  # legacy/prose screen (documentary) — W2 skips it, prints it unresolved
    _require(not (has_all and has_any),
             f"{where}: screen must have exactly one of 'all' or 'any', not both")
    key = "all" if has_all else "any"
    _require(isinstance(screen[key], list) and screen[key],
             f"{where}: screen '{key}' must be a non-empty list of clauses")
    for i, clause in enumerate(screen[key]):
        _validate_screen_clause(clause, f"{where}.{key}[{i}]")


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
    for flag, screen in screens.items():
        _validate_screen(screen, f"{filename}:exposure_screens[{flag}]")


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


# --------------------------------------------------------------------------- #
# VECTORIZED metric evaluation (W3 shared surface). `_series_metric` above computes a
# node's series metric at the LAST bar (nightly point-in-time). The W3 episode miner needs
# the SAME metric at EVERY historical bar — so the formula must live in exactly one place.
# `series_metric_timeseries` re-expresses each `_series_metric` branch as a full pd.Series
# over the aligned index; `series_test_timeseries` applies the whitelisted comparator to
# yield the node's boolean history. The miner (engine/transmission_calibration.py) imports
# these — it never re-derives a threshold or a metric (masterplan §W3: "REUSE the node-
# evaluation logic, do not duplicate the threshold parser"). A `_series_metric` at index -1
# and `series_metric_timeseries().iloc[-1]` are the same number by construction.
# --------------------------------------------------------------------------- #
def series_metric_timeseries(get_series, t: dict) -> pd.Series:
    """The value of a series-metric `test` at EVERY bar → a float pd.Series (NaN where the
    window has insufficient lookback). `get_series(name)` returns the raw close series for a
    ticker (the miner passes a store-backed reader). Mirrors `_series_metric` exactly:
      * ret        pct change over `window` trading days (×100)
      * ret_bp     absolute Δ of a level series over `window`, in basis points (×100)
      * ma_slope   change of the `window`-day MA over `lookback` days (raw units)
      * rs         own `window`-return minus `vs`-return, in percentage points
      * ratio_ret  pct return of the `series/ratio` price ratio (×100)
    """
    metric = t["metric"]
    window = int(t["window"])
    s = get_series(t["series"])
    if metric == "rs":
        v = get_series(t["vs"])
        own, oth = s.align(v, join="inner")
        own_ret = own / own.shift(window) - 1.0
        oth_ret = oth / oth.shift(window) - 1.0
        return ((own_ret - oth_ret) * 100.0).dropna()
    if metric == "ratio_ret":
        den = get_series(t["ratio"])
        num, den = s.align(den, join="inner")
        ratio = (num / den).dropna()
        return ((ratio / ratio.shift(window) - 1.0) * 100.0).dropna()
    if metric == "ret":
        return ((s / s.shift(window) - 1.0) * 100.0).dropna()
    if metric == "ret_bp":
        return ((s - s.shift(window)) * 100.0).dropna()
    if metric == "ma_slope":
        lookback = int(t.get("lookback", 5))
        ma = s.rolling(window).mean()
        return (ma - ma.shift(lookback)).dropna()
    raise ChainSchemaError(f"unhandled metric {metric!r}")  # pragma: no cover (validated at load)


def _apply_op_vec(op: str, lhs: pd.Series, value: Any) -> pd.Series:
    """Vectorized twin of `_apply_op` for the numeric comparators a series metric can use
    (gt/gte/lt/lte/eq/ne). Returns a boolean pd.Series aligned to `lhs`. Non-numeric ops
    (is_true/in/...) never appear on a series metric (load-time validation guarantees a
    series test carries a numeric-metric value), so they are not handled here."""
    y = float(value)
    if op == "gt":
        return lhs > y
    if op == "gte":
        return lhs >= y
    if op == "lt":
        return lhs < y
    if op == "lte":
        return lhs <= y
    if op == "eq":
        return lhs == y
    if op == "ne":
        return lhs != y
    raise ChainSchemaError(f"non-numeric op {op!r} on a series metric")  # pragma: no cover


def series_test_timeseries(get_series, t: dict) -> pd.Series:
    """The boolean history of a (possibly `all`/`any`-combined) SERIES test → a bool
    pd.Series on the intersection of its leg indices. Every leaf must be a series metric
    (the miner only calls this for series-adapter nodes); a path leaf raises. Mirrors
    `eval_test`'s combinator semantics with vectorized leaves."""
    if "all" in t:
        legs = [series_test_timeseries(get_series, sub) for sub in t["all"]]
        out = legs[0]
        for leg in legs[1:]:
            out = out & leg
        return out.dropna().astype(bool)
    if "any" in t:
        legs = [series_test_timeseries(get_series, sub) for sub in t["any"]]
        out = legs[0]
        for leg in legs[1:]:
            out = out | leg
        return out.dropna().astype(bool)
    if "series" not in t:
        raise _Unresolvable("series_test_timeseries requires a series leaf (got a path test)")
    vals = series_metric_timeseries(get_series, t)
    return _apply_op_vec(t["op"], vals, t.get("value")).dropna().astype(bool)


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
    {"en": "Per-hop base rates come from the WEEKLY historical episode miner (W3) when its "
           "artifact is present: pooled + per-regime P(hop confirms | upstream fired) with n. "
           "A hop with n below the floor prints \"untested\" WITH its n — never a fabricated "
           "rate. Absent the artifact, base_rates is null. A propagating chain is not a forecast; "
           "a base rate is a printed conditional frequency, not a signal.",
     "zh": "各跳基础发生率来自每周历史情景挖掘（W3）——存在其产物时：汇总＋分regime的P(跳确认|上游触发)并附n。"
           "样本量低于下限的跳打印“未检验”并附其n——绝不编造发生率。无该产物时base_rates为null。传导中的链并非预测；基础发生率是打印的条件频率，而非信号。"},
    {"en": "Per-name blast radius (`blast`) is a WATCH-grade membership screen with a field "
           "receipt, resolved over the per-ticker substrate — never a call and never a size. "
           "Counts always include the unevaluable (missing-field) bucket: a missing field is "
           "neither safe nor unsafe. Only ARMED chains resolve; dormant chains carry blast={}.",
     "zh": "个股层面的传导范围（blast）是带字段凭证的观察级成员筛选，基于个股数据解析——绝非交易指令、绝非仓位。"
           "计数始终包含无法评估（字段缺失）的桶：字段缺失既不安全也不危险。仅已触发的链解析；休眠链的blast为空。"},
]


# --------------------------------------------------------------------------- #
# W2 — BLAST-RADIUS RESOLVER (TXI-R3). An ARMED chain (arming|propagating|expressed)
# resolves WHICH NAMES are downstream, via which named channel, with field receipts. The
# universe is the baked per-ticker substrate `site/stockdata/<T>.json` (~1.6k names); the
# resolver sweeps the dir ONCE, loads each JSON once, precomputes per-field universe
# percentiles, and evaluates every armed chain's structured screens together. Server stores
# TICKERS + numeric cuts only (no per-name receipts — consumers rebuild them client-side
# from the same per-ticker JSON). Counts ALWAYS include an `unevaluable` bucket: a name
# whose screen fields are missing is NEVER silently safe or unsafe.
#
# DISCIPLINE: display-only, deterministic, LLM-free. A screen never scores/ranks/sizes; it
# is a WATCH-grade membership flag with the field receipt (masterplan §4; DNR row 45).
# --------------------------------------------------------------------------- #
_ARMED_STATES = {"arming", "propagating", "expressed"}


def _is_iso_date(s: Any) -> bool:
    """True iff `s` is a well-formed YYYY-MM-DD prefix (rejects 'NaT', None, junk)."""
    if not isinstance(s, str) or len(s) < 10:
        return False
    try:
        datetime.strptime(s[:10], "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _normalize_substrate_doc(d: dict) -> None:
    """Lift a few list-shaped substrate fields into flat, dotted-addressable synthetic paths
    so the screen mini-form stays pure `{path, op, value}` (no list-indexing grammar).

    Currently: ``factors.radar`` (the known-good `[{key, z}, ...]` factor list — masterplan
    field map) → ``factors.radar_<key>_z`` scalars. A null z is dropped (unevaluable, not 0).
    Idempotent and in-place; a doc missing the field is left untouched."""
    factors = d.get("factors")
    if isinstance(factors, dict):
        radar = factors.get("radar")
        if isinstance(radar, list):
            for leg in radar:
                if isinstance(leg, dict) and isinstance(leg.get("key"), str):
                    z = leg.get("z")
                    if isinstance(z, (int, float)) and not isinstance(z, bool):
                        factors[f"radar_{leg['key']}_z"] = z


class SubstrateStore:
    """The per-ticker substrate universe, loaded once. Each entry is the parsed JSON of one
    `site/stockdata/<T>.json`. Precomputes, lazily and per (field-path), the sorted vector
    of that field's numeric values across the evaluable universe so `pctile_*` cuts are O(log
    n) and the numeric cut is printable. ROOT-AWARE + hermetic (a tmp dir of synthetic
    tickers drives the tests)."""

    def __init__(self, docs: dict[str, dict], *, asofs: list[str] | None = None):
        self.docs = docs                                  # ticker -> parsed JSON
        self._sorted_cache: dict[str, list[float]] = {}   # path -> sorted numeric values
        self.asofs = asofs or []

    # ---- construction -----------------------------------------------------
    @classmethod
    def from_dir(cls, substrate_dir: Path) -> "SubstrateStore":
        """Load every `*.json` in the substrate dir EXCEPT index.json. A file that isn't a
        per-ticker doc (no ticker + not parseable as one) is skipped, not fatal. The ticker
        id is the doc's `ticker` field, else the filename stem."""
        docs: dict[str, dict] = {}
        asofs: list[str] = []
        if not substrate_dir.exists():
            log.warning("substrate dir absent: %s", substrate_dir)
            return cls(docs)
        for path in sorted(substrate_dir.glob("*.json")):
            if path.name == "index.json":
                continue
            try:
                d = json.loads(path.read_text())
            except Exception as e:  # noqa: BLE001 — one bad substrate file is not fatal
                log.warning("skipping unreadable substrate file %s: %s", path.name, e)
                continue
            if not isinstance(d, dict):
                continue
            tkr = d.get("ticker") or path.stem
            if not isinstance(tkr, str):
                continue
            _normalize_substrate_doc(d)
            docs[tkr] = d
            a = d.get("asof")
            # only a well-formed ISO date counts toward the substrate_asof stamp — some files
            # carry a serialized 'NaT'/None (verified: MMC, FI, fund_flows) which must not
            # pollute the min/max.
            if _is_iso_date(a):
                asofs.append(a)
        return cls(docs, asofs=asofs)

    def substrate_asof(self) -> dict[str, str | None]:
        """The min/max per-file `asof` — stamped in the emit so a one-render-stale sweep is
        honest (fundamentals-grade fields don't move intraday; masterplan §scoping.2)."""
        if not self.asofs:
            return {"min": None, "max": None}
        return {"min": min(self.asofs), "max": max(self.asofs)}

    # ---- percentile support ----------------------------------------------
    def _sorted_values(self, path: str) -> list[float]:
        """The sorted vector of numeric values of `path` across the evaluable universe
        (missing / non-numeric names excluded). Cached per path."""
        if path not in self._sorted_cache:
            vals = []
            for d in self.docs.values():
                v = _dig(d, path)
                if isinstance(v, bool):
                    continue  # a bool is not a percentile-able number
                if isinstance(v, (int, float)):
                    vals.append(float(v))
            vals.sort()
            self._sorted_cache[path] = vals
        return self._sorted_cache[path]

    def pctile_cut(self, path: str, frac: float) -> float | None:
        """The numeric value at the `frac` quantile of `path`'s universe (nearest-rank). This
        value IS the membership boundary printed in the emit — a consumer holding the per-ticker
        JSON rebuilds the exact ticker set client-side by comparing its field to this cut
        (masterplan §scoping.4). None if the field has no numeric values anywhere (the pctile
        clause is then unevaluable for every name)."""
        vals = self._sorted_values(path)
        if not vals:
            return None
        idx = min(int(frac * len(vals)), len(vals) - 1)   # nearest-rank; frac in [0,1]
        return vals[idx]


_MISSING = object()   # distinct from a present-but-null field (both are "unevaluable")


def _dig(doc: Any, dotted: str) -> Any:
    """A dotted path into a substrate JSON. Returns _MISSING sentinel if any hop is absent."""
    cur = doc
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _eval_screen_clause(clause: dict, doc: dict, store: SubstrateStore,
                        cuts: dict[str, float]) -> bool | None:
    """Evaluate ONE screen clause against one ticker doc.

    Returns:
      * True / False  — the clause is evaluable for this name (field present + comparable)
      * None          — UNEVALUABLE: the field is missing or null (or a pctile field with no
                        universe). None is neither pass nor fail — the caller buckets it.
    """
    path = clause["path"]
    op = clause["op"]
    raw = _dig(doc, path)
    present = raw is not _MISSING and raw is not None

    if op == "exists":
        return present
    if not present:
        return None                       # can't compare a missing/null field
    if op in _SCREEN_PCTILE_OPS:
        if not isinstance(raw, (int, float)) or isinstance(raw, bool):
            return None
        cut = cuts.get(path)
        if cut is None:                   # no universe for this field → unevaluable
            return None
        # Membership is decided by the PRINTED NUMERIC CUT (not by recomputing each name's
        # percentile) so a consumer holding the per-ticker JSON can rebuild the exact same
        # ticker set client-side from the emitted `cuts` value alone (masterplan §scoping.4:
        # "receipts rebuild client-side from the same fields; server stores tickers + cuts
        # only"). pctile_gte → value >= cut (the frac-quantile value); pctile_lte → value <= cut.
        return float(raw) >= cut if op == "pctile_gte" else float(raw) <= cut
    # scalar comparators — reuse the node grammar's engine (raises _Unresolvable on a
    # non-numeric lhs for a numeric op; we translate that to "unevaluable").
    concrete = _SCREEN_OP_ALIASES.get(op, op)   # "<" -> "lt", "==" -> "eq", ...
    try:
        return _apply_op(concrete, raw, clause.get("value"))
    except _Unresolvable:
        return None


def _eval_screen(screen: dict, doc: dict, store: SubstrateStore,
                 cuts: dict[str, float]) -> bool | None:
    """Evaluate one structured screen (`all`/`any` of clauses) against one ticker doc.

    `all`:  every clause must be True. If ANY clause is unevaluable (None), the whole screen
            is UNEVALUABLE (we cannot assert membership with a missing field — masterplan:
            missing-field names are NEVER silently safe/unsafe).
    `any`:  True if any clause is True. If no clause is True but AT LEAST ONE is unevaluable,
            the screen is UNEVALUABLE (a present field could have flipped it). Only when
            every clause is evaluable-and-False is the screen a clean False.
    A prose-only (no all/any) screen returns None (not resolved in W2)."""
    if "all" in screen:
        results = [_eval_screen_clause(c, doc, store, cuts) for c in screen["all"]]
        if any(r is None for r in results):
            return None
        return all(results)
    if "any" in screen:
        results = [_eval_screen_clause(c, doc, store, cuts) for c in screen["any"]]
        if any(r is True for r in results):
            return True
        if any(r is None for r in results):
            return None
        return False
    return None


def _dropped_channel_entry(screen: Any, universe: int, *, note_override=None) -> dict:
    """The emit for a declared-but-not-resolved channel (prose-only / dropped / a malformed
    clause skipped at resolve time). n:0, whole universe unevaluable, resolved:false, with the
    bilingual note carried through so a dropped/proxy channel is HONEST, never silently absent."""
    lbl = screen.get("label") if isinstance(screen, dict) else None
    note = note_override if note_override is not None else (
        screen.get("note") if isinstance(screen, dict) else None)
    return {"label": lbl, "n": 0, "cuts": {}, "unevaluable": universe,
            "names": [], "resolved": False, "note": note}


def _resolve_channel(screen: dict, store: SubstrateStore) -> dict:
    """Resolve ONE structured channel over the whole substrate → the blast entry. Precomputes
    the pctile cuts (printed), then buckets every name into member / unevaluable."""
    # precompute the numeric cut for each pctile clause (printed in the emit)
    cuts: dict[str, float] = {}
    for key in ("all", "any"):
        for c in screen.get(key, []):
            if isinstance(c, dict) and c.get("op") in _SCREEN_PCTILE_OPS:
                cut = store.pctile_cut(c["path"], float(c["value"]))
                if cut is not None:
                    cuts[c["path"]] = round(cut, 4)
    names: list[str] = []
    unevaluable = 0
    for tkr, doc in store.docs.items():
        res = _eval_screen(screen, doc, store, cuts)
        if res is None:
            unevaluable += 1
        elif res:
            names.append(tkr)
    entry = {
        "label": screen.get("label"),
        "n": len(names),
        "cuts": cuts,
        "unevaluable": unevaluable,
        "names": sorted(names),   # full ticker array — tickers are cheap (cap nothing)
        "resolved": True,
    }
    if screen.get("note"):
        entry["note"] = screen["note"]
    return entry


def resolve_blast(chain: dict, per_chain: dict, store: SubstrateStore) -> dict:
    """Resolve one chain's blast radius over the substrate universe.

    Returns the `blast` block for chain_state.json: `{}` when the chain is DORMANT (state not
    in arming|propagating|expressed), else `{flag: {label, n, cuts, unevaluable, names,
    resolved, note?}}` per channel. A prose-only / DROPPED channel (no all/any) still emits —
    resolved:false, n:0, whole universe unevaluable — so a dropped/proxy channel is HONEST,
    never silently absent. Bilingual notes on dropped/proxy channels live in the YAML and are
    echoed here.

    ROBUST: a malformed clause that slips past load-time validation (or any per-channel
    error) SKIPS just that channel with a resolved:false + note marker — one bad screen never
    crashes the sweep or the other channels (masterplan §Tests: "malformed clause → channel
    skipped with note, never crashes")."""
    if per_chain.get("state") not in _ARMED_STATES:
        return {}
    screens = chain.get("exposure_screens", {}) or {}
    universe = len(store.docs)
    blast: dict[str, Any] = {}
    for flag, screen in screens.items():
        if not isinstance(screen, dict) or not ("all" in screen or "any" in screen):
            # prose-only / legacy / dropped screen — declared, not resolvable in W2.
            blast[flag] = _dropped_channel_entry(screen, universe)
            continue
        try:
            blast[flag] = _resolve_channel(screen, store)
        except Exception as e:  # noqa: BLE001 — a malformed clause skips THIS channel, not the chain
            log.error("chain %s screen %s failed to resolve (skipped): %s",
                      chain.get("chain"), flag, e)
            note = screen.get("note") if isinstance(screen.get("note"), dict) else None
            blast[flag] = _dropped_channel_entry(
                screen, universe,
                note_override={"en": f"unresolved (screen error): {e}",
                               "zh": f"未解析（筛选错误）：{e}"} if note is None else note)
    return blast


# --------------------------------------------------------------------------- #
# W3 — CALIBRATION MERGE. The nightly read fills each hop's `base_rates` slot (the W1 null
# placeholder) from the WEEKLY-mined chain_calibration.json when present, and promotes a
# chain from `hypothesis` to the `calibrated_context` DISPLAY tier once ≥1 hop carries a real
# (n>=floor) base rate. DISPLAY-ONLY: this only enriches printed context — never a score,
# gate, size, rank, or escalation (masterplan §4). A missing/mismatched-rev calibration
# artifact leaves base_rates null and the tier untouched (fail-open — W1 behavior).
# --------------------------------------------------------------------------- #
def load_calibration(data_dir: Path) -> dict | None:
    """Read data/transmission/chain_calibration.json if present → the parsed dict, else None
    (fail-open: absent artifact = base_rates stays the W1 null placeholder)."""
    p = data_dir / "transmission" / "chain_calibration.json"
    if not p.exists():
        return None
    try:
        doc = json.loads(p.read_text())
        return doc if isinstance(doc, dict) else None
    except Exception as e:  # noqa: BLE001 — a corrupt calibration file must not break the read
        log.warning("chain_calibration.json unreadable (%s) — base_rates null", e)
        return None


def _calibration_index(calibration: dict | None) -> dict[str, dict]:
    """Index the calibration doc's chains by slug for O(1) hop lookup."""
    if not isinstance(calibration, dict):
        return {}
    return {c.get("chain"): c for c in calibration.get("chains", []) if isinstance(c, dict)}


def _merge_calibration(per_chain: dict, chain: dict, cal_entry: dict | None) -> None:
    """In place: fill `per_chain['base_rates']` from `cal_entry` (the calibration for this
    chain, matched by slug) and promote the tier to `calibrated_context` if ≥1 hop is measured.

    base_rates shape (per hop, keyed by the hop id `from->to`): {p_confirm, n, lag_d, method,
    per_regime, regime_split, ...} — a straight copy of the miner's per-hop dict (pooled +
    per-regime). An untested hop keeps its "untested"+n honesty. When `cal_entry` is absent OR
    its rev does not match the live chain rev, base_rates stays null and the tier is untouched
    (a stale calibration from a prior chain revision must NOT be shown against new thresholds).
    """
    if not isinstance(cal_entry, dict):
        return  # no calibration for this chain → null placeholder, tier unchanged (W1)
    if cal_entry.get("rev") != chain.get("rev"):
        # rev mismatch: the mined rates were measured against a DIFFERENT chain revision's
        # thresholds — showing them would be dishonest. Leave null + record why.
        per_chain["base_rates"] = None
        per_chain["base_rates_note"] = {
            "en": f"calibration is for rev {cal_entry.get('rev')} but the live chain is rev "
                  f"{chain.get('rev')}; base rates withheld until re-mined against this revision.",
            "zh": f"校准针对rev {cal_entry.get('rev')}，而当前链为rev {chain.get('rev')}；"
                  f"在按此修订重新挖掘前暂不展示基础发生率。"}
        return
    hops_cal = cal_entry.get("hops", [])
    by_id: dict[str, dict] = {}
    measured = 0
    for h in hops_cal:
        if not isinstance(h, dict):
            continue
        hid = f"{h.get('from')}->{h.get('to')}"
        by_id[hid] = h
        if h.get("p_confirm") != "untested" and isinstance(h.get("n"), int) and h.get("n", 0) > 0:
            measured += 1
    per_chain["base_rates"] = {
        "asof": cal_entry.get("asof"),
        "n_floor": None,   # filled by caller from the doc-level floor
        "calibrated_hops": cal_entry.get("calibrated_hops", measured),
        "n_hops": cal_entry.get("n_hops", len(hops_cal)),
        "by_hop": by_id,
        "cohort_event_study": cal_entry.get("cohort_event_study"),
    }
    # also mirror the base rate onto each hop_view entry for consumers reading hops[] directly
    for hv in per_chain.get("hops", []):
        hid = hv.get("id")
        if hid in by_id:
            h = by_id[hid]
            hv["base_rate"] = {"p_confirm": h.get("p_confirm"), "n": h.get("n"),
                               "regime_split": h.get("regime_split"),
                               "per_regime": h.get("per_regime", {})}
    # tier promotion (display-only): hypothesis → calibrated_context when ≥1 hop measured.
    # A chain that declared `probe`/`calibrated` in YAML keeps its (higher) declared tier.
    if measured >= 1 and per_chain.get("tier") == "hypothesis":
        per_chain["tier"] = CALIBRATED_CONTEXT_TIER


def build_chain_state(chains: list[dict], adapters: dict[str, Any], asof: str,
                      ledger_rows: list[dict] | None = None,
                      substrate: SubstrateStore | None = None,
                      calibration: dict | None = None) -> tuple[dict, list[dict]]:
    """Evaluate every chain → (chain_state.json dict, all NEW transitions to append).
    `ledger_rows` is the existing chain_episodes.jsonl content; each chain is advanced
    from its own prior rows (temporal state machine). A chain that raises during
    evaluation is logged and SKIPPED (fail-open).

    When a `substrate` store is supplied (W2), each ARMED chain's blast radius is resolved
    over the per-ticker universe and merged into its `blast` block; dormant chains keep
    `blast: {}`. Substrate resolution NEVER crashes the nightly — a resolver error on one
    chain is logged and that chain keeps `blast: {}`.

    When a `calibration` dict is supplied (W3 — the parsed chain_calibration.json), each
    chain's `base_rates` slot is filled from its matching (slug+rev) mined entry and the tier
    is promoted hypothesis→calibrated_context if ≥1 hop is measured (n>=floor). Absent /
    mismatched calibration leaves base_rates null + tier unchanged (fail-open). Display-only."""
    ledger_rows = ledger_rows or []
    cal_index = _calibration_index(calibration)
    cal_floor = calibration.get("n_floor") if isinstance(calibration, dict) else None
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
        per_chain = res["per_chain"]
        if substrate is not None:
            try:
                per_chain["blast"] = resolve_blast(chain, per_chain, substrate)
            except Exception as e:  # noqa: BLE001 — a resolver error keeps blast:{}, never fatal
                log.error("chain %s blast-radius resolution failed (blast={}): %s",
                          chain.get("chain"), e)
                per_chain["blast"] = {}
        # W3: fill base_rates from the weekly calibration + promote tier (fail-open — a merge
        # error leaves base_rates null and the tier unchanged, never crashing the nightly).
        try:
            _merge_calibration(per_chain, chain, cal_index.get(chain.get("chain")))
            if isinstance(per_chain.get("base_rates"), dict) and cal_floor is not None:
                per_chain["base_rates"]["n_floor"] = cal_floor
        except Exception as e:  # noqa: BLE001
            log.error("chain %s calibration merge failed (base_rates null): %s",
                      chain.get("chain"), e)
        per_chains.append(per_chain)
        all_transitions.extend(res["transitions"])
    state = {
        "schema": SCHEMA_ID,
        "asof": asof,
        "built": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "chains": per_chains,
        "caveats": CAVEATS,
        "display_only": True,
    }
    if substrate is not None:
        state["substrate"] = {
            "universe": len(substrate.docs),
            "substrate_asof": substrate.substrate_asof(),
        }
    return state, all_transitions


SUBSTRATE_RELDIR = ("site", "stockdata")   # per-ticker universe (W2 blast resolver)


def run(root: Path | None = None, *, write: bool = True,
        substrate_dir: Path | None = None, resolve_blast_radius: bool = True) -> dict:
    """Load the chain library, evaluate current state from artifacts, resolve armed-chain
    blast radius over the per-ticker substrate (W2), and (if write) emit chain_state.json +
    append chain_episodes.jsonl. Returns the chain_state dict.

    ADDITIVE / FAIL-OPEN: absent upstream artifacts leave chains unresolvable (dormant),
    never raising; an absent substrate dir leaves every `blast` empty (armed chains get
    `{}`), never raising. `write=False` is the dry-run path (used by the runner's --dry-run
    and by tests, which pass a tmp root so no data/ write escapes). `substrate_dir` overrides
    the default `<root>/site/stockdata`; `resolve_blast_radius=False` skips the sweep
    entirely (W1-compatible: `blast` stays `[]`)."""
    base = Path(root) if root else ROOT
    data_dir = base / "data"
    chains = load_chains(base)  # FAIL-LOUD: a malformed file raises here
    adapters = build_adapters(data_dir)
    asof = _resolve_asof(adapters)
    ledger_path = data_dir / "transmission" / "chain_episodes.jsonl"
    ledger_rows = _read_ledger(ledger_path)   # advance episodes from their history
    substrate: SubstrateStore | None = None
    if resolve_blast_radius:
        sdir = Path(substrate_dir) if substrate_dir else base.joinpath(*SUBSTRATE_RELDIR)
        substrate = SubstrateStore.from_dir(sdir)
    # W3: the weekly-mined base rates (absent → base_rates stays the W1 null placeholder).
    calibration = load_calibration(data_dir)
    state, transitions = build_chain_state(chains, adapters, asof, ledger_rows,
                                           substrate=substrate, calibration=calibration)
    if write:
        outdir = data_dir / "transmission"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "chain_state.json").write_text(
            json.dumps(state, indent=2, ensure_ascii=False, default=str))
        n = _append_transitions(ledger_path, transitions)
        log.info("transmission_chains: %d chains, asof=%s, %d new ledger transition(s)",
                 len(state["chains"]), asof, n)
    return state
