# Source vs browser route reconciliation

- Intersection (nav path also a top-level generated HTML file): 78
- Browser-only: 2 — , stocks/earnings/index.html
- Source-only (top-level html not in nav; families recorded, not all sampled): 169

Source-only includes generated strategy/fund/utility pages. They are user-facing if generated into `site/` without mock/qa prefix, but they are not primary-nav destinations.
