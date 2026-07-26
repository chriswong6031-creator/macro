# W-D DESIGN PIN — Support page + Email system

Status: **BINDING** for the Support & Email Estate builders (W1 `app/mailer.py`,
W2 `templates/support.html.j2`, W3 billing emails, W4 campaign shell).
Wave W-D of `research/SUPPORT_EMAIL_ESTATE_MASTERPLAN_BY_FABLE.md`.

Inputs loaded before designing: `docs/DESIGN_DOCTRINE.md` (content law — wins on
conflict) and the `frontend-design:frontend-design` skill (visual bar).

**Implement from this file plus the three mockups. There are no taste decisions
left for the builder.** Anything not named here should copy `templates/plans.html.j2`,
the nearest sibling public page.

| File | What it is |
|---|---|
| `support_page.html` | executable pin for `/support.html` — all states, both themes, EN/ZH |
| `email_base.html` | email shell with named slots; the only base any send may use |
| `email_receipt_sample.html` | every slot filled; the integration reference — open it raw |
| `crops/` | rendered proof (desktop+mobile, light+dark, EN+ZH, email light+dark) |

State toggles in the page mockup are URL params:
`?theme=dark|light&lang=en|zh&auth=out|in&form=idle|success|error&bar=0`.

---

## 1. Where the colour comes from

Every page colour is a **`theme.css` token**. The support page introduces no new
palette — it is a new room in an existing house. Do not hardcode any hex from the
table below into the template; use the token. The hexes are listed only so the
builder can verify a render.

| Token | Dark (`:root`) | Light (`html[data-theme="light"]`) | Used for |
|---|---|---|---|
| `--bg` | `#0f1115` | `#f7f8fa` | page canvas |
| `--panel` | `#181b21` | `#ffffff` | surface base |
| `--panel2` | `#1e222a` | `#eef1f6` | input fill, slip fill |
| `--text` | `#d7dce3` | `#1c2430` | primary text |
| `--muted` | `#8b93a1` | `#5d6b7e` | secondary text, all micro-labels |
| `--line` | `#2a2f3a` | `#eaecf0` | hairlines, field borders |
| `--info` | `#5b9bf0` | `#285fff` | **the page accent**: rail, focus, CTA, links |
| `--link` | `#7aa7e0` | `#285fff` | inline links, focus ring |
| `--ok` | `#3da564` | `#2f8a52` | success only |
| `--act` | `#e05555` | `#c43d3d` | error only |
| `--glass-brd` | `color-mix(--text 14%, transparent)` | `color-mix(#1c2430 9%, transparent)` | card borders |
| `--card-shadow` | `0 1px 0 rgba(255,255,255,.02)` | `0 1px 3px rgba(20,30,50,.07)` | card shadow |

Two page-local additions, and only two:

```css
:root{
  /* opaque elevated fill. --glass-bg is translucent and needs a backdrop-filter
     to stay legible; a content surface must never depend on one. Same recipe as
     plans.html.j2. */
  --surface: color-mix(in srgb, var(--panel) 96%, var(--text));
  /* the brand mark's gradient stops (_navlinks.html.j2 brand glyph). Used ONLY
     for the headline accent. */
  --brand-a:#3b82f6; --brand-b:#6366f1; --brand-c:#7c5cff;
}
html[data-theme="light"]{ --surface: color-mix(in srgb, var(--panel) 97%, #000); }
```

### 1.1 State colour law — do not "simplify" this

```
success  →  var(--ok)      error  →  var(--act)
```

**Never `--up` / `--down`.** Those are price-direction tokens and `theme.css`
lines 138-147 swap them under `html[data-lang="zh"]` for the Asia red-up
convention. A success panel painted with `--up` **turns red for every Chinese
reader**. `--ok`/`--act` encode health, not direction, and deliberately never swap.

---

## 2. Type

Two families, both already on every page. No new webfont: `theme.css` self-hosts
Inter because the Google Fonts CDN is blocked in mainland China, and Archivo
(used on the landing) is not vendored for `theme.css` pages.

```
--font-ui   : Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
              "Helvetica Neue", "PingFang SC", "Hiragino Sans GB",
              "Microsoft YaHei", "Noto Sans CJK SC", sans-serif
--font-mono : ui-monospace, "SF Mono", SFMono-Regular, "Cascadia Mono",
              Menlo, Consolas, "DejaVu Sans Mono", monospace
```

