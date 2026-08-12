# W2 mockup gate — Portfolio Intelligence workspace

Artifact for the W2 mockup gate of the Watchlist + Portfolio CEO revamp
(`research/MASTERMIND_WATCHLIST_PORTFOLIO_W0_COMMISSIONING_PACKET_2026-08-12.md` §5/§12,
CEO handoff §14–§17). **Not production code.** The commissioning session reviews the crops
and pins this as the exact design for the W2 builder.

- Mockup: `workspace.html` — self-contained, opens standalone.
  Harness: `?state=anon-empty|anon-analyzed|portfolio|watchlists|chips`, `&theme=light`,
  `&lang=zh`, `&bare=1` (hides the harness bar; all crops are `bare`).
- Crops: `crops/` — 5 states × {desktop dark EN, desktop light EN, desktop ZH, 390 dark EN,
  390 dark ZH} = 25 PNGs at 2× device scale, full-page (viewports 1440×900 and 390×844).
  The harness is byte-deterministic **except** for the `05_savechip` set: the `Saving…` chip's
  `chippulse` dot animation is sampled at whatever phase the shot lands on, so those five re-render
  with ~248 differing pixels every time. Re-shoot them only when state (e) actually changes.

---

## 1. The signature: **the Book Seam**

One signature, spent deliberately. It is the **BOOK READ card treatment**, not the attention
stack — and the attention stack was the runner-up, rejected for a specific reason (§1.3).

**What it is.** Under the book read's plain-language sentence sit two hairline rails of equal
width, one segment per position, same order:

```
        ┌──────────── 75% of the money ─────────────┐
MONEY  [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░░░░░▨▨]     ← every position
                                    ┆▒▒▒▒▒┆          ← the overhang
RISK   [▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓░░░░◌ ]      ← modeled risk only
        └───────────── 85% of the risk ─────────────┘
```

Top rail = each position's share of the **money**. Bottom rail = its share of the **modeled
risk**. A bracket over each rail names the dominant cluster's share; a dashed guide drops from
the money edge and a faint wash covers the ground the risk bracket takes but the money bracket
does not. The difference between the two bracket widths *is* the finding.

**Why this and not a KPI tile row.** The frontend-design skill names "a big number with a small
label, supporting stats, and a gradient accent" as the template answer, and the CEO handoff §16
explicitly asks for less "pile of unrelated cards". The single truest thing a portfolio engine
can tell someone — and the thing their brokerage app cannot — is that **the sizes they chose are
not the risks they took**. That deserves the page's one memorable device. The book read is
therefore a *sentence* at 30px with the computed figures set heavier and in tabular mono
("These **12** positions move like about **3** bets."), and the seam is the sentence's evidence.

**The honesty is the design — the part I'd defend hardest.** A position the risk model does not
cover (IBIT here) is hatched on the money rail — it is real money — and drawn as an **empty
outline** on the risk rail, and it is excluded from the risk denominator. The coverage
disclosure the doctrine requires in words is *also* rendered as a shape. The compliant thing
and the beautiful thing are the same object, which is why the device survives review pressure
in a way a decorative graphic would not.

**Direction-neutral by construction.** The seam paints only from `--link` and `--muted`, never
from `--up`/`--down`. Under `html[data-lang="zh"]` the direction pair swaps (红涨绿跌) and the
seam is untouched — correct, because it encodes *composition*, not direction.

### 1.1 It is not the count ladder, and does not borrow it

The count ladder is reserved to the Board archetype (P0 packet §330 anti-sameness contract).
Four properties keep these distinct:

| | Count ladder (Board) | Book Seam (this page) |
|---|---|---|
| Cell meaning | a **stage enum** category | one **individual position** |
| Arithmetic law | integer cells summing to the page's canonical total | two continuous **100% distributions** |
| Interaction | cells **are** the filter control | read-only; hover names the position |
| Claim | "how many setups exist" | "money and risk are split differently" |

Neither holdings table borrows ladder geometry either — no cell strip, no counted filter row.

### 1.2 What I *did* adopt from the P0 packet (system law, not archetype device)

**Stage is encoded by weight, never by hue** (P0 §0, binding all pages): Early = dashed outline ·
Confirming = half-filled · Confirmed = solid strong ink · Losing steam = solid muted · Running
hot = solid muted **overshooting its own end cap** · Broke down = hollow, struck · Not covered =
dotted, dimmed. This survives the zh direction flip and never collides with the `--up`/`--down`
inks. **Violet stays lock-only** (`.mx-tier-gate--prophet`, `#7c5cff`) — it appears in exactly
two places, both meaning *locked*.

