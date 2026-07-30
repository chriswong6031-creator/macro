"""engine.neuralweb.brain_curve — Mastermind: the full Treasury curve on demand.

CLASSIFICATION: read-only retrieval helper for the Mastermind brain gateway.
This module holds ONE function and its Anthropic tool schema; the gateway owns
dispatch, the tool allowlist, and tier gating. Nothing here is imported by the
nightly, writes a file, opens a socket, or calls an LLM.

TIER: display/context — READ-ONLY AGGREGATION. Not one number here is computed,
re-derived, or re-classified. `engine.yield_curve.snapshot()` is a LEAF display
module: it already publishes the spreads, the percentiles, the 63-day changes,
the PCA, the regime label and the recession suite. This module SLICES that block
out of whichever parent artifact carries it and reshapes it for a chat turn.

PUBLIC API
----------
get_curve_detail(root) -> dict
    The curated curve read: regime label, four spreads with percentiles, the
    real/breakeven decomposition, shape + PCA variance shares, momentum, the
    recession suite, forwards, and the live intraday tenor overlay when the tape
    is up. Never raises.

CURVE_TOOL_SCHEMA
    Anthropic tool definition, shaped like brain_gateway._brain_tool_schemas().

WHERE THE DEPTH LIVES (the one substrate, two parents)
-----------------------------------------------------
The `yield_curve` block (~18 KB) is published verbatim inside TWO parents:

    data/transmission/latest.json["yield_curve"]   66 KB parent, display tier
    data/regime/latest.json["yield_curve"]        770 KB parent, infra tier

Transmission is read first — it is the display-tier parent, it is an order of
magnitude smaller, and it also carries the real/breakeven decomposition in its
own `state` block, so the happy path is ONE file open. The regime parent is the
fallback and carries no `state`, so on that rung the decomposition falls through
to data/neuralweb/world_state.json.

Only the block is sliced; neither parent is ever returned whole.

WHAT IS DELIBERATELY LEFT BEHIND (TI-R5 / A7)
---------------------------------------------
The source block carries `regime.favored` / `regime.pressured` (ETF lists) and a
`signals.sector` table of per-ETF tilts with forward ICs and CONFIRMED /
DIRECTIONAL verdicts. Those are a shock -> beneficiary/casualty map, which is a
standing house KILL (TI-R5, research/DO_NOT_REBUILD.md §1 "laundered directional
escalation on nulled continuation claims"), and an LLM may not originate or
relay a signal or escalation (A7). They are NOT in the output, and
tests/test_brain_curve.py pins that mechanically by asserting no ticker from
either list survives projection — so a future source that renames or moves them
cannot leak them in. Every emitted value is built field-by-field from a literal
key list; there is no ``{**block}`` spread anywhere on the output path, and the
result is cached as a STRING, so no caller can mutate a source dict either.

The display-only disclosure travels WITH the numbers: the source's own
`scored_status` and `caveats` (the calibrator found no yield-curve leg robust
enough to move an allocation) are carried into `caveats`, plus the weekly-FRED
seam. Nulls printed, not hidden.

LANGUAGE
--------
The regime LABEL ships EN + ZH because the desk precomputes both
(`curve_regime_label_zh` is the packet's precedent). The prose fields (fed
phase, desk note, caveats) ship the desk's EN text only: carrying both would
roughly double a payload that has an 8 KB budget, and the chat's LANGUAGE
directive governs the reply's language. Same rule as market_packet's zh digest —
desk-precomputed Chinese only, never machine-translated on the way out.

CACHE
-----
An in-process cache keyed on the source mtimes with a 60 s ceiling, mirroring
market_packet.digest: the nightly parents move once a night, but `live_tenors`
rides the intraday tape, so a purely mtime-keyed entry could serve a stale
overlay indefinitely. The cached value is the serialised JSON, so every caller
gets its own dict.
"""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path

# --------------------------------------------------------------------------- #
# Contract
# --------------------------------------------------------------------------- #
SCHEMA = "brain.curve_detail.v1"
ERROR_UNAVAILABLE = "curve_detail_unavailable"