| Role | Spec |
|---|---|
| h1 | `700 clamp(29px,5.2vw,45px)/1.06 --font-ui`, `letter-spacing:-.025em`, `max-width:20ch` |
| h1 accent clause | `display:inline-block` + brand gradient via `background-clip:text` |
| hero sub | `clamp(14.5px,2.2vw,16.5px)`, `--muted`, `max-width:50ch`, `line-height:1.5` |
| eyebrow | `600 11px/1 --font-ui`, `letter-spacing:.18em`, uppercase, `--muted`, hairline rule each side |
| **micro-label `.mlab`** | `600 10.5px/1 --font-mono`, `letter-spacing:.14em`, uppercase, `--muted` |
| body / inputs | `14.5px/1.55 --font-ui` |
| success h2 | `700 21px/1.2 --font-ui`, `letter-spacing:-.01em` |
| slip key | `600 10px/1 --font-mono`, `letter-spacing:.14em`, uppercase, `--muted`, `width:78px` |
| slip value | `500 13.2px/1.3 --font-mono`; ticket row `600 15px`, `letter-spacing:.06em`, `--ok` |

**The mono micro-label is the page's type signature** — it is what makes a contact
form read as part of a trading desk rather than a generic support portal. Use
`.mlab` for every field label, card label and slip key. Never restyle it per block.

### 2.1 CJK rules (required)

```css
html[data-lang="zh"] .mlab,
html[data-lang="zh"] .slip .k{
  font-family:"PingFang SC","Hiragino Sans GB","Microsoft YaHei",
              "Noto Sans CJK SC",var(--font-mono);
  letter-spacing:.04em;
}
html[data-lang="zh"] .hero .eyebrow{ letter-spacing:.08em; }
```
The mono stack carries no Hanzi, so a ZH label otherwise falls through to whatever
the system picks — on some machines a **serif** (SF Mono → Songti). Wide Latin
tracking also reads as broken spacing on Hanzi; `theme.css` line 172 does the same
de-tracking for `h2`.

Put the EN word-space **inside** the `l-en` span when two dual-spans sit adjacent
(`<span class="l-en">Write once. </span><span class="l-zh">一次写清，</span>`).
Markup whitespace between them prints a stray gap after a ZH full-width comma.

---

## 3. Spacing + layout

Scale (px): **4 · 7 · 10 · 14 · 16 · 18 · 22 · 30 · 52**.

- `body{ padding-top:18px }` — the house 18px top gap, same as `plans.html.j2`.
- `.wrap{ max-width:960px; padding:20px 18px 64px }`; ≥900px → `28px 26px 88px`.
- Two columns ≥940px: `grid-template-columns: minmax(0,1fr) 300px; gap:22px`.
  Ticket panel is `grid-column:1`, aside `grid-column:2 / grid-row:1`, aside
  `position:sticky; top:74px`.
- **DOM order = aside first, form second.** Mobile then shows the self-serve
  routes before the long form with no `order` hacks, and a screen reader is
  offered the shortcut first. Desktop placement is explicit grid-column, so the
  visual order still reads form-then-aside left-to-right.
- Email + Topic share one row from **620px** up (`.frow`, `1fr 1fr`, `gap:0 16px`).
  Both auth variants live inside **one** `.fcell` so hiding either never reflows
  the grid.
- Card radii: ticket panel `16px`, aside card `14px`, inputs `10px`, slip `11px`,
  primary button `11px`.
- Mobile ≤480px: hero left-aligns, `.hero .eyebrow::before{display:none}` (its
  leading hairline otherwise reads as a stray indent), submit button goes
  full-width and `order:-1` above its note, `.tk-ref .k` hides.

---

## 4. Components

### 4.1 Input / select / textarea

```css
.inp{ width:100%; box-sizing:border-box; padding:10px 13px; border-radius:10px;
  border:1px solid var(--line); background:var(--panel2); color:var(--text);
  font:inherit; font-size:14.5px; outline:none;
  transition:border-color .18s ease, box-shadow .25s ease; }
.inp::placeholder{ color:color-mix(in srgb,var(--muted) 80%,transparent); }
.inp:hover{ border-color:color-mix(in srgb,var(--link) 45%,var(--line)); }
.inp:focus{ border-color:var(--link);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--link) 20%,transparent); }
textarea.inp{ min-height:118px; resize:vertical; line-height:1.55; }
.f.bad .inp{ border-color:var(--act); }
.f.bad .fmsg{ color:var(--act); }
```

