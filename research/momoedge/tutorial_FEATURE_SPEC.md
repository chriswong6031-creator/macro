# MomoEdge Tutorial (learning.html) — Canonical Feature Spec

Faithful reconstruction of MomoEdge's interactive beginner course, the "LEARN" surface reached from the top-nav "Learn" link and gated **before terminal access** (required-course completion is checked by the access gate; see competitive study §Access Gate). Source evidence: 4 raw screenshot-analysis files (`tutorial_1..4.md`, ~40 screenshots, captured 2026-06-25) + competitive study (course covers "Oracle Sphere, Signal Stream, Flow Feed, GEX, risk management, and a Momo tutor"; terminal has "required-course gating and course-related progress checks").

> Evidence caveat: all readings are OCR from downscaled screenshots. Verbatim copy is high-confidence where quoted; layout pixel geometry, exact colors, and animation timing are inferred. Two counter schemes appear in captures ("X/6 COMPLETE" vs an older "X/5 COMPLETE" / "0/3 COMPLETE") — the 6-module scheme is canonical; the 5-count and 3-count are earlier build states / a transient display bug. Treat 6 modules as ground truth.

---

## 1. Surface Overview & Layout

**Product context.** The tutorial (`learning.html`, aka the "LEARN" section) is a full-screen, self-contained guided course that a new user must complete before entering the live Oracle Terminal. On finishing the last module the user hits a **ToS acceptance gate**, then lands in `terminal.html`. Each module is a 1:1 teaching mirror of a real terminal tab/surface, using **sample (non-live) data**.

**Persistent chrome (present on every step).**
- **Top nav bar:** MomoEdge logo (top-left) · nav links `Blog · Changelog · Feedback · Learn` · user avatar with initials (e.g. "KL"/"RL", top-right) · progress indicator `N / 6 COMPLETE` with a horizontal green progress bar · `Skip → Terminal` link (far top-right).
- **Left sidebar** (`MODULES · N OF 6 DONE` header): vertical numbered list of the 6 modules, each row = number + NAME + one-line subtitle + status icon (✓ complete / ▶ active / 🔒 locked). Rows are clickable to jump (completed/active only). Active row highlighted (teal/lighter background).
- **Main content pane** (center-right): module breadcrumb (`MODULE 0N — NAME`), lesson title, lesson body/subtitle paragraph, then the module's interactive visualization (Sphere / flow table / signal card / GEX chart / heatmap / position-sizing widget). A persistent disclaimer line sits at the bottom of the content: *"Sample data for learning — not live signals. Built to match the current terminal layout (FLOW · HEATMAP · GEX tabs)."*
- **Bottom strip = MOMO assistant** (the "Momo"/"MOMO" AI tutor): robot icon + a label (`MOMO · STEP X OF Y` during a lesson, or `MOMO · FREE EXPLORE` after completion) + instruction/message text + optional inline action link (e.g. "click the Sphere") + a free-text chat input (`Ask Momo anything — what's a sweep? why does confidence drop? ...`) with an `Ask` button + `Back` / `Next` (or `Finish`) navigation buttons.

**Layout regions (desktop):** 3-zone — left sidebar (~fixed narrow), center content (flex-fill), bottom MOMO strip (full-width dock). Some modules add a **right-side panel** inside the content zone (GEX `MARKET STATE`; SIGNALS `CONFIDENCE` gauge + `RISK:REWARD`). Dark navy/near-black theme throughout; teal/green is the primary accent; green=bullish, red=bearish, amber=spot/attention.

**Mobile evidence:** none. All captures are wide desktop. A couple of frames render "smaller/zoomed-out" but that is viewport-zoom, not a responsive breakpoint. Mobile layout is a **gap** (§7).

---

## 2. Complete Control Inventory

