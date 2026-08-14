"""engine/entry_radar/universe.py — the Probe Set funnel (Layers A–D).

THE FUNNEL (contract §6)
------------------------
  Layer A  broad eligibility — a LENS, not a door.  It classifies every
           supported tradable U.S. name (operating equity / ADR / wrapper /
           unclassified) and excludes wrappers.  It admits NOBODY.
  Layer B  core — index membership (S&P 1500), liquid large/mids, and the
           operator watchlist/holdings.
  Layer C  dynamic hot — admission on measured attention (dollar-volume rank,
           relative volume, intraday RVOL, realized range, gap, short-term
           momentum).  HOTNESS ADMITS, IT NEVER SCORES.
  Layer D  lobe nominations — ANY valid v1 nomination auto-admits, regardless of
           rank, index membership or size (contract §0 P-6).

**Membership is B ∪ C ∪ D, filtered through the Layer-A lens.**  An eligible
name with no B/C/D reason is NOT probed — otherwise the Probe Set would simply
BE the broad universe (~2,966 names), B/C/D would contribute nothing, the
500–1,500 budget would be exceeded on every pass, and the escalation warning
would fire unconditionally.  An alarm that is always on is not an alarm.

A name in one layer is probed exactly as hard as a name in three;
``admission_layers`` records which doors it came through, and that is
provenance, not a score.  ``layer_counts["A"]`` is therefore NOT an admission
count — it reports how many probed names the eligibility universe vouches for,
and the gap to ``n_probed`` is the lobe-nominated tail Layer A never heard of
(gate P-6's whole population).

THE UNIVERSE IS READ, NOT REBUILT (Track C §2)
----------------------------------------------
Layer A consumes the same underlying artifacts the canonical ~2,966-name
universe is built from — ``data/breadth/constituents.parquet`` and its
midcap/smallcap/russell siblings, plus the deep-history store — in the same
priority order.  It deliberately does NOT import
``scripts/build_stock_library.py``: that module is a G-8-adjacent protected
consumer path, and importing it would couple Radar's funnel to Prophet-side
scoring machinery.  Reading the same artifacts gets the same names with none of
the coupling.

Every source reports its own availability (the ``universe_sources()``
self-audit analog): a group silently dropping shrinks the universe by O(1000)
and is a known real failure mode (Track C §2 cites the 2026-07-25 incident).

WRAPPER CLASSIFICATION IS FAIL-CLOSED
-------------------------------------
No systematic ETF/ETN/leveraged classifier exists in the estate — only two
narrow curated lists (Track C §3).  So the classifier here is curated-list
first, then name/ticker-shape heuristics, and it lands on ``unclassified``
whenever it cannot tell.  ``unclassified`` names stay in the Probe Set,
separately classified and visible: never silently dropped (we would lose a real
operating company) and never silently admitted as an operating company (we
would probe a 3x leveraged ETN and grade its "entry").

THE RETENTION RULE — MISSING IS NOT NEGATIVE (contract §5)
-----------------------------------------------------------
This is the rule the module picks, and it is tested by
``test_unavailable_producer_retains_prior_members``:

  * A producer read ``ok`` that simply does not mention a name is a REAL
    NEGATIVE OBSERVATION.  That name's admission reason from that producer
    lapses immediately, as it should.
  * A producer read ``unavailable`` says nothing at all.  Every name that
    producer previously admitted is RETAINED, with its admission reason marked
    ``source_status="unavailable"`` and ``retained_stale=True``, for
    ``retention.unavailable_retention_sessions`` (default 3) sessions — then it
    lapses.  Silence from a broken producer is not evidence of absence, and
    evicting a name because a reader crashed would make an outage look like a
    market event.
  * A producer read ``stale`` carries real but aged facts: its names are
    admitted normally with ``source_status="stale"``.

THE BUDGET IS SOFT (contract §6)
--------------------------------
Target envelope 500–1,500 names.  If the assembly exceeds it, every name is
admitted anyway and a ``budget_exceeded`` note rides on the artifact.  Nothing
is ever silently truncated — "if 1,700 deserve probing, 1,700 are probed and
the budget question is escalated".

NO DETECTOR MATH LIVES HERE.  Layer C reads attention features that other
producers already computed; it computes no oscillator, no RSI, no StochRSI, no
turn.  Those are PR-2/PR-3.
"""
from __future__ import annotations

import fnmatch
import logging
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import (
    ADMISSION_LAYERS,
    AUTHORITY_BLOCK,
    PROBE_SET_SCHEMA,
    AdmissionReason,
    Nomination,
    ProbeRecord,
    ProducerRead,
    iso,
    parse_ts,
    utcnow,
)
from engine.entry_radar.nomination_bus import NominationBus

log = logging.getLogger(__name__)

_CONFIG_REL = "config/entry_radar.yml"

DEFAULTS: dict[str, Any] = {
    "probe_set": {"target_min": 500, "target_max": 1500},
    # No min_history_sessions: young history is first-class (contract §6/§12).
    "layer_a": {"sources": []},
    "layer_b": {"index_memberships": ["sp500", "sp400", "sp600"],
                "dollar_vol_20d_min": 50_000_000},
    "layer_c": {"enabled": True, "dollar_vol_rank_max": 300, "rel_volume_min": 2.0,
                "rvol_tod_min": 2.5, "realized_range_pct_min": 6.0,
                "gap_abs_pct_min": 4.0, "momentum_20d_abs_pct_min": 20.0},
    "layer_d": {"auto_admit": True},
    "producers": {"stale_after_minutes": {}, "default_stale_after_minutes": 2160},
    "retention": {"unavailable_retention_sessions": 3},
    # No default_ttl_minutes: TTL derives per-artifact from stale_after_minutes.
    "spool": {"prefix": "live_flow/entry_radar_nominations"},
}


