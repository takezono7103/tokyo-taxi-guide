(function(){
  const SERVERS = ["https://overpass.kumi.systems/api/interpreter","https://overpass-api.de/api/interpreter","https://overpass.nchc.org.tw/api/interpreter"];
  let serverIndex=0,lastRequest=0,busy=false;
  async function getRoadData(lat,lon){
    if(busy||Date.now()-lastRequest<60000)return;
    busy=true;lastRequest=Date.now();
    const query=`[out:json][timeout:20];(way(around:700,${lat},${lon})[highway][name];node(around:700,${lat},${lon})[name][highway=traffic_signals];node(around:700,${lat},${lon})[name][junction];node(around:700,${lat},${lon})[name][highway=mini_roundabout];);out geom;`;
    try{
      let data=null;
      for(let i=0;i<SERVERS.length;i++){
        const url=SERVERS[(serverIndex+i)%SERVERS.length];
        try{
          const r=await fetch(url,{method:"POST",body:"data="+encodeURIComponent(query),headers:{"Content-Type":"application/x-www-form-urlencoded"}});
          if(!r.ok)throw Error("HTTP "+r.status);
          data=await r.json();serverIndex=(serverIndex+i)%SERVERS.length;break;
        }catch(e){console.warn("Overpass failed",e)}
      }
      if(!data)throw Error("道路情報を取得できません");
      window.taxiRoadData=data.elements;
      console.log("道路データ取得",data.elements.length);
    }catch(e){console.warn(e)}finally{busy=false}
  }
  window.taxiGetRoadData=getRoadData;
})();