### 1.3 Why not the attention stack

"What needs attention" is content-identical to Archetype A's `.chg-row` (name · change clause ·
stance verb · chevron) on `start.html`. Making it *this* page's signature would collide with A
head-on. So it **composes** that grammar rather than reinventing it, and stays visually quiet.

---

## 2. Primitives composed, and where each came from

No new token system, no new header family, no new card grammar.

| Composed | Source | Use here |
|---|---|---|
| Full token set (`--bg/--panel/--panel2/--text/--muted/--line`, `--up/--down`, `--warn/--act/--ok`, `--link/--info`, glass + `gbtn` sets, `--ink-*` rungs) | `templates/theme.css` — copied **verbatim**, values unchanged | every colour on the page |
| `.mx-tier-gate` / `--prophet` / `-copy` / `-eyebrow` / `-mark` / `-actions` / `-primary` / `-signin` | `templates/tier_preview.css` — copied verbatim | the anonymous save gate |
| `.gbtn` + `-sm` + `-cta` recipe | `theme.css` gbtn block | every button |
| `.pos` / `.neg` → `--ink-up` / `--ink-down` | `theme.css` | since-entry figures only |
| `.l-en` / `.l-zh` dual emit + `html[data-lang="zh"]` CJK stack | `theme.css:337-347` | all bilingual copy |
| `data-tip-en` / `data-tip-zh` (LENS contract) | `theme.css:1615` | every Tier-2 receipt (197 tips) |
| aurora `body::before`, both themes | `theme.css` | page backdrop |
| `.chg-row` grammar (name · clause · stance · chevron) | P0 packet Archetype A | the attention stack |
| `.tbl-filter` search field styling | `theme.css:894` | table filters |

**Institutionalize PR-0 is not on `origin/main`** (verified: no type ramp, no `.empty-why`, no
stage field in `theme.css` at `e0ed5f89b9a`). Per packet §11 I therefore composed what exists and
minted **no parallel primitives**: the type ramp is page-local literals, and the empty-state
explanation is a plain `.empty-why`-shaped paragraph, not a claimed shared class. Every
page-local class is `ws-`/`bk-`/`seam-`/`att-`/`rc-` prefixed so PR-0 can land without collision.

**Type.** `--font-ui` (Inter) for all words. `--font-mono` + `tabular-nums` **only on figures** —
and the ZH event dates deliberately drop `.fig`, because "8月27日" contains *words* and mono
numerals are for figures, never words. Page ramp: 30 / 21 / 17 / 15 / 13 / 12.5 / 11 / 10.

**Palette decision.** One accent — `--link` (`#7aa7e0` dark / `#285fff` light) — carries every
interactive affordance *and* the seam's cluster fill. Direction inks are reserved to figures;
`--warn` is reserved to attention severity; violet is reserved to locks. Four reserved meanings,
no fifth hue introduced.

---

## 3. Responsive strategy for the dense table at 390px

Verified at 390×844: **all rows present, all visible, `scrollWidth - clientWidth = 0`, zero
console errors** — 55/55 watchlist, 12/12 holdings, 8/8 anonymous.

Not `overflow-x` on the table. Below 720px each `<tr>` becomes a **CSS grid of named areas** —
semantic `<table>` markup is preserved, only `display` changes — and the header row is visually
hidden (kept for assistive tech). Two deliberate demotions, chosen so the row still answers the
job it exists for:

**Holdings (3 lines):**
```
"sym  val  exp"     SYMBOL + company            value + weight    ⌄
"sig  att  exp"     stage mark + word           attention flag
"meta meta exp"     next event
```
Demoted into the row drawer: **Day**, **Since entry**, **Risk share**.

**Watchlist (3 lines) — a different template, on purpose:**
```
"sym  val  exp"     SYMBOL + company            last price        ⌄
"sig  att  exp"     stage mark + word           risk flag
"meta chg  exp"     next event                  Δ since last visit
```
Demoted: **Sector/theme**. **Δ-since-visit is deliberately NOT demoted** — the list header
promises "4 changed since your last visit", so dropping the column that shows *which four*
would break the page's own contract at exactly the width where scanning is hardest. This is why
the two tables have different mobile templates rather than one shared reduction.

**Δ column, both widths:** unchanged rows render **blank**, not `—`. Only the four changed names
carry ink, and the header count disambiguates blank-as-"nothing happened" from missing data.

---

## 4. Honest-data handling (what is deliberately absent)