def load_config(root: Path | None = None, *, cfg: Mapping[str, Any] | None = None
                ) -> dict[str, Any]:
    """Read ``config/entry_radar.yml`` over ``DEFAULTS``.  Never raises.

    ``cfg`` short-circuits the file read (tests, and any caller holding config
    in memory).  A missing or malformed file degrades to the defaults with a
    line-start annotation rather than failing the lane — every value in it is a
    budget knob, and a budget knob is not worth an outage.
    """
    out = {k: dict(v) if isinstance(v, dict) else v for k, v in DEFAULTS.items()}
    raw: Mapping[str, Any] | None = cfg
    if raw is None:
        base = root or Path(__file__).resolve().parents[2]
        path = base / _CONFIG_REL
        try:
            import yaml  # noqa: PLC0415
            loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            raw = (loaded.get("entry_radar") or {}) if isinstance(loaded, dict) else {}
        except FileNotFoundError:
            print(f"::notice title=entry-radar::{_CONFIG_REL} absent — budget defaults used",
                  flush=True)
            raw = {}
        except Exception as exc:  # noqa: BLE001
            print(f"::warning title=entry-radar::{_CONFIG_REL} unreadable ({exc}) — "
                  "budget defaults used", flush=True)
            raw = {}
    if isinstance(raw, Mapping) and "entry_radar" in raw:
        raw = raw.get("entry_radar") or {}
    for key, val in (raw or {}).items():
        if isinstance(val, Mapping) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **dict(val)}
        else:
            out[key] = val
    return out


# ---------------------------------------------------------------------------
# Layer A — wrapper classifier
# ---------------------------------------------------------------------------

#: Whole-phrase markers of a wrapper/derivative product.  Matched
#: case-insensitively against the security NAME.
_WRAPPER_NAME_TOKENS: tuple[str, ...] = (
    "etf", "etn", "exchange traded", "exchange-traded", "index fund", "index trust",
    "ultrashort", "ultrapro", "ultra short", "proshares", "direxion", "leveraged",
    "inverse", "bull 2x", "bull 3x", "bear 2x", "bear 3x", "2x shares", "3x shares",
    "daily 2x", "daily 3x", "-1x", "1.5x", "ishares", "spdr", "vaneck", "global x",
    "wisdomtree", "xtrackers", "invesco qqq", "first trust", "franklin ftse",
    "amplify", "roundhill", "yieldmax", "defiance", "graniteshares", "simplify",
    "innovator", "pacer", "alerian", "breakwave", "currencyshares", "currency shares",
    "commodity trust", "commodity index", "futures fund", "physical gold",
    "physical silver", "physical platinum", "physical palladium", "bitcoin trust",
    "covered call", "buffer etf", "closed-end", "closed end fund", "unit trust",
    "depositary receipt fund", "royalty trust", "income fund", "municipal fund",
)

#: Warrant / right / unit markers — the "decaying derivative wrapper" bucket.
_DERIVATIVE_NAME_TOKENS: tuple[str, ...] = (
    "warrant", "warrants", " rights", "rights (", "subscription right",
    " units", "unit (", "subunit",
)

_ADR_NAME_TOKENS: tuple[str, ...] = (
    "adr", "ads", "american depositary", "american depository", "sponsored adr",
)

#: Unambiguous ticker-shape suffixes (explicit separators).
_WRAPPER_TICKER_SUFFIXES: tuple[str, ...] = (
    ".W", ".WS", ".WT", "-WT", ".U", ".UN", "-UN", ".RT", ".R", ".RTS", "+",
)

_WORD_RE = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True, slots=True)
class EligibilityVerdict:
    """Layer-A classification for one name, with its own provenance."""

    state: str
    reason: str
    confidence: str = "high"

    def to_dict(self) -> dict[str, Any]:
        return {"state": self.state, "reason": self.reason, "confidence": self.confidence}


def curated_wrapper_tickers(cfg: Mapping[str, Any] | None = None) -> frozenset[str]:
    """The two narrow curated wrapper lists the estate already has (Track C §2).

    ``engine.etf_registry.fund_registry()`` (board funds) and
    ``engine.factor_exposure.ETF_NAMES`` (factor/sector ETFs).  Both are
    LAZILY imported and fail soft: they are a *supplement* to the heuristics,
    never a prerequisite, and neither answers "is this arbitrary new ticker a
    wrapper" outside its own narrow context.
    """
    out: set[str] = set()
    try:
        from engine.etf_registry import fund_registry  # noqa: PLC0415
        out.update(str(t).strip().upper() for t in (fund_registry(cfg) or {}))
    except Exception as exc:  # noqa: BLE001
        log.info("entry_radar.universe: etf_registry unavailable (%s) — heuristics only", exc)
    try:
        from engine.factor_exposure import ETF_NAMES  # noqa: PLC0415
        out.update(str(t).strip().upper() for t in (ETF_NAMES or {}))
    except Exception as exc:  # noqa: BLE001
        log.info("entry_radar.universe: factor_exposure unavailable (%s) — heuristics only", exc)
    return frozenset(t for t in out if t)


