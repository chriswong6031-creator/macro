"""Guard `collectors.china_universe._index_constituents` — the CSI index union.

The search universe unions CSI 300 + CSI 1000 into the Sina top-N. Sourced from
`ak.index_stock_cons`, that union shipped SHORT and silent: the 1000-row CSI 1000
frame carries only 772 unique codes (288 of 300 for CSI 300, measured 2026-08-04),
dropping 228 real constituents — 002716.SZ 湖南白银 among them — while the collector
logged `len(df)` = 1000 as if coverage were full and deduplicated the shortfall away
downstream. Nothing tested this function, so the gap shipped dark.

`ak.index_stock_cons_csindex` (official CSIndex) is the fix, and its columns are the
trap the first tests here exist to pin: the frame carries 指数代码/指数名称 (the INDEX's own
code and name) alongside 成分券代码/成分券名称, so the old "代码"/"名称" substring scan matches
the index columns FIRST and maps every row to one bogus ticker. No network.

Three further defects, measured 2026-08-05 (receipts: research/CHINA_FULL_UNIVERSE_
MASTERPLAN_BY_FABLE.md §7.7, PR #4587), are pinned below:

1. **No timeout.** akshare's csindex reader is a bare `requests.get(url)` — no timeout
   argument, so it inherits requests' "wait forever". A probe from the nightly host hung
   **742 s**; the only other bound was the 165-min asia-close job cap. The collector now
   fetches the same .xls itself through `http_get`, with an explicit timeout.
2. **The lossy fallback is silent, and it FIRES.** A live probe on 2026-08-05 returned
   `src='index_stock_cons'` for 000300 on an ordinary night — the degraded path is not
   hypothetical. It only `log.warning`-ed, so universe membership flickered night to
   night, and a name leaving china_search freezes its `closes` column and is marked in
   `dropped.parquet`. It must now raise a GitHub annotation and prefer the last
   known-good membership.
3. **The raw .xls speaks a different header dialect than akshare's reader** — bilingual
   headers built on 成**份**券 (fen4) where akshare's positional rename writes 成**分**券
   (fen1), with int64 constituent codes (平安银行 arrives as `1`). A parser pinned to one
   dialect silently reads zero constituents from the other.
"""
from __future__ import annotations

import logging
import sys
import types
from io import BytesIO
from pathlib import Path

import pandas as pd
import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors import china_universe as cu  # noqa: E402

CSINDEX_COLS = ["日期", "指数代码", "指数名称", "指数英文名称", "成分券代码",
                "成分券名称", "成分券英文名称", "交易所", "交易所英文名称"]

# The RAW .xls headers, verified against the live file 2026-08-05. Bilingual, and the
# constituent columns use 成份 (fen4) — NOT akshare's 成分 (fen1). Reproduced exactly so a
# parser that only knows akshare's dialect fails here instead of in the nightly.
RAW_COLS = ["日期Date", "指数代码 Index Code", "指数名称 Index Name",
            "指数英文名称Index Name(Eng)", "成份券代码Constituent Code",
            "成份券名称Constituent Name", "成份券英文名称Constituent Name(Eng)",
            "交易所Exchange", "交易所英文名称Exchange(Eng)"]

# The live 000852 frame's own index code — a valid 6-digit code that _code_to_ticker
# maps to 000852.SZ, so a substring-scan column pick is DETECTABLE in the output
# rather than merely plausible. Never reused as a constituent code below.
INDEX_CODE = "000852"
EXPECTED_852 = cu._INDEX_EXPECTED_SIZE[INDEX_CODE]     # 1000 — 中证1000, not 852

# A real CSIndex symbol (中证红利) deliberately absent from the size table: a
# dividend-screen index has no fixed member count, so it is the case where the shortfall
# check cannot fire and the source check has to carry the alarm alone.
UNSIZED_INDEX = "000922"


def _csindex_frame(codes: list[str], names: list[str] | None = None) -> pd.DataFrame:
    """A CSIndex-shaped frame as akshare hands it over (all nine columns, 成分 dialect)."""
    names = names or [f"名称{c}" for c in codes]
    n = len(codes)
    return pd.DataFrame({
        "日期": ["2026-08-04"] * n,
        "指数代码": [INDEX_CODE] * n,
        "指数名称": ["中证1000"] * n,
        "指数英文名称": ["CSI 1000"] * n,
        "成分券代码": list(codes),
        "成分券名称": list(names),
        "成分券英文名称": [f"EN {c}" for c in codes],
        "交易所": ["深圳证券交易所"] * n,
        "交易所英文名称": ["Shenzhen Stock Exchange"] * n,
    })[CSINDEX_COLS]