- **Day column** — the quotes Worker is dormant, so every Day cell is `—` with a Tier-2 cue
  ("Live day change is not wired up yet… everything else on this row is from last night's
  close"). Never a stale or synthesised number.
- **Anonymous Since-entry** — a pasted list has no cost basis, so it is `—` with a cue, not
  `0.0%`. (An earlier draft printed `0.0%` in green across all eight rows; that was a fabricated
  figure and was removed.)
- **Anonymous Value column** — collapses to weight only. No money is invented from a name list.
- **Mode-switch counts** — driven by state. An anonymous visitor has no saved lists, so the
  counts are **absent**, never borrowed from the signed-in mock.
- **Anonymous Signal column** — `.mx-tier-gate` lock shells, not blur. Board-tier stage reads
  are simply not delivered, so nothing to blur; the cell says what unlocks them.
- **Risk-share bars** — one shared scale (full bar = 30% of book risk), printed once in the
  Risk Center, with the number beside every bar as the truth.
- **Market books** — zero-position books render disabled with `—`, and the strip carries the
  never-mix-currencies law as its trailing subline in the holdings toolbar (§7d).

---

## 5. Doctrine tensions hit

1. **The brief's theme mechanism is inverted relative to the codebase — I followed the
   codebase.** The spawn brief says "dark is keyed on `:root[data-theme="dark"]`". It is not.
   `templates/theme.css:252-260` documents the opposite at length: dark is the **bare `:root`
   plane** and light overrides via `html[data-theme="light"]`, because the pre-paint head script
   sets no attribute at all for a first-time visitor, so a `[data-theme="dark"]` rule matches
   nothing on the live site — while still measuring green in any harness that sets the attribute
   explicitly. The mockup keys dark on bare `:root`. **The W2 builder must do the same**, and the
   brief's line should be corrected before it is copied into another spawn prompt. Restated as a
   binding rule, with the selectors, in §7a.

2. **Market books sat after the thing they filter (packet §5 order) — RESOLVED, ruled into the
   toolbar.** The ruled IA listed MARKET BOOKS last in Portfolio mode, but a filter placed below
   its table is a usability defect. The first pass did not redesign the ruled structure; it left
   the chips in the ruled position and raised the IA amendment rather than taking it as a builder
   decision. **The commissioning session ruled the amendment in:** the strip is now the second
   line of the holdings toolbar, the standalone bottom section is gone, and Watchlists mode stays
   books-free. The disclosure line ("Showing **all 12** · all books") stays exactly where it was
   and keeps its packet §11 job — curing the silently-shortening persisted book filter. Full
   semantics in §7d.

3. **Stance vocabulary vs. the no-imperatives rule — RESOLVED, ruled as standing.** The doctrine's
   ratified stance set includes "Act" and "Protect gains", which read close to trade instructions
   on a page showing someone's actual money. I used only the safely descriptive subset —
   **Watch · Get ready · No action** — plus a plain "Nothing here needs a decision today." for the
   book read (Law 1 is satisfied even when the honest answer is *nothing*). The commissioning
   session ratified this as the rule for portfolio surfaces, not a one-page preference: §7b.

4. **Stage names as plain words.** Early sign / Confirming / Confirmed / Losing steam / Running
   hot / Broke down are PR-0's user-facing stage lexicon, used here as plain English with a
   two-character ZH twin (初现 / 确认中 / 已确认 / 转弱 / 过热 / 已失效). If PR-0 lands a
   different lexicon, the builder adopts PR-0's — these are not competing names.

5. **The Concentration tab was duplicating the seam's claim.** First draft had both saying
   "seven tech names, 75% of money, 85% of risk". One dominant idea per section, no duplicate
   content: the seam keeps the **cluster** claim, the tab now carries the **single-name** claim
   ("One name, NVDA, carries a quarter of this book's risk on a sixth of its money").

## 6. ZH copy notes

Written as Chinese product copy, not translated English. Notable choices:
**组合透视** for "Portfolio Intelligence" (透视 = see-through/x-ray, which is what the page does)
over the literal 投资组合情报; **持仓** / **自选股** for the two modes — 自选股 is *the* term
every Chinese brokerage uses for a watchlist; "12 只持仓，实际只相当于大约 3 个方向。" leads with
the count and uses 方向 (directions/bets), the natural Chinese framing, rather than calquing
"move like". Placeholders use a `data-ph-en`/`data-ph-zh` pair set at paint and on language
change — an attribute cannot hold the dual-emit spans, which is the same reason translated copy
never goes in `title=`. **Zero `title=` attributes on the page** (verified across all 5 states ×
2 languages), and zero banned glance-tier vocabulary.

Two later additions, same rule — Chinese product copy, not translated English:

- The book-strip label is **分市场** ("by market"), not a calque of "books". EN keeps the
  product's own noun (*Books* — the page says "this book" throughout); ZH takes the label every
  Chinese brokerage would use for the same control. The two are not literal twins on purpose.
- The entry-price footnote ends **不会进入我们的信号计算** ("does not enter our signal
  computation") rather than a literal rendering of "never feeds our signals" — 进入…计算 is how
  a Chinese product says a value is excluded from a model.

---

## 7. Builder inheritance — rulings the W2 build must carry

Four decisions that are settled, not open. None of them changes a pixel in these crops; they are
here so the next session inherits them instead of re-deriving them.

### (a) Theme mechanism — dark is the bare plane

`:root` **is** the dark theme. Light is the override:

```css
:root                     { /* dark — a first-time visitor has NO data-theme at all */ }
html[data-theme="light"]  { /* light — wins on specificity 0,1,1 vs 0,1,0        */ }
```

**`html[data-theme="dark"]` selectors ship DEAD on this codebase.** The pre-paint head script
sets no attribute for a first-time visitor, so such a rule matches nothing on the live site —
while still measuring green in any harness that sets the attribute explicitly, which is exactly
why the defect survives review. `templates/theme.css:252-260` documents this at length. Key dark
on bare `:root`; see §5.1.

### (b) Stance vocabulary — portfolio surfaces are descriptive only

Portfolio surfaces use **Watch · Get ready · No action**, plus a plain "Nothing here needs a
decision today." when the honest answer is *nothing*.

**"Act" and "Protect gains" are barred from holdings surfaces.** Both sit in the doctrine's
ratified stance set (Law 1) and both stay legal on other surfaces — but on a page showing
someone's actual positions they read as trade instructions rather than descriptions of state.
Doctrine Law 1 is fully satisfied by the descriptive subset: every row still answers "so what do
I do", including when the answer is "nothing". See §5.3.

### (c) The 390px holdings column set

Below 720px each `<tr>` becomes a CSS grid of named areas — semantic `<table>` markup preserved,
only `display` changes (§3). The split is not a build-time judgement call; it is this list.

**Rendered inline at 390** — three lines, `"sym val exp" / "sig att exp" / "meta meta exp"`:

| Area | Cell | Carries |
|---|---|---|
| `sym` | `.c-sym` | SYMBOL + company name |
| `val` | `.c-val` | position value + weight % |
| `sig` | `.c-sig` | stage mark + plain stage word |
| `att` | `.c-att` | attention flag |
| `meta` | `.c-evt` | next event |
| `exp` | `.c-exp` | row-drawer toggle (spans all three lines) |

**Demoted to the row drawer at 390** — `display:none` in the row, reachable only by opening it:

| Cell | Column | Why demoting it is safe |
|---|---|---|
| `.c-day` | Day | every cell is `—` while the quotes Worker is dormant (§4) |
| `.c-since` | Since entry | a check-in figure, not a scan figure |
| `.c-rc` | Risk share | the Risk Center one screen down is entirely about this |

The watchlist uses a **different** mobile template on purpose (`"meta chg exp"`), because
Δ-since-visit has to survive the reduction — the list header promises "4 changed since your last
visit". Reasoning in §3.

### (d) Book-chip semantics

Pinned by the commissioning session, verbatim:

> The book chips filter the HOLDINGS TABLE VIEW only; BOOK READ, the attention stack, and the
> Risk Center always describe the WHOLE portfolio; when a book is active the disclosure line
> reads "Showing 11 of 12 — United States book"; the sentence "Each book totals in its own
> currency. We never add two currencies into one number." survives as the strip's
> subline/tooltip.

As built: the strip is the **second line of the holdings toolbar** — one `.tbl-bar` control block,
`.tbl-top` above and `.tbl-books` below, with a single hairline under both, so a filter never
reads as its own section. The label's hover carries the views-not-portfolios rule; the currency
law is the strip's trailing subline, pushed right by `margin-left:auto` in the same grammar
`.tbl-foot` already uses, and dropping to its own line below 1080px.

`.tbl-scope` is the disclosure line and it is load-bearing, not decoration: it is what stops a
persisted book filter from silently shortening the list (packet §11). At 390 the chips scroll
**inside `.books-strip`** — the same `overflow-x:auto` + hidden-scrollbar technique `.rc-tabs`
already uses on this page — so the page itself never scrolls sideways (verified 0px).

**Watchlists mode has no books**, by rule. `.tbl-bar` scopes the border removal, so the
watchlist's own `.tbl-top` is untouched — verified bit-identical across all five watchlist crops.