def classify_eligibility(ticker: str, *, name: str | None = None,
                         meta: Mapping[str, Any] | None = None,
                         curated: frozenset[str] | None = None) -> EligibilityVerdict:
    """Classify one name into the §6 Layer-A states.  FAIL-CLOSED.

    Order: explicit metadata → curated list → name tokens → unambiguous ticker
    shape → Nasdaq fifth-letter convention (name-absent only) → name present
    and clean ⇒ ``operating_equity`` → otherwise ``unclassified``.

    The last branch is the important one: **no evidence is not evidence of
    being an operating company.**  A bare ticker with no name and no metadata
    lands in ``unclassified``, stays in the Probe Set, and is visibly flagged.
    """
    sym = str(ticker or "").strip().upper()
    meta = meta or {}
    label = str(name if name is not None else (meta.get("name") or meta.get("company") or "")).strip()

    declared = str(meta.get("instrument_type") or meta.get("security_type") or "").strip().lower()
    if declared:
        if declared in ("etf", "etn", "fund", "trust", "warrant", "right", "unit", "wrapper"):
            return EligibilityVerdict("wrapper_excluded", f"metadata instrument_type={declared}")
        if declared in ("adr", "ads"):
            return EligibilityVerdict("adr", f"metadata instrument_type={declared}")
        if declared in ("cs", "common stock", "equity", "operating_equity", "common"):
            return EligibilityVerdict("operating_equity", f"metadata instrument_type={declared}")

    if curated and sym in curated:
        return EligibilityVerdict("wrapper_excluded", "curated fund registry hit")

    low = label.lower()
    if low:
        words = set(_WORD_RE.findall(low))
        for token in _WRAPPER_NAME_TOKENS:
            if (" " in token or "-" in token or "." in token):
                if token in low:
                    return EligibilityVerdict("wrapper_excluded", f"name token {token!r}")
            elif token in words:
                return EligibilityVerdict("wrapper_excluded", f"name token {token!r}")
        for token in _DERIVATIVE_NAME_TOKENS:
            if token.strip() in low:
                return EligibilityVerdict("wrapper_excluded", f"derivative token {token.strip()!r}")
        for token in _ADR_NAME_TOKENS:
            if token in words or (" " in token and token in low):
                return EligibilityVerdict("adr", f"name token {token!r}")

    for suffix in _WRAPPER_TICKER_SUFFIXES:
        if sym.endswith(suffix):
            return EligibilityVerdict("wrapper_excluded", f"ticker suffix {suffix!r}")

    if not low and len(sym) == 5 and sym.isalpha():
        # Nasdaq fifth-letter convention.  Shape-only, so it is recorded at
        # LOW confidence and only consulted when no name exists to contradict it.
        fifth = sym[-1]
        if fifth in ("W", "R", "U"):
            return EligibilityVerdict("wrapper_excluded",
                                      f"nasdaq fifth-letter {fifth!r} (warrant/right/unit)",
                                      confidence="low")
        if fifth == "Y":
            return EligibilityVerdict("adr", "nasdaq fifth-letter 'Y' (ADR)", confidence="low")

    if low:
        return EligibilityVerdict("operating_equity", "no wrapper/ADR marker in name")

    return EligibilityVerdict("unclassified", "no name or metadata available — fail-closed",
                              confidence="low")


# ---------------------------------------------------------------------------
# Layer A — universe sources
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class UniverseSourceRead:
    """One Layer-A source's contribution + its own availability."""

    key: str
    status: str
    tickers: tuple[str, ...] = ()
    meta: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"key": self.key, "status": self.status, "n": len(self.tickers),
                "detail": self.detail}


def read_constituents(path: Path, *, key: str, loader: Any = None) -> UniverseSourceRead:
    """Read one ``constituents.parquet`` — symbol index + optional GICS columns.

    ``loader`` is injected in tests (this worktree is sparse: ``data/`` is
    absent, and an absent artifact must NEVER be read as an empty index).
    Production path uses pandas lazily.  A read failure is ``unavailable``,
    never an empty universe.
    """
    try:
        if loader is not None:
            frame = loader(path)
        else:
            import pandas as pd  # noqa: PLC0415
            frame = pd.read_parquet(path)
    except FileNotFoundError:
        return UniverseSourceRead(key=key, status="unavailable", detail=f"{path} absent")
    except Exception as exc:  # noqa: BLE001
        return UniverseSourceRead(key=key, status="unavailable", detail=f"{path}: {exc}")

    syms: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    try:
        if isinstance(frame, Mapping):
            rows = [{"symbol": k, **(v if isinstance(v, Mapping) else {})}
                    for k, v in frame.items()]
        elif hasattr(frame, "reset_index"):
            rows = frame.reset_index().to_dict("records")
        else:
            rows = list(frame)
        for row in rows:
            sym = str(row.get("symbol") or row.get("ticker") or row.get("index") or "").strip().upper()
            if not sym:
                continue
            syms.append(sym)
            meta[sym] = {k: v for k, v in row.items()
                         if k in ("name", "company", "security", "sector", "gics_sector",
                                  "industry", "instrument_type", "security_type")}
    except Exception as exc:  # noqa: BLE001
        return UniverseSourceRead(key=key, status="unavailable", detail=f"{path} parse: {exc}")

    if not syms:
        return UniverseSourceRead(key=key, status="unavailable",
                                  detail=f"{path} yielded zero symbols — treated as an "
                                         "outage, not an empty index")
    return UniverseSourceRead(key=key, status="ok", tickers=tuple(syms), meta=meta,
                              detail=f"{len(syms)} symbols")


def read_deep_history(dir_path: Path, *, key: str = "deep_history") -> UniverseSourceRead:
    """Ticker stems of ``data/stocks/*.parquet`` — the deep-history store."""
    try:
        if not dir_path.is_dir():
            return UniverseSourceRead(key=key, status="unavailable", detail=f"{dir_path} absent")
        syms = tuple(sorted({p.stem.strip().upper() for p in dir_path.glob("*.parquet")}))
    except OSError as exc:
        return UniverseSourceRead(key=key, status="unavailable", detail=f"{dir_path}: {exc}")
    if not syms:
        return UniverseSourceRead(key=key, status="unavailable",
                                  detail=f"{dir_path} holds no parquet files")
    return UniverseSourceRead(key=key, status="ok", tickers=syms, detail=f"{len(syms)} symbols")