The focus recipe is copied verbatim from `theme.css` `.tbl-filter input:focus` —
keep it identical so every focus ring on the site matches. `select.inp` uses the
inline SVG chevron in the mockup (`appearance:none`, `padding-right:38px`,
`background-position:right 12px center`, `background-size:15px`).

**Validation timing:** never mark a field red before submit. `.inp:invalid` is
explicitly neutralised; the `.f.bad` class is added by JS on a failed submit only.

### 4.2 Primary button

`gbtn`-family recipe (theme.css lines 302-328) with the `-cta` tint, **without**
the breathing animation — a form's primary action must not pulse while you type.

```css
padding:10px 20px; border-radius:11px; font:600 13.5px/1 var(--font-ui);
border:1px solid color-mix(in srgb,var(--info) 45%,var(--gbtn-brd));
background:linear-gradient(180deg, color-mix(in srgb,var(--info) 16%,var(--gbtn-bg)), var(--gbtn-bg));
box-shadow:inset 0 1px 0 var(--gbtn-sheen), 0 1px 2px rgba(3,7,18,.18);
/* hover: border-color:var(--info); translateY(-1px); 0 8px 24px -10px info@55%
   active: translateY(0) scale(.985)   focus-visible: 2px solid var(--link), offset 2px
   [aria-busy=true]: pointer-events:none; opacity:.75 */
```
Ghost variant (`Write another request`): `--gbtn-bg` fill, `--gbtn-brd` border,
`--muted` text, `12.8px`, no shadow on hover.

Reduced motion: strip the lift, the sheen sweep and the ref stamp animation.

### 4.3 The two signature elements

**a. The "what to include" line (`.hint`).** A single line under Message that
swaps with the chosen topic. This is the reason the page exists in this shape: it
turns a three-round-trip ticket into one. Content, not decoration — do not drop it,
do not turn it into a tooltip.

```css
.hint{ padding:10px 12px; border-radius:10px; font-size:12.9px; line-height:1.45;
  color:var(--muted); background:color-mix(in srgb,var(--info) 7%,transparent);
  border:1px solid color-mix(in srgb,var(--info) 22%,transparent); }
```

| topic value | EN | ZH |
|---|---|---|
| `billing` | Include the email on the receipt and the date of the charge. | 请附上收据上的邮箱，以及扣款日期。 |
| `account` | Tell us the email you signed up with, and what happens when you try to sign in. | 请说明注册时使用的邮箱，以及登录时出现了什么。 |
| `bug` | Tell us the page, what you did, and what you expected to see. | 请说明页面、你的操作，以及你预期看到的结果。 |
| `data` | Name the page and the number you are asking about. | 请说明是哪个页面、哪个数字。 |
| `feature` | Tell us what you are trying to do — not only the feature you want. | 请说明你想完成什么——而不只是想要哪个功能。 |
| `other` | One short paragraph is plenty. | 一小段话就够了。 |

**b. The ref slip.** The panel header reads `REF ········` while the form is open
— a promise that a number is coming and worth keeping. On success the header
label flips to **Received** (`--ok`) , the header ref **hides**, and the real
number stamps in at full size in the slip below. The ref is never printed twice
in one panel (doctrine Law 4).

```css
@keyframes stamp{ from{ opacity:0; transform:translateY(-2px) scale(1.06); letter-spacing:.26em; }
  to{ opacity:1; transform:none; letter-spacing:.06em; } }
```

**Ticket ref short form: `MX-` + the first 8 hex characters of the ticket uuid,
uppercased** → `MX-7F3A2B91`. Same string on the page, in the ack email subject,
and in the admin thread.

### 4.4 Form states

| State | `html[data-form]` | What renders |
|---|---|---|
| idle | `idle` | form; rail `--info`; header `New request` + `REF ········` |
| sending | `idle` | submit gets `aria-busy="true"` (dimmed, inert) |
| error | `error` | form stays **fully populated**; rail `--act`; `.err` bar above the first field |
| success | `success` | form hidden; rail `--ok`; header `Received`; seal + slip + ghost button |

