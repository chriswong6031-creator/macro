---
key: OPEX-FUTURE-MONTH-LAST-OBS-CLAMP
claim: >
  engine/opex.py expiration_days maps every month's third Friday to the last index
  date <= that Friday with no future-expiration guard, stores results in a date-keyed
  dict, and last-write-wins; future months collapse onto the series tail and a later
  December pass stamps is_quad=True onto that observation. A history ending 2026-08-19
  therefore labels Wednesday Aug. 19 a quad expiration (td_to=0, td_since=0) even though
  the real August monthly is Friday Aug. 21 (engine.options_stamp._opex_stamp reports
  opt_opex_days=2). There is no tests/test_opex.py.
falsifier: >
  python3 against engine.opex.expiration_days(pd.bdate_range("2024-01-02","2026-08-19"))
  with 2026-08-19 absent from the returned index and is_quad false on that date; or
  tests/test_opex.py Case A green on origin/main.
so_what: >
  Do not treat Intraday Flow glance_en "0d to expiry / quad-witching" as market fact
  while this function is unfixed. Fix expiration_days (skip months whose Friday is
  after idx[-1]; no date-key overwrite) and make tag() td_to null-safe. Do not
  hand-edit generated site/vol/regime.json. Display-only — do not promote OPEX to
  sizing authority.
kind: architecture
verified_at: 2026-08-19
verified_by: >
  In-memory fixture python3 - engine.opex.expiration_days/tag on bdate_range ending
  2026-08-19; engine/opex.py:41-54 date-keyed loop; engine.options_stamp._opex_stamp
  date(2026,8,19) -> opt_opex_days=2; no tests/test_opex.py on origin/main.
scope:
  - macro
  - options-intelligence
  - engine/opex.py
confidence: verified
---
