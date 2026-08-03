/* ============================================================================
   MASTERMIND LANDING — onboarding sheet controller
   ----------------------------------------------------------------------------
   A self-contained IIFE. When any Start free / trial / Log in CTA on the landing
   is clicked, this opens a large floating sheet IN PLACE over the page:
     1 Account · 2 Preferences · 3 Plan · 4 Billing (paid only) · 5 Done
   built in the LANDING's design language (see onboard.css). The CTA <a> hrefs to
   app.mastermind-x.com/terminal?sign… remain the no-JS fallback; this script
   INTERCEPTS those clicks on THIS page and opens the local sheet instead.

   Dependencies (all lazy / optional):
     • window.MDXAuth (theme.js) — Supabase auth broker. If absent (index.html
       does not load theme.js by default), we lazy-load theme.js same-origin so
       the sheet still works. Auth degrades to an honest disabled state if
       Supabase is not configured (window.SUPABASE_CFG null on a local build).
     • window.LANG (index.html inline) — EN⇄中文 applier. We subscribe to it and
       mirror the same __en-innerHTML swap over our own subtree.
     • Stripe.js — injected on demand at the billing step only.
     • billing via (window.MM_API||'') + /api/billing/*  (mirrors account.js).

   Paired asset: templates/onboard.js MUST byte-match site/onboard.js
   (scripts/check_template_site_sync).
   ========================================================================== */
