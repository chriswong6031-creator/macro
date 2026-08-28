(function(global){
  'use strict';

  /*
   * The award and subaward rails intentionally have separate immutable
   * generations: grd1-* describes primes/actions and grsd1-* describes
   * receipt-bound subaward observations. Never compare them to each other.
   */
  /* /api/government-revenue/* is a paid (site_full) surface and authenticates on
   * the Authorization header, not the session cookie, so every read has to carry
   * the Supabase bearer token. Same shape as capital_structure.js; shared by both
   * factories below. Resolved per call, not at load time, because theme.js (which
   * defines MDXAuth) is loaded after this script. */
  function withAuth(headers){
    headers=headers||{};
    if(!(global.MDXAuth&&global.MDXAuth.client))return Promise.resolve(headers);
    return global.MDXAuth.client().then(function(client){return client.auth.getSession()}).then(function(result){
      var token=result&&result.data&&result.data.session&&result.data.session.access_token;
      if(token)headers.Authorization='Bearer '+token;
      return headers;
    }).catch(function(){return headers});
  }
  function authSettled(){
    if(global.__govrevAuthSettled)return true;
    try{if(global.MDXAuth&&typeof global.MDXAuth.enabled==='function'&&!global.MDXAuth.enabled())return true;}catch(e){}
    return false;
  }
  function markAuthSettled(){global.__govrevAuthSettled=true;}

  global.createGovernmentRevenueDossier=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,factCell=api.factCell,hostFor=api.host,getSelected=api.selected;
    var epoch=0,session=null,searchTimer=null;
    var SUBAWARD_PAGE_SIZE=25;

    function field(x,keys){x=obj(x)?x:{};for(var i=0;i<keys.length;i++)if(x[keys[i]]!=null&&x[keys[i]]!=='')return x[keys[i]];return null}
    function fetchPage(route,rail){
      var prefix=rail==='subaward'?'grsd1-':rail==='idv'?'griv1-':'grd1-';
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      return withAuth({Accept:'application/json'}).then(function(headers){
        return global.fetch('/api/government-revenue/'+route,{credentials:'same-origin',headers:headers});
      }).then(function(r){if(!r.ok)throw new Error('http_'+r.status);return r.json()}).then(function(x){
        if(!obj(x)||x.schema_version!=='1.0.0'||!new RegExp('^'+prefix+'[a-f0-9]{24}$').test(text(x.content_id,'')))throw new Error('contract');
        return x;
      });
    }
    function name(a){return text(field(a,['description'])||field(obj(a.program)?a.program:{},['name','description','title'])||field(a,['piid','award_key']),tr('Official award record','官方授标记录'))}
    function recipient(a){var x=obj(a.recipient)?a.recipient:{};return text(field(x,['name','legal_name'])||field(a,['recipient_name']),tr('Recipient not reported','未报告收款方'))}
    function identity(a){return obj(a.identity)?a.identity:{}}
    function agency(a){var x=obj(a.agency)?a.agency:{};return text(field(x,['awarding_subagency','awarding','funding_subagency','funding','office_name','subagency_name','department_name','name'])||field(a,['awarding_agency']),tr('Agency not reported','未报告机构'))}
    function amount(a,key){return field(obj(a.values)?a.values:{},[key])}
    function shellMode(open){if(typeof api.shellMode==='function')api.shellMode(!!open)}
    function clearSearchTimer(){if(searchTimer){global.clearTimeout(searchTimer);searchTimer=null}}
    function leaveAwardView(s){
      clearSearchTimer();if(!s)return;
      s.awardViewToken=(n(s.awardViewToken)||0)+1;s.awardViewActive=false;s.subawardLoading=false;
    }
    function enterAwardView(s){
      clearSearchTimer();s.awardViewToken=(n(s.awardViewToken)||0)+1;s.awardViewActive=true;return s.awardViewToken;
    }
    function isActiveAwardView(s,token){return session===s&&s.awardViewActive===true&&s.awardViewToken===token}
    function cards(rows){return arr(rows).filter(obj).map(function(a){var id=identity(a);return'<button type="button" class="award-card" data-award-key="'+esc(text(a.award_key,''))+'"><span><strong>'+esc(name(a))+'</strong><small>'+esc(text(id.piid,id.generated_award_id))+' · '+esc(agency(a))+'</small></span><span class="award-money">'+esc(money(amount(a,'obligated')))+'<small>'+esc(tr('obligated','已承诺义务'))+'</small></span></button>'}).join('')}

    function bind(host){
      host.querySelectorAll('[data-award-key]').forEach(function(b){b.addEventListener('click',function(){loadAward(b.dataset.awardKey)})});
      var more=host.querySelector('[data-more-awards]');if(more)more.addEventListener('click',moreAwards);
      var back=host.querySelector('[data-dossier-back]');if(back)back.addEventListener('click',renderBook);
      var actions=host.querySelector('[data-more-actions]');if(actions)actions.addEventListener('click',moreActions);
      bindSubawards(host);
      bindIdvRelationships(host);
    }

    function renderBook(){
      var s=session,host=hostFor();if(!s||!host)return;
      leaveAwardView(s);
      shellMode(false);
      var c=s.company||{},coverage=obj(s.list.source_coverage)?s.list.source_coverage:{},fresh=text((s.list.freshness||{}).status,'unavailable'),scope=text(coverage.scope,tr('bounded official award-detail sample','受限的官方授标明细样本')),shown=s.awards.length,total=n(s.list.total);
      host.innerHTML='<div class="dossier-status"><span><b>'+esc(tr('Official award book','官方授标档案'))+'</b><span>'+esc(scope)+' · '+esc(tr('source state ','来源状态 ')+fresh)+'</span></span><span class="dossier-count">'+esc(shown+' / '+text(total,shown))+'</span></div>'+(shown?cards(s.awards):'<div class="dossier-empty">'+esc(tr('No official award record is visible for this company in the bounded source cut.','当前受限来源截点中没有该公司的可见官方授标记录。'))+'</div>')+(s.next?'<button class="tool-btn" type="button" data-more-awards>'+esc(tr('Load more awards','加载更多授标'))+'</button>':'')+'<div class="limit-copy">'+esc(tr('Stable award identity prefers the generated USAspending award ID. A PIID alone never collapses separate awards.','稳定授标身份优先使用 USAspending 生成授标 ID。仅凭 PIID 绝不会合并不同授标。'))+(c.action_count!=null?' '+esc(tr('Covered actions: ','覆盖行动：')+c.action_count)+'.':'')+'</div>';
      bind(host);
    }

    function loadCompany(ticker){
      var host=hostFor(),ticket=++epoch;ticker=text(ticker,'');if(!host||!/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker))return;
      leaveAwardView(session);session=null;
      shellMode(false);
      host.innerHTML='<div class="dossier-status"><span><b>'+esc(tr('Opening official award book','正在打开官方授标档案'))+'</b><span>'+esc(tr('Loading bounded award records and source coverage…','正在加载受限授标记录与来源覆盖…'))+'</span></span><span class="dossier-count">•••</span></div>';
      Promise.all([fetchPage('dossier/company/'+encodeURIComponent(ticker),'prime'),fetchPage('company/'+encodeURIComponent(ticker)+'/awards?limit=8','prime')]).then(function(x){
        if(ticket!==epoch||getSelected()!=='company:'+ticker)return;
        if(x[0].content_id!==x[1].content_id)throw new Error('generation_mismatch');
        session={ticker:ticker,content_id:x[0].content_id,company:x[0].company||{},list:x[1],awards:arr(x[1].results).filter(obj),next:x[1].next_cursor,award:null,actions:[],actionNext:null,subawards:[],subawardNext:null,subawardTotal:0,subawardContentId:null,subawardCoverage:null,subawardQuery:'',subawardCursors:[null],subawardPage:0,subawardError:false,subawardLoading:false,idvRelationships:[],idvContentId:null,idvCoverage:null,idvAwardCoverage:null,idvSelection:null,idvError:false,awardViewToken:0,awardViewActive:false};
        renderBook();
      }).catch(function(){if(ticket===epoch&&host)host.innerHTML='<div class="dossier-error"><strong>'+esc(tr('Award book unavailable','授标档案不可用'))+'</strong><br>'+esc(tr('The compact company context remains visible. No dossier row was reconstructed in the browser.','精简公司情境仍然可见。浏览器未重建任何档案记录。'))+'</div>'})
    }

    function moreAwards(){
      var s=session,host=hostFor(),companyEpoch=epoch,bookToken=s&&s.awardViewToken;if(!s||!s.next||!host)return;
      fetchPage('company/'+encodeURIComponent(s.ticker)+'/awards?limit=8&cursor='+encodeURIComponent(s.next),'prime').then(function(page){
        if(!session||session!==s||companyEpoch!==epoch||s.awardViewActive||s.awardViewToken!==bookToken||page.content_id!==s.content_id)throw new Error('generation_mismatch');
        s.awards=s.awards.concat(arr(page.results).filter(obj));s.next=page.next_cursor;renderBook();
      }).catch(function(){if(session===s&&companyEpoch===epoch&&!s.awardViewActive&&s.awardViewToken===bookToken)host.insertAdjacentHTML('beforeend','<div class="dossier-error">'+esc(tr('The next award page could not be verified.','下一页授标记录无法核验。'))+'</div>')})
    }

    function actionRows(rows){return arr(rows).filter(obj).map(function(a){var effective=field(a,['effective_at','action_date']),known=field(a,['known_at']),value=field(a,['obligation','federal_action_obligation','obligation_delta','amount']);return'<div class="action-row"><time>'+esc(date(effective))+'</time><span><strong>'+esc(text(field(a,['action_type_description','description','modification_number','action_id']),tr('Official action','官方行动')))+'</strong><span class="dual-clock">'+esc(tr('Effective ','生效 ')+text(effective)+' · '+tr('known ','获知 ')+text(known))+'</span></span><b>'+esc(money(value))+'</b></div>'}).join('')}
    function subawardCoverage(s){return obj(s&&s.subawardCoverage)?s.subawardCoverage:{}}
    function coverageClass(coverage){var status=text(coverage.status,'unavailable');return status==='ok'?'ok':status==='partial'?'warn':'muted'}
    function coverageCopy(coverage){
      var status=text(coverage.status,'unavailable'),state=text(coverage.collection_state,''),reported=n(coverage.reported_count),published=n(coverage.records_published);
      if(status==='partial'&&coverage.count_verified===true)return{headline:tr('Count verified · details not collected','数量已核验 · 未采集明细'),body:tr('USAspending reported ','USAspending 报告 ')+text(reported,0)+tr(' subawards. Detail rows were intentionally not fetched under the bounded collection policy.',' 条分包；根据受限采集策略，明细行未被采集。')};
      if(status==='ok'&&state==='zero')return{headline:tr('No subawards reported','未报告分包'),body:tr('The receipt-bound count is zero for this exact prime award.','该主合同的凭证绑定数量为零。')};
      if(status==='ok')return{headline:text(published,0)+(published===1?tr(' verified detail',' 条已核验明细'):tr(' verified details',' 条已核验明细')),body:tr('USAspending count and stored details are receipt-bound for this exact prime award.','USAspending 数量与存储明细均已与该主合同的凭证绑定。')};
      return{headline:tr('Not collected for this award','此主合同未纳入采集'),body:tr('No subaward coverage was selected in this bounded collector generation.','在本次受限采集代次中未选择该主合同的分包覆盖。')};
    }
    function subawardSourceAmount(row){var amountValue=obj(row.reported_amount)?row.reported_amount.amount:null;return money(amountValue)}
    function subawardRows(rows){return arr(rows).filter(obj).map(function(row){var id=identity(row),desc=text(row.description,tr('No description reported','未报告描述')),suffix=row.description_truncated?tr(' (truncated)','（已截断）'):'';return'<tr><td data-label="'+esc(tr('Subrecipient','分包接收方'))+'"><strong>'+esc(text(row.subawardee_name,tr('Subrecipient not reported','未报告分包接收方')))+'</strong><small>'+esc(text(id.displayed_subaward_number,id.source_subaward_id))+'</small></td><td data-label="'+esc(tr('Reported amount','报告金额'))+'"><b>'+esc(subawardSourceAmount(row))+'</b><small>'+esc(tr('reported amount','报告金额'))+'</small></td><td data-label="'+esc(tr('Action date','行动日期'))+'">'+esc(date((row.dates||{}).action_date))+'</td><td data-label="'+esc(tr('Description','说明'))+'">'+esc(desc+suffix)+'</td><td data-label="'+esc(tr('Evidence','凭证'))+'"><button type="button" class="tool-btn" data-subaward-key="'+esc(text(row.subaward_key,''))+'">'+esc(tr('Evidence','凭证'))+'</button></td></tr>'}).join('')}
    function subawardPager(s){
      var total=n(s.subawardTotal),shown=s.subawards.length,start=shown?s.subawardPage*SUBAWARD_PAGE_SIZE+1:0,end=shown?start+shown-1:0,previous=s.subawardPage>0,hasNext=!!s.subawardNext;
      return'<div class="subaward-pager"><span aria-live="polite">'+esc(shown?start+'–'+end+tr(' of ',' / ')+text(total,shown)+tr(' detailed records',' 条明细记录'):tr('No detailed records in this view','此视图中无明细记录'))+'</span><span><button type="button" class="tool-btn" data-subaward-prev'+(previous?'':' disabled')+'>'+esc(tr('Previous','上一页'))+'</button><button type="button" class="tool-btn" data-subaward-next'+(hasNext?'':' disabled')+'>'+esc(tr('Next','下一页'))+'</button></span></div>';
    }
    function renderSubawardLedger(s){
      var coverage=subawardCoverage(s),copy=coverageCopy(coverage),status=text(coverage.status,'unavailable'),partial=status==='partial'&&coverage.count_verified===true;
      var header='<section class="subaward-ledger" aria-labelledby="subawardLedgerTitle"><div class="inspect-label" id="subawardLedgerTitle">'+esc(tr('Subaward ledger','分包账本'))+'</div><div class="subaward-coverage '+esc(coverageClass(coverage))+'" role="status" aria-live="polite"><strong>'+esc(copy.headline)+'</strong><span>'+esc(copy.body)+'</span></div>';
      if(s.subawardLoading)return header+'<div class="dossier-status" aria-busy="true"><span><b>'+esc(tr('Refreshing subaward details','正在刷新分包明细'))+'</b><span>'+esc(tr('The server is applying the subrecipient search.','服务器正在应用分包接收方搜索。'))+'</span></span><span class="dossier-count">•••</span></div></section>';
      if(s.subawardError)return header+'<div class="dossier-error"><strong>'+esc(tr('Subaward ledger unavailable','分包账本不可用'))+'</strong><br>'+esc(tr('Award and action evidence remains available.','授标与行动证据仍然可用。'))+'</div></section>';
      if(partial)return header+'<div class="limit-copy">'+esc(tr('This is a verified count-only state, not a zero-result table.','这是已核验的仅数量状态，并非零结果表格。'))+'</div></section>';
      if(status!=='ok')return header+'<div class="dossier-empty">'+esc(tr('No subaward detail is available for this award in the active collection cut.','当前采集截点中没有该主合同的可用分包明细。'))+'</div></section>';
      if(text(coverage.collection_state,'')==='zero')return header+'</section>';
      var tools='<div class="subaward-tools"><label>'+esc(tr('Search subrecipient','搜索分包接收方'))+'<input class="field" type="search" data-subaward-search value="'+esc(s.subawardQuery)+'" autocomplete="off" placeholder="'+esc(tr('Name','名称'))+'" aria-controls="subawardTable"></label><span class="limit-copy">'+esc(tr('A USAspending-reported subaward observation—not a federal obligation, prime value, revenue, backlog, cash flow, or an additive total.','USAspending 报告的分包观测，并非联邦义务额、主合同价值、收入、积压、现金流或可加总金额。'))+'</span></div>';
      if(!s.subawards.length)return header+tools+'<div class="dossier-empty">'+esc(tr('No reported subawards match this view.','当前视图没有匹配的已报告分包。'))+'</div></section>';
      return header+tools+'<div class="subaward-table-wrap"><table class="subaward-table" id="subawardTable"><caption>'+esc(tr('Receipt-bound USAspending subaward details','与凭证绑定的 USAspending 分包明细'))+'</caption><thead><tr><th scope="col">'+esc(tr('Subrecipient','分包接收方'))+'</th><th scope="col">'+esc(tr('Reported amount','报告金额'))+'</th><th scope="col">'+esc(tr('Action date','行动日期'))+'</th><th scope="col">'+esc(tr('Description','说明'))+'</th><th scope="col"><span class="sr-only">'+esc(tr('Evidence','凭证'))+'</span></th></tr></thead><tbody>'+subawardRows(s.subawards)+'</tbody></table></div>'+subawardPager(s)+'</section>';
    }

    function idvCoverage(s){return obj(s&&s.idvCoverage)?s.idvCoverage:{}}
    function idvAwardCoverage(s){return obj(s&&s.idvAwardCoverage)?s.idvAwardCoverage:{}}
    function idvSelection(s){return obj(s&&s.idvSelection)?s.idvSelection:{}}
    function idvStatusCopy(s){var coverage=idvCoverage(s),award=idvAwardCoverage(s),status=text(coverage.status,'unavailable'),selected=n(award.selected_parent_count);if(status==='ok'&&award.status==='observed')return{headline:tr('Exact relationship observed','已观测精确关系'),body:tr('Only exact generated-ID award-to-IDV observations are shown.','仅展示生成 ID 精确匹配的授标至 IDV 观测。')};if(status==='ok'&&award.status==='not_observed')return{headline:tr('No exact bridge in this bounded cut','此受限截点中无精确桥接'),body:tr('No match was observed among ','在 ')+text(selected,0)+tr(' selected parent IDVs; this is not evidence that no IDV relationship exists.',' 个已选父级 IDV 中未观察到匹配；这不代表 IDV 关系不存在。')};if(status==='partial')return{headline:tr('Qualified relationship coverage','关系覆盖受限'),body:text(coverage.reason,tr('The active collection cut is qualified.','当前采集截点存在限制。'))};return{headline:tr('Relationship rail unavailable','关系链路不可用'),body:text(coverage.reason,tr('No IDV relationship result was inferred.','未推断任何 IDV 关系结果。'))}}
    function idvSelectionCopy(s){var selection=idvSelection(s);if(selection.status!=='verified')return'';return'<div class="limit-copy">'+esc(tr('Bounded selection ','受限选择 ')+text(selection.selection_manifest_id)+tr(' · selected parents ',' · 已选父级 ')+text(selection.selected_parent_count,0)+tr(' · non-exhaustive.',' · 非穷尽。'))+'</div>'}
    function idvDepth(value){return value==='direct_child'?tr('Direct child of IDV','IDV 直接子项'):tr('Grandchild award in source activity','来源活动中的孙级授标')}
    function idvRows(rows){return arr(rows).filter(obj).map(function(row){var identity=obj(row.identity)?row.identity:{},dates=obj(row.dates)?row.dates:{};return'<article class="idv-relationship"><div class="idv-relationship-top"><span class="truth official">'+esc(idvDepth(identity.relationship_depth))+'</span><button class="tool-btn" type="button" data-idv-key="'+esc(text(row.relationship_key,''))+'">'+esc(tr('Evidence','凭证'))+'</button></div><strong>'+esc(text(identity.idv_generated_award_id))+'</strong><div class="idv-relationship-meta"><span>'+esc(tr('Recipient ','收款方 ')+text(row.recipient_name,tr('not reported','未报告')))+' · '+esc(tr('Agency ','机构 ')+text(row.agency,tr('not reported','未报告')))+' </span><span>'+esc(tr('Start ','开始 ')+date(dates.start_date)+' · '+tr('End ','结束 ')+date(dates.potential_end_date))+'</span></div></article>'}).join('')}
    function idvEvidenceHtml(row){var identity=obj(row.identity)?row.identity:{},dates=obj(row.dates)?row.dates:{},provenance=obj(row.provenance)?row.provenance:{},source=obj(row.source)?row.source:{},url=safeUrl(source.activity_url);var html='<article class="receipt"><div class="receipt-kind">'+esc(tr('USAspending IDV activity relationship','USAspending IDV 活动关系'))+'</div><h3>'+esc(text(identity.idv_generated_award_id))+'</h3><p>'+esc(tr('Source-native relationship evidence only. It does not establish a vehicle seat, participation, utilization, conversion, award value, revenue, backlog, or issuer attribution.','仅为来源原生关系证据。它不证明合同载具席位、参与、使用、转化、授标价值、收入、积压或发行人归属。'))+'</p><div class="receipt-code">'+esc('relationship_key: '+text(row.relationship_key)+'\nchild_award_key: '+text(row.child_award_key)+'\nparent_idv: '+text(identity.idv_generated_award_id)+'\nchild_award: '+text(identity.child_generated_award_id)+'\nrelationship_depth: '+text(identity.relationship_depth)+'\nparent_piid: '+text(identity.parent_piid)+'\nchild_piid: '+text(identity.child_piid)+'\nstart_date: '+text(dates.start_date)+'\npotential_end_date: '+text(dates.potential_end_date))+'</div></article>';
      html+='<article class="receipt"><div class="receipt-kind">'+esc(tr('Receipt provenance','凭证出处'))+'</div><div class="receipt-code">'+esc('receipt_id: '+text(provenance.receipt_id)+'\nresponse_sha256: '+text(provenance.response_sha256)+'\nsource_record_count: '+text(provenance.source_record_count)+'\nknown_at: '+text(provenance.known_at)+'\ncollection_scope_ticker: '+text(provenance.collection_scope_ticker))+'</div><p>'+esc(arr(provenance.limitations).join(' · '))+'</p>'+(url?'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open USAspending activity source','打开 USAspending 活动来源'))+'</b><span>↗</span></a>':'')+'</article>';
      return html;
    }
    function renderIdvRelationships(s){var coverage=idvCoverage(s),copy=idvStatusCopy(s),status=text(coverage.status,'unavailable'),rows=arr(s.idvRelationships).filter(obj),header='<section class="idv-relationships" aria-labelledby="idvRelationshipTitle"><div class="inspect-label" id="idvRelationshipTitle">'+esc(tr('Observed IDV relationships','已观测 IDV 关系'))+'</div><div class="idv-coverage '+esc(coverageClass(coverage))+'" role="status" aria-live="polite"><strong>'+esc(copy.headline)+'</strong><span>'+esc(copy.body)+'</span></div>'+idvSelectionCopy(s);
      if(s.idvError)return header+'<div class="dossier-error"><strong>'+esc(tr('IDV relationship rail unavailable','IDV 关系链路不可用'))+'</strong><br>'+esc(tr('Award, action and subaward evidence remains available.','授标、行动及分包证据仍可用。'))+'</div></section>';
      if(!rows.length)return header+'<div class="dossier-empty">'+esc(status==='ok'?tr('Bounded non-observation only—not evidence that this award has no IDV relationship.','仅为受限范围内未观察到，并非该授标不存在 IDV 关系的证据。'):tr('No IDV relationship detail is available for this exact award in the active collection cut.','当前采集截点中没有该精确授标的可用 IDV 关系明细。'))+'</div></section>';
      return header+'<div class="idv-list">'+idvRows(rows)+'</div><div class="limit-copy">'+esc(tr('Relationship-only: not vehicle seat, participation, utilization, conversion, value, revenue, backlog, or issuer attribution.','仅关系：并非合同载具席位、参与、使用、转化、价值、收入、积压或发行人归属。'))+'</div></section>';
    }
    function openIdvEvidence(key,focus){var s=session,row=s&&arr(s.idvRelationships).find(function(item){return obj(item)&&item.relationship_key===key});if(!s||!s.awardViewActive||!row||typeof api.openEvidenceDrawer!=='function')return;api.openEvidenceDrawer({title:tr('IDV relationship evidence','IDV 关系凭证'),html:idvEvidenceHtml(row),focus:focus})}
    function bindIdvRelationships(host){host.querySelectorAll('[data-idv-key]').forEach(function(button){button.addEventListener('click',function(){openIdvEvidence(button.dataset.idvKey,button)})})}

    function renderAward(){
      var s=session,host=hostFor(),a=s&&s.award;if(!s||!host||!a)return;
      shellMode(true);
      var id=identity(a),dates=obj(a.dates)?a.dates:{},source=obj(a.source)?a.source:{},src=safeUrl(source.award_page_url||source.award_detail_url||source.award_search_url);
      host.innerHTML='<div class="dossier-detail"><div class="dossier-nav"><button class="tool-btn" type="button" data-dossier-back>← '+esc(tr('Award book','授标档案'))+'</button><span class="truth official">'+esc(tr('Official record','官方记录'))+'</span></div><h3>'+esc(name(a))+'</h3><div class="dossier-detail-id">'+esc(text(id.generated_award_id,a.award_key))+'</div><div class="inspect-meta">'+esc(recipient(a))+' · '+esc(agency(a))+'</div><div class="semantic-values"><div><span>'+esc(tr('Obligated','已承诺义务'))+'</span><b>'+esc(money(amount(a,'obligated')))+'</b></div><div><span>'+esc(tr('Current value','当前价值'))+'</span><b>'+esc(money(amount(a,'current_award_value')))+'</b></div><div><span>'+esc(tr('Potential ceiling','潜在上限'))+'</span><b>'+esc(money(amount(a,'ceiling')))+'</b></div></div><div class="facts-grid" style="margin-top:9px">'+factCell(tr('Effective at','生效于'),date(field(dates,['effective_at','start_date'])))+factCell(tr('Known at','获知于'),date(field(dates,['known_at'])))+factCell(tr('Current POP end','当前履约结束'),date(field(dates,['end_date'])))+factCell(tr('Award / PIID','授标 / PIID'),text(id.piid))+'</div>'+(src?'<a class="source-link" href="'+esc(src)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open official award','打开官方授标'))+'</b><span>↗</span></a>':'')+renderSubawardLedger(s)+renderIdvRelationships(s)+'<div class="inspect-label" style="margin-top:13px">'+esc(tr('Official action tape','官方行动脉搏'))+'</div><div class="action-tape">'+(s.actions.length?actionRows(s.actions):'<div class="dossier-empty">'+esc(tr('No action row is visible in this source cut.','当前来源截点中没有可见行动记录。'))+'</div>')+'</div>'+(s.actionNext?'<button class="tool-btn" type="button" data-more-actions style="margin-top:8px">'+esc(tr('Load more actions','加载更多行动'))+'</button>':'')+'<div class="limit-copy" style="margin-top:8px">'+esc(tr('Obligation, current value and potential ceiling are distinct official amount semantics. None is GAAP backlog or reported revenue.','义务额、当前价值与潜在上限是不同的官方金额语义，均不等于 GAAP 积压或报告收入。'))+'</div></div>';
      bind(host);
    }

    function subawardRoute(s,cursor){var route='award/'+encodeURIComponent(s.award.award_key)+'/subawards?limit='+SUBAWARD_PAGE_SIZE;if(s.subawardQuery)route+='&subrecipient='+encodeURIComponent(s.subawardQuery);if(cursor)route+='&cursor='+encodeURIComponent(cursor);return route}
    function loadSubawardPage(s,cursor){
      var viewToken=s.awardViewToken,request=++s.subawardRequest;if(!isActiveAwardView(s,viewToken))return Promise.resolve();s.subawardLoading=true;s.subawardError=false;renderAward();
      return fetchPage(subawardRoute(s,cursor),'subaward').then(function(page){
        if(!isActiveAwardView(s,viewToken)||s.subawardRequest!==request)throw new Error('stale_request');
        if(s.subawardContentId&&page.content_id!==s.subawardContentId)throw new Error('subaward_generation_mismatch');
        s.subawardContentId=page.content_id;s.subawards=arr(page.results).filter(obj);s.subawardNext=page.next_cursor||null;s.subawardTotal=n(page.total)||0;s.subawardCoverage=obj(page.parent_coverage)?page.parent_coverage:{};s.subawardError=false;s.subawardLoading=false;renderAward();
      }).catch(function(){
        if(isActiveAwardView(s,viewToken)&&s.subawardRequest===request){s.subawardLoading=false;s.subawardError=true;renderAward()}
      });
    }
    function restartSubawardSearch(s){s.subawardCursors=[null];s.subawardPage=0;s.subawardNext=null;return loadSubawardPage(s,null)}
    function nextSubawardPage(){var s=session;if(!s||!s.awardViewActive||!s.subawardNext)return;s.subawardPage+=1;s.subawardCursors[s.subawardPage]=s.subawardNext;loadSubawardPage(s,s.subawardNext)}
    function previousSubawardPage(){var s=session;if(!s||!s.awardViewActive||s.subawardPage<1)return;s.subawardPage-=1;loadSubawardPage(s,s.subawardCursors[s.subawardPage]||null)}
    function evidenceHtml(row){
      var id=identity(row),dates=obj(row.dates)?row.dates:{},provenance=obj(row.provenance)?row.provenance:{},amountData=obj(row.reported_amount)?row.reported_amount:{},source=obj(row.source)?row.source:{},sourceUrl=safeUrl(source.subaward_url),parentUrl=safeUrl(source.parent_award_url);
      function receipt(label,value){return'<article class="receipt"><div class="receipt-kind">'+esc(label)+'</div><div class="receipt-code">'+esc(value)+'</div></article>'}
      var html='<article class="receipt"><div class="receipt-kind">'+esc(tr('Reported subaward','报告分包'))+'</div><h3>'+esc(text(row.subawardee_name,tr('Subrecipient not reported','未报告分包接收方')))+'</h3><p>'+esc(text(row.description,tr('No description reported','未报告说明')))+(row.description_truncated?' '+esc(tr('(description truncated)','（说明已截断）')):'')+'</p><div class="receipt-code">'+esc(tr('reported amount: ','报告金额：')+subawardSourceAmount(row)+'\nsemantic: '+text(amountData.semantic,'reported_subaward_amount')+'\ncurrency: '+text(amountData.currency,'USD')+'\naction date: '+text(dates.action_date)+'\neffective at: '+text(dates.effective_at)+'\nknown at: '+text(dates.known_at))+'</div></article>';
      html+=receipt(tr('Identity','身份'),tr('native source ID: ','原生来源 ID：')+text(id.source_subaward_id)+'\n'+tr('display number: ','显示编号：')+text(id.displayed_subaward_number)+'\n'+tr('parent generated award ID: ','父级生成授标 ID：')+text(id.parent_generated_award_id));
      html+=receipt(tr('Receipt provenance','凭证出处'),tr('receipt ID: ','凭证 ID：')+text(provenance.receipt_id)+'\nsha256: '+text(provenance.response_sha256)+'\n'+tr('source rows: ','来源行数：')+text(provenance.source_record_count));
      html+='<article class="receipt"><div class="receipt-kind">'+esc(tr('Limits','限制'))+'</div><p>'+esc(arr(provenance.limitations).concat([tr('Reported amount is not a federal obligation, prime-award value, revenue, backlog, cash flow, or an additive amount.','报告金额并非联邦义务额、主授标价值、收入、积压、现金流或可加总金额。')]).join(' · '))+'</p>'+(sourceUrl?'<a class="source-link" href="'+esc(sourceUrl)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open USAspending source','打开 USAspending 来源'))+'</b><span>↗</span></a>':'')+(parentUrl?'<a class="source-link" href="'+esc(parentUrl)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open parent award','打开主授标'))+'</b><span>↗</span></a>':'')+'</article>';
      return html;
    }
    function openSubawardEvidence(key,focus){
      var s=session,host=hostFor(),viewToken=s&&s.awardViewToken;if(!s||!s.award||!s.awardViewActive||!key)return;
      fetchPage('subaward/'+encodeURIComponent(key),'subaward').then(function(detail){
        if(!isActiveAwardView(s,viewToken)||detail.content_id!==s.subawardContentId)throw new Error('subaward_generation_mismatch');
        if(typeof api.openEvidenceDrawer!=='function')throw new Error('drawer_unavailable');
        api.openEvidenceDrawer({title:tr('Subaward evidence','分包凭证'),html:evidenceHtml(detail.subaward||{}),focus:focus});
      }).catch(function(){if(isActiveAwardView(s,viewToken)&&host)host.insertAdjacentHTML('beforeend','<div class="dossier-error">'+esc(tr('This subaward receipt could not be verified against the active subaward generation.','该分包凭证无法与当前分包数据代次完成核验。'))+'</div>')})
    }
    function bindSubawards(host){
      var search=host.querySelector('[data-subaward-search]');
      if(search){search.addEventListener('input',function(){var s=session,viewToken=s&&s.awardViewToken;if(!s||!s.awardViewActive)return;s.subawardQuery=this.value.trim();clearSearchTimer();searchTimer=global.setTimeout(function(){searchTimer=null;if(isActiveAwardView(s,viewToken))restartSubawardSearch(s)},250)});search.addEventListener('keydown',function(event){if(event.key!=='Escape')return;event.preventDefault();clearSearchTimer();var s=session;if(!s||!s.awardViewActive)return;this.value='';s.subawardQuery='';restartSubawardSearch(s)})}
      var next=host.querySelector('[data-subaward-next]');if(next)next.addEventListener('click',nextSubawardPage);
      var previous=host.querySelector('[data-subaward-prev]');if(previous)previous.addEventListener('click',previousSubawardPage);
      host.querySelectorAll('[data-subaward-key]').forEach(function(button){button.addEventListener('click',function(){openSubawardEvidence(button.dataset.subawardKey,button)})});
    }

    function loadAward(key){
      var s=session,host=hostFor();if(!s||!host||!key)return;
      var viewToken=enterAwardView(s);
      host.innerHTML='<div class="dossier-status"><span><b>'+esc(tr('Opening award history','正在打开授标历史'))+'</b><span>'+esc(tr('Verifying record, action, subaward and IDV relationship generations…','正在核验记录、行动、分包及 IDV 关系数据代次…'))+'</span></span><span class="dossier-count">•••</span></div>';
      var route='award/'+encodeURIComponent(key),subRoute=route+'/subawards?limit='+SUBAWARD_PAGE_SIZE,idvRoute=route+'/idv-relationships';
      Promise.all([fetchPage(route,'prime'),fetchPage(route+'/actions?limit=20','prime'),fetchPage(subRoute,'subaward').then(function(value){return{ok:true,value:value}},function(){return{ok:false,value:null}}),fetchPage(idvRoute,'idv').then(function(value){return{ok:true,value:value}},function(){return{ok:false,value:null}})]).then(function(x){
        if(!isActiveAwardView(s,viewToken)||x[0].content_id!==s.content_id||x[1].content_id!==s.content_id)throw new Error('generation_mismatch');
        s.award=x[0].award;s.actions=arr(x[1].results).filter(obj);s.actionNext=x[1].next_cursor;s.subawardQuery='';s.subawardCursors=[null];s.subawardPage=0;s.subawardRequest=0;s.subawardLoading=false;
        if(x[2].ok){s.subawardContentId=x[2].value.content_id;s.subawards=arr(x[2].value.results).filter(obj);s.subawardNext=x[2].value.next_cursor||null;s.subawardTotal=n(x[2].value.total)||0;s.subawardCoverage=obj(x[2].value.parent_coverage)?x[2].value.parent_coverage:{};s.subawardError=false}else{s.subawardContentId=null;s.subawards=[];s.subawardNext=null;s.subawardTotal=0;s.subawardCoverage={status:'unavailable'};s.subawardError=true}
        if(x[3].ok){s.idvContentId=x[3].value.content_id;s.idvRelationships=arr(x[3].value.relationships).filter(obj);s.idvCoverage=obj(x[3].value.source_coverage)?x[3].value.source_coverage:{};s.idvAwardCoverage=obj(x[3].value.award_coverage)?x[3].value.award_coverage:{};s.idvSelection=obj(x[3].value.selection_provenance)?x[3].value.selection_provenance:{};s.idvError=false}else{s.idvContentId=null;s.idvRelationships=[];s.idvCoverage={status:'unavailable'};s.idvAwardCoverage={status:'unavailable',exhaustive:false};s.idvSelection={status:'unavailable'};s.idvError=true}
        renderAward();
      }).catch(function(){if(!isActiveAwardView(s,viewToken))return;host.innerHTML='<div class="dossier-error">'+esc(tr('This award detail could not be verified against the active dossier generation.','该授标明细无法与当前档案代次完成核验。'))+'</div><button class="tool-btn" type="button" data-dossier-back style="margin-top:8px">← '+esc(tr('Award book','授标档案'))+'</button>';bind(host)})
    }
    function moreActions(){var s=session,viewToken=s&&s.awardViewToken,awardKey=s&&s.award&&s.award.award_key;if(!s||!s.award||!s.awardViewActive||!s.actionNext)return;fetchPage('award/'+encodeURIComponent(awardKey)+'/actions?limit=20&cursor='+encodeURIComponent(s.actionNext),'prime').then(function(page){if(!isActiveAwardView(s,viewToken)||!s.award||s.award.award_key!==awardKey||page.content_id!==s.content_id)throw new Error('generation_mismatch');s.actions=s.actions.concat(arr(page.results).filter(obj));s.actionNext=page.next_cursor;renderAward()}).catch(function(){var host=hostFor();if(isActiveAwardView(s,viewToken)&&host)host.insertAdjacentHTML('beforeend','<div class="dossier-error">'+esc(tr('The next action page could not be verified.','下一页行动记录无法核验。'))+'</div>')})}

    return{loadCompany:loadCompany,invalidate:function(){epoch++;leaveAwardView(session);session=null;shellMode(false)}};
  };

  /* Identity Atlas — the reviewed path from an exact award recipient up to a listed
   * issuer, point in time. It is the identity rail ONLY: it carries no award, event,
   * action or amount, so it structurally cannot leak attribution onto an unlinked
   * event. Cookie plane (government-revenue-data/identity_atlas.json), fetched once
   * per session and indexed by ticker; a 401/403 degrades to the same members-only
   * teaser the workspace and candidate ledger already use. Every hop that is not
   * reviewed renders as a broken link in the rail rather than a minted one. */
  global.createGovernmentRevenueIdentityAtlas=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,date=api.date,tr=api.tr,safeUrl=api.safeUrl,hostFor=api.host;
    var isZh=typeof api.zh==='function'?api.zh:function(){return false};
    var ATLAS_PATH='government-revenue-data/identity-atlas.json';
    var pending=null,index=null,header=null,loadState='idle',ticker='',epoch=0;

    function failure(code){var error=new Error(code);error.code=code;return error}
    function tone(host,name){if(!host||!host.classList||typeof host.classList.remove!=='function')return;host.classList.remove('is-unresolved','is-historic');if(name)host.classList.add(name)}
    /* Localized field pick: the projector may ship `<base>`, `<base>_en` and `<base>_zh`.
     * A zh reader never falls through to an English state name while a zh twin exists. */
    function loc(row,base){
      row=obj(row)?row:{};
      var native=isZh()?row[base+'_zh']:row[base+'_en'],plain=row[base],other=isZh()?row[base+'_en']:row[base+'_zh'];
      if(native!=null&&native!=='')return String(native);
      if(plain!=null&&plain!=='')return String(plain);
      if(other!=null&&other!=='')return String(other);
      return'';
    }
    function relationshipWord(value){
      if(value==='issuer_legal_entity')return tr('Issuer of record','登记发行主体');
      if(value==='wholly_owned')return tr('Wholly owned','全资持有');
      if(value==='majority_owned')return tr('Majority owned','多数持有');
      if(value==='joint_venture')return tr('Joint venture','合资企业');
      return tr('Relationship on file','档案所载关系');
    }
    function stateWord(value){
      if(value==='reviewed')return tr('Reviewed','已核验');
      if(value==='observed')return tr('Observed','已观测');
      if(value==='mapping_needed')return tr('Link pending','关联待核');
      if(value==='evidence_conflict')return tr('Conflict on record','记录存在冲突');
      if(value==='not_asserted')return tr('Not asserted','未作断言');
      return tr('State unclear','状态未知');
    }
    function stateChip(value){return value==='reviewed'?'reviewed':value==='observed'?'observed':value==='evidence_conflict'?'conflict':value==='not_asserted'?'historic':'derived'}
    function gapWords(gap){
      if(typeof gap==='string')return gap;
      var direct=loc(gap,'text');if(direct)return direct;
      var code=text(gap&&gap.code,'');
      /* Projector-emitted codes (engine/government_revenue/identity_atlas.py) --
       * fallbacks only, since every real gap already ships text_en/text_zh and
       * takes the `direct` branch above. */
      if(code==='no_reviewed_exact_path')return tr('no reviewed exact recipient → legal entity path exists','没有已核验的精确收款方 → 法律实体路径');
      if(code==='unresolved_identifiers_present')return tr('some curated identifiers carry a reviewed conflict or gap and stay unresolved','部分已审核标识符存在冲突或缺口，保持未解决状态');
      if(code==='observed_identifiers_without_reviewed_path')return tr('recipient identifiers observed in the discovery file have no reviewed path — discovery association only, never issuer proof','发现文件中观测到的收款方标识没有已审核路径 — 仅为发现关联，绝非发行人证明');
      return'';
    }
    function reasonWords(row){
      var direct=loc(row,'reason');if(direct)return direct;
      return tr('No reason was recorded for this identifier.','该标识未记录原因。');
    }
    function evidenceList(row){var value=obj(row)?row.evidence:null;return Array.isArray(value)?value.filter(obj):obj(value)?[value]:[]}
    function evidenceLinks(row,label){
      return evidenceList(row).map(function(item){
        var url=safeUrl(item.url);if(!url)return'';
        return'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(text(item.publisher,label||tr('Open source record','打开来源记录')))+'</b><span>↗</span></a>';
      }).join('');
    }
    function evidenceCode(row){
      return evidenceList(row).map(function(item){
        return tr('publisher: ','发布方：')+text(item.publisher)+'\n'+tr('record: ','记录：')+text(item.evidence_id)+'\nsha256: '+text(item.content_sha256);
      }).join('\n\n');
    }

    function security(record){return obj(record.public_security)?record.public_security:{}}
    function securityState(record){return text(security(record).state,'')}
    function entities(record){return arr(record.entities).filter(obj)}
    function unresolved(record){return arr(record.unresolved_identifiers).filter(obj)}
    function reviewedIdCount(record){var total=0;entities(record).forEach(function(entity){total+=arr(entity.identifiers).filter(obj).length});return total}
    function hasConflict(record){return unresolved(record).some(function(row){return row.state==='evidence_conflict'})}
    function isHistoric(record){return securityState(record)==='listing_terminated'}
    function endDate(record){var events=arr(record.listing_events).filter(obj);return date(security(record).last_date||(events[0]||{}).effective_at)}

    function securityWords(record){
      var state=securityState(record);
      if(state==='verified_live')return tr('verified','已核验');
      if(state==='listing_terminated')return isZh()?('上市已于 '+endDate(record)+' 终止'):('listing ended '+endDate(record));
      if(state==='not_in_si_universe')return tr('not in the covered listing universe','不在已覆盖的上市范围内');
      return tr('unconfirmed','未确认');
    }
    function recipientWords(record){
      var reviewed=reviewedIdCount(record),open=unresolved(record).length;
      if(!reviewed)return tr('unresolved','未解析');
      if(open)return isZh()?('已核验，另有 '+open+' 项未解析'):('reviewed, '+open+' still unresolved');
      return tr('reviewed','已核验');
    }
    function attributionWords(record){return record.issuer_attribution==='reviewed'?tr('reviewed','已核验'):tr('not asserted','未作断言')}
    /* The one-sentence read. Composed, never stored, so the three hops always agree
     * with the rail underneath and a zh reader gets a native sentence. */
    function readLine(record){
      var parts=[
        tr('Public security: ','上市证券：')+securityWords(record),
        tr('Government recipient attribution: ','政府收款方归属：')+recipientWords(record),
        tr('Exact issuer attribution: ','精确发行人归属：')+attributionWords(record)
      ];
      var lead=gapWords(arr(record.gaps)[0]),out=parts.join(' · ')+(lead?' — '+lead:'');
      return/[.。]$/.test(out)?out:out+(isZh()?'。':'.');
    }
    function stance(record){
      if(isHistoric(record))return[tr('Ignore','忽略'),tr('This listing has ended. Read what follows as history — there is no live issuer behind it.','该股票已终止上市。以下内容仅为历史 — 其背后已无在市发行人。')];
      if(record.issuer_attribution!=='reviewed')return[tr('Stand aside','暂不参与'),tr('No reviewed path ties an exact recipient to this issuer. Treat award totals under this name as unattributed.','没有已核验的路径将精确收款方与该发行人相连。请将该名称下的授标金额视为未归属。')];
      if(unresolved(record).length)return[tr('Watch — don’t chase','观察，不要追高'),tr('The reviewed path holds for the identifiers below; the unresolved ones are not part of it. Read the award tape against the reviewed path only.','下方标识的已核验路径成立；未解析项不在其中。请仅依据已核验路径阅读授标脉搏。')];
      return[tr('Watch — don’t chase','观察，不要追高'),tr('The path from award recipient to this issuer is reviewed. Read the award tape against it — a reviewed path is not a buy signal.','从授标收款方到该发行人的路径已核验。可据此阅读授标脉搏 — 已核验路径不是买入信号。')];
    }
    function chips(record){
      var out=[];
      if(record.issuer_attribution==='reviewed')out.push(['reviewed',tr('Reviewed issuer path','已核验发行人路径')]);
      else out.push(['historic',tr('Identity unresolved','身份未解析')]);
      if(unresolved(record).some(function(row){return row.state!=='evidence_conflict'}))out.push(['derived',tr('Link pending','关联待核')]);
      if(hasConflict(record))out.push(['conflict',tr('Conflict on record','记录存在冲突')]);
      if(isHistoric(record))out.push(['historic',tr('Listing terminated','上市已终止')]);
      return'<div class="atlas-chips">'+out.map(function(pair){return'<span class="truth '+pair[0]+'">'+esc(pair[1])+'</span>'}).join('')+'</div>';
    }

    /* Named gap counts the rail must never contradict. `unresolved(record)` is
     * curated-only (FIX-6/finding B6): a scope-observed identifier with no
     * reviewed path and no curated review is never named, only counted in this
     * gap. Folding it into the rung's own open-state keeps "every observed
     * identifier sits on the reviewed path" from printing in the SAME breath as
     * a gaps line saying N of them do not (FIX-D). */
    function gapCount(record,code){
      var row=arr(record.gaps).filter(obj).find(function(g){return g.code===code});
      return row?(n(row.count)||0):0;
    }
    /* The rail. Four rungs, top to bottom; a rung whose successor is not reviewed
     * carries a dashed connector, so the break in the chain is visible before a
     * word is read. */
    function hop(rung,tone,fact,note){return{rung:rung,tone:tone,fact:fact,note:note}}
    function chain(record){
      var state=securityState(record),issuer=obj(record.legal_issuer)?record.legal_issuer:null,rows=entities(record),reviewed=reviewedIdCount(record);
      var curatedOpen=unresolved(record).length,observedOpen=gapCount(record,'observed_identifiers_without_reviewed_path'),open=curatedOpen+observedOpen;
      var hops=[];
      hops.push(hop(
        tr('Public security','上市证券'),
        state==='verified_live'?'reviewed':state==='listing_terminated'?'historic':'unresolved',
        text(record.company_name,text(record.ticker))+' · '+text(record.ticker),
        state==='verified_live'?(isZh()?('行情更新至 '+date(security(record).last_date)):('tape through '+date(security(record).last_date)))
          :state==='listing_terminated'?(isZh()?('最后交易日 '+endDate(record)):('last traded '+endDate(record)))
          :tr('No covered listing record','没有已覆盖的上市记录')
      ));
      hops.push(hop(
        tr('Legal issuer','法律发行主体'),
        issuer&&issuer.state==='reviewed'?'reviewed':'unresolved',
        issuer&&issuer.state==='reviewed'?text(issuer.canonical_name,text(record.ticker)):tr('Not asserted','未作断言'),
        issuer&&issuer.state==='reviewed'?stateWord(issuer.review_state):loc(record,'attribution_reason')||tr('No filing evidence names an issuer for these recipients.','没有披露证据为这些收款方指明发行主体。')
      ));
      hops.push(hop(
        tr('Legal entities','法律实体'),
        rows.length?'reviewed':'unresolved',
        rows.length?(isZh()?(rows.length+' 个已核验法律实体'):(rows.length+' reviewed legal '+(rows.length===1?'entity':'entities'))):tr('No reviewed legal entity','没有已核验的法律实体'),
        rows.length?tr('Named in the company’s own filing','由公司自身披露文件列明'):tr('Nothing is minted where the filing is silent','披露文件未提及之处不作推定')
      ));
      hops.push(hop(
        tr('Recipient identifiers','收款方标识'),
        reviewed?'reviewed':hasConflict(record)?'conflict':'unresolved',
        reviewed?(isZh()?(reviewed+' 个精确收款方标识已核验'):(reviewed+' exact recipient '+(reviewed===1?'identifier':'identifiers')+' reviewed')):tr('No reviewed recipient identifier','没有已核验的收款方标识'),
        open?(isZh()?(open+' 项仍未解析'+(curatedOpen?'，见下方':'')):(open+' still unresolved'+(curatedOpen?', listed below':''))):reviewed?tr('Every observed identifier sits on the reviewed path','每个已观测标识均位于已核验路径上'):tr('No recipient identifier is on record for this company','该公司没有在册的收款方标识')
      ));
      return'<ol class="atlas-chain">'+hops.map(function(row,i){
        var next=hops[i+1],broken=next&&next.tone!=='reviewed'&&next.tone!=='historic';
        return'<li class="atlas-hop '+row.tone+(broken?' break':'')+'"><i class="atlas-node" aria-hidden="true"></i><span class="atlas-rung">'+esc(row.rung)+'</span><strong class="atlas-fact">'+esc(row.fact)+'</strong><span class="atlas-note">'+esc(row.note)+'</span></li>';
      }).join('')+'</ol>';
    }

    function sharePhrase(entity){
      var share=n(entity.economic_share);
      if(share==null)return'';
      if(entity.relationship==='wholly_owned'&&share===1)return'';
      return isZh()?(Math.round(share*1000)/10+'% 经济权益'):(Math.round(share*1000)/10+'% economic share');
    }
    function validityPhrase(entity){
      var from=entity.valid_from?date(entity.valid_from):'',to=entity.valid_to?date(entity.valid_to):'';
      if(!from&&!to)return tr('No validity interval on record','档案未记录有效区间');
      if(from&&to)return isZh()?(from+' 至 '+to+' 在册'):('on record '+from+' to '+to);
      if(from)return isZh()?('自 '+from+' 起在册'):('on record since '+from);
      return isZh()?('至 '+to+' 止'):('on record until '+to);
    }
    function identifierCount(entity){
      var rows=arr(entity.identifiers).filter(obj);
      if(!rows.length)return tr('No award recipient identifier observed for this entity yet','尚未观测到该实体的授标收款方标识');
      return isZh()?('持有 '+rows.length+' 个精确收款方标识'):('Holds '+rows.length+' exact recipient '+(rows.length===1?'identifier':'identifiers'));
    }
    function identifierRows(entity){
      return arr(entity.identifiers).filter(obj).map(function(row){
        return'<div class="atlas-id"><code>'+esc(text(row.value))+'</code><b>'+esc(stateWord(row.verification_state))+'</b></div>';
      }).join('');
    }
    function entityReceipt(entity){
      var rows=arr(entity.identifiers).filter(obj),lines=[];
      if(rows.length)lines.push(tr('identifier namespace: ','标识命名空间：')+text((rows[0]||{}).namespace));
      lines.push(tr('valid from: ','有效自：')+text(entity.valid_from));
      lines.push(tr('valid to: ','有效至：')+text(entity.valid_to,tr('open','未终止')));
      lines.push(tr('first known at: ','首次获知：')+text(entity.known_at));
      var code=evidenceCode(entity);if(code)lines.push(code);
      rows.forEach(function(row){var extra=evidenceCode(row);if(extra)lines.push(text(row.value)+'\n'+extra)});
      var summary=rows.length?tr('Show identifiers, dates and receipts','显示标识、日期与凭证'):tr('Show dates and the filing receipt','显示日期与披露凭证');
      return'<details class="atlas-receipt"><summary>'+esc(summary)+'</summary><div class="atlas-receipt-body">'+identifierRows(entity)+'<div class="atlas-code">'+esc(lines.join('\n'))+'</div>'+evidenceLinks(entity,tr('Open filing source','打开披露来源'))+arr(entity.identifiers).filter(obj).map(function(row){return evidenceLinks(row,tr('Open award record','打开授标记录'))}).join('')+'</div></details>';
    }
    function entityCards(record){
      var rows=entities(record);
      if(!rows.length)return'';
      return'<div class="atlas-sub">'+esc(tr('Legal entities on record','在册法律实体'))+'</div><div class="atlas-entities">'+rows.map(function(entity){
        var meta=[relationshipWord(entity.relationship),sharePhrase(entity),validityPhrase(entity)].filter(Boolean).join(' · ');
        return'<article class="atlas-entity '+esc(stateChip(entity.verification_state))+'"><div class="atlas-entity-top"><div><strong class="atlas-entity-name">'+esc(text(entity.canonical_name))+'</strong><span class="atlas-entity-meta">'+esc(meta)+'</span></div><span class="truth '+esc(stateChip(entity.verification_state))+'">'+esc(stateWord(entity.verification_state))+'</span></div><span class="atlas-entity-meta">'+esc(identifierCount(entity))+'</span>'+entityReceipt(entity)+'</article>';
      }).join('')+'</div>';
    }
    /* Identifiers blocked for the SAME recorded reason are ONE card, not N copies of
     * one sentence (GE ships five). A constant belongs once, and the count is the
     * fact the reader needs; the individual identifiers stay one expand away. */
    function unresolvedGroups(record){
      var order=[],byKey={};
      unresolved(record).forEach(function(row){
        var key=text(row.state,'')+' '+reasonWords(row);
        if(!byKey[key]){byKey[key]={state:row.state,reason:reasonWords(row),rows:[],links:[],seen:{}};order.push(key)}
        var group=byKey[key];group.rows.push(row);
        evidenceList(row).forEach(function(item){var url=safeUrl(item.url);if(url&&!group.seen[url]){group.seen[url]=true;group.links.push(item)}});
      });
      return order.map(function(key){return byKey[key]});
    }
    function groupHeadline(group){
      var rows=group.rows,first=rows[0]||{},name=text(first.observed_name,'');
      if(rows.length===1)return text(first.observed_name,tr('Recipient name not reported','未报告收款方名称'));
      var same=rows.every(function(row){return text(row.observed_name,'')===name});
      if(same&&name)return isZh()?(rows.length+' 个收款方登记均显示「'+name+'」'):(rows.length+' recipient registrations named “'+name+'”');
      var names=rows.map(function(row){return text(row.observed_name,'')}).filter(Boolean);
      if(names.length&&names.length<=3)return names.join(' · ');
      return isZh()?(rows.length+' 个收款方标识'):(rows.length+' recipient identifiers');
    }
    function unresolvedCards(record){
      var groups=unresolvedGroups(record);
      if(!groups.length)return'';
      return'<div class="atlas-sub">'+esc(tr('Where the trail stops','线索中断之处'))+'</div><div class="atlas-unresolved">'+groups.map(function(group){
        var conflict=group.state==='evidence_conflict',lines=group.rows.map(function(row){
          return'<div class="atlas-id"><code>'+esc(text(row.value))+'</code><b>'+esc(text(row.namespace))+'</b></div>';
        }).join(''),code=group.rows.map(function(row){return text(row.value)+'\n'+evidenceCode(row)}).join('\n\n');
        return'<div class="atlas-gap'+(conflict?' conflict':'')+'"><div class="atlas-gap-top"><strong>'+esc(groupHeadline(group))+'</strong><span class="truth '+esc(stateChip(group.state))+'">'+esc(stateWord(group.state))+'</span></div><span>'+esc(group.reason)+'</span>'+group.links.map(function(item){var url=safeUrl(item.url);return'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(text(item.publisher,tr('Open source record','打开来源记录')))+'</b><span>↗</span></a>'}).join('')+'<details class="atlas-receipt"><summary>'+esc(group.rows.length===1?tr('Show the identifier and its receipts','显示该标识及其凭证'):tr('Show every identifier and its receipts','显示全部标识及其凭证'))+'</summary><div class="atlas-receipt-body">'+lines+'<div class="atlas-code">'+esc(code.trim())+'</div></div></details></div>';
      }).join('')+'</div>';
    }
    function eventWords(event){
      var head=loc(event,'headline');if(head)return head;
      if(event.event_type==='listing_terminated')return tr('The listing ended.','该股票终止上市。');
      if(event.event_type==='spin_off')return tr('A business separated into its own listed company.','一项业务分拆为独立上市公司。');
      if(event.event_type==='name_change')return tr('The trade name changed; the filing entity did not.','商号变更；披露主体未变。');
      return tr('A corporate change is on record.','已记录一项公司变更。');
    }
    function historyCards(record){
      var rows=arr(record.listing_events).filter(obj).concat(arr(record.separation_events).filter(obj));
      if(!rows.length)return'';
      return'<div class="atlas-sub">'+esc(tr('Corporate history on record','在册公司历史'))+'</div><div class="atlas-history">'+rows.map(function(event){
        return'<div class="atlas-event"><time>'+esc(date(event.effective_at))+'</time><div><span>'+esc(eventWords(event))+'</span>'+evidenceLinks(event,tr('Open the filing','打开披露文件'))+'</div></div>';
      }).join('')+'</div>';
    }
    function remainingGaps(record){
      var rows=arr(record.gaps).slice(1).map(gapWords).filter(Boolean);
      if(!rows.length)return'';
      return'<div class="atlas-sub">'+esc(tr('Still unresolved','仍未解析'))+'</div><ul class="atlas-open">'+rows.map(function(row){return'<li>'+esc(row)+'</li>'}).join('')+'</ul>';
    }
    function cutReceipt(){
      var head=obj(header)?header:{};
      return'<details class="atlas-receipt"><summary>'+esc(tr('Show the evidence cut behind this path','显示该路径背后的证据截点'))+'</summary><div class="atlas-receipt-body"><div class="atlas-code">'+esc('graph_id: '+text(head.graph_id)+'\ngraph_digest: '+text(head.graph_digest)+'\nsi_asof: '+text(head.si_asof)+'\ncontract: '+text(head.contract)+'\nschema_version: '+text(head.schema_version))+'</div></div></details>';
    }

    function question(){return'<p class="atlas-question">'+esc(tr('Who the government actually paid, and how that reaches this ticker.','政府实际付款给谁，以及这如何连到该股票代码。'))+'</p>'}
    function recordHtml(record){
      var verdict=stance(record);
      return question()+chips(record)+chain(record)+
        '<p class="atlas-read">'+esc(readLine(record))+'</p>'+
        '<div class="stance"><b>'+esc(verdict[0])+'</b><span>'+esc(verdict[1])+'</span></div>'+
        entityCards(record)+unresolvedCards(record)+historyCards(record)+remainingGaps(record)+
        '<div class="atlas-asof">'+esc(isZh()?('身份记录截至 '+date((header||{}).generated_at)):('Identity record as of '+date((header||{}).generated_at)))+'</div>'+
        cutReceipt()+
        '<div class="limit-copy">'+esc(tr('Identity paths only — no award, event or amount is attributed here. It cannot rank a company, size a position or trigger a trade.','仅为身份路径 — 此处不归属任何授标、事件或金额。不得为公司排序、调整仓位或触发交易。'))+'</div>';
    }
    function loadingHtml(){return'<div class="dossier-status" aria-busy="true"><span><b>'+esc(tr('Tracing the identity path','正在追踪身份路径'))+'</b><span>'+esc(tr('Loading the reviewed recipient, entity and ownership record…','正在加载已核验的收款方、实体与所有权记录…'))+'</span></span><span class="dossier-count">•••</span></div>'}
    function lockedHtml(){return question()+'<div class="dossier-empty"><strong>'+esc(tr('Identity path locked','身份路径已锁定'))+'</strong><p>'+esc(tr('The reviewed recipient-to-issuer path is part of a membership. Award history below stays open and is not issuer proof.','已核验的收款方至发行人路径包含在会员权益中。下方授标历史保持开放，且不构成发行人证明。'))+'</p><div class="candidate-empty-meta"><a class="tool-btn" href="plans.html">'+esc(tr('View membership plans','查看会员方案'))+'</a></div></div>'}
    function errorHtml(){return'<div class="dossier-error"><strong>'+esc(tr('Identity path unavailable','身份路径不可用'))+'</strong><br>'+esc(tr('The identity record could not be verified. Award history below remains available and is not issuer proof.','身份记录无法完成核验。下方授标历史仍然可用，且不构成发行人证明。'))+'</div>'}
    function absentHtml(){return question()+'<div class="dossier-empty"><strong>'+esc(tr('No identity record for this company','该公司暂无身份记录'))+'</strong><p>'+esc(tr('The reviewed identity record covers a bounded set of issuers in this evidence cut. Nothing is inferred for the others.','已核验的身份记录仅覆盖本证据截点内的有限发行人集合。对其他公司不作任何推断。'))+'</p></div>'}

    function render(){
      var host=hostFor();if(!host)return;
      if(loadState==='loading'||loadState==='idle'){tone(host,null);host.innerHTML=loadingHtml();return}
      if(loadState==='locked'){tone(host,'is-unresolved');host.innerHTML=lockedHtml();return}
      if(loadState!=='ok'){tone(host,'is-unresolved');host.innerHTML=errorHtml();return}
      var record=index&&index[ticker];
      if(!obj(record)){tone(host,null);host.innerHTML=absentHtml();return}
      tone(host,isHistoric(record)?'is-historic':record.issuer_attribution==='reviewed'?null:'is-unresolved');
      host.innerHTML=recordHtml(record);
    }
    function ensure(){
      if(pending)return pending;
      if(typeof global.fetch!=='function'){loadState='unavailable';return Promise.resolve(false)}
      loadState='loading';
      pending=global.fetch(ATLAS_PATH,{credentials:'same-origin'}).then(function(response){
        if(response.status===401||response.status===403)throw failure('locked');
        if(!response.ok)throw failure('unavailable');
        return response.json();
      }).then(function(value){
        if(!obj(value)||value.contract!=='government_revenue_identity_atlas.v1'||!/^1\./.test(text(value.schema_version,'')))throw failure('invalid');
        header=value;index={};
        arr(value.issuers).filter(obj).forEach(function(row){var key=text(row.ticker,'').toUpperCase();if(key&&!index[key])index[key]=row});
        loadState='ok';return true;
      }).catch(function(error){header=null;index=null;loadState=(error&&error.code)||'unavailable';return false});
      return pending;
    }
    function loadCompany(value){
      var ticket=++epoch;ticker=text(value,'').toUpperCase();
      if(!hostFor())return;
      if(loadState==='ok'||loadState==='locked')render();else{loadState=loadState==='idle'?'loading':loadState;render()}
      ensure().then(function(){if(ticket===epoch)render()});
    }
    /* A member who signs in after the page loaded gets the path without a reload:
     * only the locked arm is retried, so a healthy cache is never refetched. */
    function bindAuthReload(){
      function onAuth(){markAuthSettled();if(loadState!=='locked')return;pending=null;loadState='idle';if(ticker){var ticket=++epoch;render();ensure().then(function(){if(ticket===epoch)render()})}}
      if(global.MDXAuth&&typeof global.MDXAuth.onChange==='function')global.MDXAuth.onChange(onAuth);
      else if(typeof global.addEventListener==='function')global.addEventListener('mdx-auth',onAuth);
    }
    bindAuthReload();
    return{loadCompany:loadCompany,invalidate:function(){epoch++;ticker=''},state:function(){return loadState}};
  };

  /* D4 — Company Financial Truth Bridge (IRDM only, frozen golden constant).
   * Puts the reviewed P00032 government fact beside the canonical earnings
   * owner's v1 context packet, read-only, so a reader can separately answer
   * what-the-government-recorded vs what-the-company-reports. Government
   * facts come from the already-loaded workspace events (api.workspaceEvents)
   * -- no new fetch -- and stay byte-identical across every company-packet
   * variation. Comparison is FIXED closed-state copy (review amendment
   * 2026-08-20, DEC:D4-COMPANY-RAIL-CONSUMES-CI-V1-CONTEXT): the module's
   * ONLY network read is /api/company-intelligence/{ticker} -- no candidates
   * artifact fetch, no ratio node ever, on any input. */
  global.createGovernmentRevenueCompanyBridge=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,date=api.date,tr=api.tr,safeUrl=api.safeUrl,factCell=api.factCell,hostFor=api.host;
    var workspaceEvents=typeof api.workspaceEvents==='function'?api.workspaceEvents:function(){return[]};
    var workspaceReady=typeof api.workspaceComplete==='function'?api.workspaceComplete:function(){return true};
    var FETCH_TIMEOUT_MS=typeof api.companyFetchTimeoutMs==='number'?api.companyFetchTimeoutMs:10000;
    var IRDM='IRDM',AWARD_PIID='HC101319C0006',MOD_NUMBER='P00032',LINEAGE_OK='earnings_history',COMPANY_SCHEMA='company_intelligence_context.v1';
    var epoch=0,ticker='',companyState='idle',companyPacket=null;
    var pendingByTicker={},successByTicker={};

    function modNumber(award){
      var actionId=text(award.action_id,''),piid=text(award.piid,'');
      if(!actionId||!piid)return'';
      var marker='_'+piid+'_',idx=actionId.indexOf(marker);
      if(idx<0)return'';
      var rest=actionId.slice(idx+marker.length).split('_');
      return rest[0]||'';
    }
    /* R10: constrain to events that actually carry the IRDM ticker (never
     * trust piid/mod alone), and when more than one qualifies, prefer the
     * one with the LATEST known_at -- the freshest reviewed record wins. */
    function eventTickers(e){
      var out=[],impacts=arr(e.listed_company_impacts).filter(obj);
      impacts.forEach(function(row){var t=text(row.ticker,'');if(t)out.push(t)});
      arr(e.tickers).forEach(function(t){if(typeof t==='string'&&t)out.push(t)});
      var primary=text(e.primary_ticker,'');if(primary)out.push(primary);
      return out;
    }
    function govEvent(){
      var matches=arr(workspaceEvents()).filter(obj).filter(function(e){
        var award=obj(e.award_change)?e.award_change:{};
        return award.piid===AWARD_PIID&&modNumber(award)===MOD_NUMBER&&eventTickers(e).indexOf(IRDM)>-1;
      });
      if(!matches.length)return null;
      matches.sort(function(a,b){
        var ak=text((obj(a.change)?a.change:{}).known_at,''),bk=text((obj(b.change)?b.change:{}).known_at,'');
        return bk<ak?-1:bk>ak?1:0;
      });
      return matches[0];
    }
    function amountValue(event){
      var rows=arr(event.amounts).filter(obj),row=rows.find(function(r){return r.id==='federal_action_obligation'})||rows[0];
      return row?n(row.value):null;
    }
    /* R12: exact, non-rounding display -- the reviewed obligation is never
     * abbreviated to "$18.4M" the way money() would (§0 gate 1), and never
     * ROUNDED the way toFixed(2) would either: whatever fractional digits the
     * source number carries are shown verbatim, comma-grouped, nothing more. */
    function preciseMoney(v){
      v=n(v);if(v==null)return'—';
      var neg=v<0,parts=String(Math.abs(v)).split('.');
      parts[0]=parts[0].replace(/\B(?=(\d{3})+(?!\d))/g,',');
      return(neg?'−':'')+'$'+parts.join('.');
    }
    /* R4: the receipt bound to THIS action's own transaction record --
     * matched by content_sha256 against award_change.source_identity, never
     * by URL shape (an /awards/ URL is the AWARD snapshot receipt, a
     * different observation from the action that actually carries P00032).
     * R14: no exact sha match => NO source link, never a positional fallback --
     * a missing/absent source_identity or a receipt set with no matching
     * content_sha256 must never fall back to rows[0]: presenting an
     * unrelated first receipt as "Open official receipt" recreates the
     * award-snapshot-vs-transaction provenance error R4 exists to prevent.
     * The government facts still render with no link at all in that case. */
    function receiptUrl(event){
      var award=obj(event.award_change)?event.award_change:{},identity=obj(award.source_identity)?award.source_identity:{},wantSha=text(identity.content_sha256,'');
      var rows=arr((event.evidence||{}).receipts).filter(obj);
      if(!wantSha)return'';
      var pick=rows.find(function(r){return text(r.content_sha256,'')===wantSha});
      if(!pick)return'';
      return safeUrl(pick.url);
    }
    /* R5: govEvent() returning null is ambiguous between "not yet hydrated"
     * (the embedded first-paint slice may not carry this event) and
     * "genuinely absent". Only the latter may say "unavailable" -- see the
     * `governmentworkspacehydrated` re-render pointer in government_revenue.html.j2
     * for why a stale pre-hydration render self-heals without polling here. */
    function govFactHtml(){
      var event=govEvent();
      if(!event){
        if(!workspaceReady())return'<div class="dossier-status" aria-busy="true"><span><b>'+esc(tr('Loading government record','正在加载政府记录'))+'</b></span></div>';
        return'<div class="dossier-empty">'+esc(tr('Government fact unavailable','政府事实不可用'))+'</div>';
      }
      var award=obj(event.award_change)?event.award_change:{},change=obj(event.change)?event.change:{},late=award.is_late_discovery===true,url=receiptUrl(event);
      return(late?'<div class="atlas-chips"><span class="truth late">'+esc(tr('Late discovery','延迟发现'))+'</span></div>':'')+
        '<div class="facts-grid">'+
          factCell(tr('Award / PIID','授标 / PIID'),text(award.piid))+
          factCell(tr('Modification','修订编号'),modNumber(award)||'—')+
          factCell(tr('Obligation','拨款义务'),preciseMoney(amountValue(event)))+
          factCell(tr('Took effect','生效'),date(change.effective_at))+
          factCell(tr('First known to Mastermind','Mastermind 首次获知'),date(change.known_at))+
        '</div>'+
        (url?'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open official receipt','打开官方凭证'))+'</b><span>↗</span></a>':'');
    }

    /* Company Truth -- read-only consumption of the canonical earnings owner's
     * closed per-ticker packet. Only earnings_history-lineage fields render;
     * score_overlay-lineage fields (e.g. summary) are never touched here.
     * R2: bounded timeout races the fetch so a hung network call cannot leave
     * an aria-busy state that lives forever -- it resolves to the same typed
     * unavailable state as any other fetch failure. */
    function withTimeout(promise,ms){
      return new Promise(function(resolve,reject){
        var settled=false,timer=global.setTimeout(function(){
          if(settled)return;settled=true;reject(new Error('timeout'));
        },ms);
        promise.then(function(value){
          if(settled)return;settled=true;global.clearTimeout(timer);resolve(value);
        },function(error){
          if(settled)return;settled=true;global.clearTimeout(timer);reject(error);
        });
      });
    }
    function fetchCompany(t){
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      var chain=global.fetch('/api/company-intelligence/'+encodeURIComponent(t),{credentials:'same-origin',headers:{Accept:'application/json'}}).then(function(r){
        if(r.status!==200)throw new Error('http_'+r.status);
        return r.json();
      }).then(function(data){
        if(!obj(data)||data.available!==true||data.schema!==COMPANY_SCHEMA)throw new Error('contract');
        return data;
      });
      return withTimeout(chain,FETCH_TIMEOUT_MS);
    }
    /* R7: memoize per ticker -- a success is cached (repeated selections and
     * search keystrokes on an already-open IRDM panel never refetch); an
     * in-flight fetch is shared; a failure is NEVER cached, so a fresh
     * selection (which invalidate() always precedes) retries. Restatement
     * (§0 gate 6 / T7) advances on the NEXT fresh load, i.e. after the panel
     * is re-opened -- not mid-display on every keystroke. */
    function loadCompanyPacket(t){
      if(successByTicker[t])return Promise.resolve(successByTicker[t]);
      if(pendingByTicker[t])return pendingByTicker[t];
      var p=fetchCompany(t).then(function(data){
        successByTicker[t]=data;delete pendingByTicker[t];return data;
      },function(error){
        delete pendingByTicker[t];throw error;
      });
      pendingByTicker[t]=p;
      return p;
    }
    function highlightList(items,lineageArr,label){
      items=arr(items);lineageArr=arr(lineageArr);
      var kept=[];
      for(var i=0;i<items.length&&kept.length<2;i++){
        if(lineageArr[i]===LINEAGE_OK&&typeof items[i]==='string'&&items[i])kept.push(items[i]);
      }
      if(!kept.length)return'';
      return'<div class="atlas-sub">'+esc(label)+'</div><ul class="atlas-open">'+kept.map(function(t){return'<li>'+esc(t)+'</li>'}).join('')+'</ul>';
    }
    function sourcesLine(latest){
      /* R15: source-status metadata is lineage too. D4 may disclose the
       * earnings/transcript rails, but must never surface the banned
       * score_overlay rail merely because it arrived in latest.sources. */
      var rows=arr(latest.sources).filter(obj).filter(function(s){return text(s.kind)!=='score_overlay'});
      if(!rows.length)return'';
      return'<div class="limit-copy">'+esc(rows.map(function(s){return text(s.kind)+': '+text(s.status)}).join(' · '))+'</div>';
    }
    function companyHtml(){
      if(companyState==='unavailable')return'<div class="dossier-empty">'+esc(tr('Company packet unavailable','公司数据包不可用'))+'</div>';
      if(companyState!=='ok'||!obj(companyPacket))return'<div class="dossier-status" aria-busy="true"><span><b>'+esc(tr('Loading company packet','正在加载公司数据包'))+'</b></span></div>';
      var data=companyPacket,latest=obj(data.latest_event)?data.latest_event:{},lineage=obj(latest.field_lineage)?latest.field_lineage:{},metricsLineage=obj(lineage.metrics)?lineage.metrics:{},metrics=obj(latest.metrics)?latest.metrics:{};
      var period=(latest.fiscal_year!=null?'FY'+text(latest.fiscal_year):'')+(latest.fiscal_quarter!=null?' Q'+text(latest.fiscal_quarter):'');
      var rows=factCell(tr('Fiscal period','财报周期'),period||'—')+factCell(tr('Call date','电话会日期'),date(latest.call_date));
      /* R9: a null/non-numeric growth figure is SKIPPED entirely -- never a
       * "—" value claim standing in for a number the owner did not assert. */
      if(metricsLineage.revenue_growth_pct===LINEAGE_OK){
        var g=n(metrics.revenue_growth_pct);
        if(g!=null)rows+=factCell(tr('Revenue growth (owner-reported)','收入增长（公司披露）'),(g>0?'+':'')+g+'%');
      }
      var html='<div class="facts-grid">'+rows+'</div>'+
        highlightList(latest.positive_highlights,lineage.positive_highlights,tr('Positive highlights','正面亮点'))+
        highlightList(latest.negative_highlights,lineage.negative_highlights,tr('Negative highlights','负面亮点'));
      if(latest.claim_citations_pending===true)html+='<div class="limit-copy">'+esc(tr('Wording verification pending','措辞核验中'))+'</div>';
      html+=sourcesLine(latest);
      html+='<div class="atlas-asof">'+esc(tr('Company packet as of ','公司数据包截至 ')+date(data.generated_at))+'</div>';
      return html;
    }

    /* Comparison -- FIXED closed-state copy (review amendment 2026-08-20).
     * The producer's own recorded materiality
     * (comparison_state: not_comparable, reason_code:
     * exact_issuer_attributed_denominator_not_available) is the truth this
     * copy mirrors, but the UI performs NO fetch for it: no ratio node ever
     * renders on any input, so nothing here can vary with a network read. */
    function comparisonHtml(){
      return'<p class="limit-copy">'+esc(tr('Not comparable — no issuer-attributed denominator has been asserted.','不可比 — 尚无发行人归属的分母。'))+'</p>'+
        '<p class="limit-copy">'+esc(tr('The government-side materiality record confirms no issuer-attributed denominator exists yet.','政府侧重要性记录确认目前尚无发行人归属的分母。'))+'</p>';
    }

    function researchHtml(){
      return'<p class="atlas-question">'+esc(tr('Watch the next company print or owner packet for a lawful transmission bridge — windows, not certainties, redrawn on each new record.','关注下一次公司财报或所有者数据包，寻找合规的传导桥梁——这些只是观察窗口，并非确定结论，随每份新记录重新绘制。'))+'</p>';
    }

    function render(){
      var host=hostFor();if(!host)return;
      if(ticker!==IRDM){host.hidden=true;host.innerHTML='';return}
      host.hidden=false;
      host.innerHTML=
        '<div class="inspect-label">'+esc(tr('Government fact','政府事实'))+'</div>'+govFactHtml()+
        '<div class="inspect-label">'+esc(tr('Company truth','公司披露'))+'</div>'+companyHtml()+
        '<div class="inspect-label">'+esc(tr('Comparison','可比性'))+'</div>'+comparisonHtml()+
        '<div class="inspect-label">'+esc(tr('Research question','研究问题'))+'</div>'+researchHtml();
    }

    function loadCompany(value){
      var ticket=++epoch;ticker=text(value,'').toUpperCase();
      if(!hostFor())return;
      if(ticker!==IRDM){render();return}
      if(successByTicker[ticker]){companyPacket=successByTicker[ticker];companyState='ok';render();return}
      companyState='loading';companyPacket=null;render();
      loadCompanyPacket(ticker).then(function(data){
        if(ticket!==epoch)return;
        companyPacket=data;companyState='ok';render();
      }).catch(function(){
        if(ticket!==epoch)return;
        companyPacket=null;companyState='unavailable';render();
      });
    }

    return{loadCompany:loadCompany,invalidate:function(){
      epoch++;ticker='';companyState='idle';companyPacket=null;
      pendingByTicker={};successByTicker={};
      var host=hostFor();if(host){host.hidden=true;host.innerHTML=''}
    }};
  };

  global.createGovernmentRevenueBudget=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,hostFor=api.host;
    var contentId=null,detailEpoch=0,loadEpoch=0,detailCache={},loadState='loading',listing=null;

    function validAuthority(value){return obj(value)&&value.tier==='display'&&value.context_only===true&&value.can_rank===false&&value.can_size===false&&value.can_gate===false&&value.can_originate_signal===false&&value.can_add_candidates===false&&value.can_escalate===false}
    function fetchBudget(route){
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      return withAuth({Accept:'application/json'}).then(function(headers){
        return global.fetch('/api/government-revenue/'+route,{credentials:'same-origin',headers:headers});
      }).then(function(response){if(!response.ok)throw new Error('http_'+response.status);return response.json()}).then(function(value){
        if(!obj(value)||value.contract!=='government_budget_program_graph.v1'||value.schema_version!=='1.0.0'||!/^grbg1-[a-f0-9]{24}$/.test(text(value.content_id,''))||!validAuthority(value.authority))throw new Error('contract');
        return value;
      });
    }
    function programKind(value){return value==='procurement_line_item'?tr('P-1 procurement line','P-1 采购项目行'):tr('R-1 RDT&E program element','R-1 研发试验项目要素')}
    function rowsFrom(value){return arr(value.programs).filter(obj).map(function(program){return{id:'budget:'+text(program.program_key),kind:'budget_program',truth:'official',truthCopy:tr("Official President's Budget request","总统预算请求官方记录"),linked:false,defense:true,tickers:[],agency:'Department of Defense',date:value.known_at,title:text(program.name,tr('Unnamed DoD program','未命名国防部项目')),subtitle:programKind(program.kind)+' · '+text(program.native_identifier),program:program,budgetEnvelope:{content_id:value.content_id,known_at:value.known_at,as_of:value.as_of,source_coverage:value.source_coverage,documents:value.documents,limitations:value.limitations}}})}
    function load(){
      var ticket=++loadEpoch;loadState='loading';
      if(typeof api.onRows==='function'&&!listing)api.onRows([],{status:'loading',content_id:null,total:0});
      return fetchBudget('budget-programs').then(function(value){
        if(ticket!==loadEpoch)return listing?rowsFrom(listing):[];
        listing=value;contentId=value.content_id;loadState='ok';
        var rows=rowsFrom(value);
        if(typeof api.onRows==='function')api.onRows(rows,{status:'ok',content_id:contentId,total:rows.length});
        return rows;
      }).catch(function(error){
        if(ticket!==loadEpoch)return listing?rowsFrom(listing):[];
        var message=error&&error.message||'';
        if((message==='http_401'||message==='http_403')&&!authSettled()){
          loadState='loading';
          if(typeof api.onRows==='function')api.onRows([],{status:'loading',content_id:null,total:0});
          return[];
        }
        listing=null;contentId=null;detailCache={};
        loadState=(message==='http_404'||message==='http_503'||message==='contract')?'projection_missing':'unavailable';
        if(typeof api.onRows==='function')api.onRows([],{status:loadState,content_id:null,total:0});
        return[];
      });
    }
    function bindAuthReload(){
      function onAuth(){markAuthSettled();load();}
      if(global.MDXAuth&&typeof global.MDXAuth.onChange==='function')global.MDXAuth.onChange(onAuth);
      else if(typeof global.addEventListener==='function')global.addEventListener('mdx-auth',onAuth);
    }
    bindAuthReload();
    function semanticValue(line,semantic){var cell=arr((line||{}).amounts).find(function(item){return obj(item)&&item.semantic===semantic});return cell?n(cell.amount_usd):null}
    function latestLine(lines){return arr(lines).filter(obj).slice().sort(function(a,b){return(n(b.fiscal_year)||0)-(n(a.fiscal_year)||0)||String(b.known_at||'').localeCompare(String(a.known_at||''))})[0]||null}
    function statusClass(status){return status==='ok'?'ok':status==='partial'?'warn':'muted'}
    function coverageWord(status){return{ok:tr('Collected','已采集'),partial:tr('Partly collected','部分采集'),uncollected:tr('Not collected','未采集')}[status]||tr('Status unclear','状态未知')}
    function coverageCard(label,rail){rail=obj(rail)?rail:{};var status=text(rail.status,'uncollected');return'<div class="budget-rail '+esc(statusClass(status))+'"><span>'+esc(label)+'</span><b>'+esc(coverageWord(status))+'</b><small>'+esc(text(rail.reason,tr('No source rail is active.','来源链路尚未启用。')))+'</small></div>'}
    function amountCard(label,value,copy,primary){return'<div class="budget-amount'+(primary?' primary':'')+'"><span>'+esc(label)+'</span><b>'+esc(money(value))+'</b><small>'+esc(copy)+'</small></div>'}
    function lineCards(lines){return arr(lines).filter(obj).map(function(line){var native=obj(line.native_identifier)?line.native_identifier:{},provenance=obj(line.provenance)?line.provenance:{};return'<article class="budget-line-card"><div><span class="budget-line-tag">'+esc(String(line.exhibit||'').toUpperCase()+' · FY '+text(line.fiscal_year))+'</span><strong>'+esc(text(line.program_name))+'</strong><small>'+esc(text(line.component)+' · '+text(line.appropriation_code)+' · '+text(line.budget_activity))+'</small></div><div><b>'+esc(money(semanticValue(line,'president_budget_request_total')))+'</b><small>'+esc(tr('total request','请求总额'))+'</small></div><code>'+esc(text(native.value))+' · p.'+esc(text(provenance.page_number))+'</code></article>'}).join('')}
    function reviewedBridges(detail){var edges=arr(detail.documentary_edges).filter(obj).filter(function(edge){return edge.edge_type==='reviewed_documentary'&&edge.from_type==='program'&&edge.to_type==='award'});if(!edges.length)return'<div class="budget-null"><strong>'+esc(tr('No reviewed award bridge','无经核验的授标桥接'))+'</strong><span>'+esc(tr('No beneficiary, award allocation, or economic transmission is inferred from the program name.','不会根据项目名称推断受益者、授标分配或经济传导。'))+'</span></div>';return edges.map(function(edge){return'<article class="budget-bridge"><span class="truth reviewed">'+esc(tr('Reviewed documentary link','经核验的文件关联'))+'</span><strong>'+esc(text(edge.to_id))+'</strong><small>'+esc(tr('Exact award identity · economic weight intentionally null','精确授标身份 · 经济权重有意留空'))+'</small></article>'}).join('')}
    function evidenceHtml(detail){
      var docs=arr(detail.documents).filter(obj),lines=arr(detail.lines).filter(obj),limitations=arr(detail.limitations),html='';
      lines.forEach(function(line){var source=obj(line.source)?line.source:{},provenance=obj(line.provenance)?line.provenance:{},doc=docs.find(function(item){return item.receipt_id===source.receipt_id})||{},url=safeUrl(source.source_url||doc.source_url);html+='<article class="receipt"><div class="receipt-kind">'+esc(tr('DoD request exhibit line','国防部预算请求表行'))+'</div><h3>'+esc(text(line.program_name))+'</h3><p>'+esc(tr("President's Budget request evidence only—not authorization, enacted appropriation, execution, award value, backlog, or revenue.","仅为总统预算请求证据，并非授权、已颁拨款、执行、授标价值、积压或收入。"))+'</p><div class="receipt-code">'+esc('line_key: '+text(line.line_key)+'\nreceipt_id: '+text(source.receipt_id)+'\ndocument_sha256: '+text(source.document_sha256)+'\nextraction_sha256: '+text(doc.extraction_semantic_sha256)+'\npage: '+text(provenance.page_number)+'\npage_text_sha256: '+text(provenance.page_text_sha256)+'\nknown_at: '+text(line.known_at))+'</div>'+(url?'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open official DoD exhibit','打开国防部官方表件'))+'</b><span>↗</span></a>':'')+'</article>'});
      html+='<article class="receipt"><div class="receipt-kind">'+esc(tr('Authority boundary','权限边界'))+'</div><h3>'+esc(tr('Display-only context','仅展示情境'))+'</h3><p>'+esc(limitations.join(' · '))+'</p><div class="receipt-code">can_rank: false\ncan_size: false\ncan_gate: false\ncan_originate_signal: false\neconomic_weight: null</div></article>';
      return html;
    }
    function renderDetail(row,detail,host){
      var program=detail.program||row.program||{},lines=arr(detail.lines).filter(obj),latest=latestLine(lines),coverage=obj(detail.source_coverage)?detail.source_coverage:{},doc=arr(detail.documents).filter(obj)[0]||{},src=safeUrl(doc.source_url),request=latest?semanticValue(latest,'president_budget_request_total'):null,disc=latest?semanticValue(latest,'discretionary_request'):null,recon=latest?semanticValue(latest,'reconciliation_request'):null,enacted=latest?semanticValue(latest,'prior_year_enacted_reference'):null;
      host.className='inspector budget-inspector';
      host.innerHTML='<div class="inspect-hero budget-hero"><div class="inspect-kicker"><span class="inspect-type">'+esc(tr('DoD budget program','国防部预算项目'))+'</span><span class="inspect-id">'+esc(text(program.native_identifier))+'</span></div><h2>'+esc(text(program.name))+'</h2><div class="inspect-meta">'+esc(programKind(program.kind)+' · '+tr("President's Budget request lane","总统预算请求链路"))+'</div><div class="inspect-truth"><span class="truth official">'+esc(tr('Official request evidence','官方请求证据'))+'</span><span class="truth derived">'+esc(tr('Display only','仅展示'))+'</span></div><div class="inspect-actions"><button class="tool-btn" type="button" data-budget-evidence>'+esc(tr('View source chain','查看来源链'))+'</button><button class="tool-btn" type="button" data-budget-copy>'+esc(tr('Copy link','复制链接'))+'</button>'+(src?'<a class="tool-btn" href="'+esc(src)+'" target="_blank" rel="noopener">'+esc(tr('Official exhibit ↗','官方表件 ↗'))+'</a>':'')+'</div></div>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Latest request frame','最新请求框架'))+'</div><div class="budget-amounts">'+amountCard(tr('FY '+text(latest&&latest.fiscal_year)+' total request','FY '+text(latest&&latest.fiscal_year)+' 请求总额'),request,tr('President’s Budget total','总统预算请求总额'),true)+amountCard(tr('Discretionary request','可自由支配请求'),disc,tr('Source-native column','来源原生列'),false)+amountCard(tr('Mandatory request','强制性请求'),recon,tr('Source-native column','来源原生列'),false)+amountCard(tr('Prior enacted reference','上年已颁参考'),enacted,tr('Historical reference only','仅历史参考'),false)+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Funding-stage firewall','资金阶段防火墙'))+'</div><div class="budget-coverage">'+coverageCard(tr("President's Budget request",'总统预算请求'),coverage.president_budget_request)+coverageCard(tr('Authorization','授权'),coverage.authorization)+coverageCard(tr('Enacted appropriation','已颁拨款'),coverage.appropriation_enacted)+coverageCard(tr('Execution','执行'),coverage.execution)+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Source-native program lines','来源原生项目行'))+'</div><div class="budget-lines">'+(lines.length?lineCards(lines):'<div class="budget-null">'+esc(tr('No retained line is available.','没有可用的保留项目行。'))+'</div>')+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Reviewed award bridges','经核验的授标桥接'))+'</div><div class="budget-bridges">'+reviewedBridges(detail)+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Research boundary','研究边界'))+'</div><div class="budget-boundary"><strong>'+esc(tr('Request evidence is upstream—not funded revenue.','请求证据位于上游，并非已获资金收入。'))+'</strong><span>'+esc(tr('This rail cannot rank, size, gate, add candidates, escalate, or originate a Prophet signal. Issuer transmission remains unresolved until exact reviewed evidence exists.','该链路不得排序、调整仓位、设闸、添加候选、升级或生成 Prophet 信号。在精确证据经核验前，发行人传导保持未解析。'))+'</span></div></section>';
      var evidence=host.querySelector('[data-budget-evidence]');if(evidence)evidence.addEventListener('click',function(){if(typeof api.openEvidenceDrawer==='function')api.openEvidenceDrawer({title:tr('DoD budget source chain','国防部预算来源链'),html:evidenceHtml(detail),focus:evidence})});
      var copy=host.querySelector('[data-budget-copy]');if(copy)copy.addEventListener('click',function(){if(typeof api.copyLink==='function')api.copyLink(copy)});
      if(typeof api.setMobile==='function')api.setMobile(text(program.name),programKind(program.kind));
    }
    function render(row){
      var host=hostFor(),ticket=++detailEpoch;if(!host||!row)return;
      host.className='inspector budget-inspector';host.innerHTML='<div class="budget-loading" aria-busy="true"><span class="budget-scan" aria-hidden="true"></span><strong>'+esc(tr('Verifying budget evidence graph','正在核验预算证据图谱'))+'</strong><small>'+esc(tr('Loading precomputed program lines and funding-stage boundaries…','正在加载预计算项目行及资金阶段边界…'))+'</small></div>';
      var key=text((row.program||{}).program_key,'');if(!key)return;
      var cached=detailCache[key];if(cached&&cached.content_id===contentId){renderDetail(row,cached,host);return}
      fetchBudget('program/'+encodeURIComponent(key)).then(function(detail){if(ticket!==detailEpoch||detail.content_id!==contentId||(typeof api.isSelected==='function'&&!api.isSelected(row.id)))throw new Error('stale');detailCache[key]=detail;renderDetail(row,detail,host)}).catch(function(){if(ticket!==detailEpoch)return;host.innerHTML='<div class="dossier-error"><strong>'+esc(tr('Budget evidence unavailable','预算证据不可用'))+'</strong><br>'+esc(tr('No request amount or program bridge was reconstructed in the browser.','浏览器未重建任何请求金额或项目桥接。'))+'</div>'});
    }
    return{load:load,refresh:function(){if(!listing||loadState!=='ok')return[];var rows=rowsFrom(listing);if(typeof api.onRows==='function')api.onRows(rows,{status:'ok',content_id:contentId,total:rows.length});return rows},render:render,invalidate:function(){detailEpoch++},state:function(){return loadState}};
  };

  /* D5 Program/Platform Dossier -- composed `government_program_dossier.v1`
   * bundle (engine/government_revenue/program_dossier.py), read-only, one
   * static site twin fetched once: government-revenue-data/program-dossier.json.
   * Same cookie-plane fetch idiom as the Identity Atlas above: same-origin
   * credentials, a 401/403 degrades to the members-only teaser, any other
   * failure is a typed `unavailable`, a contract mismatch is `invalid` --
   * never a crash and never a blank (freeze DEFENSE_D5_PROGRAM_GRAPH_
   * ARCHITECTURE_FREEZE.md SS4). The bundle-level pair `dossiers: []` +
   * `ontology_graph_id: null` is the frozen page-level "no certified
   * ontology yet" state (SS4); `dossiers: []` with a non-null graph id is
   * the distinct, valid "certified ontology, zero current programs" state.
   *
   * Every rail renders a typed plain-word state, never a blank (SS4/SS6).
   * No numeric budget/request figure is ever read, summed or compared here
   * (T5 -- this module never calls a money/number formatter). No firm-to-
   * firm edge or adjacency is ever rendered (T12). No node-link graph is
   * rendered as the primary surface (SS9). Copy strings below reproduce the
   * frozen bilingual copy table (D5 mode=programs surface, 2026-08-23)
   * verbatim for every enum-keyed typed state and gap; ordinary structural
   * labels (section headers already given by the freeze's six questions
   * aside) follow the same plain house idiom used throughout this file. */
  global.createGovernmentRevenueProgramDossier=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,tr=api.tr,hostFor=api.host;
    var DOSSIER_PATH='government-revenue-data/program-dossier.json';
    var pending=null,bundle=null,loadState='idle',epoch=0;

    function failure(code){var e=new Error(code);e.code=code;return e}
    function ensure(){
      if(pending)return pending;
      if(typeof global.fetch!=='function'){loadState='unavailable';return Promise.resolve(false)}
      loadState='loading';
      pending=global.fetch(DOSSIER_PATH,{credentials:'same-origin'}).then(function(response){
        if(response.status===401||response.status===403)throw failure('locked');
        if(!response.ok)throw failure('unavailable');
        return response.json();
      }).then(function(value){
        if(!obj(value)||value.contract!=='government_program_dossier.v1'||!/^1\./.test(text(value.schema_version,'')))throw failure('invalid');
        bundle=value;
        loadState=value.ontology_graph_id==null?'ontology_unavailable':(arr(value.dossiers).filter(obj).length?'ok':'empty');
        return true;
      }).catch(function(error){bundle=null;loadState=(error&&error.code)||'unavailable';return false});
      return pending;
    }

    // --- frozen typed-state copy (rail-scoped; verbatim from the D5 copy table) ---
    function copyProgramUmbrella(){return tr('Program relationship: unresolved / not asserted','项目归属:未解决/未认定')}
    function copyProgramConflicted(){return tr('Program attribution: conflicting reviewed claims — attribution withheld','项目归属:复核证据冲突——暂不认定')}
    function copyQuantityGap(){return tr('Quantity is not representable from the award tape (v1); available once SAR/budget sources land','数量无法由合同事件源表示(v1);待SAR/预算来源接入后提供')}
    function copyEconomicsGap(){return tr('No reviewed economic exposure — participation is not a revenue share','无已复核经济敞口——参与关系不代表收入份额')}
    function copyContractTypeGap(){return tr('Contract type: available once an event is reviewed against this program','合同类型:待事件与该项目完成复核关联后提供')}
    function copyGaoGap(){return tr('GAO/DOT&E assessment: not yet on file','GAO/DOT&E 评估:暂未收录')}
    // Count-free (MEDIUM-6 repair): the row shape carries only a bool
    // (`shared_scope`), never a program count, so the copy must never name
    // a specific number -- a second shared-scope supplier spanning two or
    // five programs would otherwise render a fabricated "three".
    function copySharedScope(){return tr('Supplier scope shared across programs','供应范围横跨多个项目')}
    function copyHistorical(){return tr('historical only','仅历史记录')}
    function copyIssuerNotAsserted(){return tr('Issuer path: not asserted','发行人路径:未认定')}
    function copyParticipationLimitation(){return tr('Companies on this rail participate in the same program; no commercial relationship between them is asserted.','本栏公司参与同一项目;不主张它们之间存在任何商业关系。')}
    function copyAllocationLimitation(){return tr('Reviewed participation is not a share of revenue. Nothing here allocates award value to a ticker.','已复核的参与关系不代表收入份额。此处不将合同金额分配至任何股票。')}
    function copyParticipantsNotReviewed(){return tr('Participants not yet reviewed','参与方尚未复核')}
    function copyParticipantsReviewedNone(){return tr('Reviewed — no admissible participants','已复核——无可采信参与方')}
    function copyMilestonesNotReviewed(){return tr('Forward milestones not yet reviewed','前瞻里程碑尚未复核')}
    function copyMilestonesReviewedNone(){return tr('Reviewed — no admissible forward milestone','已复核——无可采信的前瞻里程碑')}
    function copyMilestonesReviewedEmpty(){return tr('Reviewed — no upcoming milestone on file','已复核——暂无即将到来的里程碑')}
    function copyBudget(stateName){return stateName==='projection_missing'?tr('Budget request rail unavailable — no budget projection exists yet (planned for a later wave)','预算请求栏不可用——预算投影尚未建立(规划于后续阶段)'):tr('Budget source unavailable','预算来源不可用')}
    function copyEconomicRelationships(){return tr('No reviewed economic-relationship data','无已复核的经济关系数据')}
    // House "windows, not certainties" idiom (vector.html.j2), reused verbatim.
    function copyWindowsNotCertainties(){return tr('Windows, not certainties. The watch window is re-drawn nightly as the evidence changes.','这是观察窗口，不是确定预测。证据变化时，窗口会在每晚重新绘制。')}
    var QUESTIONS=function(){return[
      tr('What is this?','这是什么?'),
      tr('Why does government need it?','政府为何需要?'),
      tr('What changed?','有何变化?'),
      tr('Which listed companies have reviewed access?','哪些上市公司经复核参与?'),
      tr('What remains unresolved?','尚有哪些未决?'),
      tr('What happens next?','接下来是什么?')
    ]};

    function chip(kind,label){return'<span class="truth '+esc(kind)+'">'+esc(label)+'</span>'}
    function roleWord(role){
      // Closed v1 role enum (freeze SS3.1); the pilot's three values get
      // house copy, any other value degrades to a mechanical, non-invented
      // snake_case-to-words transform rather than a fabricated label.
      var known={prime_contractor:tr('Prime contractor','主承包商'),teaming_partner:tr('Teaming partner','联合承包伙伴'),supplier:tr('Supplier','供应商')};
      return known[role]||text(role,'').replace(/_/g,' ')
    }
    function securityWord(stateName){
      if(stateName==='verified_live')return tr('verified','已核验');
      if(stateName==='listing_terminated')return tr('listing ended','上市已终止');
      if(stateName==='not_in_si_universe')return tr('not in the covered listing universe','不在已覆盖的上市范围内');
      return tr('unconfirmed','未确认')
    }
    function windowWords(window){
      window=obj(window)?window:{};
      var from=text(window.from,''),to=text(window.to,'');
      if(from&&to)return from+' – '+to;
      return to||from||tr('window not specified','窗口未指定')
    }
    function railState(rail,key){rail=obj(rail)?rail:{};return text(rail[key],'not_reviewed')}
    function gapCopyFor(stateName){return stateName==='conflicted'?copyProgramConflicted():copyProgramUmbrella()}

    function rowsFrom(value){
      return arr((value||{}).dossiers).filter(obj).map(function(d){
        var pi=obj(d.program_identity)?d.program_identity:{},reviewed=pi.state==='reviewed';
        return{
          id:'program:'+text(d.program_id),kind:'program_dossier',
          truth:reviewed?'reviewed':'derived',
          truthCopy:reviewed?tr('Program identity reviewed','项目身份已核验'):gapCopyFor(pi.state),
          linked:false,defense:true,tickers:[],agency:text(pi.sponsor_agency,''),
          date:text((value||{}).generated_at,''),
          title:reviewed?text(pi.name,text(d.program_id)):text(d.program_id),
          subtitle:reviewed?text(pi.phase,''):gapCopyFor(pi.state),
          dossier:d,bundleLimitations:arr((value||{}).limitations)
        };
      });
    }

    function load(){
      var ticket=++epoch;
      if(typeof api.onRows==='function')api.onRows([],{status:'loading',content_id:null,total:0});
      return ensure().then(function(){
        if(ticket!==epoch)return;
        var ok=loadState==='ok'||loadState==='empty',rows=ok?rowsFrom(bundle):[];
        if(typeof api.onRows==='function')api.onRows(rows,{status:loadState,content_id:bundle&&bundle.content_id||null,total:rows.length});
      });
    }
    function bindAuthReload(){
      function onAuth(){markAuthSettled();if(loadState!=='locked')return;pending=null;load()}
      if(global.MDXAuth&&typeof global.MDXAuth.onChange==='function')global.MDXAuth.onChange(onAuth);
      else if(typeof global.addEventListener==='function')global.addEventListener('mdx-auth',onAuth);
    }
    bindAuthReload();

    // --- six-question sections (freeze SS9, in the frozen order) ---
    function sectionWhatIsThis(d){
      var pi=obj(d.program_identity)?d.program_identity:{};
      if(pi.state!=='reviewed')return'<p class="inspect-value">'+esc(gapCopyFor(pi.state))+'</p>';
      var meta=[pi.phase?tr('Phase: ','阶段：')+text(pi.phase):'',pi.sponsor_agency?tr('Sponsor: ','主管机构：')+text(pi.sponsor_agency):''].filter(Boolean).join(' · ');
      var out='<p class="inspect-value"><strong>'+esc(text(pi.name))+'</strong></p>';
      if(meta)out+='<p class="inspect-value">'+esc(meta)+'</p>';
      out+='<p class="inspect-value">'+esc(pi.latest_platform_name?tr('Latest block in the reviewed record: ','已核验记录中的最新型别：')+text(pi.latest_platform_name):tr('No platform/block variant is yet in the reviewed record.','已核验记录中尚无型别/批次变体。'))+'</p>';
      // LOW-2 repair: NO "read being updated" chip is rendered here. It was
      // gated on `program_revision > 1`, which LATCHES FOREVER -- revision
      // never decreases, so a pure rename from years ago would render the
      // transient D3 chip permanently. D3's own chip (cycle_app.js
      // firedBannerHTML) is gated on an engine-maintained boolean latch
      // (`tw.state==='FIRED' && tw.latched`), not a client-side recency
      // window -- there is no time-based mechanism in D3 to mirror. The
      // frozen `government_program_dossier.v1` program_identity rail shape
      // (freeze SS4) carries no `known_at`/succession timestamp of any
      // kind, so the reviewer's fallback (`program_revision > 1 AND the
      // resolved revision's known_at within 14 days of the bundle as_of`)
      // cannot be computed client-side without an engine/schema change,
      // which is out of this packet's scope. `bundle.generated_at` is not
      // a substitute: it refreshes every nightly build regardless of
      // whether this row's revision actually changed, so gating on it
      // would still effectively latch (or worse, fabricate recency).
      // Removed rather than ship either the original bug or a fabricated
      // proxy; a correct implementation needs a revision-scoped `known_at`
      // added to the rail by a future engine packet.
      return out;
    }
    function sectionWhy(d){
      var cap=obj(d.capability)?d.capability:{},out='';
      if(cap.state!=='reviewed'){
        out+='<p class="inspect-value">'+esc(gapCopyFor(cap.state))+'</p>';
      }else{
        out+='<p class="inspect-value"><strong>'+esc(text(cap.name))+'</strong></p>';
        out+='<p class="inspect-value">'+esc(text(cap.need_statement,''))+'</p>';
      }
      // Freeze SS9: the quantity gap is named ALWAYS in v1, reviewed link or not.
      out+='<div class="budget-null"><span>'+esc(copyQuantityGap())+'</span></div>';
      out+='<div class="budget-null"><span>'+esc(copyEconomicsGap())+'</span></div>';
      return out;
    }
    function sectionChanged(d){
      var aw=obj(d.awards)?d.awards:{},src=railState(aw,'source_state'),link=railState(aw,'link_state'),out='';
      if(link==='conflicted'){
        out+='<div class="budget-rail warn"><span>'+esc(tr('Award attribution','授标归属'))+'</span><b>'+esc(tr('Event attribution conflicted — under review','事件归属存在冲突——复核中'))+'</b></div>';
      }else if(src==='current'){
        var msg=link==='reviewed_none'?tr('Award tape current — reviewed: no linkable events on the tape','合同事件源为最新——已复核:暂无可关联事件'):tr('Award tape current — no event reviewed against this program yet','合同事件源为最新——尚无事件与该项目完成复核关联');
        out+='<div class="budget-rail'+(link==='reviewed'?' ok':' warn')+'"><span>'+esc(tr('Award source','合同事件源'))+'</span><b>'+esc(msg)+'</b></div>';
      }else{
        var srcCopy=src==='partial'?tr('Award source partial','合同事件源部分可用'):src==='stale'?tr('Award source stale (source latency: days to weeks)','合同事件源滞后(来源延迟数天至数周)'):tr('Award source unavailable','合同事件源不可用');
        out+='<div class="budget-rail warn"><span>'+esc(tr('Award source','合同事件源'))+'</span><b>'+esc(srcCopy)+'</b></div>';
      }
      // Freeze SS9: contract type is read-only from the award plane joined on
      // a reviewed program_event_link; this build never performs that join
      // (see the packet's reported GAP), so the named gap always renders.
      out+='<div class="budget-null"><span>'+esc(copyContractTypeGap())+'</span></div>';
      return out;
    }
    function sectionParticipants(d){
      var p=obj(d.participants)?d.participants:{},stateName=railState(p,'state'),out='';
      if(stateName==='reviewed'){
        var rows=arr(p.rows).filter(obj);
        if(!rows.length){
          out+='<div class="budget-null"><strong>'+esc(copyParticipantsReviewedNone())+'</strong></div>';
        }else{
          out+='<div class="atlas-chips" style="display:grid;gap:8px">'+rows.map(function(row){
            var reviewedIssuer=row.issuer_path_state==='reviewed';
            var issuerBit=reviewedIssuer?(text(row.central_id,'')+' · '+securityWord(row.public_security)):copyIssuerNotAsserted();
            var chips=chip(reviewedIssuer?'reviewed':'derived',reviewedIssuer?tr('reviewed','已核验'):tr('not asserted','未认定'))
              +(row.historical?chip('historic',copyHistorical()):'')
              +(row.shared_scope?chip('derived',copySharedScope()):'');
            return'<article class="atlas-entity'+(reviewedIssuer?'':' derived')+'"><div class="atlas-entity-top"><div><span class="atlas-entity-name">'+esc(roleWord(row.role))+(row.role_scope?' — '+esc(text(row.role_scope)):'')+'</span><span class="atlas-entity-meta">'+esc(issuerBit)+'</span></div>'+chips+'</div></article>';
          }).join('')+'</div>';
        }
      }else{
        out+='<div class="budget-null"><strong>'+esc(stateName==='conflicted'?copyProgramConflicted():stateName==='reviewed_none'?copyParticipantsReviewedNone():copyParticipantsNotReviewed())+'</strong></div>';
      }
      // Freeze SS4: both limitation strings are populated on every rail
      // state, not only `reviewed` -- render them unconditionally (T12).
      out+='<p class="limit-copy">'+esc(copyParticipationLimitation())+'</p>';
      out+='<p class="limit-copy">'+esc(copyAllocationLimitation())+'</p>';
      return out;
    }
    function sectionUnresolved(d){
      var budget=obj(d.budget)?d.budget:{},out='';
      out+='<div class="budget-rail warn"><span>'+esc(tr('Budget','预算'))+'</span><b>'+esc(copyBudget(railState(budget,'state')))+'</b></div>';
      out+='<div class="budget-rail"><span>'+esc(tr('Economic relationships','经济关系'))+'</span><b>'+esc(copyEconomicRelationships())+'</b></div>';
      var sharedRow=arr((obj(d.participants)?d.participants:{}).rows).filter(obj).some(function(row){return row.shared_scope});
      if(sharedRow)out+='<div class="budget-rail warn"><span>'+esc(tr('Supplier scope','供应范围'))+'</span><b>'+esc(copySharedScope())+'</b></div>';
      out+='<div class="budget-rail warn"><span>'+esc(tr('Oversight','监督'))+'</span><b>'+esc(copyGaoGap())+'</b></div>';
      return out;
    }
    function sectionNext(d){
      var m=obj(d.milestones)?d.milestones:{},stateName=railState(m,'state');
      if(stateName==='reviewed'){
        var rows=arr(m.rows).filter(obj);
        if(!rows.length)return'<div class="budget-null"><strong>'+esc(copyMilestonesReviewedEmpty())+'</strong></div>';
        return rows.map(function(row){
          var when=row.temporal_kind==='window'?windowWords(row.window):text(row.date);
          return'<div class="budget-rail ok"><span>'+esc(tr('Forward milestone','前瞻里程碑'))+'</span><b>'+esc(text(row.title))+'</b><small>'+esc(when)+'</small></div>';
        }).join('')+'<p class="limit-copy">'+esc(copyWindowsNotCertainties())+'</p>';
      }
      return'<div class="budget-null"><strong>'+esc(stateName==='conflicted'?copyProgramConflicted():stateName==='reviewed_none'?copyMilestonesReviewedNone():copyMilestonesNotReviewed())+'</strong></div>';
    }
    function sectionInspectorIds(d){
      var pi=obj(d.program_identity)?d.program_identity:{},cap=obj(d.capability)?d.capability:{},aw=obj(d.awards)?d.awards:{},p=obj(d.participants)?d.participants:{},m=obj(d.milestones)?d.milestones:{};
      var lines=['program_id: '+text(d.program_id)];
      if(pi.state==='reviewed'){
        lines.push('program_revision: '+text(pi.program_revision));
        if(pi.latest_platform_id)lines.push('latest_platform_id: '+text(pi.latest_platform_id));
      }
      if(cap.state==='reviewed'){
        lines.push('capability_id: '+text(cap.capability_id));
        lines.push('program_capability_link_id: '+text(cap.program_capability_link_id));
      }
      if(arr(aw.program_event_link_ids).length)lines.push('program_event_link_ids: '+arr(aw.program_event_link_ids).join(', '));
      if(arr(aw.event_ids).length)lines.push('event_ids: '+arr(aw.event_ids).join(', '));
      arr(p.rows).filter(obj).forEach(function(row){lines.push('role_assertion_id ('+text(row.role)+'): '+text(row.role_assertion_id))});
      arr(m.rows).filter(obj).forEach(function(row){lines.push('milestone_id: '+text(row.milestone_id))});
      return'<article class="receipt"><div class="receipt-kind">'+esc(tr('Technical identity','技术标识'))+'</div><div class="receipt-code">'+esc(lines.join('\n'))+'</div></article>';
    }
    function render(row){
      var host=hostFor();if(!host||!row)return;
      var d=obj(row.dossier)?row.dossier:{},pi=obj(d.program_identity)?d.program_identity:{},reviewed=pi.state==='reviewed';
      var title=reviewed?text(pi.name,text(d.program_id)):text(d.program_id);
      var questions=QUESTIONS();
      var sections=[sectionWhatIsThis(d),sectionWhy(d),sectionChanged(d),sectionParticipants(d),sectionUnresolved(d),sectionNext(d)];
      var stanceChips=chip(reviewed?'reviewed':'derived',reviewed?tr('Program identity reviewed','项目身份已核验'):gapCopyFor(pi.state))
        +chip('derived',tr('Display only','仅展示'))
        +chip('derived',tr("Watch — don't chase",'观察，不追逐'));
      host.className='inspector program-inspector';
      host.innerHTML=
        '<div class="inspect-hero"><div class="inspect-kicker"><span class="inspect-type">'+esc(tr('Program Dossier','项目档案'))+'</span><span class="inspect-id">'+esc(text(d.program_id))+'</span></div><h2>'+esc(title)+'</h2><div class="inspect-truth">'+stanceChips+'</div></div>'+
        questions.map(function(question,i){return'<section class="inspect-section"><div class="inspect-label">'+esc(question)+'</div>'+sections[i]+'</section>'}).join('')+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Inspector · technical identity','检查器 · 技术标识'))+'</div>'+sectionInspectorIds(d)+'</section>'+
        (arr(row.bundleLimitations).length?'<section class="inspect-section"><div class="inspect-label">'+esc(tr('Read-model limitations','读取模型限制'))+'</div><div class="limit-copy">'+esc(arr(row.bundleLimitations).join(' · '))+'</div></section>':'');
      if(typeof api.setMobile==='function')api.setMobile(title,tr('Program Dossier','项目档案'));
    }

    return{
      load:load,
      refresh:function(){var ok=loadState==='ok'||loadState==='empty',rows=ok?rowsFrom(bundle):[];if(typeof api.onRows==='function')api.onRows(rows,{status:loadState,content_id:bundle&&bundle.content_id||null,total:rows.length});return rows},
      render:render,
      invalidate:function(){},
      state:function(){return loadState}
    };
  };
  /* D6-B1 FMS congressional-notification rail -- read-only projection of
   * `government_fms_case.v1` (engine/government_revenue/fms_cases.py). One
   * fetch of the full case graph; every case already carries its complete
   * observation history (spec §4), so unlike the DoD budget rail above this
   * factory never opens a second per-case detail request. Stage is always
   * `congressional_notification` in v1 -- this file never computes, stores,
   * or displays a review-period-elapsed conclusion (freeze §4.4, T3). Values
   * are proposed-sale estimates and are never summed across cases (T13). The
   * five-answer copy strings below reproduce the frozen U5 bilingual table
   * (DEFENSE_D6B1_FMS_IMPLEMENTATION_SPEC_2026-08-25.md §9.3) verbatim. */
  global.createGovernmentRevenueFms=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,hostFor=api.host;
    var contentId=null,loadEpoch=0,loadState='loading',listing=null;

    function validAuthority(value){return obj(value)&&value.tier==='display'&&value.context_only===true&&value.can_rank===false&&value.can_size===false&&value.can_gate===false&&value.can_originate_signal===false&&value.can_add_candidates===false&&value.can_escalate===false}
    function fetchFms(route){
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      return withAuth({Accept:'application/json'}).then(function(headers){
        return global.fetch('/api/government-revenue/'+route,{credentials:'same-origin',headers:headers});
      }).then(function(response){if(!response.ok)throw new Error('http_'+response.status);return response.json()}).then(function(value){
        if(!obj(value)||value.contract!=='government_fms_case.v1'||value.schema_version!=='1.0.0'||!/^grfms1-[a-f0-9]{24}$/.test(text(value.content_id,''))||!validAuthority(value.authority))throw new Error('contract');
        return value;
      });
    }
    function rowsFrom(value){return arr(value.cases).filter(obj).map(function(c){return{id:'fms:'+text(c.case_key),kind:'fms_case',truth:'official',truthCopy:tr('Official 36(b) congressional notification','36(b) 国会通知官方记录'),linked:false,defense:true,tickers:[],agency:null,date:value.known_at,title:text(c.capability_title,text(c.customer_country)),subtitle:text(c.transmittal_number,'—')+' · '+text(c.customer_country),case:c,fmsEnvelope:{content_id:value.content_id,known_at:value.known_at,as_of:value.as_of,coverage:value.coverage,limitations:value.limitations}}})}
    function load(){
      var ticket=++loadEpoch;loadState='loading';
      if(typeof api.onRows==='function'&&!listing)api.onRows([],{status:'loading',content_id:null,total:0});
      return fetchFms('fms-cases').then(function(value){
        if(ticket!==loadEpoch)return listing?rowsFrom(listing):[];
        listing=value;contentId=value.content_id;loadState='ok';
        var rows=rowsFrom(value);
        if(typeof api.onRows==='function')api.onRows(rows,{status:'ok',content_id:contentId,total:rows.length});
        return rows;
      }).catch(function(error){
        if(ticket!==loadEpoch)return listing?rowsFrom(listing):[];
        var message=error&&error.message||'';
        if((message==='http_401'||message==='http_403')&&!authSettled()){
          loadState='loading';
          if(typeof api.onRows==='function')api.onRows([],{status:'loading',content_id:null,total:0});
          return[];
        }
        listing=null;contentId=null;
        loadState=(message==='http_404'||message==='http_503'||message==='contract')?'unavailable':'unavailable';
        if(typeof api.onRows==='function')api.onRows([],{status:loadState,content_id:null,total:0});
        return[];
      });
    }
    function bindAuthReload(){
      function onAuth(){markAuthSettled();load();}
      if(global.MDXAuth&&typeof global.MDXAuth.onChange==='function')global.MDXAuth.onChange(onAuth);
      else if(typeof global.addEventListener==='function')global.addEventListener('mdx-auth',onAuth);
    }
    bindAuthReload();
    function contractorRow(item){return'<article class="budget-bridge"><span class="truth observed">'+esc(tr('Named in source — identity not reviewed','来源点名 — 身份未审核'))+'</span><strong>'+esc(text(item.name_as_printed))+'</strong>'+(item.location_as_printed?'<small>'+esc(text(item.location_as_printed))+'</small>':'')+'</article>'}
    function evidenceHtml(c){
      var html='';
      arr(c.observations).filter(obj).forEach(function(o){
        html+='<article class="receipt"><div class="receipt-kind">'+esc(text(o.source_surface)+' · '+text(o.kind))+'</div><p>'+esc(tr('Version','版本')+' '+text(o.version))+'</p><div class="receipt-code">'+esc('observation_id: '+text(o.observation_id)+'\nsha256: '+text(o.response_sha256)+'\nobserved_at: '+text(o.observed_at)+'\nknown_at: '+text(o.known_at))+'</div>'+(safeUrl(o.source_url)?'<a class="source-link" href="'+esc(safeUrl(o.source_url))+'" target="_blank" rel="noopener"><b>'+esc(tr('Open source receipt ↗','打开来源凭证 ↗'))+'</b><span>↗</span></a>':'')+'</article>';
      });
      return html;
    }
    function render(row){
      var host=hostFor();if(!host||!row)return;
      var c=row.case||{},env=row.fmsEnvelope||{},cov=obj(c.source_coverage)?c.source_coverage:{},clocks=obj(c.clocks)?c.clocks:{},notif=obj(clocks.official_notification_date)?clocks.official_notification_date:{},pub=obj(clocks.official_web_publication_date)?clocks.official_web_publication_date:{},contractors=arr(c.contractors).filter(obj);
      host.className='inspector budget-inspector';
      host.innerHTML='<div class="inspect-hero budget-hero"><div class="inspect-kicker"><span class="inspect-type">'+esc(tr('FMS congressional notification','FMS 国会通知'))+'</span><span class="inspect-id">'+esc(text(c.transmittal_number,'—'))+'</span></div><h2>'+esc(text(c.customer_country))+'</h2><div class="inspect-meta">'+esc(text(c.capability_title,tr('Capability not disclosed by an official web post','官方网页公告未披露该能力')))+'</div><div class="inspect-truth"><span class="truth official">'+esc(tr('Official 36(b) congressional notification','36(b) 国会通知官方记录'))+'</span><span class="truth derived">'+esc(tr('Display only','仅展示'))+'</span></div><div class="inspect-actions"><button class="tool-btn" type="button" data-fms-evidence>'+esc(tr('View source chain','查看来源链'))+'</button><button class="tool-btn" type="button" data-fms-copy>'+esc(tr('Copy link','复制链接'))+'</button></div></div>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Stage','阶段'))+'</div><div class="budget-boundary"><strong>'+esc(tr('Notified to Congress — not a signed sale','已通知国会 — 尚非已签署军售'))+'</strong><span>'+esc(tr('Later stage not observed','未观察到后续阶段'))+'</span></div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Amount','金额'))+'</div><div class="budget-amounts">'+'<div class="budget-amount primary"><span>'+esc(tr('Estimated notification value','通知估算金额'))+'</span><b>'+esc(money(c.estimated_notification_value))+'</b><small>'+esc(tr('Proposed-sale estimate — not an award, backlog, or revenue','拟议军售估算 — 并非合同授予、订单积压或收入'))+'</small></div>'+'</div>'+(c.source_caveat?'<p class="budget-null">'+esc(text(c.source_caveat))+'</p>':'')+'</section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Clocks','时间线'))+'</div><div class="budget-coverage">'+'<div class="budget-rail muted"><span>'+esc(tr('Official notification date','官方通知日期'))+'</span><b>'+esc(notif.value?date(notif.value):tr('Official notification date unavailable','官方通知日期暂无'))+'</b></div>'+'<div class="budget-rail muted"><span>'+esc(tr('Official web publication date','官方网页发布日期'))+'</span><b>'+esc(date(pub.value))+'</b></div>'+'<div class="budget-rail muted"><span>'+esc(tr('First observed','首次获知'))+'</span><b>'+esc(date((clocks||{}).first_observed_at))+'</b></div>'+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Linkage','关联'))+'</div><div class="budget-bridges">'+(contractors.length?contractors.map(contractorRow).join(''):(c.contractor_note?'<p class="budget-null">'+esc(text(c.contractor_note))+'</p>':''))+'<article class="budget-bridge"><span class="truth observed">'+esc(tr('Program link not reviewed','项目关联未审核'))+'</span></article>'+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Advancement','推进'))+'</div><div class="budget-boundary"><span>'+esc(tr('Requires official evidence of an offered, accepted, or implemented LOA','须有官方证据证明 LOA 已提出、接受或实施'))+'</span></div></section>'+
        (cov.web_presence===false?'<section class="inspect-section"><div class="inspect-label">'+esc(tr('Coverage note','覆盖说明'))+'</div><div class="budget-null"><span>'+esc(tr('Recovered from the Federal Register official record — no agency web post exists for this case.','该案例来自联邦公报官方记录 — 该机构未发布对应网页公告。'))+'</span><br><span>'+esc(text((env.coverage||{}).history_disclosure))+'</span></div></section>':'')+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Evidence & limits','证据与限制'))+'</div><div class="limit-copy">'+esc(tr('Display-only context. It cannot rank a case, size a position, gate a trade, or add a candidate.','仅作展示情境。不得为案例排序、调整仓位、设闸或添加候选。'))+'</div></section>';
      var evidence=host.querySelector('[data-fms-evidence]');if(evidence)evidence.addEventListener('click',function(){if(typeof api.openEvidenceDrawer==='function')api.openEvidenceDrawer({title:tr('FMS source chain','FMS 来源链'),html:evidenceHtml(c),focus:evidence})});
      var copy=host.querySelector('[data-fms-copy]');if(copy)copy.addEventListener('click',function(){if(typeof api.copyLink==='function')api.copyLink(copy)});
      if(typeof api.setMobile==='function')api.setMobile(text(c.customer_country),text(c.transmittal_number,'—'));
    }
    return{load:load,refresh:function(){if(!listing||loadState!=='ok')return[];var rows=rowsFrom(listing);if(typeof api.onRows==='function')api.onRows(rows,{status:'ok',content_id:contentId,total:rows.length});return rows},render:render,invalidate:function(){},state:function(){return loadState}};
  };

})(window);
