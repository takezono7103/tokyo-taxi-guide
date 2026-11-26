(() => {
  'use strict';
  const gpsDatabase = 'tokyo_taxi_shift_gps_v0428';
  const activeKey = 'taxi_shift_gps_active_v0428';
  const closeKey = 'taxi_operating_close_v0451';
  const tokyo = time => new Date(time).toLocaleDateString('sv-SE', {timeZone:'Asia/Tokyo'});
  const localClock = new Intl.DateTimeFormat('ja-JP', {
    timeZone:'Asia/Tokyo', hour:'2-digit', minute:'2-digit', hourCycle:'h23'
  });
  function openGps() {
    return new Promise((resolve,reject) => {
      const request = indexedDB.open(gpsDatabase,1);
      request.onupgradeneeded = () => {
        const db=request.result;
        db.createObjectStore('sessions',{keyPath:'id'});
        const points=db.createObjectStore('points',{keyPath:['sid','n']});
        points.createIndex('bySession','sid',{unique:false});
      };
      request.onsuccess=()=>resolve(request.result);
      request.onerror=()=>reject(request.error);
      request.onblocked=()=>reject(new Error('GPSの保存領域を開けません。'));
    });
  }
  async function readGps(store, query) {
    const db=await openGps();
    try {
      return await new Promise((resolve,reject) => {
        const request=query(db.transaction(store,'readonly').objectStore(store));
        request.onsuccess=()=>resolve(request.result);
        request.onerror=()=>reject(request.error);
      });
    } finally {
      db.close();
    }
  }
  const activeId=()=>localStorage.getItem(activeKey);
  async function listFinished() {
    const sessions=await readGps('sessions',store=>store.getAll());
    return sessions.filter(shift=>shift.endAt).sort((a,b)=>b.endAt-a.endAt);
  }
  async function trackFor(shift) {
    if(!shift.endAt||activeId()===shift.id)throw new Error('メインで営業を終了してください。');
    const points=await readGps('points',store=>store.index('bySession').getAll(IDBKeyRange.only(shift.id)));
    points.sort((a,b)=>a.n-b.n);
    const segments=[];
    let previous;
    for (const point of points) {
      if (!Number.isFinite(point.t)||!Number.isFinite(point.lat)||!Number.isFinite(point.lon)) continue;
      if (!previous||previous.seg!==point.seg||previous.t>point.t) segments.push([]);
      segments.at(-1).push({time:point.t,lat:point.lat,lon:point.lon});
      previous=point;
    }
    return segments;
  }
  function readClosings() {
    const value=JSON.parse(localStorage.getItem(closeKey)||'{}');
    if(!value||typeof value!=='object'||Array.isArray(value))throw new Error('保存済みの締め集計を確認できません。');
    return value;
  }
  function saveClosing(report) {
    if(!/^\d{4}-\d{2}-\d{2}$/.test(report.date))throw new Error('日報の乗務日を確認してください。');
    const saved=readClosings();
    saved[report.date]=report;
    localStorage.setItem(closeKey,JSON.stringify(saved));
    return report;
  }
  function latestClosing() {
    const reports=Object.values(readClosings());
    return reports.sort((a,b)=>b.savedAt-a.savedAt)[0]??null;
  }
  function displayShift(shift) {
    return (shift.dutyDate||tokyo(shift.startAt))+' '+localClock.format(shift.startAt)+'〜'+
      localClock.format(shift.endAt)+' ／ '+(shift.pointsCount||0)+'点';
  }
  window.taxiShiftLink={activeId,listFinished,trackFor,saveClosing,readClosings,latestClosing,displayShift,closeKey,tokyo};
})();
