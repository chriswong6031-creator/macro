(function(){
  'use strict';
  var input=document.getElementById('wire-search');
  var grid=document.getElementById('wire-grid');
  function zh(){return document.documentElement.getAttribute('data-lang')==='zh';}
  if(input&&grid){
    var cards=Array.prototype.slice.call(grid.querySelectorAll('[data-wire-card]'));
    var filters=Array.prototype.slice.call(document.querySelectorAll('[data-wire-filter]'));
    var empty=document.getElementById('wire-empty');
    var results=document.getElementById('wire-results');
    var current='all';
    function resultText(count){
      if(zh())return count===1?'本页显示 1 条记录。':'本页显示 '+count+' 条记录。';
      return count===1?'Showing 1 record on this page.':'Showing '+count+' records on this page.';
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
    function syncLanguage(){
      input.setAttribute('placeholder',input.getAttribute(zh()?'data-placeholder-zh':'data-placeholder-en')||'');
      apply();
    }
    input.addEventListener('input',apply);
    filters.forEach(function(button){button.addEventListener('click',function(){
      current=button.getAttribute('data-wire-filter')||'all';
      filters.forEach(function(item){var active=item===button;item.classList.toggle('active',active);item.setAttribute('aria-pressed',active?'true':'false');});
      apply();
    });});
    document.addEventListener('langchange',syncLanguage);
    syncLanguage();
  }

  var gateState=document.getElementById('earnings-gate-state');
  if(!gateState)return;
  var gate;
  try{gate=JSON.parse(gateState.textContent||'null');}catch(e){gate=null;}
  if(!gate||!gate.payload)return;

  function whenAuthSettled(){
    return new Promise(function(resolve){
      var done=false;
      function go(){if(done)return;done=true;resolve();}
      if(window.MDXAuth){go();return;}
      window.addEventListener('mdx-auth',go,{once:true});
      setTimeout(go,3000);
    });
  }
  function accessToken(){
    try{
      if(window.MDXAuth&&window.MDXAuth.client&&window.MDXAuth.hasSession&&window.MDXAuth.hasSession()){
        return window.MDXAuth.client()
          .then(function(sb){return sb.auth.getSession();})
          .then(function(result){
            var session=result&&result.data&&result.data.session;
            if(!session||!session.access_token)throw new Error('signed out');
            return session.access_token;
          });
      }
    }catch(e){}
    return Promise.reject(new Error('signed out'));
  }
  function hydrate(payload){
    if(!payload||payload.schema!=='earnings.tier_payload/v1'||payload.slug!==gate.slug)throw new Error('invalid payload');
    var facts=document.querySelector('.ewa-facts');
    var receiptBody=document.querySelector('.ewa-receipts tbody');
    if(facts&&payload.facts_html)facts.insertAdjacentHTML('beforeend',payload.facts_html);
    if(receiptBody&&payload.receipt_rows_html)receiptBody.insertAdjacentHTML('beforeend',payload.receipt_rows_html);
    var wall=document.getElementById('earnings-member-gate');
    if(wall)wall.remove();
    document.documentElement.setAttribute('data-earnings-member','unlocked');
  }
  function revealSignin(){
    var button=document.querySelector('[data-earnings-signin]');
    var signedIn=false;
    try{signedIn=!!(window.MDXAuth&&window.MDXAuth.user&&window.MDXAuth.user());}catch(e){}
    if(!button||signedIn)return;
    button.hidden=false;
    button.addEventListener('click',function(){
      try{window.MDXAuth.open('signin');}catch(e){location.href='../../plans.html';}
    },{once:true});
  }
  whenAuthSettled()
    .then(accessToken)
    .then(function(token){return fetch(gate.payload,{
      credentials:'same-origin',
      cache:'no-store',
      headers:{'Accept':'application/json','Authorization':'Bearer '+token}
    });})
    .then(function(response){if(!response||!response.ok)throw new Error('locked');return response.json();})
    .then(hydrate)
    .catch(revealSignin);
})();
