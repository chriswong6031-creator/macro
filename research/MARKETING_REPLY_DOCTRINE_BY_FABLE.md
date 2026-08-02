# Reply doctrine — what a reply must carry to be worth posting

**Program:** Content Studio LLM-first, §10 **E4 — reply-craft intelligence**
(`research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md`).
**Ground truth:** `research/marketing_dockets/reply_corpus_2026_07_29/`
(`playbook.md` + `replies.jsonl`) — 180 top replies under 12 large finance posts,
captured 2026-07-29. Every number and every quoted line in this file traces to
that corpus; nothing here is invented.

**Consumed by three things, which is why it is a file and not a comment:**

1. `engine/marketing/reply_voice.py` — the LLM phrasing pass builds its system
   prompt from §2, §3, §6, §7 and §8.
2. `engine/marketing/reply_critics.py::reply_value` — the deterministic critic
   that kills the §8 anti-patterns before a human ever sees them.
3. The M1 operator, via `docs/reply_desk_runbook.md` §7 — the same bar the
   machine is held to is the bar the human approves against.

---

## §0. ACCEPTANCE GATES

A change to the reply lane is not done unless:

1. **The deterministic draft still ships when the model path fails.** Voice is
   an upgrade on top of `reply_drafter.compose()`, never a dependency of it. Any
   gate hit, any provider failure, any disarmed key → the template posts.
2. **No number reaches X that our engine did not compute.** The model phrases;
   it never originates a figure (CLAUDE.md §Epistemics; `fact_discipline`).
3. **The critic roster is complete at the store.** `reply_queue.enqueue` refuses
   an item whose stamp does not list every critic in `reply_critics.CRITICS`.
   Adding a critic without updating the roster pins breaks enqueue, loudly.
4. **Nothing here opens a send.** The mode dial is the only thing that sends,
   the standing cap is 0, and this doctrine changes neither.

---

## §1. The one-sentence law

> A reply is rent paid for someone else's audience. The rent is a **gift the
> thread did not already have**, delivered in **about eleven words**, aimed at
> **the room** and not at the poster.

Everything below is that sentence with evidence attached.

---

## §2. The value taxonomy — the five things a reply may carry

A draft that carries none of these is not a short reply, it is noise. The corpus
classification of the global top 60 is the evidence column.

### Data drop

A concrete, checkable number or level the parent post did not have. The
highest-density winning pattern in the market-analysis threads (data-drop = 8 of
the top 60 on its own, and 39.4% of all 180 replies contain a number).

> "Support at 900-925" — **22 likes**, under a -17% SanDisk day.

Ours comes from an own-feed fact builder, so it is already whitelisted. This is
Kelly's home and the flagship's second gear.

### Sharp read

One sentence that reframes the stat into something felt. The highest ceiling per
unit of parent size in the whole corpus — 96 likes off an account far smaller
than the megacaps.

> "KOSPI is a semiconductor ETF with miscellaneous stocks added for
> diversification." — **80 likes**, under the South Korea chip selloff.

### Dry wit

Deadpan, native idiom, no explanation, no setup. 28.3% of the top 60 is humor,
which makes it the single largest category — and the one most likely to be
mis-executed (see §8: a joke that does not parse gets 0).

> "The nerve of them to miss earnings after that whole ipo commotion" —
> **23 likes**.

House constraint: our humor law is already written (`copywriter.copy_laws`, v3
fintwit register) — deadpan understatement, aimed at forecasts and crowds, never
at people. The corpus's slang register is **evidence about the audience, not a
licence to change ours**.

### Useful reframe

Grant the frame, change what the move is *about*, or zoom out to the rule the
audience already half-believes.

> "Doesn't matter now if companies beat or not, every earnings announcement
> results in a lower stock price" — **44 likes**.

### Missing-number correction

Fix or sharpen the record with one figure. Works at every account size and is
the pattern with the cleanest fit to what we can actually produce.

> "Actually closer to -10%" — **23 likes**.
> "You missed the fact that they blew out net profit the bottom line. Q o Q up
> 133%" — **12 likes**.

**House amendment, non-negotiable:** correction without humiliation
(constitution §9.4). We fix the fact and never name the person, so the corpus's
"You missed…" opener ships here as "Worth adding: net profit was up 133% QoQ."

---

## §3. The length law

n=180 replies, URLs stripped: **min 1, median 11, mean 14.5, max 110 words.**

| bucket | count | share |
|---|---|---|
| 1-5 words | 47 | 26.1% |
| 6-15 words | 73 | 40.6% |
| 16-30 words | 37 | 20.6% |
| 31-50 words | 21 | 11.7% |
| 51+ words | 2 | 1.1% |

**Two-thirds of high-engagement replies are under 16 words.** The operating
targets:

* **Target 11 words. Ceiling 30 words / 240 characters.** The 240 is a hard law
  in the prompt; X's cap is 280 and the headroom is deliberate.
* **One thought, not three.** The 110-word winner in the corpus closes on one
  crisp line; the 0-like essay of comparable length carries three disconnected
  claims. Length is not the defect — *unclosed* length is.
* **Long form is a permitted exception, not a default.** Only 2 of the top 60
  are mini-essays. Our `micro_framework` family is the one that may run long,
  because its structure is the payload.

---

## §4. What lives and what dies under a big post

**Lives:**

* Crowd-voiced rhetoric. A question mark aimed at *everyone reading* is an
  accusation, not an ask: "Isn't FIFA supposed to be a non profit?" (30 likes).
