# Source map — Prophet detail (`/stock.html#ONTO`)

- Live URL: `https://www.mastermind-x.com/stock.html#ONTO`
- Template: `templates/stock.html.j2` → `site/stock.html` (**VERIFIED** = live HTML)
- Payload: `stockdata/ONTO.json` — account-gated (401 anonymous). This run used in-memory session cookies; payload itself is **UNVERIFIED** vs local (gitignored).
- Chart: `#tvbox` + `lightweight-charts-v5.js`
- Verdict: `render()` / `ladderAction` / `DISP` — cycle caps the action verb
- Hash routing: `fromHash()` / `load(t)`