Error copy is the interface voice — what happened, what to do, no apology:
> That didn't send. Check your connection and try again — or write to support@mastermind-x.com.
> 没有发送成功。请检查网络后重试，或发邮件至 support@mastermind-x.com。

Never discard typed content on error. `.err a` and `.tk-done .after a` carry
`white-space:nowrap` so the fallback address never breaks mid-address.

### 4.5 Auth states

- **Signed out** — editable `type="email"` input, `required`, `autocomplete="email"`.
- **Signed in** — the input is replaced by a static chip: `.who` with a `--ok`
  check glyph, the address in mono `13px`, and a `Verified / 已验证` pill
  (`--ok` at 13% fill, 32% border, `999px`). Label above changes
  `Your email / 你的邮箱` → `Signed in as / 当前登录`.

### 4.6 Footer

Anatomy and class names are the landing footer's (`templates/index.html`
~1507-1534): `footer.mx-footer > .f-in > .f-grid > .f-brand{.fb-row,.fm,.fn,.ft}`
+ `.f-cols > .f-col` + `.f-bot`. **Colours are re-resolved from theme tokens**
rather than the landing's hardcoded `#04070c` slab, because `/support.html` has a
real light mode where a near-black slab would read as a broken component; and the
landing's `Archivo` face is not vendored for `theme.css` pages, so `.fn`/`.fm` use
Inter 800 at the landing's `.08em` tracking. Keep the class names identical so the
two footers stay one component if a shared partial ever lands.

W2 also adds the same `Support / 支持` line to the **Resources** column of
`templates/index.html` (masterplan R6).

---

## 5. Page copy (final — both languages)

| Slot | EN | ZH |
|---|---|---|
| eyebrow | Support | 支持 |
| h1 | Write once. **Get a real answer.** | 一次写清，**真人回复。** |
| sub | Support replies by email — usually within one business day. | 我们通过邮件回复——通常在一个工作日内。 |
| aside label | Faster than writing | 比写信更快 |
| → `plans.html?billing=portal` | Manage or cancel your subscription | 管理或取消订阅 |
| → `plans.html` | Plans, prices and what's included | 方案、价格与包含内容 |
| → `methodology.html` | How a number is calculated | 某个数字是怎么算出来的 |
| next label | What happens next | 接下来会发生什么 |
| next 1 | You get an email with a **ticket number**. | 你会收到一封带**工单号**的邮件。 |
| next 2 | A person reads it — not a bot. | 由真人阅读，不是机器人。 |
| next 3 | Reply to that email to add anything. | 回复那封邮件即可补充信息。 |
| panel (open) | New request | 新建请求 |
| panel (sent) | Received | 已收到 |
| fields | Your email · Signed in as · Topic · Subject · Message | 你的邮箱 · 当前登录 · 问题类型 · 主题 · 内容 |
| subject ph. | One line — what is this about? | 一句话说明这是什么问题 |
| message ph. | Write it however you like. | 怎么写都可以。 |
| submit | Send request | 发送请求 |
| submit note | Your email is used only to answer this request. | 你的邮箱仅用于回复本次请求。 |
| success h2 | Request received. | 已收到你的请求。 |
| success p | We emailed a copy to **{email}**. Reply to that email any time to add detail. | 我们已把副本发送到 **{email}**。随时回复那封邮件补充信息。 |
| slip keys | Ticket · Topic · Sent | 工单号 · 类型 · 发送时间 |
| success note | No email in a few minutes? Check spam, or write to support@mastermind-x.com. | 几分钟内没收到邮件？请查看垃圾箱，或发邮件至 support@mastermind-x.com。 |
| again | Write another request | 再写一条请求 |

**Topic options** — `value` must match the `support_tickets.topic` check
constraint (masterplan §5). Option text cannot hold `l-en`/`l-zh` spans, so it is
painted by JS from `data-en`/`data-zh`:

| value | EN | ZH |
|---|---|---|
| `billing` | Billing & payments | 账单与付款 |
| `account` | Account & sign-in | 账户与登录 |
| `bug` | Something is broken | 有功能坏了 |
| `data` | Question about the data | 数据相关问题 |
| `feature` | Idea for something new | 功能建议 |
| `other` | Something else | 其他 |

