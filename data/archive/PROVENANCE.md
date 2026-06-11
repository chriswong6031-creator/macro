# Archived OAS history — provenance

FRED serves only a rolling 3-year window for ICE BofA OAS series since
April 2026. The files here restore full history for classifier validation.

| file | series | range | source |
|---|---|---|---|
| BAMLH0A0HYM2.parquet | ICE BofA US High Yield OAS | 1996-12-31 .. 2025-11-03 | Wayback capture 2025-11-04 of fred.stlouisfed.org/graph/fredgraph.csv?id=BAMLH0A0HYM2 |
| BAMLC0A0CM.parquet | ICE BofA US Corporate OAS | 1996-12-31 .. 2024-10-24 | Wayback capture 2024-10-27 of fred.stlouisfed.org/data/BAMLC0A0CM (HTML table) |

Spot-checks at storage time (exact): HY 2008-12-15 = 21.82, 2020-03-23 = 10.87,
2021-06-15 = 3.17. IG 2008-12-15 = 6.51, 2020-03-23 = 4.01.
Publisher of underlying data: Federal Reserve Bank of St. Louis / ICE Data Indices.
Live observations (2023+) are merged from the ongoing FRED collector, whose
store is append-only — nothing fetched is ever dropped.