@dataclass(frozen=True, slots=True)
class LayerAResult:
    """Layer A: the eligible population + per-name classification + source audit."""

    eligibility: Mapping[str, EligibilityVerdict]
    meta: Mapping[str, Mapping[str, Any]]
    sources: tuple[UniverseSourceRead, ...]

    @property
    def tickers(self) -> tuple[str, ...]:
        return tuple(sorted(self.eligibility))

    def probeable(self) -> tuple[str, ...]:
        """Everything except confirmed wrappers.  ``unclassified`` IS probeable.

        Excluding ``unclassified`` would silently drop real operating companies
        whose metadata is merely missing; including it as ``operating_equity``
        would silently admit leveraged wrappers.  It is probed AND flagged.
        """
        return tuple(sorted(t for t, v in self.eligibility.items()
                            if v.state != "wrapper_excluded"))

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for verdict in self.eligibility.values():
            out[verdict.state] = out.get(verdict.state, 0) + 1
        return out


def build_layer_a(sources: Sequence[UniverseSourceRead], *,
                  names: Mapping[str, str] | None = None,
                  curated: frozenset[str] | None = None) -> LayerAResult:
    """Union the Layer-A sources in priority order and classify every name.

    Priority order is the caller's order (deep-history first, matching Track C
    §2): earlier sources win metadata ties.
    """
    meta: dict[str, dict[str, Any]] = {}
    for src in sources:
        if src.status != "ok":
            continue
        for sym in src.tickers:
            row = meta.setdefault(sym, {})
            row.setdefault("universe_source", src.key)
            for k, v in (src.meta.get(sym) or {}).items():
                if v is not None and k not in row:
                    row[k] = v
    for sym, label in (names or {}).items():
        meta.setdefault(str(sym).strip().upper(), {}).setdefault("name", label)

    curated = curated if curated is not None else frozenset()
    eligibility = {sym: classify_eligibility(sym, meta=row, curated=curated)
                   for sym, row in meta.items()}
    return LayerAResult(eligibility=eligibility, meta=meta, sources=tuple(sources))


# ---------------------------------------------------------------------------
# Layer B — core (index membership, liquidity, operator watchlist)
# ---------------------------------------------------------------------------

class SupabaseWatchlistAdapter:
    """Operator watchlist/holdings — a server-side DB read, not a file read.

    The operator watchlist lives in Supabase (``watchlists`` /
    ``watchlist_symbols`` / ``portfolio_positions``, RLS owner-scoped —
    Track C §2), which makes it architecturally unlike every other producer
    here, and its provenance field says so.

    The client is INJECTED.  With no client (the render host, CI, every test)
    the adapter returns ``unavailable`` — never an empty watchlist, because an
    empty watchlist is a claim about the operator and an outage is not.  The VPS
    lane wires the real client in a later PR.
    """

    SOURCE_ID = "supabase:watchlist"

    def __init__(self, client: Any = None, *,
                 tables: Sequence[str] = ("watchlists", "watchlist_symbols",
                                          "portfolio_positions")) -> None:
        self._client = client
        self._tables = tuple(tables)

    def read(self, *, now: datetime | None = None,
             ttl_minutes: float = 1440.0) -> ProducerRead:
        stamp = now or utcnow()
        if self._client is None:
            return ProducerRead(source_id=self.SOURCE_ID, status="unavailable",
                                observed_at=stamp,
                                detail="no Supabase client injected — operator watchlist "
                                       "not readable on this host (NOT an empty watchlist)")
        rows: list[Mapping[str, Any]] = []
        newest: datetime | None = None
        try:
            for table in self._tables:
                got = self._client.table(table).select("*").execute()
                data = getattr(got, "data", None)
                if data is None and isinstance(got, Mapping):
                    data = got.get("data")
                for row in data or ():
                    if isinstance(row, Mapping):
                        rows.append(row)
                        asof = parse_ts(row.get("updated_at") or row.get("created_at"))
                        if asof is not None:
                            newest = asof if newest is None else max(newest, asof)
        except Exception as exc:  # noqa: BLE001
            return ProducerRead(source_id=self.SOURCE_ID, status="unavailable",
                                observed_at=stamp, detail=f"Supabase read failed: {exc}")

        asof = newest or stamp
        clamped = asof > stamp
        asof = min(asof, stamp)
        noms: list[Nomination] = []
        seen: set[str] = set()
        from datetime import timedelta  # noqa: PLC0415
        for row in rows:
            sym = str(row.get("symbol") or row.get("ticker") or "").strip().upper()
            if not sym or sym in seen:
                continue
            seen.add(sym)
            held = row.get("quantity") is not None or row.get("shares") is not None
            code = "operator.portfolio_position" if held else "operator.watchlist_member"
            noms.append(Nomination(
                ticker=sym, source_id=self.SOURCE_ID, source_family="operator",
                reason_code=code,
                reason_text=("Held in the operator portfolio" if held
                             else "On an operator watchlist"),
                observed_at=stamp, source_asof=asof,
                ttl_until=stamp + timedelta(minutes=ttl_minutes),
                evidence_ref="supabase:watchlists/watchlist_symbols/portfolio_positions",
                data_quality="degraded" if clamped else "ok",
            ))
        return ProducerRead(source_id=self.SOURCE_ID,
                            status="stale" if clamped else "ok", nominations=tuple(noms),
                            source_asof=asof, observed_at=stamp,
                            detail=f"{len(noms)} operator symbol(s) from {len(rows)} row(s)")


#: Universe source keys that are INDEX MEMBERSHIPS (deep-history is not one).
MEMBERSHIP_KEYS: frozenset[str] = frozenset({"sp500", "sp400", "sp600", "russell2000"})