### 2.1 Global / persistent controls
| Control | Type | Options / states | Behavior |
|---|---|---|---|
| Sidebar module rows | Clickable list (6) | ORACLE, FLOW, SIGNALS, GEX, HEATMAP, RISK — each ✓ / ▶ / 🔒 | Jump to a completed or active module; locked modules non-interactive until unlocked sequentially. |
| `Skip → Terminal` | Link (top-right) | — | Bypasses the whole tutorial and jumps to terminal (still subject to ToS gate downstream, inferred). |
| Progress indicator | Read-only + bar | `N / 6 COMPLETE` | Increments by 1 when a module's `Finish` is hit. |
| `Back` | Button | active on all but first step | Go to previous step within a module. |
| `Next` | Button (primary, teal) | active except final step | Advance to next step. On the final step of a module it is **replaced by `Finish`**. |
| `Finish` | Button (primary, teal) | appears only on last step | Completes the module → triggers completion modal + increments progress. |
| MOMO chat input | Text field + `Ask` | free text | Sends a question to the Momo tutor AI; returns a free-form explanation (the "Ask anything" affordance is live in FREE EXPLORE and during steps). |
| Inline action link | Text link inside MOMO msg | context-specific (e.g. "click the Sphere", "click an NVDA row", "click the CALLS filter", "click the flip line", "drag spot left, past 5910", "click the FLOW chip", "click the NVDA tile", "drag the risk slider", "pick an answer") | Directs/gates the required interaction for the current step; often the step won't advance until performed. |

### 2.2 Completion-modal controls (per module)
- `Review` / `Replay lesson` (secondary, outlined) — re-run the just-completed module.
- `Continue → NEXTMODULE` (primary, teal) — advance to next module (label names the next module, e.g. `Continue → FLOW`, `Continue > SIGNALS`, `Continue → GEX`, `Continue → HEATMAP`, `Continue → RISK`).

### 2.3 Module-specific interactive controls
| Module | Control(s) | Options/behavior |
|---|---|---|
| **ORACLE** | The Sphere orb (clickable) | Cycles environment state on each click: **GREEN → YELLOW → RED → (back to GREEN)**. Updates orb color, label, and Direction/Posture legend live. |
| **FLOW** | Filter tabs `ALL / CALLS / PUTS` | Toggle tape by side (bullish/bearish/all). *(An earlier build showed `ALL / BULL / BEAR / TITAN` and a `SAMPLE TAPE` tab — see §7 drift note.)* |
| **FLOW** | Table rows (clickable) | Click expands an inline **detail strip** beneath the row (open/closing print, repetition, size trend). Multiple cluster rows highlighted as `C1 / C2 / C3` for a guided multi-click. |
| **SIGNALS** | Signal card `TAP TO OPEN THE SIGNAL` | Expands card → thesis + levels rail + originating Oracle print. |
| **SIGNALS** | Levels-rail markers `STOP / ENTRY / T1 / T2` (clickable) | Each click surfaces that level's explanation + price; progress chips at bottom track which are done. |
| **SIGNALS** | `RISK:REWARD` panel (focus target) | Highlighted on final step; MOMO explains R:R math. |
| **GEX** | Amber spot marker (draggable) | Drag across strikes; when spot crosses the flip line, `MARKET STATE` toggles POSITIVE ⇄ NEGATIVE GAMMA live. Sub-instruction "drag spot left, past 5910". |
| **GEX** | Flip line (dashed cyan, clickable) | Click surfaces flip-level explanation ("the most important level on the board"). |
| **GEX** | Call-wall / Put-wall bars (clickable) | Each surfaces a wall explanation; chips `CALL WALL` / `PUT WALL` gate the step. |
| **HEATMAP** | Sub-tab "chips" `PRICE / FLOW / MAP / TABLE / CAP / ALL FLOW` | Switch heatmap layer. In FLOW view, `CAP` chip is replaced by `PREMIUM`. Guided: "click the FLOW chip". |
| **HEATMAP** | Tiles (clickable) | Click a tile → expands `TICKER · FLOW TRADES (n)` list below the grid. Quiz: "click the tile hiding the biggest put-heavy bet" (answer = TSLA). |
| **RISK** | `Risk per trade` slider | Continuous, ~0%→10%+; live-recalculates MAX LOSS / SHARES. Track gradient green(safe)→red(risky); warning past 5%. Value shown in a dark pill on the handle. |
| **RISK** | Quiz buttons (2 per quiz) | Quiz 1: `SIZE UP` / `SIZE DOWN` (answer=DOWN). Quiz 2: `THE ONE 10% TRADE` / `THE FIVE 2% TRADES` (answer=THE ONE 10% TRADE). Ghost/outline buttons; branching feedback. |
| **RISK (completion)** | Email capture | Email input (pre-filled with account email) + `Subscribe`; `Display lessons` (replay) + `Enter the Terminal →`. |

