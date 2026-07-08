"""HK Washout Watch — ignition organ for the stock-board revamp (display-tier).

Surfaces per-name CONFLUENCE evidence when a deep-decline high-beta name shows
ignition signals. The existing board hard-excludes cycle-blocked/DECLINE names;
in risk-off the whole board can be empty (eligible: 0). This organ operates on
the FULL entry list so washout candidates with confluence are VISIBLE even when
the main board is dark.

DOCTRINE
--------
- DISPLAY-ONLY / CONTEXT.  Not a validated buy signal.  HK selection alpha is
  weak/dead — do NOT claim otherwise.  This organ detects CONFLUENCE: ≥2
  independent context organs aligning on the same washout name.
- Aggressive-early tuning (operator's explicit choice): K=2 threshold.  Fire
  early; log every fire to the forward ledger; false starts are expected and
  visible as CONTEXT chips.
- Falling-knife names KEPT with a visible `knife_risk: True` chip.
- No LLM-originated score / escalation.
- ADDITIVE + FAIL-OPEN: never raises; never mutates the existing board dict.

STATE LADDER
------------
washout_watch       candidate + ≥1 confluence signal
ignition_watch      candidate + ≥2 confluence INCLUDING oversold-reclaim
pullback_entry_watch was igniting + now controlled pullback (lower RSI re-test)
chase_risk          was igniting + now extended (RSI hot / gapped-up too far)
invalidated         dilution veto / failed thrust / reversal — dropped from list

SIX CONFLUENCE ORGANS (each fail-open — missing organ = signal absent)
-----------------------------------------------------------------------
1. hk_adr_bridge    implied_open_gap_pct > 0   → ADR_GAP_UP  +1
2. hk_cbbc          leverage_state = bear_skew* → BEAR_EXHAUST +1
   (* bear_skew or bear_skew_froth = bears crowded, squeeze risk)
3. hk_filing_bus    recent buyback_flag         → BUYBACK      +1
                    recent dilution_flag        → DILUTION_VETO (blocks ignition)
4. hk_narrative     attention_shock_z elevated + tone turning up → NARRATIVE +1
5. hk_southbound_stocks  accum_z turning positive               → SB_ACCUM  +1
6. price            RSI oversold AND turning up (reclaim)       → RSI_RECLAIM +1

LEDGER
------
data/hk_impulse/washout_watch_ledger.jsonl
Append-only, atomic temp+rename, idempotent on (ticker, date).
Gated by CN_LANE=asia (house law: nightly sole advancer).
Grade step stamps asymmetric outcome fields when forward data is available.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lane guard (same pattern as all HK organs)
# ---------------------------------------------------------------------------

def _ledger_advance_enabled() -> bool:
    """True only when running in the asia-close nightly lane (CN_LANE=asia)."""
    return os.environ.get("CN_LANE", "").lower() == "asia"


# ---------------------------------------------------------------------------
# Candidacy thresholds
# ---------------------------------------------------------------------------

# A name is a washout candidate when ANY of these fire (OR logic, aggressive):
#   - cycle_blocked/DECLINE (excluded by _entry_ok in the main board)
#   - dist_200dma <= PCT_BELOW_200DMA_THRESH (deep below 200dma)
#   - rsi <= RSI_OVERSOLD (oversold RSI)
PCT_BELOW_200DMA_THRESH = -0.12   # 12% below 200dma
RSI_OVERSOLD            = 40.0    # RSI <= 40 → oversold
RSI_EXTENDED            = 70.0    # RSI >= 70 → extended (chase_risk)

# RSI reclaim = was oversold, now turning; threshold for "turning up"
RSI_RECLAIM_MIN   = 30.0   # was at least this oversold
RSI_RECLAIM_MAX   = 50.0   # now recovered to at most this (≥30 but ≤50 = valid reclaim zone)

# Confluence thresholds (K=2, aggressive tuning)
CONFLUENCE_WATCH   = 1   # ≥1 → washout_watch
CONFLUENCE_IGNITE  = 2   # ≥2 INCLUDING reclaim → ignition_watch

# Attention shock threshold for the narrative organ
NARRATIVE_SHOCK_Z_MIN  = 1.5
NARRATIVE_TONE_MIN_PCT = 55.0   # tone_pctile > this = turning up

# Southbound accumulation threshold
SB_ACCUM_Z_MIN = 0.3   # accum_z > this → SB accumulating (low bar: aggressive)

# ADR gap threshold for ignition signal
ADR_GAP_UP_MIN_PCT = 0.5   # implied_open_gap_pct > 0.5% = gap up

# Falling-knife: deepest trailing-3M-return quintile (alpha z ≤ P20)
# We reuse the enriched entry list's alpha field + build a simple quintile.
import statistics as _stats


# ---------------------------------------------------------------------------
# Ledger path helper (mirrors hk_adr_bridge/hk_cbbc pattern)
# ---------------------------------------------------------------------------

_LEDGER_DIR  = "hk_impulse"
_LEDGER_FILE = "washout_watch_ledger.jsonl"


def _ledger_path(data_root: Path | None = None) -> Path:
    from lib import config
    root = data_root if data_root is not None else config.data_dir()
    return root / _LEDGER_DIR / _LEDGER_FILE


def load_ledger(data_root: Path | None = None) -> list[dict]:
    """Load all ledger rows. Returns [] if file missing/corrupt."""
    p = _ledger_path(data_root)
    if not p.exists():
        return []
    out: list[dict] = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _write_ledger(rows: list[dict], data_root: Path | None = None) -> None:
    """Write ledger atomically via temp-file + os.replace (same pattern as sibling organs)."""
    p = _ledger_path(data_root)
    p.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(r, default=str) for r in rows)
    if content:
        content += "\n"
    fd, tmp_path = tempfile.mkstemp(dir=p.parent, prefix=".washout_watch_ledger_tmp_")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        os.replace(tmp_path, p)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def stamp_ledger(
    watch_rows: list[dict],
    as_of: str | None = None,
    data_root: Path | None = None,
) -> int:
    """Append one row per new (ticker, date) fire.

    Idempotent on (ticker, date). Gated by CN_LANE=asia. Never raises.
    Returns count of appended rows.
    """
    if not _ledger_advance_enabled():
        log.debug("hk_washout_watch.stamp_ledger: skipped (CN_LANE != asia)")
        return 0
    if not watch_rows:
        return 0
    today_str = as_of or date.today().isoformat()
    try:
        rows = load_ledger(data_root)
        existing = {(r.get("ticker"), r.get("date")) for r in rows}
        appended = 0
        for w in watch_rows:
            key = (w.get("ticker"), today_str)
            if key in existing:
                continue
            rows.append({
                "date":              today_str,
                "ticker":            w.get("ticker"),
                "state":             w.get("state"),
                "confluence_count":  w.get("confluence_count"),
                "confluence_signals": w.get("confluence_signals", []),
                "knife_risk":        w.get("knife_risk", False),
                "price":             w.get("price"),
                "rsi":               w.get("rsi"),
                "dist_200dma":       w.get("dist_200dma"),
                "asof_freshness":    w.get("asof_freshness"),
                # Asymmetric outcome fields — blank at fire time, graded forward:
                "fwd_max_return":    None,   # MFE
                "fwd_min_return":    None,   # MAE
                "days_to_local_low": None,   # timing error
                "max_adverse_after_peak": None,
                "graded_at":         None,
            })
            existing.add(key)
            appended += 1
        if appended:
            _write_ledger(rows, data_root)
        return appended
    except Exception as e:  # noqa: BLE001
        log.warning("hk_washout_watch.stamp_ledger failed: %s", e)
        return 0


def grade_ledger(data_root: Path | None = None) -> int:
    """Grade matured ledger rows with asymmetric outcome fields.

    Checks rows where fwd_max_return is None and enough calendar time has
    passed to read forward returns from stored price data. Writes graded rows
    back atomically. Returns count of newly graded rows.

    This is a best-effort accumulation step; it never raises.
    """
    # Grading is future work — the schema is pre-registered here so the
    # forward ledger accrues the correct shape from day one. The actual
    # grade fn will be added once ≥21 calendar days of fires exist.
    return 0


# ---------------------------------------------------------------------------
# Organ signal readers (each fail-open — exception = signal absent)
# ---------------------------------------------------------------------------

def _read_adr_signals(organ_signals: dict) -> dict[str, Any]:
    """Extract per-HK-ticker implied gap from the adr_bridge snapshot.

    Returns {hk_ticker: gap_pct} for tickers with a positive gap.
    """
    out: dict[str, Any] = {}
    try:
        adr_snap = organ_signals.get("adr_bridge") or {}
        for entry in adr_snap.get("names", []):
            tk = entry.get("hk_ticker")
            gap = entry.get("implied_open_gap_pct")
            if tk and gap is not None:
                out[tk] = gap
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: adr_bridge read failed (%s)", e)
    return out


def _read_cbbc_signals(organ_signals: dict) -> dict[str, str]:
    """Extract leverage_state per HK ticker from cbbc snapshot.

    Returns {hk_ticker: leverage_state}.
    """
    out: dict[str, str] = {}
    try:
        cbbc_snap = organ_signals.get("cbbc") or {}
        for entry in cbbc_snap.get("bellwethers", []):
            tk = entry.get("ticker")
            ls = entry.get("leverage_state")
            if tk and ls:
                out[tk] = ls
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: cbbc read failed (%s)", e)
    return out


def _read_filing_signals(organ_signals: dict) -> dict[str, dict]:
    """Extract buyback_flag / dilution_flag per ticker from filing_bus snapshot.

    Returns {ticker: {buyback: bool, dilution: bool}}.
    """
    out: dict[str, dict] = {}
    try:
        filing_snap = organ_signals.get("filing_bus") or {}
        for bw in filing_snap.get("bellwethers", []):
            tk = bw.get("ticker")
            if not tk:
                continue
            out[tk] = {
                "buyback":  bool(bw.get("has_buyback", False)),
                "dilution": bool(bw.get("has_dilution", False)),
            }
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: filing_bus read failed (%s)", e)
    return out


def _read_narrative_signals(organ_signals: dict) -> dict[str, dict]:
    """Extract attention_shock_z + tone_pctile per ticker from narrative snapshot.

    Returns {ticker: {shock_z: float|None, tone_pctile: float|None}}.
    """
    out: dict[str, dict] = {}
    try:
        narrative_snap = organ_signals.get("narrative") or {}
        for ent in narrative_snap.get("entities", []):
            tk = ent.get("ticker")
            if not tk:
                continue
            out[tk] = {
                "shock_z":    ent.get("attention_shock_z"),
                "tone_pctile": ent.get("tone_pctile"),
            }
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: narrative read failed (%s)", e)
    return out


def _read_southbound_signals(organ_signals: dict) -> dict[str, float]:
    """Extract accum_z per ticker from southbound snapshot.

    Returns {ticker: accum_z}.
    """
    out: dict[str, float] = {}
    try:
        sb_snap = organ_signals.get("southbound") or {}
        # southbound signal() returns dict[ticker, {accum_z, ...}]
        # or may be stored as a dict keyed by ticker directly
        for tk, val in sb_snap.items():
            if isinstance(val, dict):
                az = val.get("accum_z")
                if az is not None:
                    out[tk] = float(az)
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: southbound read failed (%s)", e)
    return out


def _read_catalyst_signals(organ_signals: dict, ticker: str, as_of: str | None) -> bool:
    """Check if there is an imminent scheduled catalyst for this ticker.

    Returns True when an imminent catalyst in the calendar window affects
    the ticker (index or sector level — the catalyst calendar is index-level
    so we treat any imminent catalyst as a context signal for all names).
    """
    try:
        cat_snap = organ_signals.get("catalyst_calendar") or {}
        for ev in cat_snap.get("events", []):
            if ev.get("imminent"):
                return True
    except Exception as e:  # noqa: BLE001
        log.debug("hk_washout_watch: catalyst read for %s failed (%s)", ticker, e)
    return False


# ---------------------------------------------------------------------------
# RSI / price helpers
# ---------------------------------------------------------------------------

def _rsi_reclaim(rsi: float | None) -> bool:
    """True when RSI is in the reclaim zone (was oversold, now recovering).

    Aggressive tuning: RSI_RECLAIM_MIN .. RSI_RECLAIM_MAX is [30, 50].
    """
    if rsi is None:
        return False
    return RSI_RECLAIM_MIN <= rsi <= RSI_RECLAIM_MAX


def _rsi_oversold(rsi: float | None) -> bool:
    if rsi is None:
        return False
    return rsi <= RSI_OVERSOLD


def _rsi_extended(rsi: float | None) -> bool:
    if rsi is None:
        return False
    return rsi >= RSI_EXTENDED


# ---------------------------------------------------------------------------
# Candidacy test
# ---------------------------------------------------------------------------

def _is_washout_candidate(e: dict) -> bool:
    """True if the entry is a washout candidate (OR logic across three criteria)."""
    c = e.get("conviction") or {}
    if c.get("cycle_blocked"):
        return True

    # Cycle label includes DECLINE / FALL phase
    label = str(e.get("label") or "").upper()
    if any(kw in label for kw in ("DECLINE", "FALL", "DOWNTREND", "BEAR")):
        return True

    # Deep below 200dma
    # dist_200dma from enriched entry (tech field off_high is % off 52w high;
    # the 200dma distance comes from a different field if present, else we use
    # a fallback: compare price vs the moving average embedded in conviction axes)
    dist = e.get("dist_200dma")
    if dist is None:
        # Try to derive from price & 200dma if available
        rec = e.get("_rec") or {}
        tech = rec.get("tech") or {}
        price = tech.get("price") or e.get("price")
        ma200 = tech.get("ma200")
        if price and ma200 and float(ma200) > 0:
            dist = float(price) / float(ma200) - 1.0
    if dist is not None and dist <= PCT_BELOW_200DMA_THRESH:
        return True

    # Oversold RSI
    rsi = e.get("rsi")
    if _rsi_oversold(rsi):
        return True

    return False


# ---------------------------------------------------------------------------
# Per-name confluence fusion
# ---------------------------------------------------------------------------

def _confluence_for(
    ticker: str,
    e: dict,
    adr_map: dict,
    cbbc_map: dict,
    filing_map: dict,
    narrative_map: dict,
    sb_map: dict,
    organ_signals: dict,
    as_of: str | None,
) -> tuple[int, list[str], bool]:
    """Compute confluence count, signal list, and dilution-veto flag for one name.

    Returns (count, signals, has_dilution_veto).
    count: number of positive confluence signals
    signals: list of signal-name strings that fired
    has_dilution_veto: True when a dilution event is active (blocks ignition)
    """
    signals: list[str] = []
    has_dilution_veto = False
    rsi = e.get("rsi")

    # --- Organ 1: ADR gap up ---
    try:
        gap = adr_map.get(ticker)
        if gap is not None and float(gap) >= ADR_GAP_UP_MIN_PCT:
            signals.append("ADR_GAP_UP")
    except Exception:  # noqa: BLE001
        pass

    # --- Organ 2: CBBC bear exhaustion ---
    try:
        ls = cbbc_map.get(ticker)
        if ls in ("bear_skew", "bear_skew_froth"):
            signals.append("BEAR_EXHAUST")
    except Exception:  # noqa: BLE001
        pass

    # --- Organ 3: Filing — buyback (positive) and dilution (veto) ---
    try:
        filing = filing_map.get(ticker) or {}
        if filing.get("dilution"):
            has_dilution_veto = True
        if filing.get("buyback"):
            signals.append("BUYBACK")
    except Exception:  # noqa: BLE001
        pass

    # --- Organ 4: Narrative attention + tone turning up ---
    try:
        narr = narrative_map.get(ticker) or {}
        shock_z = narr.get("shock_z")
        tone_p = narr.get("tone_pctile")
        if (shock_z is not None and float(shock_z) >= NARRATIVE_SHOCK_Z_MIN
                and tone_p is not None and float(tone_p) >= NARRATIVE_TONE_MIN_PCT):
            signals.append("NARRATIVE")
    except Exception:  # noqa: BLE001
        pass

    # --- Organ 5: Southbound accumulation reversal ---
    try:
        az = sb_map.get(ticker)
        if az is not None and float(az) >= SB_ACCUM_Z_MIN:
            signals.append("SB_ACCUM")
    except Exception:  # noqa: BLE001
        pass

    # --- Organ 6: RSI/StochRSI oversold + reclaim ---
    try:
        if _rsi_reclaim(rsi):
            signals.append("RSI_RECLAIM")
    except Exception:  # noqa: BLE001
        pass

    # --- Context: imminent catalyst (worth +0.5; add as context, not a full count) ---
    try:
        if _read_catalyst_signals(organ_signals, ticker, as_of):
            signals.append("CATALYST_CONTEXT")
    except Exception:  # noqa: BLE001
        pass

    # Count excludes the context chip (CATALYST_CONTEXT is context, not a full +1)
    count = sum(1 for s in signals if s != "CATALYST_CONTEXT")

    return count, signals, has_dilution_veto


# ---------------------------------------------------------------------------
# State assignment
# ---------------------------------------------------------------------------

def _assign_state(
    e: dict,
    confluence_count: int,
    signals: list[str],
    has_dilution_veto: bool,
) -> str | None:
    """Assign the ignition state label, or None if the candidate should be invalidated/dropped.

    Returns state string or None (dropped).
    """
    rsi = e.get("rsi")

    # Dilution veto blocks ignition outright
    if has_dilution_veto:
        return "invalidated"

    # Not enough confluence → not on the strip
    if confluence_count < CONFLUENCE_WATCH:
        return None

    # Chase risk: RSI extended (jumped too far)
    if _rsi_extended(rsi):
        return "chase_risk"

    # ignition_watch requires ≥2 confluence INCLUDING the oversold-reclaim
    if confluence_count >= CONFLUENCE_IGNITE and "RSI_RECLAIM" in signals:
        return "ignition_watch"

    # pullback_entry_watch: was igniting, now a controlled pullback re-test.
    # Detect via: ≥2 confluence but RSI has dipped back below reclaim zone
    # (oversold again after having been in reclaim — a re-test).
    if confluence_count >= CONFLUENCE_IGNITE and _rsi_oversold(rsi):
        return "pullback_entry_watch"

    # washout_watch: ≥1 confluence
    return "washout_watch"


# ---------------------------------------------------------------------------
# Entry hint (plain-text, bilingual)
# ---------------------------------------------------------------------------

def _entry_hint(state: str, rsi: float | None, dist_200dma: float | None) -> dict:
    """Bilingual entry context hint for the UI card."""
    if state == "ignition_watch":
        return {
            "en": "Oversold + reclaim underway · unconfirmed · wait for follow-through",
            "zh": "超卖中 + 反抽启动 · 未确认 · 等待跟进确认",
        }
    if state == "washout_watch":
        return {
            "en": "Confluence building · no reclaim yet · monitoring",
            "zh": "共振积累中 · 尚未反抽 · 持续观察",
        }
    if state == "pullback_entry_watch":
        return {
            "en": "Re-testing lows after ignition — controlled pullback",
            "zh": "点火后回测低位 — 受控回调",
        }
    if state == "chase_risk":
        return {
            "en": "Extended — do not chase (RSI hot / gapped too far)",
            "zh": "过热 — 勿追涨（RSI 高位 / 跳空过大）",
        }
    return {"en": "Invalidated — dilution or reversal", "zh": "已失效 — 稀释或反转"}


# ---------------------------------------------------------------------------
# Knife quintile helper
# ---------------------------------------------------------------------------

def _knife_quintile_cut(entries: list[dict]) -> float | None:
    """Compute the P20 alpha cut from the full entry universe."""
    alphas = [e.get("alpha") for e in entries if e.get("alpha") is not None]
    if len(alphas) < 5:
        return None
    try:
        return _stats.quantiles(alphas, n=5, method="inclusive")[0]
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# dist_200dma derivation
# ---------------------------------------------------------------------------

def _derive_dist_200dma(e: dict) -> float | None:
    """Try to extract distance to 200dma from entry fields."""
    dist = e.get("dist_200dma")
    if dist is not None:
        return dist
    # Try from _rec tech fields (only available before bulk-pop)
    try:
        rec = e.get("_rec") or {}
        tech = rec.get("tech") or {}
        price = tech.get("price") or e.get("price")
        ma200 = tech.get("ma200")
        if price and ma200 and float(ma200) > 0:
            return round(float(price) / float(ma200) - 1.0, 4)
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Main public API
# ---------------------------------------------------------------------------

def compute(
    entries: list[dict],
    organ_signals: dict,
    risk_state: str | None = None,
    as_of: str | None = None,
    data_root: Path | None = None,
) -> dict:
    """Compute the HK Washout Watch ignition organ.

    Parameters
    ----------
    entries:
        The FULL per-name enriched list (NOT filtered by _entry_ok).  Washout
        candidates are exactly the names that _entry_ok would exclude.
    organ_signals:
        Dict of pre-computed organ snapshots, keyed by organ name.  Each
        organ is read fail-open; a missing key means that organ's signals
        are simply absent.  Expected keys (all optional):
          "adr_bridge"         → hk_adr_bridge.snapshot()
          "cbbc"               → hk_cbbc.run()
          "filing_bus"         → hk_filing_bus.run()
          "narrative"          → hk_narrative.snapshot()
          "southbound"         → hk_southbound_stocks.signal() (dict[ticker, dict])
          "catalyst_calendar"  → {"events": [catalyst_events(...)]}
    risk_state:
        "risk_off" | "neutral" | "risk_on" — context label (unused in the
        compute logic; stamped on the ledger for context).
    as_of:
        ISO date string for the ledger stamp.
    data_root:
        Override data root (for testing).

    Returns
    -------
    dict with keys:
        washout_watch   : list of candidate dicts
        display_only    : True
    Never raises.
    """
    try:
        return _compute_inner(entries, organ_signals, risk_state, as_of, data_root)
    except Exception as e:  # noqa: BLE001
        log.error("hk_washout_watch.compute crashed (%s) — returning empty list", e)
        return {"washout_watch": [], "display_only": True}


def _compute_inner(
    entries: list[dict],
    organ_signals: dict,
    risk_state: str | None,
    as_of: str | None,
    data_root: Path | None,
) -> dict:
    if not entries:
        return {"washout_watch": [], "display_only": True}

    # Build organ signal maps (each fail-open)
    adr_map       = _read_adr_signals(organ_signals)
    cbbc_map      = _read_cbbc_signals(organ_signals)
    filing_map    = _read_filing_signals(organ_signals)
    narrative_map = _read_narrative_signals(organ_signals)
    sb_map        = _read_southbound_signals(organ_signals)

    # Knife quintile cut over the full universe
    knife_cut = _knife_quintile_cut(entries)

    result: list[dict] = []

    for e in entries:
        ticker = e.get("ticker")
        if not ticker:
            continue

        try:
            # Is this a washout candidate?
            if not _is_washout_candidate(e):
                continue

            rsi = e.get("rsi")
            price = e.get("price")
            dist_200dma = _derive_dist_200dma(e)

            # Confluence fusion
            confluence_count, signals, has_dilution_veto = _confluence_for(
                ticker, e, adr_map, cbbc_map, filing_map,
                narrative_map, sb_map, organ_signals, as_of,
            )

            # State assignment
            state = _assign_state(e, confluence_count, signals, has_dilution_veto)

            # Drop invalidated names and those with no state
            if state is None or state == "invalidated":
                continue

            # Knife risk: deepest-quintile 3M loser — KEEP but stamp
            alpha = e.get("alpha")
            knife_risk = bool(
                alpha is not None and knife_cut is not None and alpha <= knife_cut
            )

            entry_hint = _entry_hint(state, rsi, dist_200dma)

            row: dict = {
                "ticker":            ticker,
                "name":              e.get("name"),
                "state":             state,
                "confluence_count":  confluence_count,
                "confluence_signals": signals,
                "knife_risk":        knife_risk,
                "dist_200dma":       dist_200dma,
                "rsi":               rsi,
                "price":             price,
                "entry_hint":        entry_hint,
                "display_only":      True,
                # Extra context fields for the card
                "sector":            e.get("sector"),
                "sector_zh":         e.get("sector_zh"),
                "dir":               e.get("dir"),
                "label":             e.get("label"),
                "label_zh":          e.get("label_zh"),
                "asof_freshness":    as_of,
            }
            result.append(row)

        except Exception as ex:  # noqa: BLE001 — one bad name must never abort the rest
            log.debug("hk_washout_watch: entry %s failed (%s)", ticker, ex)
            continue

    # Sort: ignition_watch first, then washout_watch, then others
    _STATE_ORDER = {
        "ignition_watch":      0,
        "pullback_entry_watch": 1,
        "washout_watch":       2,
        "chase_risk":          3,
    }
    result.sort(
        key=lambda r: (
            _STATE_ORDER.get(r["state"], 9),
            -(r.get("confluence_count") or 0),
        )
    )

    # Stamp the forward ledger (CN_LANE=asia gate inside stamp_ledger)
    try:
        n = stamp_ledger(result, as_of=as_of, data_root=data_root)
        if n:
            log.info("hk_washout_watch: stamped %d rows to ledger", n)
    except Exception as ex:  # noqa: BLE001 — ledger write never breaks the render
        log.warning("hk_washout_watch: ledger stamp failed (%s)", ex)

    return {"washout_watch": result, "display_only": True}