def universe_source_id(key: str) -> str:
    """The ``source_id`` a universe source publishes under.

    Membership sources share the id their Layer-B admission reasons carry
    (``breadth:constituents:<key>``) so that an outage on ``sp500`` matches the
    reasons ``sp500`` created.  Retention keys off ``source_id``, so a mismatch
    here silently disables it: the names an index admitted would be evicted the
    moment that index failed to read, turning a reader crash into a market
    event.
    """
    return f"breadth:constituents:{key}" if key in MEMBERSHIP_KEYS else f"universe:{key}"


def _with_dollar_vol_rank(features: Mapping[str, Mapping[str, Any]] | None
                          ) -> dict[str, dict[str, Any]]:
    """Derive ``dollar_vol_rank`` from ``dollar_vol_20d`` across the snapshot.

    No producer in the estate publishes a dollar-volume RANK (Track C lists
    ``dollar_vol_20d`` and ``rel_volume`` only), so the knob had no feeder and
    the rule never fired.  The rank is cheap and honest to compute here: sort
    the names we actually hold by 20d dollar volume, 1 = largest.

    It is a rank WITHIN THE SNAPSHOT WE READ, not within the market — a partial
    stock-library read makes it optimistic.  That is why it admits and never
    scores, and why the reason text records the value it matched.
    """
    out = {sym: dict(row) for sym, row in (features or {}).items()}
    ranked = sorted(
        ((sym, float(row["dollar_vol_20d"])) for sym, row in out.items()
         if row.get("dollar_vol_20d") is not None),
        key=lambda kv: kv[1], reverse=True)
    for pos, (sym, _dv) in enumerate(ranked, start=1):
        out[sym].setdefault("dollar_vol_rank", pos)
    return out


def layer_b_admissions(cfg: Mapping[str, Any], *,
                       memberships: Mapping[str, Sequence[str]] | None = None,
                       liquidity: Mapping[str, Mapping[str, Any]] | None = None,
                       watchlist: ProducerRead | None = None,
                       now: datetime | None = None) -> dict[str, list[AdmissionReason]]:
    """Layer B — index membership + liquid large/mids + operator names."""
    stamp = now or utcnow()
    knobs = {**DEFAULTS["layer_b"], **dict(cfg.get("layer_b") or {})}
    wanted = set(knobs.get("index_memberships") or ())
    out: dict[str, list[AdmissionReason]] = {}

    for index_key, syms in (memberships or {}).items():
        if wanted and index_key not in wanted:
            continue
        for sym in syms or ():
            key = str(sym).strip().upper()
            if not key:
                continue
            out.setdefault(key, []).append(AdmissionReason(
                layer="B", source_id=f"breadth:constituents:{index_key}",
                reason_code="core.index_member",
                reason_text=f"{index_key.upper()} index member",
                source_asof=None, observed_at=stamp, detail={"index": index_key}))

    floor = float(knobs.get("dollar_vol_20d_min") or 0.0)
    for sym, row in (liquidity or {}).items():
        try:
            dv = float(row.get("dollar_vol_20d"))
        except (TypeError, ValueError):
            continue
        if dv < floor:
            continue
        key = str(sym).strip().upper()
        out.setdefault(key, []).append(AdmissionReason(
            layer="B", source_id="stockdata:master", reason_code="core.liquid_large_mid",
            reason_text=f"20d dollar volume ${dv:,.0f} ≥ ${floor:,.0f} budget floor",
            observed_at=stamp, detail={"dollar_vol_20d": dv, "floor": floor}))

    if watchlist is not None and watchlist.usable:
        for nom in watchlist.nominations:
            out.setdefault(nom.ticker, []).append(AdmissionReason(
                layer="B", source_id=nom.source_id, reason_code=nom.reason_code,
                reason_text=nom.reason_text, source_status=watchlist.status,
                source_asof=nom.source_asof, observed_at=nom.observed_at,
                detail={"provenance": "supabase server-side DB read (RLS owner-scoped)"}))
    return out


# ---------------------------------------------------------------------------
# Layer C — dynamic hot
# ---------------------------------------------------------------------------

#: ``feature key -> (config knob, comparison, human phrasing)``.  Every one is
#: an ATTENTION measure that already exists in a producer artifact (Track C §2).
#: Share turnover is deliberately absent — no float data exists (contract §6).
_HOT_RULES: tuple[tuple[str, str, str, str], ...] = (
    ("dollar_vol_rank", "dollar_vol_rank_max", "<=", "dollar-volume rank {value:.0f} ≤ {knob:.0f}"),
    ("rel_volume", "rel_volume_min", ">=", "relative volume {value:.2f}× ≥ {knob:.2f}×"),
    ("rvol_tod", "rvol_tod_min", ">=", "intraday RVOL {value:.2f}× ≥ {knob:.2f}×"),
    ("realized_range_pct", "realized_range_pct_min", ">=",
     "realized range {value:.1f}% ≥ {knob:.1f}%"),
    ("gap_abs_pct", "gap_abs_pct_min", ">=", "overnight gap {value:.1f}% ≥ {knob:.1f}%"),
    ("momentum_20d_abs_pct", "momentum_20d_abs_pct_min", ">=",
     "20-session move {value:.1f}% ≥ {knob:.1f}%"),
)