* Being early. Reply timing inside the post's first minutes is a real, separate
  factor from content (see §9).
* One beat. Every winner in the top 60 has exactly one move in it.

**Dies:**

* **A genuine question addressed to the OP.** "What do you think of TIPS in this
  environment?" — **0 likes**. It reads as a DM: it asks the original account to
  do work for one person and gives bystanders nothing to like. Genuine
  OP-directed questions clustered in the zero-like pool.
* **Advice-column boilerplate.** Text that could be pasted under any headline.
* **Restating a fact already in the thread.** "All intercepted" — 0 likes.
* **One-word reactions.** "Oh wonderful." — 0 likes. Too generic to be dry wit,
  which needs the specific native-idiom phrasing.
* **Off-topic self-promo.** A plug wearing a news reaction as a costume.
* **Formatting tells.** One 11-like outlier padded itself with dozens of
  invisible whitespace characters before an @-mention. A manipulation artifact a
  generator must never reproduce.

**Standing brand exclusion — the moral-outrage pattern.** The two highest-liked
replies in the entire corpus (2,186 and 1,877 likes) are blunt moral verdicts on
a political-crossover post. **We never write that pattern.** It is the highest
ceiling in the data and it is forbidden here: it carries no information, it
borrows a crowd's anger, and one screenshot of it next to our profile costs more
than every like it could earn. The corpus's ceiling is not our objective
function.

---

## §5. Persona-register map

Which desk owns which pattern. The reply families
(`reply_drafter.FAMILIES`) are the mechanical form; this is the register.

| Desk | Primary patterns | Families it leans on | Never |
|---|---|---|---|
| **Kelly** (mechanism detective) | missing-number correction, data drop, receipts | `correction`, `missing_variable`, `compression`, `cross_market_lead` | hedging softeners; a number she cannot verify |
| **Sophia** (narrative architect) | sharp read via precedent and analogy | `reframe`, `second_order`, `micro_framework` | forced metaphor; exclamations; hype verbs |
| **Cici** (cross-border correspondent) | the group read — what the Asia session did and what New York inherits | `cross_market_lead`, `reframe` | untranslated Chinese; "China up/down" simplifications |
| **Meagan** (crowd translator) | process read — what the room feels against what positioning did | `human_reaction`, `acknowledgment_plus_one` | finance-bro irony; more than one exclamation |
| **flagship** (The Desk) | sharp read + data drop, terse verdict | `compression`, `missing_variable`, `conditional_prediction` | any exclamation; anything warm |
| **founder** | plain first-person read, dry about his own misses | `human_reaction`, `compression` | pitching the product; victory laps |

**Nobody gets the moral-outrage pattern (§4).** Nobody gets meme cosplay. Dry
wit is available to every desk within its own emoji and sarcasm budget, which
`expression_dial` already enforces per account and per kind.

---

## §6. Compliance rails — unchanged by this doctrine

This file changes *what we say*, never *what we are allowed to say*. All of the
following continue to bind, and all of them are enforced in code, not prose:

* **No advice, no calls.** No entry/exit/sizing/target language anywhere
  (`hot_tape_llm.call_violations`, and the house ban list in
  `copywriter.banned_language`).
* **No position claims.** We do not say what we own.
* **Zero cross-account engagement, ever.** No reply from one of our accounts to
  another; enforced by the `blocklist` critic against `desk_network`, not by
  operator discipline.
* **Numbers only from the own-feed whitelist** (`fact_discipline`).
* **No em dashes, no hashtags, one emoji at most** per the persona budget.
* **Sensitive events are a hard stop.** We do not borrow distribution from a
  tragedy (`DEFAULT_SENSITIVE_TERMS`).
* **The dignity rubric.** If it would read badly screenshotted next to our
  profile, it does not ship.
* **M0 is the standing state.** Nothing in this file sends anything.

---

## §7. Exemplars — verbatim, with their like counts as evidence

These ten are what `reply_voice.PLAYBOOK_EXEMPLARS` ships to the model. They are
transcribed exactly as posted; **their phrasing is evidence about the audience,
not a licence** — our own rails (§6) still decide what may ship.

| likes | pattern | reply |
|---|---|---|
| 96 | sharp analogy | "missing earnings expectations by $3b is like showing up to the olympics and finishing second. still incredible. wall street just doesn't care." |
| 80 | sharp read | "KOSPI is a semiconductor ETF with miscellaneous stocks added for diversification." |
| 75 | reasoned contrarian | "We have not even begun to fulfill demand this is nonsense." |
| 44 | cynical rule | "Doesn't matter now if companies beat or not, every earnings announcement results in a lower stock price" |
| 41 | contrarian with a demand for evidence | "And yet they are still making record profits and revenue with no slowdown in sight. Seriously, I have yet to see a single legitimate date as to when the growth stops for this company" |
| 25 | cross-market missing number | "All the blood and yet, VIX is still below 20." |
| 23 | correct the record | "Actually closer to -10%" |
| 23 | dry wit | "The nerve of them to miss earnings after that whole ipo commotion" |
| 22 | checkable level | "Support at 900-925" |
| 13 | human reaction + stance | "Kind of a rough quarter, but I'm still watching their long-term memory play closely." |

Two of these carry a lesson the like count alone does not:

* **"This is such an overreaction" (43 likes) is deliberately excluded.** It
  earns, and it fails our own `informational_surplus` gate: no referent, no
  number, nothing the thread did not have. A pattern that wins on X and loses
  here is still a loss here.
* The corpus's top two replies (2,186 / 1,877 likes) are excluded for the
  reason given in §4.

