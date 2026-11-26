(() => {
  'use strict';
  const prefix = 'taxi_cockpit_peer_v0458_';
  const scopeKey = 'taxi_cockpit_storage_scope_v0458';
  const probeKey = prefix + 'probe';
  const roles = ['main', 'quick', 'closing'];
  const signal = 'taxi:cockpit-peer';
  const peers = new Map();
  const publishers = new Map();
  let scope = '';
  let channel = null;
  let lastRequestAt = 0;
  try {
    scope = localStorage.getItem(scopeKey) || '';
    if (!scope) {
      scope = typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Date.now() + '-' + Math.random();
      localStorage.setItem(scopeKey, scope);
      scope = localStorage.getItem(scopeKey);
    }
  } catch (_) {}
  try { channel = new BroadcastChannel('taxi_cockpit_sync_v0458'); } catch (_) {}

  function receive(packet) {
    if (!packet || !scope || packet.scope !== scope || !roles.includes(packet.role) ||
        !Number.isFinite(packet.at) || packet.at > Date.now() + 1000) return;
    const previous = peers.get(packet.role);
    if (!previous || previous.at <= packet.at) peers.set(packet.role, packet);
  }
  function last(role) {
    try { receive(JSON.parse(localStorage.getItem(prefix + role) || 'null')); } catch (_) {}
    return peers.get(role) || null;
  }
  function read(role) {
    const value = last(role);
    return value && Date.now() - value.at <= 20000 ? value : null;
  }
  function describe(role) {
    const value = last(role);
    if (!value) return '応答待ち';
    if (read(role)) return '接続済';
    return '更新待ち（最終 ' + new Date(value.at).toLocaleTimeString('ja-JP',{hour:'2-digit',minute:'2-digit',second:'2-digit'}) + '）';
  }
  function emit(role, data) {
    const packet = {...data, role, scope, at: Date.now()};
    let saved = false;
    try {
      localStorage.setItem(prefix + role, JSON.stringify(packet));
      saved = !!scope;
    } catch (_) {}
    receive(packet);
    try { channel?.postMessage(packet); } catch (_) {}
    return saved;
  }
  function notify() { document.dispatchEvent(new CustomEvent(signal)); }
  function request() {
    const now = Date.now();
    if (!scope || now - lastRequestAt < 1500) return;
    lastRequestAt = now;
    const packet = {type:'probe', scope, at:now};
    try { localStorage.setItem(probeKey, JSON.stringify(packet)); } catch (_) {}
    try { channel?.postMessage(packet); } catch (_) {}
  }
  let lastProbe = 0;
  function handleProbe(packet) {
    if (!scope || packet?.scope !== scope || !Number.isFinite(packet.at) ||
        packet.at <= lastProbe || Date.now() - packet.at > 10000) return;
    lastProbe = packet.at;
    for (const publish of publishers.values()) publish();
  }
  window.addEventListener('storage', event => {
    if (event.key === probeKey) {
      try { handleProbe(JSON.parse(event.newValue || 'null')); } catch (_) {}
    } else if (event.key?.startsWith(prefix)) {
      try { receive(JSON.parse(event.newValue || 'null')); } catch (_) {}
      notify();
    }
  });
  if (channel) channel.onmessage = event => {
    if (event.data?.type === 'probe') handleProbe(event.data);
    else { receive(event.data); notify(); }
  };
  function attach(role, snapshot, render) {
    let lastSaved = true;
    function update() {
      try { render(read, lastSaved); } catch (_) {}
    }
    function publish() {
      try { lastSaved = emit(role, snapshot()); } catch (_) { lastSaved = false; }
      update();
    }
    function resume() { publish(); request(); }
    publishers.set(role, publish);
    document.addEventListener(signal, update);
    window.addEventListener('focus', resume);
    window.addEventListener('pageshow', resume);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) resume(); });
    setInterval(publish, 4000);
    resume();
    return publish;
  }
  window.taxiCockpitSync = {attach, read, last, describe, request, signal};
})();
