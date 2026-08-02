(function () {
  'use strict';

  // Apply stored chrome preferences before CSS paints. The shared theme runtime
  // owns subsequent changes and emits `langchange`; this tiny external boot
  // keeps the premium desk CSP-friendly and prevents an English/theme flash.
  try {
    var theme = localStorage.getItem('theme');
    var lang = localStorage.getItem('lang');
    if (theme === 'dark' || theme === 'light') {
      document.documentElement.setAttribute('data-theme', theme);
    }
    if (lang === 'en' || lang === 'zh') {
      document.documentElement.setAttribute('data-lang', lang);
      document.documentElement.lang = lang === 'zh' ? 'zh-CN' : 'en';
    }
  } catch (error) {
    // Storage can be unavailable in hardened browsing contexts; the document's
    // English/dark defaults remain a complete, readable fallback.
  }
}());