No global search, sort, or view-mode controls in the tutorial (those live in the real terminal). All "controls" are pedagogical.

---

## 3. Data Model (displayed fields)

### 3.1 Course / progress
| Field | Type/units | Semantics |
|---|---|---|
| Module list | 6 fixed entries | `{number, name, subtitle, status ∈ complete/active/locked}` |
| Module subtitles | string | 1=Read the environment, 2=Read the tape, 3=Anatomy of a trade, 4=Gamma, flip & walls, 5=Price & flow layers, 6=Size & survive |
| Progress | `N / 6` int | completed module count |
| MOMO step | `STEP X OF Y` | per-module guided step counter (Y varies: ORACLE=5, FLOW=4, SIGNALS=4, GEX=4 [an older var showed 3], HEATMAP=4, RISK=4) |

### 3.2 ORACLE Sphere
| Field | Type | Semantics |
|---|---|---|
| Environment state | enum {GREEN, YELLOW, RED} | GREEN=RISK-ON ENVIRONMENT; YELLOW=MIXED / TRANSITION; RED=RISK-OFF DOWNTREND |
| Direction | string | which side to trade (per state, see §4) |
| Posture | string | aggression/behavior guidance (per state) |
| Panel title | string | `ORACLE SPHERE · MARKET ENVIRONMENT` |

### 3.3 FLOW tape row
| Field | Type/units | Example |
|---|---|---|
| Ticker | string | NVDA, TSLA, MSFT, AAPL, AMD |
| Trade type chip | enum {CALL SWEEP, CALL BLOCK, PUT SWEEP, PUT BLOCK} | color-coded green(call)/red(put) |
| Strike | `$NNN` + C/P | `$145C` = $145 call |
| Expiry | `EXP MON DD` | `EXP FEB 12` |
| Premium | `$X.XM` (USD millions) | `$2.1M` |
| Timestamp | `HH:MM:SS` (ET) | `14:02:15` |
| Score | int 0–100 | right-aligned significance/confidence (92/94/64/96/73 seen) |
| Detail strip (on expand) | text | print openness, repetition, size trend |
| Cluster total | derived $ | e.g. 3 NVDA sweeps = "$10.5M total" |

### 3.4 SIGNALS card
| Field | Type | Example |
|---|---|---|
| Ticker | string | NVDA |
| Direction | enum {LONG, SHORT} pill | LONG (green) |
| Live price | `$NNN.NN` | $142.30 |
| Change | `±X.X%` | +1.4% |
| Thesis | free text | "An infrastructure cycle accelerating, institutions call flow dominant on every reload." |
| Confidence | 0–100% gauge | 85% |
| Confidence delta | `+N THIS WEEK` | +18 THIS WEEK |
| Risk:Reward | decimal | 2.3 |
| Levels rail | 4 markers | STOP $118.00, ENTRY $131.00, (LIVE $142.30), T1, T2 (~$151 implied) |
| Originating Oracle print | print record | `ORACLE PRINT: CALL | NVDA | BULK | EXP 06.27 | $142 | ...` |

### 3.5 GEX board
| Field | Type/units | Example |
|---|---|---|
| Net-gamma-by-strike | bar series (green=+ / red=−) | per-strike bars |
| Spot | index level (draggable) | 5942 / 5960 |
| Flip | price level | $910 (=5910) |
| Call wall | price level | $000 (=6000) |
| Put wall | price level | $860 (=5860) |
| Net GEX | `$X.XB` (USD billions) | +$1.8B |
| Market state | enum {POSITIVE GAMMA, NEGATIVE GAMMA} | POSITIVE (spot>flip) |
| Regime description | string | POSITIVE: "Dealers dampen moves — ranges, pins, mean reversion." NEGATIVE (implied): dealers amplify — trending/volatile. |

