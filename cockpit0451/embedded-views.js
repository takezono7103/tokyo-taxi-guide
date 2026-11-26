(() => {
  'use strict';
  const views = {
    quick: {panel:'taxiQuickPanel', frame:'taxiQuickFrame', page:'quick.html'},
    closing: {panel:'taxiClosingPanel', frame:'taxiClosingFrame', page:'closing.html'}
  };
  const get = id => document.getElementById(id);
  const toggles = [...document.querySelectorAll('[data-embedded-view]')];
  function setView(name, visible) {
    const {panel, frame, page} = views[name];
    const section = get(panel);
    const child = get(frame);
    section.hidden = !visible;
    for (const button of toggles) if (button.dataset.embeddedView === name) {
      button.setAttribute('aria-expanded', String(visible));
    }
    if (visible && !child.hasAttribute('src')) {
      if(name==='quick')get('taxiQuickLinkStatus').textContent='小窓を読み込み中…';
      child.src = new URL('./' + page + '?embed=1', location.href).href;
    }
  }
  for (const button of toggles) button.addEventListener('click', () => {
    const name = button.dataset.embeddedView;
    const open = get(views[name].panel).hidden;
    for (const candidate of Object.keys(views)) setView(candidate, candidate === name && open);
    if(open)get(views[name].panel).scrollIntoView({block:'nearest'});
  });
  for (const button of document.querySelectorAll('[data-embedded-close]')) {
    button.addEventListener('click', () => {
      const name = button.dataset.embeddedClose;
      setView(name, false);
      toggles.find(toggle => toggle.dataset.embeddedView === name)?.focus();
    });
  }
  window.addEventListener('message', event => {
    if (event.origin !== location.origin || event.source !== get('taxiQuickFrame').contentWindow) return;
    if (event.data?.type === 'taxi-quick-navigation-v0453') {
      if (event.data.view === 'main') {
        setView('quick', false);
        setView('closing', false);
        document.querySelector('[data-tab="home"]')?.click();
        get('taxiOperatingNav').scrollIntoView({block:'nearest'});
      } else if (event.data.view === 'closing') {
        setView('quick', false);
        setView('closing', true);
        get(views.closing.panel).scrollIntoView({block:'nearest'});
      }
      return;
    }
    if (event.data?.type !== 'taxi-quick-ready-v0453') return;
    get('taxiQuickLinkStatus').textContent = event.data.available
      ? 'メインと計測データを共有中'
      : '計測データを共有できません。SafariでサイトのURLを開いてください。';
  });
})();
