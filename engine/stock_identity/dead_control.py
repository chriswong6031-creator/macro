"""W3S Dead Instrument Control Set — deterministic cohort builder.

Registration: ``research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md``
(operation ``SI-W3S-DEAD-CONTROL-V1``). That file is the LAW; this module only
executes it. The screen ladder, the exclusion codes, the deterministic ordering and
the 252-session floor are fixed there and may not be retuned here.

WHY THIS EXISTS. W5/Q1 survivorship needs a control set of instruments that actually
STOPPED EXISTING. Every cheap proxy for "dead" is wrong in a way that silently
inverts the science:

  * ``collectors.edgar_deadnames.dead_universe()`` selects on a CLOSED S&P membership
    row, which is an INDEX EXIT. 172 of its 1,083 names still trade today, so reading
    it as a death list builds a control set out of living companies.
  * Absence from the exchange symbol directory means "not exchange-listed", which is
    the NORMAL, LIVE state of an OTC ADR (ANGPY/IMPUY/RHHBY). Absence alone is not death.
  * A vendor "possibly delisted" flag is a hint. Yahoo says exactly that about a live
    security whose symbol merely changed.
  * A tape that simply stops is a stale feed, a halt, or a fetch bound — not a death.
  * Worst: a vendor may SPLICE the acquirer's continuing series onto the dead symbol
    (the documented AVB case), so the tape runs happily past the terminal date and
    looks like a survivor. ``plane.load_symbol`` does NOT truncate at ``last_session``,
    so a contaminated parquet reaches the behavioral layer intact.

So termination is proven on TWO independent axes and the tape is then checked against
that proof, rather than trusted.

The permitted bounded source act (Sol) is OWNER REUSE: no new provider, no second
price plane, no new identity authority. Every fact below comes from a store this repo
already owns.
"""
from __future__ import annotations

import glob
import hashlib
import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from . import hygiene, plane

log = logging.getLogger(__name__)

#: Registration §2 — binding history floor (fingerprint.MIN_SESSIONS).
MIN_SESSIONS = 252

#: Registration §4 S8 — a terminated tape may not carry real bars past its proven
#: terminal date. Directory snapshots are not daily (a 9-day gap is observed in the
#: current store), so the terminal date is only known to within the snapshot cadence;
#: this grace absorbs that quantization, never a splice. A successor splice runs for
#: weeks and is caught regardless.
TERMINAL_GRACE_SESSIONS = 10

#: Minimum parquet count for a plane's modal last-date to count as the store's "today".
TIP_MIN_FILES = 20

EXCLUSION_CODES = (
    "E1_NOT_TERMINATED",
    "E2_KEY_MIGRATION",
    "E3_NOT_US_LISTED",
    "E5_INSUFFICIENT_HISTORY",
    "E6_NO_LAWFUL_ADJUSTED_OHLCV",
    "E7_RIGHTS_UNRESOLVED",
    "E8_TAPE_CONTAMINATED",
    "E9_IDENTITY_UNRESOLVED",
    "ADJUSTMENT_UNPROVEN",
)

#: Registration §4 S6/S10 — planes whose split+dividend adjustment is asserted in repo
#: code. Value is the assertion site, carried into the receipt so the claim is auditable.
ADJUSTED_PLANE_EVIDENCE = {
    "stocks_tr_v1": "collectors/_stock_ohlc.py:83 fetch_ohlc(auto_adjust=True) — dividend/split-adjusted total return",
    "baskets_ohlcv_v1": "scripts/fetch_basket_ohlcv.py:563 yf.download(auto_adjust=True)",
    "stock_identity_ohlcv_v1": "data/stock_identity/ohlcv/manifest.json adjustment_mode=auto_adjust=True",
}


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Candidate:
    ticker: str
    sources: list[str] = field(default_factory=list)
    accepted: bool = False
    code: str | None = None
    screen: str | None = None
    reason: str = ""
    receipt: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
