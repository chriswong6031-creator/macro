"""Reused-ticker / zombie-print tripwire for the per-ticker US price stores.

WHY THIS EXISTS (2026-08-06, the ECHO identity swap): a ticker STRING is not a stable
identity. Echo Global Logistics (NASDAQ ECHO, CUSIP 27875T101) was taken private
2021-12 at $48.25 and its genuine series ended in the dead-name registry — then
EchoStar Corporation renamed SATS->ECHO effective 2026-06-24 (press release
2026-06-22; NASDAQ directory + SEC EDGAR CIK 1415404 + OpenFIGI BBG000TGLV00 all
confirm), entered a sector SPDR top-20, and the stores' bare-string yfinance fetch
minted data/stocks/ECHO.parquet + data/baskets/ohlcv/ECHO.parquet holding EchoStar's
FULL spliced history back to 2008 — 20 months before Echo Global Logistics even
IPO'd. Every historical join by the string (the Signal Episode Atlas W6 study was the
discoverer) silently reads another company's tape. The class is not singular: the
2026-08 sweep also found SPWR (new-SunPower né Complete Solaria over SunPower Corp's
2024 Ch.11 corpse) and RPT (Rithm Property Trust over RPT Realty's Kimco-merger
corpse) contaminated the same way, CAMP/NP/WOLF reborn under recycled strings with a
clean break, and EA printing fresh bars pinned at its take-private deal price while
already absent from the NASDAQ symbol directory.

WHAT IT CHECKS — every per-ticker parquet in data/stocks/ and data/baskets/ohlcv/
(leading-underscore stems skipped), cross-referenced against the dead-name registry
(data/edgar/dead_name_prices.parquet) and the live NASDAQ symbol directory
(nasdaqtrader.com symdir; dot/dash class-share notation normalized):

  zombie            in the dead registry, tip advancing > `reused_grace_days` past the
                    registry's last bar, file SPANS that death date, and the overlap
                    receipt says DIFFERENT instrument (min of full-overlap and last-60
                    daily-return correlation < 0.35, or overlap too thin to verify).
                    Another company's tape under a dead company's key — historical
                    joins by this string are poisoned. ::warning per name unless acked.
  rebirth           registry name advancing past death but the file STARTS after the
                    death date: a new security under a recycled string, no poisoned
                    rows in-store (WOLF post-Ch.11, CAMP4 under CAMP). JSON only.
  registry_mismatch registry name advancing, file spans death, but receipts say SAME
                    instrument (corr >= 0.35, in practice ~1.0): the store is innocent
                    and the DEAD REGISTRY itself carries live/foreign rows under this
                    name (its own bare-string price fetch ate reused/live tape — 125
                    names measured 2026-08). JSON + one ::notice; fuel for a registry
                    heal, never a store alarm.
  ledger_identity   (2026-08-12) the same fires logged TWICE, once under each of a
                    renamed company's two strings, in the append-only
                    data/signal_archive/track_record.parquet. The classes above all look
                    at STORES; this one follows the rename downstream, which is where the
                    ECHO ack's blind spot was — acking the store silenced the alarm while
                    128 EchoStar fires sat double-logged (SATS + ECHO, identical
                    (date, type) key sets) double-weighting one company in every per-row
                    statistic. `undeclared_candidates` (identical key sets, no ratified
                    identity) is a ::warning; a `declared_duplicate` (a ratified rename
                    whose superseded key still carries rows, awaiting the gated repair
                    scripts/migrate_track_record_keys.py) is a ::notice.
  delisted_printing NOT in the registry, tip FRESH (<= stocks_stale_calendar_days),
                    but the string is absent from today's NASDAQ symbol directory:
                    rows keep flowing for a string with no current US listing — an
                    in-flight take-private the registry has not caught yet (EA, pinned
                    at ~$209 vs its $210 deal price, 2026-08 specimen) or a deliberate
                    OTC member (ack RHHBY). One summary ::warning for un-acked names.
  member_identity   (2026-08-14) curated NAME vs the directory's CURRENT issuer for
                    the same symbol — data/baskets/membership.json rationales written
                    as 'Company — thesis' and config.yml stock_search.extra_names
                    labels. A reused symbol that stays LISTED is invisible to every
                    class above (nothing is dead, nothing is stale, the file simply
                    belongs to the directory's current issuer): gold_miners carried
                    'Barrick Mining' on NYSE 'GOLD' for two weeks while the symbol —
                    and the whole store tape — belonged to Gold.com, a bullion dealer
                    (#5613; roster repaired the day this class shipped). Matching is
                    on distinctive name tokens (generic corporate/industry words
                    dropped) plus directory initialisms and token containment, so
                    'Newmont' matches 'Newmont Corporation', 'IBM Quantum' matches
                    'International Business Machines' and 'SpaceX' matches 'Space
                    Exploration Technologies', while 'Barrick Mining' can never match
                    'Gold.com, Inc.'. A rationale that leads with a thesis rather
                    than a name-cased company ('Azure + Copilot — …', 'S&P 500
                    Materials constituent') makes no name claim and is skipped;
                    `removed` members are the curator's exit ledger (skipped);
                    symbols absent from the directory are delisted_printing's beat.
                    First live sweep (516 names checked): the GOLD defect plus two
                    stale same-registrant brand names (NXT Nextracker->Nextpower CIK
                    1852131, QFIN Qifu->Qfin CIK 1741530), zero false positives — all
                    three fixed at the source in the shipping PR. One summary
                    ::warning for un-acked names.

ACKS — config.yml `quality.reused_ticker_acks` ({TICKER: identity rationale}),
`quality.delisted_printing_acks` ([TICKER, ...] — plus, for the delisted_printing
class only, any name carrying a resolved exit row in config/delisted_symbols.yml:
the exit row is the triage the warning asks for, so it reads as acked with a
"resolved exit" rationale rather than warning until the tip ages out) and
`quality.member_identity_acks` ({TICKER: verified-identity rationale, for a curated
name that legitimately disagrees with the directory}) are operator-ratified
identities: acked names are still disclosed in the JSON every night (with the
rationale echoed) but never annotated. The ack text IS the key-migration
documentation the house law requires (memory: ticker-rename-is-a-key-migration,
#4622).

EVERYTHING IS A FLAG, NEVER A FAIL (CSP-R1 — staleness/identity is disclosure, not
fail-dark): findings go through Universe.flag(), n_failed stays 0, and the default
exit code is 0 so neither run_quality_audits nor the daily.yml step can lose the
night on this audit's account. `--strict` exits 3 when any un-acked zombie or
delisted_printing name exists (for humans and tests). An unexpected crash exits 2.

DEGRADED MODES ARE DISCLOSED, NEVER SILENT: a missing dead registry darkens the
registry classes (::warning), a failed NASDAQ directory download darkens
delisted_printing (::warning), an absent store skips its cohort quietly (CI-lite
checkout convention, matching audit_prices/audit_stocks_freshness).

READ-ONLY over the stores; writes only data/quality/reused_tickers_audit.json.
Wired into scripts/collect.py run_quality_audits AND its own daily.yml step (the
nightly `--exclude-group asia` collect skips the whole gate as a partial run — same
double-wiring rationale as audit_stocks_freshness).
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from lib import config, delisted_symbols, nyse_calendar  # noqa: E402
from scripts import audit_common as ac  # noqa: E402

log = logging.getLogger("audit.reused_tickers")

#: (cohort name, store path relative to the data dir)
STORES: tuple[tuple[str, str], ...] = (("stocks", "stocks"), ("baskets_ohlcv", "baskets/ohlcv"))

#: below this daily-return correlation on the overlap, the store series is a
#: DIFFERENT instrument than the registry's death-era closes. Measured separation on
#: the 2026-08 population: zombies ECHO -0.03 / SPWR 0.05 / RPT 0.22 (recent window)
#: vs same-instrument registry false positives at ~1.0 (nearest gray case SITC 0.54).
CORR_DIFFERENT_INSTRUMENT = 0.35
#: fewer common rows than this and the correlation receipt is unverifiable ("thin").
MIN_OVERLAP_ROWS = 20
#: last-60-common-rows window for the recent-correlation receipt (adjustment steps
#: accumulate over long overlaps and depress full-window correlation for the SAME
#: instrument — the recent window is the decisive read; needs >= MIN_OVERLAP_ROWS).
RECENT_WINDOW = 60

_SYMDIR_URLS = (
    "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt",
    "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt",
)


def _today_et(now: datetime | None) -> date:
    """ET calendar date `now` falls on (same convention as audit_stocks_freshness)."""
    if now is None:
        now = datetime.now(timezone.utc)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(nyse_calendar.ET).date()


def fetch_directory(timeout: int = 20) -> dict[str, str] | None:
    """Current US listings {ACT symbol: security name} from the NASDAQ symbol
    directory (both files). None on any failure — the caller darkens the
    delisted_printing class, never crashes."""
    import requests
    out: dict[str, str] = {}
    try:
        for url in _SYMDIR_URLS:
            r = requests.get(url, timeout=timeout)
            r.raise_for_status()
            for line in r.text.splitlines()[1:]:
                parts = line.split("|")
                # trailer line ("File Creation Time...") has no name column
                if len(parts) > 1 and parts[0] and not parts[0].startswith("File Creation"):
                    out[parts[0]] = parts[1]
    except Exception as e:  # noqa: BLE001 — network is best-effort; absence is disclosed
        log.warning("[reused_tickers] symbol-directory fetch failed: %s", e)
        return None
    return out or None


def _listed(t: str, directory: dict[str, str]) -> bool:
    """Directory presence with vendor-notation normalization: yfinance spells class
    shares with '-' (BRK-B) where the directory uses '.' (BRK.B)."""
    return t in directory or t.replace("-", ".") in directory


def _overlap_receipt(store_close: pd.Series, registry_close: pd.Series) -> dict:
    """Same-instrument receipt: daily-return correlation over the full overlap AND
    over the last RECENT_WINDOW common rows. The store is auto-adjusted while the
    registry is raw, so close LEVELS legitimately diverge (dividend factors); daily
    RETURNS still match for the same instrument."""
    both = pd.concat([store_close.rename("s"), registry_close.rename("r")],
                     axis=1, join="inner").dropna()
    rec: dict = {"n_overlap": int(len(both))}
    if len(both) < MIN_OVERLAP_ROWS:
        return rec
    corrs = [both["s"].pct_change().corr(both["r"].pct_change())]
    recent = both.tail(RECENT_WINDOW)
    if len(recent) >= MIN_OVERLAP_ROWS:
        corrs.append(recent["s"].pct_change().corr(recent["r"].pct_change()))
    valid = [float(c) for c in corrs if pd.notna(c)]
    if not valid:
        return rec  # constant/degenerate overlap — treat as thin
    rec["ret_corr_full"] = round(float(corrs[0]), 4) if pd.notna(corrs[0]) else None
    if len(corrs) > 1 and pd.notna(corrs[1]):
        rec["ret_corr_recent"] = round(float(corrs[1]), 4)
    rec["min_ret_corr"] = round(min(valid), 4)
    return rec


def _acks(cfg_quality: dict | None) -> tuple[dict[str, str], set[str], dict[str, str]]:
    q = cfg_quality if cfg_quality is not None else (config.load().get("quality") or {})
    reused = {str(k): str(v) for k, v in (q.get("reused_ticker_acks") or {}).items()}
    delisted = {str(t) for t in (q.get("delisted_printing_acks") or [])}
    member = {str(k): str(v) for k, v in (q.get("member_identity_acks") or {}).items()}
    return reused, delisted, member


# ------------------------------------------------------------- member identity (names)
#: Name tokens too generic to identify a company on their own — legal suffixes,
#: security-type boilerplate and broad industry words. 'Barrick Mining' must reduce
#: to {barrick} so it can never ride 'mining' into a match, and 'Gold.com, Inc.
#: Common Stock' must reduce to {} rather than lending 'gold' to any gold miner.
_NAME_GENERIC = frozenset("""
inc incorporated corp corporation company co ltd limited plc llc lp sa nv se ag ab
adr ads gdr american depositary depository shares share each representing per unit
units ordinary common stock class capital voting redeemable warrants warrant rights
right trust the of and de new group groups holdings holding international global
worldwide com technologies technology tech industries industrial systems solutions
brands enterprises services ventures partners properties property realty reit fund
funds etf index mining miners metals gold silver copper platinum resources energy
oil gas petroleum pharmaceuticals pharma pharmaceutical therapeutics biosciences
sciences labs laboratories financial financials bancorp bancshares bank banking
capital markets communications communication media entertainment platforms airlines
air lines motors motor foods food beverages beverage products product materials
semiconductor semiconductors software digital data cloud networks network health
healthcare medical home homes builders usa us na
""".split())

#: A membership rationale's leading clause is a NAME CLAIM only when it reads like a
#: proper name. Thesis-first rationales ('Azure + Copilot — …', 'Grid equipment +
#: gas turbines — …', '[DAT TRADING SLEEVE …') contain connectives/case shapes no
#: company name has — they make no identity claim, so there is nothing to contradict.
_CLAIM_DISQUALIFIERS = ("+", "&", " vs ", "[")


def _name_tokens(name: str) -> set[str]:
    toks = re.findall(r"[a-z0-9]+", name.lower())
    return {w for w in toks if w not in _NAME_GENERIC and not w.isdigit() and len(w) >= 2}


def _dir_initialisms(dir_name: str) -> set[str]:
    """Prefix initialisms of the directory name's leading words — 'International
    Business Machines Corporation Common Stock' -> {'ib','ibm','ibmc',…} — so a
    curated 'IBM Quantum' matches the legal name it abbreviates. Boilerplate after
    a ' - ' separator ('- Class A Common Stock') never contributes initials."""
    words = re.findall(r"[A-Za-z][\w'.-]*", dir_name.split(" - ")[0])
    initials = "".join(w[0].lower() for w in words if w[0].isalpha())
    return {initials[:i] for i in range(2, len(initials) + 1)}


def _member_name_claim(rationale: str) -> str | None:
    """The 'Company' of a 'Company — thesis' rationale, or None when the rationale
    makes no name claim (no em-dash, thesis-shaped prefix, or a single short token —
    ticker echoes like 'AIP' identify a product, not an issuer)."""
    if "—" not in rationale:
        return None
    prefix = rationale.split("—", 1)[0].strip()
    if not prefix or any(d in prefix for d in _CLAIM_DISQUALIFIERS):
        return None
    words = prefix.split()
    if not all(w[0].isupper() or w[0].isdigit() or w[0] == "(" for w in words):
        return None
    if len(words) == 1 and len(words[0]) < 5:
        return None
    return prefix


def _names_match(claim_tokens: set[str], dir_name: str) -> bool:
    """True when the curated name plausibly names the directory's issuer: shared
    distinctive token ('Newmont'), the directory initialism ('IBM' vs International
    Business Machines), or token containment >= 4 chars either way ('SpaceX' ⊇
    'Space' of Space Exploration Technologies). An empty claim contradicts nothing."""
    if not claim_tokens:
        return True
    dir_tokens = _name_tokens(dir_name)
    if claim_tokens & dir_tokens:
        return True
    if claim_tokens & _dir_initialisms(dir_name):
        return True
    for c in claim_tokens:
        for d in dir_tokens:
            if (len(d) >= 4 and d in c) or (len(c) >= 4 and c in d):
                return True
    return False


def _member_identity_rows(data_dir: Path, directory: dict[str, str] | None,
                          acks: dict[str, str],
                          stock_search_raw: dict | None) -> tuple[list[dict], list[str]]:
    """Curated names vs the live directory (the GOLD class). Returns (rows, unacked).

    Sources checked: every ACTIVE data/baskets/membership.json member whose rationale
    leads with a name claim, and every config.yml stock_search.extra_names label.
    Symbols absent from the directory are skipped (delisted_printing's beat); a dark
    directory returns nothing (run() already discloses directory_dark)."""
    rows: list[dict] = []
    unacked: list[str] = []
    if not directory:
        return rows, unacked

    def _check(ticker: str, where: str, source: str, curated_name: str) -> None:
        dir_name = directory.get(ticker) or directory.get(ticker.replace("-", "."))
        if not dir_name:
            return
        if _names_match(_name_tokens(curated_name), dir_name):
            return
        entry = {"ticker": ticker, "where": where, "source": source,
                 "curated_name": curated_name.strip()[:80],
                 "directory_name": str(dir_name).strip(), "acked": ticker in acks}
        if entry["acked"]:
            entry["ack"] = acks[ticker]
        else:
            unacked.append(f"{where}/{ticker}")
        rows.append(entry)

    mem_p = data_dir / "baskets" / "membership.json"
    if mem_p.exists():
        try:
            baskets = json.loads(mem_p.read_text()).get("baskets") or {}
        except Exception as e:  # noqa: BLE001 — a corrupt roster is not this audit's fail
            log.warning("[reused_tickers] membership.json unreadable (%s)", e)
            baskets = {}
        items = baskets.items() if isinstance(baskets, dict) else ((b.get("id"), b) for b in baskets)
        for bid, b in items:
            for m in b.get("members") or []:
                t = m.get("ticker")
                if not t or m.get("removed"):
                    continue
                claim = _member_name_claim(str(m.get("rationale") or ""))
                if claim:
                    _check(str(t), str(bid), "membership_rationale", claim)

    ss = stock_search_raw if stock_search_raw is not None else (config.load().get("stock_search") or {})
    for t, meta in (ss.get("extra_names") or {}).items():
        nm = str((meta or {}).get("name") or "")
        if nm:
            _check(str(t), "stock_search.extra_names", "extra_names", nm)
    return rows, unacked


def _ledger_identity_section(data_dir: Path, quality_raw: dict | None,
                             ledger_path: Path | None = None) -> dict:
    """What a ratified rename did DOWNSTREAM of the stores, in the append-only ledger.

    THE GAP THIS CLOSES (2026-08-12): this audit owns the identity doctrine and the
    operator-ratified acks, but it only ever looked at the per-ticker price STORES.
    Acking ECHO silenced the store alarm; nothing asked what the SATS->ECHO rename had
    already done to `data/signal_archive/track_record.parquet`, where 128 EchoStar fires
    sat logged twice — once under each string — double-weighting one company in every
    per-row statistic for six weeks before an unrelated investigation tripped over it.

    Same disclosure discipline as the rest of this file (CSP-R1): findings, never a fail.
    An absent ledger skips quietly (CI-lite / sparse checkouts); a corrupt one darkens
    loudly rather than reading as "clean".
    """
    from engine import ledger_identity  # local: keeps this audit importable without engine

    if ledger_path is None:
        ledger_path = data_dir / "signal_archive" / "track_record.parquet"
    sec: dict = {"ledger": str(ledger_path), "declared_duplicates": [],
                 "undeclared_candidates": []}
    migrations = ledger_identity.load_migrations(quality_raw)
    sec["ticker_key_migrations"] = migrations
    if not Path(ledger_path).exists():
        sec["skipped"] = "ledger absent"
        return sec
    try:
        # Key columns only — the geometry is the finding; the cell-by-cell losslessness
        # receipt belongs to scripts/migrate_track_record_keys, not to a nightly audit.
        df = pd.read_parquet(ledger_path, columns=list(ledger_identity.KEY_COLS))
    except Exception as e:  # noqa: BLE001
        sec["ledger_dark"] = True
        log.warning("[reused_tickers] ledger unreadable (%s)", e)
        print("::warning title=ledger identity::track_record.parquet unreadable — the "
              "duplicate-identity detector is DARK this run", flush=True)
        return sec
    sec["ledger_rows"] = int(len(df))
    sec["declared_duplicates"] = ledger_identity.find_declared_duplicates(df, migrations)
    sec["undeclared_candidates"] = ledger_identity.find_undeclared_duplicates(df, migrations)
    return sec


def run(cfg: dict | None = None, now: datetime | None = None,
        out_dir: Path | None = None, data_dir: Path | None = None,
        directory: dict[str, str] | None = None,
        quality_raw: dict | None = None,
        ledger_path: Path | None = None,
        stock_search_raw: dict | None = None,
        exit_ledger: frozenset[str] | None = None) -> dict:
    """Audit both per-ticker stores for reused/zombie ticker keys and persist
    data/quality/reused_tickers_audit.json. Never raises for a data issue.

    `directory` injects the {symbol: name} listing map (tests); None downloads it.
    `quality_raw` injects the raw config `quality:` block for the ack lists (tests);
    None reads config.yml. `stock_search_raw` injects the `stock_search:` block for
    the member_identity extra_names source (tests); None reads config.yml. `cfg` is
    the quality_cfg() threshold view (collect.py passes it); only
    `stocks_stale_calendar_days` and `reused_grace_days` are read."""
    cfg = cfg or ac.quality_cfg()
    data_dir = Path(data_dir) if data_dir is not None else ac.ROOT / "data"
    stale_days = int(cfg.get("stocks_stale_calendar_days", 7))
    grace_days = int(cfg.get("reused_grace_days", 30))
    today = _today_et(now)
    reused_acks, delisted_acks, member_acks = _acks(quality_raw)
    # A resolved exit row (config/delisted_symbols.yml) IS the triage this class
    # asks for: "delisted still printing" exists to surface an in-flight
    # take-private nobody has resolved yet, and once the exit ledger carries the
    # name — evidence-backed, #4622 protocol — the freshly-dead tip is the
    # already-diagnosed final-session window, not an un-triaged alarm (the fetch
    # exclusion freezes the tip within a session; the freshness lanes' delisted
    # contradiction shout still owns bars past last_session). Union, never a
    # replacement: quality.delisted_printing_acks stays the home for names that
    # legitimately keep printing OTC (RHHBY, STRS). tickers() fails open to
    # empty, so a broken ledger degrades to pre-ledger behaviour. `exit_ledger`
    # injects the resolved-exit set (tests); None reads config/delisted_symbols.yml.
    if exit_ledger is None:
        exit_ledger = delisted_symbols.tickers()

    # --- dead registry: per-ticker death-era closes -------------------------------
    reg_path = data_dir / "edgar" / "dead_name_prices.parquet"
    registry: dict[str, pd.Series] = {}
    registry_dark = False
    try:
        reg = pd.read_parquet(reg_path, columns=["ticker", "date", "close"])
        reg["date"] = pd.to_datetime(reg["date"])
        registry = {t: g.set_index("date")["close"].sort_index()
                    for t, g in reg.groupby("ticker")}
    except Exception as e:  # noqa: BLE001 — absence/corruption darkens, never crashes
        registry_dark = True
        log.warning("[reused_tickers] dead-name registry unreadable (%s)", e)

    if directory is None:
        directory = fetch_directory()
    directory_dark = directory is None

    universes: list[ac.Universe] = []
    per_store: list[dict] = []
    totals = {"zombie": 0, "rebirth": 0, "registry_mismatch": 0, "delisted_printing": 0,
              "member_identity": 0}
    unacked_zombies: list[str] = []
    unacked_delisted: list[str] = []

    for cohort, rel in STORES:
        uni = ac.Universe(name=cohort)
        store_dir = data_dir / Path(rel)
        files = sorted(store_dir.glob("*.parquet")) if store_dir.is_dir() else []
        files = [p for p in files if not p.stem.startswith("_")]
        rec: dict = {"store": str(rel), "n_files": len(files),
                     "zombie": [], "rebirth": [], "registry_mismatch": [],
                     "delisted_printing": []}
        if not files:
            uni.skipped = True
            uni.note = f"data/{rel} absent/empty — cohort skipped"
            universes.append(uni)
            per_store.append(rec)
            continue
        uni.n = len(files)
        for p in files:
            t = p.stem
            try:
                idx = pd.to_datetime(pd.read_parquet(p, columns=[]).index)
            except Exception:  # noqa: BLE001 — corruption is audit_prices' beat
                continue
            if len(idx) == 0:
                continue
            tip = idx.max().date()
            start = idx.min().date()
            if t in registry:
                death = registry[t].index.max().date()
                past = (tip - death).days
                if past <= grace_days:
                    continue  # frozen at/near death — audit_stocks_freshness territory
                if start > death:
                    totals["rebirth"] += 1
                    rec["rebirth"].append({"ticker": t, "registry_last": str(death),
                                           "store_start": str(start), "store_tip": str(tip)})
                    uni.flag(t, "rebirth", f"recycled string; new security starts {start}, "
                                           f"prior holder's last registry bar {death}")
                    continue
                try:
                    close = pd.read_parquet(p, columns=["close"])["close"]
                    close.index = pd.to_datetime(close.index)
                except Exception:  # noqa: BLE001
                    close = pd.Series(dtype=float)
                receipt = _overlap_receipt(close, registry[t])
                min_corr = receipt.get("min_ret_corr")
                entry = {"ticker": t, "registry_last": str(death), "store_tip": str(tip),
                         "days_past_death": past, "overlap": receipt,
                         "listed_now": (_listed(t, directory) if directory else None)}
                if min_corr is not None and min_corr >= CORR_DIFFERENT_INSTRUMENT:
                    totals["registry_mismatch"] += 1
                    rec["registry_mismatch"].append(entry)
                    uni.flag(t, "registry_mismatch",
                             f"same instrument as its dead-registry rows (corr {min_corr}) — "
                             "the registry, not the store, carries foreign/live tape")
                    continue
                entry["acked"] = t in reused_acks
                if entry["acked"]:
                    entry["ack"] = reused_acks[t]
                totals["zombie"] += 1
                rec["zombie"].append(entry)
                why = (f"overlap corr {min_corr}" if min_corr is not None
                       else f"overlap too thin to verify ({receipt['n_overlap']} rows)")
                uni.flag(t, "zombie", f"dead-registry name advancing {past}d past its "
                                      f"{death} registry bar; {why}")
                if not entry["acked"]:
                    unacked_zombies.append(f"{rel}/{t}")
                    print(f"::warning title=reused ticker key::{rel}/{t}.parquet advances "
                          f"{past}d past the dead-name registry's last bar ({death}) with a "
                          f"mismatched overlap ({why}) — another company's tape under a dead "
                          f"key; historical joins by '{t}' are poisoned. Resolve identity "
                          "(NASDAQ directory + OpenFIGI), then ack in config.yml "
                          "quality.reused_ticker_acks or migrate the key.", flush=True)
            elif directory is not None and (today - tip).days <= stale_days \
                    and not _listed(t, directory):
                resolved = t in exit_ledger
                acked = t in delisted_acks or resolved
                totals["delisted_printing"] += 1
                entry = {"ticker": t, "store_tip": str(tip), "acked": acked}
                if resolved:
                    entry["ack"] = "resolved exit — config/delisted_symbols.yml"
                rec["delisted_printing"].append(entry)
                uni.flag(t, "delisted_printing",
                         f"fresh bars ({tip}) but no current NASDAQ/NYSE listing")
                if not acked:
                    unacked_delisted.append(f"{rel}/{t}")
        universes.append(uni)
        per_store.append(rec)

    member_rows, unacked_member = _member_identity_rows(
        data_dir, directory, member_acks, stock_search_raw)
    totals["member_identity"] = len(member_rows)

    ledger_sec = _ledger_identity_section(data_dir, quality_raw, ledger_path)

    doc = ac.write_audit("reused_tickers", "stocks", universes, cfg, asof=today, out_dir=out_dir)
    doc["ledger_identity"] = ledger_sec
    doc["grace_days"] = grace_days
    doc["stale_calendar_days"] = stale_days
    doc["totals"] = totals
    doc["stores"] = per_store
    doc["member_identity"] = member_rows
    doc["reused_ticker_acks"] = reused_acks
    doc["delisted_printing_acks"] = sorted(delisted_acks)
    doc["member_identity_acks"] = member_acks
    if registry_dark:
        doc["registry_dark"] = True
        print("::warning title=reused ticker key::dead-name registry unreadable — the "
              "zombie/rebirth/registry_mismatch detectors are DARK this run", flush=True)
    if directory_dark:
        doc["directory_dark"] = True
        print("::warning title=delisted still printing::NASDAQ symbol-directory fetch "
              "failed — the delisted_printing detector is DARK this run", flush=True)
    if unacked_delisted:
        shown = ", ".join(unacked_delisted[:10])
        tail = f" +{len(unacked_delisted) - 10} more" if len(unacked_delisted) > 10 else ""
        print(f"::warning title=delisted still printing::{len(unacked_delisted)} fresh-printing "
              f"name(s) have no current NASDAQ/NYSE listing: {shown}{tail} — in-flight "
              "take-private/delisting or vendor remap; verify identity (an acked OTC member "
              "belongs in config.yml quality.delisted_printing_acks)", flush=True)
    if unacked_member:
        shown = "; ".join(
            f"{r['where']}/{r['ticker']}: curated '{r['curated_name']}' vs directory "
            f"'{r['directory_name']}'" for r in member_rows if not r["acked"])[:600]
        print(f"::warning title=member identity::{len(unacked_member)} curated name(s) "
              f"disagree with the symbol's CURRENT issuer in the NASDAQ directory: {shown} "
              "— a reused symbol stays listed, so no store-level class fires (the "
              "gold_miners GOLD defect read a bullion dealer as 'Barrick' for two weeks). "
              "Resolve identity (NASDAQ directory + EDGAR CIK + OpenFIGI): repair the "
              "roster/label at the source, or ack a verified same-registrant mismatch in "
              "config.yml quality.member_identity_acks.", flush=True)
    if totals["registry_mismatch"]:
        names = [e["ticker"] for s in per_store for e in s["registry_mismatch"]]
        shown = ", ".join(names[:8])
        tail = f" +{len(names) - 8} more" if len(names) > 8 else ""
        print(f"::notice title=dead registry contamination::{len(names)} dead-registry "
              f"name(s) are the SAME live instrument as their store series ({shown}{tail}) — "
              "the registry's own bare-string price fetch ate reused/live tape; heal the "
              "registry, the stores are innocent", flush=True)
    if ledger_sec.get("undeclared_candidates"):
        groups = "; ".join("/".join(c["tickers"]) + f" ({c['n_keys']} keys)"
                           for c in ledger_sec["undeclared_candidates"][:5])
        print(f"::warning title=ledger identity::{len(ledger_sec['undeclared_candidates'])} "
              f"ticker group(s) in track_record.parquet share an IDENTICAL (date, type) "
              f"key set with no ratified identity linking them: {groups} — one company "
              "logged under two strings double-weights it in every per-row statistic. "
              "Resolve identity (NASDAQ directory + EDGAR CIK + OpenFIGI), then add the "
              "row to config.yml quality.ticker_key_migrations.", flush=True)
    if ledger_sec.get("declared_duplicates"):
        pend = ", ".join(f"{d['superseded']}->{d['current']} ({d['superseded_rows']} rows)"
                         for d in ledger_sec["declared_duplicates"])
        print(f"::notice title=ledger identity::{len(ledger_sec['declared_duplicates'])} "
              f"ratified rename(s) still carry rows under the superseded key: {pend} — the "
              "ledger double-weights them until the gated repair runs "
              "(python scripts/migrate_track_record_keys.py --apply). The ingest guard has "
              "stopped the count from growing.", flush=True)
    out = Path(out_dir) if out_dir is not None else ac.quality_dir()
    out.mkdir(parents=True, exist_ok=True)
    (out / "reused_tickers_audit.json").write_text(json.dumps(doc, indent=1))
    print(f"[reused_tickers] asof={today} zombie={totals['zombie']} "
          f"(unacked={len(unacked_zombies)}) rebirth={totals['rebirth']} "
          f"registry_mismatch={totals['registry_mismatch']} "
          f"delisted_printing={totals['delisted_printing']} "
          f"(unacked={len(unacked_delisted)}) "
          f"member_identity={totals['member_identity']} "
          f"(unacked={len(unacked_member)}) "
          f"ledger_declared_dupes={len(ledger_sec.get('declared_duplicates', []))} "
          f"ledger_undeclared={len(ledger_sec.get('undeclared_candidates', []))}"
          + (" registry_dark=True" if registry_dark else "")
          + (" directory_dark=True" if directory_dark else "")
          + (" ledger_dark=True" if ledger_sec.get("ledger_dark") else ""))
    doc["unacked_zombies"] = unacked_zombies
    doc["unacked_delisted_printing"] = unacked_delisted
    doc["unacked_member_identity"] = unacked_member
    doc["undeclared_ledger_identities"] = [
        "/".join(c["tickers"]) for c in ledger_sec.get("undeclared_candidates", [])
    ]
    (out / "reused_tickers_audit.json").write_text(json.dumps(doc, indent=1))
    return doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true",
                    help="exit 3 when any un-acked zombie / delisted_printing / "
                         "member_identity name, or any undeclared ledger identity, exists")
    args = ap.parse_args(argv)
    try:
        doc = run()
    except Exception:  # noqa: BLE001 — crash is exit 2; data findings never raise
        log.exception("[reused_tickers] crashed")
        return 2
    if args.strict and (doc.get("unacked_zombies")
                        or doc.get("unacked_delisted_printing")
                        or doc.get("unacked_member_identity")
                        or doc.get("undeclared_ledger_identities")):
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
