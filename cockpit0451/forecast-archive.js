(() => {
  'use strict';
  const key = 'taxi_forecast_archive_v0460';
  const schema = 'tokyo-taxi-forecast-archive-v1';
  const empty = () => ({schema,through:'',source:'',daily:[],routeDays:[],rides:[],transitions:[]});
  let state = empty(), loadError = '', lastRaw;
  const on = (condition, message) => { if (!condition) throw new Error(message); };
  const string = (value, max = 200) => typeof value === 'string' && value.length <= max;
  const date = value => string(value,10) && /^20\d{2}-\d{2}-\d{2}$/.test(value) &&
    Number.isFinite(Date.parse(value)) && new Date(value).toISOString().slice(0,10)===value;
  const stamp = value => string(value,40) && /^20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?\+09:00$/.test(value) && Number.isFinite(Date.parse(value));
  const num = (value, max) => typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= max;
  const nullable = (value, max) => value === null || num(value,max);
  const id = value => string(value,12) && /^\d+$/.test(value) && Number(value)>0;
  function rowKey(row, type) {
    return type === 'rides' || type === 'transitions' ? row.d+'#'+Number(row.n) : row.d;
  }
  function validUnique(rows, type, normalize) {
    on(Array.isArray(rows)&&rows.length<=15000,type+' の形式または件数が不正です');
    const keys=new Set();
    return rows.map(row=>{
      on(row&&typeof row==='object'&&date(row.d),type+' の乗務日が不正です');
      const normalized=normalize(row), k=rowKey(normalized,type);
      on(!keys.has(k),type+' に重複があります');
      keys.add(k);return normalized;
    });
  }
  function validate(input) {
    on(input?.schema===schema&&date(input.through)&&string(input.source), '対応する営業データJSONを選択してください');
    const daily=validUnique(input.daily,'日報集計',r=>{
      on(string(r.kind)&&string(r.group)&&num(r.gross,1e7)&&num(r.net,1e7)&&num(r.rides,1000)&&num(r.rest,2880)&&num(r.minutes,2880)&&nullable(r.rate,100),'日報集計値が不正です');
      return {d:r.d,kind:r.kind,group:r.group,gross:r.gross,net:r.net,rides:r.rides,rest:r.rest,minutes:r.minutes,rate:r.rate};
    });
    const routeDays=validUnique(input.routeDays,'日別GPS',r=>{
      on(num(r.km,5000)&&nullable(r.nightKm,5000)&&string(r.coverage),'日別GPS集計値が不正です');
      return {d:r.d,km:r.km,nightKm:r.nightKm,coverage:r.coverage};
    });
    const rides=validUnique(input.rides,'rides',r=>{
      on(id(r.n)&&stamp(r.at)&&num(r.fare,1e6)&&r.fare>0&&string(r.place)&&r.place.trim()&&['full','night'].includes(r.scope),'通常乗車明細が不正です');
      return {d:r.d,n:String(Number(r.n)),at:r.at,fare:r.fare,place:r.place,scope:r.scope};
    });
    const transitions=validUnique(input.transitions,'transitions',r=>{
      on(id(r.n)&&stamp(r.s)&&stamp(r.e)&&num(r.min,2880)&&r.min>0&&Math.abs((Date.parse(r.e)-Date.parse(r.s))/60000-r.min)<=.2&&
        nullable(r.km,5000)&&nullable(r.obs,2880)&&(r.km===null)===(r.obs===null)&&
        (r.obs===null||r.obs<=r.min+.2)&&string(r.dest)&&r.dest.trim()&&(typeof r.cc==='boolean'||r.cc===null),'乗降間隔・GPS観測値が不正です');
      return {d:r.d,n:String(Number(r.n)),s:r.s,e:r.e,min:r.min,km:r.km,obs:r.obs,dest:r.dest,cc:r.cc};
    });
    for(const r of [...daily,...routeDays,...rides,...transitions])on(r.d<=input.through,'集計対象日が終了日を超えています');
    return {schema,through:input.through,source:input.source,daily,routeDays,rides,transitions};
  }
  function read() {
    try {
      const raw=localStorage.getItem(key);
      state=raw?validate(JSON.parse(raw)):empty();lastRaw=raw;
      loadError='';
    } catch(error) { state=empty();loadError=String(error.message||error); }
  }
  function load(text,options={}) {
    read();
    on(!loadError,'既存データ読込失敗');
    const incoming=validate(JSON.parse(String(text).replace(/^\uFEFF/,'')));
    if(options.appendOnly){const types=['daily','routeDays','rides','transitions'];const dates=new Set(types.flatMap(type=>state[type].map(r=>r.d)));on(!types.some(type=>incoming[type].some(r=>dates.has(r.d))),'登録済み乗務日');}
    const merged={schema,through:[state.through,incoming.through].sort().pop(),source:incoming.source};
    for (const type of ['daily','routeDays','rides','transitions']) {
      const rows=new Map(state[type].map(row=>[rowKey(row,type),row]));
      for (const row of incoming[type]) rows.set(rowKey(row,type),row);
      merged[type]=[...rows.values()];
    }
    const next=validate(merged);
    // Store all four datasets atomically, without touching any existing cockpit data.
    const serialized=JSON.stringify(next);localStorage.setItem(key,serialized);lastRaw=serialized;
    state=next;loadError='';
    document.dispatchEvent(new CustomEvent('taxi:forecast-archive-updated'));
    return {daily:next.daily.length,routeDays:next.routeDays.length,rides:next.rides.length,transitions:next.transitions.length};
  }
  window.addEventListener('storage',event=>{
    if(event.key===key){read();document.dispatchEvent(new CustomEvent('taxi:forecast-archive-updated'));}
  });
  function refresh(){
    try{if(localStorage.getItem(key)===lastRaw&&!loadError)return;}catch(_){}
    read();document.dispatchEvent(new CustomEvent('taxi:forecast-archive-updated'));
  }
  window.addEventListener('focus',refresh);
  window.addEventListener('pageshow',refresh);
  document.addEventListener('visibilitychange',()=>{if(!document.hidden)refresh();});
  read();
  window.taxiForecastArchive=Object.freeze({get:()=>state,load,error:()=>loadError});
})();
