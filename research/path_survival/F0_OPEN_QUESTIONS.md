# F0 — Open Questions

**Commission:** MASTERMIND GROK-F0  
**As-of:** 2026-08-18

Questions only. No answers invented. Defaults in the contract draft are marked as defaults, not as rulings.

---

## A. Ownership / authority

1. Who is the Path Survival workstream owner, and does it `owns_paths` include `engine/grading.py`? No `WS-PATH-SURVIVAL` exists today. Inventing ownership is forbidden by the side-quest law.
2. Does Setup Species still own the *named* terminal-state objects (`clean8_21`, `clean15_126`), with Path Survival only adding context metrics? Masterplan §1.1 says those states are the primary verdict object.
3. Radar W5 prereg is frozen. May Path Survival lift ATR first-passage into `grading.py` without a Radar amendment, or is that a Radar-owned law that must be cited-and-called?
4. Eval-OS `do_not_redo` blocks retrospective qledger claims and horizons > 63. Does a path row on a board fire count as a new claim family (needs Eval-OS) or as a board-ledger column (already graded)?

---

## B. Definition forks (class-c if a build starts)

5. **Censoring:** spine returns `None` when `n_fwd < H`. Radar writes last-available + `censored=true`. Which is Path Survival v0? Contract draft defaults to spine. Radar-shaped rows may need the other.
6. **P0 for board fires that are not Radar episodes:** next-bar close only, or may a later wave attach `first_trade_after_known_at` without a minute store?
7. **`capture` units:** `track_scoring` reports median capture in **percent PnL / percent MFE** (already shipped). If the spine emits `capture`, must it be that exact quantity (including `MFE_FLOOR` and `n_capture_undefined`), or a 0–1 ratio? Do not mint a second name.
8. **Close-location:** mean of `(c−l)/(h−l)` over the window, last bar only, or fraction of bars closing in the top tercile of their range?
9. **Time underwater from fill:** count of closes < P0, or length of the longest consecutive run below P0, or time from fill until first reclaim of P0?
10. **Overnight vs RTH:** is baskets `open/prior_close` an acceptable *gap* proxy, or is the metric banned until a minute plane exists?
11. **False-start clause B** (StochRSI K + washout low): house primitive or Radar-only extra? Contract draft keeps it Radar-only.

---

## C. Data / coverage

12. What is on the VPS/R2 for `data/entry_radar/forward.parquet`? Local checkout is `WAITING_FOR_LIVE_SOURCE` / 0 rows. Production-forward availability of Radar path metrics is **UNKNOWN** beyond that local file.
13. Should Path Survival restore `massive_stock_day` from R2 for unadjusted open/high/low as a *diagnostic* plane, or is the SI ban absolute even for diagnostics?
14. Is `data/baskets/ohlcv` split+div adjusted on every column (open/high/low/close) or only close? Census treated it as an adjusted survivor tape (**PRIMARY SOURCE** from PSS reports) but did not independently verify open vs close basis on a known split.
15. `data/stocks` H/L vs `data/yahoo` close on the same name: are they the same TR vintage? A mismatch would make sibling `close_only` vs `ohlc` rows incomparable.
16. Does the Studio/VPS hold any Tushare minute partitions? Absent here.
17. Opening-auction: is there any US historical auction print (Polygon first-trade, NYSE open, etc.) already paid for and unused?

---

## D. Fill / corporate action

18. Confirm whether `data/stocks` high/low are jointly TR-adjusted with close (ratios cancel) or raw. `grading.py` discusses close; it does not mention H/L adjustment.
19. Ex-div flag source of record for gap-through exclusion (Radar W5 already requires one). Which calendar?
20. CN Path Survival: in or out of v0? CN fill is already a second convention by law. Mixing it into a US holdability table without `fill_convention` would be dishonest.
21. Mastermind `brain/outcomes` target-wins vs spine stop-wins: is the bot thesis label allowed to stay divergent forever, or must it eventually call the spine?

---

## E. Live-forward

22. Radar live source: what unblocks `WAITING_FOR_LIVE_SOURCE`? Path Survival must not invent a source.
22b. Who owns producing `day0_samples`? Attach/prereg declare it; `episodes.py` does not set it. Is that an unfinished M4 wire or a silent narrowing of the primary window?
22c. `engine/track_scoring.py` vs `engine/grading.py`: both are close-path graders used by board desks. Is Path Survival allowed to treat `capture` as spine-owned, or must capture stay on the Track-record desks' scorer?
23. If `ohlc` columns are added to `grade_us_board`, is that a schema union (nullable, keep-FRESH/FIRST?) on the existing parquet, and does nightly time budget allow H/L scans for the full board?
24. Are Path Survival rows allowed to accrue on the nightly, or only on an offline research runner (Radar W5 style)?

---

## F. Joins

25. Is there a durable fire id that Radar episodes, board rows, and SI episodes can share? None found.
26. `species_id` on board rows: how often is it still null? Masterplan required it; Stage B notes said null because multiple species bind. A holdability-by-species read is blocked until this is answered with a count.
27. SI W3 ruler vs Path Survival: if W3 ships a localization-first episode ruler, which object is the holdability read — the trade or the episode?

---

## G. What would flip the contract draft

- If the CEO/operator rules "Radar outcomes *are* the path grader and the spine stays close-only," then §2.2 of the contract is withdrawn and Path Survival is a documentation/join wave only.
- If yahoo H/L are about to be collected for the full universe, the 2014 baskets bound is temporary.
- If a minute plane is commissioned for another program (C3, CN mins), overnight/RTH can enter v1. It does not enter v0.

---

## H. Unverified on purpose (session bounds)

- VPS live `forward.parquet` and nightly Radar reconcile output.
- Row-level `species_id` fill rate on `grade_us_board` output.
- Exact `data/signal_archive/track_record.parquet` schema on this checkout (not opened).
- Mastermind production `held_risk` marks vs which price vendor.
- Whether `data/baskets/ohlcv` open is dividend-adjusted.
- Full Agent OS discovery corpus beyond the WS files named in the commission.

Those are UNKNOWN, not zeros.