# Parents carrying the `yield_curve` block, highest precedence first. See the
# module docstring for why transmission leads.
_PARENT_RELS: tuple[tuple[str, ...], ...] = (
    ("data", "transmission", "latest.json"),
    ("data", "regime", "latest.json"),
)
_WORLD_STATE_REL: tuple[str, ...] = ("data", "neuralweb", "world_state.json")

# The weekly-FRED seam, appended to whatever the source already discloses. Some
# legs (the TIPS/breakeven curve especially) publish with a multi-day official
# lag, so "yesterday's asof" does not mean "yesterday's data" on every leg.
_FRED_SEAM_CAVEAT = (
    "Nightly FRED-derived; some legs publish with a multi-day official lag."
)

# Structural budget guards. The tool has an 8 KB serialised ceiling (pinned in
# tests/test_brain_curve.py); these keep a future source that appends twenty
# caveats or a 4 KB desk note from blowing through it silently.
_MAX_CAVEATS = 6
_CAVEAT_MAX_CHARS = 400
_NOTE_MAX_CHARS = 700
_PHASE_MAX_CHARS = 240

# Spreads carried, in reading order: the cycle slope, the recession slope, the
# long-end/term-premium slope, the front belly. `real_5s10s`, `be_5s10s` and
# `tp_adj` live in `decomposition` instead, where the real/breakeven split is.
_SPREAD_KEYS: tuple[str, ...] = ("2s10s", "3m10y", "5s30s", "2s5s")

# Momentum is projected key-by-key rather than passed through, so an upstream
# addition cannot reach the model without an edit here.
_MOMENTUM_KEYS: tuple[str, ...] = (
    "real10y_speed_bp",
    "nom10y_speed_bp",
    "front2y_speed_bp",
    "slope_chg_bp",
    "real_speed_pctile",
    "trend_spread",
    "trend_spread_dir",
    "trend_spread_chg_1y_bp",
    "window_d",
)

# PCA factor keys -> output keys. The per-factor number in the source is a
# VARIANCE SHARE, not a rate, so the output key says so: a bare `"level": 0.825`
# next to `"nominal_10y": 4.61` invites exactly the yield-direction misread the
# evaluation rubric tracks as a failure mode (§9).
_PCA_FACTORS: tuple[tuple[str, str], ...] = (
    ("level", "level_var_explained"),
    ("slope", "slope_var_explained"),
    ("curvature", "curvature_var_explained"),
)

_CACHE_TTL_S = 60.0
_CACHE: dict[tuple, tuple[str, float]] = {}
_CACHE_LOCK = threading.Lock()


