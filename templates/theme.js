/* Theme toggle, shared across pages. The no-flash init runs inline in <head>;
   this file wires the button. */
(function () {
  function cur() { return document.documentElement.getAttribute('data-theme') || 'dark'; }
  function set(t) {
    document.documentElement.setAttribute('data-theme', t);
    try { localStorage.setItem('theme', t); } catch (e) {}
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.textContent = t === 'light' ? '🌙 Dark' : '☀️ Light';
    });
    // let visual widgets recolor against the new CSS variables
    if (window.hydrateMTF) window.hydrateMTF();
    document.dispatchEvent(new CustomEvent('themechange', { detail: t }));
  }
  window.toggleTheme = function () { set(cur() === 'light' ? 'dark' : 'light'); };
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('.theme-btn').forEach(function (b) {
      b.addEventListener('click', window.toggleTheme);
      b.textContent = cur() === 'light' ? '🌙 Dark' : '☀️ Light';
    });
  });
})();