# §3.1 population
# --------------------------------------------------------------------------- #
def _snapshot_history(root: Path) -> tuple[dict[str, list[str]], dict[str, dict], list[str]]:
    """symbol -> ascending snapshot dates present; plus latest row meta; plus dates."""
    files = sorted(glob.glob(str(root / "data/symbol_directory/snapshots/*.parquet")))
    seen: dict[str, list[str]] = {}
    meta: dict[str, dict] = {}
    dates: list[str] = []
    for f in files:
        d = pd.read_parquet(f)
        dt = Path(f).stem
        dates.append(dt)
        for r in d.itertuples():
            seen.setdefault(str(r.symbol), []).append(dt)
            meta[str(r.symbol)] = {
                "exchange": str(r.exchange), "etf": bool(r.etf),
                "test_issue": bool(r.test_issue), "is_preferred": bool(r.is_preferred),
                "security_name": str(r.security_name),
            }
    return seen, meta, dates


def enumerate_population(root: Path) -> tuple[dict[str, list[str]], dict[str, str]]:
    """§3.1 — P = S-A ∪ S-B ∪ S-C, with per-source content hashes."""
    pop: dict[str, list[str]] = {}
    hashes: dict[str, str] = {}

    p_a = root / "config/delisted_symbols.yml"
    for t in (yaml.safe_load(p_a.read_text()).get("symbols") or {}):
        pop.setdefault(t, []).append("S-A")
    hashes["S-A:config/delisted_symbols.yml"] = _sha256(p_a)

    p_b = root / "data/quality/reused_tickers_audit.json"
    aud = json.loads(p_b.read_text())
    for entry in list(aud.get("unacked_delisted_printing") or []) + list(aud.get("delisted_printing_acks") or []):
        pop.setdefault(str(entry).split("/")[-1], []).append("S-B")
    hashes["S-B:data/quality/reused_tickers_audit.json"] = _sha256(p_b)

    p_c1 = root / "data/edgar/dead_name_cik.json"
    p_c2 = root / "data/edgar/dead_name_delisting.json"
    dl = json.loads(p_c2.read_text())
    for t in dl:
        pop.setdefault(t, []).append("S-C")
    hashes["S-C:data/edgar/dead_name_cik.json"] = _sha256(p_c1)
    hashes["S-C:data/edgar/dead_name_delisting.json"] = _sha256(p_c2)
    return pop, hashes


