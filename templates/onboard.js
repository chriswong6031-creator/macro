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

  // Raw cents — the ONLY hand-entered plan numbers (mirror config/plans.yml /
  // terminal plans.ts). Every displayed figure is DERIVED from these.
  var CENTS = {
    insider: { monthly: 6900, annual: 58800 },
    pro:     { monthly: 9900, annual: 82800 }
  };
  function perMonth(key, period) { var c = CENTS[key]; return Math.round(period === "annual" ? c.annual / 12 / 100 : c.monthly / 100); }
  function monthlyPrice(key) { return Math.round(CENTS[key].monthly / 100); }
  function annualBilled(key) { return Math.round(CENTS[key].annual / 100); }
  function savePct(key) { var c = CENTS[key]; return Math.round(((c.monthly - c.annual / 12) / c.monthly) * 100); }
  function bestSavePct() { return Math.max(savePct("insider"), savePct("pro")); }
  function firstInvoiceTotal(key, period) { return period === "annual" ? annualBilled(key) : monthlyPrice(key); }
  function proWedge() { return perMonth("pro", "annual") - perMonth("insider", "annual"); }

  // ── bilingual: [en, zh] tuples. `zh` may contain inline HTML (matches the
  //    landing's data-zh contract, which swaps innerHTML). ──────────────────────
  var LEX = {
    // pane (left) — step-adaptive headline + subline
    paneAccountH:  ["Your desk is one step away.", "你的台席，仅一步之遥。"],
    paneAccountS:  ["Create your account to unlock every dashboard, signal and the Terminal — free.", "创建账户，解锁全部看板、信号与 Terminal——免费。"],
    panePrefsH:    ["Make it read the way you think.", "让它按你的思路来解读。"],
    panePrefsS:    ["Pick your markets and theme. Everything here is optional — change it any time.", "选择你的市场与主题。此处全部可选，随时可改。"],
    planePlanH:    ["Free to read. Cheap to go deep.", "免费阅读。深度也不贵。"],
    planePlanS:    ["Start free forever, or add the analyst and the desks. Every paid plan is a 7-day free trial.", "永久免费开始，或加上分析师与各台席。所有付费方案均含 7 天免费试用。"],
    paneBillH:     ["7 days free. Cancel in one click.", "7 天免费。一键取消。"],
    paneBillS:     ["Your card starts the trial. We tell you exactly when the first charge lands — and cancelling before then costs nothing.", "绑卡即开启试用。我们会明确告知首次扣款时间——在此之前取消，分文不收。"],
    paneDoneH:     ["Welcome to the desk.", "欢迎来到你的台席。"],
    paneDoneS:     ["Everything is live. Open the dashboard and pick up where the market is right now.", "一切已就绪。打开看板，从当下的市场接手。"],

    // desk pane (the materializing mini-desk in the left rail)
    asmTrial:  ["7-DAY TRIAL", "7天试用"],
    deskYour:  ["YOUR DESK", "你的工作台"],
    deskTf:    ["DAILY", "日线"],
    deskZone:  ["ENTRY ZONE", "入场区间"],
    capRead:   ["Daily read · 6 signals a day", "每日研判 · 每天 6 条信号"],
    capFlow:   ["Intraday options flow", "日内期权流"],
    capAI:     ["Pro AI research dives", "Pro AI 深度研究"],

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
    terms:        ["By continuing you agree to our Terms and Privacy Policy.", "继续即表示你同意我们的服务条款与隐私政策。"],

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
    planSub:      ["Free forever, or start a 7-day trial of a paid plan.", "永久免费，或开启付费方案的 7 天试用。"],
    togAnnual:    ["Annual <span class=\"obm-save\">SAVE UP TO " + bestSavePct() + "%</span>", "按年 <span class=\"obm-save\">最高省 " + bestSavePct() + "%</span>"],
    togMonthly:   ["Monthly", "按月"],
    planFree:     ["Free", "免费"],
    planInsider:  ["Insider", "Insider"],
    planPro:      ["Pro", "Pro"],
    whoFree:      ["The daily read, six signals, the Terminal — forever.", "每日研判、六条信号、Terminal——永久免费。"],
    whoInsider:   ["The working desk, with the analyst on call.", "随叫随到的分析师，配上完整的工作台席。"],
    whoPro:       ["For the ones who ask harder questions.", "为那些提出更难问题的人准备。"],
    perMoAnnual:  ["/mo billed annually", "/月 · 按年结算"],
    perMo:        ["/mo", "/月"],
    free0:        ["$0", "$0"],
    ribbon:       ["MOST POPULAR", "最受欢迎"],
    // summaries
    sumGetFree:   ["What you get", "你将获得"],
    sumMissFree:  ["What you're missing", "你还缺少"],
    sumPlusInsider:["Everything in Free, plus", "免费版全部功能，另加"],
    sumPlusPro:   ["Everything in Insider, plus", "Insider 全部功能，另加"],
    getFree1:     ["The daily read + <b>every macro dashboard</b>", "每日研判 + <b>全部宏观看板</b>"],
    getFree2:     ["<b>6 buy signals a day</b> with a public track record", "<b>每天 6 条买入信号</b>，战绩公开可查"],
    getFree3:     ["The full Terminal — live charts, no install", "完整 Terminal——实时图表，无需安装"],
    missIns1:     ["Unlimited Flash AI + 20 Pro AI dives a month", "无限量 Flash AI + 每月 20 次 Pro AI 深度分析"],
    missIns2:     ["Intraday options flow, Insider & Congress desks", "日内期权流、内部人与国会台席"],
    missPro1:     ["Mastermind + institutional research reports", "Mastermind + 机构研究报告"],
    plusIns1:     ["<b>Unlimited Flash AI</b>, 20 Pro AI dives a month", "<b>无限量 Flash AI</b>、每月 20 次 Pro AI 深度分析"],
    plusIns2:     ["<b>Intraday options flow</b> — sweeps and blocks as they print", "<b>日内期权流</b>——扫单与大宗成交实时打印"],
    plusIns3:     ["Insider/Congress & 13F desks, transcripts, daily briefs", "内部人/国会与 13F 台席、电话会记录、每日简报"],
    plusPro1:     ["<b>50 Pro AI dives a month</b>", "<b>每月 50 次 Pro AI 深度分析</b>"],
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

    // step 4 — billing
    billTitle:    ["Add your card", "添加银行卡"],
    billSub:      ["Your 7-day trial starts now. Cancel any time before it ends and you pay nothing.", "7 天试用现在开始。在结束前随时取消，分文不收。"],
    billPerMo:    ["/mo", "/月"],
    billBilledAnnually:["Billed $__T__ per year after the trial.", "试用结束后每年扣款 $__T__。"],
    billBilledMonthly: ["Billed monthly after the trial.", "试用结束后按月扣款。"],
    billTrialLine:["<b>7-day free trial</b> — your first charge of $__T__ lands on __D__.", "<b>7 天免费试用</b>——首次扣款 $__T__ 将于 __D__ 进行。"],
    billCancelLine:["Cancel before then and you pay nothing.", "在此之前取消，分文不收。"],
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
    billOrFree:   ["or continue with Free", "或改用免费版"],
    billConfirmFirst:["Confirm your email first, then add your card to start the trial. We've sent a confirmation link.", "请先确认邮箱，再绑卡开启试用。确认链接已发送。"],
    billConfirmGo:["Continue", "继续"],

    // step 5 — done
    doneTitle:    ["You're in.", "你已加入。"],
    doneTitleNamed:["You're in, __N__.", "你已加入，__N__。"],
    doneConfirm:  ["Check __E__ to confirm your email and finish setting up.", "查收 __E__ 以确认邮箱并完成设置。"],
    doneTrial:    ["Your __T__ trial is live — first charge on __D__.", "你的 __T__ 试用已生效——首次扣款为 __D__。"],
    doneReady:    ["Your dashboards, signals and the Terminal are ready.", "你的看板、信号与 Terminal 已就绪。"],
    openDashboard:["Open the dashboard", "打开仪表盘"],
    openTerminal: ["Open the Terminal →", "打开 Terminal →"],

    // ── upgrade mode (post-login monetization sheet) ──
    upTitle:      ["Upgrade your desk", "升级你的台席"],
    upLoad:       ["Loading your plan…", "正在加载你的方案…"],
    upErr:        ["We couldn't load your plan. Please try again.", "无法加载你的方案，请重试。"],
    upRetry:      ["Try again", "重试"],
    // free → start a trial
    upFreeSub:    ["Start a 7-day free trial of Insider or Pro — your card starts the trial and we tell you exactly when the first charge lands.", "开启 Insider 或 Pro 的 7 天免费试用——绑卡即开始试用，我们会明确告知首次扣款时间。"],
    // annual-discount subheads
    upToAnnualSub:["Switch to annual and save up to " + bestSavePct() + "%.", "切换为年付，最高可省 " + bestSavePct() + "%。"],
    upProAnnualSub:["Move up to Pro Annual — everything in Pro, at the lowest per-month price.", "升级到 Pro 年付——Pro 全部功能，月均价格最低。"],
    // lane cards
    laneInsAnnual:["Insider Annual", "Insider 年付"],
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
    upConfirmProrate:["You'll be charged the prorated difference now.", "现在将按比例向你收取差额。"],
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

  // ── state ────────────────────────────────────────────────────────────────
  var S = {
    open: false, mode: "signup", step: STEP_ACCOUNT,
    firstName: "", lastName: "", email: "", password: "",
    prefs: { market_focus: [], trade_types: [], theme_pref: "auto" },
    plan: "pro", period: "annual",
    confirmPending: false, trialActive: false, trialEnd: null,
    // upgrade mode (post-login monetization sheet)
    pendingUpgrade: false, upgradeOpts: null, me: null
  };

  // ── stash (per-tab, password never persisted) ──────────────────────────────
  function stashSave() {
    try {
      sessionStorage.setItem(SS_STASH, JSON.stringify({
        open: S.open, mode: S.mode, step: S.step,
        firstName: S.firstName, lastName: S.lastName, email: S.email,
        prefs: S.prefs, plan: S.plan, period: S.period,
        confirmPending: S.confirmPending, trialActive: S.trialActive, trialEnd: S.trialEnd,
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
  function apiBase() { return (window.MM_API || "").replace(/\/+$/, ""); }
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
  var LOCK = '<svg class="obm-desk-lk" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';
  // The desk pane's annotated mini-chart: an uptrend that pulls back INTO the
  // buy-zone band and resumes — the product's own entry story, not a skeleton.
  // pathLength=1 lets CSS draw the line with a single dashoffset animation.
  var DESK_CHART =
    '<svg viewBox="0 0 300 124" preserveAspectRatio="none" aria-hidden="true">' +
    '<defs>' +
    '<linearGradient id="obmDL" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#285fff"/><stop offset="1" stop-color="#7862e0"/></linearGradient>' +
    '<linearGradient id="obmDA" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#285fff" stop-opacity=".14"/><stop offset="1" stop-color="#285fff" stop-opacity="0"/></linearGradient>' +
    '</defs>' +
    '<g stroke="rgba(28,36,48,.06)" stroke-width="1"><path d="M0 33H300"/><path d="M0 64H300"/><path d="M0 95H300"/></g>' +
    '<rect x="0" y="78" width="300" height="26" fill="rgba(40,95,255,.07)"/>' +
    '<path d="M0 78H300" stroke="rgba(40,95,255,.30)" stroke-width="1" stroke-dasharray="3 4" fill="none"/>' +
    '<path d="M0 104H300" stroke="rgba(40,95,255,.30)" stroke-width="1" stroke-dasharray="3 4" fill="none"/>' +
    '<path class="obm-desk-area" d="M8 68 L40 60 L66 66 L92 46 L118 52 L148 84 L172 90 L198 68 L232 50 L262 40 L292 27 L292 124 L8 124 Z" fill="url(#obmDA)"/>' +
    '<path class="obm-desk-line" pathLength="1" d="M8 68 L40 60 L66 66 L92 46 L118 52 L148 84 L172 90 L198 68 L232 50 L262 40 L292 27" fill="none" stroke="url(#obmDL)" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>' +
    '<circle class="obm-desk-pt" cx="292" cy="27" r="3.2" fill="#285fff"/>' +
    '<circle class="obm-desk-ring" cx="292" cy="27" r="3.2" fill="none" stroke="#285fff" stroke-width="1.4"/>' +
    '</svg>';
  var DESK =
    '<div class="obm-desk-plate"><span class="obm-desk-ava" data-desk="ava">M</span><span class="obm-desk-name" data-desk="name"></span><span class="obm-desk-trial" data-desk="trial" hidden></span></div>' +
    '<div class="obm-desk-chart"><div class="obm-desk-tkr"><b data-desk="tkr">SPY</b><span class="obm-desk-tf" data-k="deskTf"></span></div>' + DESK_CHART + '<span class="obm-desk-zone" data-k="deskZone"></span></div>' +
    '<div class="obm-desk-chips" data-desk="mkts"></div>' +
    '<div class="obm-desk-caps" data-desk="caps"></div>';

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

    // ── LEFT pane ──
    var pane = h("div", "obm-pane");
    var brand = h("div", "obm-brand"); brand.innerHTML = GLYPH + '<span>MASTERMIND</span>';
    var paneCopy = h("div", "obm-pane-copy");
    var paneH = h("h2", "obm-pane-h"); var paneS = h("p", "obm-pane-sub");
    paneCopy.appendChild(paneH); paneCopy.appendChild(paneS);
    var asm = h("div", "obm-desk");
    asm.innerHTML = DESK;
    pane.appendChild(brand); pane.appendChild(paneCopy); pane.appendChild(asm);

    // ── RIGHT form pane ──
    var formPane = h("div", "obm-form-pane");
    var steps = h("div", "obm-steps");
    var body = h("div", "obm-body");
    var foot = h("div", "obm-foot");
    formPane.appendChild(steps); formPane.appendChild(body); formPane.appendChild(foot);

    sheet.appendChild(close); sheet.appendChild(pane); sheet.appendChild(formPane);
    scrim.appendChild(sheet);
    document.body.appendChild(scrim);

    // scrim click closes (but not clicks inside the sheet)
    scrim.addEventListener("mousedown", function (e) { if (e.target === scrim) requestClose(); });

    el = { scrim: scrim, sheet: sheet, pane: pane, paneH: paneH, paneS: paneS, asm: asm, steps: steps, body: body, foot: foot };

    // subscribe to language changes → re-apply our subtree
    if (window.LANG && typeof window.LANG.onChange === "function") window.LANG.onChange(applyLang);
    // also observe html[data-lang] directly (robust if LANG isn't present yet)
    try {
      new MutationObserver(function () { applyLang(); }).observe(document.documentElement, { attributes: true, attributeFilter: ["data-lang"] });
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
    // the desk nameplate builds its possessive per-language in code, not via [data-k]
    renderAssembly();
  }

  // helper: create a node whose text is a LEX key, re-applied on lang change
  function T(tag, cls, key, attrs) { var n = h(tag, cls, attrs); n.setAttribute("data-k", key); n.innerHTML = tx(key); return n; }

  // ══════════════════════════ stepper ════════════════════════════════════════
  function paidSelected() { return S.plan === "insider" || S.plan === "pro"; }
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
      if (d.n === S.step) s.classList.add("obm-cur");
      else if (isStepDone(d.n)) s.classList.add("obm-done");
      var num = ("0" + d.n).slice(-2);
      s.innerHTML = '<span class="obm-step-n">' + svgCheck("obm-step-ck") + '<span class="obm-step-num">' + num + '</span></span>';
      // hide the number when done-check shows
      var nEl = s.querySelector(".obm-step-n");
      if (s.classList.contains("obm-done")) { var numSpan = nEl.querySelector(".obm-step-num"); if (numSpan) numSpan.style.display = "none"; }
      var lbl = T("span", "obm-step-lbl", d.key); s.appendChild(lbl);
      el.steps.appendChild(s);
      if (idx < shown.length - 1) el.steps.appendChild(h("span", "obm-step-sep"));
    });
  }
  function isStepDone(n) {
    // signin mode has no stepper progression; treat all as neutral
    if (S.mode === "signin") return false;
    if (S.step === STEP_DONE) return n < STEP_DONE;
    return n < S.step;
  }

  // ══════════════════════════ left-pane content ══════════════════════════════
  function renderPane() {
    var map = {
      1: ["paneAccountH", "paneAccountS"], 2: ["panePrefsH", "panePrefsS"],
      3: ["planePlanH", "planePlanS"], 4: ["paneBillH", "paneBillS"], 5: ["paneDoneH", "paneDoneS"]
    };
    // upgrade mode borrows the billing pane copy ("7 days free · cancel in one click")
    var m = (S.mode === "upgrade") ? ["paneBillH", "paneBillS"] : (map[S.step] || map[1]);
    el.paneH.setAttribute("data-k", m[0]); el.paneH.innerHTML = tx(m[0]);
    el.paneS.setAttribute("data-k", m[1]); el.paneS.innerHTML = tx(m[1]);
    renderAssembly();
  }
  // The desk pane — a miniature Mastermind desk that materializes as the user
  // progresses. Nothing here echoes form fields back; every element is a piece
  // of the product responding to a choice the user actually made:
  //   nameplate  ← the typed first name (default "YOUR DESK")
  //   chart+chips← the market picks (first pick drives the chart's ticker)
  //   cap rows   ← the chosen plan (lock/check; untouched plan = neutral list)
  // Upgrade mode shows the SAME desk read off /api/me — locked rows are exactly
  // what the upgrade buys.
  var MKD = {
    us:     { t: "NVDA",    c: ["NVDA", "SPY", "TSLA"] },
    cn:     { t: "600519",  c: ["600519", "300750", "BABA"] },
    hk:     { t: "0700.HK", c: ["0700", "9988", "3690"] },
    ca:     { t: "SHOP.TO", c: ["SHOP", "RY", "ENB"] },
    global: { t: "SPY",     c: ["SPY", "ASML", "0700"] }
  };
  function renderAssembly() {
    if (!el.asm) return;
    var q = function (s) { return el.asm.querySelector(s); };
    var zh = lang() === "zh";
    // nameplate — becomes THEIRS the moment they type a first name
    var first = (S.mode === "upgrade") ? (fullNameFromMeta().split(" ")[0] || "") : S.firstName.trim();
    var plate = q('[data-desk="name"]');
    if (first) {
      var up = first.toUpperCase();
      plate.textContent = zh ? up + " 的工作台" : up + (/S$/.test(up) ? "’ DESK" : "’S DESK");
    } else { plate.textContent = tx("deskYour"); }
    q('[data-desk="ava"]').textContent = first ? first.charAt(0).toUpperCase() : "M";
    // chart ticker + watch chips follow the market picks
    var picks = S.prefs.market_focus;
    var tkr = q('[data-desk="tkr"]');
    var newT = (picks.length ? (MKD[picks[0]] || MKD.us) : MKD.global).t;
    if (tkr.textContent !== newT) { tkr.textContent = newT; redrawDesk(); }
    var chips = [];
    (picks.length ? picks : ["global"]).forEach(function (k) {
      (MKD[k] || MKD.us).c.forEach(function (t) { if (chips.indexOf(t) === -1) chips.push(t); });
    });
    var mk = q('[data-desk="mkts"]'); mk.innerHTML = "";
    chips.slice(0, 4).forEach(function (t) { var c = h("span", "obm-desk-chip"); c.textContent = t; mk.appendChild(c); });
    // capability rows — neutral until the user actually reaches the plan step
    // (the preselected default is not THEIR choice yet; honesty law unchanged)
    var tier = null;
    if (S.mode === "upgrade") tier = (S.me && S.me.tier) || "free";
    else if (S.planTouched) tier = S.plan;
    var RANK = { free: 0, insider: 1, pro: 2, unlimited: 2 };
    var caps = q('[data-desk="caps"]'); caps.innerHTML = "";
    [["capRead", 0], ["capFlow", 1], ["capAI", 2]].forEach(function (cp) {
      var row = h("div", "obm-desk-cap");
      var have = tier == null ? null : (RANK[tier] != null ? RANK[tier] : 0);
      var ic = h("span", "obm-desk-ci");
      if (have == null) ic.innerHTML = '<i class="obm-desk-dot2"></i>';
      else if (have >= cp[1]) { row.classList.add("obm-on"); ic.innerHTML = svgCheck("obm-desk-ck"); }
      else { row.classList.add("obm-off"); ic.innerHTML = LOCK; }
      row.appendChild(ic);
      row.appendChild(T("span", "obm-desk-cl", cp[0]));
      if (have != null && have < cp[1]) { var tag = h("span", "obm-desk-tag"); tag.textContent = cp[1] === 2 ? "PRO" : "INSIDER"; row.appendChild(tag); }
      caps.appendChild(row);
    });
    // trial chip on the plate once a paid plan is the user's actual choice
    var trial = q('[data-desk="trial"]');
    var paidChosen = S.mode !== "upgrade" && S.planTouched && (S.plan === "insider" || S.plan === "pro");
    trial.hidden = !paidChosen;
    if (paidChosen) trial.textContent = tx("asmTrial");
    // keep keyed labels (timeframe/zone chips) fresh
    var keys = el.asm.querySelectorAll("[data-k]");
    for (var i = 0; i < keys.length; i++) keys[i].innerHTML = tx(keys[i].getAttribute("data-k"));
  }
  // restart the chart's draw-in (used on open + when the ticker swaps)
  function redrawDesk() {
    if (!el.asm) return;
    el.asm.classList.remove("obm-draw");
    void el.asm.offsetWidth;
    el.asm.classList.add("obm-draw");
  }

  // ══════════════════════════ router ═════════════════════════════════════════
  function go(step) { S.step = step; if (step >= STEP_PLAN && S.mode === "signup") S.planTouched = true; render(); stashSave(); }
  function render() {
    if (!el.sheet) return;
    renderSteps();
    // signin + upgrade are compact single-panel variants — hide the multi-step stepper
    el.steps.style.display = (S.mode === "signin" || S.mode === "upgrade") ? "none" : "";
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
    applyLang();
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
      row.appendChild(field("firstName", "ob-fn", "text", S.firstName, "Jordan", "given-name", function (v) { S.firstName = v; renderAssembly(); }));
      row.appendChild(field("lastName", "ob-ln", "text", S.lastName, "Wei", "family-name", function (v) { S.lastName = v; renderAssembly(); }));
      form.appendChild(row);
    }
    form.appendChild(field("email", "ob-email", "email", S.email, "you@example.com", "email", function (v) { S.email = v; renderAssembly(); }, true));
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
      mkWrap.appendChild(chip(m[0], m[1], S.prefs.market_focus, function () { toggleArr(S.prefs.market_focus, m[0]); render(); }));
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
      trWrap.appendChild(chip(tr[0], tr[1], S.prefs.trade_types, function () { toggleArr(S.prefs.trade_types, tr[0]); render(); }));
    });
    root.appendChild(trWrap);

    footNav({ secondaryKey: null, primaryKey: "continue", onPrimary: onPrefsContinue, dots: true });
    // add the full-width quiet Skip at the left of the footer
    var skip = T("button", "obm-quiet", "skipForNow", { type: "button" });
    skip.style.width = "auto"; skip.addEventListener("click", onPrefsContinue);
    el.foot.insertBefore(skip, el.foot.firstChild);
    return root;
  }
  function chip(key, lblKey, arr, onClick) {
    var on = arr.indexOf(key) !== -1;
    var b = h("button", "obm-chip" + (on ? " obm-on" : ""), { type: "button", "aria-pressed": on ? "true" : "false" });
    b.innerHTML = (on ? svgCheck("obm-chip-ck") : "") + '<span data-k="' + lblKey + '">' + tx(lblKey) + '</span>';
    b.addEventListener("click", onClick);
    return b;
  }
  function thumb(key, lblKey) {
    var on = S.prefs.theme_pref === key;
    var b = h("button", "obm-thumb" + (on ? " obm-on" : ""), { type: "button", "aria-pressed": on ? "true" : "false" });
    b.innerHTML =
      '<span class="obm-thumb-prev obm-' + key + '"><i></i><i></i></span>' +
      '<span class="obm-thumb-foot"><span class="obm-thumb-nm" data-k="' + lblKey + '">' + tx(lblKey) + '</span>' +
      '<span class="obm-radio">' + svgCheck("") + '</span></span>';
    b.addEventListener("click", function () { S.prefs.theme_pref = key; applyThemeChoice(key); render(); });
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

    // period toggle
    var tog = h("div", "obm-toggle", { role: "group" });
    var bA = h("button", "", { type: "button", "aria-pressed": S.period === "annual" ? "true" : "false" }); bA.setAttribute("data-obm-zh", LEX.togAnnual[1]); bA.innerHTML = LEX.togAnnual[0];
    var bM = T("button", "", "togMonthly", { type: "button", "aria-pressed": S.period === "monthly" ? "true" : "false" });
    bA.addEventListener("click", function () { S.period = "annual"; render(); stashSave(); });
    bM.addEventListener("click", function () { S.period = "monthly"; render(); stashSave(); });
    tog.appendChild(bA); tog.appendChild(bM);
    root.appendChild(tog);

    // plan cards
    var plans = h("div", "obm-plans");
    plans.appendChild(planCard("free"));
    plans.appendChild(planCard("insider"));
    plans.appendChild(planCard("pro"));
    root.appendChild(plans);

    // summary switcher
    root.appendChild(planSummary());

    // compare link
    var cmp = T("button", "obm-link obm-brand-link obm-compare", "compareAll", { type: "button" });
    cmp.addEventListener("click", function () { closeSheet(); setTimeout(function () { location.hash = "#pricing"; }, 60); });
    root.appendChild(cmp);

    // footer: back + primary (Free → done, paid → billing)
    footNav({
      back: true, onBack: function () { go(STEP_PREFS); },
      primaryKey: S.plan === "free" ? "contFree" : "contBilling",
      onPrimary: onPlanContinue, dots: true
    });
    return root;
  }
  function planCard(key) {
    var on = S.plan === key, hot = key === "pro";
    var card = h("button", "obm-plan" + (on ? " obm-on" : "") + (hot ? " obm-hot" : ""), { type: "button", "aria-pressed": on ? "true" : "false" });
    var left = h("div", "obm-plan-l");
    var nm = h("div", "obm-plan-nm");
    nm.innerHTML = '<span data-k="' + (key === "free" ? "planFree" : key === "pro" ? "planPro" : "planInsider") + '">' + tx(key === "free" ? "planFree" : key === "pro" ? "planPro" : "planInsider") + '</span>';
    var who = T("div", "obm-plan-who", key === "free" ? "whoFree" : key === "pro" ? "whoPro" : "whoInsider");
    left.appendChild(nm); left.appendChild(who);
    var right = h("div", "obm-plan-r");
    var price = h("div", "obm-plan-price");
    if (key === "free") {
      price.innerHTML = '$0';
    } else {
      var annual = S.period === "annual";
      var mo = perMonth(key, S.period);
      var was = annual ? ('<span class="obm-was">$' + monthlyPrice(key) + '</span>') : "";
      var perK = annual ? "perMoAnnual" : "perMo";
      price.innerHTML = was + '$' + mo + '<span class="obm-per" data-k="' + perK + '">' + tx(perK) + '</span>';
    }
    var radio = h("span", "obm-radio"); radio.innerHTML = svgCheck("");
    right.appendChild(price); right.appendChild(radio);
    card.appendChild(left); card.appendChild(right);
    if (hot) { var rb = h("span", "obm-ribbon", { "data-k": "ribbon" }); rb.textContent = tx("ribbon"); card.appendChild(rb); }
    card.addEventListener("click", function () { S.plan = key; render(); stashSave(); });
    return card;
  }
  function planSummary() {
    var box = h("div", "obm-summary");
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
    } else if (S.plan === "insider") {
      box.appendChild(hd("sumPlusInsider"));
      box.appendChild(list(["plusIns1", "plusIns2", "plusIns3"]));
      var wedge = h("div", "obm-wedge");
      var wtxt = h("span"); wtxt.setAttribute("data-obm-zh", LEX.wedge[1]); wtxt.innerHTML = LEX.wedge[0];
      var wcta = T("button", "obm-link obm-brand-link obm-wedge-cta", "switchPro", { type: "button" });
      wcta.addEventListener("click", function () { S.plan = "pro"; render(); stashSave(); });
      wedge.appendChild(wtxt); wedge.appendChild(wcta);
      box.appendChild(wedge);
    } else {
      box.appendChild(hd("sumPlusPro"));
      box.appendChild(list(["plusPro1", "plusPro2", "plusPro3"]));
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
    if (S.plan === "free") { S.trialActive = false; S.trialEnd = null; go(STEP_DONE); }
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
      if (o && o.t && (Date.now() - o.t) < ME_TTL && o.me) return o.me;
    } catch (e) {}
    return null;
  }
  function writeMeCache(me) { try { sessionStorage.setItem(SS_ME, JSON.stringify({ t: Date.now(), me: me })); } catch (e) {} }
  function clearMeCache() { try { sessionStorage.removeItem(SS_ME); } catch (e) {} }
  function fetchMe(force) {
    var cached = force ? null : readMeCache();
    if (cached) return Promise.resolve(cached);
    return getAccessToken().then(function (token) {
      if (!token) return null;
      return fetch(apiBase() + "/api/me", { headers: { Authorization: "Bearer " + token }, cache: "no-store" })
        .then(function (r) { if (!r || !r.ok) return null; return r.json().catch(function () { return null; }); })
        .then(function (me) { if (me) writeMeCache(me); return me; });
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
      el.scrim.style.display = "flex";
      requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
      document.documentElement.style.overflow = "hidden";
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
    S.me = null; S.upDone = null; S.upErr = false;
    S.open = true; _lastFocus = document.activeElement;
    el.scrim.style.display = "flex";
    requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
    document.documentElement.style.overflow = "hidden";
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

    var tier = (S.me.tier || "free");
    var interval = S.me.interval || null;

    // free (or no active status) → reuse the PLAN→BILLING→DONE steps (they work
    // for a signed-in user; subscribe/init is authenticated). Preselect Pro annual.
    if (tier === "free") {
      S.mode = "signup";                      // hand off to the wizard machinery
      S.step = STEP_PLAN; S.planTouched = true;
      S.confirmPending = false;               // signed-in: no email-confirm gate
      var o = S.upgradeOpts || {};
      S.plan = (o.plan === "insider" || o.plan === "pro") ? o.plan : "pro";
      S.period = (o.period === "monthly" || o.period === "annual") ? o.period : "annual";
      render();                                // re-enter as the plan step (owns el.body)
      return null;                             // signal render() to not append over it
    }

    // paid tiers → lane cards
    var lanes = upgradeLanes(tier, interval);
    if (!lanes.length) return upgradeBest(root);   // pro-annual / unlimited

    // insider-monthly has the three-lane "switch to annual" story; the single-lane
    // cases (insider-annual, pro-monthly) all point up to Pro Annual.
    var subKey = (tier === "insider" && (interval === "monthly" || !interval)) ? "upToAnnualSub" : "upProAnnualSub";
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

  // The lane matrix (upward-only, tier and interval may each rise, never fall).
  function upgradeLanes(tier, interval) {
    var monthly = (interval === "monthly" || !interval);
    if (tier === "insider" && monthly) {
      return [
        { tier: "insider", interval: "annual" },
        { tier: "pro", interval: "monthly" },
        { tier: "pro", interval: "annual", popular: true }
      ];
    }
    if (tier === "insider") return [{ tier: "pro", interval: "annual", proPitch: true }];   // insider-annual
    if (tier === "pro" && monthly) return [{ tier: "pro", interval: "annual", proPitch: true }];
    return [];   // pro-annual / unlimited → best-plan panel
  }

  function upgradeLaneCard(ln) {
    var annual = ln.interval === "annual";
    var nmKey = ln.tier === "insider" ? "laneInsAnnual" : (annual ? "laneProAnnual" : "laneProMonthly");
    var whoKey = ln.tier === "insider" ? "laneInsAnnualWho" : (annual ? "laneProAnnualWho" : "laneProMonthlyWho");
    var hue = ln.tier === "pro" ? "var(--ob-pro)" : "var(--ob-insider)";
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
    // pro-pitch framing line (insider-annual / pro-monthly → pro-annual) — computed
    if (ln.proPitch) {
      var pitch = h("p", "obm-up-pitch");
      var a = annualBilled(ln.tier), m = monthlyPrice(ln.tier) * 12, p = savePct(ln.tier);
      pitch.setAttribute("data-obm-zh", LEX.laneProAnnualPitch[1].replace("__A__", String(a)).replace("__M__", String(m)).replace("__P__", String(p)));
      pitch.innerHTML = LEX.laneProAnnualPitch[0].replace("__A__", String(a)).replace("__M__", String(m)).replace("__P__", String(p));
      left.appendChild(pitch);
    }

    var right = h("div", "obm-plan-r");
    var price = h("div", "obm-plan-price");
    var was = annual ? ('<span class="obm-was">$' + monthlyPrice(ln.tier) + '</span>') : "";
    var perK = annual ? "laneBilledAnnual" : "laneBilledMonthly";
    price.innerHTML = was + '$' + mo + '<span class="obm-per" data-k="' + perK + '">' + tx(perK) + '</span>';
    right.appendChild(price);
    var chev = h("span", "obm-up-chev"); chev.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18l6-6-6-6"/></svg>';
    right.appendChild(chev);

    card.appendChild(left); card.appendChild(right);
    if (ln.popular) { var rb = h("span", "obm-ribbon", { "data-k": "lanePopular" }); rb.textContent = tx("lanePopular"); card.appendChild(rb); }

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
        body: JSON.stringify({ tier: ln.tier, interval: ln.interval })
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
      if (res.status === 404) {   // no Stripe sub (comp'd) → subscribe lane preselecting the target
        S.mode = "signup"; S.step = STEP_PLAN; S.planTouched = true; S.confirmPending = false;
        S.plan = ln.tier; S.period = ln.interval;
        go(STEP_BILLING);
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
      cg.addEventListener("click", function () { go(STEP_DONE); });
      blk.appendChild(cg);
      root.appendChild(blk);
      footNav({ back: true, onBack: function () { go(STEP_PLAN); }, dots: true });
      return root;
    }

    root.appendChild(T("p", "obm-sub", "billSub"));
    root.appendChild(orderCard());
    var host = h("div", "", { "data-obm-billhost": "" });
    root.appendChild(host);
    footNav({ back: true, onBack: function () { go(STEP_PLAN); }, dots: true });

    // kick off async init
    initBilling(host);
    return root;
  }
  function orderCard() {
    var tier = S.plan, annual = S.period === "annual";
    var hue = tier === "pro" ? "var(--ob-pro)" : "var(--ob-insider)";
    var mo = perMonth(tier, S.period), total = firstInvoiceTotal(tier, S.period);
    var date = fmtDate(trialChargeDate());
    var card = h("div", "obm-order"); card.style.setProperty("--obm-accent", hue);
    var billed = annual ? LEX.billBilledAnnually : LEX.billBilledMonthly;
    var billedEn = billed[0].replace("__T__", String(annualBilled(tier)));
    var billedZh = billed[1].replace("__T__", String(annualBilled(tier)));
    var trialEn = LEX.billTrialLine[0].replace("__T__", String(total)).replace("__D__", date);
    var trialZh = LEX.billTrialLine[1].replace("__T__", String(total)).replace("__D__", date);
    card.innerHTML =
      '<div class="obm-order-hd"><span class="obm-order-dot"></span>' +
      '<span class="obm-order-nm" data-k="' + (tier === "pro" ? "planPro" : "planInsider") + '">' + tx(tier === "pro" ? "planPro" : "planInsider") + '</span>' +
      '<span class="obm-order-price">$' + mo + '<span class="obm-order-per" data-k="billPerMo">' + tx("billPerMo") + '</span></span></div>' +
      '<div class="obm-order-billed" data-obm-zh="' + esc(billedZh) + '">' + billedEn + '</div>' +
      '<div class="obm-order-truth">' +
      '<p class="obm-order-trial" data-obm-zh="' + esc(trialZh) + '">' + trialEn + '</p>' +
      '<p class="obm-order-cancel" data-k="billCancelLine">' + tx("billCancelLine") + '</p></div>';
    return card;
  }
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
          body: JSON.stringify({ tier: tier, interval: period })
        }).then(function (initRes) {
          if (initRes.status === 409) { return billAlready(host); }
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
    billState(host, '<p class="obm-bill-state-msg" data-k="billErr">' + tx("billErr") + '</p><button type="button" class="obm-btn" data-obm-retry style="width:auto;margin:0 auto"><span data-k="billRetry">' + tx("billRetry") + '</span></button><button type="button" class="obm-quiet" data-obm-payfree style="margin-top:12px"><span data-k="billOrFree">' + tx("billOrFree") + '</span></button>');
    var r = host.querySelector("[data-obm-retry]"); if (r) r.addEventListener("click", function () { initBilling(host); });
    var f = host.querySelector("[data-obm-payfree]"); if (f) f.addEventListener("click", function () { S.plan = "free"; S.trialActive = false; S.trialEnd = null; go(STEP_DONE); });
  }
  function billNotConfigured(host) {
    billState(host, '<p class="obm-bill-state-msg" data-k="billNotConfigured">' + tx("billNotConfigured") + '</p><a class="obm-link obm-brand-link" href="' + PLANS_HTML + '" target="_blank" rel="noopener noreferrer"><span data-k="billPlansLink">' + tx("billPlansLink") + '</span> →</a>');
  }
  function billAlready(host) {
    billState(host, '<div class="obm-bill-state-hd" data-k="billAlready">' + tx("billAlready") + '</div><p class="obm-bill-state-msg" data-k="billAlreadySub">' + tx("billAlreadySub") + '</p><button type="button" class="obm-btn" data-obm-already style="width:auto;margin:0 auto"><span data-k="billAlreadyGo">' + tx("billAlreadyGo") + '</span></button>');
    var b = host.querySelector("[data-obm-already]"); if (b) b.addEventListener("click", function () { S.trialActive = false; go(STEP_DONE); });
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
    var appearance = {
      theme: "stripe",
      variables: { colorPrimary: "#285fff", colorText: "#1c2430", colorBackground: "#ffffff", borderRadius: "10px", fontFamily: "Inter, system-ui, sans-serif" }
    };
    var elements = stripe.elements({ clientSecret: clientSecret, appearance: appearance });
    _stripe = stripe; _elements = elements;
    host.innerHTML =
      '<form class="obm-bill-form" data-obm-payform>' +
      '<div class="obm-bill-el" data-obm-payel></div>' +
      '<div class="obm-err" data-obm-payerr style="display:none"></div>' +
      '<button type="submit" class="obm-btn" data-obm-paysubmit disabled style="margin-top:14px"><span data-k="billSubmit">' + tx("billSubmit") + '</span></button>' +
      '<button type="button" class="obm-quiet" data-obm-payfree style="margin-top:12px"><span data-k="billOrFree">' + tx("billOrFree") + '</span></button>' +
      '</form>';
    var payEl = elements.create("payment");
    payEl.mount(host.querySelector("[data-obm-payel]"));
    var submitBtn = host.querySelector("[data-obm-paysubmit]");
    payEl.on("ready", function () { submitBtn.disabled = false; });
    host.querySelector("[data-obm-payfree]").addEventListener("click", function () { S.plan = "free"; S.trialActive = false; S.trialEnd = null; go(STEP_DONE); });
    host.querySelector("[data-obm-payform]").addEventListener("submit", function (e) {
      e.preventDefault(); onPaySubmit(host, tier, period);
    });
  }
  function onPaySubmit(host, tier, period) {
    if (!_stripe || !_elements) return;
    var submitBtn = host.querySelector("[data-obm-paysubmit]");
    var errBox = host.querySelector("[data-obm-payerr]");
    function setPayErr(m) { if (!errBox) return; if (!m) { errBox.style.display = "none"; return; } errBox.style.display = ""; errBox.textContent = m; }
    submitBtn.disabled = true; submitBtn.textContent = tx("billSubmitBusy"); setPayErr("");
    _stripe.confirmSetup({ elements: _elements, redirect: "if_required" }).then(function (res) {
      if (res.error) {
        // Stripe's own message (declines etc.) — do NOT translate
        setPayErr(res.error.message || tx("billErr"));
        submitBtn.disabled = false; submitBtn.setAttribute("data-k", "billSubmit"); submitBtn.innerHTML = tx("billSubmit");
        return;
      }
      var si = res.setupIntent;
      if (!si || !si.id) { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx("billSubmit"); return; }
      getAccessToken().then(function (token) {
        var headers = { "Content-Type": "application/json" };
        if (token) headers["Authorization"] = "Bearer " + token;
        return fetch(apiBase() + "/api/billing/subscribe/complete", {
          method: "POST", credentials: "include", headers: headers,
          body: JSON.stringify({ setup_intent_id: si.id, tier: tier, interval: period })
        });
      }).then(function (r) {
        if (!r.ok) { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx("billSubmit"); return; }
        return r.json().catch(function () { return {}; }).then(function (data) {
          S.trialActive = true;
          S.trialEnd = (data && typeof data.trial_end === "number") ? data.trial_end : null;
          go(STEP_DONE);
        });
      }).catch(function () { setPayErr(tx("billErr")); submitBtn.disabled = false; submitBtn.innerHTML = tx("billSubmit"); });
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
    if (S.trialActive) {
      var tierNm = tx(S.plan === "pro" ? "planPro" : "planInsider");
      var l2 = h("p", "obm-done-line");
      l2.innerHTML = escLine(LEX.doneTrial, { "__T__": esc(tierNm), "__D__": esc(fmtDate(doneTrialDate())) });
      bodyBox.appendChild(l2);
    }
    if (!S.confirmPending && !S.trialActive) { bodyBox.appendChild(T("p", "obm-done-line", "doneReady")); }
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
  function _pfx() { return location.pathname.indexOf("/sectors/") > -1 ? "../" : ""; }
  function ensureAssets() {
    if (!document.querySelector('link[href*="onboard.css"]')) {
      var l = document.createElement("link"); l.rel = "stylesheet"; l.href = _pfx() + "onboard.css";
      document.head.appendChild(l);
    }
    if (!document.querySelector('link[href*="Archivo+Expanded"]')) {
      var f = document.createElement("link"); f.rel = "stylesheet";
      f.href = "https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800;900&family=Archivo+Expanded:wght@600;700;800;900&family=Inter:wght@400;450;500;600;700&display=swap";
      document.head.appendChild(f);
    }
  }
  var _lastFocus = null;
  function openSheet(mode, opts) {
    if (mode === "upgrade") { openUpgrade(opts || {}); return; }
    ensureAssets();
    build();
    S.mode = mode || "signup";
    if (opts && opts.plan && (opts.plan === "free" || opts.plan === "insider" || opts.plan === "pro")) S.plan = opts.plan;
    if (opts && opts.period && (opts.period === "monthly" || opts.period === "annual")) S.period = opts.period;
    if (opts && opts.resume) S.step = STEP_PREFS;
    if (S.mode === "signin") S.step = STEP_ACCOUNT;
    S.open = true;
    _lastFocus = document.activeElement;
    el.scrim.style.display = "flex";
    // next frame → transition in
    requestAnimationFrame(function () { el.scrim.classList.add("obm-open"); });
    document.documentElement.style.overflow = "hidden";
    render();
    redrawDesk();
    stashSave();
  }
  // The registration wall 302s guests to /?signin=1&ret=<path>; after a
  // successful sign-in (or finishing signup) return them to that page.
  // Same-origin PATHS only — never navigate off-origin from a query param.
  function retTarget() {
    try {
      var p = new URLSearchParams(location.search).get("ret");
      if (p && p.charAt(0) === "/" && p.slice(0, 2) !== "//") return p;
    } catch (e) { /* ignore */ }
    return "";
  }
  // Post-login landing: the ?ret= wall target if present, else the prefix-aware
  // /start.html (pages under /sectors/ need "../"). A signed-in user must never
  // be dropped back on the marketing page.
  function loginDest() { return retTarget() || (_pfx() + "start.html"); }
  function closeSheet() {
    if (!el.scrim) return;
    S.open = false;
    el.scrim.classList.remove("obm-open");
    document.documentElement.style.overflow = "";
    // keep stash unless cleared by Done; hide after transition
    setTimeout(function () { if (!S.open) el.scrim.style.display = "none"; }, 220);
    if (_lastFocus && _lastFocus.focus) { try { _lastFocus.focus(); } catch (e) {} }
    stashSave();
  }
  function requestClose() { closeSheet(); }

  // ESC + focus trap
  document.addEventListener("keydown", function (e) {
    if (!S.open || !el.sheet) return;
    if (e.key === "Escape") { e.preventDefault(); requestClose(); return; }
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
    var plan = sp.get("plan"), period = sp.get("period");
    return {
      mode: (wantSignin && !wantSignup) ? "signin" : "signup",
      plan: (plan === "insider" || plan === "pro" || plan === "free") ? plan : null,
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
    openDash: ["Open the dashboard", "打开仪表盘"],
    included: ["Included", "已包含"],
    current: ["Current plan", "当前方案"]
  };
  function _byId(id) { return document.getElementById(id); }

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
    var tier = me.tier || "free";
    var interval = me.interval || null;
    var best = (tier === "unlimited") || (tier === "pro" && interval === "annual");
    var start = _pfx() + "start.html";

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

    // 4) pricing-card CTAs
    document.querySelectorAll(".js-plan-cta").forEach(function (pc) {
      var plan = pc.getAttribute("data-plan");
      if (plan === "free") {
        // Free card: inert "Current plan" when free, else "Included" (paid tiers include Free)
        makeInert(pc, tier === "free" ? "current" : "included");
      } else {
        // paid card → open upgrade preselecting that plan (or best-plan panel)
        pc.setAttribute("href", start);
        pc.__upgradePlan = { plan: plan, period: pc.getAttribute("data-period") || "annual" };
        bindPlanCta(pc);
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
    pc.addEventListener("click", function (e) { e.preventDefault(); openSheet("upgrade", pc.__upgradePlan || {}); });
  }
  function makeInert(pc, key) {
    paintBilingual(pc, UPCHROME[key][0], UPCHROME[key][1]);
    pc.setAttribute("aria-disabled", "true");
    pc.removeAttribute("href");
    pc.style.pointerEvents = "none"; pc.style.opacity = ".65";
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

  // Entry: sniff the cookie; if signed-in, resolve /api/me and paint. Fail quiet.
  function initAuthChrome() {
    // Only the landing has these ids; bail on macro pages (this file's other
    // consumers never render the landing nav).
    if (!_byId("nav-cta") && !_byId("gp-acct-out")) return;
    wireGearAccount();                         // always (signed-out gear needs its buttons)
    if (!hasSessionCookie()) return;           // guest → default signed-out markup, zero network
    // resolve the broker so MDXAuth.user() is available for the avatar, then /api/me
    ensureAuthBroker().then(function () {
      fetchMe(false).then(function (me) {
        if (!me) return;                       // token expired / 401 → leave signed-out chrome
        applyAuthChrome(me);                    // re-applies LANG over the nodes it rewrites
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
        if (resumeStash.plan) S.plan = resumeStash.plan;
        if (resumeStash.period) S.period = resumeStash.period;
        if (resumeStash.prefs) S.prefs = resumeStash.prefs;
      }
      // Google-OAuth return: a signin-mode round-trip lands on the desk (ret wins),
      // not back in the sheet; a pending-upgrade round-trip resumes the upgrade panel.
      if (intent.resume && resumeStash) {
        if (resumeStash.pendingUpgrade) { stripOnboardParams(); openSheet("upgrade", resumeStash.upgradeOpts || {}); return; }
        if (resumeStash.mode === "signin") { stripOnboardParams(); location.href = loginDest(); return; }
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
      S.prefs = st.prefs || S.prefs; S.plan = st.plan || S.plan; S.period = st.period || S.period;
      S.confirmPending = !!st.confirmPending; S.trialActive = !!st.trialActive; S.trialEnd = (typeof st.trialEnd === "number") ? st.trialEnd : null;
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
  window.MMOnboard = { open: openSheet, close: closeSheet, applyChrome: applyAuthChrome };
})();