**Shortcut line** (`.shortcut`, `→` prefix in `--info`) shows for two topics only:

- `billing`: Cancelling or changing a card? **Do it now in the billing portal** — no waiting. / 要取消订阅或更换银行卡？**现在就到账单中心处理**——无需等待。
- `account`: Can't sign in? **Ask for a new sign-in link** first — that fixes most of these. / 登录不了？先**重新获取登录链接**——大多数问题都能解决。

The honeypot (`.hp`, off-screen, `tabindex="-1"`) is abuse hardening from
masterplan R2 — **never remove it**.

### 5.1 Doctrine compliance notes

- The hero states one expectation, **once**: "usually within one business day".
  It is not repeated in the success state (Law 4). The success state spends its
  words on the next-most-useful fact instead: what to do if the email never
  arrives.
- No SLA theater, no live "desk open" dot: nothing on the page claims a status we
  cannot back.
- Every panel answers "so what do I do": the aside routes you to a faster answer,
  the hint tells you what to include, the success slip tells you how to follow up.

---

## 6. Email system

### 6.1 Colour

Designed light-first (the majority), with a `prefers-color-scheme` overlay that is
**enhancement only**. Gmail and Outlook.com ignore it and force-invert regardless,
which is why **every element sets `background-color` and `color` together** — an
inverter that flips both keeps the pair legible; one that flips only the
background is what produces black-on-black.

| Role | Light | Dark overlay | Notes |
|---|---|---|---|
| canvas | `#eef1f5` | `#0b0d11` | on `<body>` **and** the wrapper table |
| card | `#ffffff` | `#181b21` | |
| brand band | `#0f1115` | `#0f1115` | dark in **both** schemes — it is the product's identity, and an already-dark band is the safest thing to hand an inverter. The dark canvas is a shade darker so the band still reads as a band. |
| text | `#1c2430` | `#d7dce3` | |
| muted | `#5d6b7e` | `#96a0b0` | |
| hairline | `#e3e7ee` | `#2a2f3a` | |
| slip fill | `#f6f8fb` | `#1e222a` | |
| CTA fill | `#285fff` | `#285fff` | white label in both; do not tint per scheme |
| footer text | `#7b8798` | `#8b93a1` | |
| gradient bar | `#3b82f6` / `#6366f1` / `#7c5cff` | same | |

Required in `<head>`:
```html
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
```

### 6.2 Structure — the seven hard rules

1. Tables for layout. Every table gets `role="presentation" border="0"
   cellpadding="0" cellspacing="0"`. No flex, no grid, no float.
2. All CSS inline on the element. The `<style>` block is progressive enhancement
   only (dark + mobile) — Gmail strips it in several contexts, so nothing in it
   may be load-bearing.
3. **No images.** The brand is text. A blocked logo makes a billing email look
   like phishing.
4. `width="600"` + `max-width:600px`; fluid below 620px via the media query.
5. Set `background-color` **and** `color` on the same element, always.
6. Buttons are table-based (bulletproof); `border-radius` is decoration —
   Outlook drops it and renders a square button. Accepted degrade.
7. Every sentence obeys the doctrine: plain words, numbers with meaning, no
   internal vocabulary.

### 6.3 Type (email)

```
UI   : -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue',
       Arial, 'PingFang SC', 'Microsoft YaHei', sans-serif
Mono : SFMono-Regular, Consolas, 'Liberation Mono', Menlo, monospace
```
h1 `25px/1.22 700`, `-0.4px` · ZH h2 `20px/1.35 700` · lede `15px/1.6` ·
ZH body `14.5px/1.75` (CJK needs the looser leading) · fine print `13px/1.55` ·
footer `12px/1.6` · wordmark `14px 700`, `letter-spacing:2.2px`, `#ffffff` ·
eyebrow `10px 600 mono`, `letter-spacing:1.6px` · slip key `10px 600 mono`,
`letter-spacing:1.3px`, uppercase (ZH slip keys use the **UI** face at `11.5px`,
no tracking — see §2.1) · slip value `13px mono`.

Padding: band `18px 32px` · card `30px 32px 0` · mobile override `22px`.

### 6.4 The signature: gradient bar as three solid cells