def layer_c_admissions(cfg: Mapping[str, Any], *,
                       features: Mapping[str, Mapping[str, Any]] | None = None,
                       source_id: str = "stockdata:master",
                       source_status: str = "ok",
                       source_asof: datetime | None = None,
                       now: datetime | None = None) -> dict[str, list[AdmissionReason]]:
    """Layer C — admission on measured attention.  ADMITS, NEVER SCORES.

    Each satisfied rule is one admission reason with the measured value
    preserved for provenance.  The values are explicitly forbidden from
    entering any Radar score (contract §9: "admission-time attention levels
    never enter any score") — they are here to say *why we are looking*.
    """
    stamp = now or utcnow()
    knobs = {**DEFAULTS["layer_c"], **dict(cfg.get("layer_c") or {})}
    out: dict[str, list[AdmissionReason]] = {}
    if not knobs.get("enabled", True):
        return out
    for sym, row in (features or {}).items():
        key = str(sym).strip().upper()
        if not key or not isinstance(row, Mapping):
            continue
        for feat, knob_key, op, phrasing in _HOT_RULES:
            if feat not in row or row.get(feat) is None:
                continue
            try:
                value = float(row[feat])
                knob = float(knobs[knob_key])
            except (TypeError, ValueError, KeyError):
                continue
            hit = value <= knob if op == "<=" else value >= knob
            if not hit:
                continue
            out.setdefault(key, []).append(AdmissionReason(
                layer="C", source_id=source_id, reason_code=f"hot.{feat}",
                reason_text=phrasing.format(value=value, knob=knob),
                source_status=source_status, source_asof=source_asof, observed_at=stamp,
                detail={"feature": feat, "value": value, "threshold": knob,
                        "note": "attention admits; it never scores"}))
    return out


# ---------------------------------------------------------------------------
# Layer D — lobe nominations
# ---------------------------------------------------------------------------

def layer_d_admissions(bus: NominationBus, *, cfg: Mapping[str, Any] | None = None,
                       now: datetime | None = None) -> dict[str, list[AdmissionReason]]:
    """Layer D — every active nomination auto-admits its ticker.

    No threshold, no rank filter, no index-membership filter, no size filter
    (contract §0 P-6).  Provenance is preserved WHOLE: the admission reason
    carries the producer's identity and the nomination itself rides on the
    probe record intact.
    """
    stamp = now or utcnow()
    knobs = {**DEFAULTS["layer_d"], **dict((cfg or {}).get("layer_d") or {})}
    out: dict[str, list[AdmissionReason]] = {}
    if not knobs.get("auto_admit", True):
        return out
    for nom in bus.active(now=stamp):
        read = bus.reads.get(nom.source_id)
        out.setdefault(nom.ticker, []).append(AdmissionReason(
            layer="D", source_id=nom.source_id, reason_code=nom.reason_code,
            reason_text=nom.reason_text,
            source_status=(read.status if read is not None else "ok"),
            source_asof=nom.source_asof, observed_at=nom.observed_at,
            detail={"source_family": nom.source_family,
                    "source_horizon": nom.source_horizon,
                    "evidence_ref": nom.evidence_ref}))
    return out


# ---------------------------------------------------------------------------
# Probe Set assembly
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class ProbeSet:
    """The assembled Probe Set + its budget, availability and notes."""

    records: tuple[ProbeRecord, ...]
    assembled_at: datetime
    market_session: str
    budget: dict[str, Any]
    notes: tuple[dict[str, Any], ...] = ()
    availability: dict[str, Any] = field(default_factory=dict)
    layer_counts: dict[str, int] = field(default_factory=dict)
    eligibility_counts: dict[str, int] = field(default_factory=dict)
    nomination_summary: dict[str, Any] = field(default_factory=dict)
    universe: dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.records)

    def by_ticker(self) -> dict[str, ProbeRecord]:
        return {r.ticker: r for r in self.records}

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": PROBE_SET_SCHEMA,
            "authority": dict(AUTHORITY_BLOCK),
            "assembled_at": iso(self.assembled_at),
            "market_session": self.market_session,
            "n_probed": len(self.records),
            "budget": dict(self.budget),
            "notes": [dict(n) for n in self.notes],
            "layer_counts": dict(self.layer_counts),
            "eligibility_counts": dict(self.eligibility_counts),
            "universe": dict(self.universe),
            "availability": dict(self.availability),
            "nomination_summary": dict(self.nomination_summary),
            "probes": [r.to_dict() for r in self.records],
        }

    def summary_lines(self) -> list[str]:
        """Operator-readable assembly summary (the ``--dry-run`` body)."""
        layers = " ".join(f"{k}={self.layer_counts.get(k, 0)}" for k in ADMISSION_LAYERS)
        lines = [
            f"probe set        {len(self.records)} names   session={self.market_session}",
            f"eligible universe {self.universe.get('eligible', 0)} names "
            f"(Layer A is a LENS — it classifies, it never admits)",
            f"admission layers {layers}   [A = probed names Layer A vouches for]",
            "eligibility      " + " ".join(f"{k}={v}" for k, v in
                                           sorted(self.eligibility_counts.items())),
            f"budget           {self.budget.get('state')} "
            f"(target {self.budget.get('target_min')}–{self.budget.get('target_max')})",
            f"nominations      active={self.nomination_summary.get('n_active', 0)} "
            f"tickers={self.nomination_summary.get('n_tickers', 0)} "
            f"expired={self.nomination_summary.get('n_expired', 0)}",
        ]
        avail = self.availability or {}
        if avail.get("unavailable_sources"):
            lines.append("UNAVAILABLE      " + ", ".join(avail["unavailable_sources"]))
        if avail.get("stale_sources"):
            lines.append("STALE            " + ", ".join(avail["stale_sources"]))
        for note in self.notes:
            lines.append(f"note[{note.get('severity', 'info')}] {note.get('code')}: "
                         f"{note.get('text')}")
        return lines