# --------------------------------------------------------------------------- #
# tape helpers
# --------------------------------------------------------------------------- #
def _strip_flat_forward(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Drop the documented zero-volume flat-forward padding tail (CTRA/TPH/AVB tell).

    A padded bar is zero (or absent) volume AND an unchanged close. Only a contiguous
    tail is stripped; an interior zero-volume day is a real halt and is preserved.
    """
    if "volume" not in df.columns or df.empty:
        return df, 0
    vol = df["volume"].fillna(0.0).to_numpy()
    close = df["close"].to_numpy()
    n = 0
    i = len(df) - 1
    while i > 0 and vol[i] <= 0.0 and close[i] == close[i - 1]:
        n += 1
        i -= 1
    return (df.iloc[: len(df) - n] if n else df), n


def _plane_tip(root: Path, plane_id: str) -> str | None:
    """Modal last-date across the plane — the store's 'today'. A tape ending here is
    CURRENT, which is the opposite of terminated."""
    d = plane.plane_dir(plane_id, root)
    if not d.exists():
        return None
    files = sorted(d.glob("*.parquet"))
    # A modal tip drawn from a handful of files is not the store's "today" — on a thin
    # plane the candidate IS the mode, so the check would refuse the very tape it is
    # meant to protect. Below the floor there is no authoritative tip and S8 falls back
    # to the (stronger) ledger/directory evidence.
    if len(files) < TIP_MIN_FILES:
        return None
    tips: dict[str, int] = {}
    for f in files[:1200]:
        try:
            idx = pd.read_parquet(f, columns=["close"]).index
            if len(idx):
                k = str(idx.max())[:10]
                tips[k] = tips.get(k, 0) + 1
        except Exception:  # noqa: BLE001 — a single unreadable file must not blind the tip
            continue
    return max(tips, key=tips.get) if tips else None


# --------------------------------------------------------------------------- #
# §4 screen ladder — first failure assigns the code
# --------------------------------------------------------------------------- #
def screen_symbol(
    ticker: str,
    *,
    root: Path,
    sources: list[str],
    ledger: dict[str, Any],
    edgar: dict[str, Any],
    seen: dict[str, list[str]],
    meta: dict[str, dict],
    snap_dates: list[str],
    plane_tips: dict[str, str | None],
) -> Candidate:
    c = Candidate(ticker=ticker, sources=sorted(set(sources)))
    row = ledger.get(ticker) or {}
    ev = edgar.get(ticker) or {}
    latest = snap_dates[-1]
    present = seen.get(ticker) or []
    exit_date = present[-1] if present else None          # last date observed listed
    c.receipt["directory_last_listed"] = exit_date
    c.receipt["directory_snapshot_latest"] = latest

    # ---- S1 terminated, not stale ----------------------------------------- #
    # (a) EDGAR / curated primary evidence.
    if ticker in ledger:
        ev_a = f"curated exit ledger row (reason={row.get('reason')}, receipts={bool(row.get('receipts'))})"
    elif ev.get("method") in ("8k_item_5.01", "8k_item_1.03") or ev.get("bankruptcy_accession"):
        ev_a = f"EDGAR {ev.get('method')} (reason={ev.get('reason')}, bankruptcy={ev.get('bankruptcy_accession')})"
    else:
        c.code, c.screen = "E1_NOT_TERMINATED", "S1"
        c.reason = (
            f"no primary terminal-event evidence: not in the curated exit ledger and EDGAR "
            f"method={ev.get('method')!r} reason={ev.get('reason')!r} carries no Form-25-equivalent "
            "or bankruptcy accession. Index-exit membership alone is not a death."
        )
        return c
    # (b) absent from the CURRENT directory (registration S1 clause (b), verbatim).
    # NOT "observed listed then absent": the snapshot archive only opens 2026-07-13, so a name
    # that died before it would fail an in-window-transition test purely from archive coverage.
    # Absence-now is what the law asks; the observed transition, when present, additionally
    # dates the exit and is recorded as the stronger corroboration.
    if exit_date == latest:
        c.code, c.screen = "E1_NOT_TERMINATED", "S1"
        c.reason = f"still exchange-listed in the latest directory snapshot ({latest}) — alive, not terminated."
        return c
    c.receipt["s1_evidence"] = {
        "filing": ev_a,
        "directory": (f"listed through {exit_date}, absent by {latest} (exit observed in-window)"
                      if present else
                      f"absent from the current directory ({latest}); exit predates the archive "
                      f"window opening {snap_dates[0]}, so the date is not directory-witnessed"),
    }

    # ---- S2 not a key migration ------------------------------------------- #
    hyg = hygiene.check_symbol(ticker, repo_root=root)
    c.receipt["hygiene_flags"] = hyg["flags"]
    if "ticker_key_migration_source" in hyg["flags"] or "ticker_key_migration_target" in hyg["flags"]:
        c.code, c.screen = "E2_KEY_MIGRATION", "S2"
        c.reason = f"rename/key migration, not a death: {hyg['notes']}"
        return c
    if row.get("successor_ticker"):
        c.code, c.screen = "E2_KEY_MIGRATION", "S2"
        c.reason = f"ledger declares successor_ticker={row['successor_ticker']!r}; the tape continues elsewhere."
        return c

    # ---- S3 U.S. exchange listed ------------------------------------------ #
    m = meta.get(ticker) or {}
    if m.get("etf") or m.get("test_issue") or m.get("is_preferred"):
        c.code, c.screen = "E3_NOT_US_LISTED", "S3"
        c.reason = f"not common equity (etf={m.get('etf')}, test={m.get('test_issue')}, preferred={m.get('is_preferred')})."
        return c
    # S3 needs POSITIVE evidence of U.S. exchange common-equity listing. Without it, an OTC
    # ADR (ANGPY/IMPUY/RHHBY) sails through every absence-based test, because never being in
    # the exchange directory is its normal LIVE state, not a death.
    if not present and not (row.get("exchange")):
        c.code, c.screen = "E3_NOT_US_LISTED", "S3"
        c.reason = (
            f"no evidence of U.S. exchange common-equity listing: never present in any directory "
            f"snapshot ({snap_dates[0]}..{latest}) and no curated ledger row declaring an exchange. "
            "Absence from an exchange directory is the normal live state of an OTC/ADR line."
        )
        return c
    c.receipt["exchange"] = m.get("exchange")
    c.receipt["security_name"] = m.get("security_name")

    # ---- S4 identity resolved --------------------------------------------- #
    if "reused_ticker_acked" in hyg["flags"] or not hyg["compute_eligible"]:
        c.code, c.screen = "E9_IDENTITY_UNRESOLVED", "S4"
        c.reason = f"ticker-identity hygiene refuses this symbol: flags={hyg['flags']}, notes={hyg['notes']}"
        return c

    # ---- S5 on a registered plane with required fields --------------------- #
    plane_id = next((p for p in plane.PLANE_PRECEDENCE if ticker in plane.symbols_on_plane(p, root)), None)
    if plane_id is None:
        c.code, c.screen = "E6_NO_LAWFUL_ADJUSTED_OHLCV", "S5"
        c.reason = "absent from every registered price plane — missing is an exclusion, never a partial control."
        return c
    try:
        df = plane.load_symbol(ticker, plane_id, root)
    except Exception as e:  # noqa: BLE001
        c.code, c.screen = "E6_NO_LAWFUL_ADJUSTED_OHLCV", "S5"
        c.reason = f"plane load failed: {type(e).__name__}: {e}"
        return c
    c.receipt["price_plane_id"] = plane_id
    c.receipt["has_open"] = plane.has_open(plane_id)

    # ---- S6 / S10 adjusted, code-asserted leg ------------------------------ #
    if plane_id not in ADJUSTED_PLANE_EVIDENCE:
        c.code, c.screen = "ADJUSTMENT_UNPROVEN", "S10"
        c.reason = f"plane {plane_id} has no code-asserted split+dividend adjustment."
        return c
    c.receipt["adjustment_mode"] = ADJUSTED_PLANE_EVIDENCE[plane_id]

    # ---- padding is stripped before either S7 or S8 reads the tape ---------- #
    core, padded = _strip_flat_forward(df)
    c.receipt["flat_forward_bars_stripped"] = padded
    if core.empty:
        c.code, c.screen = "E8_TAPE_CONTAMINATED", "S8"
        c.reason = "tape is entirely flat-forward padding."
        return c

    # ---- S7 history horizon ------------------------------------------------ #
    n = int(len(core))
    c.receipt["sessions"] = n
    if n < MIN_SESSIONS:
        c.code, c.screen = "E5_INSUFFICIENT_HISTORY", "S7"
        c.reason = f"{n} sessions < MIN_SESSIONS={MIN_SESSIONS} (fingerprint returns all-null below the floor)."
        return c

    # ---- S8 terminal tape integrity ---------------------------------------- #
    tape_last = core.index.max()
    c.receipt["tape_first"] = str(core.index.min())[:10]
    c.receipt["tape_last"] = str(tape_last)[:10]
    tip = plane_tips.get(plane_id)
    c.receipt["plane_tip"] = tip
    if tip and str(tape_last)[:10] >= tip:
        c.code, c.screen = "E8_TAPE_CONTAMINATED", "S8"
        c.reason = (
            f"tape runs to the plane's current tip ({tip}) after stripping {padded} padding bar(s): "
            "this series is still being fed, which is a live/stale feed, not a terminated tape."
        )
        return c
    if row.get("last_session"):
        ls = pd.Timestamp(str(row["last_session"]))
        over2 = int((core.index > ls).sum())
        c.receipt["bars_after_ledger_last_session"] = over2
        if over2 > 0:
            c.code, c.screen = "E8_TAPE_CONTAMINATED", "S8"
            c.reason = (
                f"{over2} real bar(s) after the curated ledger's last_session={row['last_session']}. "
                "The ledger is the resolved terminal truth; bars past it are not this security."
            )
            return c

    # Real bars materially past the proven delisting window = successor splice.
    overrun = int((core.index > pd.Timestamp(exit_date)).sum()) if exit_date else 0
    c.receipt["bars_after_directory_exit"] = overrun
    if overrun > TERMINAL_GRACE_SESSIONS:
        c.code, c.screen = "E8_TAPE_CONTAMINATED", "S8"
        c.reason = (
            f"{overrun} real bars after the last date the symbol was observed exchange-listed "
            f"({exit_date}), beyond the {TERMINAL_GRACE_SESSIONS}-session snapshot-cadence grace. "
            "A dead symbol cannot keep printing volume; this is a successor-series splice "
            "(the documented AVB failure mode), and plane.load_symbol does not truncate it."
        )
        return c

    # ---- S9 rights --------------------------------------------------------- #
    c.receipt["rights"] = (
        "persisted in-repo by an existing owner already committing this plane to the repository; "
        "W3S adds no new provider, no redistribution surface and no new entitlement."
    )
    c.accepted = True
    c.screen = "ACCEPTED"
    c.reason = "passes S1-S10"
    return c


def build_cohort(repo_root: str | Path) -> dict[str, Any]:
    """Execute the registered ladder. Deterministic: same inputs -> same output."""
    root = Path(repo_root)
    pop, hashes = enumerate_population(root)
    ledger = yaml.safe_load((root / "config/delisted_symbols.yml").read_text()).get("symbols") or {}
    edgar = json.loads((root / "data/edgar/dead_name_delisting.json").read_text())
    seen, meta, snap_dates = _snapshot_history(root)
    plane_tips = {p: _plane_tip(root, p) for p in plane.PLANE_PRECEDENCE}

    def _term_date(t: str) -> str:
        r = ledger.get(t) or {}
        if r.get("last_session"):
            return str(r["last_session"])
        s = seen.get(t) or []
        return s[-1] if s else "9999-12-31"

    # §3.2 deterministic ordering, fixed before screening.
    order = sorted(pop, key=lambda t: (_term_date(t), t))
    results = [
        screen_symbol(t, root=root, sources=pop[t], ledger=ledger, edgar=edgar,
                      seen=seen, meta=meta, snap_dates=snap_dates, plane_tips=plane_tips)
        for t in order
    ]
    accepted = [c for c in results if c.accepted]
    by_code: dict[str, int] = {}
    for c in results:
        if not c.accepted:
            by_code[c.code] = by_code.get(c.code, 0) + 1
    return {
        "schema": "stock_identity.dead_control_cohort.v1",
        "operation_key": "SI-W3S-DEAD-CONTROL-V1",
        "registration": "research/stock_identity/W3_DEAD_INSTRUMENT_CONTROL_REGISTRATION.md",
        "min_sessions": MIN_SESSIONS,
        "source_hashes": hashes,
        "plane_tips": plane_tips,
        "directory_window": [snap_dates[0], snap_dates[-1]] if snap_dates else None,
        "n_population": len(order),
        "n_accepted": len(accepted),
        "exclusions_by_code": dict(sorted(by_code.items())),
        "accepted": [asdict(c) for c in accepted],
        "ledger": [asdict(c) for c in results],
        "authority": {"can_rank": False, "can_size": False, "can_gate": False,
                      "can_escalate": False, "can_originate_signal": False},
    }


def compatibility_smoke(ticker: str, plane_id: str, repo_root: str | Path) -> dict[str, Any]:
    """Prove one tape runs through the CURRENT fingerprint/episode inputs.

    Real compute, not a shape assertion: a control that cannot produce a fingerprint or an
    episode catalog is not a control, and the only way to know is to run them.
    """
    from . import episodes, fingerprint  # local: keeps module import cheap

    root = Path(repo_root)
    df = plane.load_symbol(ticker, plane_id, root)
    core, padded = _strip_flat_forward(df)
    asof = core.index.max()
    vals = json.loads((root / "data/stock_identity/constants/si_constants_v1.json").read_text())["values"]
    ec = episodes.EpisodeConstants(
        X=float(vals["X"]), Y=float(vals["Y"]), N=int(vals["N"]), k=float(vals["k"]),
        z=float(vals["z"]), M=int(vals["M"]), m=int(vals["m"]), D1=int(vals["D1"]),
        D2=int(vals["D2"]), S_reclaim=int(vals["S_reclaim"]),
    )
    fp = fingerprint.compute_raw(core, plane_id=plane_id, asof=asof)
    non_null = sum(1 for v in fp.values() if isinstance(v, (int, float)) and v == v)
    cat = episodes.build_catalog(core, symbol=ticker, plane_id=plane_id, const=ec)
    return {
        "symbol": ticker, "price_plane_id": plane_id, "sessions": int(len(core)),
        "flat_forward_bars_stripped": int(padded), "asof": str(asof)[:10],
        "fingerprint_metrics": len(fp), "fingerprint_non_null": int(non_null),
        "episode_rows": int(len(cat)),
        "ok": bool(len(core) >= MIN_SESSIONS and non_null > 0),
    }