---

## §8. Anti-exemplars — the shapes that got zero

Quoted from `playbook.md` §(c), drawn from the same threads and the same
timing window, so they are directly comparable to §7.

1. **Advice-column boilerplate** — *"Breaking events like this remind us why
   risk management matters… Stay informed, avoid emotional decisions, and watch
   for official statements before jumping to conclusions."* (0 likes)
2. **A genuine question aimed at the OP** — *"What do you think of TIPS in this
   environment?"* (0 likes)
3. **Rambling multi-fact essay with no single payload** — three claims, no
   closing line, nothing to agree with in one glance. (0 likes)
4. **Redundant restatement** — *"All intercepted"* (0 likes)
5. **One-word reaction** — *"Oh wonderful."* (0 likes)
6. **Off-topic self-promo** — *"iran news shaking markets, check cmc for
   real-time btc moves"* (0 likes)
7. **Muddled joke** — a metaphor that does not parse. (0 likes)
8. **Ideological rant / conspiracy jargon** — alienates instead of
   crystallizing. (0 likes)

Anti-patterns 1, 2, 3 and 5 are enforced deterministically by the `reply_value`
critic. The rest are already covered: 4 by `informational_surplus`, 6 by
`persona_label` + the house ban list, 7 and 8 by `dignity` and `vocab`.

---

## §9. What this doctrine does NOT claim

The corpus is honest about its own confounds and so is this file. Carried
forward from `playbook.md` §(a) and §(c):

* **Quality is necessary, not sufficient.** One genuinely sharp, specific
  analytical reply in the corpus — *"5.17% on the 30y, highest weekly close
  since 07, and they still call inflation tame…"* — got **0 likes**. It is a
  clean example of the sharp-read pattern and would not look out of place in the
  top 60. It came from a 144-follower non-Blue account, several hours into the
  thread. **Treat a good pattern match as necessary, never as a guarantee.**
* **Timing and account standing are separate, unmeasured factors.** 83.3% of the
  top-60 repliers were Blue-verified, and Blue buys reply-ranking placement on
  X. That is a platform artifact tangled up in the content signal, and this
  corpus cannot disentangle them.
* **Follower count is not the driver.** 46.7% of top-60 repliers had under 500
  followers; only 6.7% had over 50,000. This is the encouraging half of the
  same finding.
* **Two of the twelve source posts went viral outside finance** (a FIFA story
  and a US-politics story) and supply most of the outrage, meme and long-rant
  entries in the top 60. The patterns weighted here are the ones that repeat in
  the ten **market-analysis** threads, because that is the regime a finance
  reply desk actually works.
* **n is small and the window is three days** (2026-07-27 → 2026-07-29), inside
  one live news cycle. Nothing here is a measurement and nothing here is a
  backtest. It is a documented prior with its evidence attached, and the labels
  loop (`engine/marketing/labels.py`, reply outcomes polled by
  `reply_producer.poll_reply_outcomes`) is what will eventually grade it.
* **The like count is not our objective function.** Charter §3 says the
  highest-value reply outcome is the **author replying back**, which is exactly
  what the zero-like "genuine question to the OP" optimises for. That is why the
  `author_question` family survives §4: a question that *also* carries a gift
  gives the room something and gives the author a reason to answer. A question
  with no gift is what dies.

---

## §10. Where this is enforced

| Law | Enforced by |
|---|---|
| taxonomy + register + exemplars | `engine/marketing/reply_voice.py` (system prompt) |
| ≤240 chars, one thought | `reply_voice.validate_reply_copy` |
| numbers from the packet only | `hot_tape_llm.numeric_violations` (imported) + `reply_critics.fact_discipline` |
| no advice / no calls | `copywriter.banned_language` + `hot_tape_llm.call_violations` (both imported) |
| OP-directed questions, boilerplate, one-word reactions, unclosed length | `reply_critics.reply_value` |
| everything in §6 | the eight pre-existing critics, unchanged |
| the model never scores | `reply_critics.run_critics` — the LLM hook may only de-escalate |

---

## §11. AMENDMENT — the warmth register (2026-08-01)

**Status:** amendment, not a revision. Everything above stands. This section
adds the half of the reply formula the original doctrine did not have, and where
it constrains a rule above it says so explicitly.

### §11.1 Why the doctrine needed amending

