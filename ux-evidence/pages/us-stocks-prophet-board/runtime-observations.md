# Runtime observations — Prophet board

Capture window: 2026-08-16T12:12Z via AionUi in-app browser CDP.

## Auth / session

- Anonymous session: `html[data-user]=null`, no account chip.
- Board still rendered 69 `.pvcard` nodes and full overnight copy. No paywall overlay observed on this load.
- `templates/tier_preview.js` can gate `#us-standouts`; that state was **not** triggered here.

## Network / console

- CDP recorded many `Network.loadingFailed` / `net::ERR_ABORTED` (Fetch, Script, Stylesheet, Document, Ping) during navigations and viewport changes. These look like aborted in-flight loads from `Page.navigate` / emulation, not a visibly broken board.
- No React overlay (page is static HTML + vanilla JS).
- Live quote dashes (“—”) appeared next to card prices at capture time (e.g. ONTO $337.82 —).

## Behavior vs source

| Topic | Source intent | Observed |
|---|---|---|
| Stage filter | CSS hide via `#us-standouts[data-stagef]` | URL unchanged. Live=28 visible, Setting up=31, Ran label 20 but only 8 visible (pagination), Basing=1, Blocked=1 |
| “All 81” vs “69 shown” | Header says 69 shown / 77 setups; filter All badge is 81 | Three different counts visible at once |
| Grid default | Cards | Default is card grid; first rows are LIVE NOW |
| Table view | `st-table-mode` | Table appears with extra filters (Search, Stage, Sector, Lane, Fresh only). Page also shows “WHAT TO ACT ON NOW” sector rail above the board |
| Track record | dialog `#trd-dlg` | Opens as modal; `aria-expanded=true`; copy matches 59.6% / +1.19% / 386 trades |
| `#prophet-live` | optional live panel | Present in DOM, `hidden` |
| Pagination | “Show 15 more” / “Show all 74” | Default grid showed 15 of 74 in the live section plus a “Passed on tonight 20 of 69” rail |
| Help `?` | CSS tooltip | Hover/focus script ran; extracted tooltip text was only “?” — full tip copy may be in a child not exposed as `innerText` until hover CSS applies |
| Light / ZH | `data-theme` / `data-lang` | Attribute toggle restyled the board (screenshots taken). This did **not** persist via Settings UI; it was a DOM attribute write |

## Capture artifacts (not product bugs unless confirmed elsewhere)

- Many 1440×1000 PNGs show a **right-hand duplicate strip** of the same page. The in-app webview is narrower than the emulated 1440 width; `Emulation.setDeviceMetricsOverride` layouts at 1440 then the compositor shows overflow. Treat the left ~80% as the intended frame.
- Scroll-mid and scroll-top shots after later interactions look similar because stage-filter / table restore left the board mid-page.

## Keyboard

- Not systematically tab-tested. Track record uses a real `<button>` + dialog. Stage filters are `<button>`. Cards are `<a href>`.
