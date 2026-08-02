(function(){
  'use strict';
  var input=document.getElementById('wire-search');
  var grid=document.getElementById('wire-grid');
  if(!input||!grid)return;
  var cards=Array.prototype.slice.call(grid.querySelectorAll('[data-wire-card]'));
  var filters=Array.prototype.slice.call(document.querySelectorAll('[data-wire-filter]'));
  var empty=document.getElementById('wire-empty');
  var results=document.getElementById('wire-results');
  var current='all';
  function zh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  function resultText(count){
    if(zh())return count===1?'本页显示 1 条记录。':'本页显示 '+count+' 条记录。';
    return count===1?'Showing 1 record on this page.':'Showing '+count+' records on this page.';
  }
  function syncLanguage(){
    input.setAttribute('placeholder',input.getAttribute(zh()?'data-placeholder-zh':'data-placeholder-en')||'');
    apply();
  }
  function apply(){
    var query=(input.value||'').trim().toLowerCase();
    var count=0;
    cards.forEach(function(card){
      var text=card.getAttribute('data-search')||'';
      var categories=card.getAttribute('data-categories')||'';
      var match=(!query||text.indexOf(query)!==-1)&&(current==='all'||categories.indexOf(current)!==-1);
      card.hidden=!match;
      if(match)count++;
    });
    if(empty)empty.hidden=count!==0;
    if(results)results.textContent=resultText(count);
  }
  input.addEventListener('input',apply);
  filters.forEach(function(button){button.addEventListener('click',function(){
    current=button.getAttribute('data-wire-filter')||'all';
    filters.forEach(function(item){var active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-pressed',active?'true':'false');});
    apply();
  });});
  document.addEventListener('langchange',syncLanguage);
  syncLanguage();
})();