The register audit found the gap and it is structural, not stylistic: every
entry in `reply_drafter.FAMILIES` is an analytical move — missing variable,
second order, respectful disagreement, correction, compression. `human_reaction`
is the closest thing to warmth in the whole register and its template is still
gift-led analysis wearing one canned line of affect ("okay, this one is actually
interesting."). Nothing in the register could carry warmth, delight, curiosity,
or the shared-frustration move.

The operator's brief names the consequence: replies come out "completely
analytical and cold", and people follow accounts that are **both** insightful
and high emotional value. Four of the six desks are real named women whose
warmth is a hiring fact, not a copy device — so the warmth has to be real and
it has to be fabrication-free.

### §11.2 The one law that governs all of it

> **Warmth is FUSED into the clause that delivers the gift. It is never a
> second sentence bolted on in front of one.**

This is the sharpest finding in the winning-reply corpus and the only one
consistent across every account sampled. The winner shape is a three-word
concession running straight into the mechanism with no full stop. The absent
shape — "Great point! Also, here's a stat:" — does not appear anywhere near the
top of the corpus, and **its absence is the finding**.

Two supporting numbers, both **THIN** (fewer than ~15 rows per bucket, one live
news cycle, nothing here is a measurement):

| bucket | n | median eng/view |
|---|---|---|
| pure reaction warmth, zero information | 14 | 0.0032 |
| pure analytical, zero warmth markers | 10 | 0.0122 |

Read correctly this does **not** say "be cold". It says **warmth is not a
payload**: warmth that occupies its own sentence spends words and returns
nothing, while warmth that shapes the *delivery* of a real point costs zero
words and changes who replies. §1's one-sentence law is unchanged — one gift,
one grip, one doorway — and warmth is now an attribute of the gift's delivery.

**Consequence for §2.** The five-value taxonomy is unchanged. A warmth move is
not a sixth value: a reply still has to carry one of the five, and abstention on
an empty gift (Law 1) is unchanged. The single exception is `quiet_sympathy`
(§11.3), which ships without a gift, is explicitly not a growth move, and is
confined to the relationship tier.

### §11.3 The eight moves

The register is `reply_drafter.WARMTH_MOVES`, a **second rotation axis** beside
`FAMILIES` with its own LRU. Two independent LRUs is deliberate: one rotation
over the product would let a single family×warmth pairing recur while reading as
rotated.

| Move | The sentence-level mechanic | Fits | dial floor |
|---|---|---|---|
| `concede_and_hold` | grant the other side in ≤5 words, no full stop, into the mechanism | claim, hot take, prediction, correction | 1 |
| `flat_confession` | a prior wrong read stated flatly, then the corrected model | claim, prediction, hot take | 2 |
| `verdict_first` | an unhedged verdict of ≤5 words, then the gift | claim, chart, data, question to the room | 1 |
| `specific_credit` | credit one NAMED detail, never an adjective, then add | chart, thread, claim, data, personal win | 1 |
| `wry_solidarity` | a frustration aimed at a process, a crowd or an institution — never a person | wire, hot take, prediction, claim | 2 |
| `concrete_image` | the point delivered as one physical image instead of the mechanism | claim, data, wire, chart | 2 |
| `open_curiosity` | name what we cannot resolve, as a statement not a question | claim, chart, prediction, thread | 2 |
| `quiet_sympathy` | ≤8 words on a professional setback, no first name, then stop | personal setback ONLY | 2 |

`wry_solidarity` is the most tightly fenced, and the fence is the TARGET. The
corpus's highest-liked cluster in this register (15 rows, 226–4,564 likes) is
the same emotional energy pointed at *people*, and it is a standing brand
exclusion under §4 — highest ceiling in the data, zero information, incompatible
with AM-R1 personas. Aimed at a process it is the move; aimed at a person it is
the antipattern, so a draft whose object resolves to a handle, a named
individual or a second-person pronoun withdraws the move.

`open_curiosity` survives on **charter grounds with the like evidence against
it** (§9's second bullet is the ground: an author reply-back is the objective
function and likes are not). Its default form is therefore a statement, and the
question form is capped.

### §11.4 `dial_floor` is wired here, and it is what §5's "Never: anything warm" means

Every `FAMILIES` entry declares a `dial_floor` and **nothing reads it**. Here it
is load-bearing: a warmth move is admissible only when the account's reply dial
(`expression_dial`, from `voice_codex.dial_profile`) reaches the move's floor.
Employees resolve to 2, the flagship and the founder to 1. That is the mechanism
that keeps the flagship an evidence desk in someone else's thread — until now
the §5 register map's "Never: anything warm" was prose with no enforcement
behind it.

**§5 gains a warmth column.** Availability is derived from each desk's own
codex, never from a table in the module, so it moves when the spec moves:

| Desk | Warmth channel | Moves | Out of character, and why |
|---|---|---|---|
| **Kelly** | flat concessions and dry solidarity; her codex bans every hedging softener, so a concession is `fair.`, never `fair point, maybe` | concede, confession, verdict, credit, wry, image, curiosity | `quiet_sympathy` — a terse dry register makes sympathy read as stiff or sarcastic, the worst possible miss |
| **Sophia** | generosity of frame: she concedes ground elegantly and holds position | concede, confession, verdict, credit, wry, image, curiosity, sympathy | zero exclamations, absolute; her metaphor budget is 1/7d so her image frame spends none of it |
| **Cici** | generosity with context, and the glossed local term is free — `zh_gloss` is classed PRECISION, not personality, so it is not charged to her dial | concede, confession, verdict, credit, image, curiosity, sympathy | `wry_solidarity` — "bright, worldly" is her pinned register and world-weariness is off-register |
| **Meagan** | the playful line then the useful one, which is §11.2 in her own pinned codex words | concede, confession, credit, wry (warm variant), image, curiosity, sympathy | `verdict_first` — her codex requires the playful line THEN the useful one, so a bare verdict is off-shape; and no irony, ever |
| **flagship / founder** | none | none | charter §2 amendment 3; the dial floor enforces it |

**Kelly's confession is a franchise, not a weakness.** "What Would Prove This
Wrong?" is her pinned method; `flat_confession` is that method applied to
herself. Note the wiring: every confession opener must contain a literal
`reply_critics._CHANGE_MARKERS` phrase, because `position_consistency` rejects a
draft that contradicts an open thesis without one — an opener phrased "I read
this backwards" would trip the very critic the move exists to satisfy. And the
move needs an OPEN thesis in the ledger: AM-R1 applied to our own reasoning
history, we do not invent having been wrong any more than we invent having been
anywhere.

### §11.5 The bright line — feminine energy without fabrication

> **A reader may learn from a reply how she THINKS and how she REACTS. They may
> never learn anything about her LIFE.**

The test on any candidate clause: *could a journalist print this as a fact about
her?* "Sophia thinks the tariff read is mispriced" is not a life fact and is
lawful. "Sophia was at a museum this weekend" is, and is forbidden twice over
(AM-R1, and `museum` is on her own banned list).

Lawful — every item is a predicate about her **thinking**: register and rhythm;
reaction to information; first person about analysis (watching, reading, waiting
on, unable to settle); first person about having been wrong in a prior public
read; craft judgment about a chart or an argument; delight and curiosity about a
market fact; warmth toward the interlocutor's **idea**; humour aimed at
forecasts, crowds and institutions; sympathy for a professional setback.

Forbidden — every item is a predicate about her **circumstances**: positions and
P&L; meetings, sources and colleagues; product testimonials; **any place, meal,
drink, purchase, commute, travel, weather, time of day or physical state**; any
claimed routine; any claimed feeling implying a life event; any dark
`lifestyle_*` canon noun; any implied physical presence; the other person's
first name.

That asymmetry is why the register can be genuinely warm with zero fabricated
facts. The corpus's own warmth exemplars lean on real biography and are cited
here as **register anchors only**, never as templates. Lifestyle canon stays
DARK on every employee spec pending that employee's own confirmation; nothing in
this amendment flips a `lifestyle_*` marker or edits a `voice_codex` block,
which remain §5-FROZEN.

### §11.6 The anti-cold law, and what it deliberately does NOT do

`reply_critics.warmth_register` is three checks:

* **W1 — cold printout.** An employee-desk reply of ≥12 content units carrying
  no human-register marker at all rejects. **The length condition is
  load-bearing and is not a hedge:** the corpus's best analytical replies are 3
  to 5 units ("Support at 900-925", "Actually closer to -10%") and killing those
  would contradict the strongest measured effect in the data. Coldness is a
  defect of *length* — at twelve-plus units, carrying no register is a choice.
* **W2 — cold register drift.** Coldness is a property of a **feed**, not of a
  reply. Below a 45% warm share over the desk's last 20 items, another
  marker-free reply rejects. The first cold reply is free and the eleventh
  consecutive one is impossible. **Its fail direction is open and that is a
  real cost:** under 8 items of history it is inert, so a freshly armed account
  can ship its first few replies cold. The mitigation is supply side — the
  drafter offers a move from item one — and must not be "fixed" by making an
  empty history reject, which would block the lane at arming.
* **W3 — bolted-on warmth.** An opening sentence that is *about the thread*
  ("great point", "appreciate you laying this out"), spends more than 5 content
  units and carries no referent, rejects. **Scoped to thread-directed warmth on
  purpose:** phrased as "any long referent-free first sentence" it also rejects
  biancoresearch's cold Fed-vote correction (18 likes, 0.0067 eng/view), which
  is a winning reply and is this rule's calibration fixture.

**What it does not do: it does not require warmth on any single reply.** It
cannot — the evidence points the other way per reply. It requires that the
*register* is not cold and that no single reply is a long printout. Anyone
implementing "every reply must contain a feeling" has misread §11.2.

### §11.7 Fabrication is its own critic, on its own line

`reply_critics.fabrication` calls `expression_dial.am_r1_hits` **directly**,
plus a circumstance-class detector the AM-R1 lines never covered, plus the
parent author's name. It is separate from `vocab` for a reason that is a defect
fix, not a preference: `vocab` reaches AM-R1 only through
`expression_dial.violations`, which returns `[]` for any account with **no
codex** — which is the flagship, and any account whose spec fails to load. The
one gate between a real named human and a fabricated first-person claim was
silently absent for part of the roster. Every rejection quotes the offending
sentence, because a reject an operator cannot act on is a reject that gets
overridden.

### §11.8 The doorway, re-ranked

§1 already says the doorway need not be a question. The corpus says something
sharper: **the question is the weakest doorway form and the verdict is the
strongest.** Question rate across 75 landing replies is 16%, and the highest
per-view replies carry no question at all.

| # | Form | Why it earns an answer | Grade |
|---|---|---|---|
| D1 | **verdict left standing** plus a clause implying a division | people reply to disagree with confidence far more readily than to answer a question | strong |
| D2 | **named condition** — a falsifiable if/then with a level | a standing invitation with a scoreboard | strong |
| D3 | **specific credit with a named detail** | highest author-reply-back rate in the sample | strong |
| D4 | room-aimed rhetorical question, no second person | an accusation aimed at everyone reading | medium |
| D5 | the half-step — stop one clause short of the conclusion | the room finishes it in the replies | medium |
| D6 | author-directed question | highest value when it lands, lowest like rate in both corpora | weak, capped |

D1–D3 are the defaults. **D2 is X-legal in plain terms** — charter §2 amendment
4 makes falsification formats legal on X and "What Would Prove This Wrong?" is
Kelly's franchise. The #3821 operator ruling banning falsifier language is
**site surfaces only** and a builder pattern-matching on it must not scrub D2
off the reply desk.

The question caps (≤20% of an account's replies ending in a question, ≤2
author-directed per account per 7 days, never two to the same author inside 30
days) belong at **selection** time in `reply_producer`, not in a critic: a
critic sees one draft and cannot express a rolling week, and rejecting at critic
time wastes an already-composed draft. They fail **closed** on a store read
error — an unreadable history must not license an uncapped week.

### §11.9 What this amendment does NOT claim

* **The effect sizes are THIN and are not measurements.** Both buckets in §11.2
  are under 15 rows, from one live news cycle. They are a documented prior with
  its evidence attached; the labels loop is what will grade it.
* **It does not claim warm replies beat cold ones.** Per reply the corpus says
  the opposite, which is exactly why W1 is length-scoped and W2 is a rolling
  register test rather than a per-reply requirement.
* **It does not claim these eight moves are the register.** They are the eight
  the corpus supports today. A ninth is a doctrine amendment plus a test, not a
  dictionary edit.
* **It measures none of the objective function.** Charter §3's objective is the
  author replying back and a follow. Every number here is a like or a view.

---

## §12. Where the warmth register is enforced

| Law | Enforced by |
|---|---|
| the fusion law, the bright line, lawful vs forbidden | `reply_voice.SYSTEM_PROMPT` (`WHAT WARMTH IS AND IS NOT`) + the warmth-move intent in `build_user_message` |
| warmth exists before the model runs | `reply_drafter.compose(..., warmth=)` — deterministic, so a muted model still ships a warm reply |
| a move wrong for the parent shape is unavailable | `reply_drafter.classify_parent` + `fits`/`wrong_when` in `warmth_moves_for` |
| a move out of character is unavailable | `warmth_moves_for`: the account's dial, its `zh` flag, and a live sweep of every opener through `banned_language` + `expression_dial.violations` + `am_r1_hits` |
| no move hardens into a tell | `reply_drafter.rotate_warmth` — an LRU independent of the family LRU, keyed on the LAST use |
| the flagship stays an evidence desk | `dial_floor` against `expression_dial.dial_for("reply", ...)` |
| a cold reply, and a cold RUN of replies | `reply_critics.warmth_register` (W1, W2) |
| warmth bolted on in front of the analysis | `reply_critics.warmth_register` (W3) |
| no fabricated biography, on ANY account | `reply_critics.fabrication` — `am_r1_hits` called directly, plus the circumstance class and the author's name, with the sentence quoted |
| a model that fabricates or goes cold cannot ship | `reply_voice.validate_reply_copy` runs both critics before the copy is accepted; ONE repair turn, then the warm deterministic draft |
| the question caps | `reply_producer` at selection time (§11.8) |

---

## §13. AMENDMENT — the shape axis and the response mix (2026-08-02)

*Written from the XG-W4b build (§A/§B). Same standard as §11: evidence attached,
thin numbers labelled thin, and §13.9 says what this does not claim.*

### §13.1 The law this adds

> A reply's SHAPE is a third rotation axis beside family and warmth, it is
> chosen by a deficit-weighted stable draw rather than a cycle, and the
> deterministic path must be able to emit a fourteen-word committed sentence —
> because a desk whose every reply is gift + grip + doorway is a template with
> four names on it.

### §13.2 Why the doctrine needed amending again

§3 already carries the length law and its evidence: the corpus median winner is
11 words, 26.1% of the winners are 1–5 words, and 66.7% are under 16. The
composer could not obey it. `reply_drafter.compose()` had exactly one output
shape — nine of the fourteen families rendered `{gift}\n\n{drawn tail}` and the
other five `{frame}{gift}` — so every employee reply was two sentences minimum
and typically 30–45 words. `reply_value.MAX_REPLY_WORDS = 60` is a CEILING, not
a shape: it could stop a reply being long and could not make one short.

**Measured share of short-form output before this amendment: 0.00.** The
operator's brief asks for roughly 0.30 and names the reason — "the biggest
difference between human and AI replies is that humans have a SPECIFIC REACTION,
not a competent summary." §3 was a law with no mechanism behind it for eight
months.

### §13.3 The five shapes

| id | what it is | units | chars | sentences | doorway |
|---|---|---|---|---|---|
| `one_line` | one committed sentence | ≤14 | ≤100 | 1 | never |
| `fragment_exchange` | two short clauses, texting rhythm | ≤18 | ≤130 | 2 | never |
| `addition` | agreement plus the thing they missed | ≤26 | ≤180 | 2 | replaces s2 |
| `compact_chain` | the arrow form (`a -> b -> c`) | ≤22 | ≤160 | 1 | never |
| `full` | today's gift + grip + doorway | ≤60 words | ≤240 | — | yes |

Budgets are enforced at BUILD time, in content units and characters, and an
over-budget render **refuses** — it returns nothing and the caller falls to the
next legal shape, ending at `full`, which is always legal. **Nothing truncates.**
A reply clipped to fit a budget has lost its verb, and a half sentence under a
real woman's byline is worse than a mini-essay.

Three build-time gates sit beside the budget, and all three exist because a
shape the critics will kill a moment later is an abstention the reader never
sees and the operator cannot diagnose:

* **W1** — a dial-2 draft at or over 12 content units with no register marker.
  The draw is narrowed to the marker-carrying entries of the desk's own pool
  rather than the copy being rewritten.
* **the two-of-five element floor** (§13.6) — a `one_line` carrying nothing but
  the gift is a competent summary, which is the named failure mode.
* **W3**, already there since the warmth build, on any opener that stands alone.

`compact_chain`'s connector is ASCII `->` and that is load-bearing, not a style
choice: U+2192 `→` sits inside `expression_dial._EMOJI_RE`'s `←-⇿` class, so
`apply_pass` STRIPS it and `violations` reports an off-signature emoji. The chain
would ship as "higher oil stickier inflation fewer cuts" — the causality silently
deleted — and the dial would blame the desk for an emoji it never chose. Pinned
in both directions by test.

### §13.4 The fifteenth family — `dry_understatement`

Humor is 28.3% of the top-60 corpus and the single largest winning category
(§2, "Dry wit"); §5 grants a humor budget to every employee desk; the operator's
mix puts 5% on it. **No family's MOVE produced it.** A humor quota routed to
`human_reaction` is a plain reaction with a comedy label on it, which is a
distribution that reads right in a report and wrong in a timeline.

§11.9 sets the standard — "a ninth is a doctrine amendment plus a test, not a
dictionary edit" — and this is a FAMILY rather than a warmth move, so the same
ceremony applies to the table it did not land in. Per-desk lawfulness comes from
each pinned codex: kelly ("internet-native dry wit") owns it; meagan's is the
warm variant only, because her codex bans finance-bro irony and her restraint
line puts the useful sentence after the playful one; sophia's is rare, and her
craft-metaphor cap is untouched because understatement spends no metaphor; cici's
is **narrowed to the clock and the forecasters** — never a market, a people or a
policy — a narrowing derived from her own banned list (`exotic`, `mysterious
east`), which names exactly the failure mode of humor on her beat.

It carries `dial_floor: 2`, and that is **the moment `FAMILIES.dial_floor` stops
being decorative.** Every entry has declared the field since the register was
written and nothing read it; `draft_reply`'s `allowed` comprehension now does.
Humor is therefore unavailable to the flagship and the founder with no second
availability table to keep in step — which is what §5's "Never: anything warm"
means, mechanically, for families as §11.4 already made it mean for warmth moves.
The same gate withdraws `human_reaction` (also `dial_floor: 2`) from the two
evidence desks, which is a behaviour change and is correct: "okay, this one is
actually interesting." was never the flagship's register.

### §13.5 The mix, and why it is a draw and not a rotation

The requirement is contradictory on purpose and both halves are real. The
measured mix must land near the operator's 30/25/15/15/10/5, and a deterministic
30/25/15/15/10/5 **cycle is itself a tell** — four accounts sharing one fintwit
audience, stepping through shapes in lockstep, is the same bot-farm signature the
tail build closed one axis over.

The resolution: **the day is the control loop, the draw is the randomiser, and
the hash is what makes both auditable.** A response type is drawn per reply
against the desk's own weights, bent toward whatever bucket is running cold
today; the shape is drawn against a prior belonging to that type. Both rolls come
from blake2b over (account, as_of, thread, family, salt) — never `hash()`, whose
per-interpreter randomisation would make a queue record unable to explain its own
pick — and both functions return their weights, deficits, roll and legal set, so
an operator re-derives any pick exactly instead of arguing with a coin flip.

Per-persona weights, each row derived from that desk's own codex:

| account | short | analytical | agreement | disagree | question | humor |
|---|---|---|---|---|---|---|
| kelly | 0.34 | 0.24 | 0.10 | 0.18 | 0.08 | 0.06 |
| sophia | 0.22 | 0.34 | 0.18 | 0.14 | 0.06 | 0.06 |
| cici | 0.28 | 0.28 | 0.20 | 0.12 | 0.08 | 0.04 |
| meagan | 0.36 | 0.20 | 0.16 | 0.10 | 0.10 | 0.08 |
| flagship | 0.30 | 0.45 | 0.05 | 0.12 | 0.08 | 0.00 |
| founder | 0.34 | 0.34 | 0.10 | 0.12 | 0.10 | 0.00 |

The four-employee mean is **0.30 / 0.265 / 0.16 / 0.135 / 0.08 / 0.06** and no
two desks share a row — "percentages should vary by persona" satisfied without
drifting the fleet mix. **One bucket misses by two points, not one and a half:**
`question` means 0.08 against the operator's 0.10, because sophia ("sparing
questions") and kelly ("pointed questions only when answerable") both sit below
the fleet number and nothing above it compensates. Recorded rather than rounded.

**The deficit formula deviates from the XG-W4b spec's literal step 4, and the
arithmetic is why.** The spec writes `d = max(0, w - r) + 0.05` with a raw
`r = counts/seen`, and separately requires every per-account share to land within
±0.05 of target. Those cannot both hold on an 18-reply day: solving the spec's
own recursion at equilibrium for meagan's 0.36 short-reaction weight gives a
CEILING of 0.275 — a fixed point, not variance — and a raw `counts/seen` puts one
bucket at r = 1.00 after the first draw of the morning, suppressing the desk's
highest-weight register hardest. The shipped form is
`d = w + 3.0 · max(0, w − r_smooth) + 0.01` with `r_smooth` anchored on the
target by 18 pseudo-counts: the base is the target weight, so with no information
the draw IS the target; the floor keeps its stated job of making a bucket at
quota unlikely and never impossible.

Measured over 5,000 draws across the four employee desks with the real tables:

| shape | realised | nominal prior |
|---|---|---|
| `one_line` | 0.313 | — |
| `fragment_exchange` | 0.141 | — |
| `addition` | 0.213 | — |
| `compact_chain` | 0.046 | — |
| `full` | **0.287** | 0.244 |

Worst per-account response-type error: **0.047**. Longest consecutive run of one
shape: 6 over 1,250 draws, against 9 with the deficit correction disarmed — which
is what makes the control loop load-bearing rather than decorative.

The mix is JUDGED per account over a rolling 7 days at a minimum of 40 items;
below that the shares are reported with their `n` and not graded, because a share
off six items is the vacuous-N trap. The alarm is a bare line-start
`::warning title=reply_shape_mix_drift::` at a 7-day `full` share above 0.45.

### §13.6 The engagement floor, and the two gates it opened

The operator's generation rule — every substantive reply carries at least two of
{a specific reference to the post, a clear opinion, a reason, a conversational
marker, a question or opening} — is enforced by `reply_critics.reply_elements`
and is checked again at BUILD time by the shape layer, so a shape that cannot
clear it falls to one that can rather than drafting and silently abstaining.

Two structural blockers had to fall with it, and both were measured on HEAD:

1. `_referents("Yeah, but that is the problem.")` is EMPTY, so `persona_label`
   rejected every short reaction. Closed by a narrow, double-gated, fail-closed
   exemption keyed on `ctx["shape"]` — which the producer must stamp, and now
   does.
2. Quoting the parent's own figure — the canonical "the 18% inventory increase is
   the part that worries me" — was rejected by `fact_discipline`, because that
   number is not on OUR whitelist. Closed by licensing a figure that appears
   verbatim in the parent: we are quoting them, not asserting it, and verbatim
   presence is checkable by anyone reading the thread.

### §13.7 The rotation axes were resetting every night

Not a new law — a defect this amendment closes, and it is worth writing down
because it made the last two builds partly decorative in production.
`draft_reply` has accepted `recent_warmth` and `recent_tails` since the warmth
and tail builds; `reply_producer._produce_once` passed neither, and `make_item`
persisted neither. **Both LRUs saw an empty window on every producer run.** With
an empty window `rotate_warmth` always returns the first unseen entry, which
collapsed kelly's entire fourteen-family register onto two warmth moves. The
queue item now carries `warmth`, `tail`, `shape`, `shape_copy`, `response_type`
and both rolls; the producer reads them back and advances all four windows
inside the tick, because an item enqueued this tick is invisible to the queue
reader until the next one.

### §13.8 Where the shape axis is enforced

| Law | Enforced by |
|---|---|
| the shape exists before the model runs | `reply_drafter.compose(..., shape=)` — deterministic, so a muted provider still ships short replies |
| `full` is unchanged | a parity test over the whole family × warmth grid: `compose(f, g, c, warmth=w)` is byte-identical to `compose(..., shape="full")` |
| a shape wrong for the family is unavailable | `reply_shape.shapes_for` (the §A.3 matrix), plus gates for a sensitive parent, a sympathy draft, an over-long gift and an absent chain |
| the mix is a draw, not a cycle | `reply_shape.choose_response_type` / `choose_shape` — blake2b rolls, per-thread and per-day |
| the day corrects itself | `reply_producer._day_counts`, threaded into both draws and advanced in-tick |
| no head or closer hardens into a tell | `reply_drafter.pick_from_pool` — the SAME selector the doorway tails use, over disjoint per-desk lanes |
| copy out of character is unavailable | `reply_shape.heads_for` / `closers_for` — the same single guard sweep the openers and tails run |
| a short shape never ships a doorway | `REPLY_SHAPES[*]["doorway"]`, read by `draft_reply` before it reports a tail |
| humor stays off the evidence desks | `FAMILIES["dry_understatement"]["dial_floor"]`, read by `draft_reply`'s `allowed` comprehension |
| alternates still differ in reasoning move | `_compose_shaped`'s `avoid` set — the short shapes drop the family frame, so two families would otherwise collapse to one sentence |
| the mix does not drift back | `reply_shape.shape_mix` + the `reply_shape_mix_drift` annotation |

### §13.9 What this amendment does NOT claim

* **The response-mix weights are a designed prior with no outcome evidence
  behind them.** Every row is derived from a pinned codex line, which makes it
  arguable — it does not make it measured. Nothing in the labels loop has yet
  graded a short reaction against a mini-essay from the same desk on the same
  kind of parent. The 30/25/15/15/10/5 is the operator's judgment, and the
  per-persona skew is ours.
* **The relationship layer ships INERT.** `data/marketing/personas/<id>/relations.jsonl`
  is written only by the M1 approval path and every desk is at M0, so every
  handle resolves to `stranger` and the familiarity tier changes nothing today.
  It warms as approvals accumulate. Built now because building it after the store
  fills means a month of replies written at the wrong register.
* **`compact_chain` ships inert too.** No fact builder supplies `ctx["chain"]`,
  and the drafter may NOT synthesise a causal chain from a single gift — that is
  inventing a mechanism, the same class of defect as inventing a figure. Its
  0.046 measured share is a simulation with chains supplied; live it is 0.00
  until a builder emits one.
* **`compact_chain` cannot reach the spec's 0.08 floor even then**, and the
  reason is the family matrix rather than the weights: the 0.30 prior applies to
  `analytical_addition` (fleet weight 0.265) but the shape admits only 3 of that
  type's 7 families, so the reachable ceiling is ≈0.034 before the deficit
  correction lifts it. Raising it is a §A.3 matrix ruling, not a re-weighting.
* **The producer-side question caps remain UNBUILT.** §11.8 places three caps at
  selection time; the rolling ≤20%-ending-in-a-question half moved to a critic
  (which can read `ctx["corpus"]`, as W2 already proves), but **≤2
  author-directed per account per 7 days** and **never two to the same author
  inside 30 days** genuinely need the queue and nothing implements them. Named
  here as a gap rather than left to look built. This is a recorded disagreement
  with §11.8's "belongs at selection time, not in a critic", not a quiet override.
* **It measures none of the objective function.** Charter §3's objective is the
  author replying back and a follow. Every number in §13.5 is a simulation of our
  own sampler, not an outcome.