def _raw_xls_bytes(codes: list[int | str], names: list[str] | None = None,
                   english_first: bool = False) -> bytes:
    """The .xls as CSIndex serves it: bilingual 成份 headers, INT constituent codes.

    `english_first` moves 成份券英文名称Constituent Name(Eng) ahead of the Chinese name
    column, so a pick that only wins by column ORDER is separable from one that wins on
    the header text.
    """
    names = names or [f"名称{c}" for c in codes]
    n = len(codes)
    df = pd.DataFrame(dict(zip(RAW_COLS, [
        [20260804] * n, [300] * n, ["沪深300"] * n, ["CSI 300"] * n,
        list(codes), list(names), [f"EN {c}" for c in codes],
        ["深圳证券交易所"] * n, ["Shenzhen Stock Exchange"] * n,
    ])))
    if english_first:
        cn, en = RAW_COLS[5], RAW_COLS[6]
        df = df[[c for c in RAW_COLS if c not in (cn, en)][:5] + [en, cn]
                + [c for c in RAW_COLS[7:]]]
    buf = BytesIO()
    df.to_excel(buf, index=False)
    return buf.getvalue()


class _Resp:
    """The only attribute _csindex_direct touches on an http_get result."""

    def __init__(self, content: bytes) -> None:
        self.content = content


def _install_ak(monkeypatch, *, csindex=None, legacy=None) -> None:
    """Inject a fake `akshare` — the collector imports it lazily inside the function."""
    def _absent(*a, **kw):
        raise AssertionError("this endpoint must not be called")
    mod = types.ModuleType("akshare")
    mod.index_stock_cons_csindex = csindex or _absent
    mod.index_stock_cons = legacy or _absent
    monkeypatch.setitem(sys.modules, "akshare", mod)


@pytest.fixture()
def adapter(tmp_path, monkeypatch):
    """Adapter whose cache lives in tmp_path and whose DIRECT csindex fetch is dead.

    Dead-by-default keeps the akshare-dialect tests below aimed at what they were
    written for, and — because no test may touch the network — makes a test that means
    to exercise the direct rung say so by stubbing `http_get` itself.  The stub raises a
    plain RuntimeError, NOT a connection error: an unreachable host deliberately skips
    akshare's untimed reader (see the host-dead test), which would silence rung 2.
    """
    ad = cu.ChinaUniverseAdapter()
    ad.dir = tmp_path
    ad.index_cache_path = tmp_path / "index_cons.parquet"
    monkeypatch.setattr(ad, "http_get", lambda *a, **kw: (_ for _ in ()).throw(
        RuntimeError("csindex .xls not stubbed for this test")))
    return ad


def _annotations(capsys) -> list[str]:
    """Stdout lines that GitHub would actually parse as a workflow command.

    `startswith` is the whole point: every builder here logs through a prefixing
    formatter, so an annotation emitted via `log.warning` arrives as
    `WARNING ::warning …` and GitHub silently drops it — an alarm that reviews as
    wired and produces nothing (tests/test_gh_annotation_line_start.py).
    """
    return [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("::")]


# --------------------------------------------------------------------------
# Column selection + code mapping (both header dialects)
# --------------------------------------------------------------------------