def _prior_records(previous: ProbeSet | Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if previous is None:
        return {}
    if isinstance(previous, ProbeSet):
        return {r.ticker: r.to_dict() for r in previous.records}
    probes = previous.get("probes") if isinstance(previous, Mapping) else None
    out: dict[str, Mapping[str, Any]] = {}
    for row in probes or ():
        if isinstance(row, Mapping) and row.get("ticker"):
            out[str(row["ticker"]).strip().upper()] = row
    return out


def _retained_reasons(prior: Mapping[str, Any], unavailable: set[str], *,
                      now: datetime, retention_sessions: int
                      ) -> list[AdmissionReason]:
    """Reasons carried forward from an UNAVAILABLE producer — the retention rule."""
    out: list[AdmissionReason] = []
    for raw in prior.get("admission_reasons") or ():
        if not isinstance(raw, Mapping):
            continue
        source_id = str(raw.get("source_id") or "")
        if source_id not in unavailable:
            continue
        first_seen = parse_ts(raw.get("observed_at")) or now
        # Calendar-day proxy for sessions: the lane runs on session days, and a
        # weekend cannot age a reason past its retention without a session.
        try:
            from lib.nyse_calendar import sessions_strictly_between  # noqa: PLC0415
            aged = len(sessions_strictly_between(first_seen.date(), now.date()))
        except Exception:  # noqa: BLE001
            aged = max(0, (now.date() - first_seen.date()).days)
        if aged > max(0, int(retention_sessions)):
            continue
        layer = str(raw.get("layer") or "D")
        out.append(AdmissionReason(
            layer=layer if layer in ADMISSION_LAYERS else "D",
            source_id=source_id,
            reason_code=str(raw.get("reason_code") or "retained.unavailable_producer"),
            reason_text=str(raw.get("reason_text") or "retained across a producer outage"),
            source_status="unavailable",
            source_asof=parse_ts(raw.get("source_asof")),
            observed_at=first_seen,
            detail={**(dict(raw.get("detail") or {})),
                    "retained_reason": "producer unavailable — silence is not evidence of "
                                       "absence (contract §5)",
                    "retained_sessions": aged,
                    "retention_budget_sessions": int(retention_sessions)},
            retained_stale=True))
    return out


def assemble_probe_set(*, layer_a: LayerAResult,
                       bus: NominationBus,
                       cfg: Mapping[str, Any] | None = None,
                       memberships: Mapping[str, Sequence[str]] | None = None,
                       liquidity: Mapping[str, Mapping[str, Any]] | None = None,
                       watchlist: ProducerRead | None = None,
                       hot_features: Mapping[str, Mapping[str, Any]] | None = None,
                       hot_source_id: str = "stockdata:master",
                       hot_read: ProducerRead | None = None,
                       history_age: Mapping[str, int] | None = None,
                       previous: ProbeSet | Mapping[str, Any] | None = None,
                       market_session: str = "",
                       now: datetime | None = None) -> ProbeSet:
    """Union Layers A–D into the Probe Set.

    Layer A is the ELIGIBILITY LENS, not a membership requirement: a Layer-D
    lobe nomination for a name Layer A never heard of is still admitted (that
    is the whole point of P-6), classified fail-closed as ``unclassified``, and
    flagged.  Only a name Layer A positively classifies as ``wrapper_excluded``
    is held out of the probe set — and it is held out *with* its
    classification, never silently.
    """
    stamp = now or utcnow()
    cfg = dict(cfg or load_config())
    retention = {**DEFAULTS["retention"], **dict(cfg.get("retention") or {})}
    budget_cfg = {**DEFAULTS["probe_set"], **dict(cfg.get("probe_set") or {})}

    reasons: dict[str, list[AdmissionReason]] = {}

    def _merge(block: Mapping[str, Sequence[AdmissionReason]]) -> None:
        for sym, rows in block.items():
            reasons.setdefault(sym, []).extend(rows)

    # LAYER A IS A LENS, NOT A DOOR.  It classifies eligibility and excludes
    # wrappers; it does not admit.  Admitting every eligible name would make the
    # Probe Set identical to the broad universe (~2,966 in production), leave
    # B/C/D contributing nothing, blow the 500-1500 budget on every single pass,
    # and fire the escalation warning unconditionally — an alarm that is always
    # on is not an alarm.  Membership is B ∪ C ∪ D.
    eligible = set(layer_a.probeable())

    _merge(layer_b_admissions(cfg, memberships=memberships, liquidity=liquidity,
                              watchlist=watchlist, now=stamp))
    _merge(layer_c_admissions(cfg, features=_with_dollar_vol_rank(hot_features),
                              source_id=hot_source_id,
                              source_status=(hot_read.status if hot_read else "ok"),
                              source_asof=(hot_read.source_asof if hot_read else None),
                              now=stamp))
    _merge(layer_d_admissions(bus, cfg=cfg, now=stamp))

    availability = bus.availability()
    unavailable = set(availability.get("unavailable_sources") or ())
    if watchlist is not None and watchlist.status == "unavailable":
        unavailable.add(watchlist.source_id)
    for src in layer_a.sources:
        if src.status != "ok":
            # The outage key MUST equal the source_id the reasons that source
            # created carry, or retention can never match it and a single failed
            # index read EMPTIES the probe set — the O(1000)-shrink incident this
            # module's docstring cites, reproduced exactly.
            unavailable.add(universe_source_id(src.key))

    prior = _prior_records(previous)
    retained_names: list[str] = []
    if unavailable:
        for sym, row in prior.items():
            carried = _retained_reasons(row, unavailable, now=stamp,
                                        retention_sessions=retention.get(
                                            "unavailable_retention_sessions", 3))
            if not carried:
                continue
            have = {(r.source_id, r.reason_code) for r in reasons.get(sym, ())}
            new = [r for r in carried if (r.source_id, r.reason_code) not in have]
            if new:
                reasons.setdefault(sym, []).extend(new)
                retained_names.append(sym)

    # Wrapper exclusion is the ONLY hard drop, and it is a classified drop.
    excluded = {sym for sym, v in layer_a.eligibility.items()
                if v.state == "wrapper_excluded"}
    dropped_wrappers = sorted(excluded & set(reasons))
    for sym in dropped_wrappers:
        reasons.pop(sym, None)

    noms_by_ticker = bus.by_ticker(now=stamp)
    records: list[ProbeRecord] = []
    # ``A`` is NOT an admission count — Layer A admits nobody.  It reports how
    # many PROBED names the broad-eligibility universe actually vouches for; the
    # gap between it and n_probed is the lobe-nominated tail Layer A never heard
    # of, which is precisely the population gate P-6 exists to protect.
    layer_counts: dict[str, int] = {k: 0 for k in ADMISSION_LAYERS}
    for sym in sorted(reasons):
        rows = reasons[sym]
        layers = tuple(sorted({r.layer for r in rows}))
        for layer in layers:
            layer_counts[layer] = layer_counts.get(layer, 0) + 1
        if sym in eligible:
            layer_counts["A"] = layer_counts.get("A", 0) + 1
        verdict = layer_a.eligibility.get(sym) or classify_eligibility(sym)
        prior_row = prior.get(sym) or {}
        first_at = parse_ts(prior_row.get("first_admitted_at")) or stamp
        noms = tuple(noms_by_ticker.get(sym) or ())
        statuses = {r.source_status for r in rows}
        asofs = [r.source_asof for r in rows if r.source_asof is not None]
        quality = "ok"
        if "unavailable" in statuses or verdict.state == "unclassified":
            quality = "degraded"
        elif "stale" in statuses:
            quality = "degraded"
        records.append(ProbeRecord(
            ticker=sym,
            admission_layers=layers,
            admission_reasons=tuple(rows),
            eligibility=verdict.state,
            history_age_sessions=(history_age or {}).get(sym),
            first_admitted_at=first_at,
            last_refreshed_at=stamp,
            freshness={
                "computed_at": iso(stamp),
                "oldest_source_asof": iso(min(asofs)) if asofs else None,
                "newest_source_asof": iso(max(asofs)) if asofs else None,
                "stale_reasons": sorted({r.source_id for r in rows
                                         if r.source_status == "stale"}),
                "unavailable_reasons": sorted({r.source_id for r in rows
                                               if r.source_status == "unavailable"}),
                "retained_stale": any(r.retained_stale for r in rows),
                "eligibility_confidence": verdict.confidence,
            },
            data_quality=quality,
            nominations=noms,
        ))

    notes: list[dict[str, Any]] = []
    n = len(records)
    target_min = int(budget_cfg.get("target_min", 500))
    target_max = int(budget_cfg.get("target_max", 1500))
    state = "within"
    if n > target_max:
        state = "exceeded"
        msg = (f"{n} names admitted vs a {target_max} soft budget — every name is probed; "
               "NOTHING truncated. Escalate the compute budget (contract §6).")
        notes.append({"code": "budget_exceeded", "severity": "warning", "text": msg,
                      "n_probed": n, "target_max": target_max})
        print(f"::warning title=entry-radar-budget::{msg}", flush=True)
    elif n < target_min:
        state = "below"
        notes.append({"code": "budget_below_target", "severity": "notice",
                      "text": f"{n} names admitted vs a {target_min} soft floor — check the "
                              "Layer-A source audit before reading this as a quiet tape.",
                      "n_probed": n, "target_min": target_min})
    if unavailable:
        n_retained = len(set(retained_names))
        notes.append({"code": "producers_unavailable", "severity": "warning",
                      "text": "Unavailable producers: " + ", ".join(sorted(unavailable)) +
                              f" — {n_retained} prior member(s) retained under the "
                              "outage-retention rule (missing is not negative, §5).",
                      "sources": sorted(unavailable), "retained_names": n_retained})
    if dropped_wrappers:
        notes.append({"code": "wrapper_excluded", "severity": "notice",
                      "text": f"{len(dropped_wrappers)} name(s) classified as wrappers and "
                              "held out WITH classification (never silently dropped).",
                      "tickers": dropped_wrappers[:50]})
    unclassified = [r.ticker for r in records if r.eligibility == "unclassified"]
    if unclassified:
        notes.append({"code": "unclassified_present", "severity": "notice",
                      "text": f"{len(unclassified)} name(s) could not be classified and are "
                              "probed WITH a fail-closed 'unclassified' flag.",
                      "tickers": unclassified[:50]})

    if not market_session:
        print("::warning title=entry-radar::no market_session supplied — stamping the "
              "artifact with the UTC date, which is NOT the NYSE session for an "
              "after-hours or holiday caller; pass one from lib.nyse_calendar",
              flush=True)
    return ProbeSet(
        records=tuple(records),
        assembled_at=stamp,
        market_session=market_session or stamp.date().isoformat(),
        budget={"target_min": target_min, "target_max": target_max,
                "n_probed": n, "state": state, "truncated": False},
        notes=tuple(notes),
        availability={
            **availability,
            "universe_sources": [s.to_dict() for s in layer_a.sources],
            "watchlist": watchlist.to_dict() if watchlist is not None else None,
            "hot_features": hot_read.to_dict() if hot_read is not None else None,
        },
        layer_counts=layer_counts,
        eligibility_counts=layer_a.counts(),
        nomination_summary=bus.summary(now=stamp),
        universe={
            "eligible": len(eligible),
            "probed_outside_eligible": sorted(set(reasons) - eligible)[:50],
            "n_probed_outside_eligible": len(set(reasons) - eligible),
            "note": "membership is B∪C∪D; Layer A classifies eligibility and "
                    "excludes wrappers, it does not admit",
        },
    )


def matches_any(ticker: str, patterns: Sequence[str]) -> bool:
    """Small glob helper for operator include/exclude lists."""
    sym = str(ticker or "").strip().upper()
    return any(fnmatch.fnmatch(sym, str(p).strip().upper()) for p in patterns or ())
