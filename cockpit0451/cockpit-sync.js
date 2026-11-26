(() => {
  'use strict';
  const prefix='taxi_cockpit_peer_v0457_';
  const roles=['main','quick','closing'];
  const signal='taxi:cockpit-peer';
  let channel=null;
  try { channel=new BroadcastChannel('taxi_cockpit_sync_v0457'); } catch (_) {}
  const peers=new Map();
  function receive(role,packet){
    if(!roles.includes(role)||!packet||packet.role!==role||
       !Number.isFinite(packet.at)||packet.at>Date.now()+1000)return;
    const previous=peers.get(role);
    if(previous&&previous.at>packet.at)return;
    peers.set(role,packet);
  }
  function read(role){
    try{receive(role,JSON.parse(localStorage.getItem(prefix+role)||'null'));}catch(_){}
    const value=peers.get(role);
    return value&&Date.now()-value.at<=20000?value:null;
  }
  function emit(role,data){
    const packet={...data,role,at:Date.now()};
    let saved=false;
    try{localStorage.setItem(prefix+role,JSON.stringify(packet));saved=true;}catch(_){}
    receive(role,packet);
    try{channel?.postMessage(packet);}catch(_){}
    return saved;
  }
  function notify(){
    document.dispatchEvent(new CustomEvent(signal));
  }
  window.addEventListener('storage',event=>{
    if(event.key?.startsWith(prefix)){
      try{receive(event.key.slice(prefix.length),JSON.parse(event.newValue||'null'));}catch(_){}
      notify();
    }
  });
  if(channel)channel.onmessage=event=>{
    receive(event.data?.role,event.data);
    notify();
  };
  function attach(role, snapshot, render){
    let lastSaved=true;
    function update(){
      try{render(read,lastSaved);}catch(_){}
    }
    function publish(){
      try{lastSaved=emit(role,snapshot());}catch(_){lastSaved=false;}
      update();
    }
    document.addEventListener(signal,update);
    window.addEventListener('focus',publish);
    window.addEventListener('pageshow',publish);
    document.addEventListener('visibilitychange',()=>{if(!document.hidden)publish();});
    setInterval(publish,4000);
    publish();
    return publish;
  }
  window.taxiCockpitSync={attach,read,signal};
})();