def test_constituents_come_from_the_constituent_columns(monkeypatch, adapter):
    """THE mutation test: 成分券代码/成分券名称 by name, never a 代码/名称 substring scan.

    A scan picks 指数代码 ('000852' → 000852.SZ) and 指数名称 ('中证1000') for EVERY row.
    The legacy endpoint is wired to explode, so preferring csindex is pinned too."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["600519", "002716", "000001"], ["贵州茅台", "湖南白银", "平安银行"]))

    rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS", "002716.SZ", "000001.SZ"]
    assert [r["name_zh"] for r in rows] == ["贵州茅台", "湖南白银", "平安银行"]
    assert "000852.SZ" not in {r["ticker"] for r in rows}, "index code leaked in as a constituent"
    assert "中证1000" not in {r["name_zh"] for r in rows}, "index name leaked in as a constituent"


def test_raw_xls_dialect_parses_with_the_same_discrimination(monkeypatch, adapter, capsys):
    """The direct .xls speaks 成份券代码Constituent Code, and types codes as int64.

    Two ways to read zero constituents off it: pin the parser to akshare's 成分 (fen1)
    spelling, or let the ENGLISH column '成份券英文名称Constituent Name(Eng)' win the name
    pick — it contains the lowercased marker 'constituent name'. Codes arrive as ints
    (平安银行 is `1`, not '000001'), so the zero-pad is load-bearing too."""
    monkeypatch.setattr(adapter, "http_get",
                        lambda *a, **kw: _Resp(_raw_xls_bytes(
                            [1, 63, 600519], ["平安银行", "中兴通讯", "贵州茅台"])))
    _install_ak(monkeypatch)          # both akshare endpoints explode if reached

    rows = adapter._index_constituents(["000300"])

    assert [r["ticker"] for r in rows] == ["000001.SZ", "000063.SZ", "600519.SS"]
    assert [r["name_zh"] for r in rows] == ["平安银行", "中兴通讯", "贵州茅台"]
    assert not any("EN " in r["name_zh"] for r in rows), "English name column won the pick"


def test_column_pick_does_not_depend_on_column_order(monkeypatch, adapter):
    """The English constituent column must lose on its NAME, not on its position.

    '成份券英文名称Constituent Name(Eng)' contains the lowercased marker 'constituent name',
    so with the Chinese column merely sitting to its left the exclusion looks load-bearing
    while doing nothing. Put English first and the pick has to earn it — otherwise every
    name_zh in the universe silently becomes an English string."""
    monkeypatch.setattr(adapter, "http_get",
                        lambda *a, **kw: _Resp(_raw_xls_bytes(
                            [1, 600519], ["平安银行", "贵州茅台"], english_first=True)))
    _install_ak(monkeypatch)

    rows = adapter._index_constituents(["000300"])

    assert [r["ticker"] for r in rows] == ["000001.SZ", "600519.SS"]
    assert [r["name_zh"] for r in rows] == ["平安银行", "贵州茅台"]


def test_float_typed_codes_survive_the_zero_pad():
    """A NaN anywhere in the column promotes it to float, so 平安银行 arrives as `1.0` —
    which zfill(6) turns into '0001.0' and _code_to_ticker then drops as non-digit."""
    assert cu._norm_code(1.0) == "000001"
    assert cu._norm_code(600519.0) == "600519"
    assert cu._code_to_ticker(cu._norm_code(1.0)) == "000001.SZ"


def test_duplicate_codes_collapse_to_one_entry(monkeypatch, adapter):
    """The exact shape of the legacy defect: repeated codes must not inflate the union."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["002716", "600519", "002716", "600519"]))

    tickers = [r["ticker"] for r in adapter._index_constituents([INDEX_CODE])]

    assert tickers == ["002716.SZ", "600519.SS"]


def test_beijing_codes_are_dropped(monkeypatch, adapter):
    """Beijing's code space is 4xxxxx / 8xxxxx AND 92xxxx — the segment the BSE has
    issued since 2023 (920045, 920807 奔朗新材, 920914 远航精密, all live in 同花顺
    concept-board data). 92xxxx used to fall into the .SS branch that exists for
    Shanghai's 900xxx B-shares, minting a NONEXISTENT '920045.SS': yfinance returns
    nothing for it and `dropna(axis=1, how='all')` then deletes the column, so the
    bad mapping shrinks the universe silently instead of raising."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["830799", "430418", "920045", "920914", "688508", "300061"]))

    tickers = [r["ticker"] for r in adapter._index_constituents([INDEX_CODE])]

    assert tickers == ["688508.SS", "300061.SZ"]


def test_shanghai_b_shares_are_not_swept_up_by_the_beijing_exclusion(monkeypatch, adapter):
    """The other half of the same edge: 900xxx really IS Shanghai (SSE B-shares), so
    excluding 92xxxx must not degrade into dropping every 9-prefixed code."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(["900001", "600519"]))

    tickers = [r["ticker"] for r in adapter._index_constituents([INDEX_CODE])]

    assert tickers == ["900001.SS", "600519.SS"]