### 3.6 HEATMAP
| Field | Type/units | Semantics |
|---|---|---|
| Tile | ticker cell | sized + colored by active layer |
| PRICE layer | size=market cap, color=today's % move | NVDA +2.4%, TSLA −3.2% |
| FLOW layer | size=premium spent today, color=call/put bias | NVDA `$49.2M · 12 sweeps · 3 whales` |
| Breadth badge | `Breadth · BULLISH` (rendered "Breath") | market-wide breadth |
| Flow bias badge | `Flow · CALL-HEAVY` | flow-side breadth |
| sweeps | int | sweep-order count per ticker |
| whales | int | large-institutional-order count |
| Tile expand | `TICKER · FLOW TRADES (n)` | list of `HH:MM CALL/PUT SWEEP/BLOCK $STRIKEC/P — $X.XM` |

### 3.7 RISK position sizing
| Field | Type/units | Example |
|---|---|---|
| Account | $ (sample) | $25,000 |
| Entry / Stop | $ | $131.00 / $118.00 |
| Risk per trade | % (slider) | 2.0–10%+ |
| MAX LOSS | $ = account × risk% | $500 @2%, $2,500 @10% |
| STOP DISTANCE | $ = entry − stop | $13.00 (static) |
| SHARES | int = maxloss ÷ stopdist | 38 @2%, 192 @10% |

---

## 4. Scoring / Legend / Tier Semantics (verbatim)

**ORACLE Sphere — three environments:**
- **GREEN / RISK-ON ENVIRONMENT** — Direction: "Favors swing trading long positions and call positions." Posture: "The trend is your friend. This is when swing setups get room to work." Mnemonic: *"GREEN = press the trend."*
- **YELLOW / MIXED · TRANSITION** — Direction: "Fade extremes. Capitalize on short-term moves rather than swing trades." Posture: "Cautious. Smaller size, faster exits. Do not position aggressively." Mnemonic: *"YELLOW = stay right."*
- **RED / RISK-OFF DOWNTREND** — Direction: "Favors swing trading bearish positions and put positions — the trend is down." Posture: "Trade with the downtrend, not against it. Setups are for positioning, not chasing." Mnemonic: *"RED = play defense."*
- Sphere outputs are formally named **Direction (which side)** and **Aggression (how hard)**. "It won't flip on a single red day — it reads the multi-week trend, so it only shifts on real evidence."

**FLOW score column:** 0–100 significance/confidence per print; cluster prints score high (92/94/96), isolated prints lower (64/73). Trade-type taxonomy: SWEEP (aggressive, cross-exchange) vs BLOCK (single large negotiated print); CALL(bullish)/PUT(bearish). "Repetition is the tell." Same ticker+strike+expiry+short window = a **cluster / campaign**.

**SIGNALS confidence:** "85% means my pillars — **progress, pace, retention, market** — agree. Under 60, I tell you to wait. The delta (+18 this week) matters more than the level." R:R gate: "I only surface setups where the math is on your side."

**GEX regime:** POSITIVE GAMMA (spot>flip) = "Dealers dampen moves — ranges, pins, mean reversion." NEGATIVE GAMMA (spot<flip) = dealers amplify (trending/volatile). Flip = "the most important level on the board." Put wall = "the deepest negative-gamma strike below spot… often marks 'the floor' of a flush." Call wall = "the biggest positive-gamma strike above spot. Rallies stall here… Pin city."

**HEATMAP:** PRICE = "what happened", FLOW = "what's being paid for." Tile size on FLOW = premium spent today (not market cap).

**RISK:** Formula (verbatim): **`account × risk % ÷ stop distance = size`**. Rule: "Cap risk per trade, always." "Size follows risk, never the other way around."

---

## 5. States & Interactions