The brand gradient is rendered as **three solid `<td>`s** at `height:4px`
(`#3b82f6` / `#6366f1` / `#7c5cff`). A CSS gradient silently disappears in Outlook
and a gradient image would be blocked — three solid cells paint identically
everywhere. Keep it as the first row of every email.

### 6.5 Detail slip

Two-column table, `border:1px solid {hairline}`, `border-radius:10px`, key column
`width="150"`, rows `padding:11px 16px` with a hairline `border-bottom` on all but
the last. Keys are mono uppercase; values are mono so money and dates align. This
is deliberately the same anatomy as the ticket slip on `/support.html` — the site
and the inbox must read as one product.

### 6.6 Bilingual

Dual-language v1 (masterplan R4): **one email, EN primary, ZH secondary**, split by
a rule with a centred `中文` chip so a Chinese reader finds their half in one scan.
No per-user locale guessing. Subject line = `EN · ZH`, both kept short.

### 6.7 Class discipline

| | transactional | marketing |
|---|---|---|
| examples | receipt/trial, upgrade, payment failed, cancellation, trial-ending, ticket ack, ticket reply | welcome extras, campaigns |
| unsubscribe link | **never** | **required** |
| `List-Unsubscribe` headers | no | yes, + `List-Unsubscribe-Post` |
| opt-out / suppression check | never suppressed | checked at send time |

A receipt is information the reader is owed and the send happens regardless of
marketing opt-out — an unsubscribe link on one would lie about what it does. The
unsubscribe slot in `email_base.html` is marked; **delete the whole block on
transactional sends**. Unsubscribe URL:
`https://www.mastermind-x.com/unsubscribe.html?t={token}`.

---

## 7. Per-template content skeletons

CTA targets: billing portal = `https://www.mastermind-x.com/plans.html?billing=portal`
(W3 adds the query-param handler to `plans.html.j2` that auto-launches
`GET /api/billing/portal` for a signed-in visitor). Plans = `/plans.html`.
Support = `/support.html`.

**One CTA per email, maximum.** The label is the verb of what happens
("Manage billing"), never "Click here".

---

### 7.1 Purchase / trial confirmation — *see `email_receipt_sample.html`*
- **Eyebrow** `TRIAL` (or `RECEIPT` when there is no trial)
- **Subject** Your Insider trial has started · Insider 试用已开始
- **Preheader** Free until 1 Aug 2026. Cancel before then and you are not charged.
- **Blocks** headline → lede → slip (Plan · Price · Free until · First charge ·
  That covers) → CTA `Manage billing / 管理账单` → fine print (cancel window +
  what happens if they do nothing)
- **Why-line** You received this because you started an Insider trial on {date}.

### 7.2 Plan upgrade
- **Eyebrow** `UPGRADE`
- **Subject** You're on Pro now · 你已升级到 Pro
- **Preheader** Pro is active. Your next bill is {date}.
- **Blocks** headline "You're on Pro now." → lede: what is newly available, in
  plain words (one sentence, name the actual capability, not the tier) → slip
  (Plan · Price · Changed on · Next bill) → CTA `Manage billing` → fine print:
  how proration was handled, stated plainly
- **Why-line** You received this because you changed your plan on {date}.

### 7.3 Payment failed
- **Eyebrow** `PAYMENT`
- **Subject** Your card was declined · 银行卡扣款失败
- **Preheader** Access stays on until {date}. Update the card to keep it.
- **Blocks** headline "Your card was declined." → lede: **what still works and
  until when** (this is the only thing the reader cares about) → slip (Plan ·
  Amount · Attempted on · Access until) → CTA `Update card / 更新银行卡` → fine
  print: when the next retry happens, what happens if it fails again
- **Why-line** You received this because a payment on your account did not go through.
- No blame language, no exclamation marks, no "urgent".

### 7.4 Cancellation
- **Eyebrow** `CANCELLATION`
- **Subject** Your plan is cancelled · 订阅已取消
- **Preheader** You keep full access until {date}. Nothing more will be charged.
- **Blocks** headline → lede: access end date + no further charges → slip (Plan ·
  Cancelled on · Access until · Refund, if any) → CTA `Start again / 重新订阅`
  → `/plans.html` → fine print: what happens to saved work/watchlists
