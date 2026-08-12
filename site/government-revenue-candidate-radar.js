(function(global){
  'use strict';

  /*
   * The Candidate Radar only accepts the bounded, receipt-verified candidate
   * queue.  Discovery-company coverage intentionally lives in a separate
   * mode and is never used as a fallback here.
   */
  global.createGovernmentRevenueCandidateRadar=function(api){
    var obj=api.obj,arr=api.arr,esc=api.esc,text=api.text,n=api.n,money=api.money,date=api.date,tr=api.tr,safeUrl=api.safeUrl,hostFor=api.host;
    var epoch=0,listing=null,loadState='loading',MAX_PAGES=4;

    function requiredText(value){return typeof value==='string'&&value.trim()?value.trim():''}
    function validAuthority(value){return obj(value)&&value.tier==='display'&&value.context_only===true&&value.can_rank===false&&value.can_size===false&&value.can_gate===false&&value.can_originate_signal===false&&value.can_add_candidates===false&&value.can_escalate===false}
    function scalar(value,fallback){
      if(typeof value==='string'||typeof value==='number')return String(value);
      if(obj(value)){
        var keys=['display','summary','detail','text','label','name','title','value','ref_id','record_id','graph_id','edge_id','candidate_id','event_id'];
        for(var i=0;i<keys.length;i++)if(typeof value[keys[i]]==='string'&&value[keys[i]].trim())return value[keys[i]].trim();
      }
      return fallback||'';
    }
    function refText(value){
      if(typeof value==='string')return value;
      if(obj(value))return scalar(value,'');
      return '';
    }
    function refUrl(value){
      if(typeof value==='string')return safeUrl(value);
      if(obj(value))return safeUrl(value.url||value.source_url||value.href);
      return '';
    }
    function validRefs(value){return Array.isArray(value)&&value.length>0&&value.every(function(ref){return !!refText(ref)})}
    function candidateCompany(value,ticker){return requiredText(value.company_name)||requiredText(value.issuer_company_name)||requiredText((value.issuer||{}).company_name)||ticker}
    function candidateAgency(value){var agency=obj(value.agency)?value.agency:{};return requiredText(value.agency_name)||requiredText(agency.department_name)||requiredText(agency.name)||''}
    function eventCopy(value){var mechanism=obj(value.mechanism)?value.mechanism:{};return scalar(value.observed_change,scalar(value.event_summary,scalar(mechanism.observed_change,tr('Receipt-bound procurement change','与凭证绑定的采购变化'))))}
    function earningsCopy(value){var transmission=obj(value.earnings_transmission)?value.earnings_transmission:{},channels=arr(transmission.possible_earnings_channels).filter(function(channel){return typeof channel==='string'&&channel});if(channels.length)return tr('Possible channels: ','可能传导渠道：')+channels.join(', ')+'.';return scalar(value.earnings_transmission,tr('Possible statement channel is still being documented.','潜在财报传导路径仍在整理。'))}
    function materialityCopy(value){var materiality=obj(value.materiality)?value.materiality:{},amount=n(materiality.observed_event_amount),attributable=n(materiality.attributable_amount);if(amount!=null)return tr('Observed event amount: ','观测事件金额：')+(typeof money==='function'?money(amount):String(amount))+(attributable!=null?tr(' · attributable amount: ',' · 可归属金额：')+(typeof money==='function'?money(attributable):String(attributable)):'')+'. '+tr('No issuer-attributed denominator is available, so no materiality ratio is shown.','暂无发行人归属分母，因此不显示重要性比例。');return tr('A transparent comparison is not available yet.','尚无可展示的透明比较。')}
    function candidateState(value){var state=requiredText(value.candidate_state);return{detected:tr('Research now','立即研究'),awaiting_crosscheck:tr('Checking other evidence','核对其他证据'),active:tr('Research now','立即研究'),matured:tr('Review outcome','复核结果'),superseded:tr('Newer evidence available','已有更新证据'),withdrawn:tr('Record withdrawn','记录已撤回'),blocked:tr('Research paused','研究暂停')}[state]||tr('Research queue','研究队列')}
    function directionCopy(value){return{possible_positive:tr('Possible upside channel','可能的上行通道'),possible_negative:tr('Possible downside channel','可能的下行通道'),mixed:tr('Mixed statement channel','混合财报通道'),unknown:tr('Channel still open','传导路径仍待明确')}[requiredText(value.transmission_direction)]||tr('Channel still open','传导路径仍待明确')}
    function normalize(value){
      if(!obj(value))throw new Error('candidate_row');
      var candidateId=requiredText(value.candidate_id),ticker=requiredText(value.ticker),issuer=requiredText(value.issuer_company_id),resolution=obj(value.issuer_resolution_ref)?value.issuer_resolution_ref:{},knownAt=requiredText(value.known_at),effectiveAt=requiredText(value.effective_at);
      if(value.contract!=='government_revenue_candidate.v1'||value.schema_version!=='1.0.0'||!/^grc1-[a-f0-9]{24}$/.test(candidateId)||!issuer||resolution.contract!=='government_recipient_resolution.v1'||!requiredText(resolution.graph_id)||!validRefs(resolution.evidence_refs)||!knownAt||!effectiveAt||!new RegExp('^[A-Z][A-Z0-9.-]{0,9}$').test(ticker))throw new Error('candidate_identity');
      if(value.candidate_scope!=='government_revenue_research'||value.is_neuralweb_trade_candidate!==false||!requiredText(value.candidate_family)||!requiredText(value.candidate_state)||!requiredText(value.transmission_direction))throw new Error('candidate_scope');
      if(!validRefs(value.event_refs)||!validRefs(value.source_receipt_refs)||!validRefs(value.ownership_path_refs)||!validAuthority(value.authority))throw new Error('candidate_proof');
      return{id:'candidate:'+candidateId,kind:'candidate',truth:'official',truthCopy:tr('Receipt-bound event','与凭证绑定的事件'),linked:true,exactIssuer:true,defense:value.defense_relevant!==false,tickers:[ticker],agency:candidateAgency(value),date:knownAt,title:ticker+' · '+candidateCompany(value,ticker),subtitle:eventCopy(value),candidate:value};
    }
    function queueRows(value){
      if(!obj(value)||value.contract!=='government_revenue_candidate_queue.v1'||value.schema_version!=='1.0.0'||!/^grcq1-[a-f0-9]{24}$/.test(requiredText(value.content_id))||!validAuthority(value.authority))throw new Error('candidate_queue_contract');
      var items=Array.isArray(value.candidates)?value.candidates:(Array.isArray(value.items)?value.items:null),counts=obj(value.counts)?value.counts:{},total=n(value.total);if(total==null)total=n(counts.total);
      if(!items||total==null||total<0||Math.floor(total)!==total||items.length>total)throw new Error('candidate_queue_shape');
      var mappingStates=obj(value.mapping_backlog_states)?value.mapping_backlog_states:{};
      Object.keys(mappingStates).forEach(function(ticker){if(!/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker)||['mapping_needed','partial_identifier_coverage'].indexOf(mappingStates[ticker])<0)throw new Error('mapping_state_map')});
      return{rows:items.map(normalize),total:total,mappingBacklog:n(value.mapping_backlog_total)||(Array.isArray(value.mapping_backlog)?value.mapping_backlog.length:0),mappingBacklogTickers:arr(value.mapping_backlog_tickers).filter(function(ticker){return /^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker)}),mappingBacklogStates:mappingStates,contentId:value.content_id,knownAt:value.known_at||null,asOf:value.as_of||null,freshness:obj(value.freshness)?value.freshness:{},limitations:arr(value.limitations)};
    }
    function publish(value){
      listing=value;loadState=value.total?'ok':'empty';
      if(typeof api.onRows==='function')api.onRows(value.rows,{status:loadState,total:value.total,mapping_backlog_total:value.mappingBacklog,mapping_backlog_tickers:value.mappingBacklogTickers,mapping_backlog_states:value.mappingBacklogStates,content_id:value.contentId,known_at:value.knownAt,as_of:value.asOf,freshness:value.freshness,limitations:value.limitations});
      return value.rows;
    }
    function unavailable(reason){listing=null;loadState=reason==='locked'?'locked':'unavailable';if(typeof api.onRows==='function')api.onRows([],{status:loadState,total:0,mapping_backlog_total:0,mapping_backlog_tickers:null,mapping_backlog_states:null,content_id:null,freshness:{exact_candidate_availability:'unavailable'}});return[]}
    function lockedFailure(error){var message=error&&error.message||'';return message==='http_401'||message==='http_403'}
    function pageEnvelope(value,kind){
      if(!obj(value)||value.contract!=='government_revenue_candidate_queue.v1'||value.schema_version!=='1.0.0'||!/^grcq1-[a-f0-9]{24}$/.test(requiredText(value.content_id))||!validAuthority(value.authority))throw new Error(kind+'_contract');
      var items=Array.isArray(value.items)?value.items:null,total=n(value.total),cursor=value.next_cursor;
      if(!items||total==null||total<0||Math.floor(total)!==total||items.length>total||!(cursor==null||typeof cursor==='string'&&cursor))throw new Error(kind+'_shape');
      if(kind==='mapping')items.forEach(function(row){if(!obj(row)||!/^grmb1-[a-f0-9]{24}$/.test(requiredText(row.backlog_id))||['mapping_needed','partial_identifier_coverage'].indexOf(row.mapping_state)<0||row.issuer_attribution!=='not_asserted'||!/^[A-Z][A-Z0-9.-]{0,9}$/.test(requiredText(row.ticker)))throw new Error('mapping_row')});
      return{value:value,items:items,total:total,next:cursor||null,contentId:value.content_id};
    }
    function fetchPages(path,kind){
      var pages=0,seen={},all=[],first=null;
      function next(cursor){
        if(pages>=MAX_PAGES)throw new Error(kind+'_page_cap');
        pages++;
        var url=path+(cursor?'&cursor='+encodeURIComponent(cursor):'');
        return global.fetch(url,{credentials:'same-origin',headers:{Accept:'application/json'}}).then(function(response){if(!response.ok)throw new Error('http_'+response.status);return response.json()}).then(function(value){
          var page=pageEnvelope(value,kind);
          if(!first)first=page;else if(page.contentId!==first.contentId||page.total!==first.total)throw new Error(kind+'_generation_drift');
          all=all.concat(page.items);
          if(all.length>page.total)throw new Error(kind+'_overflow');
          if(page.next){if(seen[page.next])throw new Error(kind+'_cursor_loop');seen[page.next]=true;return next(page.next)}
          if(all.length!==page.total)throw new Error(kind+'_truncated');
          return{envelope:first.value,items:all,total:page.total,contentId:page.contentId};
        });
      }
      return next(null);
    }
    function load(){
      var ticket=++epoch;loadState='loading';
      if(typeof global.fetch!=='function')return Promise.resolve(unavailable());
      return Promise.all([
        fetchPages('/api/government-revenue/candidates?limit=100','candidate'),
        fetchPages('/api/government-revenue/mapping-backlog?limit=100','mapping')
      ]).then(function(result){
        if(ticket!==epoch)return[];
        var candidatePages=result[0],mappingPages=result[1],value=Object.assign({},candidatePages.envelope),expectedBacklog=n(value.mapping_backlog_total);
        if(candidatePages.contentId!==mappingPages.contentId||expectedBacklog==null||expectedBacklog!==mappingPages.total)throw new Error('candidate_mapping_generation_drift');
        value.items=candidatePages.items;value.total=candidatePages.total;value.next_cursor=null;value.mapping_backlog_total=mappingPages.total;value.mapping_backlog_tickers=Array.from(new Set(mappingPages.items.map(function(row){return row.ticker}))).sort();value.mapping_backlog_states=mappingPages.items.reduce(function(states,row){states[row.ticker]=row.mapping_state;return states},{});
        return publish(queueRows(value));
      }).catch(function(error){if(ticket!==epoch)return[];return unavailable(lockedFailure(error)?'locked':'')});
    }
    function crosscheckEntry(value){
      var state=typeof value==='string'?value:obj(value)?scalar(value.state||value.status||value.label,''):'';
      var normalized=String(state||'').toLowerCase();
      if(/match|agree|confirm|available|ready/.test(normalized))return{copy:tr('Match found','发现匹配'),className:'ok'};
      if(/conflict|mixed|disagree|warn/.test(normalized))return{copy:tr('Mixed evidence','证据不一致'),className:'mixed'};
      return{copy:tr('Not attached','尚未关联'),className:'pending'};
    }
    function crosschecks(value,compact){
      var source=obj(value.crosscheck_state)?value.crosscheck_state:{},legs=obj(source.legs)?source.legs:source,names=[['technical',tr('Technical','技术面')],['earnings',tr('Earnings','业绩')],['valuation',tr('Valuation','估值')],['alternative_data',tr('Alternative data','另类数据')],['regime',tr('Regime','市场环境')],['geopolitics',tr('Geopolitics','地缘政治')]];
      return names.map(function(pair){var entry=crosscheckEntry(legs[pair[0]]);return compact?'<span class="candidate-crosscheck '+esc(entry.className)+'">'+esc(pair[1])+': '+esc(entry.copy)+'</span>':'<div class="'+esc(entry.className)+'"><b>'+esc(pair[1])+'</b><span>'+esc(entry.copy)+'</span></div>'}).join('');
    }
    function sourceRows(value){return arr(value.source_receipt_refs).concat(arr(value.event_refs)).map(function(ref){var title=refText(ref),url=refUrl(ref);return'<article class="receipt"><div class="receipt-kind">'+esc(tr('Retained reference','保留引用'))+'</div><p>'+esc(title)+'</p>'+(url?'<a class="source-link" href="'+esc(url)+'" target="_blank" rel="noopener"><b>'+esc(tr('Open source','打开来源'))+'</b><span>↗</span></a>':'')+'</article>'}).join('')}
    function proofCopy(value){var resolution=obj(value.issuer_resolution_ref)?value.issuer_resolution_ref:{};return tr('Exact issuer path retained in graph ','精确发行人路径已保留于图谱 ')+requiredText(resolution.graph_id)+'. '+tr('The linked legal entity and ownership path are available in the evidence record.','关联法人及所有权路径可在证据记录中查看。')}
    function render(row){
      var host=hostFor(),value=row&&row.candidate;if(!host||!obj(value))return;
      var ticker=requiredText(value.ticker),source=arr(value.source_receipt_refs).map(refUrl).find(Boolean)||'',limits=arr(value.limitations).map(refText).filter(Boolean),resolution=obj(value.issuer_resolution_ref)?value.issuer_resolution_ref:{},evidenceHtml=sourceRows(value)+
        '<article class="receipt"><div class="receipt-kind">'+esc(tr('Issuer path','发行人路径'))+'</div><p>'+esc(proofCopy(value))+'</p><div class="receipt-code">'+esc('candidate_id: '+requiredText(value.candidate_id)+'\nissuer_company_id: '+requiredText(value.issuer_company_id)+'\nissuer_resolution_ref: '+requiredText(resolution.graph_id)+'\ngraph_evidence_refs: '+arr(resolution.evidence_refs).map(refText).join(', ')+'\nownership_path_refs: '+arr(value.ownership_path_refs).map(refText).join(', ')+'\nartifact_content_ids: '+arr(value.artifact_content_ids).map(refText).join(', ')+'\neffective_at: '+requiredText(value.effective_at)+'\nknown_at: '+requiredText(value.known_at))+'</div></article>'+
        '<article class="receipt"><div class="receipt-kind">'+esc(tr('Research boundary','研究边界'))+'</div><p>'+esc(limits.concat([tr('This is a research candidate, not a buy signal or trade instruction.','这是研究候选，并非买入信号或交易指令。')]).join(' · '))+'</p></article>';
      host.className='inspector candidate-inspector';
      host.innerHTML='<div class="inspect-hero"><div class="inspect-kicker"><span class="inspect-type">'+esc(tr('Research candidate','研究候选'))+'</span><span class="inspect-id">'+esc(ticker)+'</span></div><h2>'+esc(ticker+' · '+candidateCompany(value,ticker))+'</h2><div class="inspect-meta">'+esc(candidateState(value)+' · '+date(value.known_at))+'</div><div class="inspect-truth"><span class="truth official">'+esc(tr('Receipt-bound event','与凭证绑定的事件'))+'</span><span class="truth reviewed">'+esc(tr('Exact issuer path','精确发行人路径'))+'</span></div><div class="inspect-actions"><button class="tool-btn" type="button" data-candidate-evidence>'+esc(tr('View evidence','查看证据'))+'</button><button class="tool-btn" type="button" data-candidate-copy>'+esc(tr('Copy link','复制链接'))+'</button>'+(source?'<a class="tool-btn" href="'+esc(source)+'" target="_blank" rel="noopener">'+esc(tr('Open source ↗','打开来源 ↗'))+'</a>':'')+'</div></div>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('What changed','发生了什么变化'))+'</div><div class="inspect-value"><strong>'+esc(eventCopy(value))+'</strong></div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Why this ticker is linked','为何关联此代码'))+'</div><div class="candidate-proof"><strong>'+esc(tr('Exact issuer path','精确发行人路径'))+'</strong><span>'+esc(proofCopy(value))+'</span></div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('How it could reach earnings','可能如何传导至业绩'))+'</div><div class="inspect-value">'+esc(earningsCopy(value))+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Materiality context','重要性情境'))+'</div><div class="inspect-value">'+esc(materialityCopy(value))+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Other Mastermind evidence','其他 Mastermind 证据'))+'</div><div class="candidate-crosscheck-grid">'+crosschecks(value,false)+'</div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Research stance','研究动作'))+'</div><div class="stance"><b>'+esc(candidateState(value))+'</b><span>'+esc(tr('Use this as a research lead, then weigh each independent evidence leg separately.','将其作为研究线索，再分别权衡每个独立证据层。'))+'</span></div></section>'+
        '<section class="inspect-section"><div class="inspect-label">'+esc(tr('Evidence & limits','证据与限制'))+'</div><div class="limit-copy">'+esc(tr('Research context only. It cannot rank a company, change conviction, size a position or trigger a trade.','仅作研究情境。不得为公司排序、改变信心、调整仓位或触发交易。'))+'</div></section>';
      var evidence=host.querySelector('[data-candidate-evidence]');if(evidence)evidence.addEventListener('click',function(){if(typeof api.openEvidenceDrawer==='function')api.openEvidenceDrawer({title:tr('Candidate evidence','候选证据'),html:evidenceHtml,focus:evidence})});
      var copy=host.querySelector('[data-candidate-copy]');if(copy)copy.addEventListener('click',function(){if(typeof api.copyLink==='function')api.copyLink(copy)});
      if(typeof api.setMobile==='function')api.setMobile(ticker+' · '+candidateCompany(value,ticker),candidateState(value));
    }
    return{load:load,refresh:load,render:render,invalidate:function(){epoch++},state:function(){return loadState},crosschecks:crosschecks};
  };
})(window);