- **Guided-step gating:** each module runs a fixed MOMO step sequence. Most steps require a specific interaction (click Sphere / click row / drag spot / drag slider / pick quiz answer) before `Next`/`Finish` becomes the sensible action; MOMO supplies the inline action link and updates its message per state.
- **Hover:** rail markers, tiles, GEX bars, and the flip line appear hoverable (tooltips inferred); not explicitly captured.
- **Click-through:** Sphere cycles states; rows/tiles expand inline (no modal); markers/walls surface explanations; quiz buttons branch to correct/incorrect feedback text.
- **Live recompute:** GEX market-state widget and RISK output cards recompute in real time as spot/slider move.
- **Completion state:** on `Finish`, a centered teal completion modal overlays the content — title `NAME module complete`, body "Free-explore unlocked — click anything and Momo explains it.", buttons `Review`/`Replay lesson` + `Continue → NEXT`. Sidebar row flips to ✓, next module unlocks, progress increments.
- **FREE EXPLORE mode:** after completion the MOMO label switches from `STEP X OF Y` to `FREE EXPLORE`; the just-completed visualization stays interactive and Momo answers free-form questions.
- **Quiz feedback (branching):** RISK Quiz 1 correct (SIZE DOWN): "Down. Wider stop = more risk per share, so fewer shares carry the same $500 max loss. The account risk never changes — the position size does." Wrong (SIZE UP): "Other way. Wider stop = more risk per share. To keep the same $500 max loss you must take FEWER shares. Size down." Quiz 2 correct (THE ONE 10% TRADE): "The single 10% hit — and it's not close psychologically either. Five small losses leave you calm and solvent; one oversized loss invites revenge trading. Cap risk per trade, always."
- **Course end:** RISK completion adds a `STAY IN THE LOOP` email-capture block (pre-filled email + `Subscribe`) and exits: `Display lessons` (replay) or `Enter the Terminal →` → **ToS gate** ("REQUIRED · BEFORE TERMINAL ACCESS", checkbox to enable `ACCEPT & CONTINUE`, or `DECLINE & SIGN OUT`) → live terminal.
- **Empty states / keyboard shortcuts:** none observed (§7 gap).

---

## 6. Engine Inferences (thresholds / formulas)

- **RISK sizing (fully solved):** MAX LOSS = account × risk%; STOP DISTANCE = entry − stop (static, slider-independent); SHARES = ⌊MAX LOSS ÷ STOP DISTANCE⌋. Verified across 2/3/4/5.5/6/7/10% ($500/38, $750/57, $1000/76, $1375/105, $1500/115, $1750/134, $2500/192). Equity sizing (shares, not contracts). Risk >5% flagged as danger zone.
- **SIGNALS R:R:** displayed 2.3 with entry $131 / stop $118 / T2 reward $20 → text says "risk to the stop is $13 and reward to T2 is $20 — 2.3:1" (note $20/$13≈1.54; the copy states 2.3, so T2 reward is likely ~$30 or the ratio uses a different target; **confirm from source**). Confidence <60 = "wait" threshold; confidence has 4 named pillars (progress, pace, retention, market); delta weighted over level.
- **ORACLE:** 3-state finite machine, multi-week lookback, hysteresis ("only shifts on real evidence"). Tutorial Sphere is a pure client-side cycle (GREEN→YELLOW→RED→GREEN).
- **GEX:** market-state = sign(spot − flip): spot>flip ⇒ POSITIVE GAMMA, spot<flip ⇒ NEGATIVE GAMMA. Net GEX in $B. Call/put walls = extreme positive/negative-gamma strikes.
- **FLOW score:** 0–100; clustering boosts score; open + repeated + size-increasing prints = campaign.
- **HEATMAP:** PRICE tile size = market cap, color = daily %; FLOW tile size = premium $ today, color = call/put net bias; per-ticker sweep & whale counts aggregated.

---

## 7. Gap List (unknowns — builder must decide / confirm from source)

