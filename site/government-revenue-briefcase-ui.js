/* Device-local Government Revenue briefcase controls.
 *
 * The state/alert/export contract lives in government-revenue-briefcase.js.
 * This file only mounts that contract onto the page and never performs remote
 * delivery, polling, or account synchronization.
 */
(function(root){
  'use strict';

  root.mountGovernmentRevenueBriefcaseUI=function(api){
    var briefcase=null,selectedView='',bound=false;
    var get=api.get,tr=api.tr,esc=api.esc,text=api.text;
    try{briefcase=root.createGovernmentRevenueBriefcase({storage:root.localStorage})}catch(error){briefcase=null}

    function status(copy,warn){var el=get('briefcaseStatus');if(!el)return;el.className='briefcase-status'+(warn?' warn':'');el.textContent=copy}
    function typeLabel(type){return{opportunity:tr('Opportunity change','机会变化'),award_change:tr('Award / action change','授标 / 行动变化'),recompete:tr('Derived expiry watch','推导到期观察')}[type]||type}
    function selectedAlert(){if(!briefcase||!selectedView)return null;var type=get('alertType').value;return briefcase.listAlerts().find(function(row){return row.view_id===selectedView&&row.type===type})||null}

    function render(message,warn){
      var select=get('savedViewSelect'),toggle=get('toggleLocalAlert'),remove=get('deleteView');
      if(!select||!toggle||!remove)return;
      if(!briefcase){
        select.disabled=true;toggle.disabled=true;remove.disabled=true;get('exportViewJson').disabled=true;get('exportViewCsv').disabled=true;
        status(tr('Local research storage is unavailable in this browser.','此浏览器无法使用本地研究存储。'),true);return;
      }
      var views=briefcase.listViews();
      if(selectedView&&!views.some(function(view){return view.id===selectedView}))selectedView='';
      select.innerHTML='<option value="">'+esc(tr('Current unsaved view','当前未保存视图'))+'</option>'+views.map(function(view){return'<option value="'+esc(view.id)+'">'+esc(view.name)+'</option>'}).join('');
      select.value=selectedView;
      var view=selectedView?briefcase.getView(selectedView):null;
      get('savedViewName').value=view?view.name:'';remove.disabled=!view;toggle.disabled=!view;
      var alert=selectedAlert();
      toggle.textContent=alert&&alert.enabled?tr('Disable local alert','停用本地提醒'):tr('Enable local alert','启用本地提醒');
      get('localInboxCount').textContent=briefcase.listInbox().length;
      status(message!=null?message:tr('Saved views and alerts stay in this browser. Alerts are checked only when you open or refresh this page.','保存的视图和提醒仅保留在此浏览器中。提醒仅在打开或刷新此页面时检查。'),warn===true);
    }

    function applySaved(){
      if(!briefcase)return;
      var view=briefcase.getView(get('savedViewSelect').value);selectedView=view?view.id:'';
      if(!view){render();return}
      api.applyFilters(view.filters||{});
      render(tr('Saved view applied · ','已应用保存视图 · ')+view.name,false);
    }

    function save(){
      if(!briefcase)return;
      var name=get('savedViewName').value.trim();
      if(!name){status(tr('Name the current view before saving it.','请先为当前视图命名。'),true);get('savedViewName').focus();return}
      try{
        var result=selectedView?briefcase.updateView(selectedView,{name:name,filters:api.getFilters()}):briefcase.createView({name:name,filters:api.getFilters()});
        selectedView=result.view.id;
        render(result.persisted?tr('View saved on this device.','视图已保存在此设备。'):tr('View is available for this tab, but browser storage is unavailable.','视图可在此标签页使用，但浏览器存储不可用。'),!result.persisted);
      }catch(error){status(tr('This view could not be saved.','无法保存此视图。'),true)}
    }

    function remove(){
      if(!briefcase||!selectedView)return;
      var result=briefcase.deleteView(selectedView);selectedView='';
      render(result.deleted?tr('Saved view and its local alerts were deleted.','已删除保存视图及其本地提醒。'):tr('Saved view was not found.','未找到保存视图。'),!result.deleted);
    }

    function reconcile(announce){
      if(!briefcase||!api.isWorkspaceReady())return null;
      var result=briefcase.reconcile(api.getWorkspace(),{complete:true,bundle_matched:true});
      if(!result.reconciled)return result;
      var copy=result.alerts.length?result.alerts.length+tr(' new local alert receipts.',' 条新的本地提醒凭证。'):result.withheld_alert_ids.length?tr('Award-change alert baseline withheld: the official award rail is unavailable.','授标变化提醒基线已暂停：官方授标链路不可用。'):announce?tr('Local alert baseline checked against the complete governed workspace.','已根据完整受治理工作区检查本地提醒基线。'):null;
      render(copy,!!result.withheld_alert_ids.length);return result;
    }

    function toggleAlert(){
      if(!briefcase||!selectedView)return;
      var alert=selectedAlert();
      try{
        if(alert)briefcase.updateAlert(alert.id,{enabled:!alert.enabled});
        else briefcase.createAlert({view_id:selectedView,type:get('alertType').value});
        var result=reconcile(true);
        if(!result)render(tr('Local alert saved. Its first baseline will be established after the complete workspace loads.','本地提醒已保存。完整工作区加载后将建立首次基线。'),false);
      }catch(error){status(tr('This local alert could not be changed.','无法更改此本地提醒。'),true)}
    }

    function openInbox(){
      if(!briefcase)return;
      var rows=briefcase.listInbox(),html=rows.map(function(item){return'<article class="receipt"><div class="receipt-kind">'+esc(typeLabel(item.type))+'</div><h3>'+esc(item.title||item.event_id)+'</h3><p>'+esc(item.message)+(item.warning?'<br><strong>'+esc(item.warning)+'</strong>':'')+'</p><div class="receipt-code">'+esc('event_id: '+text(item.event_id)+'\nobserved_at: '+text(item.observed_at)+'\nworkspace: '+text(item.workspace_bundle_id))+'</div></article>'}).join('')||'<div class="empty-state"><div><span class="empty-mark" aria-hidden="true">○</span><strong>'+esc(tr('No local alert receipts','暂无本地提醒凭证'))+'</strong><p>'+esc(tr('The first complete-workspace check establishes a baseline and never backfills historical alerts.','首次完整工作区检查仅建立基线，绝不回填历史提醒。'))+'</p></div></div>';
      api.openDrawer({title:tr('Local research inbox','本地研究收件箱'),html:html,focus:root.document.activeElement});
    }

    function download(filename,content,mediaType){
      try{var blob=new Blob([content],{type:mediaType}),href=URL.createObjectURL(blob),link=root.document.createElement('a');link.href=href;link.download=filename;root.document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(href);return true}catch(error){return false}
    }

    function exportView(kind){
      if(!briefcase)return;
      try{
        if(kind==='csv'){
          var csv=briefcase.buildCsvExport(api.getWorkspace(),api.getFilters()),csvOk=download(csv.filename,csv.content,csv.media_type);
          status(csvOk?tr('Auditable CSV view exported.','已导出可审计的 CSV 视图。'):tr('CSV export is unavailable in this browser.','此浏览器无法导出 CSV。'),!csvOk);return;
        }
        var payload=briefcase.buildJsonExport(api.getWorkspace(),api.getFilters()),day=text((payload.workspace||{}).as_of,'undated').replace(/[^0-9-]/g,''),bundle=text((payload.workspace||{}).bundle_id,'unversioned').replace(/[^A-Za-z0-9._-]/g,'_'),content=JSON.stringify(payload,null,2)+'\n',jsonOk=download('government-revenue-'+day+'-'+bundle+'-view.json',content,'application/json;charset=utf-8');
        status(jsonOk?tr('Auditable JSON view exported.','已导出可审计的 JSON 视图。'):tr('JSON export is unavailable in this browser.','此浏览器无法导出 JSON。'),!jsonOk);
      }catch(error){status(tr('The governed view could not be exported.','无法导出受治理视图。'),true)}
    }

    function bind(){
      if(bound||!briefcase){render();return}bound=true;
      get('savedViewSelect').addEventListener('change',applySaved);get('saveView').addEventListener('click',save);
      get('savedViewName').addEventListener('keydown',function(event){if(event.key==='Enter'){event.preventDefault();save()}});
      get('deleteView').addEventListener('click',remove);get('alertType').addEventListener('change',function(){render()});
      get('toggleLocalAlert').addEventListener('click',toggleAlert);get('localInbox').addEventListener('click',openInbox);
      get('exportViewJson').addEventListener('click',function(){exportView('json')});get('exportViewCsv').addEventListener('click',function(){exportView('csv')});
    }

    return{bind:bind,render:render,reconcile:reconcile,available:!!briefcase};
  };
})(window);
