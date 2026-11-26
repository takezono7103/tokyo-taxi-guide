(() => {
  'use strict';
  for(const link of document.querySelectorAll('a[target^="taxiCockpit0451"]')){
    link.addEventListener('click',event=>{
      if(event.defaultPrevented||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
      try {
        const destination=new URL(link.href);
        const other=window.open('',link.target);
        if(!other)return;
        event.preventDefault();
        if(other.location.href==='about:blank')other.location.replace(destination.href);
        else {
          const current=new URL(other.location.href);
          const normalize=url=>url.pathname.replace(/index\.html$/,'');
          const needsVersion=current.origin===destination.origin&&destination.searchParams.get('v')==='0463'&&!other.document.title.includes('v0.4.63');
          if(current.origin!==destination.origin||normalize(current)!==normalize(destination)||current.searchParams.has('embed')!==destination.searchParams.has('embed')||needsVersion)other.location.assign(destination.href);
        }
        other.focus();
      }catch(_){}
    });
  }
})();