1. **Mobile/responsive layout** — no evidence; needs design.
2. **Exact MOMO AI backend** — is "Ask" a real LLM call, canned FAQ, or hybrid? Rate limits? (competitive study: "Momo tutor" exists; behavior unconfirmed).
3. **Step-gating strictness** — can you `Next` without doing the interaction, or is it hard-blocked? Observed as strongly guided; hardness unknown.
4. **FLOW filter set drift** — canonical `ALL/CALLS/PUTS` vs older `ALL/BULL/BEAR/TITAN` + `SAMPLE TAPE` tab. Confirm current set; "TITAN" tier unexplained.
5. **HEATMAP sub-tab set** — `PRICE/FLOW/MAP/TABLE/CAP/ALL FLOW` with CAP↔PREMIUM swap by layer; MAP/TABLE/ALL FLOW behaviors never shown.
6. **Progress persistence** — server-side (Supabase course-progress checks per study) vs local. Resume behavior on return? Whether `Skip → Terminal` still counts course as complete for the access gate.
7. **SIGNALS R:R formula** — 2.3 vs $20/$13 discrepancy; exact target math unknown.
8. **Confidence pillar computation** — progress/pace/retention/market weights unknown.
9. **GEX exact chart interaction** — snap-to-strike vs continuous drag; whether walls recompute on drag; NEGATIVE-GAMMA description exact copy not captured.
10. **Completion-modal exact subtext** ("You can now free explore…") partially OCR'd.
11. **Keyboard shortcuts / a11y / empty states** — none observed.
12. **Sample-data source** — hardcoded fixtures vs seeded-from-live snapshot.
13. **Email subscribe endpoint** and whether it's skippable.
14. **ToS gate** exact full legal text (Risk Disclosure truncated).
15. **"Crash course" reference** — SIGNALS copy says "You met this card in the crash course," implying a separate shorter onboarding precedes this course. Relationship unconfirmed.

---

## 8. Reconstructed Ordered Tutorial Flow

**Chapter structure:** 6 sequential, lock-gated modules, each = lesson title + subtitle + MOMO guided steps + completion modal + FREE EXPLORE. Global order:
**ORACLE → FLOW → SIGNALS → GEX → HEATMAP → RISK →** (email capture) → ToS gate → Terminal.

### Module 1 — ORACLE · "The Sphere: what kind of market is this?" (5 steps)
Body: *"The Oracle Sphere is the first thing you see — before a single ticker. In two seconds it answers the most important question in trading: what kind of market are you in? Learn to read its three environments."*
- **Step 1** — msg: "This is the Oracle Sphere — the first thing you see in the terminal, right at the top of the Oracle tab. Right now it's GREEN: a risk-on environment. Before you've looked at a single ticker, the Sphere has already told you what kind of market you're in." → Next.
- **Step 2** — msg: "Green favors swing longs and calls — the trend is your friend. Click the Sphere to see what happens when the market shifts." → **interaction: click the Sphere** (→YELLOW).
- **Step 3** — msg: "YELLOW — mixed / transition. Fade extremes, smaller size, faster exits. Don't position aggressively. Click again." → **click Sphere** (→RED).
- **Step 4** — msg: "RED — downtrend. Now it favors puts and bearish swings — trade with the downtrend, not against it. Click once more to bring it back to GREEN." → **click Sphere** (→GREEN).
- **Step 5** — msg: "That's the whole idea: one glance sets Direction (which side) and Aggression (how hard). And it won't flip on a single red day — it reads the multi-week trend, so it only shifts on real evidence. Hit Finish when ready." → **Finish**.
- **Completion** — "ORACLE module complete" · FREE EXPLORE msg: "GREEN = press the trend · YELLOW = stay right · RED = play defense. The Sphere sets Direction and Aggression before you touch a ticker. Free explore: click the Sphere to revisit each environment. Next: FLOW — reading the live tape." · `Continue → FLOW`.

