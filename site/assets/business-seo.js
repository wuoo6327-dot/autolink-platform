/* Public metadata uses reviewed API records; never infer an offer or guarantee. */
(() => {
  const origin='https://autolinkglobal.com';
  const languages=['en','zh','ar','ru','kk','uz','ko','fr','sw'];
  const language=()=>{const active=window.businessI18n?.language||new URLSearchParams(location.search).get('lang')||'en';return active==='zh-CN'?'zh':languages.includes(active)?active:'en';};
  const localizedUrl=(path,code=language())=>origin+path+(code==='en'?'':'?lang='+code);
  const baseDescription='AUTOLINK · Connecting Chinese vehicle suppliers and global buyers.';
  const text=value=>String(value??'').replace(/[\u0000-\u001f\u007f]/g,' ').replace(/\s+/g,' ').trim();
  const tr=value=>window.businessI18n?.text(value)||value;
  let details=null;
  let generatedDescription=null;
  const customDescriptions=new Map();
  const put=(selector,attributes)=>{let node=document.head.querySelector(selector);if(!node){node=document.createElement(selector.startsWith('link')?'link':'meta');document.head.append(node);}for(const [name,value] of Object.entries(attributes))node.setAttribute(name,value);};
  const drop=selector=>document.head.querySelector(selector)?.remove();
  const imageUrl=value=>{
    if(!value)return null;
    try{const url=new URL(value,origin);if(url.protocol!=='https:'||url.username||url.password)return null;
      if(url.origin===origin&&!/^\/(images|assets|autolink\/public\/vehicle-images)\//.test(url.pathname))return null;
      return url.href;
    }catch{return null;}
  };
  const homeGraph=[{'@type':'Organization','@id':origin+'/#organization',name:'AUTOLINK',url:origin},
    {'@type':'WebSite',name:'AUTOLINK',url:origin,potentialAction:{'@type':'SearchAction',target:{'@type':'EntryPoint',urlTemplate:origin+'/trade/vehicles?keyword={search_term_string}'},'query-input':'required name=search_term_string'}}];
  function update(){
    const rawPath=location.pathname.replace(/\/$/,'')||'/';
    const path=rawPath==='/trade'?'/trade/vehicles':rawPath;
    if(details?.path!==path)details=null;
    const privatePage=/^\/(buyer|account|supplier|admin|merchant|platform|workspace|login|register|auth|autolink|api)(\/|$)/.test(path);
    const filtered=path.startsWith('/trade/')&&[...new URLSearchParams(location.search).keys()].some(key=>key!=='lang');
    const excluded=privatePage||details?.kind==='error'||path==='/trade/compare'||filtered;
    const canonical=localizedUrl(path);
    const existingDescription=document.head.querySelector('meta[name="description"]')?.content;
    if(!privatePage&&!path.startsWith('/trade/')&&existingDescription&&existingDescription!==generatedDescription)customDescriptions.set(path,existingDescription);
    const description=privatePage?'AUTOLINK account workspace.':details?.description||customDescriptions.get(path)||tr(baseDescription);
    generatedDescription=description;
    put('link[rel="canonical"]',{rel:'canonical',href:canonical});
    for(const node of document.head.querySelectorAll('link[rel="alternate"][hreflang]'))node.remove();
    if(!excluded){
      for(const code of languages){const node=document.createElement('link');node.rel='alternate';node.hreflang=code==='zh'?'zh-CN':code;node.href=localizedUrl(path,code);document.head.append(node);}
      const node=document.createElement('link');node.rel='alternate';node.hreflang='x-default';node.href=localizedUrl(path,'en');document.head.append(node);
    }
    put('meta[name="robots"]',{name:'robots',content:privatePage?'noindex, nofollow':excluded?'noindex, follow':'index, follow'});
    put('meta[name="description"]',{name:'description',content:description});
    for(const [property,content] of Object.entries({'og:type':'website','og:title':document.title,'og:description':description,'og:url':canonical}))
      put('meta[property="'+property+'"]',{property,content});
    put('meta[name="twitter:card"]',{name:'twitter:card',content:details?.image&&!excluded?'summary_large_image':'summary'});
    put('meta[name="twitter:title"]',{name:'twitter:title',content:document.title});
    put('meta[name="twitter:description"]',{name:'twitter:description',content:description});
    for(const [selector,attributes] of [['meta[property="og:image"]',{property:'og:image'}],['meta[name="twitter:image"]',{name:'twitter:image'}]]){
      if(details?.image&&!excluded)put(selector,{...attributes,content:details.image});else drop(selector);
    }
    const graph=!excluded?(path==='/'?homeGraph:details?.graph||[]):[];
    let node=document.head.querySelector('#autolink-public-jsonld');
    if(graph.length){if(!node){node=document.createElement('script');node.id='autolink-public-jsonld';node.type='application/ld+json';document.head.append(node);}
      node.textContent=JSON.stringify({'@context':'https://schema.org','@graph':graph}).replace(/</g,'\\u003c');
    }else node?.remove();
  }
  function page(kind,data={}){
    const path=location.pathname.replace(/\/$/,'')||'/';
    if(!path.startsWith('/trade/'))return;
    const collection={vehicle:'vehicles',supplier:'suppliers',model:'models',brand:'brands'}[kind];
    const matches=collection&&data.id&&path==='/trade/'+collection+'/'+encodeURIComponent(data.id);
    if(collection&&!matches)return page('error');
    const canonical=localizedUrl(path);
    const listingName=[data.brand,data.model,data.model_year].filter(value=>value!==null&&value!==undefined&&value!=='').map(text).join(' ');
    const modelName=[data.brand,data.model,data.year].filter(value=>value!==null&&value!==undefined&&value!=='').map(text).join(' ');
    const templates={vehicle:['{vehicle} for Export from China | AUTOLINK','vehicle',listingName],supplier:['{supplier} | Chinese Vehicle Supplier | AUTOLINK','supplier',text(data.company_name)],
      model:['{model} Model Reference | AUTOLINK','model',modelName],brand:['{brand} Vehicles for Export from China | AUTOLINK','brand',text(data.name)]};
    const listTitles={vehicles:'Approved Supplier Vehicle Listings | AUTOLINK',suppliers:'Chinese Vehicle Suppliers | AUTOLINK',models:'Chinese Vehicle Model References | AUTOLINK',brands:'Vehicle Brands | AUTOLINK',compare:'Compare Vehicles | AUTOLINK',error:'Page Not Found | AUTOLINK'};
    let title=listTitles[kind]?tr(listTitles[kind]):document.title;
    if(kind==='error'&&data.status&&data.status!==404)title=tr(data.status===403?'Access Denied | AUTOLINK':'Unable to Load Page | AUTOLINK');
    if(templates[kind]){const [template,key,value]=templates[kind];title=tr(template).replace('{'+key+'}',()=>value);}
    const label=kind==='vehicle'?listingName:kind==='supplier'?text(data.company_name):kind==='model'?modelName:kind==='brand'?text(data.name):'';
    const description=text([label,kind==='vehicle'?data.trim:'',kind==='vehicle'?[data.incoterm,data.origin_port].filter(Boolean).join(' '):'',kind==='supplier'?[data.city,data.country].filter(Boolean).join(', '):'',tr(baseDescription)].filter(Boolean).join(' · ')).slice(0,320);
    let image=null,entity=null;
    // Only approved detail renderers call page with records from public APIs.
    // Require the record ID to match this route; a stale response cannot brand another URL.
    if(matches&&kind==='vehicle'){
      image=data.referenceImage===false?imageUrl(data.image):null;
      entity={'@type':'Vehicle','@id':canonical+'#vehicle',url:canonical,name:listingName};
      if(data.brand)entity.brand={'@type':'Brand',name:text(data.brand)};
      if(data.model)entity.model=text(data.model);
      if(data.trim)entity.vehicleConfiguration=text(data.trim);
      if(data.energy_type)entity.fuelType=text(data.energy_type);
      if(['LHD','RHD'].includes(data.steering))entity.steeringPosition='https://schema.org/'+(data.steering==='LHD'?'LeftHandDriving':'RightHandDriving');
      if(['NEW','USED'].includes(data.vehicle_condition))entity.itemCondition='https://schema.org/'+(data.vehicle_condition==='NEW'?'NewCondition':'UsedCondition');
      if(image)entity.image=image;
      // Price is a reference, not a binding offer; no Offer/Review/Rating is emitted.
    }else if(matches&&kind==='supplier'){
      image=imageUrl(data.logo_url);
      entity={'@type':'Organization','@id':canonical+'#supplier',name:text(data.company_name),url:canonical};
      if(image)entity.logo=image;
      if(data.city||data.country)entity.address={'@type':'PostalAddress',...(data.city?{addressLocality:text(data.city)}:{}),...(data.country?{addressCountry:text(data.country)}:{})};
    }else if(matches&&kind==='model'){
      image=imageUrl(data.image);
      entity={'@type':'ProductModel','@id':canonical+'#model',name:modelName,url:canonical,description:tr('Model reference · not a supplier inventory offer.')};
      if(data.brand)entity.brand={'@type':'Brand',name:text(data.brand)};
      if(image)entity.image=image;
    }else if(matches&&kind==='brand')image=imageUrl(data.logo);
    const graph=[];
    if(matches){
      const parentLabel=tr({vehicle:'Vehicles',supplier:'Suppliers',model:'Model references',brand:'Brands'}[kind]);
      graph.push({'@type':'BreadcrumbList',itemListElement:[{name:tr('Home'),item:origin+'/'},{name:parentLabel,item:origin+'/trade/'+collection},{name:label,item:canonical}].map((item,index)=>({'@type':'ListItem',position:index+1,...item}))});
      if(entity)graph.push(entity);
    }
    details={path,kind,description,image,graph};document.title=title;update();
  }
  window.businessSEO=Object.freeze({page,update});
  update();const title=document.head.querySelector('title');if(title)new MutationObserver(update).observe(title,{childList:true,subtree:true});
})();
