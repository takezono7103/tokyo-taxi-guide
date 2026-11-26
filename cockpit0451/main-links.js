(() => {
  'use strict';
  window.name='taxiCockpit0451Main';
  const bar=document.getElementById('taxiOperatingStatus');
  const link=window.taxiShiftLink;
  function render(){
    try {
      const shift=window.taxiShiftGpsReadOnly?.snapshot();
      const report=link.latestClosing();
      const state=shift?.active?'GPS営業記録中'+(shift.dutyDate?' '+shift.dutyDate:''):
        shift?.hasSession?'GPS営業記録 保存済み':'GPS営業記録 未開始';
      const closing=report?'締め登録 '+report.date+' ／ 税込 '+report.paperTotal.toLocaleString('ja-JP')+'円':
        '締め登録 なし';
      bar.textContent=state+' ｜ '+closing;
    }catch(error){
      bar.textContent='乗務の連携状態を確認できません。'+error.message;
    }
  }
  window.addEventListener('storage',event=>{if(!event.key||event.key===link.closeKey)render();});
  window.addEventListener('focus',render);
  window.addEventListener('pageshow',render);
  document.addEventListener('taxi:shift-gps-updated-v0429',render);
  render();
  const publish=window.taxiCockpitSync.attach('main',()=>{
    const shift=window.taxiShiftGpsReadOnly?.snapshot()||{};
    const report=link.latestClosing();
    return {...shift,registeredDate:report?.date||'',registeredAt:report?.savedAt||0};
  },(get,saved)=>{
    const quick=get('quick'),closing=get('closing');
    document.getElementById('taxiPeerStatus').textContent=saved?
      '小窓 '+(quick?'接続済':'応答待ち')+' ／ 締め '+(closing?'接続済':'応答待ち'):'3画面の共有保存エラー';
    render();
  });
  document.addEventListener('taxi:shift-gps-updated-v0429',publish);
  window.addEventListener('storage',event=>{if(event.key===link.closeKey)publish();});
})();