### Module 2 — FLOW · "Read the live tape" (4 steps)
Body: *"The FLOW tab is the real-time feed of institutional options activity. Learn to spot the prints that matter — and the clusters that become signals."*
- **Step 1** — "Welcome to the tape — every row is real institutional money hitting the options market. This is the FLOW tab exactly as you'll see it in the terminal." → Next.
- **Step 2** — "Click any NVDA row. Someone has been busy at the $145 strike." → **interaction: click an NVDA row** (expands detail strip).
- **Step 3** — "Open print. Second hit, same strike, 7 minutes later — size increasing. Repetition is the tell. That detail strip is on every row in the terminal. Take it in, then hit Next." → Next.
- **Step 4** — "Now cut the noise. Click CALLS to see only the bullish side of the tape." then (after filter) "Three NVDA call sweeps, same strike, fifteen minutes, $10.5M total. That is a cluster — click all three highlighted rows to read the campaign." → **interaction: click CALLS filter, then click C1/C2/C3 rows** → **Finish**.
- **Completion** — "FLOW module complete" · "Free explore unlocked — click anything and Momo explains it." · FREE EXPLORE msg: "You can read a tape now — prints, sweeps vs blocks, and the clusters that become my signals. Free explore: click any row or filter. SIGNALS is next." · `Continue → SIGNALS`.

### Module 3 — SIGNALS · "Anatomy of a live signal" (4 steps)
Subtitle: *"You met this card in the crash course. Now drive it — open the signal, read the confidence, walk every level on the rail."*
- **Step 1** — "This is a live signal: ticker, direction, live price, my thesis. Click the highlighted card to open it up." → **interaction: TAP TO OPEN THE SIGNAL**.
- **Step 2** — "There it is — thesis, levels rail, my pick. Now look right. My confidence gauge. 85% means my pillars — progress, pace, retention, market — agree. Under 60, I tell you to wait. The delta (+18 this week) matters more than the level." → Next.
- **Step 3** — "Every signal lives on one line: stop → entry → live → targets. Click all four markers — STOP, ENTRY, T1 and T2." → **interaction: click each rail marker**. Per-marker copy: STOP "your line in the sand. If price closes below $118.00 the thesis is wrong and the trade is over. The stop is set before entry, so the loss is decided in advance…"; ENTRY "where the signal fired. I triggered this one at $131.00. Everything on the card — confidence, R:R, targets — is measured from here."; (T1/T2 target copy not captured).
- **Step 4** — R:R focus: "Risk-to-reward: from entry $131, risk to the stop is $13 and reward to T2 is $20 — 2.3 : 1. I only surface setups where the math is on your side before you click anything." → **Finish**.
- **Completion** — "SIGNALS module complete" · FREE EXPLORE: "Module done — that card has no secrets left. You're in free explore: click anything and I'll explain it, or type a question below. GEX is next." · `Continue → GEX`.

### Module 4 — GEX · "Gamma: calm above, chaos below" (4 steps; an older build showed 3)
Subtitle: *"The GEX tab shows where dealer hedging pins the market and where it pours fuel. Drag spot across the flip and watch the regime change."* Chart: `SPY · NET GAMMA BY STRIKE — drag the amber spot marker`. Market State panel (POSITIVE GAMMA · Net GEX +$1.8B · Flip $910 · Call wall $000 · Put wall $860 · Spot 5942).
- **Step 1** — "This is the GEX board from the terminal's GEX tab. Green bars: strikes where dealers calm the market. Red bars: strikes where they chase it." → Next.
- **Step 2** — "The dashed cyan line is the most important level on the board. Click it." → **interaction: click the flip line**.
- **Step 3** — "Now drag the amber spot marker below the flip and watch the market-state widget on the right." (sub: "drag spot left, past 5910") → **interaction: drag spot below flip** (POSITIVE→NEGATIVE GAMMA).
- **Step 4 (walls)** — "Regime flipped — see how the widget reads it. Last thing: the market's two guardrails. Click the two outlined bars I've marked on the chart." → **interaction: click PUT WALL + CALL WALL**. PUT WALL copy: "the deepest negative-gamma strike below spot. If price reaches it, hedging pressure is at maximum; it often marks 'the floor' of a flush." CALL WALL copy: "the biggest positive-gamma strike above spot. Rallies stall here because dealer hedging leans against price. Pin city." → **Finish**.
- **Completion** — "GEX module complete" · "Free-explore unlocked…" · FREE EXPLORE: "You've finished this one — free explore is on. Click anything, or hit Replay to run the lesson again." · `Replay lesson` / `Continue → HEATMAP`.

