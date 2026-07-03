# HK Connect Southbound Roster — provenance

Built 2026-07-03 by scripts/collect_hk_connect_roster.py.

## Source (usable, dated, free)
SSE 港股通公告 archive `sse.com.cn/services/hkexsc/disclo/announ/` — paginated
`s_list_N.shtml` (N=2..27, floor ~2015-09), each 关于沪港通下港股通标的调整的通知
`c/c_YYYYMMDD_ID.shtml` a structured table with 调入(add)/调出(remove) rows +
effective-date phrasing. This is the SH-HK southbound adjustment record.

## Routes tried and REJECTED (see research/H_INCL_PREREG.md §0)
- HKEX View-All-Eligible-Securities: NORTHBOUND (SSE/SZSE) only, no SEHK southbound list.
- akshare stock_hk_ggt_components_em: CURRENT snapshot only, no dates; host WAF-blocked.
- HKEX CCASS mutualmarket.aspx per-date search: STRICT ~365-day rolling window
  (2026/07/03..2025/07/03 populate; 2025/07/02 earlier empty) — cannot reach 2016.
- SZSE 深港通 notices parse identically (调入/调出/生效) — robustness cross-check,
  not the primary enumeration (annList API 500s to our UA).

## Columns
ticker (NNNN.HK panel form) · action (add|remove) · announce_date · code5 (raw 5-digit) ·
effective_date_fallback (announce+1 BDay; the analysis step overrides with the next _HSI
trading day) · source · notice_url.

## Caveat
The union southbound roster is SH-HK + SZ-HK (~90% overlapping); this file is the
SSE (沪港通) adjustment record, the cleanly-enumerable authoritative source.
