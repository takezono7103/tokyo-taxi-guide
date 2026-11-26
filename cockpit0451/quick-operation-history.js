(() => {
  'use strict';
  const key='taxi_quick_action_audit_v0419';
  const buttons={free:'start',ride:'call',return:'break',rest:'rest'};
  let previousRaw, cached=[];
  function read() {
    const raw=localStorage.getItem(key);
    if(raw===previousRaw)return cached;
    const values=JSON.parse(raw||'[]');
    if(!Array.isArray(values))throw Error('営業クイックの操作履歴を読めません。');
    cached=values.flatMap(row=>{
      const mode=buttons[row?.button];
      if(!mode||row.ok!==true||row.mode!==mode)return [];
      const at=row.modeAt||Date.parse(row.at);
      return Number.isFinite(at)?[{mode,at,source:'quick-audit'}]:[];
    }).sort((a,b)=>a.at-b.at);
    previousRaw=raw;
    return cached;
  }
  function count(states) {
    return states.filter(state=>state.source!=='start-snapshot'&&Object.values(buttons).includes(state.mode)).length;
  }
  window.taxiQuickOperationHistory={key,read,count};
})();