### Module 5 — HEATMAP · "Two layers: price and flow" (4 steps)
Subtitle: *"The HEATMAP tab has two layers. PRICE tells you what moved. FLOW tells you where the money is going. Learn to flip between them."* Sub-tabs `PRICE · FLOW · MAP · TABLE · CAP/PREMIUM · ALL FLOW`.
- **Step 1** — "The heatmap, exactly as it lives in its terminal tab. Right now you're on the PRICE layer — tiles sized by market cap, colored by today's move." (tiles: NVDA +2.4%, MSFT +0.8%, AAPL +0.5%, TSLA −3.2%, AMD −1.1%; Breadth · BULLISH) → Next.
- **Step 2** — "Price is history. Click FLOW to see where the money is going instead." → **interaction: click the FLOW chip** (tiles switch to premium/sweeps/whales; Flow · CALL-HEAVY).
- **Step 3** — "Everything changed: size is now premium spent today. NVDA isn't the biggest company on this board — it's the biggest bet. Click the NVDA tile to open its flow trades." → **interaction: click NVDA tile** → expands `NVDA · FLOW TRADES (3)`: 14:16 CALL SWEEP $145C — $5.0M / 14:09 … $3.4M / 14:02 … $2.1M.
- **Step 4 (quiz)** — "Those are the cluster sweeps from your Flow lesson — same prints, different lens. Quiz: click the tile hiding the biggest put-heavy bet." (sub: "one tile is the answer") → **interaction: click TSLA tile** (correct) → `TSLA · FLOW TRADES (2)`: 14:05 PUT BLOCK $215P — $1.8M / 13:48 PUT SWEEP $210P — $1.2M → **Finish**.
- **Completion** — "HEATMAP module complete" · FREE EXPLORE: "PRICE = what happened, FLOW = what's being paid for. Free explore: flip layers, open any tile. RISK is last — and it's the one that keeps your account alive." · `Replay lesson` / `Continue → RISK`.

### Module 6 — RISK · "Size the trade, survive the streak" (4 steps)
Subtitle: *"Every signal you'll ever take starts with the same math: account × risk % ÷ stop distance. Get this reflex right and no single trade can hurt you."* Widget: `POSITION SIZING · $25,000 SAMPLE ACCOUNT · NVDA ENTRY $131.00 / STOP $118.00` → MAX LOSS / STOP DISTANCE / SHARES.
- **Step 1** — "Last lesson — the one that decides whether you're still trading in a year. Three numbers, one formula: account × risk % ÷ stop distance = size." → Next.
- **Step 2** — "Move the slider. Watch how max loss and share count chase it — and notice what happens past 5%." (sub: "drag the risk slider") → **interaction: drag slider** (live recompute) → "Same formula every time — the size follows the risk, never the other way around. Play with it as long as you like, then hit Next." → Next.
- **Step 3 (quiz 1)** — "Quiz one. Your stop moves wider — same 2% account risk. Do you size UP or DOWN?" → **buttons: SIZE UP / SIZE DOWN** (correct=DOWN; branching feedback in §5) → Next.
- **Step 4 (quiz 2)** — "Last one. Which bleeds an account faster: one 10%-risk trade, or five 2%-risk trades that all lose?" → **buttons: THE ONE 10% TRADE / THE FIVE 2% TRADES** (correct=THE ONE 10% TRADE) → **Finish**.
- **Completion** — "RISK module complete" · FREE EXPLORE: "That's the whole course — tape, signals, gamma, heat, and the math that keeps you solvent. Free explore anything, ask me anything, or head into the terminal." · `STAY IN THE LOOP` email block ("Get Momo's weekly market notes and product updates — no spam, cancelable anytime." + email + `Subscribe`) · `Display lessons` / `Enter the Terminal →` → **ToS gate** → **Live Oracle Terminal**.

**Post-course ToS gate** (`REQUIRED · BEFORE TERMINAL ACCESS`): sections ACCEPTANCE / USE OF THE SERVICE / RISK DISCLOSURE + checkbox "I have read and agree to the MomoEdge Terms of Service and Privacy Policy." + `DECLINE & SIGN OUT` / `ACCEPT & CONTINUE` (disabled until checked).
