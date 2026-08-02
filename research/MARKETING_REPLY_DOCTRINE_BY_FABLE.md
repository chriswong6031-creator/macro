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