(function () {
  "use strict";
  if (window.__mmOnboard) return;            // idempotent (defer + possible double-include)
  window.__mmOnboard = true;

  // ── constants ──────────────────────────────────────────────────────────────
  var STEP_ACCOUNT = 1, STEP_PREFS = 2, STEP_PLAN = 3, STEP_BILLING = 4, STEP_DONE = 5;
  var SS_STASH = "mm.onboardLanding";        // per-tab wizard stash (this surface)
  var LS_PENDING_PREFS = "mm.pendingPrefs";  // SAME key the Terminal applies on first sign-in
  var LS_ONBOARD_RESUME = "mm.onboardResume";// Google-OAuth round-trip stash (matches terminal oauth.ts)
  var SS_ME = "mm.me";                        // /api/me cache (60s) — shared by upgrade mode + auth chrome
  var ME_TTL = 60000;                         // 60s
  var STRIPE_JS = "https://js.stripe.com/v3";
  var TERMINAL_URL = "https://app.mastermind-x.com/terminal";
  var PLANS_HTML = "https://www.mastermind-x.com/plans.html";
  var TRIAL_DAYS = 7;
  // ── tier alias (rename migration, Phases 2 + 4) ───────────────────────────
  // `essential` is the WIRE value; `insider` is what the estate shipped before the
  // rename (lib/tiers.py is the server's copy of this exact table). The direction
  // reversed in Phase 2, Phase 4 flipped the landing's `data-plan` / `?plan=` markup
  // ids to match — and the old value STILL never expires: entitlement rows written
  // before the flip say `insider` and are never back-filled, this file is served
  // `immutable` with a far-future max-age so an older copy keeps sending it, and old
  // shared links carry `?plan=insider` indefinitely. This table is permanent, and
  // nothing here may ever EMIT `insider`. Every tier that arrives from outside
  // (?plan=, data-plan, /api/me, a stash, an opener's opts) hops through normTier()
  // before anything keys on it, so every internal comparison stays canonical.
  var TIER_ALIAS = { insider: "essential" };
  function normTier(v) {
    var t = String(v == null ? "" : v).trim().toLowerCase();
    return TIER_ALIAS[t] || t;
  }
  // An /api/me payload with its tier made canonical (null stays null).
  function normMe(me) {
    if (!me || !me.tier) return me;
    if (!TIER_ALIAS[String(me.tier).trim().toLowerCase()]) return me;
    var out = {}; for (var k in me) if (me.hasOwnProperty(k)) out[k] = me[k];
    out.tier = normTier(me.tier);
    return out;
  }
  // Mirrors config/plans.yml products[].trial_days. Essential has NO trial as of
  // 2026-07-31: the funnel puts everyone who wants to try the desk into Pro's seven
  // days, and Essential is bought outright. Every trial promise in this sheet is
  // keyed off this map — nothing may offer a trial the billing spine will not
  // actually create.
  var TRIAL_BY_PLAN = { essential: 0, pro: TRIAL_DAYS };
  function trialDaysFor(plan) { return TRIAL_BY_PLAN[normTier(plan)] || 0; }
  function planHasTrial(plan) { return trialDaysFor(plan) > 0; }
  // Browser `type=email` accepts local-network shapes such as `name@domain`.
  // Account creation requires a routable domain with a real suffix instead.
  var EMAIL_RE = /^(?=.{3,254}$)(?=.{1,64}@)[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.(?:[A-Za-z]{2,63}|xn--[A-Za-z0-9-]{2,59})$/;
  function validEmail(value) { return EMAIL_RE.test(String(value || "").trim()); }

  // Raw cents — the ONLY hand-entered plan numbers (mirror config/plans.yml /
  // terminal plans.ts). Every displayed figure is DERIVED from these.
  var CENTS = {
    essential: { monthly: 9900, annual: 90000 },
    pro:     { monthly: 14900, annual: 130800 }
  };
  var FOUNDING_PRO = { key: "founding_pro", active: true, annual: 90000, cap: 2000, claimed: null };
  // CENTS is keyed by the WIRE tier, so every lookup takes the alias hop — a lane or a
  // ?plan= that says 'essential' must price as Essential, never throw on an absent key.
  function cents(key) { return CENTS[normTier(key)]; }
  function offerFor(key, period) { return normTier(key) === "pro" && period === "annual" && FOUNDING_PRO.active ? FOUNDING_PRO.key : null; }
  function annualCents(key) { return offerFor(key, "annual") ? FOUNDING_PRO.annual : cents(key).annual; }
  function perMonth(key, period) { var c = cents(key); return Math.round(period === "annual" ? annualCents(key) / 12 / 100 : c.monthly / 100); }
  function monthlyPrice(key) { return Math.round(cents(key).monthly / 100); }
  function annualBilled(key) { return Math.round(annualCents(key) / 100); }
  function annualWas(key) { return normTier(key) === "pro" && FOUNDING_PRO.active ? Math.round(CENTS.pro.annual / 12 / 100) : monthlyPrice(key); }
  function savePct(key) { var c = cents(key); return Math.round(((c.monthly - annualCents(key) / 12) / c.monthly) * 100); }
  function bestSavePct() { return Math.max(savePct("essential"), savePct("pro")); }
  function firstInvoiceTotal(key, period) { return period === "annual" ? annualBilled(key) : monthlyPrice(key); }
  function proWedge() { return perMonth("pro", "annual") - perMonth("essential", "annual"); }

  // ── bilingual: [en, zh] tuples. `zh` may contain inline HTML (matches the
  //    landing's data-zh contract, which swaps innerHTML). ──────────────────────
  var LEX = {
    // pane (left) — step-adaptive headline + subline
    paneAccountH:  ["Your desk is one step away.", "你的台席，仅一步之遥。"],
    paneAccountS:  ["Create your account to unlock every dashboard, signal and the Terminal — free.", "创建账户，解锁全部看板、信号与 Terminal——免费。"],
    panePrefsH:    ["Make it read the way you think.", "让它按你的思路来解读。"],
    panePrefsS:    ["Pick your markets and theme. Everything here is optional — change it any time.", "选择你的市场与主题。此处全部可选，随时可改。"],
    planePlanH:    ["Free to explore. Built for deeper decisions.", "免费探索。为更深的决策而生。"],
    planePlanS:    ["Start free forever, or add the analyst and the desks. Pro comes with a 7-day free trial.", "永久免费开始，或加上分析师与各台席。Pro 含 7 天免费试用。"],
    paneBillH:     ["7 days free. Cancel in one click.", "7 天免费。一键取消。"],
    paneBillS:     ["Your card starts the trial. We tell you exactly when the first charge lands — and cancelling before then costs nothing.", "绑卡即开启试用。我们会明确告知首次扣款时间——在此之前取消，分文不收。"],
    // the same pane for a plan with no trial: the promise is a clear price today,
    // not free days. Never says "trial" — see TRIAL_BY_PLAN.
    paneBillNoTrialH: ["Starts today. Cancel in one click.", "今日开通。一键取消。"],
    paneBillNoTrialS: ["We show you exactly what you're charged today before you confirm — and you can cancel from your account whenever you like.", "确认前我们会明确显示今日扣款金额——你也可随时在账户中取消。"],
    paneDoneH:     ["Welcome to the desk.", "欢迎来到你的台席。"],
    paneDoneS:     ["Everything is live. Open the dashboard and pick up where the market is right now.", "一切已就绪。打开看板，从当下的市场接手。"],

    // ── the stage (left column): nameplate, chart, tier lattice, trial meter ──
    asmTrial:  ["7-DAY TRIAL", "7天试用"],
    asmCheckout:["CHECKOUT", "结算"],
    deskYour:  ["YOUR DESK", "你的工作台"],
    deskTf:    ["DAILY", "日线"],
    deskZone:  ["ENTRY ZONE", "入场区间"],
    deskSample:["SAMPLE VIEW", "示意视图"],
    deskSignal:["BUY SIGNAL", "买入信号"],
    plateSetup:["SETTING UP", "配置中"],
    plateLive: ["LIVE", "已上线"],
    // lattice rows = the three tiers, so the picture IS the pricing truth
    rowFree:   ["FREE", "免费版"],
    rowInsider:["ESSENTIAL", "ESSENTIAL"],
    rowPro:    ["PRO", "PRO"],
    tlRead:    ["Daily market read", "每日市场研判"],
    tlSignals: ["Stock signals", "股票信号"],
    tlCharts:  ["Live charts", "实时图表"],
    tlFlow:    ["Options flow", "期权资金流"],
    tlDesks:   ["Insider & Congress", "内部人与国会"],
    tlFlash:   ["Flash AI answers", "Flash AI 问答"],
    tlReports: ["Research reports", "研究报告"],
    // the quota, not the feature: Essential already includes 10 dives a month, so a
    // bare "Pro AI dives" lock on this row would overstate what Pro adds
    tlDives:   ["150 AI dives a month", "每月 150 次 AI 深度分析"],
    tlBots:    ["Bot portfolios", "机器人组合"],
    meterHd:   ["7-DAY FREE TRIAL", "7 天免费试用"],
    meterToday:["TODAY · YOU'RE IN", "今天 · 已开通"],
    meterChg:  ["FIRST CHARGE __D__", "首次扣款 __D__"],
    meterNote: ["Cancel any time before then and you pay nothing.", "在此之前随时取消，分文不收。"],
    // compact mobile stepper
    stepOf:    ["Step __N__ of __T__", "第 __N__ 步，共 __T__ 步"],

    // stepper
    stAccount: ["Account", "账户"],
    stPrefs:   ["Preferences", "偏好"],
    stPlan:    ["Plan", "方案"],
    stBilling: ["Billing", "结算"],
    stDone:    ["Done", "完成"],

    // step 1 — account
    accountTitle: ["Create your account", "创建账户"],
    accountSub:   ["First name feeds your greetings and briefs everywhere later.", "名字之后会用于各处的问候与简报。"],
    signinTitle:  ["Welcome back", "欢迎回来"],
    signinSub:    ["Sign in to your Mastermind desk.", "登录你的 Mastermind 台席。"],
    firstName:    ["First name", "名"],
    lastName:     ["Last name", "姓"],
    email:        ["Email", "邮箱"],
    emailInvalid: ["Enter a valid email address, including the domain suffix (for example, name@example.com).",
                   "请输入完整有效的邮箱地址，包括域名后缀（例如 name@example.com）。"],
    password:     ["Password", "密码"],
    pwHintShort:  ["At least 8 characters.", "至少 8 个字符。"],
    pwHintOk:     ["Looks good.", "看起来不错。"],
    createAccount:["Create account", "创建账户"],
    signin:       ["Sign in", "登录"],
    busy:         ["Working…", "处理中…"],
    or:           ["or", "或"],
    continueGoogle:["Continue with Google", "使用 Google 继续"],
    appleSoon:    ["Apple — coming soon", "Apple — 即将支持"],
    toSignin:     ["Already have an account? Sign in", "已有账户？登录"],
    toSignup:     ["New to Mastermind? Create an account", "初次使用？创建账户"],
    terms:        ["By continuing you agree to our <a href='/terms.html' target='_blank' rel='noopener'>Terms</a> and <a href='/privacy.html' target='_blank' rel='noopener'>Privacy Policy</a>.", "继续即表示你同意我们的<a href='/terms.html' target='_blank' rel='noopener'>服务条款</a>与<a href='/privacy.html' target='_blank' rel='noopener'>隐私政策</a>。"],

    // step 2 — preferences
    prefsTitle:   ["Set up your desk", "配置你的台席"],
    prefsSub:     ["Tune the read to your markets and taste. All optional.", "按你的市场与偏好调校解读。全部可选。"],
    marketFocus:  ["Market focus", "市场重点"],
    mktUs:        ["United States", "美国"],
    mktCn:        ["China", "中国"],
    mktHk:        ["Hong Kong", "香港"],
    mktCa:        ["Canada", "加拿大"],
    mktGlobal:    ["Global", "全球"],
    theme:        ["Theme", "主题"],
    themeLight:   ["Light", "浅色"],
    themeDark:    ["Dark", "深色"],
    themeAuto:    ["Auto", "自动"],
    themeCaption: ["Auto follows your system — and switches to dark after sunset.", "自动跟随系统——并在日落后切换为深色。"],
    trade:        ["What you trade", "你交易什么"],
    tradeStocks:  ["Stocks", "股票"],
    tradeOptions: ["Options", "期权"],
    tradeCrypto:  ["Crypto", "加密货币"],
    skipForNow:   ["Skip for now", "暂时跳过"],
    continue:     ["Continue", "继续"],

    // step 3 — plan
    planTitle:    ["Choose your plan", "选择你的方案"],
    planSub:      ["Free forever, subscribe to Essential, or start a 7-day trial of Pro.", "永久免费；也可订阅 Essential，或开启 Pro 的 7 天试用。"],
    togAnnual:    ["Annual <span class=\"obm-save\">FOUNDING PRO AVAILABLE</span>", "按年 <span class=\"obm-save\">FOUNDING PRO 开放中</span>"],
    togMonthly:   ["Monthly", "按月"],
    planFree:     ["Free", "免费"],
    planInsider:  ["Essential", "Essential"],
    planPro:      ["Pro", "Pro"],
    whoFree:      ["The daily read, six signals, the Terminal — forever.", "每日研判、六条信号、Terminal——永久免费。"],
    whoInsider:   ["The working desk, with the analyst on call.", "随叫随到的分析师，配上完整的工作台席。"],
    whoPro:       ["For the ones who ask harder questions.", "为那些提出更难问题的人准备。"],
    perMoAnnual:  ["/mo billed annually", "/月 · 按年结算"],
    perMo:        ["/mo", "/月"],
    free0:        ["$0", "$0"],
    ribbon:       ["MOST POPULAR", "最受欢迎"],
    foundingRibbon:["FOUNDING PRO", "FOUNDING PRO"],
    foundingFine: ["Every Pro feature for the Essential annual price · $__T__/year.",
                   "以 Essential 年付价格解锁 Pro 全部功能 · 每年 $__T__。"],
    foundingGone: ["The last founding spot was claimed. Review the regular Pro Annual price to continue.",
                   "最后一个创始会员名额已被领取。请查看 Pro 常规年付价格后继续。"],
    // summaries
    sumGetFree:   ["What you get", "你将获得"],
    sumMissFree:  ["What you're missing", "你还缺少"],
    sumPlusInsider:["Everything in Free, plus", "免费版全部功能，另加"],
    sumPlusPro:   ["Everything in Essential, plus", "Essential 全部功能，另加"],
    getFree1:     ["The daily read + <b>every macro dashboard</b>", "每日研判 + <b>全部宏观看板</b>"],
    getFree2:     ["<b>3 signals per daily list</b> with a public track record", "<b>每个每日列表 3 条信号</b>，战绩公开可查"],
    getFree3:     ["The full Terminal — live charts, no install", "完整 Terminal——实时图表，无需安装"],
    missIns1:     ["300 Flash AI answers + 10 Pro AI dives a month", "每月 300 次 Flash AI + 10 次 Pro AI 深度分析"],
    missIns2:     ["Intraday options flow, Insider & Congress desks", "日内期权流、内部人与国会台席"],
    missPro1:     ["Mastermind + institutional research reports", "Mastermind + 机构研究报告"],
    plusIns1:     ["<b>300 Flash AI answers</b>, 10 Pro AI dives a month", "<b>每月 300 次 Flash AI</b>、10 次 Pro AI 深度分析"],
    plusIns2:     ["<b>Intraday options flow</b> — sweeps and blocks as they print", "<b>日内期权流</b>——扫单与大宗成交实时打印"],
    plusIns3:     ["Insider/Congress & 13F desks, transcripts, daily briefs", "内部人/国会与 13F 台席、电话会记录、每日简报"],
    plusPro1:     ["<b>150 Pro AI dives a month + unlimited Flash AI</b>", "<b>每月 150 次 Pro AI 深度分析 + 无限量 Flash AI</b>"],
    plusPro2:     ["Mastermind + institutional research reports", "Mastermind + 机构研究报告"],
    plusPro3:     ["Mastermind Bot Portfolios", "Mastermind 机器人组合"],
    proFine:      ["Institutional research library: JPM · Citi · Morgan Stanley · UBS · Goldman Sachs · BofA.", "机构研究库：摩根大通 · 花旗 · 摩根士丹利 · 瑞银 · 高盛 · 美银。"],
    wedge:        ["<b>+$" + proWedge() + "/mo</b> on annual gets you everything in Pro.", "按年再加 <b>$" + proWedge() + "/月</b> 即可获得 Pro 全部功能。"],
    switchPro:    ["Switch to Pro", "切换到 Pro"],
    mcpSoon:      ["MCP", "MCP"],
    mcpSoonTag:   ["COMING SOON", "即将推出"],
    compareAll:   ["Compare every feature →", "逐项对比 →"],
    contFree:     ["Continue with Free", "免费开始"],
    contBilling:  ["Continue to billing", "去结算"],

    // ── compare panel (opens OVER the plan step; never navigates away) ──
    cmpTitle:     ["Compare every feature", "逐项对比"],
    cmpBack:      ["Back to plans", "返回方案"],
    cmpPick:      ["Continue with __N__", "继续使用 __N__"],
    cmpFeature:   ["Feature", "功能"],
    cmpSoon:      ["SOON", "即将"],
    cmpPerAnnual: ["/mo annual", "/月 · 年付"],
    cmpPerMonthly:["/mo monthly", "/月 · 月付"],

    // step 4 — billing
    billTitle:    ["Add your card", "添加银行卡"],
    billSub:      ["Your 7-day trial starts now. Cancel any time before it ends and you pay nothing.", "7 天试用现在开始。在结束前随时取消，分文不收。"],
    billSubNoTrial:["Your plan starts as soon as you confirm. Cancel any time from your account.", "确认后方案立即生效。可随时在账户中取消。"],
    billPerMo:    ["/mo", "/月"],
    billBilledAnnually:["Billed $__T__ per year after the trial.", "试用结束后每年扣款 $__T__。"],
    billBilledMonthly: ["Billed monthly after the trial.", "试用结束后按月扣款。"],
    billBilledAnnuallyNow:["Billed $__T__ per year, starting today.", "自今日起每年扣款 $__T__。"],
    billBilledMonthlyNow: ["Billed monthly, starting today.", "自今日起按月扣款。"],
    billTrialLine:["<b>7-day free trial</b> — your first charge of $__T__ lands on __D__.", "<b>7 天免费试用</b>——首次扣款 $__T__ 将于 __D__ 进行。"],
    billChargeLine:["<b>$__T__ today</b> — your subscription starts as soon as you confirm.", "<b>今日扣款 $__T__</b>——确认后订阅立即生效。"],
    billCancelLine:["Cancel before then and you pay nothing.", "在此之前取消，分文不收。"],
    billCancelAnytime:["Cancel any time from your account.", "可随时在账户中取消。"],
    billLoading:  ["Securely loading checkout…", "正在安全加载结算…"],
    billErr:      ["Something went wrong loading checkout. Please try again.", "加载结算时出错，请重试。"],
    billRetry:    ["Try again", "重试"],
    billAlready:  ["You already have an active plan", "你已有一个生效中的方案"],
    billAlreadySub:["Your subscription is live — no need to add a card again.", "你的订阅已生效——无需再次绑卡。"],
    billAlreadyGo:["Continue", "继续"],
    billSignin:   ["Please sign in to continue to billing.", "请先登录以继续结算。"],
    billNotConfigured:["Billing isn't configured on this environment yet.", "此环境尚未配置结算。"],
    billPlansLink:["See plans & pricing", "查看方案与定价"],
    billSubmit:   ["Start 7-day trial", "开始 7 天试用"],
    billSubmitBusy:["Starting your trial…", "正在开启试用…"],
    billSubmitNow:["Subscribe now", "立即订阅"],
    billSubmitNowBusy:["Subscribing…", "正在订阅…"],
    billOrFree:   ["or continue with Free", "或改用免费版"],
    billConfirmFirst:["Confirm your email first, then add your card. We've sent a confirmation link.", "请先确认邮箱，再绑卡。确认链接已发送。"],
    billConfirmGo:["Continue", "继续"],

    // step 5 — done
    doneTitle:    ["You're in.", "你已加入。"],
    doneTitleNamed:["You're in, __N__.", "你已加入，__N__。"],
    doneConfirm:  ["Check __E__ to confirm your email and finish setting up.", "查收 __E__ 以确认邮箱并完成设置。"],
    doneTrial:    ["Your __T__ trial is live — first charge on __D__.", "你的 __T__ 试用已生效——首次扣款为 __D__。"],
    doneSubscribed:["Your __T__ plan is live.", "你的 __T__ 方案已开通。"],
    doneReady:    ["Your dashboards, signals and the Terminal are ready.", "你的看板、信号与 Terminal 已就绪。"],
    openDashboard:["Open the dashboard", "打开仪表盘"],
    openTerminal: ["Open the Terminal →", "打开 Terminal →"],

    // ── upgrade mode (post-login monetization sheet) ──
    upTitle:      ["Upgrade your desk", "升级你的台席"],
    upLoad:       ["Loading your plan…", "正在加载你的方案…"],
    upErr:        ["We couldn't load your plan. Please try again.", "无法加载你的方案，请重试。"],
    upRetry:      ["Try again", "重试"],
    // free → start a trial
    upFreeSub:    ["Subscribe to Essential, or start a 7-day free trial of Pro. Either way we tell you exactly what you're charged, and when.", "订阅 Essential，或开启 Pro 的 7 天免费试用。无论哪种，我们都会明确告知扣款金额与时间。"],
    upCurFree:    ["ON FREE", "当前免费版"],
    upNotNow:     ["Not now", "暂不升级"],
    // annual-discount subheads
    upToAnnualSub:["Step up to Pro Annual — the full desk at its lowest monthly price. Your remaining Essential time is credited toward it.", "升级到 Pro 年付——以月均最低价获得完整台席。剩余的 Essential 时长将折算抵扣。"],
    upProAnnualSub:["Move up to Pro Annual — everything in Pro, at the lowest per-month price.", "升级到 Pro 年付——Pro 全部功能，月均价格最低。"],
    // lane cards
    laneInsAnnual:["Essential Annual", "Essential 年付"],
    laneProMonthly:["Pro Monthly", "Pro 月付"],
    laneProAnnual:["Pro Annual", "Pro 年付"],
    laneInsAnnualWho:["Your desk, billed yearly — same features, lower monthly price.", "你的台席，按年结算——功能不变，月均更低。"],
    laneProMonthlyWho:["Every Pro desk and report, month to month.", "全部 Pro 台席与报告，按月付。"],
    laneProAnnualWho:["Everything in Pro at the best price we offer.", "以我们最优的价格获得 Pro 全部功能。"],
    laneBilledAnnual:["/mo billed annually", "/月 · 按年结算"],
    laneBilledMonthly:["/mo", "/月"],
    laneSave:     ["SAVE __P__%", "省 __P__%"],
    lanePopular:  ["MOST POPULAR", "最受欢迎"],
    laneProAnnualPitch:["$__A__/yr instead of $__M__ — save __P__%.", "$__A__/年，而非 $__M__——省 __P__%。"],
    // inline confirm
    upConfirmProrate:["Your unused time is credited — you pay only the prorated difference today.", "未使用时长将折算为抵扣——今天只需支付按比例计算的差额。"],
    upConfirmTrial:["Your trial continues — billing switches when it ends.", "试用继续——结算将在试用结束时切换。"],
    upConfirmGo:  ["Confirm upgrade", "确认升级"],
    upConfirmGoBusy:["Upgrading…", "正在升级…"],
    // best-plan panel
    upBestH:      ["You're on the best plan.", "你已在最优方案。"],
    upBestS:      ["Pro Annual is our top tier — every desk, report and dive is already yours.", "Pro 年付是我们的最高方案——全部台席、报告与深度分析均已包含。"],
    // success panel
    upDoneH:      ["You're upgraded.", "已升级完成。"],
    upDonePlan:   ["You're now on __N__.", "你现在使用 __N__。"],
    upDoneCharged:["Charged today: $__T__.", "今日扣款：$__T__。"],
    upDoneRenew:  ["Renews __D__.", "续订日 __D__。"],

    goBack:       ["Go back", "返回"],
    closeLbl:     ["Close", "关闭"],
    dialogLbl:    ["Onboarding", "引导"]
  };

  function lang() { try { return (window.LANG && window.LANG.cur && window.LANG.cur() === "zh") ? "zh" : (document.documentElement.getAttribute("data-lang") === "zh" ? "zh" : "en"); } catch (e) { return "en"; } }
  function tx(key) { var e = LEX[key]; if (!e) return key; return lang() === "zh" ? e[1] : e[0]; }

  // ── the feature matrix, mirroring the landing's #pricing-matrix ────────────
  // Cell values: 1 = included · 0 = not included · [en,zh] = the quota itself ·
  // "soon" = shipped-but-not-yet. tests/test_onboard_compare_matrix.py pins every
  // English label to the landing table so the two can never drift apart.
  var COMPARE = [
    { g: ["INTELLIGENCE — THE DAILY READ", "情报 — 每日研判"], rows: [
      { l: ["Daily macro dashboards", "每日宏观看板"],     v: [1, 1, 1] },
      { l: ["Stock dossiers", "个股档案"],                 v: [1, 1, 1] },
      { l: ["Theme rotation lanes", "主题轮动通道"],       v: [1, 1, 1] },
      { l: ["Special situations", "特殊机会"],             v: [1, 1, 1] },
      { l: ["Bitcoin · Commodities · FX", "比特币 · 大宗 · 外汇"], v: [1, 1, 1] },
      { l: ["Insider & Congress desks", "内部人 & 国会台席"], v: [0, 1, 1] },
      { l: ["13F institutional flows", "13F 机构资金流"],  v: [0, 1, 1] }
    ] },
    { g: ["SIGNALS", "信号"], rows: [
      { l: ["Daily buy signals", "每日买入信号"], v: [["3 / list", "每列表 3 条"], ["Full book", "完整名册"], ["Full book", "完整名册"]] },
      { l: ["Track record & autopsies", "公开战绩 & 复盘"], v: [1, 1, 1] },
      { l: ["Daily AI morning brief", "每日 AI 晨间简报"],  v: [0, 1, 1] }
    ] },
    { g: ["TERMINAL", "TERMINAL"], rows: [
      { l: ["Live charting", "实时图表"],                  v: [1, 1, 1] },
      { l: ["Advanced indicator modules", "高级指标模块"], v: [["1 / 31", "1 / 31"], ["15 / 31", "15 / 31"], ["All 31", "全部 31 个"]] },
      { l: ["Intraday options flow", "日内期权流"],        v: [0, 1, 1] },
      { l: ["Earnings call transcripts", "财报电话会记录"], v: [0, 1, 1] }
    ] },
    { g: ["MASTERMIND AI", "MASTERMIND AI"], rows: [
      { l: ["Flash AI", "Flash AI"], v: [["5 / wk", "5 次/周"], ["300 / mo", "300 次/月"], ["Unlimited", "无限量"]] },
      { l: ["Pro AI", "Pro AI"],     v: [0, ["10 / mo", "10 次/月"], ["150 / mo", "150 次/月"]] },
      { l: ["Drives Terminal charts", "操控 Terminal 图表"], v: [0, 1, 1] }
    ] },
    { g: ["RESEARCH", "研究"], rows: [
      { l: ["Mastermind research reports", "Mastermind 研究报告"], v: [0, 0, 1] },
      { l: ["Institutional research library", "机构研究库"],       v: [0, 0, 1] },
      { l: ["Mastermind Bot Portfolios", "Mastermind 机器人组合"], v: [0, 0, 1] },
      { l: ["MCP server", "MCP 服务器"],                           v: [0, 0, "soon"] }
    ] }
  ];

  // ── host skin ──────────────────────────────────────────────────────────────
  // The sheet opens over the LIGHT landing and over the DARK macro pages alike.
  // A page that ships theme.css owns a real light/dark skin; the landing does
  // not (it is light-only), so its html[data-theme] — which the Preferences step
  // writes — must never darken the sheet there.
  function hostThemed() { try { return !!document.querySelector('link[href*="theme.css"]'); } catch (e) { return false; } }
  // What the page ACTUALLY looks like, not what it says it is: html[data-theme]
  // is the fast path, but a dark-by-default page carries no attribute until
  // theme.js boots (and the render lane can rename stylesheets out from under a
  // link-based check). The rendered background is the fact we care about — we
  // are covering it — so fall back to its luminance.
  function pageIsDark() {
    try {
      var nodes = [document.body, document.documentElement];
      for (var i = 0; i < nodes.length; i++) {
        if (!nodes[i]) continue;
        var m = /rgba?\(\s*([\d.]+)[,\s]+([\d.]+)[,\s]+([\d.]+)(?:[,\s/]+([\d.]+))?/.exec(getComputedStyle(nodes[i]).backgroundColor || "");
        if (!m) continue;
        if (m[4] !== undefined && parseFloat(m[4]) === 0) continue;   // transparent → ask the parent
        var lum = (0.2126 * +m[1] + 0.7152 * +m[2] + 0.0722 * +m[3]) / 255;
        return lum < 0.45;
      }
    } catch (e) {}
    return false;
  }
  function hostSkin() {
    if (!hostThemed()) return "light";           // the landing is light-only by design
    try {
      var attr = document.documentElement.getAttribute("data-theme");
      if (attr === "dark") return "dark";
      if (attr === "light") return "light";
    } catch (e) {}
    return pageIsDark() ? "dark" : "light";
  }
  function syncSkin() {
    if (!el.scrim) return;
    var sk = hostSkin();
    if (el.scrim.getAttribute("data-obm-skin") !== sk) el.scrim.setAttribute("data-obm-skin", sk);
  }

  // ── state ────────────────────────────────────────────────────────────────
  var S = {
    open: false, mode: "signup", step: STEP_ACCOUNT,
    firstName: "", lastName: "", email: "", password: "",
    prefs: { market_focus: [], trade_types: [], theme_pref: "auto" },
    plan: "pro", period: "annual",
    confirmPending: false, trialActive: false, trialEnd: null, subLive: false,
    // upgrade mode (post-login monetization sheet). upStep is the upgrade lane's
    // OWN progression (plan → billing) — it never borrows the signup stepper.
    pendingUpgrade: false, upgradeOpts: null, me: null, upStep: "plan",
    // the compare layer (over the plan step) + which column a phone is reading
    compare: false, compareCol: null
  };

  // ── stash (per-tab, password never persisted) ──────────────────────────────
  function stashSave() {
    try {
      sessionStorage.setItem(SS_STASH, JSON.stringify({
        open: S.open, mode: S.mode, step: S.step,
        firstName: S.firstName, lastName: S.lastName, email: S.email,
        prefs: S.prefs, plan: S.plan, period: S.period,
        confirmPending: S.confirmPending, trialActive: S.trialActive, trialEnd: S.trialEnd,
        subLive: S.subLive,
        planTouched: S.planTouched
      }));
    } catch (e) { /* storage blocked */ }
  }
  function stashClear() { try { sessionStorage.removeItem(SS_STASH); } catch (e) {} }
  function stashLoad() {
    var raw = null; try { raw = sessionStorage.getItem(SS_STASH); } catch (e) {}
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (e) { return null; }
  }

  // ── Supabase broker (via MDXAuth; lazy-load theme.js if the page lacks it) ──
  var _themeLoad = null;
  function ensureAuthBroker() {
    if (window.MDXAuth) return Promise.resolve(window.MDXAuth);
    if (_themeLoad) return _themeLoad;
    _themeLoad = new Promise(function (resolve) {
      var s = document.createElement("script");
      s.src = "theme.js"; s.defer = true;
      s.onload = function () { resolve(window.MDXAuth || null); };
      s.onerror = function () { resolve(null); };
      (document.head || document.documentElement).appendChild(s);
    });
    return _themeLoad;
  }
  function sbClient() {
    return ensureAuthBroker().then(function (auth) {
      if (auth && typeof auth.client === "function") return auth.client();
      return null;
    });
  }
  function authEnabled() { return !!(window.MDXAuth && window.MDXAuth.enabled && window.MDXAuth.enabled()); }
  // The landing serves /api/* on its OWN origin (Caddy proxies to macro-api). theme.js
  // sets window.MM_API='https://app.mastermind-x.com' for the macro DASHBOARD pages, but
  // on the landing that turns /api/me + /api/billing/* into CROSS-ORIGIN calls the Terminal
  // answers WITHOUT CORS headers → the browser blocks the read, fetchMe rejects, and the
  // signed-in chrome never paints (the "Log in still shows after login" bug). So the landing
  // always talks same-origin; only honor a cross-origin MM_API when hosted off the site.
  function apiBase() {
    var host = location.hostname || "";
    if (/(^|\.)mastermind-x\.com$/i.test(host) || host === "localhost" || host === "127.0.0.1") return "";
    return (window.MM_API || "").replace(/\/+$/, "");
  }
  function syncFoundingOffer() {
    return fetch(apiBase() + "/api/billing/offers/" + encodeURIComponent(FOUNDING_PRO.key), {
      cache: "no-store", credentials: "include"
    }).then(function (r) {
      if (!r.ok) return null;
      return r.json().catch(function () { return null; });
    }).then(function (o) {
      if (!o) return null;
      FOUNDING_PRO.active = !!o.active;
      FOUNDING_PRO.claimed = typeof o.claimed === "number" ? o.claimed : null;
      FOUNDING_PRO.cap = typeof o.cap === "number" ? o.cap : FOUNDING_PRO.cap;
      if (el.body && el.body.querySelector("[data-obm-plan]")) updatePlanUI();
      return o;
    }).catch(function () { return null; });
  }
  // Cheap signed-in sniff without loading theme.js (mirrors theme.js _hasSessionCookie):
  // an `sb-…-auth-token` or a chunk `…-auth-token.0` cookie. Guests pay zero cost.
  function hasSessionCookie() {
    try {
      var parts = String(document.cookie || "").split(";");
      for (var i = 0; i < parts.length; i++) {
        var name = parts[i].split("=")[0].trim();
        if (/^sb-.*-auth-token(\.\d+)?$/.test(name)) return true;
      }
    } catch (e) {}
    return false;
  }

  // ── DOM refs (built lazily on first open) ──────────────────────────────────
  var el = {};   // { scrim, sheet, steps, body, foot, ... }
  var built = false;

  function h(tag, cls, attrs) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (attrs) for (var k in attrs) if (attrs.hasOwnProperty(k)) n.setAttribute(k, attrs[k]);
    return n;
  }
  // icons
  function svgCheck(cls) { return '<svg class="' + (cls || "") + '" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg>'; }
  var GLYPH = '<svg viewBox="0 0 40 40" xmlns="http://www.w3.org/2000/svg" aria-hidden="true"><defs><linearGradient id="obmTile" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5b9dff"/><stop offset=".42" stop-color="#3b82f6"/><stop offset=".74" stop-color="#6366f1"/><stop offset="1" stop-color="#7c5cff"/></linearGradient><linearGradient id="obmSheen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff" stop-opacity=".34"/><stop offset=".55" stop-color="#ffffff" stop-opacity="0"/></linearGradient><radialGradient id="obmGlow" cx=".5" cy=".4" r=".65"><stop offset="0" stop-color="#ffffff" stop-opacity=".22"/><stop offset="1" stop-color="#ffffff" stop-opacity="0"/></radialGradient><linearGradient id="obmInk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffffff"/><stop offset="1" stop-color="#dbe7ff"/></linearGradient></defs><rect x="3" y="3" width="34" height="34" rx="10.5" fill="url(#obmTile)"/><rect x="3" y="3" width="34" height="34" rx="10.5" fill="url(#obmGlow)"/><rect x="3" y="3" width="34" height="34" rx="10.5" fill="url(#obmSheen)"/><rect x="3.7" y="3.7" width="32.6" height="32.6" rx="9.9" fill="none" stroke="#ffffff" stroke-opacity=".28"/><g fill="none" stroke-linecap="round" stroke-linejoin="round" stroke-width="3.3"><path d="M13 28 L13 14.5 L20 22 L27 12.5 L27 28" stroke="#15205a" stroke-opacity=".30" transform="translate(0,1.1)"/><path d="M13 28 L13 14.5 L20 22 L27 12.5 L27 28" stroke="url(#obmInk)"/></g></svg>';
  var GOOGLE = '<svg viewBox="0 0 18 18" width="16" height="16" aria-hidden="true"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"/><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"/><path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33z"/><path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"/></svg>';
  var LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  // The stage's annotated mini-chart: an uptrend that pulls back INTO the
  // buy-zone band and resumes — the product's own entry story, not a skeleton.
  // pathLength=1 lets CSS draw the line with a single dashoffset animation.
  var DESK_CHART =
    '<svg viewBox="0 0 300 124" preserveAspectRatio="none" aria-hidden="true">' +
    '<defs>' +
    '<linearGradient id="obmDL" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#285fff"/><stop offset="1" stop-color="#7862e0"/></linearGradient>' +
    '<linearGradient id="obmDA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#285fff" stop-opacity=".14"/><stop offset="1" stop-color="#285fff" stop-opacity="0"/></linearGradient>' +
    '</defs>' +
    '<g stroke="currentColor" stroke-opacity=".07" stroke-width="1"><path d="M0 33H300"/><path d="M0 64H300"/><path d="M0 95H300"/></g>' +
    '<rect x="0" y="78" width="300" height="26" fill="rgba(40,95,255,.07)"/>' +
    '<path d="M0 78H300" stroke="rgba(40,95,255,.30)" stroke-width="1" stroke-dasharray="3 4" fill="none"/>' +
    '<path d="M0 104H300" stroke="rgba(40,95,255,.30)" stroke-width="1" stroke-dasharray="3 4" fill="none"/>' +
    '<path class="obm-hero-area" d="M8 68 L40 60 L66 66 L92 46 L118 52 L148 84 L172 90 L198 68 L232 50 L262 40 L292 27 L292 124 L8 124 Z" fill="url(#obmDA)"/>' +
    '<path class="obm-hero-line" pathLength="1" d="M8 68 L40 60 L66 66 L92 46 L118 52 L148 84 L172 90 L198 68 L232 50 L262 40 L292 27" fill="none" stroke="url(#obmDL)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<circle cx="292" cy="27" r="3.2" fill="#285fff"/>' +
    '<circle class="obm-hero-ring" cx="292" cy="27" r="3.2" fill="none" stroke="#285fff" stroke-width="1.4"/>' +
    '</svg>';

  // ── the tier lattice ────────────────────────────────────────────────────────
  // Nine capability tiles in three rows, and the ROWS ARE THE TIERS. Picking a
  // plan lights every row up to it, in a staggered cascade; the rows above your
  // plan keep their lock. The picture and the price list can never disagree,
  // because they are generated from the same table.
  var TILE_ICON = {
    read:    '<path d="M4 19h16"/><path d="M4 15l4.5-5 3.5 3 4-6 4 5"/>',
    signals: '<path d="M12 3v3"/><path d="M12 18v3"/><circle cx="12" cy="12" r="4"/><path d="M3 12h3"/><path d="M18 12h3"/>',
    charts:  '<path d="M7 4v16"/><rect x="4.5" y="8" width="5" height="7" rx="1"/><path d="M17 4v16"/><rect x="14.5" y="6" width="5" height="9" rx="1"/>',
    flow:    '<path d="M3 9h12l-3-3"/><path d="M21 15H9l3 3"/>',
    desks:   '<path d="M3 20h18"/><path d="M5 20V10"/><path d="M10 20V10"/><path d="M14 20V10"/><path d="M19 20V10"/><path d="M3.5 10 12 4l8.5 6"/>',
    flash:   '<path d="M13 3 5 14h6l-1 7 8-11h-6z"/>',
    reports: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/><path d="M9 12h6"/><path d="M9 16h4"/>',
    dives:   '<path d="M12 3 4 8l8 5 8-5z"/><path d="M4 14l8 5 8-5"/>',
    bots:    '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>'
  };
  var LATTICE = [
    { tier: "free",    lbl: "rowFree",    tiles: [["read", "tlRead"], ["signals", "tlSignals"], ["charts", "tlCharts"]] },
    { tier: "essential", lbl: "rowInsider", tiles: [["flow", "tlFlow"], ["desks", "tlDesks"], ["flash", "tlFlash"]] },
    { tier: "pro",     lbl: "rowPro",     tiles: [["reports", "tlReports"], ["dives", "tlDives"], ["bots", "tlBots"]] }
  ];
  // which tile each "what you trade" answer pins — the pick has a visible consequence
  var TRADE_PIN = { stocks: "signals", options: "flow", crypto: "charts" };

  function latticeHtml() {
    var out = "", i = 0;
    LATTICE.forEach(function (row) {
      out += '<div class="obm-row" data-tier="' + row.tier + '">' +
             '<span class="obm-row-lbl" data-k="' + row.lbl + '">' + tx(row.lbl) + '</span>';
      row.tiles.forEach(function (t) {
        out += '<div class="obm-tile" data-tile="' + t[0] + '" style="--i:' + (i++) + '">' +
               '<span class="obm-tile-i"><svg viewBox="0 0 24 24" aria-hidden="true">' + TILE_ICON[t[0]] + '</svg></span>' +
               '<span class="obm-tile-l" data-k="' + t[1] + '">' + tx(t[1]) + '</span>' +
               '<span class="obm-tile-lk">' + LOCK + '</span></div>';
      });
      out += '</div>';
    });
    return out;
  }
  function meterHtml() {
    var ticks = "";
    for (var d = 0; d < 7; d++) ticks += '<i style="--i:' + d + ';--h:' + (d * 3) + '"></i>';
    return '<p class="obm-meter-hd" data-k="meterHd">' + tx("meterHd") + '</p>' +
           '<div class="obm-meter-track">' + ticks + '</div>' +
           '<div class="obm-meter-foot"><span class="obm-meter-day" data-k="meterToday">' + tx("meterToday") + '</span>' +
           '<span class="obm-meter-chg" data-stage="charge"></span></div>' +
           '<p class="obm-meter-note" data-k="meterNote">' + tx("meterNote") + '</p>';
  }
  function deskHtml() {
    return '<div class="obm-plate"><span class="obm-plate-ava" data-stage="ava">M</span>' +
           '<span class="obm-plate-nm" data-stage="name"></span>' +
           '<span class="obm-plate-st" data-stage="state"><i></i><b data-stage="statetxt"></b></span></div>' +
           '<div class="obm-hero"><div class="obm-hero-hd"><b data-stage="tkr">SPY</b>' +
           '<span class="obm-hero-tf" data-k="deskTf"></span>' +
           '<span class="obm-hero-sig" data-k="deskSignal"></span></div>' + DESK_CHART +
           '<span class="obm-hero-zone" data-k="deskZone"></span>' +
           '<span class="obm-hero-note" data-k="deskSample"></span></div>' +
           '<div class="obm-lat">' + latticeHtml() + '</div>' +
           '<div class="obm-tape"><div class="obm-tape-in" data-stage="tape"></div></div>';
  }

  // ── build the sheet DOM once ──────────────────────────────────────────────
  function build() {
    if (built) return;
    built = true;

    var scrim = h("div", "obm-scrim");
    var sheet = h("div", "obm-sheet obm-root", { role: "dialog", "aria-modal": "true", "aria-label": tx("dialogLbl") });

    // close
    var close = h("button", "obm-close", { type: "button", "aria-label": tx("closeLbl") });
    close.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M6 6l12 12M18 6L6 18"/></svg>';
    close.addEventListener("click", requestClose);

    // ── LEFT — the stage ──
    var pane = h("div", "obm-pane", { "data-step": "1", "data-tone": "light", "aria-hidden": "true" });
    pane.appendChild(h("div", "obm-beam"));
    var brand = h("div", "obm-brand"); brand.innerHTML = GLYPH + '<span>MASTERMIND</span>';
    var paneCopy = h("div", "obm-pane-copy");
    var paneH = h("h2", "obm-pane-h"); var paneS = h("p", "obm-pane-sub");
    paneCopy.appendChild(paneH); paneCopy.appendChild(paneS);
    var stage = h("div", "obm-stage");
    var desk = h("div", "obm-desk");
    desk.innerHTML = deskHtml();
    var meter = h("div", "obm-meter");
    meter.innerHTML = meterHtml();
    stage.appendChild(desk); stage.appendChild(meter);
    pane.appendChild(brand); pane.appendChild(paneCopy); pane.appendChild(stage);

    // ── RIGHT form pane ──
    var formPane = h("div", "obm-form-pane");
    var steps = h("div", "obm-steps");
    var mini = h("div", "obm-steps-mini");
    mini.innerHTML = '<div class="obm-mini-bar"><i style="width:0"></i></div>' +
                     '<div class="obm-mini-lbl"><b data-stage="miniN"></b><span data-stage="miniT"></span></div>';
    var body = h("div", "obm-body");
    var foot = h("div", "obm-foot");
    formPane.appendChild(steps); formPane.appendChild(mini); formPane.appendChild(body); formPane.appendChild(foot);
    // footer lifts while there is still content below the fold (the Plan step's
    // list used to be silently clipped — now it is visibly scrollable)
    body.addEventListener("scroll", syncFootLift, { passive: true });

    sheet.appendChild(close); sheet.appendChild(pane); sheet.appendChild(formPane);
    scrim.appendChild(sheet);
    document.body.appendChild(scrim);

    // scrim click closes (but not clicks inside the sheet)
    scrim.addEventListener("mousedown", function (e) { if (e.target === scrim) requestClose(); });
    // any interaction wakes the stage's ambient motion back up (see nudgeIdle)
    sheet.addEventListener("pointerdown", nudgeIdle, { passive: true });
    sheet.addEventListener("keydown", nudgeIdle, { passive: true });

    el = { scrim: scrim, sheet: sheet, pane: pane, paneH: paneH, paneS: paneS, paneCopy: paneCopy,
           desk: desk, meter: meter, steps: steps, mini: mini, body: body, foot: foot,
           formPane: formPane, cmp: null };
    syncSkin();

    // Ambient motion is a battery cost, not a feature: park every loop the
    // moment the tab is hidden (same law as the start.html hero guard).
    try {
      document.addEventListener("visibilitychange", function () {
        if (document.hidden) parkStage(true); else if (S.open) parkStage(false);
      });
    } catch (e) {}

    // subscribe to language changes → re-apply our subtree
    if (window.LANG && typeof window.LANG.onChange === "function") window.LANG.onChange(applyLang);
    // also observe html[data-lang] directly (robust if LANG isn't present yet),
    // and html[data-theme] so the sheet's skin tracks a theme flip made behind
    // it — or by our own Preferences step on a theme-capable page.
    try {
      new MutationObserver(function (recs) {
        var lang = false;
        for (var i = 0; i < recs.length; i++) if (recs[i].attributeName === "data-lang") lang = true;
        syncSkin();
        if (lang) applyLang(); else renderStage();
      }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-lang", "data-theme"] });
    } catch (e) {}
  }

  // ── bilingual applier over OUR subtree (mirrors the landing's __en swap) ────
  function applyLang() {
    if (!el.sheet) return;
    var zh = lang() === "zh";
    // static [data-obm-zh] nodes (innerHTML swap, caching the English original once)
    var nodes = el.sheet.querySelectorAll("[data-obm-zh]");
    for (var i = 0; i < nodes.length; i++) {
      var n = nodes[i];
      if (n.__en == null) n.__en = n.innerHTML;
      n.innerHTML = zh ? n.getAttribute("data-obm-zh") : n.__en;
    }
    // keyed nodes ([data-k]) — label from LEX by key
    var keyed = el.sheet.querySelectorAll("[data-k]");
    for (var j = 0; j < keyed.length; j++) keyed[j].innerHTML = tx(keyed[j].getAttribute("data-k"));
    el.sheet.setAttribute("aria-label", tx("dialogLbl"));
    // substituted labels (no [data-k]) rebuild by hand
    if (el.cmp) { var go = el.cmp.querySelector("[data-obm-cmp-go]"); if (go) go.textContent = comparePickLabel(); }
    // the nameplate builds its possessive per-language in code, not via [data-k]
    renderStage();
    renderMini();
  }

  // helper: create a node whose text is a LEX key, re-applied on lang change
  function T(tag, cls, key, attrs) { var n = h(tag, cls, attrs); n.setAttribute("data-k", key); n.innerHTML = tx(key); return n; }

  // ══════════════════════════ stepper ════════════════════════════════════════
  function paidSelected() { return S.plan === "essential" || S.plan === "pro"; }
  function renderSteps() {
    var defs = [
      { n: STEP_ACCOUNT, key: "stAccount" },
      { n: STEP_PREFS, key: "stPrefs" },
      { n: STEP_PLAN, key: "stPlan" },
      { n: STEP_BILLING, key: "stBilling", paidOnly: true },
      { n: STEP_DONE, key: "stDone" }
    ];
    el.steps.innerHTML = "";
    var shown = defs.filter(function (d) { return !(d.paidOnly && !paidSelected()); });
    shown.forEach(function (d, idx) {
      var s = h("div", "obm-step");
      var done = isStepDone(d.n);
      if (d.n === S.step) s.classList.add("obm-cur");
      else if (done) s.classList.add("obm-past");   /* not "obm-done": that class is the Done VIEW (a column flexbox) */
      // single digits: "01" never fit its 19px ring — that was the padding defect
      s.innerHTML = '<span class="obm-step-n">' + svgCheck("obm-step-ck") +
                    '<span class="obm-step-num">' + d.n + '</span></span>';
      s.appendChild(T("span", "obm-step-lbl", d.key));
      el.steps.appendChild(s);
      if (idx < shown.length - 1) {
        var sep = h("span", "obm-step-sep" + (done ? " obm-on" : ""));
        sep.innerHTML = "<i></i>";
        el.steps.appendChild(sep);
      }
    });
    renderMini();
  }
  // phone stepper: one rail + "Step 3 of 5 · Plan" (five chips never fit a 375px screen)
  function renderMini() {
    if (!el.mini) return;
    var order = paidSelected() ? [1, 2, 3, 4, 5] : [1, 2, 3, 5];
    var keys = { 1: "stAccount", 2: "stPrefs", 3: "stPlan", 4: "stBilling", 5: "stDone" };
    var idx = Math.max(0, order.indexOf(S.step));
    var bar = el.mini.querySelector(".obm-mini-bar i");
    if (bar) bar.style.width = Math.round(((idx + 1) / order.length) * 100) + "%";
    var n = el.mini.querySelector('[data-stage="miniN"]');
    var t = el.mini.querySelector('[data-stage="miniT"]');
    if (n) n.textContent = escLine(LEX.stepOf, { "__N__": String(idx + 1), "__T__": String(order.length) });
    if (t) { t.setAttribute("data-k", keys[S.step] || "stAccount"); t.textContent = tx(keys[S.step] || "stAccount"); }
  }
  function isStepDone(n) {
    // signin mode has no stepper progression; treat all as neutral
    if (S.mode === "signin") return false;
    if (S.step === STEP_DONE) return n < STEP_DONE;
    return n < S.step;
  }
  // the footer floats once the body has more below the fold
  function syncFootLift() {
    if (!el.body || !el.foot) return;
    var more = (el.body.scrollHeight - el.body.scrollTop - el.body.clientHeight) > 4;
    el.foot.classList.toggle("obm-lift", more);
  }

  // ══════════════════════════ THE STAGE ══════════════════════════════════════
  // The left column plays the desk coming online. Nothing here echoes a form
  // field back; every element is a piece of the product responding to a choice
  // the visitor actually made:
  //   nameplate  ← the typed first name (default "YOUR DESK")
  //   chart+tape ← the market picks (the first pick drives the chart's ticker)
  //   lattice    ← the chosen plan: rows ARE the tiers, so picking one lights
  //                exactly what it buys and locks exactly what it doesn't
  //   meter      ← billing: the seven trial days and the date of first charge
  // Upgrade mode plays the same stage off /api/me — the locked rows are then
  // literally what the upgrade would light up.
  var MKD = {
    us:     { t: "NVDA",    c: ["NVDA", "SPY", "TSLA", "AAPL", "MSFT"] },
    cn:     { t: "600519",  c: ["600519", "300750", "BABA", "000858", "601318"] },
    hk:     { t: "0700.HK", c: ["0700", "9988", "3690", "1810", "0388"] },
    ca:     { t: "SHOP.TO", c: ["SHOP", "RY", "ENB", "CNQ", "BN"] },
    global: { t: "SPY",     c: ["SPY", "ASML", "0700", "NVDA", "TSM"] }
  };
  // Ranks BOTH tier spellings: this is fed pre-normalisation in places, and a
  // pre-rename row saying "insider" must not out-rank nothing.
  var RANK = { free: 0, essential: 1, insider: 1, pro: 2, unlimited: 2 };

  function stageStep() {
    // upgrade mode plays the same stage on its OWN two-step lane
    if (S.mode === "upgrade") return S.upDone ? 5 : (S.upStep === "billing" ? 4 : 3);
    if (S.mode === "signin") return 1;
    return S.step;
  }
  // the tone the stage previews: the visitor's theme pick. "auto" on a
  // theme-capable page means the page itself already IS their real setting.
  function stageTone() {
    var p = S.prefs.theme_pref;
    if (p === "dark") return "dark";
    if (p === "light") return "light";
    if (hostThemed()) return hostSkin();
    var hh = new Date().getHours(); return (hh >= 7 && hh < 19) ? "light" : "dark";
  }
  // The billing pane sells free days on a trial plan and a clear price today on one
  // without — the honest split, chosen by KEY so the language applier keeps working.
  function billPaneKeys() {
    return planHasTrial(S.plan) ? ["paneBillH", "paneBillS"] : ["paneBillNoTrialH", "paneBillNoTrialS"];
  }
  function renderPane() {
    var map = {
      1: ["paneAccountH", "paneAccountS"], 2: ["panePrefsH", "panePrefsS"],
      3: ["planePlanH", "planePlanS"], 4: billPaneKeys(), 5: ["paneDoneH", "paneDoneS"]
    };
    // upgrade mode borrows the billing pane copy ("7 days free · cancel in one
    // click") until it lands, then the Done copy
    var m = (S.mode === "upgrade")
      ? (S.upDone ? ["paneDoneH", "paneDoneS"] : billPaneKeys())
      : (map[S.step] || map[1]);
    var changed = el.paneH.getAttribute("data-k") !== m[0];
    el.paneH.setAttribute("data-k", m[0]); el.paneH.innerHTML = tx(m[0]);
    el.paneS.setAttribute("data-k", m[1]); el.paneS.innerHTML = tx(m[1]);
    if (changed && el.paneCopy) {           // re-set the copy on a real step change only
      el.paneCopy.classList.remove("obm-swap");
      void el.paneCopy.offsetWidth;
      el.paneCopy.classList.add("obm-swap");
    }
    renderStage();
  }

  function renderStage() {
    if (!el.desk || !el.pane) return;
    var q = function (s) { return el.desk.querySelector(s); };
    var zh = lang() === "zh";
    var step = stageStep();
    el.pane.setAttribute("data-step", String(step));
    el.pane.setAttribute("data-tone", stageTone());

    // ── nameplate ──
    var first = (S.mode === "upgrade") ? (fullNameFromMeta().split(" ")[0] || "") : S.firstName.trim();
    var plate = q('[data-stage="name"]');
    var want = first
      ? (zh ? first.toUpperCase() + " 的工作台"
            : first.toUpperCase() + (/S$/.test(first.toUpperCase()) ? "’ DESK" : "’S DESK"))
      : tx("deskYour");
    if (plate.textContent !== want) plate.textContent = want;
    var ava = q('[data-stage="ava"]');
    var initial = first ? first.charAt(0).toUpperCase() : "M";
    if (ava.textContent !== initial) {       // the initial lands with a small pop
      ava.textContent = initial;
      ava.classList.add("obm-pop");
      setTimeout(function () { ava.classList.remove("obm-pop"); }, 260);
    }

    // ── plate state: what the desk is doing right now ──
    var tier = null;
    // upgrade: paid lanes show what you HAVE (the locks are what an upgrade
    // would light); the free lane is an active pick, so it shows the pick.
    if (S.mode === "upgrade") tier = (S.upPre && S.planTouched) ? S.plan : ((S.me && normTier(S.me.tier)) || "free");
    else if (S.planTouched) tier = S.plan;
    var stBox = q('[data-stage="state"]'), stTxt = q('[data-stage="statetxt"]');
    var st = "setup", stKey = "plateSetup";
    if (step === 5) { st = "live"; stKey = "plateLive"; }
    else if (step === 4) { st = "trial"; stKey = planHasTrial(S.plan) ? "asmTrial" : "asmCheckout"; }
    else if (step === 3 && tier && tier !== "free") { st = tier === "pro" ? "pro" : "essential"; stKey = tier === "pro" ? "planPro" : "planInsider"; }
    else if (step === 3 && tier === "free") { st = "setup"; stKey = "planFree"; }
    stBox.setAttribute("data-st", st);
    stTxt.setAttribute("data-k", stKey); stTxt.textContent = tx(stKey);

    // ── chart ticker + tape follow the market picks ──
    var picks = S.prefs.market_focus;
    var mk = picks.length ? (MKD[picks[0]] || MKD.us) : MKD.global;
    var tkr = q('[data-stage="tkr"]');
    if (tkr.textContent !== mk.t) { tkr.textContent = mk.t; redrawDesk(); }
    var syms = [];
    (picks.length ? picks : ["global"]).forEach(function (k) {
      (MKD[k] || MKD.us).c.forEach(function (t) { if (syms.indexOf(t) === -1) syms.push(t); });
    });
    syms = syms.slice(0, 8);
    var tape = q('[data-stage="tape"]');
    var sig = syms.join(",");
    if (tape.__sig !== sig) {                 // rebuild only when the picks change
      tape.__sig = sig;
      var run = syms.map(function (t) { return "<span>" + esc(t) + "</span>"; }).join("");
      tape.innerHTML = run + run;             // doubled → the marquee loops seamlessly
    }
    // the chart earns its BUY SIGNAL chip once the desk is actually provisioned
    el.desk.classList.toggle("obm-armed", step >= 3);

    // ── the lattice: light every row up to the chosen tier ──
    var have = tier == null ? null : (RANK[normTier(tier)] != null ? RANK[normTier(tier)] : 0);
    var pins = pinnedTiles();
    var rows = el.desk.querySelectorAll(".obm-row");
    for (var r = 0; r < rows.length; r++) {
      var row = rows[r];
      var lit = have != null && have >= r;
      row.classList.toggle("obm-on", lit);
      var tiles = row.querySelectorAll(".obm-tile");
      for (var c = 0; c < tiles.length; c++) {
        var tile = tiles[c];
        var was = tile.classList.contains("obm-on");
        tile.classList.toggle("obm-on", lit);
        if (lit && !was) flare(tile);        // the cascade — only on a real change
        // "what you trade" pins its tile, so that answer has a visible consequence
        tile.classList.toggle("obm-pin", pins.indexOf(tile.getAttribute("data-tile")) !== -1);
      }
    }

    // ── the trial meter: seven ticks, one per free day. A plan with no trial has
    //    nothing for it to count, so it comes off the stage entirely rather than
    //    counting down days nobody was given. ──
    if (el.meter) el.meter.style.display = planHasTrial(S.plan) ? "" : "none";
    var chg = el.meter && el.meter.querySelector('[data-stage="charge"]');
    if (chg) chg.textContent = escLine(LEX.meterChg, { "__D__": fmtDate(trialChargeDate()).toUpperCase() });

    // keep keyed labels (row names, tile names, chips) in the current language
    var keys = el.pane.querySelectorAll("[data-k]");
    for (var i = 0; i < keys.length; i++) keys[i].innerHTML = tx(keys[i].getAttribute("data-k"));
  }
  function pinnedTiles() {
    var out = [];
    S.prefs.trade_types.forEach(function (t) { if (TRADE_PIN[t]) out.push(TRADE_PIN[t]); });
    return out;
  }
  // one-shot light sweep across a tile the moment it unlocks
  function flare(tile) {
    tile.classList.remove("obm-flare");
    void tile.offsetWidth;
    tile.classList.add("obm-flare");
    setTimeout(function () { tile.classList.remove("obm-flare"); }, 1400);
  }
  // restart the chart's draw-in (used on open + when the ticker swaps)
  function redrawDesk() {
    if (!el.desk) return;
    el.desk.classList.remove("obm-draw");
    void el.desk.offsetWidth;
    el.desk.classList.add("obm-draw");
  }
  // ── ambient-motion budget ────────────────────────────────────────────────
  // Two looping animations run on the stage (the light beam and the tape). Both
  // are transform-only, and both stop whenever nobody is watching: tab hidden,
  // sheet closed, or 40s without an interaction. Same law as the start.html
  // hero guard — a signup sheet must never be why a phone gets hot.
  var _idleTimer = null;
  function parkStage(on) {
    if (!el.pane) return;
    el.pane.classList.toggle("obm-park", !!on);
  }
  function nudgeIdle() {
    if (!el.pane) return;
    parkStage(false);
    if (_idleTimer) clearTimeout(_idleTimer);
    _idleTimer = setTimeout(function () { parkStage(true); }, 40000);
  }

  // ══════════════════════════ router ═════════════════════════════════════════
  function go(step) { S.step = step; if (step >= STEP_PLAN && S.mode === "signup") S.planTouched = true; render(); stashSave(); }
  function render() {
    if (!el.sheet) return;
    syncSkin();
    destroyCompare();          // a step change always dismisses the compare layer
    renderSteps();
    // signin + upgrade are compact single-panel variants — hide the multi-step stepper
    var solo = (S.mode === "signin" || S.mode === "upgrade");
    el.steps.style.display = solo ? "none" : "";
    if (el.mini) el.mini.style.display = solo ? "none" : "";
    renderPane();
    el.body.innerHTML = "";
    el.foot.innerHTML = "";
    var view;
    if (S.mode === "upgrade") view = viewUpgrade();       // post-login monetization sheet
    else if (S.mode === "signin") view = viewAccount();   // signin lives on step 1 only
    else if (S.step === STEP_ACCOUNT) view = viewAccount();
    else if (S.step === STEP_PREFS) view = viewPrefs();
    else if (S.step === STEP_PLAN) view = viewPlan();
    else if (S.step === STEP_BILLING) view = viewBilling();
    else view = viewDone();
    if (view === null) return;   // a nested render() (upgrade→free handoff) already owns the DOM
    el.body.appendChild(view);
    el.body.scrollTop = 0;
    applyLang();
    nudgeIdle();
    // a step may be taller than the pane — say so, and never clip the footer
    requestAnimationFrame(syncFootLift);
    // focus the heading (a11y)
    var head = el.body.querySelector("[data-ob-heading]");
    if (head) { try { head.focus(); } catch (e) {} }
  }

  // ── footer builders ──
  function footNav(opts) {
    // opts: { back:bool, primaryKey, onPrimary, secondaryKey, onSecondary, dots:bool, primaryOut:bool, primaryDisabled }
    var back = h("button", "obm-back", { type: "button" });
    back.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg><span data-k="goBack">' + tx("goBack") + '</span>';
    back.addEventListener("click", opts.onBack || function () {});
    if (opts.back) el.foot.appendChild(back);
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    if (opts.dots) el.foot.appendChild(dotsFor());
    if (opts.primaryKey) {
      var b = T("button", opts.primaryOut ? "obm-btn-out" : "obm-btn", opts.primaryKey, { type: "button" });
      if (opts.primaryDisabled) b.disabled = true;
      b.addEventListener("click", opts.onPrimary);
      el.foot.appendChild(b);
    }
  }
  function dotsFor() {
    var wrap = h("div", "obm-dots");
    var order = paidSelected() ? [1, 2, 3, 4, 5] : [1, 2, 3, 5];
    order.forEach(function (n) { var i = h("i"); if (n === S.step) i.classList.add("obm-on"); wrap.appendChild(i); });
    return wrap;
  }

  // ══════════════════════════ STEP 1 — ACCOUNT ══════════════════════════════
  function viewAccount() {
    var signin = S.mode === "signin";
    var root = h("div", "obm-fade");
    var head = T("h1", "obm-h1", signin ? "signinTitle" : "accountTitle"); head.setAttribute("data-ob-heading", ""); head.setAttribute("tabindex", "-1");
    var sub = T("p", "obm-sub", signin ? "signinSub" : "accountSub");
    root.appendChild(head); root.appendChild(sub);

    var form = h("form", "obm-form");
    if (!signin) {
      var row = h("div", "obm-row2");
      row.appendChild(field("firstName", "ob-fn", "text", S.firstName, "Jordan", "given-name", function (v) { S.firstName = v; renderStage(); }));
      row.appendChild(field("lastName", "ob-ln", "text", S.lastName, "Wei", "family-name", function (v) { S.lastName = v; renderStage(); }));
      form.appendChild(row);
    }
    form.appendChild(field("email", "ob-email", "email", S.email, "you@example.com", "email", function (v) { S.email = v; renderStage(); }, true));
    var pwWrap = field("password", "ob-pw", "password", S.password, "••••••••", signin ? "current-password" : "new-password", function (v) { S.password = v; refreshPwHint(); }, true, 8);
    form.appendChild(pwWrap);
    if (!signin) { var hint = h("p", "obm-hint", { "data-obm-hint": "" }); hint.style.display = "none"; form.appendChild(hint); }

    var errBox = h("div", "obm-err"); errBox.style.display = "none"; errBox.setAttribute("data-obm-err", ""); form.appendChild(errBox);

    var submit = T("button", "obm-btn", signin ? "signin" : "createAccount", { type: "submit" });
    submit.style.marginTop = "16px"; submit.setAttribute("data-obm-submit", "");
    form.appendChild(submit);
    form.addEventListener("submit", onAccountSubmit);
    root.appendChild(form);

    // divider + Google + Apple
    var or = h("div", "obm-or"); or.setAttribute("data-k", "or"); or.innerHTML = tx("or"); root.appendChild(or);
    var g = T("button", "obm-btn-out", "continueGoogle", { type: "button" }); g.innerHTML = GOOGLE + '<span data-k="continueGoogle">' + tx("continueGoogle") + '</span>';
    g.addEventListener("click", onGoogle); root.appendChild(g);
    if (!signin) {
      var apple = T("button", "obm-btn-out", "appleSoon", { type: "button", disabled: "", "aria-disabled": "true" });
      apple.style.marginTop = "10px"; apple.style.cursor = "default"; root.appendChild(apple);
    }
    // mode switch
    var sw = T("button", "obm-link obm-brand-link", signin ? "toSignup" : "toSignin", { type: "button" });
    sw.style.marginTop = "16px"; sw.style.display = "block";
    sw.addEventListener("click", function () { S.mode = signin ? "signup" : "signin"; S.step = STEP_ACCOUNT; render(); stashSave(); });
    root.appendChild(sw);
    if (!signin) root.appendChild(T("p", "obm-terms", "terms"));

    // no footer on account step (actions are inline)
    return root;
  }
  function field(labelKey, id, type, val, ph, ac, onInput, required, minLen) {
    var wrap = h("div", "obm-field-wrap");
    var lbl = T("label", "", labelKey, { "for": id });
    var inp = h("input", "obm-field", { id: id, type: type, autocomplete: ac, placeholder: ph });
    if (required) inp.required = true;
    if (minLen) inp.minLength = minLen;
    inp.value = val || "";
    inp.addEventListener("input", function () { onInput(inp.value); });
    wrap.appendChild(lbl); wrap.appendChild(inp);
    return wrap;
  }
  function pwHintKey() { if (!S.password) return null; return S.password.length < 8 ? "pwHintShort" : "pwHintOk"; }
  function refreshPwHint() {
    var hint = el.body.querySelector("[data-obm-hint]"); if (!hint) return;
    var k = pwHintKey();
    if (!k) { hint.style.display = "none"; return; }
    hint.style.display = ""; hint.className = "obm-hint" + (k === "pwHintOk" ? " obm-ok" : "");
    hint.setAttribute("data-k", k); hint.innerHTML = tx(k);
  }
  function showErr(msg) { var e = el.body.querySelector("[data-obm-err]"); if (!e) return; if (!msg) { e.style.display = "none"; return; } e.style.display = ""; e.textContent = msg; }
  function setSubmitBusy(busy) {
    var b = el.body.querySelector("[data-obm-submit]"); if (!b) return;
    b.disabled = busy;
    if (busy) b.textContent = tx("busy"); else { b.setAttribute("data-k", S.mode === "signin" ? "signin" : "createAccount"); b.innerHTML = tx(S.mode === "signin" ? "signin" : "createAccount"); }
  }

  function onAccountSubmit(e) {
    e.preventDefault();
    showErr("");
    var emailInput = document.getElementById("ob-email");
    S.email = String(S.email || "").trim();
    if (!validEmail(S.email)) {
      showErr(tx("emailInvalid"));
      if (emailInput) {
        emailInput.setAttribute("aria-invalid", "true");
        emailInput.focus();
      }
      return;
    }
    if (emailInput) emailInput.removeAttribute("aria-invalid");
    if (!authEnabled() && !window.MDXAuth) {
      // auth broker not yet resolved — try to resolve, else show honest error
    }
    setSubmitBusy(true);
    sbClient().then(function (sb) {
      if (!sb) { setSubmitBusy(false); showErr(tx("billNotConfigured")); return; }
      if (S.mode === "signin") {
        sb.auth.signInWithPassword({ email: S.email, password: S.password }).then(function (r) {
          if (r.error) { showErr(r.error.message); setSubmitBusy(false); return; }
          S.password = ""; stashClear();
          // Signin fired from the Upgrade entry: don't redirect — resolve the
          // account and continue into the upgrade panel in place.
          if (S.pendingUpgrade) { S.pendingUpgrade = false; setSubmitBusy(false); enterUpgrade(S.upgradeOpts || {}); return; }
          // Normal signin — go to the desk (?ret wall target wins, else start.html).
          location.href = loginDest();
        });
        return;
      }
      // signup — stash first/last in user_metadata (mirror of terminal StepAccount)
      sb.auth.signUp({ email: S.email, password: S.password, options: { data: { first_name: S.firstName, last_name: S.lastName } } })
        .then(function (r) {
          if (r.error) { showErr(r.error.message); setSubmitBusy(false); return; }
          S.password = "";
          if (r.data && r.data.session == null) {
            // email-confirmation ON — no session. Advance to prefs, flag pending.
            S.confirmPending = true;
          }
          setSubmitBusy(false);
          go(STEP_PREFS);
        });
    });
  }

  function onGoogle() {
    showErr("");
    // stash wizard state for the OAuth round-trip (matches terminal oauth.ts shape).
    // `mode`/`pendingUpgrade` let the resume decide between redirect (signin) and
    // continuing the wizard / upgrade panel (signup / upgrade entry).
    try {
      localStorage.setItem(LS_ONBOARD_RESUME, JSON.stringify({
        step: STEP_PREFS, mode: S.mode, pendingUpgrade: !!S.pendingUpgrade,
        upgradeOpts: S.upgradeOpts || null,
        firstName: S.firstName, lastName: S.lastName,
        plan: S.plan, period: S.period, prefs: S.prefs
      }));
    } catch (e) {}
    stashSave();
    sbClient().then(function (sb) {
      if (!sb) { showErr(tx("billNotConfigured")); return; }
      var redirectTo = location.origin + location.pathname + "?onboard=resume";
      sb.auth.signInWithOAuth({ provider: "google", options: { redirectTo: redirectTo } })
        .then(function (r) { if (r && r.error) showErr(r.error.message); });
    });
  }

  // ══════════════════════════ STEP 2 — PREFERENCES ═══════════════════════════
  function viewPrefs() {
    var root = h("div", "obm-fade");
    var head = T("h1", "obm-h1", "prefsTitle"); head.setAttribute("data-ob-heading", ""); head.setAttribute("tabindex", "-1");
    root.appendChild(head);
    root.appendChild(T("p", "obm-sub", "prefsSub"));

    // market chips
    root.appendChild(T("div", "obm-section-lbl", "marketFocus"));
    var mkWrap = h("div", "obm-chips", { role: "group" });
    [["us", "mktUs"], ["cn", "mktCn"], ["hk", "mktHk"], ["ca", "mktCa"], ["global", "mktGlobal"]].forEach(function (m) {
      mkWrap.appendChild(chip(m[0], m[1], S.prefs.market_focus));
    });
    root.appendChild(mkWrap);

    // theme thumbnails (REAL — writes localStorage theme immediately)
    root.appendChild(T("div", "obm-section-lbl", "theme"));
    var thWrap = h("div", "obm-thumbs", { role: "group" });
    [["light", "themeLight"], ["dark", "themeDark"], ["auto", "themeAuto"]].forEach(function (th) {
      thWrap.appendChild(thumb(th[0], th[1]));
    });
    root.appendChild(thWrap);
    root.appendChild(T("p", "obm-caption", "themeCaption"));

    // trade chips
    root.appendChild(T("div", "obm-section-lbl", "trade"));
    var trWrap = h("div", "obm-chips", { role: "group" });
    [["stocks", "tradeStocks"], ["options", "tradeOptions"], ["crypto", "tradeCrypto"]].forEach(function (tr) {
      trWrap.appendChild(chip(tr[0], tr[1], S.prefs.trade_types));
    });
    root.appendChild(trWrap);

    footNav({ secondaryKey: null, primaryKey: "continue", onPrimary: onPrefsContinue, dots: true });
    // add the full-width quiet Skip at the left of the footer
    var skip = T("button", "obm-quiet", "skipForNow", { type: "button" });
    skip.style.width = "auto"; skip.addEventListener("click", onPrefsContinue);
    el.foot.insertBefore(skip, el.foot.firstChild);
    return root;
  }
  // A selection may NEVER change a control's box. The check slot is always in
  // the layout (an empty ring when off), and the click updates classes in place
  // instead of re-rendering the step — a full re-render replayed the step's
  // entrance animation and reset the scroll position on every tap, which is
  // exactly what read as "the page stutters".
  function chip(key, lblKey, arr) {
    var on = arr.indexOf(key) !== -1;
    var b = h("button", "obm-chip" + (on ? " obm-on" : ""), { type: "button", "aria-pressed": on ? "true" : "false" });
    b.innerHTML = '<span class="obm-chip-box">' + svgCheck("") + '</span>' +
                  '<span data-k="' + lblKey + '">' + tx(lblKey) + '</span>';
    b.addEventListener("click", function () {
      toggleArr(arr, key);
      var now = arr.indexOf(key) !== -1;
      b.classList.toggle("obm-on", now);
      b.setAttribute("aria-pressed", now ? "true" : "false");
      renderStage(); nudgeIdle(); stashSave();
    });
    return b;
  }
  function thumb(key, lblKey) {
    var on = S.prefs.theme_pref === key;
    var b = h("button", "obm-thumb" + (on ? " obm-on" : ""), { type: "button", "aria-pressed": on ? "true" : "false" });
    b.innerHTML =
      '<span class="obm-thumb-prev obm-' + key + '"><i></i><i></i></span>' +
      '<span class="obm-thumb-foot"><span class="obm-thumb-nm" data-k="' + lblKey + '">' + tx(lblKey) + '</span>' +
      '<span class="obm-radio">' + svgCheck("") + '</span></span>';
    b.addEventListener("click", function () {
      S.prefs.theme_pref = key; applyThemeChoice(key);
      var sibs = b.parentNode ? b.parentNode.querySelectorAll(".obm-thumb") : [];
      for (var i = 0; i < sibs.length; i++) {
        var on2 = sibs[i] === b;
        sibs[i].classList.toggle("obm-on", on2);
        sibs[i].setAttribute("aria-pressed", on2 ? "true" : "false");
      }
      renderStage(); nudgeIdle(); stashSave();   // the stage flips to the picked skin
    });
    return b;
  }
  function toggleArr(arr, k) { var i = arr.indexOf(k); if (i === -1) arr.push(k); else arr.splice(i, 1); }
  // REAL theme write — matches the site's theme boot contract (localStorage theme + themeAuto)
  function applyThemeChoice(pref) {
    try {
      if (pref === "auto") {
        var hh = new Date().getHours(); var tod = (hh >= 7 && hh < 19) ? "light" : "dark";
        localStorage.setItem("themeAuto", "1"); localStorage.setItem("theme", tod);
        document.documentElement.setAttribute("data-theme", tod);
      } else {
        localStorage.removeItem("themeAuto"); localStorage.setItem("theme", pref);
        document.documentElement.setAttribute("data-theme", pref);
      }
    } catch (e) {}
  }
  function onPrefsContinue() {
    persistPrefs();
    go(STEP_PLAN);
  }
  function persistPrefs() {
    var payload = {
      first_name: S.firstName, last_name: S.lastName,
      market_focus: S.prefs.market_focus, trade_types: S.prefs.trade_types,
      theme_pref: S.prefs.theme_pref, onboarded_at: new Date().toISOString()
    };
    if (S.confirmPending) {
      // no session yet — stash to the SAME key the Terminal applies on first sign-in
      try { localStorage.setItem(LS_PENDING_PREFS, JSON.stringify(payload)); } catch (e) {}
      return;
    }
    sbClient().then(function (sb) {
      if (!sb) return;
      sb.auth.getSession().then(function (r) {
        var sess = r && r.data && r.data.session;
        if (sess) { sb.auth.updateUser({ data: payload }).then(null, function () {}); }
        else { try { localStorage.setItem(LS_PENDING_PREFS, JSON.stringify(payload)); } catch (e) {} }
      });
    });
  }

  // ══════════════════════════ STEP 3 — PLAN ══════════════════════════════════
  function viewPlan() {
    var root = h("div", "obm-fade");
    var head = T("h1", "obm-h1", "planTitle"); head.setAttribute("data-ob-heading", ""); head.setAttribute("tabindex", "-1");
    root.appendChild(head);
    root.appendChild(T("p", "obm-sub", "planSub"));

    root.appendChild(periodToggle());

    // plan cards
    var plans = h("div", "obm-plans");
    plans.appendChild(planCard("free"));
    plans.appendChild(planCard("essential"));
    plans.appendChild(planCard("pro"));
    root.appendChild(plans);

    // summary switcher
    var sum = h("div", "obm-summary", { "data-obm-sum": "" });
    fillSummary(sum);
    root.appendChild(sum);

    // compare link — opens the matrix IN PLACE (see openCompare)
    root.appendChild(compareLink());

    planFoot();
    return root;
  }
  // annual ⇄ monthly — shared by the signup plan step and the upgrade lane
  function periodToggle() {
    var tog = h("div", "obm-toggle", { role: "group" });
    var bA = h("button", "", { type: "button", "data-obm-per": "annual", "aria-pressed": S.period === "annual" ? "true" : "false" });
    bA.setAttribute("data-obm-zh", LEX.togAnnual[1]); bA.innerHTML = LEX.togAnnual[0];
    var bM = T("button", "", "togMonthly", { type: "button", "data-obm-per": "monthly", "aria-pressed": S.period === "monthly" ? "true" : "false" });
    bA.addEventListener("click", function () { S.period = "annual"; updatePlanUI(); });
    bM.addEventListener("click", function () { S.period = "monthly"; updatePlanUI(); });
    tog.appendChild(bA); tog.appendChild(bM);
    return tog;
  }
  function compareLink() {
    var cmp = T("button", "obm-link obm-brand-link obm-compare", "compareAll", { type: "button" });
    cmp.addEventListener("click", openCompare);
    return cmp;
  }

  // ══════════════════════ THE COMPARE LAYER ══════════════════════════════════
  // Pressing "Compare every feature" used to CLOSE the sheet and jump the page
  // to #pricing — the visitor was thrown out of their own signup, mid-flow, and
  // had to find their way back. The matrix now opens as a layer over the FORM
  // column: the stage, the stepper and every answer already given stay put, and
  // the tier headers are the picker, so a comparison ends in a decision instead
  // of a scroll position. Back returns to the exact step it opened from.
  var _cmpLastFocus = null;
  function compareCols() { return ["free", "essential", "pro"]; }
  function compareTierPickable(t) {
    // in upgrade mode Free is the plan you already have — readable, not pickable
    return !(S.mode === "upgrade" && t === "free");
  }
  // the same wording the landing's matrix header uses — "$75/mo" alone reads as
  // the monthly price when the toggle is on Annual
  function comparePriceLbl(t) {
    if (t === "free") return "$0";
    return "$" + perMonth(t, S.period) + tx(S.period === "annual" ? "cmpPerAnnual" : "cmpPerMonthly");
  }
  function openCompare() {
    if (S.compare) return;
    S.compare = true;
    S.compareCol = compareTierPickable(S.plan) ? S.plan : "essential";
    _cmpLastFocus = document.activeElement;
    buildCompare();
  }
  function closeCompare() {
    if (!S.compare) return;
    S.compare = false;
    destroyCompare();
    // the plan step is still mounted underneath — repaint the pick in place
    // (never a full re-render: that would replay the step and reset its scroll)
    if (el.body && el.body.querySelector("[data-obm-plan]")) updatePlanUI();
    if (_cmpLastFocus && _cmpLastFocus.focus) { try { _cmpLastFocus.focus(); } catch (e) {} }
  }
  function destroyCompare() {
    if (el.cmp && el.cmp.parentNode) el.cmp.parentNode.removeChild(el.cmp);
    el.cmp = null;
  }
  function buildCompare() {
    if (!el.formPane) return;
    destroyCompare();
    var zh = lang() === "zh";
    var root = h("div", "obm-cmp", { role: "region" });
    if (S.compareCol) root.setAttribute("data-only", S.compareCol);

    // header
    var hd = h("div", "obm-cmp-hd");
    var back = h("button", "obm-back", { type: "button" });
    back.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 18l-6-6 6-6"/></svg><span data-k="cmpBack">' + tx("cmpBack") + '</span>';
    back.addEventListener("click", closeCompare);
    var hTitle = h("h2", "obm-cmp-h", { "data-k": "cmpTitle", tabindex: "-1" });
    hTitle.innerHTML = tx("cmpTitle");
    hd.appendChild(back);
    hd.appendChild(hTitle);
    root.appendChild(hd);

    // phone tab strip — three columns never fit 375px
    var tabs = h("div", "obm-cmp-tabs", { role: "tablist" });
    compareCols().forEach(function (t) {
      var b = h("button", "obm-cmp-tab" + (S.compareCol === t ? " obm-on" : ""), { type: "button", "data-tab": t, role: "tab", "aria-selected": S.compareCol === t ? "true" : "false" });
      b.innerHTML = '<span data-k="' + tierKey(t) + '">' + tx(tierKey(t)) + '</span><i>' + esc(comparePriceLbl(t)) + '</i>';
      b.addEventListener("click", function () { pickCompareCol(t, true); });
      tabs.appendChild(b);
    });
    root.appendChild(tabs);

    // tier header = the picker
    var tiers = h("div", "obm-cmp-tiers");
    var lbl = T("span", "obm-cmp-tiers-lbl", "cmpFeature");
    tiers.appendChild(lbl);
    compareCols().forEach(function (t) {
      var pickable = compareTierPickable(t);
      var b = h("button", "obm-cmp-tier" + (S.plan === t ? " obm-on" : ""), {
        type: "button", "data-tier": t, "aria-pressed": S.plan === t ? "true" : "false"
      });
      if (!pickable) { b.disabled = true; b.style.cursor = "default"; }
      b.innerHTML = '<b data-k="' + tierKey(t) + '">' + tx(tierKey(t)) + '</b>' +
                    '<span>' + esc(pickable ? comparePriceLbl(t) : tx("upCurFree")) + '</span>';
      if (pickable) b.addEventListener("click", function () { pickComparePlan(t); });
      tiers.appendChild(b);
    });
    root.appendChild(tiers);

    // the matrix
    var body = h("div", "obm-cmp-body");
    COMPARE.forEach(function (grp) {
      var g = h("div", "obm-cmp-grp");
      g.setAttribute("data-obm-zh", grp.g[1]);
      g.textContent = zh ? grp.g[1] : grp.g[0];
      body.appendChild(g);
      grp.rows.forEach(function (r) {
        var row = h("div", "obm-cmp-row");
        var ft = h("div", "obm-cmp-ft");
        ft.setAttribute("data-obm-zh", r.l[1]);
        ft.textContent = zh ? r.l[1] : r.l[0];
        row.appendChild(ft);
        compareCols().forEach(function (t, i) {
          row.appendChild(compareCell(r.v[i], t));
        });
        body.appendChild(row);
      });
    });
    root.appendChild(body);

    // footer — the decision, spelled out
    var foot = h("div", "obm-foot");
    foot.appendChild(h("div", "obm-foot-spacer"));
    var done = h("button", "obm-btn", { type: "button", "data-obm-cmp-go": "" });
    done.textContent = comparePickLabel();
    done.addEventListener("click", closeCompare);
    foot.appendChild(done);
    root.appendChild(foot);

    el.formPane.appendChild(root);
    el.cmp = root;
    try { hTitle.focus(); } catch (e) {}
  }
  function tierKey(t) { return t === "free" ? "planFree" : t === "pro" ? "planPro" : "planInsider"; }
  function comparePickLabel() { return escLine(LEX.cmpPick, { "__N__": tx(tierKey(S.plan)) }); }
  function compareCell(v, col) {
    var cell = h("div", "obm-cmp-cell" + (S.plan === col ? " obm-cmp-live" : ""), { "data-col": col });
    if (v === 1) { cell.innerHTML = svgCheck(""); cell.setAttribute("aria-label", "included"); }
    else if (v === 0) { cell.classList.add("obm-cmp-no"); cell.setAttribute("aria-label", "not included"); }
    else if (v === "soon") { cell.innerHTML = '<span class="obm-cmp-soon" data-k="cmpSoon">' + tx("cmpSoon") + '</span>'; }
    else { cell.setAttribute("data-obm-zh", v[1]); cell.textContent = lang() === "zh" ? v[1] : v[0]; }
    return cell;
  }
  // switching the phone column also switches the plan being considered — the
  // footer always names what "Continue" would actually pick.
  function pickCompareCol(t, alsoPick) {
    S.compareCol = t;
    if (el.cmp) el.cmp.setAttribute("data-only", t);
    if (el.cmp) el.cmp.querySelectorAll(".obm-cmp-tab").forEach(function (b) {
      var on = b.getAttribute("data-tab") === t;
      b.classList.toggle("obm-on", on); b.setAttribute("aria-selected", on ? "true" : "false");
    });
    if (alsoPick && compareTierPickable(t)) pickComparePlan(t);
  }
  function pickComparePlan(t) {
    S.plan = t; S.planTouched = true;
    if (S.compareCol && compareTierPickable(t)) pickCompareCol(t, false);
    if (!el.cmp) return;
    el.cmp.querySelectorAll(".obm-cmp-tier").forEach(function (b) {
      var on = b.getAttribute("data-tier") === S.plan;
      b.classList.toggle("obm-on", on); b.setAttribute("aria-pressed", on ? "true" : "false");
      var pr = b.querySelector("span");
      var tt = b.getAttribute("data-tier");
      if (pr && compareTierPickable(tt)) pr.textContent = comparePriceLbl(tt);
    });
    el.cmp.querySelectorAll(".obm-cmp-cell").forEach(function (c) {
      c.classList.toggle("obm-cmp-live", c.getAttribute("data-col") === S.plan);
    });
    var go = el.cmp.querySelector("[data-obm-cmp-go]");
    if (go) go.textContent = comparePickLabel();
    renderStage();      // the lattice behind the layer follows the pick too
    stashSave();
  }
  // footer: back + primary (Free → done, paid → billing). Rebuilt on a plan
  // switch because the step count itself changes (Free skips Billing).
  function planFoot() {
    el.foot.innerHTML = "";
    if (S.mode === "upgrade") { upgradeFoot(); return; }
    footNav({
      back: true, onBack: function () { go(STEP_PREFS); },
      primaryKey: S.plan === "free" ? "contFree" : "contBilling",
      onPrimary: onPlanContinue, dots: true
    });
  }
  // The upgrade lane's footer: no "Back" into an account/preferences step the
  // visitor completed months ago — the only way out is forward or away.
  function upgradeFoot() {
    el.foot.innerHTML = "";
    var quiet = T("button", "obm-quiet", "upNotNow", { type: "button" });
    quiet.style.width = "auto";
    quiet.addEventListener("click", requestClose);
    el.foot.appendChild(quiet);
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    var b = T("button", "obm-btn", "contBilling", { type: "button" });
    b.addEventListener("click", function () { S.upStep = "billing"; render(); stashSave(); });
    el.foot.appendChild(b);
  }
  function priceHtml(key) {
    if (key === "free") return "$0";
    var annual = S.period === "annual";
    var was = annual ? ('<span class="obm-was">$' + annualWas(key) + '</span>') : "";
    var perK = annual ? "perMoAnnual" : "perMo";
    return was + '$' + perMonth(key, S.period) + '<span class="obm-per" data-k="' + perK + '">' + tx(perK) + '</span>';
  }
  function planCard(key) {
    var on = S.plan === key, hot = key === "pro";
    var nmKey = key === "free" ? "planFree" : key === "pro" ? "planPro" : "planInsider";
    var card = h("button", "obm-plan" + (on ? " obm-on" : "") + (hot ? " obm-hot" : ""), { type: "button", "data-obm-plan": key, "aria-pressed": on ? "true" : "false" });
    var left = h("div", "obm-plan-l");
    var nm = h("div", "obm-plan-nm");
    nm.innerHTML = '<span data-k="' + nmKey + '">' + tx(nmKey) + '</span>';
    var who = T("div", "obm-plan-who", key === "free" ? "whoFree" : key === "pro" ? "whoPro" : "whoInsider");
    left.appendChild(nm); left.appendChild(who);
    var right = h("div", "obm-plan-r");
    var price = h("div", "obm-plan-price");
    price.innerHTML = priceHtml(key);
    var radio = h("span", "obm-radio"); radio.innerHTML = svgCheck("");
    right.appendChild(price); right.appendChild(radio);
    card.appendChild(left); card.appendChild(right);
    if (hot) {
      var ribbonKey = offerFor(key, S.period) ? "foundingRibbon" : "ribbon";
      var rb = h("span", "obm-ribbon", { "data-k": ribbonKey });
      rb.textContent = tx(ribbonKey); card.appendChild(rb);
    }
    card.addEventListener("click", function () { if (S.plan === key) return; S.plan = key; updatePlanUI(); });
    return card;
  }
  // Switch plans without rebuilding the step: the cards, the prices, the
  // readout, the footer and the stage all update in place, so the lattice
  // cascade is the only thing that moves.
  function updatePlanUI() {
    S.planTouched = true;
    var cards = el.body.querySelectorAll("[data-obm-plan]");
    for (var i = 0; i < cards.length; i++) {
      var k = cards[i].getAttribute("data-obm-plan"), on = k === S.plan;
      cards[i].classList.toggle("obm-on", on);
      cards[i].setAttribute("aria-pressed", on ? "true" : "false");
      var pr = cards[i].querySelector(".obm-plan-price");
      if (pr) pr.innerHTML = priceHtml(k);
    }
    var pers = el.body.querySelectorAll("[data-obm-per]");
    for (var j = 0; j < pers.length; j++) pers[j].setAttribute("aria-pressed", pers[j].getAttribute("data-obm-per") === S.period ? "true" : "false");
    var sum = el.body.querySelector("[data-obm-sum]");
    if (sum) { sum.innerHTML = ""; fillSummary(sum); }
    planFoot();
    renderSteps();
    applyLang();          // re-paints [data-k] + the stage (cascade + plate chip)
    stashSave();
    syncFootLift();
  }
  function fillSummary(box) {
    function list(items) { var ul = h("ul", "obm-sum-list"); items.forEach(function (k) { var li = h("li"); li.setAttribute("data-obm-zh", LEX[k][1]); li.innerHTML = LEX[k][0]; ul.appendChild(li); }); return ul; }
    if (S.plan === "free") {
      box.appendChild(hd("sumGetFree"));
      box.appendChild(list(["getFree1", "getFree2", "getFree3"]));
      var miss = h("div", "obm-sum-miss");
      miss.appendChild(hdm("sumMissFree"));
      [["missIns1", "obm-ins", "planInsider"], ["missIns2", "obm-ins", "planInsider"], ["missPro1", "obm-pro", "planPro"]].forEach(function (m) {
        var r = h("div", "obm-sum-mrow");
        var chip = h("span", "obm-mchip " + m[1], { "data-k": m[2] }); chip.textContent = tx(m[2]);
        var tspan = h("span"); tspan.setAttribute("data-obm-zh", LEX[m[0]][1]); tspan.innerHTML = LEX[m[0]][0];
        r.appendChild(chip); r.appendChild(tspan); miss.appendChild(r);
      });
      box.appendChild(miss);
    } else if (S.plan === "essential") {
      box.appendChild(hd("sumPlusInsider"));
      box.appendChild(list(["plusIns1", "plusIns2", "plusIns3"]));
      var wedge = h("div", "obm-wedge");
      var wtxt = h("span"); wtxt.setAttribute("data-obm-zh", LEX.wedge[1]); wtxt.innerHTML = LEX.wedge[0];
      var wcta = T("button", "obm-link obm-brand-link obm-wedge-cta", "switchPro", { type: "button" });
      wcta.addEventListener("click", function () { S.plan = "pro"; updatePlanUI(); });
      wedge.appendChild(wtxt); wedge.appendChild(wcta);
      box.appendChild(wedge);
    } else {
      box.appendChild(hd("sumPlusPro"));
      box.appendChild(list(["plusPro1", "plusPro2", "plusPro3"]));
      if (offerFor("pro", S.period)) {
        var ff = T("p", "obm-fineprint", "foundingFine");
        ff.innerHTML = tx("foundingFine").replace("__T__", String(annualBilled("pro")));
        box.appendChild(ff);
      }
      box.appendChild(T("p", "obm-fineprint", "proFine"));
      var soon = h("div", "obm-sum-mrow"); soon.style.marginTop = "8px";
      var mc = h("span", "obm-mchip obm-soon", { "data-k": "mcpSoonTag" }); mc.textContent = tx("mcpSoonTag");
      var ms = T("span", "", "mcpSoon"); ms.style.fontWeight = "600"; ms.style.color = "var(--ink-soft)";
      soon.appendChild(ms); soon.appendChild(mc);
      box.appendChild(soon);
    }
    return box;
    function hd(k) { var p = T("p", "obm-sum-hd", k); return p; }
    function hdm(k) { var p = T("p", "obm-sum-mhd", k); return p; }
  }
  function onPlanContinue() {
    if (S.plan === "free") { S.trialActive = false; S.trialEnd = null; S.subLive = false; go(STEP_DONE); }
    else go(STEP_BILLING);
  }

  // ══════════════════════════ UPGRADE MODE ═══════════════════════════════════
  // The post-login monetization sheet. Same .obm- light-Swiss language as the
  // signup wizard; reuses the plan-price helpers so every figure is COMPUTED.
  // Entered via openSheet('upgrade') (nav "Upgrade", pricing cards, sd dash CTA).

  // /api/me with the Supabase bearer, cached 60s in sessionStorage (shared with
  // the auth-chrome module so a page open costs one fetch). null on any failure.
  function readMeCache() {
    try {
      var raw = sessionStorage.getItem(SS_ME); if (!raw) return null;
      var o = JSON.parse(raw);
      if (o && o.t && (Date.now() - o.t) < ME_TTL && o.me) return normMe(o.me);
    } catch (e) {}
    return null;
  }
  function writeMeCache(me) { try { sessionStorage.setItem(SS_ME, JSON.stringify({ t: Date.now(), me: me })); } catch (e) {} writeMeHint(me); }
  function clearMeCache() { try { sessionStorage.removeItem(SS_ME); } catch (e) {} }
  // A DURABLE signed-in hint (localStorage — survives tab close, unlike the 60s SS cache).
  // Lets the landing paint the CORRECT signed-in chrome INSTANTLY on the next visit: the
  // CTA lands on the right label for the known tier before /api/me round-trips to confirm.
  var LS_ME_HINT = "mm.me.hint";
  function readMeHint() { try { var o = JSON.parse(localStorage.getItem(LS_ME_HINT) || "null"); return (o && o.tier) ? normMe(o) : null; } catch (e) { return null; } }
  function writeMeHint(me) { try { localStorage.setItem(LS_ME_HINT, JSON.stringify({ tier: me.tier || "free", interval: me.interval || null, email: me.email || "" })); } catch (e) {} }
  function clearMeHint() { try { localStorage.removeItem(LS_ME_HINT); } catch (e) {} }
  function fetchMe(force) {
    var cached = force ? null : readMeCache();
    if (cached) return Promise.resolve(cached);
    return getAccessToken().then(function (token) {
      if (!token) return null;
      return fetch(apiBase() + "/api/me", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
        .then(function (r) { if (!r || !r.ok) return null; return r.json().catch(function () { return null; }); })
        .then(function (me) { me = normMe(me); if (me) writeMeCache(me); return me; });
    }).catch(function () { return null; });
  }

  // Open the sheet in upgrade mode. Guests → signin with a pending-upgrade flag.
  function openUpgrade(opts) {
    opts = opts || {};
    if (!opts.me && !hasSessionCookie()) {
      // not signed in → signin first, then continue into the panel (no redirect)
      ensureAssets(); build();
      S.mode = "signin"; S.step = STEP_ACCOUNT;
      S.pendingUpgrade = true; S.upgradeOpts = opts;
      S.open = true; _lastFocus = document.activeElement;
      syncSkin();
      el.scrim.style.display = "flex";
      requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
      document.documentElement.style.overflow = "hidden";
    document.documentElement.classList.add("obm-lock");
      render(); stashSave();
      return;
    }
    enterUpgrade(opts);
  }
  // Signed-in entry: show the sheet, fetch /api/me, render the tier branch.
  function enterUpgrade(opts) {
    opts = opts || {};
    ensureAssets(); build();
    S.mode = "upgrade"; S.step = STEP_PLAN; S.upgradeOpts = opts;
    S.me = null; S.upDone = null; S.upErr = false; S.upStep = "plan"; S.upPre = false; S.compare = false;
    S.open = true; _lastFocus = document.activeElement;
    syncSkin();
    el.scrim.style.display = "flex";
    requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
    document.documentElement.style.overflow = "hidden";
    document.documentElement.classList.add("obm-lock");
    render(); stashSave();
    // A host that already knows the plan may pass opts.me to skip the round-trip.
    if (opts.me) { S.me = opts.me; S.upErr = false; render(); return; }
    fetchMe(false).then(function (me) {
      S.me = me; S.upErr = !me;
      if (S.mode === "upgrade") render();
    });
  }

  // ── the upgrade view (router dispatches here when S.mode === 'upgrade') ──
  function viewUpgrade() {
    var root = h("div", "obm-fade");
    var head = T("h1", "obm-h1", "upTitle"); head.setAttribute("data-ob-heading", ""); head.setAttribute("tabindex", "-1");
    root.appendChild(head);

    // success panel (after a completed upgrade) takes precedence
    if (S.upDone) return upgradeSuccess(root);

    // loading / error before /api/me resolves
    if (!S.me) {
      if (S.upErr) {
        root.appendChild(T("p", "obm-sub", "upErr"));
        var retry = T("button", "obm-btn", "upRetry", { type: "button" }); retry.style.marginTop = "16px";
        retry.addEventListener("click", function () { S.upErr = false; render(); fetchMe(true).then(function (me) { S.me = me; S.upErr = !me; if (S.mode === "upgrade") render(); }); });
        root.appendChild(retry);
      } else {
        var sk = h("div", "obm-bill-skel", { "aria-live": "polite", "aria-busy": "true" });
        sk.innerHTML = '<span class="obm-spin"></span><span class="obm-bill-skel-lbl" data-k="upLoad">' + tx("upLoad") + '</span>';
        root.appendChild(sk);
      }
      return root;
    }

    var tier = normTier(S.me.tier) || "free";
    var interval = S.me.interval || null;

    // free (or no active status) → the upgrade lane's OWN plan → billing steps.
    // It used to hand off to the SIGNUP wizard, which put a signed-in customer
    // back in front of "Create your account" / "Set up your desk" with a Back
    // button into preferences they had already set. Nothing here is a step they
    // have completed: they pick a plan and add a card, and that is the whole lane.
    if (tier === "free") {
      if (!S.upPre) {
        var o = S.upgradeOpts || {};
        var oPlan = normTier(o.plan);
        S.plan = (oPlan === "essential" || oPlan === "pro") ? oPlan : "pro";
        S.period = (o.period === "monthly" || o.period === "annual") ? o.period : "annual";
        S.planTouched = true; S.confirmPending = false;   // signed-in: no email-confirm gate
        S.upPre = true;
      }
      return (S.upStep === "billing") ? viewBilling() : upgradeFreePlan(root);
    }

    // paid tiers → lane cards
    var lanes = upgradeLanes(tier, interval);
    if (!lanes.length) return upgradeBest(root);   // pro-annual / unlimited

    // essential-monthly has the three-lane "switch to annual" story; the single-lane
    // cases (essential-annual, pro-monthly) all point up to Pro Annual.
    var subKey = (tier === "essential" && (interval === "monthly" || !interval)) ? "upToAnnualSub" : "upProAnnualSub";
    root.appendChild(T("p", "obm-sub", subKey));

    var wrap = h("div", "obm-plans obm-up-lanes");
    lanes.forEach(function (ln) { wrap.appendChild(upgradeLaneCard(ln)); });
    root.appendChild(wrap);

    // footer: quiet "Open the dashboard" (never a dead end)
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    var dash = T("button", "obm-quiet", "openDashboard", { type: "button" }); dash.style.width = "auto";
    dash.addEventListener("click", function () { location.href = loginDest(); });
    el.foot.appendChild(dash);
    return root;
  }

  // The free-tier upgrade's plan step: the same cards and the same computed
  // prices as signup, minus every step a signed-in customer already finished.
  function upgradeFreePlan(root) {
    root.appendChild(T("p", "obm-sub", "upFreeSub"));
    root.appendChild(upgradeRail("plan"));
    root.appendChild(periodToggle());

    var plans = h("div", "obm-plans");
    plans.appendChild(planCard("essential"));
    plans.appendChild(planCard("pro"));
    root.appendChild(plans);

    var sum = h("div", "obm-summary", { "data-obm-sum": "" });
    fillSummary(sum);
    root.appendChild(sum);
    root.appendChild(compareLink());

    upgradeFoot();
    return root;
  }
  // the lane's own two-beat rail — never the signup stepper's five
  function upgradeRail(at) {
    var rail = h("div", "obm-up-rail");
    var i1 = h("i", "obm-on"), i2 = h("i", at === "billing" ? "obm-on" : "");
    var lbl = h("span");
    lbl.setAttribute("data-k", at === "billing" ? "stBilling" : "stPlan");
    lbl.textContent = tx(at === "billing" ? "stBilling" : "stPlan");
    rail.appendChild(i1); rail.appendChild(i2); rail.appendChild(lbl);
    return rail;
  }
  // Where "back" and "done" go depends on which lane we are in — the billing
  // step is shared by the signup wizard and the upgrade lane.
  function backFromBilling() {
    if (S.mode === "upgrade") { S.upStep = "plan"; render(); stashSave(); return; }
    go(STEP_PLAN);
  }
  function billingDone() {
    if (S.mode === "upgrade") {
      S.upDone = {
        tier: S.plan, interval: S.period, invoiceCents: null,
        trialing: !!S.trialActive, periodEnd: null, trialEnd: S.trialEnd
      };
      render(); stashSave(); return;
    }
    go(STEP_DONE);
  }
  // the "or continue with Free" escape hatch: in the upgrade lane the visitor
  // ALREADY has Free — the honest action is to leave, not to "choose" it again.
  function freeBailKey() { return S.mode === "upgrade" ? "upNotNow" : "billOrFree"; }
  function bailToFree() {
    if (S.mode === "upgrade") { requestClose(); return; }
    S.plan = "free"; S.trialActive = false; S.trialEnd = null; S.subLive = false; go(STEP_DONE);
  }

  // The lane matrix (upward-only, tier and interval may each rise, never fall).
  function upgradeLanes(tier, interval) {
    tier = normTier(tier);
    var monthly = (interval === "monthly" || !interval);
    if (tier === "essential" && monthly) {
      // Lead with Pro Annual — the recommended, largest-step upgrade (tier + annual),
      // then the alternatives. Order = persuasion order; `popular` drives the ribbon.
      return [
        { tier: "pro", interval: "annual", popular: true },
        { tier: "pro", interval: "monthly" },
        { tier: "essential", interval: "annual" }
      ];
    }
    if (tier === "essential") return [{ tier: "pro", interval: "annual", proPitch: true }];   // essential-annual
    if (tier === "pro" && monthly) return [{ tier: "pro", interval: "annual", proPitch: true }];
    return [];   // pro-annual / unlimited → best-plan panel
  }

  function upgradeLaneCard(ln) {
    var annual = ln.interval === "annual";
    var nmKey = ln.tier === "essential" ? "laneInsAnnual" : (annual ? "laneProAnnual" : "laneProMonthly");
    var whoKey = ln.tier === "essential" ? "laneInsAnnualWho" : (annual ? "laneProAnnualWho" : "laneProMonthlyWho");
    var hue = ln.tier === "pro" ? "var(--ob-pro)" : "var(--ob-essential)";
    var mo = perMonth(ln.tier, ln.interval);
    var card = h("button", "obm-plan obm-up-lane" + (ln.popular ? " obm-hot" : ""), { type: "button" });
    card.style.setProperty("--obm-accent", hue);

    var left = h("div", "obm-plan-l");
    var nm = h("div", "obm-plan-nm");
    nm.innerHTML = '<span data-k="' + nmKey + '">' + tx(nmKey) + '</span>';
    if (annual) {   // computed savings badge (blue-wash chip), never a hardcoded claim
      var pct = savePct(ln.tier);
      var badge = h("span", "obm-up-save");
      badge.setAttribute("data-obm-zh", LEX.laneSave[1].replace("__P__", String(pct)));
      badge.innerHTML = LEX.laneSave[0].replace("__P__", String(pct));
      nm.appendChild(badge);
    }
    left.appendChild(nm);
    left.appendChild(T("div", "obm-plan-who", whoKey));
    // pro-pitch framing line (essential-annual / pro-monthly → pro-annual) — computed
    if (ln.proPitch) {
      var pitch = h("p", "obm-up-pitch");
      var a = annualBilled(ln.tier), m = monthlyPrice(ln.tier) * 12, p = savePct(ln.tier);
      pitch.setAttribute("data-obm-zh", LEX.laneProAnnualPitch[1].replace("__A__", String(a)).replace("__M__", String(m)).replace("__P__", String(p)));
      pitch.innerHTML = LEX.laneProAnnualPitch[0].replace("__A__", String(a)).replace("__M__", String(m)).replace("__P__", String(p));
      left.appendChild(pitch);
    }

    var right = h("div", "obm-plan-r");
    var price = h("div", "obm-plan-price");
      var was = annual ? ('<span class="obm-was">$' + annualWas(ln.tier) + '</span>') : "";
    var perK = annual ? "laneBilledAnnual" : "laneBilledMonthly";
    price.innerHTML = was + '$' + mo + '<span class="obm-per" data-k="' + perK + '">' + tx(perK) + '</span>';
    right.appendChild(price);
    var chev = h("span", "obm-up-chev"); chev.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>';
    right.appendChild(chev);

    card.appendChild(left); card.appendChild(right);
    if (ln.popular || offerFor(ln.tier, ln.interval)) {
      var laneRibbonKey = offerFor(ln.tier, ln.interval) ? "foundingRibbon" : "lanePopular";
      var rb = h("span", "obm-ribbon", { "data-k": laneRibbonKey });
      rb.textContent = tx(laneRibbonKey); card.appendChild(rb);
    }

    // progressive inline confirm (mirror the sd plan block's ARM→CONFIRM pattern)
    var confirm = h("div", "obm-up-confirm");
    var trialing = S.me && S.me.status === "trialing";
    var note = T("p", "obm-up-note", trialing ? "upConfirmTrial" : "upConfirmProrate");
    var goBtn = T("button", "obm-btn", "upConfirmGo", { type: "button" });
    var msg = h("div", "obm-err obm-up-msg"); msg.style.display = "none";
    confirm.appendChild(note); confirm.appendChild(goBtn); confirm.appendChild(msg);
    card.appendChild(confirm);

    card.addEventListener("click", function (e) {
      if (confirm.contains(e.target)) return;               // clicks inside the confirm area don't re-toggle
      var open = card.classList.contains("obm-confirming");
      // single-open: collapse siblings
      var sibs = card.parentNode ? card.parentNode.querySelectorAll(".obm-up-lane.obm-confirming") : [];
      for (var i = 0; i < sibs.length; i++) sibs[i].classList.remove("obm-confirming");
      if (!open) { card.classList.add("obm-confirming"); try { goBtn.focus(); } catch (er) {} }
    });
    goBtn.addEventListener("click", function () { doUpgrade(ln, goBtn, msg); });
    return card;
  }

  // POST /api/billing/upgrade {tier, interval}. 200 → success panel; 402 → Stripe
  // message inline; 409 → refetch /api/me + re-render; 404 → fall back to subscribe.
  function doUpgrade(ln, goBtn, msgBox) {
    function setMsg(m) { if (!msgBox) return; if (!m) { msgBox.style.display = "none"; return; } msgBox.style.display = ""; msgBox.textContent = m; }
    setMsg(""); goBtn.disabled = true; goBtn.textContent = tx("upConfirmGoBusy");
    function reset() { goBtn.disabled = false; goBtn.setAttribute("data-k", "upConfirmGo"); goBtn.innerHTML = tx("upConfirmGo"); }
    getAccessToken().then(function (token) {
      var headers = { "Content-Type": "application/json" };
      if (token) headers["Authorization"] = "Bearer " + token;
      return fetch(apiBase() + "/api/billing/upgrade", {
        method: "POST", credentials: "include", headers: headers,
        body: JSON.stringify({ tier: ln.tier, interval: ln.interval, offer: offerFor(ln.tier, ln.interval) })
      });
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (body) { return { status: r.status, ok: r.ok, body: body }; });
    }).then(function (res) {
      if (res.ok) {
        clearMeCache();
        S.upDone = {
          tier: (res.body && res.body.tier) || ln.tier,
          interval: (res.body && res.body.interval) || ln.interval,
          invoiceCents: (res.body && typeof res.body.invoice_total_cents === "number") ? res.body.invoice_total_cents : null,
          trialing: !!(res.body && res.body.trialing),
          periodEnd: (res.body && res.body.current_period_end) || null
        };
        render();
        return;
      }
      reset();
      if (res.status === 402) {   // card declined — Stripe's own message, don't translate
        setMsg((res.body && (res.body.detail || res.body.message)) || tx("billErr"));
        return;
      }
      if (res.status === 409) {   // not an upward move → refetch + re-render the branch
        fetchMe(true).then(function (me) { S.me = me; S.upDone = null; render(); });
        return;
      }
      if (res.status === 410) {   // founding inventory raced to zero — require a fresh confirmation
        FOUNDING_PRO.active = false;
        render();
        return;
      }
      if (res.status === 404) {   // no Stripe sub (comp'd) → subscribe lane preselecting the target
        S.planTouched = true; S.confirmPending = false;
        S.plan = ln.tier; S.period = ln.interval;
        S.upStep = "billing"; S.upPre = true; render();
        return;
      }
      setMsg(tx("billErr"));
    }).catch(function () { reset(); setMsg(tx("billErr")); });
  }

  function upgradeSuccess(root) {
    var d = S.upDone;
    var wrap = h("div", "obm-done");
    var mark = h("div", "obm-done-mark"); mark.innerHTML = svgCheck("");
    var head = h("h1", "obm-h1", { "data-ob-heading": "", tabindex: "-1" }); head.style.margin = "0";
    head.setAttribute("data-k", "upDoneH"); head.textContent = tx("upDoneH");
    var body = h("div", "obm-done-body");
    var intLbl = d.interval === "annual" ? (lang() === "zh" ? "年付" : "Annual") : (lang() === "zh" ? "月付" : "Monthly");
    var planNm = tx(d.tier === "pro" ? "planPro" : "planInsider") + " · " + intLbl;
    var l1 = h("p", "obm-done-line"); l1.innerHTML = escLine(LEX.upDonePlan, { "__N__": esc(planNm) }); body.appendChild(l1);
    // a free → paid upgrade lands on a trial: say when the first charge is,
    // in the same words the signup lane uses
    if (d.trialing && d.trialEnd) {
      var lt = h("p", "obm-done-line");
      lt.innerHTML = escLine(LEX.doneTrial, { "__T__": esc(tx(d.tier === "pro" ? "planPro" : "planInsider")), "__D__": esc(fmtDate(new Date(d.trialEnd * 1000))) });
      body.appendChild(lt);
    }
    // amount actually invoiced today — omit when trialing / zero
    if (!d.trialing && d.invoiceCents && d.invoiceCents > 0) {
      var l2 = h("p", "obm-done-line"); l2.innerHTML = escLine(LEX.upDoneCharged, { "__T__": esc(fmtMoney(d.invoiceCents)) }); body.appendChild(l2);
    }
    if (d.periodEnd) {
      var l3 = h("p", "obm-done-line"); l3.innerHTML = escLine(LEX.upDoneRenew, { "__D__": esc(fmtDate(new Date(d.periodEnd))) }); body.appendChild(l3);
    }
    wrap.appendChild(mark); wrap.appendChild(head); wrap.appendChild(body);
    root.appendChild(wrap);
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    var dash = T("button", "obm-btn", "openDashboard", { type: "button" });
    dash.addEventListener("click", function () { location.href = loginDest(); });
    el.foot.appendChild(dash);
    return root;
  }
  function fmtMoney(cents) { var n = cents / 100; return (n % 1 === 0) ? String(n) : n.toFixed(2); }

  function upgradeBest(root) {
    var wrap = h("div", "obm-done obm-up-best");
    var mark = h("div", "obm-done-mark obm-up-best-mark"); mark.innerHTML = svgCheck("");
    var head = h("h1", "obm-h1", { "data-ob-heading": "", tabindex: "-1" }); head.style.margin = "0";
    head.setAttribute("data-k", "upBestH"); head.textContent = tx("upBestH");
    var body = h("div", "obm-done-body");
    body.appendChild(T("p", "obm-done-line", "upBestS"));
    wrap.appendChild(mark); wrap.appendChild(head); wrap.appendChild(body);
    root.appendChild(wrap);
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    var dash = T("button", "obm-btn", "openDashboard", { type: "button" });
    dash.addEventListener("click", function () { location.href = loginDest(); });
    el.foot.appendChild(dash);
    return root;
  }

  // ══════════════════════════ STEP 4 — BILLING ═══════════════════════════════
  var _stripe = null, _elements = null;
  function viewBilling() {
    var root = h("div", "obm-fade");
    var head = T("h1", "obm-h1", "billTitle"); head.setAttribute("data-ob-heading", ""); head.setAttribute("tabindex", "-1");
    root.appendChild(head);

    // confirm-email-first blocker (rare: confirmation ON + paid, no session)
    if (S.confirmPending) {
      var blk = h("div", "obm-bill-state");
      blk.appendChild(T("p", "obm-bill-state-msg", "billConfirmFirst"));
      var cg = T("button", "obm-btn", "billConfirmGo", { type: "button" }); cg.style.width = "auto"; cg.style.margin = "0 auto";
      cg.addEventListener("click", billingDone);
      blk.appendChild(cg);
      root.appendChild(blk);
      footNav({ back: true, onBack: backFromBilling, dots: S.mode !== "upgrade" });
      return root;
    }

    root.appendChild(T("p", "obm-sub", planHasTrial(S.plan) ? "billSub" : "billSubNoTrial"));
    if (S.mode === "upgrade") root.appendChild(upgradeRail("billing"));
    root.appendChild(orderCard());
    var host = h("div", "", { "data-obm-billhost": "" });
    root.appendChild(host);
    footNav({ back: true, onBack: backFromBilling, dots: S.mode !== "upgrade" });

    // kick off async init
    initBilling(host);
    return root;
  }
  function orderCard() {
    var tier = S.plan, annual = S.period === "annual";
    var hue = tier === "pro" ? "var(--ob-pro)" : "var(--ob-essential)";
    var mo = perMonth(tier, S.period), total = firstInvoiceTotal(tier, S.period);
    var date = fmtDate(trialChargeDate());
    var trial = planHasTrial(tier);
    var card = h("div", "obm-order"); card.style.setProperty("--obm-accent", hue);
    var billed = trial ? (annual ? LEX.billBilledAnnually : LEX.billBilledMonthly)
                       : (annual ? LEX.billBilledAnnuallyNow : LEX.billBilledMonthlyNow);
    var billedEn = billed[0].replace("__T__", String(annualBilled(tier)));
    var billedZh = billed[1].replace("__T__", String(annualBilled(tier)));
    var truth = trial ? LEX.billTrialLine : LEX.billChargeLine;
    var trialEn = truth[0].replace("__T__", String(total)).replace("__D__", date);
    var trialZh = truth[1].replace("__T__", String(total)).replace("__D__", date);
    card.innerHTML =
      '<div class="obm-order-hd"><span class="obm-order-dot"></span>' +
      '<span class="obm-order-nm" data-k="' + (tier === "pro" ? "planPro" : "planInsider") + '">' + tx(tier === "pro" ? "planPro" : "planInsider") + '</span>' +
      '<span class="obm-order-price">$' + mo + '<span class="obm-order-per" data-k="billPerMo">' + tx("billPerMo") + '</span></span></div>' +
      '<div class="obm-order-billed" data-obm-zh="' + esc(billedZh) + '">' + billedEn + '</div>' +
      '<div class="obm-order-truth">' +
      '<p class="obm-order-trial" data-obm-zh="' + esc(trialZh) + '">' + trialEn + '</p>' +
      '<p class="obm-order-cancel" data-k="' + (trial ? "billCancelLine" : "billCancelAnytime") + '">' +
      tx(trial ? "billCancelLine" : "billCancelAnytime") + '</p>' +
      (offerFor(tier, S.period)
        ? '<p class="obm-order-cancel" data-obm-zh="' +
          esc(LEX.foundingFine[1].replace("__T__", String(annualBilled(tier)))) + '">' +
          LEX.foundingFine[0].replace("__T__", String(annualBilled(tier))) + '</p>'
        : '') + '</div>';
    return card;
  }
  function payKey() { return planHasTrial(S.plan) ? "billSubmit" : "billSubmitNow"; }
  function trialChargeDate() { var d = new Date(); d.setDate(d.getDate() + TRIAL_DAYS); return d; }
  function fmtDate(d) { try { return d.toLocaleDateString(lang() === "zh" ? "zh-CN" : "en-US", { month: "long", day: "numeric" }); } catch (e) { return d.toDateString(); } }

  function billState(host, html) { host.innerHTML = '<div class="obm-bill-state">' + html + '</div>'; applyLang(); }
  function initBilling(host) {
    host.innerHTML = '<div class="obm-bill-skel" aria-live="polite" aria-busy="true"><span class="obm-spin"></span><span class="obm-bill-skel-lbl" data-k="billLoading">' + tx("billLoading") + '</span></div>';
    var tier = S.plan, period = S.period;
    var token = null;
    getAccessToken().then(function (t) {
      token = t;
      return fetch(apiBase() + "/api/billing/config", { cache: "no-store", credentials: "include" });
    }).then(function (cfgRes) {
      if (cfgRes.status === 503) { return billNotConfigured(host); }
      if (!cfgRes.ok) { return billError(host); }
      return cfgRes.json().catch(function () { return {}; }).then(function (cfg) {
        var pk = cfg && typeof cfg.publishable_key === "string" ? cfg.publishable_key : "";
        if (!pk) { return billNotConfigured(host); }
        var headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = "Bearer " + token;
        return fetch(apiBase() + "/api/billing/subscribe/init", {
          method: "POST", credentials: "include", headers: headers,
          body: JSON.stringify({ tier: tier, interval: period, offer: offerFor(tier, period) })
        }).then(function (initRes) {
          if (initRes.status === 409) { return billAlready(host); }
          if (initRes.status === 410) {
            FOUNDING_PRO.active = false;
            render(); return;
          }
          if (initRes.status === 401) { return billState(host, '<p class="obm-bill-state-msg" data-k="billSignin">' + tx("billSignin") + '</p>'); }
          if (!initRes.ok) { return billError(host); }
          return initRes.json().catch(function () { return {}; }).then(function (data) {
            var cs = data && typeof data.client_secret === "string" ? data.client_secret : "";
            if (!cs) { return billError(host); }
            return loadStripe(pk).then(function (stripe) {
              if (!stripe) { return billError(host); }
              mountPaymentForm(host, stripe, cs, tier, period);
            });
          });
        });
      });
    }).catch(function () { billError(host); });
  }
  function billError(host) {
    billState(host, '<p class="obm-bill-state-msg" data-k="billErr">' + tx("billErr") + '</p><button type="button" class="obm-btn" data-obm-retry style="width:auto;margin:0 auto"><span data-k="billRetry">' + tx("billRetry") + '</span></button><button type="button" class="obm-quiet" data-obm-payfree style="margin-top:12px"><span data-k="' + freeBailKey() + '">' + tx(freeBailKey()) + '</span></button>');
    var r = host.querySelector("[data-obm-retry]"); if (r) r.addEventListener("click", function () { initBilling(host); });
    var f = host.querySelector("[data-obm-payfree]"); if (f) f.addEventListener("click", bailToFree);
  }
  function billNotConfigured(host) {
    billState(host, '<p class="obm-bill-state-msg" data-k="billNotConfigured">' + tx("billNotConfigured") + '</p><a class="obm-link obm-brand-link" href="' + PLANS_HTML + '" target="_blank" rel="noopener noreferrer"><span data-k="billPlansLink">' + tx("billPlansLink") + '</span> →</a>');
  }
  function billAlready(host) {
    billState(host, '<div class="obm-bill-state-hd" data-k="billAlready">' + tx("billAlready") + '</div><p class="obm-bill-state-msg" data-k="billAlreadySub">' + tx("billAlreadySub") + '</p><button type="button" class="obm-btn" data-obm-already style="width:auto;margin:0 auto"><span data-k="billAlreadyGo">' + tx("billAlreadyGo") + '</span></button>');
    var b = host.querySelector("[data-obm-already]"); if (b) b.addEventListener("click", function () { S.trialActive = false; S.subLive = false; billingDone(); });
  }
  function getAccessToken() {
    return sbClient().then(function (sb) {
      if (!sb) return null;
      return sb.auth.getSession().then(function (r) { var s = r && r.data && r.data.session; return s ? s.access_token : null; }).catch(function () { return null; });
    }).catch(function () { return null; });
  }
  function loadStripe(pk) {
    return injectStripeJs().then(function () {
      if (!window.Stripe) return null;
      return window.Stripe(pk);
    });
  }
  var _stripeJs = null;
  function injectStripeJs() {
    if (window.Stripe) return Promise.resolve();
    if (_stripeJs) return _stripeJs;
    _stripeJs = new Promise(function (resolve) {
      var s = document.createElement("script"); s.src = STRIPE_JS; s.async = true;
      s.onload = resolve; s.onerror = function () { resolve(); };
      (document.head || document.documentElement).appendChild(s);
    });
    return _stripeJs;
  }
  function mountPaymentForm(host, stripe, clientSecret, tier, period) {
    // Stripe paints inside an iframe our CSS cannot reach — hand it the sheet's
    // own skin, or the card form lands as a white slab in a dark sheet.
    var dark = hostSkin() === "dark";
    var appearance = dark ? {
      theme: "night",
      variables: {
        colorPrimary: "#5b8cff", colorText: "#e9eef8", colorBackground: "#141b2b",
        colorTextSecondary: "#93a1b8", colorTextPlaceholder: "#6f7e98", colorDanger: "#ff7b7b",
        borderRadius: "10px", fontFamily: "Inter, system-ui, sans-serif"
      }
    } : {
      theme: "stripe",
      variables: { colorPrimary: "#285fff", colorText: "#1c2430", colorBackground: "#ffffff", borderRadius: "10px", fontFamily: "Inter, system-ui, sans-serif" }
    };
    var elements = stripe.elements({ clientSecret: clientSecret, appearance: appearance });
    _stripe = stripe; _elements = elements;
    host.innerHTML =
      '<form class="obm-bill-form" data-obm-payform>' +
      '<div class="obm-bill-el" data-obm-payel></div>' +
      '<div class="obm-err" data-obm-payerr style="display:none"></div>' +
      '<button type="submit" class="obm-btn" data-obm-paysubmit disabled style="margin-top:14px"><span data-k="' + payKey() + '">' + tx(payKey()) + '</span></button>' +
      '<button type="button" class="obm-quiet" data-obm-payfree style="margin-top:12px"><span data-k="' + freeBailKey() + '">' + tx(freeBailKey()) + '</span></button>' +
      '</form>';
    var payEl = elements.create("payment");
    payEl.mount(host.querySelector("[data-obm-payel]"));
    var submitBtn = host.querySelector("[data-obm-paysubmit]");
    payEl.on("ready", function () { submitBtn.disabled = false; });
    host.querySelector("[data-obm-payfree]").addEventListener("click", bailToFree);
    host.querySelector("[data-obm-payform]").addEventListener("submit", function (e) {
      e.preventDefault(); onPaySubmit(host, tier, period);
    });
  }
  function onPaySubmit(host, tier, period) {
    if (!_stripe || !_elements) return;
    var submitBtn = host.querySelector("[data-obm-paysubmit]");
    var errBox = host.querySelector("[data-obm-payerr]");
    function setPayErr(m) { if (!errBox) return; if (!m) { errBox.style.display = "none"; return; } errBox.style.display = ""; errBox.textContent = m; }
    submitBtn.disabled = true; submitBtn.textContent = tx(planHasTrial(S.plan) ? "billSubmitBusy" : "billSubmitNowBusy"); setPayErr("");
    _stripe.confirmSetup({ elements: _elements, redirect: "if_required" }).then(function (res) {
      if (res.error) {
        // Stripe's own message (declines etc.) — do NOT translate
        setPayErr(res.error.message || tx("billErr"));
        submitBtn.disabled = false; submitBtn.setAttribute("data-k", payKey()); submitBtn.innerHTML = tx(payKey());
        return;
      }
      var si = res.setupIntent;
      if (!si || !si.id) { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx(payKey()); return; }
      getAccessToken().then(function (token) {
        var headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = "Bearer " + token;
        return fetch(apiBase() + "/api/billing/subscribe/complete", {
          method: "POST", credentials: "include", headers: headers,
          body: JSON.stringify({ setup_intent_id: si.id, tier: tier, interval: period, offer: offerFor(tier, period) })
        });
      }).then(function (r) {
        if (r.status === 410) { FOUNDING_PRO.active = false; render(); return; }
        if (!r.ok) { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx(payKey()); return; }
        return r.json().catch(function () { return {}; }).then(function (data) {
          // trial_end comes back null for a plan the spine created with no trial —
          // that is the ONLY thing allowed to make the Done step say "trial".
          S.trialEnd = (data && typeof data.trial_end === "number") ? data.trial_end : null;
          S.trialActive = S.trialEnd != null;
          S.subLive = true;
          billingDone();
        });
      }).catch(function () { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx(payKey()); });
    });
  }

  // ══════════════════════════ STEP 5 — DONE ══════════════════════════════════
  function viewDone() {
    var root = h("div", "obm-fade");
    var wrap = h("div", "obm-done");
    var mark = h("div", "obm-done-mark"); mark.innerHTML = svgCheck("");
    var name = (S.firstName || (fullNameFromMeta().split(" ")[0]) || "").trim();
    var head = h("h1", "obm-h1", { "data-ob-heading": "", tabindex: "-1" }); head.style.margin = "0";
    head.textContent = name ? tx("doneTitleNamed").replace("__N__", name) : tx("doneTitle");
    var bodyBox = h("div", "obm-done-body");
    if (S.confirmPending) { var l1 = h("p", "obm-done-line"); l1.innerHTML = escLine(LEX.doneConfirm, { "__E__": esc(S.email || (lang() === "zh" ? "你的邮箱" : "your inbox")) }); bodyBox.appendChild(l1); }
    if (S.trialActive || S.subLive) {
      var tierNm = tx(S.plan === "pro" ? "planPro" : "planInsider");
      var l2 = h("p", "obm-done-line");
      l2.innerHTML = S.trialActive
        ? escLine(LEX.doneTrial, { "__T__": esc(tierNm), "__D__": esc(fmtDate(doneTrialDate())) })
        : escLine(LEX.doneSubscribed, { "__T__": esc(tierNm) });
      bodyBox.appendChild(l2);
    }
    if (!S.confirmPending && !S.trialActive && !S.subLive) { bodyBox.appendChild(T("p", "obm-done-line", "doneReady")); }
    wrap.appendChild(mark); wrap.appendChild(head); wrap.appendChild(bodyBox);
    root.appendChild(wrap);

    // footer: primary "Open the dashboard" (closes) + quiet "Open the Terminal →"
    el.foot.appendChild(h("div", "obm-foot-spacer"));
    var term = T("button", "obm-quiet", "openTerminal", { type: "button" }); term.style.width = "auto";
    term.addEventListener("click", function () { window.open(TERMINAL_URL, "_blank", "noopener"); });
    el.foot.appendChild(term);
    var dash = T("button", "obm-btn", "openDashboard", { type: "button" });
    dash.addEventListener("click", function () {
      stashClear();
      location.href = loginDest();   // ?ret wall target, else start.html
    });
    el.foot.appendChild(dash);
    return root;
  }
  function doneTrialDate() { if (S.trialEnd != null) return new Date(S.trialEnd * 1000); return trialChargeDate(); }
  function fullNameFromMeta() { try { var u = window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user(); return (u && u.user_metadata && (u.user_metadata.full_name || u.user_metadata.name)) || ""; } catch (e) { return ""; } }
  function escLine(tuple, subs) { var en = tuple[0], zh = tuple[1]; var s = lang() === "zh" ? zh : en; for (var k in subs) if (subs.hasOwnProperty(k)) s = s.split(k).join(subs[k]); return s; }
  function esc(s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }

  // ══════════════════════════ open / close ═══════════════════════════════════
  // The sheet is SITE-WIDE: theme.js lazy-loads onboard.js on any www page when an
  // auth entry is clicked. Such pages have neither onboard.css nor the landing's
  // display fonts — self-provision both, idempotently, before first build.
  // Site-root prefix, derived from our OWN (or theme.js's) <script src> — correct
  // at ANY depth and under subpath hosting. The old "/sectors/"-only check made
  // every other one-level-deep page (/learn/, /tools/, /stocks/, /blog/) request
  // `<dir>/onboard.css`, which 404s: the sheet opened completely unstyled there,
  // and loginDest() pointed at `<dir>/start.html`. Same technique theme.js already
  // uses for its watchlist link.
  function _pfx() {
    try {
      var s = document.querySelector('script[src$="onboard.js"],script[src*="onboard.js?"],script[src$="theme.js"],script[src*="theme.js?"]');
      if (s) {
        var src = s.getAttribute("src") || "";
        var pfx = src.replace(/(?:onboard|theme)\.js(?:\?.*)?$/, "");
        if (pfx !== src) return pfx;
      }
    } catch (e) {}
    return location.pathname.indexOf("/sectors/") > -1 ? "../" : "";
  }
  function ensureAssets() {
    if (!document.querySelector('link[href*="onboard.css"]')) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = _pfx() + "onboard.css";
      document.head.appendChild(l);
    }
    // No font <link> is injected any more. Archivo used to be pulled from
    // fonts.googleapis.com here, which is blocked in mainland China — so on every
    // page that opens the sheet, Chinese visitors got no display face at all and
    // the sheet quietly rendered in system sans. The face now travels WITH the
    // stylesheet above: onboard.css carries a self-hosted @font-face whose url()
    // resolves relative to itself, so wherever the sheet is injected from, the
    // font arrives with it. One variable file still serves both widths — the
    // wdth axis is preserved, so font-stretch:125% instances the display width
    // exactly as the CDN build did. Inter needs nothing here either: pages that
    // inject the sheet all link theme.css, which self-hosts it.
  }
  var _lastFocus = null;
  function openSheet(mode, opts) {
    if (mode === "upgrade") { openUpgrade(opts || {}); return; }
    ensureAssets();
    // Warm the Supabase broker + SDK the instant the sheet opens, so the first
    // Sign in / Create account click pays ONLY the auth network call — not a cold
    // theme.js -> supabase.js (SDK) -> createClient chain (the landing preloads
    // neither). Fire-and-forget; sbClient()/getSupabaseClient() cache their work,
    // so this is idempotent and the later submit reuses the same warm client.
    sbClient().catch(function () {});
    build();
    S.mode = mode || "signup";
    var optPlan = opts ? normTier(opts.plan) : "";
    if (optPlan === "free" || optPlan === "essential" || optPlan === "pro") S.plan = optPlan;
    if (opts && opts.period && (opts.period === "monthly" || opts.period === "annual")) S.period = opts.period;
    if (opts && opts.resume) S.step = STEP_PREFS;
    if (S.mode === "signin") S.step = STEP_ACCOUNT;
    S.open = true; S.compare = false;
    _lastFocus = document.activeElement;
    syncSkin();
    el.scrim.style.display = "flex";
    // next frame → transition in
    requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
    document.documentElement.style.overflow = "hidden";
    document.documentElement.classList.add("obm-lock");
    render();
    redrawDesk();
    nudgeIdle();
    stashSave();
  }
  // Post-login landing: the ?ret= share/deep-link target if the registration
  // wall (app/regwall.py) set one, else the signed-in HOME hub at the site root.
  // Keep the fallback root-relative: a relative "start.html" from a product page
  // resolves to /products/start.html and strands the customer after checkout.
  // Now that the SEO estate
  // (/stocks/, /tools/, /learn/, /blog/) is public, the wall only fires on
  // genuinely gated pages — so returning a visitor to the exact page they were
  // sent or shared is the right call. A generic sign-in (no ret) lands on the
  // fast hub, never the marketing landing. Same-origin "/…" paths only — never
  // navigate off-origin from a query param.
  function retTarget() {
    try {
      var p = new URLSearchParams(location.search).get("ret");
      if (p && p.charAt(0) === "/" && p.slice(0, 2) !== "//") return p;
    } catch (e) { /* ignore */ }
    return "";
  }
  function loginDest() { return retTarget() || "/start.html"; }
  // ── Silent wall-resume (sticky login) ───────────────────────────────────────
  // The registration wall (app/regwall.py) verifies the ~1-hour ACCESS token
  // server-side, but the ~390-day session cookie also carries a REFRESH token the
  // wall cannot use. A returning signed-in visitor therefore bounces here with
  // ?signin=1&ret=… holding a perfectly renewable session. Prompting them to log
  // in again is wrong: getSession() transparently refreshes the expired session
  // (rewriting the rotated cookie via theme.js COOKIE_STORAGE), after which the
  // wall passes. So: cookie present → refresh silently → return to the gated
  // page; open the sheet ONLY when the refresh truly fails (revoked/dead session).
  // Loop guard: if the wall bounced us back to the SAME destination within 45s
  // (e.g. auth upstream down → wall fails closed no matter how fresh the token),
  // stop trampolining and show the sheet instead of ping-ponging forever.
  var WALL_HOP_KEY = "obmWallHop";
  function wallHopLooping(dest) {
    try {
      var h = JSON.parse(sessionStorage.getItem(WALL_HOP_KEY) || "null");
      return !!h && h.d === dest && (Date.now() - h.t) < 45000;
    } catch (e) { return false; }
  }
  function markWallHop(dest) {
    try { sessionStorage.setItem(WALL_HOP_KEY, JSON.stringify({ d: dest, t: Date.now() })); } catch (e) {}
  }
  function silentWallResume() {
    var dest = loginDest();
    var settled = false;
    // Fallback: slow/blocked auth upstream (the GFW /sb proxy path can take
    // ~15s) — after 8s stop waiting and show the sheet so the visitor is never
    // stranded on a bare landing.
    var fallback = setTimeout(function () {
      if (settled) return;
      settled = true;
      openSheet("signin", {}); stripOnboardParams();
    }, 8000);
    getAccessToken().then(function (token) {
      if (settled) {
        // Late refresh success while the sheet sits untouched → still honor it.
        if (token && S.open && S.mode === "signin" && !S.email && !S.password) {
          markWallHop(dest); location.replace(dest);
        }
        return;
      }
      settled = true; clearTimeout(fallback);
      if (token) { markWallHop(dest); location.replace(dest); }
      else { openSheet("signin", {}); stripOnboardParams(); }
    }).catch(function () {
      if (settled) return;
      settled = true; clearTimeout(fallback);
      openSheet("signin", {}); stripOnboardParams();
    });
  }
  function closeSheet() {
    if (!el.scrim) return;
    S.open = false; S.compare = false; destroyCompare();
    el.scrim.classList.remove("obm-open");
    parkStage(true);                       // nothing animates behind a closed sheet
    if (_idleTimer) { clearTimeout(_idleTimer); _idleTimer = null; }
    document.documentElement.style.overflow = "";
    document.documentElement.classList.remove("obm-lock");
    // keep stash unless cleared by Done; hide after transition
    setTimeout(function () { if (!S.open) el.scrim.style.display = "none"; }, 220);
    if (_lastFocus && _lastFocus.focus) { try { _lastFocus.focus(); } catch (e) {} }
    stashSave();
  }
  function requestClose() { closeSheet(); }

  // ESC + focus trap
  document.addEventListener("keydown", function (e) {
    if (!S.open || !el.sheet) return;
    // ESC peels ONE layer: the compare panel first, the sheet only once it's gone
    if (e.key === "Escape") { e.preventDefault(); if (S.compare) closeCompare(); else requestClose(); return; }
    if (e.key === "Tab") trapTab(e);
  });
  function trapTab(e) {
    var f = el.sheet.querySelectorAll('a[href],button:not([disabled]),input:not([disabled]),select,textarea,[tabindex]:not([tabindex="-1"])');
    var list = []; for (var i = 0; i < f.length; i++) if (f[i].offsetParent !== null || f[i] === document.activeElement) list.push(f[i]);
    if (!list.length) return;
    var first = list[0], last = list[list.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ══════════════════════════ CTA interception ═══════════════════════════════
  // Parse ?signin/?signup/?plan/?period from an href or a query string.
  function parseIntent(qs) {
    var sp;
    try { sp = new URLSearchParams(qs); } catch (e) { sp = null; }
    if (!sp) return null;
    var wantSignup = sp.has("signup") || sp.has("onboard") || sp.has("plan");
    var wantSignin = sp.has("signin");
    if (!wantSignup && !wantSignin) return null;
    var plan = normTier(sp.get("plan")), period = sp.get("period");
    return {
      mode: (wantSignin && !wantSignup) ? "signin" : "signup",
      plan: (plan === "essential" || plan === "pro" || plan === "free") ? plan : null,
      period: (period === "monthly" || period === "annual") ? period : null,
      resume: sp.get("onboard") === "resume"
    };
  }
  // delegated listener: intercept CTA <a> to app.mastermind-x.com/terminal?sign…
  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest('a[href*="app.mastermind-x.com/terminal?sign"]') : null;
    if (!a) return;
    var href = a.getAttribute("href") || "";
    var qIdx = href.indexOf("?");
    var intent = qIdx === -1 ? null : parseIntent(href.slice(qIdx + 1));
    if (!intent) return;                       // not an onboarding link → let it navigate
    e.preventDefault();
    // Auth-aware: a signed-in user (cached /api/me) clicking a plan/signup link
    // wants to UPGRADE, not sign up again — route plan-carrying clicks to upgrade.
    var me = readMeCache();
    if (me && ((me.tier || "free") !== "free" || intent.mode === "signup")) {
      openSheet("upgrade", { plan: intent.plan, period: intent.period });
      return;
    }
    openSheet(intent.mode, { plan: intent.plan, period: intent.period, resume: intent.resume });
  }, true);

  // ══════════════════════════ LANDING AUTH CHROME ════════════════════════════
  // Auth-aware header + gear ACCOUNT wiring for the LANDING only. Every function
  // here no-ops when the landing's ids are absent (so it costs nothing on macro
  // pages, which never hit this file's landing branch). Guests pay zero network:
  // the cheap cookie sniff gates the /api/me fetch entirely.
  var UPCHROME = {
    upgrade: ["Upgrade", "升级"],
    upgradeAnnual: ["Upgrade to Annual", "升级为年付"],
    openDash: ["Open the dashboard", "打开仪表盘"],
    included: ["Included", "已包含"],
    current: ["Current plan", "当前方案"],
    yourPlan: ["Your plan", "当前方案"]
  };
  function _byId(id) { return document.getElementById(id); }
  var _navSnap = null;   // signed-out nav-cta snapshot, so a dead session can be reverted exactly
  var _planSnap = null;  // signed-out pricing-CTA snapshots (label/href/period), same purpose

  // Wire the gear ACCOUNT buttons — independent of auth state, so signed-out
  // visitors can sign in / create an account straight from the gear.
  function wireGearAccount() {
    var si = _byId("gp-signin"), su = _byId("gp-signup");
    var card = _byId("gp-acct-card"), so = _byId("gp-signout");
    if (si && !si.__wired) { si.__wired = true; si.addEventListener("click", function () { closeGearPop(); openSheet("signin", {}); }); }
    if (su && !su.__wired) { su.__wired = true; su.addEventListener("click", function () { closeGearPop(); openSheet("signup", {}); }); }
    if (card && !card.__wired) {
      card.__wired = true;
      var openMgr = function () { closeGearPop(); openSettingsDash(); };
      card.addEventListener("click", openMgr);
      card.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); openMgr(); } });
    }
    if (so && !so.__wired) {
      so.__wired = true;
      so.addEventListener("click", function () {
        ensureAuthBroker().then(function (auth) {
          clearMeCache();
          if (auth && auth.signOut) { auth.signOut().then(function () { location.reload(); }, function () { location.reload(); }); }
          else location.reload();
        });
      });
    }
  }
  function closeGearPop() { var p = _byId("gear-pop"), b = _byId("gear-btn"); if (p) p.classList.remove("open"); if (b) b.setAttribute("aria-expanded", "false"); }
  // open the personal settings dashboard (theme.js sd-* modal) — lazy-load theme.js
  function openSettingsDash() {
    if (window.MMSettings && window.MMSettings.open) { window.MMSettings.open("account"); return; }
    ensureAuthBroker().then(function () {
      if (window.MMSettings && window.MMSettings.open) window.MMSettings.open("account");
    });
  }

  // Apply the signed-in header chrome from an /api/me payload.
  function applyAuthChrome(me) {
    if (!me) return;
    snapshotPlanCtas();                        // idempotent; MMOnboard.applyChrome may arrive first
    var tier = normTier(me.tier) || "free";
    var interval = me.interval || null;
    // Lifetime/comp grants carry interval null — they hold the top plan and must never
    // be nav-upsold (mirrors the proTop predicate on the pricing cards below).
    var best = (tier === "unlimited") || (tier === "pro" && interval !== "monthly");
    var start = "/start.html";

    // 1) hide the nav "Log in"
    var login = _byId("nav-login"); if (login) { login.hidden = true; login.style.display = "none"; }

    // 2) nav CTA → best plan = "Open the dashboard"→start.html; else "Upgrade"→sheet
    var cta = _byId("nav-cta");
    if (cta) {
      if (best) { setChromeLabel(cta, "openDash"); cta.setAttribute("href", start); cta.__upgrade = false; }
      else { setChromeLabel(cta, "upgrade"); cta.setAttribute("href", start); cta.__upgrade = true; }
      bindChromeCta(cta);
    }

    // 3) hero + closing "Start free" → "Open the dashboard" → start.html (never "Start free" for a signed-in user)
    var sf = document.querySelectorAll(".js-startfree");
    for (var i = 0; i < sf.length; i++) {
      var b = sf[i];
      setChromeLabel(b, "openDash"); b.setAttribute("href", start);
      b.classList.remove("js-startfree"); b.classList.add("js-startfree-done");
    }

    // 4) pricing-card CTAs — ENTITLEMENT-AWARE. A paying member must never be sold a
    //    trial of something they already hold ("Start 7-day trial" to a Pro Lifetime
    //    member was the bug). Every actionable CTA reuses the upgrade sheet, whose lane
    //    matrix (upgradeLanes) already tailors the panel to tier×interval.
    //    Lifetime = comp / uncapped grant with no period end (mirrors theme.js _sdPlanChip).
    var lifetime = (tier === "unlimited" || me.source === "comp") &&
                   !me.current_period_end && me.status !== "canceled";
    // Nothing left to sell on the Pro card: unlimited, Pro Lifetime, or Pro Annual.
    // interval is null for comp/lifetime grants, so only an EXPLICIT "monthly" is upsellable.
    var proTop = (tier === "unlimited") || lifetime || (tier === "pro" && interval !== "monthly");
    document.querySelectorAll(".js-plan-cta").forEach(function (pc) {
      var plan = pc.getAttribute("data-plan");
      if (plan === "free") {
        // Free card: inert "Current plan" when free, else "Included" (paid tiers include Free)
        makeInert(pc, tier === "free" ? "current" : "included");
      } else if (tier === "free") {
        // signed-in free tier → unchanged: keep the card's own trial copy, open the sheet
        makePlanLive(pc, null, start, { plan: plan, period: pc.getAttribute("data-period") || "annual" });
      } else if (normTier(plan) === "essential") {
        // `plan` is the landing's data-plan MARKUP id. Phase 4 flipped it to `essential`,
        // but a warm-cached index.html still serves `insider`, so normTier lands it
        // canonical before the comparison rather than matching a literal.
        // Held by an Essential member, bundled into Pro/unlimited — not a purchase.
        makeInert(pc, tier === "essential" ? "yourPlan" : "included");
      } else if (plan === "pro") {
        if (proTop) makeInert(pc, "yourPlan");
        else if (tier === "pro") makePlanLive(pc, "upgradeAnnual", start, { plan: "pro", period: "annual" });
        else makePlanLive(pc, "upgrade", start, { plan: "pro", period: "annual" });
      } else {
        makePlanLive(pc, null, start, { plan: plan, period: pc.getAttribute("data-period") || "annual" });
      }
    });

    // 5) gear ACCOUNT card (signed-in view)
    renderGearAccount(me);
  }

  // Paint a node bilingually: cache the English original in __en and set data-zh so
  // the landing's [data-zh] LANG applier keeps it in sync on later toggles, AND show
  // the CURRENT language immediately (window.LANG isn't a global — the inline const
  // never reaches window — so we can't defer to it; do the swap in place).
  function paintBilingual(el, en, zh) {
    el.setAttribute("data-zh", zh);
    el.__en = en;
    el.innerHTML = (lang() === "zh") ? zh : en;
  }
  function setChromeLabel(el, key) { paintBilingual(el, UPCHROME[key][0], UPCHROME[key][1]); }
  function bindChromeCta(cta) {
    if (cta.__bound) return; cta.__bound = true;
    cta.addEventListener("click", function (e) { if (cta.__upgrade) { e.preventDefault(); openSheet("upgrade", {}); } });
  }
  function bindPlanCta(pc) {
    if (pc.__bound) return; pc.__bound = true;
    pc.addEventListener("click", function (e) {
      // A revertAuthChrome() (hard 401) clears __upgradePlan: the card is a guest signup
      // link again, so this listener must stand down rather than force the upgrade sheet.
      if (!pc.__upgradePlan) return;
      e.preventDefault(); openSheet("upgrade", pc.__upgradePlan);
    });
  }
  function makeInert(pc, key) {
    paintBilingual(pc, UPCHROME[key][0], UPCHROME[key][1]);
    pc.setAttribute("aria-disabled", "true");
    pc.removeAttribute("href");
    // Drop data-period too: the landing's applyPricing() re-writes `.js-plan-cta[data-period]`
    // hrefs on every billing/language toggle, and `new URL("", location.href)` does NOT throw —
    // so a toggle would silently hand the href back to a card we just made inert. An inert card
    // has no billing period to carry. __periodAttr lets makePlanLive/restore put it back.
    var per = pc.getAttribute("data-period");
    if (per != null) { pc.__periodAttr = per; pc.removeAttribute("data-period"); }
    pc.style.pointerEvents = "none"; pc.style.opacity = ".65";
  }
  // The inverse of makeInert + the actionable wiring. applyAuthChrome runs TWICE per load
  // (optimistic hint, then confirmed /api/me), so a card the first paint made inert must be
  // fully revivable when the confirmed tier turns out to be upsellable after all.
  // key === null restores the card's own signed-out copy (the trial labels) from the snapshot.
  function makePlanLive(pc, key, href, target) {
    if (key) setChromeLabel(pc, key); else restorePlanLabel(pc);
    pc.removeAttribute("aria-disabled");
    pc.style.pointerEvents = ""; pc.style.opacity = "";
    if (pc.__periodAttr != null && !pc.hasAttribute("data-period")) pc.setAttribute("data-period", pc.__periodAttr);
    pc.setAttribute("href", href);
    pc.__upgradePlan = target;
    bindPlanCta(pc);
  }
  // Snapshot the signed-out pricing CTAs once, before any repaint, so both a downgrade
  // repaint and a hard-401 revert can restore the exact original copy. LANG may already
  // have swapped the page to zh by the time this runs — __en holds the English original.
  function snapshotPlanCtas() {
    if (_planSnap) return;
    _planSnap = [];
    document.querySelectorAll(".js-plan-cta").forEach(function (pc) {
      _planSnap.push({
        el: pc,
        en: (pc.__en != null) ? pc.__en : pc.innerHTML,
        zh: pc.getAttribute("data-zh"),
        href: pc.getAttribute("href"),
        period: pc.getAttribute("data-period")
      });
    });
  }
  function _planSnapFor(pc) {
    if (!_planSnap) return null;
    for (var i = 0; i < _planSnap.length; i++) if (_planSnap[i].el === pc) return _planSnap[i];
    return null;
  }
  function restorePlanLabel(pc) {
    var s = _planSnapFor(pc);
    if (!s) return;
    if (s.zh != null) paintBilingual(pc, s.en, s.zh);
    else { pc.__en = s.en; pc.innerHTML = s.en; }
  }
  // Full signed-out restore of one pricing CTA (label + href + billing period + inert styling).
  function restorePlanCta(pc) {
    var s = _planSnapFor(pc);
    if (!s) return;
    restorePlanLabel(pc);
    pc.removeAttribute("aria-disabled");
    pc.style.pointerEvents = ""; pc.style.opacity = "";
    if (s.href != null) pc.setAttribute("href", s.href); else pc.removeAttribute("href");
    if (s.period != null) pc.setAttribute("data-period", s.period); else pc.removeAttribute("data-period");
    pc.__upgradePlan = null;
  }
  function renderGearAccount(me) {
    var out = _byId("gp-acct-out"), inn = _byId("gp-acct-in");
    if (!out || !inn) return;
    out.hidden = true; out.style.display = "none";
    inn.hidden = false; inn.style.display = "";
    // avatar initial: first name from user_metadata, else email
    var u = null; try { u = window.MDXAuth && window.MDXAuth.user && window.MDXAuth.user(); } catch (e) {}
    var meta = (u && u.user_metadata) || {};
    var first = meta.first_name || meta.display_name || meta.name || meta.full_name || "";
    var email = (u && u.email) || me.email || "";
    var initial = (first || email || "?").trim().charAt(0).toUpperCase();
    var av = _byId("gp-avatar"); if (av) av.textContent = initial || "?";
    var em = _byId("gp-email"); if (em) em.textContent = email || "";
  }

  // Undo the signed-in chrome → guest state. Called only when /api/me returns a hard 401
  // (cookie present but the session is dead/revoked): sign out locally so the stale cookie
  // stops masquerading as a live login, and restore the signed-out header from the snapshot.
  function revertAuthChrome() {
    clearMeHint(); clearMeCache();
    var login = _byId("nav-login"); if (login) { login.hidden = false; login.style.display = ""; }
    var cta = _byId("nav-cta");
    if (cta && _navSnap && _navSnap.ctaHtml != null) {
      cta.innerHTML = _navSnap.ctaHtml;
      if (_navSnap.ctaHref) cta.setAttribute("href", _navSnap.ctaHref);
      cta.__upgrade = false;
    }
    // pricing cards → back to the signed-out trial copy (label, href, billing period, no inert)
    document.querySelectorAll(".js-plan-cta").forEach(restorePlanCta);
    var out = _byId("gp-acct-out"), inn = _byId("gp-acct-in");
    if (out) { out.hidden = false; out.style.display = ""; }
    if (inn) { inn.hidden = true; inn.style.display = "none"; }
    ensureAuthBroker().then(function (auth) { if (auth && auth.signOut) { try { auth.signOut(); } catch (e) {} } });
  }

  // Entry: sniff the cookie; if signed-in, paint the signed-in chrome IMMEDIATELY (never
  // leave "Log in" up while the network is in flight), then confirm with /api/me. Fail quiet.
  function initAuthChrome() {
    // Only the landing has these ids; bail on macro pages (this file's other
    // consumers never render the landing nav).
    if (!_byId("nav-cta") && !_byId("gp-acct-out")) return;
    wireGearAccount();                         // always (signed-out gear needs its buttons)
    if (!_navSnap) { var c0 = _byId("nav-cta"); _navSnap = c0 ? { ctaHtml: c0.innerHTML, ctaHref: c0.getAttribute("href") } : {}; }
    snapshotPlanCtas();                        // pricing CTAs too — a 401 must restore the trial copy
    if (!hasSessionCookie()) { clearMeHint(); return; }   // guest → signed-out markup, zero network
    // OPTIMISTIC PAINT: a session cookie means the user IS signed in. Reflect it NOW from
    // the fresh SS cache or the durable hint (or a free-tier default) so the "Log in" chrome
    // never lingers — the root cause of "I keep having to log in" was the header waiting on a
    // /api/me that, until now, went CROSS-ORIGIN and was silently CORS-blocked.
    applyAuthChrome(readMeCache() || readMeHint() || { tier: "free", interval: null, email: "" });
    // Confirm with the server: refine the tier, or revert to signed-out ONLY on a hard 401.
    ensureAuthBroker().then(function () {
      getAccessToken().then(function (token) {
        if (!token) return;                    // no token yet → keep the optimistic chrome
        fetch(apiBase() + "/api/me", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
          .then(function (r) {
            if (r && r.ok) return r.json().then(function (me) { if (me) { writeMeCache(me); applyAuthChrome(me); } }).catch(function () {});
            if (r && r.status === 401) revertAuthChrome();   // session truly dead → signed-out
            // 429 / 5xx / offline → keep the optimistic signed-in chrome (transient)
          })
          .catch(function () {/* network/offline → keep the optimistic signed-in chrome */});
      });
    });
  }

  // ══════════════════════════ on-load: deep links + resume ═══════════════════
  function bootDeepLinks() {
    // ?upgrade=1 deep link (the _mmOpenOnboard cross-page fallback) → upgrade sheet
    try {
      if (new URLSearchParams(location.search).has("upgrade")) {
        stripOnboardParams(); openSheet("upgrade", {}); return;
      }
    } catch (e) {}
    var intent = parseIntent(window.location.search.replace(/^\?/, ""));
    var resumeStash = null;
    if (intent && intent.resume) {
      // Google OAuth return — restore the wizard stash written before redirect
      try { var raw = localStorage.getItem(LS_ONBOARD_RESUME); if (raw) resumeStash = JSON.parse(raw); } catch (e) {}
      try { localStorage.removeItem(LS_ONBOARD_RESUME); } catch (e) {}
    }
    if (intent) {
      // hydrate from resume stash first (name/prefs/plan), then open
      if (resumeStash) {
        S.firstName = resumeStash.firstName || S.firstName;
        S.lastName = resumeStash.lastName || S.lastName;
        if (resumeStash.plan) S.plan = normTier(resumeStash.plan);
        if (resumeStash.period) S.period = resumeStash.period;
        if (resumeStash.prefs) S.prefs = resumeStash.prefs;
      }
      // Google-OAuth return: a signin-mode round-trip lands on the desk (ret wins),
      // not back in the sheet; a pending-upgrade round-trip resumes the upgrade panel.
      if (intent.resume && resumeStash) {
        if (resumeStash.pendingUpgrade) { stripOnboardParams(); openSheet("upgrade", resumeStash.upgradeOpts || {}); return; }
        if (resumeStash.mode === "signin") { stripOnboardParams(); location.href = loginDest(); return; }
      }
      // STICKY LOGIN: a regwall bounce (?signin=1[&ret=…]) with a session cookie
      // present is a returning SIGNED-IN visitor whose access token expired —
      // refresh silently and go back; never prompt for credentials they have.
      if (intent.mode === "signin" && !intent.resume && hasSessionCookie() && !wallHopLooping(loginDest())) {
        silentWallResume();
        return;
      }
      openSheet(intent.mode, { plan: intent.plan || S.plan, period: intent.period || S.period, resume: intent.resume });
      stripOnboardParams();
      return;
    }
    // no deep link → restore a mid-flow per-tab stash if one exists (reload resilience)
    var st = stashLoad();
    if (st && st.open) {
      S.mode = st.mode || "signup"; S.step = st.step || STEP_ACCOUNT;
      S.firstName = st.firstName || ""; S.lastName = st.lastName || ""; S.email = st.email || "";
      S.prefs = st.prefs || S.prefs; S.plan = normTier(st.plan) || S.plan; S.period = st.period || S.period;
      S.confirmPending = !!st.confirmPending; S.trialActive = !!st.trialActive; S.trialEnd = (typeof st.trialEnd === "number") ? st.trialEnd : null;
      S.subLive = !!st.subLive;
      S.planTouched = !!st.planTouched || (st.step || 1) >= 3;  // stale stashes: reached-plan implies touched
      openSheet(S.mode, {});
    }
  }
  function stripOnboardParams() {
    try {
      var sp = new URLSearchParams(window.location.search);
      var changed = false;
      ["signup", "signin", "onboard", "plan", "period", "upgrade"].forEach(function (k) { if (sp.has(k)) { sp.delete(k); changed = true; } });
      if (!changed) return;
      var qs = sp.toString();
      var url = window.location.pathname + (qs ? "?" + qs : "") + window.location.hash;
      window.history.replaceState(null, "", url);
    } catch (e) {}
  }

  function boot() { bootDeepLinks(); initAuthChrome(); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  // expose a tiny API (parity with MDXAuth.open) for other scripts/tests.
  // applyChrome(me) lets a host that already resolved /api/me paint the landing's
  // signed-in header without re-fetching (also the console-driven verify seam).
  syncFoundingOffer();
  window.MMOnboard = { open: openSheet, close: closeSheet, applyChrome: applyAuthChrome };
})();