- **Why-line** You received this because you cancelled your plan on {date}.
- Do not ask why they left and do not try to win them back here. One honest exit.

### 7.5 Trial ending (T-2)
- **Eyebrow** `TRIAL`
- **Subject** Your trial ends in 2 days · 试用还有 2 天结束
- **Preheader** First charge {date}, US$69.00. Cancel before then and you pay nothing.
- **Blocks** headline → lede: the exact date and amount, and that doing nothing
  means being charged → slip (Plan · First charge · Amount · That covers) → CTA
  `Manage billing` → fine print: cancel link works up to the charge time
- **Why-line** You received this because your Insider trial ends on {date}.
- Behaviour-triggered only (`trialing` AND `period_end − 2d`). No drip chain.

### 7.6 Welcome
- **Eyebrow** `WELCOME`
- **Subject** You're in · 欢迎加入
- **Preheader** Three places worth opening first.
- **Blocks** headline → lede (one sentence, what the product does for them) →
  **three one-line links**, not a slip: the Terminal, the dashboards, the
  research desk → CTA `Open the Terminal / 打开终端` → no fine print
- **Why-line** You received this because you created a Mastermind account.
- Class: marketing → **carries the unsubscribe block**.

### 7.7 Ticket acknowledgment
- **Eyebrow** `SUPPORT`
- **Subject** {MX-7F3A2B91} We got your message · 我们已收到你的消息
- **Preheader** A person reads it. Reply to this email to add anything.
- **Blocks** headline "We got your message." → lede: a person reads it, usually a
  reply within one business day → slip (Ticket · Topic · Sent) → **their own
  message quoted back** in a bordered block (muted, mono-free, preserves line
  breaks) → no CTA → fine print: reply to this email to add detail
- **Why-line** You received this because you wrote to support on {date}.
- The ticket ref goes in the subject in braces so replies thread and the operator
  lane can match them.

### 7.8 Ticket reply
- **Eyebrow** `REPLY`
- **Subject** Re: {MX-7F3A2B91} {original subject}
- **Blocks** the operator's reply as plain paragraphs → hairline → the previous
  message quoted, muted → no CTA, no slip
- **Why-line** You received this because you wrote to support about {subject}.
- Keep the chrome minimal: this one should read like a person wrote it, because a
  person did. Band + gradient bar stay; everything else goes.

### 7.9 Campaign shell (W4)
- **Eyebrow** the campaign's own 1-2 word class
- **Blocks** headline → lede → body blocks (paragraphs, at most one slip, at most
  one CTA) → 中文 mirror → footer
- Class: marketing → unsubscribe block **required**, plus `List-Unsubscribe` and
  `List-Unsubscribe-Post: List-Unsubscribe=One-Click` headers, plus the send-time
  opt-out and suppression check inside `mailer.send(...)`.
- Composer copy is still doctrine-bound: no "validated" (CI-guarded), no internal
  study names, no unexplained statistics.

---

## 8. Builder handoff

**Port from `support_page.html`:** everything between the `##PAGE-START##` /
`##PAGE-END##` markers, the CSS between `##PAGE-CSS-START##` / `##PAGE-CSS-END##`,
and the JS between `##PAGE-JS-START##` / `##PAGE-JS-END##`.

**Do not port:** the token mirror block, the placeholder `<nav>`, the `#mockbar`
control panel and its CSS/JS, the head URL-param script.

**Wire up instead:**
- `{% include "_site_nav.html.j2" %}` for the real nav, and `theme.css` +
  `theme.js` for tokens, the theme/lang toggles and the `langchange` event.
- The house `{{ t('EN','中文') }}` macro (`plans.html.j2` lines 18-20) in place of
  the literal dual-spans. **No translated text in `title=`** — CI-guarded.
- The submit stub → `POST /api/support/ticket`, keeping the exact state
  transitions in §4.4. Send `lang` = current `html[data-lang]` (the
  `support_tickets.lang` column, masterplan §5).
- Placeholders follow the site's `data-ph-en` / `data-ph-zh` attribute contract —
  they cannot use `l-en`/`l-zh` spans.

**Verify before shipping:** all four form states × both themes × both languages ×
desktop and ≤480px, against the crops in `crops/`. Open
`email_receipt_sample.html` raw in a browser and match it.