# --------------------------------------------------------------------------- #
# Small fail-soft helpers
# --------------------------------------------------------------------------- #
def _read_json(path: Path):
    """Parse `path` as JSON, or return None. Never raises.

    Missing, unreadable and corrupt collapse to one answer on purpose: every
    caller here treats "no usable artifact" identically, and a retrieval tool
    that raised would take the whole chat turn down with it.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001 — any read/parse failure degrades to None
        return None


def _num(raw):
    """Coerce to float, or None. `bool` is rejected — True is not a rate."""
    if isinstance(raw, bool) or raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _txt(raw, limit: int | None = None) -> str | None:
    """Whitespace-collapsed string, or None when blank/absent.

    None rather than "": the two are different claims to the model — None reads
    as "the desk published no note", "" reads as "the note is empty".
    """
    if not isinstance(raw, str):
        return None
    clean = " ".join(raw.split())
    if not clean:
        return None
    if limit is not None and len(clean) > limit:
        clean = clean[: limit - 1] + "…"
    return clean


def _lang(raw, lang: str, limit: int | None = None) -> str | None:
    """One language out of a desk {en, zh} pair (or a bare string for `en`)."""
    if isinstance(raw, str):
        return _txt(raw, limit) if lang == "en" else None
    if isinstance(raw, dict):
        return _txt(raw.get(lang), limit)
    return None


def _dict(raw) -> dict:
    """`raw` when it is a dict, else {} — so every read below can be blind."""
    return raw if isinstance(raw, dict) else {}


def _prune(block: dict) -> dict | None:
    """Drop None-valued keys; return None when nothing survived.

    A block of nothing but nulls is worse than an absent block: it reads as
    "the desk measured this and got nothing" instead of "this leg is not
    published in this vintage".
    """
    kept = {k: v for k, v in block.items() if v is not None}
    return kept or None


# --------------------------------------------------------------------------- #
# Source resolution
# --------------------------------------------------------------------------- #
def _resolve_source(root: Path) -> tuple[dict, dict] | None:
    """First parent on the ladder carrying a `yield_curve` dict.

    Returns (yield_curve_block, parent_state) or None. `parent_state` is the
    parent's own `state` block when it has one (transmission does; regime does
    not), which is where the real/breakeven decomposition lives on the happy
    path.
    """
    for rel in _PARENT_RELS:
        payload = _read_json(root.joinpath(*rel))
        block = _dict(payload).get("yield_curve")
        if isinstance(block, dict) and block:
            return block, _dict(_dict(payload).get("state"))
    return None


def _world_state_rates(root: Path) -> dict:
    """`state`-shaped rates/expectations out of world_state.json, or {}.

    Two paths are tried because the file nests it: the flat `state` (the shape
    the spec named, and what a future flattening would produce) and the real
    2026-07 location, `rates_transmission.state`. Read ONCE — the file is
    ~174 KB and only two small sub-blocks are wanted.
    """
    payload = _dict(_read_json(root.joinpath(*_WORLD_STATE_REL)))
    for candidate in (payload.get("state"),
                      _dict(payload.get("rates_transmission")).get("state")):
        state = _dict(candidate)
        if _dict(state.get("rates")) or _dict(state.get("expectations")):
            return state
    return {}


# --------------------------------------------------------------------------- #
# Block projections — every one is literal, field by field
# --------------------------------------------------------------------------- #
def _regime(block: dict) -> dict | None:
    """The desk's curve regime: key, bilingual label, phase, note, term premium.

    `favored` / `pressured` are deliberately NOT read (see the module docstring).
    """
    regime = _dict(block.get("regime"))
    if not regime:
        return None
    return _prune({
        "key": _txt(regime.get("key")),
        "label_en": _lang(regime.get("label"), "en"),
        "label_zh": _lang(regime.get("label"), "zh"),
        "desc": _lang(regime.get("desc"), "en", _PHASE_MAX_CHARS),
        "fed_phase": _lang(regime.get("fed_phase"), "en", _PHASE_MAX_CHARS),
        "note": _lang(regime.get("note"), "en", _NOTE_MAX_CHARS),
        "term_premium_dir": _txt(regime.get("term_premium_dir")),
        "term_premium_chg_bp": _num(regime.get("term_premium_chg_bp")),
    })


def _spread(entry) -> dict | None:
    """One slope: value, percentile, 63-day change in bp, inverted flag."""
    row = _dict(entry)
    if not row:
        return None
    inverted = row.get("inverted")
    return _prune({
        "value": _num(row.get("value")),
        "pctile": _num(row.get("pctile")),
        "chg_63d_bp": _num(row.get("chg_63d_bp")),
        "inverted": inverted if isinstance(inverted, bool) else None,
    })


def _spreads(block: dict) -> dict | None:
    """The four headline spreads, each with its own percentile and 63-day move."""
    slopes = _dict(block.get("slopes"))
    out = {key: _spread(slopes.get(key)) for key in _SPREAD_KEYS}
    return _prune(out)


def _decomposition(block: dict, state: dict) -> dict | None:
    """Nominal / real / breakeven levels plus the TIPS and inflation curves.

    Levels come from the parent's `state` (rates + expectations); the curve legs
    come from the yield_curve block's own `slopes`. Both are the same nightly
    vintage on the transmission rung — the same builder writes them.
    """
    rates = _dict(state.get("rates"))
    expectations = _dict(state.get("expectations"))
    slopes = _dict(block.get("slopes"))
    return _prune({
        "nominal_10y": _num(rates.get("nominal_10y")),
        "real_10y": _num(rates.get("real_10y")),
        "real_10y_pctile": _num(rates.get("real_10y_pctile")),
        "breakeven_10y": _num(expectations.get("breakeven_10y")),
        "breakeven_5y5y": _num(expectations.get("breakeven_5y5y")),
        "anchoring": _txt(expectations.get("anchoring")),
        # NOT the funds-vs-neutral stance gap in recession.policy_stance.gap_pp.
        # engine/rate_inflation_transmission.py:87 defines this one as
        # "us2y − funds (cut/hike pricing)" — what the MARKET is pricing, not how
        # restrictive the Fed is. Both were called a "policy gap" upstream and on
        # 2026-07-29 they read 0.63 and 1.13; shipping two same-named gaps with
        # different values is how a chat answer invents a definition, so this key
        # states its own arithmetic.
        "policy_pricing_2y_minus_funds_pp": _num(rates.get("policy_gap")),
        "real_5s10s": _spread(slopes.get("real_5s10s")),
        "be_5s10s": _spread(slopes.get("be_5s10s")),
        "tp_adj_2s10s": _spread(slopes.get("tp_adj")),
    })


def _shape(block: dict) -> dict | None:
    """Level + percentile, the two butterflies, and the PCA variance shares."""
    shape = _dict(block.get("shape"))
    if not shape:
        return None
    level = _dict(shape.get("level"))
    pca_src = _dict(shape.get("pca"))
    pca: dict = {}
    factors = pca_src.get("factors")
    if isinstance(factors, list):
        by_key = {_txt(_dict(f).get("key")): _dict(f) for f in factors}
        for src_key, out_key in _PCA_FACTORS:
            pca[out_key] = _num(by_key.get(src_key, {}).get("var_explained"))
    pca["first3_var_explained"] = _num(pca_src.get("first3_var"))
    pca["window_d"] = _num(pca_src.get("window_d"))
    return _prune({
        "level": _num(level.get("value")),
        "level_pctile": _num(level.get("pctile")),
        "level_chg_63d_bp": _num(level.get("chg_63d")),
        # The flies keep their percentile: a butterfly of -0.17 has no reading
        # without one, and a bare number invites an invented interpretation.
        "fly_2s5s10s": _fly(shape.get("fly_2s5s10s")),
        "fly_5s10s30s": _fly(shape.get("fly_5s10s30s")),
        "pca": _prune(pca),
    })


def _fly(entry) -> dict | None:
    """One butterfly: value, percentile, 63-day change (the shape block's form
    names that last key `chg_63d`, not `chg_63d_bp` as `slopes` does)."""
    row = _dict(entry)
    if not row:
        return None
    return _prune({
        "value": _num(row.get("value")),
        "pctile": _num(row.get("pctile")),
        "chg_63d_bp": _num(row.get("chg_63d")),
    })


def _momentum(block: dict) -> dict | None:
    """Rate-of-change legs, projected key-by-key from _MOMENTUM_KEYS."""
    src = _dict(block.get("momentum"))
    if not src:
        return None
    out: dict = {}
    for key in _MOMENTUM_KEYS:
        value = src.get(key)
        out[key] = _txt(value) if isinstance(value, str) else _num(value)
    return _prune(out)


def _recession(block: dict) -> dict | None:
    """The recession suite: NTFS + its plain-word reading, NY Fed probability,
    un-inversion, the policy stance arithmetic, and the desk's risk word.

    `ntfs_signal` rides along with `ntfs` on purpose: 0.7 alone carries no sign
    convention, and "positive — no near-term break priced" is the desk's own
    plain-word reading of it. Number without its stance word is how a curve
    read gets inverted in a chat answer.

    `policy_stance.note` (a paragraph of Wright-2006 exposition, EN + ZH) is
    dropped — it is textbook context, not a fact about today's curve, and it
    costs a tenth of the payload budget.
    """
    src = _dict(block.get("recession"))
    if not src:
        return None
    stance = _dict(src.get("policy_stance"))
    uninversion = src.get("uninversion")
    return _prune({
        "ntfs": _num(src.get("ntfs")),
        "ntfs_signal": _txt(src.get("ntfs_signal")),
        "nyfed_prob_pct": _num(src.get("nyfed_prob")),
        "uninversion": uninversion if isinstance(uninversion, bool) else None,
        "risk": _txt(src.get("risk")),
        "policy_stance": _prune({
            "fed_funds": _num(stance.get("fed_funds")),
            "neutral_anchor": _num(stance.get("neutral_anchor")),
            "gap_pp": _num(stance.get("gap_pp")),
            "stance": _txt(stance.get("stance")),
        }),
    })


def _forwards(block: dict) -> dict | None:
    """Market-implied forward short rates plus the 10y carry+roll cushion."""
    src = _dict(block.get("forwards"))
    if not src:
        return None
    return _prune({
        "f_1y1y": _num(src.get("f_1y1y")),
        "f_2y1y": _num(src.get("f_2y1y")),
        "f_5y5y": _num(src.get("f_5y5y")),
        "carry_rolldown_10y_pct": _num(src.get("carry_roll_10y_pct")),
    })


def _caveats(block: dict) -> list[str]:
    """The source's own disclosure, then the FRED seam. Bounded, deduped.

    `scored_status` leads when present: it is the load-bearing line (no
    yield-curve leg passed the scored-leg gate), and a vintage that dropped the
    `caveats` list would otherwise ship the numbers with no display-only
    disclosure attached.
    """
    out: list[str] = []

    def _add(text: str | None) -> None:
        if text and text not in out and len(out) < _MAX_CAVEATS:
            out.append(text)

    _add(_lang(block.get("scored_status"), "en", _CAVEAT_MAX_CHARS))
    source = block.get("caveats")
    if isinstance(source, list):
        for entry in source:
            _add(_lang(entry, "en", _CAVEAT_MAX_CHARS))
    # The seam is appended even at the cap: it is OUR disclosure, not the
    # source's, and dropping it would leave the multi-day publication lag unsaid.
    if _FRED_SEAM_CAVEAT not in out:
        out.append(_FRED_SEAM_CAVEAT)
    return out


def _live_tenors(root: Path) -> dict | None:
    """The intraday tenor overlay from the Live Market State Packet, or None.

    market_packet already resolves ^IRX/^FVX/^TNX/^TYX through its live-dir
    ladder and — load-bearing — does PAIR-LEVEL yield-scale detection, because
    yield-index units are feed-dependent in this product (spark/quotes.json is
    percent-direct, the /ws/tape relay is x10). Re-reading quotes.json here
    would fork that law; calling the packet inherits it.

    Imported lazily and inside a try: a packet failure must cost the overlay,
    never the nightly curve read.
    """
    try:
        from engine.neuralweb import market_packet  # noqa: PLC0415

        curve = _dict(market_packet.build_packet(root)).get("curve")
    except Exception:  # noqa: BLE001 — the overlay is optional by contract
        return None
    tenors_src = _dict(_dict(curve).get("tenors"))
    tenors: dict = {}
    for name, row in tenors_src.items():
        label = _txt(name)
        projected = _prune({
            "level_pct": _num(_dict(row).get("level_pct")),
            "change_bp": _num(_dict(row).get("change_bp")),
        })
        if label and projected:
            tenors[label] = projected
    if not tenors:
        return None
    return _prune({"tenors": tenors, "asof": _txt(_dict(curve).get("asof"))})


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #
def _clock() -> float:
    """Monotonic seconds. Indirected so a test can age the cache."""
    return time.monotonic()


def _cache_key(root: Path) -> tuple:
    """(root, (path, mtime)*). A source that APPEARS or vanishes changes the key
    as surely as an edited one, because a missing file is keyed as None rather
    than skipped."""
    pairs: list[tuple[str, float | None]] = []
    for rel in _PARENT_RELS + (_WORLD_STATE_REL,):
        path = root.joinpath(*rel)
        try:
            pairs.append((str(path), path.stat().st_mtime))
        except OSError:
            pairs.append((str(path), None))
    return (str(root), tuple(pairs))


# --------------------------------------------------------------------------- #
# The tool
# --------------------------------------------------------------------------- #
def _build(root: Path) -> dict:
    """Assemble the payload. Pure slicing — see the module docstring."""
    resolved = _resolve_source(root)
    if resolved is None:
        return {"schema": SCHEMA, "error": ERROR_UNAVAILABLE, "note": (
            "The nightly curve artifact is not readable in this checkout — say "
            "the curve read is unavailable rather than describing the curve."
        )}
    block, parent_state = resolved

    state = parent_state
    if not (_dict(state.get("rates")) or _dict(state.get("expectations"))):
        # The regime rung carries no `state`; the decomposition lives in the
        # Neural Web world state on that path.
        state = _world_state_rates(root)

    live = _live_tenors(root)
    payload = {
        "schema": SCHEMA,
        "asof": _txt(block.get("asof")),
        "tier": "display",
        "regime": _regime(block),
        "spreads": _spreads(block),
        "decomposition": _decomposition(block, state),
        "shape": _shape(block),
        "momentum": _momentum(block),
        "recession": _recession(block),
        "forwards": _forwards(block),
        "live_tenors": live,
        "freshness": _prune({
            "source_asof": _txt(block.get("asof")),
            "live_asof": _dict(live).get("asof"),
        }),
        "caveats": _caveats(block),
    }
    # `live_tenors: null` is kept deliberately — an explicit null tells the model
    # the tape overlay is absent (closed, stale, or unresolved), where a missing
    # key reads as "not part of this tool".
    return {k: v for k, v in payload.items() if v is not None or k == "live_tenors"}


def get_curve_detail(root: Path) -> dict:
    """The full Treasury curve read — DISPLAY TIER, aggregation only.

    Slices the nightly `yield_curve` block (transmission parent, regime parent
    as fallback), blends the real/breakeven decomposition from the same vintage,
    and overlays the live intraday tenors from the Live Market State Packet when
    the tape is up.

    Computes nothing: every value, percentile, change and label is the yield
    curve engine's own published output. Emits no sector beneficiary or casualty
    list and no allocation verdict (TI-R5 / A7 — see the module docstring), and
    carries the desk's display-only disclosure in `caveats`.

    Returns the payload, or {"schema", "error": "curve_detail_unavailable",
    "note"} when neither parent artifact is readable. Never raises.
    """
    try:
        key = _cache_key(root)
        now = _clock()
        with _CACHE_LOCK:
            hit = _CACHE.get(key)
            if hit is not None and (now - hit[1]) < _CACHE_TTL_S:
                return json.loads(hit[0])
        payload = _build(root)
        text = json.dumps(payload, ensure_ascii=False)
        with _CACHE_LOCK:
            if len(_CACHE) > 32:  # unbounded roots would leak; cheap to rebuild
                _CACHE.clear()
            _CACHE[key] = (text, _clock())
        # Round-trip so the caller's dict is never the one behind the cache.
        return json.loads(text)
    except Exception:  # noqa: BLE001 — retrieval must not take the turn down
        return {"schema": SCHEMA, "error": ERROR_UNAVAILABLE,
                "note": "The curve read could not be assembled."}


# --------------------------------------------------------------------------- #
# Anthropic tool schema (shape mirrors brain_gateway._brain_tool_schemas)
# --------------------------------------------------------------------------- #
CURVE_TOOL_SCHEMA: dict = {
    "name": "get_curve_detail",
    "description": (
        "Full Treasury curve read on demand: the four headline spreads with "
        "their percentiles and 63-day moves (2s10s, 3m10y, 5s30s, 2s5s), the "
        "real / breakeven decomposition (nominal 10y, real 10y, 10y and 5y5y "
        "breakevens, TIPS and inflation curves, anchoring), the term-premium "
        "direction and TP-adjusted slope, curve level + butterflies + PCA "
        "variance shares, rate-of-change momentum, the desk's curve regime "
        "label, the recession suite (near-term forward spread, NY Fed "
        "probability, un-inversion, policy stance vs neutral), forwards with "
        "the 10y carry+roll cushion, and the live intraday tenor overlay when "
        "the tape is up. Call when the user asks about the yield curve, "
        "steepening or flattening, inversion, real rates or breakevens, term "
        "premium, duration risk, or what the bond market is pricing. "
        "DISPLAY TIER: no yield-curve leg passed the desk's scored-leg gate, so "
        "this is context for your own read — never an allocation signal. It "
        "returns no sector beneficiary or casualty list; draw any equity read "
        "yourself and say so. Levels are nightly FRED-derived and some legs "
        "publish with a multi-day official lag, so quote the asof."
    ),
    "input_schema": {"type": "object", "properties": {}, "required": []},
}
