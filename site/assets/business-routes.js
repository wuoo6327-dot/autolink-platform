/* Compatible full-page navigation from the existing compiled React shell. */
(() => {
  const routes={'/brands':'/trade/brands','/models':'/trade/models','/vehicles':'/trade/vehicles','/suppliers':'/trade/suppliers','/requests':'/buyer/requests','/supplier-apply':'/supplier/application'};
  function refreshLinks(root=document){
    const links=[...(root.matches?.('a[href]')?[root]:[]),...(root.querySelectorAll?.('a[href]')||[])];
    for(const link of links){
      const url=new URL(link.href,location.href);
      if(url.origin!==location.origin)continue;const target=routes[url.pathname]||(/^\/(brands|models|vehicles|suppliers)\//.test(url.pathname)?'/trade'+url.pathname:null);if(target)link.href=target+url.search+url.hash;
    }
  }
  const addedRoots=new Set();let refreshFrame=0;
  new MutationObserver(records=>{
    if(!records){refreshLinks();return;}
    for(const record of records)for(const node of record.addedNodes)if(node.nodeType===1)addedRoots.add(node);
    if(!addedRoots.size||refreshFrame)return;
    refreshFrame=requestAnimationFrame(()=>{
      refreshFrame=0;
      for(const root of addedRoots)if(root.isConnected)refreshLinks(root);
      addedRoots.clear();
    });
  }).observe(document.documentElement,{childList:true,subtree:true});
  refreshLinks();
  window.autolinkSearch = values => {
    const query = new URLSearchParams();
    if(values.keyword!=null){
      if(typeof values.keyword!=='string'||values.keyword.length>80||/[\x00-\x1f\x7f]/.test(values.keyword))throw Error('Invalid keyword');
      if(values.keyword.trim())query.set('keyword',values.keyword.trim());
    }
    for (const key of ['brand','model','vehicleType']) if(values[key]) query.set(key,values[key]);
    if(values.energy) query.set('energyType',values.energy);
    const prices={'Under $25,000':[null,2500000],'$25,000–$35,000':[2500000,3500000],'Over $35,000':[3500000,null]};
    const range=prices[values.price];
    if(range?.[0]!=null) query.set('minPriceMinor',range[0]);
    if(range?.[1]!=null) query.set('maxPriceMinor',range[1]);
    const target = '/trade/vehicles' + (query.size ? '?' + query : '');
    location.assign(target);
    return target;
  };
  document.addEventListener('click', event => {
    if(event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
    const link=event.target.closest('a[href]');
    if(!link||link.target==='_blank'||link.hasAttribute('download'))return;
    // A newly inserted link may be clicked before the next animation frame.
    refreshLinks(link);
    const url=new URL(link.href,location.href);
    if(url.origin!==location.origin||!/^\/(trade|supplier|buyer|support|admin)(\/|$)/.test(url.pathname))return;
    event.preventDefault();event.stopPropagation();location.assign(url.pathname+url.search+url.hash);
  },true);
})();