def test_logged_count_is_the_union_not_the_row_count(monkeypatch, adapter, caplog):
    """The old log printed len(df), so a 1000-row/772-code frame read as full coverage."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        ["002716", "002716", "830799", "600519"]))

    with caplog.at_level(logging.INFO, logger="collectors.china_universe"):
        adapter._index_constituents([INDEX_CODE])

    line = next(m for m in caplog.messages if "CSI index" in m)
    assert "2 constituents" in line and "4" in line, line


# --------------------------------------------------------------------------
# Defect 1 — the CSIndex fetch must be time-bounded
# --------------------------------------------------------------------------

def test_direct_fetch_passes_an_explicit_timeout(monkeypatch, adapter):
    """akshare's reader is `requests.get(url)` with NO timeout — a stall there hung 742 s,
    bounded by nothing but the 165-min job cap. The direct fetch must carry a positive
    timeout AND the configured retry/backoff, and must not fall through to the untimed
    reader when it succeeds."""
    seen: dict = {}

    def _http_get(url, **kw):
        seen["url"] = url
        seen.update(kw)
        return _Resp(_raw_xls_bytes([600519]))

    monkeypatch.setattr(adapter, "http_get", _http_get)
    _install_ak(monkeypatch)          # both akshare endpoints explode if reached

    rows = adapter._index_constituents(["000300"])

    assert [r["ticker"] for r in rows] == ["600519.SS"]
    assert seen["url"] == cu._CSINDEX_CONS_URL.format(symbol="000300")
    assert isinstance(seen.get("timeout"), (int, float)) and seen["timeout"] > 0, \
        f"CSIndex fetch has no positive timeout: {seen!r}"
    assert seen.get("retries", 0) >= 1 and seen.get("backoff_base", 0) > 0, seen


def test_unreachable_host_skips_the_untimed_akshare_reader(monkeypatch, adapter, capsys):
    """Rung 2 hits the SAME host with a call that cannot time out. When rung 1 failed
    because the host is unreachable, retrying through it re-opens the 742 s hang, so it
    must be skipped entirely and the legacy endpoint used instead.

    The reader is wired to SUCCEED and record itself rather than to raise: `_index_rows`
    catches Exception around rung 2, so a stub that asserts gets swallowed and the test
    passes no matter what the code does (mutation-confirmed, 2026-08-05). Recording makes
    the call visible, and returning good data makes the fallthrough visible in the output
    too — two independent ways for this to go red."""
    reader_calls: list[str] = []

    def _dead(*a, **kw):
        raise requests.exceptions.ConnectTimeout("oss-ch.csindex.com.cn: timed out")

    def _records(symbol):
        reader_calls.append(symbol)
        return _csindex_frame(["600519"])          # names 名称600519, vs legacy's 旧600519

    monkeypatch.setattr(adapter, "http_get", _dead)
    _install_ak(monkeypatch, csindex=_records,
                legacy=lambda symbol: _legacy_frame(["600519"]))

    rows = adapter._index_constituents([INDEX_CODE])

    assert reader_calls == [], "akshare's untimed csindex reader was called on a dead host"
    assert [r["name_zh"] for r in rows] == ["旧600519"], "rung 2 served this, not the legacy rung"
    assert _annotations(capsys), "a legacy-served index must still annotate"


def test_akshare_absent_no_longer_disables_the_csindex_source(monkeypatch, adapter):
    """The .xls is fetched by this adapter now, so a missing optional dep costs the two
    fallback rungs — not the authoritative source it used to cost."""
    monkeypatch.setitem(sys.modules, "akshare", None)   # `import akshare` -> ImportError
    monkeypatch.setattr(adapter, "http_get",
                        lambda *a, **kw: _Resp(_raw_xls_bytes([600519, 2])))

    rows = adapter._index_constituents(["000300"])

    assert [r["ticker"] for r in rows] == ["600519.SS", "000002.SZ"]


# --------------------------------------------------------------------------
# Defect 2 — a degraded index must be annotated, never silently shipped short
# --------------------------------------------------------------------------

def _legacy_frame(codes: list[str]) -> pd.DataFrame:
    """`ak.index_stock_cons` shape: ['品种代码','品种名称','纳入日期']."""
    return pd.DataFrame({"品种代码": list(codes),
                         "品种名称": [f"旧{c}" for c in codes],
                         "纳入日期": ["2026-06-13"] * len(codes)})


def test_falls_back_to_legacy_endpoint_when_csindex_fails(monkeypatch, adapter, caplog):
    """Old akshare (no csindex attr) or a CSIndex outage still yields constituents,
    with the incompleteness said out loud."""
    def _boom(symbol):
        raise RuntimeError("csindex down")

    _install_ak(monkeypatch, csindex=_boom,
                legacy=lambda symbol: _legacy_frame(["600519", "002716"]))

    with caplog.at_level(logging.WARNING, logger="collectors.china_universe"):
        rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS", "002716.SZ"]
    assert [r["name_zh"] for r in rows] == ["旧600519", "旧002716"]
    assert any("KNOWN-INCOMPLETE" in m for m in caplog.messages)


def test_legacy_fallback_emits_an_annotation_that_starts_the_line(monkeypatch, adapter,
                                                                 capsys, caplog):
    """The measured defect: a live probe on 2026-08-05 got src='index_stock_cons' for
    000300 on an ordinary night, and the collector only log.warning-ed it.

    The annotation must START its line — routed through a logger it arrives as
    'WARNING ::warning …' and GitHub drops it — and it must be ONE line, since GitHub
    parses a workflow command per line."""
    _install_ak(monkeypatch, csindex=lambda symbol: (_ for _ in ()).throw(
        RuntimeError("csindex down")), legacy=lambda symbol: _legacy_frame(["600519"]))

    with caplog.at_level(logging.WARNING, logger="collectors.china_universe"):
        adapter._index_constituents([INDEX_CODE])

    lines = _annotations(capsys)
    assert len(lines) == 1, lines
    assert lines[0].startswith("::warning title=csindex-fallback::"), lines[0]
    assert "index_stock_cons" in lines[0] and f"{EXPECTED_852} expected" in lines[0]
    assert lines[0].endswith("dropped.parquet"), "annotation was split across lines"
    assert not any(m.startswith("::") for m in caplog.messages), \
        "annotation went through the logger — GitHub would drop it"


def test_the_lossy_endpoint_is_degraded_even_with_no_known_size(monkeypatch, adapter,
                                                               capsys):
    """The source check and the count check must BOTH stand on their own.

    For a symbol absent from `_INDEX_EXPECTED_SIZE` the shortfall check is inert, so only
    'index_stock_cons served this' is left to notice a known-lossy list — and with a size
    in the table the two conditions cover for each other, hiding the loss of either
    (mutation-confirmed, 2026-08-05)."""
    assert UNSIZED_INDEX not in cu._INDEX_EXPECTED_SIZE, "fixture no longer unsized"
    _install_ak(monkeypatch, csindex=lambda symbol: (_ for _ in ()).throw(
        RuntimeError("csindex down")),
        legacy=lambda symbol: _legacy_frame(["600519", "002716"]))

    rows = adapter._index_constituents([UNSIZED_INDEX])

    assert [r["ticker"] for r in rows] == ["600519.SS", "002716.SZ"]
    line = _annotations(capsys)[0]
    assert line.startswith("::warning title=csindex-fallback::"), line
    assert "index_stock_cons" in line and "expected size unknown" in line, line


def test_shortfall_is_annotated_even_from_the_authoritative_source(monkeypatch, adapter,
                                                                  capsys):
    """The count check is explicit and source-independent: csindex itself can serve a
    truncated table, and 288-of-300 is a shortfall whoever hands it over."""
    short = [str(600000 + i) for i in range(int(EXPECTED_852 * 0.9))]
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(short))

    rows = adapter._index_constituents([INDEX_CODE])

    assert len(rows) == len(short)
    line = _annotations(capsys)[0]
    assert f"{len(short)} unique mappable tickers" in line
    assert f"{EXPECTED_852} expected" in line


def test_a_complete_index_is_silent_and_caches(monkeypatch, adapter, capsys):
    """The control: a full index must NOT annotate (an alarm that always fires is noise)
    and must leave the known-good membership behind for a degraded night."""
    full = [str(600000 + i) for i in range(EXPECTED_852)]
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(full))

    rows = adapter._index_constituents([INDEX_CODE])

    assert len(rows) == EXPECTED_852
    assert _annotations(capsys) == []
    cached = pd.read_parquet(adapter.index_cache_path)
    assert len(cached) == EXPECTED_852
    assert set(cached["symbol"].astype(str)) == {INDEX_CODE}


def test_shortfall_within_tolerance_is_not_degraded(monkeypatch, adapter, capsys):
    """A one-name gap is index maintenance, not an outage — the tolerance must hold."""
    near = [str(600000 + i) for i in range(EXPECTED_852 - 1)]
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(near))

    adapter._index_constituents([INDEX_CODE])

    assert _annotations(capsys) == []


# --------------------------------------------------------------------------
# Defect 2b — a transient blip must not SHRINK the universe
# --------------------------------------------------------------------------

def test_degraded_night_serves_the_cached_membership(monkeypatch, adapter, capsys):
    """The cost of shipping the short list is not abstract: every name it drops freezes
    that ticker's `closes` column and is marked in dropped.parquet. So a night that lands
    on the lossy endpoint serves the last known-good membership instead."""
    full = [str(600000 + i) for i in range(EXPECTED_852)]
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(full))
    adapter._index_constituents([INDEX_CODE])            # healthy night: fills the cache
    capsys.readouterr()

    _install_ak(monkeypatch, csindex=lambda symbol: (_ for _ in ()).throw(
        RuntimeError("csindex down")), legacy=lambda symbol: _legacy_frame(["600519"]))
    rows = adapter._index_constituents([INDEX_CODE])

    assert len(rows) == EXPECTED_852, "a one-name legacy list shrank the universe"
    assert {r["ticker"] for r in rows} == {cu._code_to_ticker(c) for c in full}
    line = _annotations(capsys)[0]
    assert line.startswith("::warning title=csindex-fallback::")
    assert "serving the cached membership" in line and f"{EXPECTED_852} tickers" in line


def test_a_stale_cache_is_not_preferred_to_a_fresh_short_list(monkeypatch, adapter, capsys):
    """Holding prior membership rides out a BLIP. Months later the cached constituent list
    is the worse answer, so the age gate must hand the night back to the live list."""
    old = str((pd.Timestamp.utcnow().tz_localize(None).normalize()
               - pd.Timedelta(days=400)).date())
    pd.DataFrame([{"symbol": INDEX_CODE, "ticker": f"{600000 + i}.SS",
                   "name_zh": "旧", "fetched_date": old}
                  for i in range(EXPECTED_852)]).to_parquet(adapter.index_cache_path,
                                                            index=False)
    _install_ak(monkeypatch, csindex=lambda symbol: (_ for _ in ()).throw(
        RuntimeError("csindex down")), legacy=lambda symbol: _legacy_frame(["600519"]))

    rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS"]
    assert "no usable cached membership" in _annotations(capsys)[0]


def test_an_unreadable_cache_does_not_kill_the_run(monkeypatch, adapter, capsys):
    """The cache is resilience, never a gate."""
    adapter.index_cache_path.write_bytes(b"not a parquet file")
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(["600519"]))

    rows = adapter._index_constituents([INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["600519.SS"]
    assert _annotations(capsys), "still a shortfall, still annotated"


def test_unchanged_membership_does_not_rewrite_the_committed_cache(monkeypatch, adapter):
    """`index_cons.parquet` is committed. Re-stamping it nightly for an index whose
    members did not move is 365 diffs a year of pure churn."""
    full = [str(600000 + i) for i in range(EXPECTED_852)]
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(full))
    adapter._index_constituents([INDEX_CODE])
    before = adapter.index_cache_path.read_bytes()

    adapter._index_constituents([INDEX_CODE])

    assert adapter.index_cache_path.read_bytes() == before


def test_cache_is_per_index(monkeypatch, adapter):
    """Two indices share one file; refreshing 000300 must not evict 000852's rows."""
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        [str(600000 + i) for i in range(EXPECTED_852)]))
    adapter._index_constituents([INDEX_CODE])
    _install_ak(monkeypatch, csindex=lambda symbol: _csindex_frame(
        [str(601000 + i) for i in range(cu._INDEX_EXPECTED_SIZE["000300"])]))
    adapter._index_constituents(["000300"])

    counts = pd.read_parquet(adapter.index_cache_path)["symbol"].astype(str).value_counts()

    assert counts.to_dict() == {INDEX_CODE: EXPECTED_852,
                                "000300": cu._INDEX_EXPECTED_SIZE["000300"]}


# --------------------------------------------------------------------------
# Best-effort contract
# --------------------------------------------------------------------------

def test_one_failing_index_does_not_block_the_other(monkeypatch, adapter):
    """Both endpoints dead for 000300; 000852 must still come back (best-effort)."""
    def _csindex(symbol):
        if symbol == "000300":
            raise RuntimeError("csindex down")
        return _csindex_frame(["002716"])

    def _legacy(symbol):
        raise RuntimeError("legacy down")

    _install_ak(monkeypatch, csindex=_csindex, legacy=_legacy)

    rows = adapter._index_constituents(["000300", INDEX_CODE])

    assert [r["ticker"] for r in rows] == ["002716.SZ"]


def test_missing_akshare_and_a_dead_csindex_is_not_fatal(monkeypatch, adapter, capsys):
    monkeypatch.setitem(sys.modules, "akshare", None)   # `import akshare` -> ImportError
    assert adapter._index_constituents([INDEX_CODE]) == []
    assert _annotations(capsys), "a total miss must still annotate"
