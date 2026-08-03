(function(global){
  'use strict';

  /*
   * The award and subaward rails intentionally have separate immutable
   * generations: grd1-* describes primes/actions and grsd1-* describes
   * receipt-bound subaward observations. Never compare them to each other.
   */
  global.createGovernmentRevenueDossier=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,factCell=api.factCell,hostFor=api.host,getSelected=api.selected;
    var epoch=0,session=null,searchTimer=null;
    var SUBAWARD_PAGE_SIZE=25;

    function field(x,keys){x=obj(x)?x:{};for(var i=0;i<keys.length;i++)if(x[keys[i]]!=null&&x[keys[i]]!=='')return x[keys[i]];return null}
    function fetchPage(route,rail){
      var prefix=rail==='subaward'?'grsd1-':rail==='idv'?'griv1-':'grd1-';
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      return global.fetch('/api/government-revenue/'+route,{credentials:'same-origin',headers:{Accept:'application/json'}}).then(function(r){if(!r.ok)throw new Error('http_'+r.status);return r.json()}).then(function(x){
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

  global.createGovernmentRevenueBudget=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,hostFor=api.host;
    var contentId=null,detailEpoch=0,detailCache={},loadState='loading',listing=null;

    function validAuthority(value){return obj(value)&&value.tier==='display'&&value.context_only===true&&value.can_rank===false&&value.can_size===false&&value.can_gate===false&&value.can_originate_signal===false&&value.can_add_candidates===false&&value.can_escalate===false}
    function fetchBudget(route){
      if(typeof global.fetch!=='function')return Promise.reject(new Error('unavailable'));
      return global.fetch('/api/government-revenue/'+route,{credentials:'same-origin',headers:{Accept:'application/json'}}).then(function(response){if(!response.ok)throw new Error('http_'+response.status);return response.json()}).then(function(value){
        if(!obj(value)||value.contract!=='government_budget_program_graph.v1'||value.schema_version!=='1.0.0'||!/^grbg1-[a-f0-9]{24}$/.test(text(value.content_id,''))||!validAuthority(value.authority))throw new Error('contract');
        return value;
      });
    }
    function programKind(value){return value==='procurement_line_item'?tr('P-1 procurement line','P-1 采购项目行'):tr('R-1 RDT&E program element','R-1 研发试验项目要素')}
    function rowsFrom(value){return arr(value.programs).filter(obj).map(function(program){return{id:'budget:'+text(program.program_key),kind:'budget_program',truth:'official',truthCopy:tr("Official President's Budget request","总统预算请求官方记录"),linked:false,defense:true,tickers:[],agency:'Department of Defense',date:value.known_at,title:text(program.name,tr('Unnamed DoD program','未命名国防部项目')),subtitle:programKind(program.kind)+' · '+text(program.native_identifier),program:program,budgetEnvelope:{content_id:value.content_id,known_at:value.known_at,as_of:value.as_of,source_coverage:value.source_coverage,documents:value.documents,limitations:value.limitations}}})}
    function load(){
      loadState='loading';
      return fetchBudget('budget-programs').then(function(value){listing=value;contentId=value.content_id;loadState='ok';var rows=rowsFrom(value);if(typeof api.onRows==='function')api.onRows(rows,{status:'ok',content_id:contentId,total:rows.length});return rows}).catch(function(){listing=null;contentId=null;detailCache={};loadState='unavailable';if(typeof api.onRows==='function')api.onRows([],{status:'unavailable',content_id:null,total:0});return[]});
    }
    function semanticValue(line,semantic){var cell=arr((line||{}).amounts).find(function(item){return obj(item)&&item.semantic===semantic});return cell?n(cell.amount_usd):null}
    function latestLine(lines){return arr(lines).filter(obj).slice().sort(function(a,b){return(n(b.fiscal_year)||0)-(n(a.fiscal_year)||0)||String(b.known_at||'').localeCompare(String(a.known_at||''))})[0]||null}
    function statusClass(status){return status==='ok'?'ok':status==='partial'?'warn':'muted'}
    function coverageCard(label,rail){rail=obj(rail)?rail:{};var status=text(rail.status,'uncollected');return'<div class="budget-rail '+esc(statusClass(status))+'"><span>'+esc(label)+'</span><b>'+esc(status.replace(/_/g,' '))+'</b><small>'+esc(text(rail.reason,tr('No source rail is active.','来源链路尚未启用。')))+'</small></div>'}
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
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Latest request frame','最新请求框架'))+'</div><div class="budget-amounts">'+amountCard(tr('FY '+text(latest&&latest.fiscal_year)+' total request','FY '+text(latest&&latest.fiscal_year)+' 请求总额'),request,tr('President’s Budget total','总统预算请求总额'),true)+amountCard(tr('Discretionary request','可自由支配请求'),disc,tr('Source-native column','来源原生列'),false)+amountCard(tr('Reconciliation request','调节请求'),recon,tr('Source-native column','来源原生列'),false)+amountCard(tr('Prior enacted reference','上年已颁参考'),enacted,tr('Historical reference only','仅历史参考'),false)+'</div></section>'+
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
})(window);
