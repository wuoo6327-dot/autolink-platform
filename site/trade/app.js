const tr = value => window.businessI18n.text(value);
const root = document.querySelector('#app');
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const usd = (cents,currency='USD') => cents==null?esc(tr('Members only')):new Intl.NumberFormat(window.businessI18n.locale,{style:'currency',currency,maximumFractionDigits:2}).format(Number(cents)/100);
// Only reference catalogues are shared in memory. Listing prices, contacts and
// account data always come from the current server-side session.
const referenceCache = new Map();
const referencePath = path => /^\/autolink\/public\/(?:models|brands)(?:\/[A-Za-z0-9_-]+)?$/.test(path);
const fetchData = async (path, method, body, signal) => {
  let response;
  try{
    response = await fetch(path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal});
    const result = await response.json();
    if(!response.ok || result.code!==200)throw Object.assign(Error(typeof result?.msg==='string'?result.msg:'Request failed.'),{status:response.ok?Number(result?.code):response.status});
    return result.data;
  }catch(error){if(error.name==='AbortError')throw error;throw window.businessI18n.apiError?.(error,response?.status)||error;}
};
const read = async (path, method='GET', body) => {
  const current=navigationId;
  try {
    let data;
    if(method==='GET'&&referencePath(path)){
      let entry=referenceCache.get(path);
      if(entry?.expiresAt>Date.now())data=await Promise.resolve(entry.value);
      else{
        if(!entry?.promise){
          entry={};referenceCache.set(path,entry);
          entry.promise=fetchData(path,method,body,AbortSignal.timeout(15000)).then(value=>{
            entry.value=value;entry.expiresAt=Date.now()+60000;delete entry.promise;return value;
          },error=>{if(referenceCache.get(path)===entry)referenceCache.delete(path);throw error;});
        }
        data=await entry.promise;
      }
    }else{
      const signal=method==='GET'&&readController?AbortSignal.any([readController.signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000);
      data=await fetchData(path,method,body,signal);
    }
    if(method==='GET'&&current!==navigationId)throw new DOMException('Navigation changed','AbortError');
    return data;
  }catch(error){
    if(method==='GET'&&current!==navigationId)throw new DOMException('Navigation changed','AbortError');
    if(error.name==='AbortError')throw error;
    throw window.businessI18n.apiError?.(error,error.status)||error;
  }
};
const link = (href,label,secondary=false) => `<a class="button-link${secondary?' secondary':''}" href="${esc(href)}">${esc(label)}</a>`;
const activeAccountLabels={"en":["Business account active","An active business account is not a platform guarantee of company credentials, stock or fulfilment."],"zh":["平台业务账号已启用","业务账号已启用不代表平台保证企业资质、库存或履约。"],"ar":["حساب الأعمال مفعّل","تفعيل حساب الأعمال لا يضمن مؤهلات الشركة أو المخزون أو تنفيذ الالتزامات."],"ru":["Бизнес-аккаунт активен","Активный бизнес-аккаунт не гарантирует документы компании, запасы или исполнение обязательств."],"kk":["Бизнес аккаунты іске қосылған","Іске қосылған бизнес аккаунты компания құжаттарына, қорға немесе міндеттемелерге кепілдік бермейді."],"uz":["Biznes hisobi faol","Faol biznes hisobi kompaniya hujjatlari, zaxira yoki majburiyatlar bajarilishiga kafolat bermaydi."],"ko":["사업 계정 활성화됨","사업 계정 활성화는 회사 자격, 재고 또는 이행을 보증하지 않습니다."],"fr":["Compte professionnel actif","Un compte professionnel actif ne garantit ni les justificatifs de l’entreprise, ni le stock, ni l’exécution."],"sw":["Akaunti ya biashara imewashwa","Akaunti ya biashara haihakikishi nyaraka za kampuni, hisa au utekelezaji."]};
const activeAccountText=index=>(activeAccountLabels[window.businessI18n.language]||activeAccountLabels.en)[index];
const verified = `<span class="trade-verified">${esc(activeAccountText(0))} <span aria-hidden="true">ⓘ</span></span>`;
let me = null, currentListing = null, currentSupplier = null;
// Legacy merchant roles retain buyer access; an explicit capability takes priority.
const hasBuyerCapability = account => Boolean(account &&
  (account.capabilities?.buyer ?? ['BUYER','MERCHANT','SUPPLIER'].includes(account.role)));
let navigationId=0,readController=null,navigationUrl=location.pathname+location.search;
function assertNavigation(current){if(current!==navigationId)throw new DOMException('Navigation changed','AbortError');}

function shell(content, title='Vehicle Listings | AUTOLINK') {
  document.title = title;
  const section=location.pathname.split('/').filter(Boolean)[1];
  if(location.pathname.split('/').filter(Boolean).length<3&&['vehicles','suppliers','models','brands','compare'].includes(section))window.businessSEO?.page(section);
  document.documentElement.lang = window.businessI18n.language;
  document.documentElement.dir = window.businessI18n.language==='ar'?'rtl':'ltr';
  root.innerHTML = `<header class="trade-head"><div class="trade-head-inner"><a class="brand" href="/">AUTOLINK<i>▪</i></a><nav class="trade-nav" aria-label="${esc(tr("Main navigation"))}"><a href="/">${esc(tr("Home"))}</a><a href="/trade/vehicles">${esc(tr("Supplier Vehicles"))}</a><a href="/trade/models">${esc(tr("Model references"))}</a><a href="/trade/brands">${esc(tr("Brands"))}</a><a href="/trade/suppliers">${esc(tr("Suppliers"))}</a><a href="/membership">${esc(tr("Membership"))}</a><a href="${me?.role==='PLATFORM_ADMIN'?'/admin':['MERCHANT','SUPPLIER'].includes(me?.role)?'/supplier':'/buyer'}">${me?esc(me.nickName||me.username||me.companyName||me.email):esc(tr('Buyer Center'))}</a><a href="/supplier/application">${esc(tr("Supplier Center"))}</a></nav>${window.businessI18n.languageControl()}</div></header><main class="trade-main" id="main">${content}</main><footer class="trade-footer"><div class="trade-footer-inner"><span>${esc(tr("AUTOLINK · Connecting Chinese vehicle suppliers and global buyers."))}</span><span><a href="/terms">${esc(tr("Terms"))}</a><a href="/membership-terms">${esc(tr("Membership Terms"))}</a><a href="/privacy">${esc(tr("Privacy"))}</a><a href="/support">${esc(tr("Contact support"))}</a></span></div></footer>`;
}
function fail(error) { error=window.businessI18n.apiError?.(error)||error; shell(`<div class="alert error trade-error" role="alert">${esc(tr(error.message))}</div>${link('/trade/vehicles',tr("Back to vehicles"))}`); window.businessSEO?.page('error',{status:error.status||500}); }
function loginLink() { return '/buyer/login?returnTo='+encodeURIComponent(location.pathname+location.search); }
function card(v) { return `<article class="trade-card"><img loading="lazy" src="${esc(v.image||'/favicon.svg')}" alt="${esc(v.brand)} ${esc(v.model)}"><div class="trade-card-body"><span class="eyebrow">${esc(v.supplier_name)}</span><h2>${esc(v.brand)} ${esc(v.model)}</h2><p>${esc(v.model_year)} · ${esc(v.trim||tr(v.energy_type||''))} · ${esc(v.steering)} · ${esc(conditionLabel(v.vehicle_condition))}</p><strong>${usd(v.price_minor,v.currency)}</strong><small>${esc(v.incoterm)} ${esc(v.origin_port)} ${esc(tr("· Reference price / unit"))}</small><small>${esc(tr("MOQ"))} ${Number(v.moq)} ${esc(tr("· Stock"))} ${Number(v.stock)}</small>${link('/trade/vehicles/'+encodeURIComponent(v.id),tr("View trade details"))}</div></article>`; }
async function vehicles() {
  const current=navigationId;
  const params=new URLSearchParams(location.search);
  const query=new URLSearchParams();
  for(const key of ['keyword','brand','model','vehicleType','energyType','condition','steering','incoterm','sort','minPriceMinor','maxPriceMinor','year','minStock','supplierId']) if(params.get(key)) query.set(key,params.get(key));
  let offset=Number(params.get('offset')||0); if(!Number.isSafeInteger(offset)||offset<0) offset=0;
  query.set('offset',String(offset));query.set('limit','25');
  const [data,suppliers,models]=await Promise.all([read('/autolink/public/vehicles?'+query),read('/autolink/public/suppliers'),modelCatalog()]);
  assertNavigation(current);
  const bodyChoices=[['','All body types'],...[...new Set(models.map(m=>m.bodyType).filter(Boolean))].sort().map(type=>[type,type])];
  if(params.get('vehicleType')&&!bodyChoices.some(([type])=>type===params.get('vehicleType')))bodyChoices.push([params.get('vehicleType'),params.get('vehicleType')]);
  const shown=data.slice(0,24),hasNext=data.length>24;
  const nextParams=new URLSearchParams(params);nextParams.set('offset',String(offset+24));
  const prevParams=new URLSearchParams(params);prevParams.set('offset',String(Math.max(0,offset-24)));
  const clearParams=new URLSearchParams();if(params.get('lang'))clearParams.set('lang',params.get('lang'));
  const clearUrl='/trade/vehicles'+(clearParams.size?'?'+clearParams:'');
  const input=(name,label,options='')=>`<label><span>${esc(tr(label))}</span><input name="${name}" value="${esc(params.get(name)||'')}" ${options}></label>`;
  const select=(name,label,choices)=>`<label><span>${esc(tr(label))}</span><select name="${name}">${choices.map(([value,caption])=>`<option value="${esc(value)}" ${(params.get(name)||'')===value?'selected':''}>${esc(tr(caption))}</option>`).join('')}</select></label>`;
  const priceInput=(name,label,key)=>`<label><span>${esc(tr(label))}</span><input name="${name}" type="number" min="0" max="10000000000" step="0.01" value="${params.has(key)?esc((Number(params.get(key))/100).toFixed(2)):''}"></label>`;
  const advanced=['vehicleType','condition','steering','incoterm','year','minStock','minPriceMinor','maxPriceMinor','supplierId'].some(key=>params.has(key));
  const supplierOptions=suppliers.map(s=>`<option value="${esc(s.id)}" ${params.get('supplierId')===s.id?'selected':''}>${esc(s.company_name)}</option>`).join('');
  const hasSelectedSupplier=suppliers.some(s=>s.id===params.get('supplierId'));
  const filters=`<form class="trade-search" id="trade-search"><div class="trade-filters">${input('keyword','Search brand, model or trim','maxlength="80"')}${input('brand','Brand','maxlength="120"')}${input('model','Model','maxlength="120"')}${select('energyType','Energy type',[['','All energy types'],['Electric','Electric'],['Plug-in Hybrid','Plug-in Hybrid'],['Gasoline','Gasoline'],['PHEV','PHEV'],['EV','EV'],['ICE','ICE'],['HEV','HEV']])}${select('sort','Sort',[['','Newest'],['price_asc','Price low to high'],['price_desc','Price high to low'],['popular','Popular']])}<button class="btn" type="submit">${esc(tr('Search Vehicles'))}</button></div><details class="trade-advanced" ${advanced?'open':''}><summary>${esc(tr('More filters'))}</summary><div class="trade-filter-options">${select('vehicleType','Body type',bodyChoices)}${input('year','Year','type="number" min="1990" max="2100"')}${input('minStock','Minimum stock','type="number" min="0" max="1000000"')}${select('condition','Condition',[['','Any condition'],['NEW','New vehicle'],['USED','Used vehicle']])}${select('steering','Steering',[['','Any steering'],['LHD','LHD'],['RHD','RHD']])}${select('incoterm','Incoterm',[['','Any incoterm'],['FOB','FOB'],['CIF','CIF'],['CFR','CFR'],['EXW','EXW']])}${priceInput('minPrice','Minimum price (USD / unit)','minPriceMinor')}${priceInput('maxPrice','Maximum price (USD / unit)','maxPriceMinor')}<label><span>${esc(tr('Supplier'))}</span><select name="supplierId"><option value="">${esc(tr('All suppliers'))}</option>${!hasSelectedSupplier&&params.get('supplierId')?`<option value="${esc(params.get('supplierId'))}" selected>${esc(tr('Selected supplier'))}</option>`:''}${supplierOptions}</select></label></div><p class="trade-note">${esc(tr('Popular uses verified buyers’ recent listing views from the last 30 days. Prices are supplier reference prices in USD per unit.'))}</p></details><div class="trade-filter-actions">${link(clearUrl,tr('Clear filters'),true)}</div></form>`;
  const resultText=tr('Listings on this page: {count}').replace('{count}',String(shown.length));
  const noResults=query.size>2?tr('No listings match these filters.'):tr('No approved vehicle listings yet.');
  shell(`<div class="trade-intro"><div><span class="eyebrow">${esc(tr('CHINA → GLOBAL MARKETS'))}</span><h1>${esc(tr('Supplier vehicle listings.'))}</h1><p>${esc(tr('Approved Chinese suppliers publish their own stock and trade terms. Prices are references until the supplier confirms a formal quotation.'))}</p></div>${link('/buyer/requests',tr('Post buying request'),true)}</div>${filters}<p class="trade-results">${esc(resultText)}</p>${shown.length?`<div class="trade-grid">${shown.map(card).join('')}</div>`:`<div class="empty"><strong>${esc(noResults)}</strong><p>${esc(tr('Suppliers can publish inventory after company and vehicle review. The model catalogue remains available for research.'))}</p>${link('/trade/models',tr('Browse model references'),true)}</div>`}<nav class="trade-pagination" aria-label="${esc(tr('Pagination'))}">${offset>0?link('/trade/vehicles?'+prevParams,tr('Previous'),true):''}${hasNext?link('/trade/vehicles?'+nextParams,tr('Next'),true):''}</nav><p class="trade-note">${esc(tr('AUTOLINK connects buyers and suppliers. Vehicle payment and trade terms are agreed directly between them. AUTOLINK does not hold vehicle purchase funds or guarantee a transaction.'))}</p>`,'Vehicle Listings from China | AUTOLINK');
}

const conditionLabel=value=>tr(value==='NEW'?'New vehicle':value==='USED'?'Used vehicle':value);
const field = (name,value) => `<div class="trade-field"><span>${esc(tr(name))}</span><strong>${esc(value===null||value===undefined||value===''?'—':value)}</strong></div>`;
const brandMark=(logo,name)=>logo?`<img class="trade-brand-logo" src="${esc(logo)}" alt="${esc(name)}" loading="lazy" decoding="async">`:'';
async function vehicleDetail(id) {
  const current=navigationId;
  let v;try{v=await read('/autolink/public/vehicles/'+encodeURIComponent(id));}catch(error){if(error.status===404){const reference=(await modelCatalog()).find(item=>item.id===id);assertNavigation(current);if(reference){await modelDetail(id,reference);return;}}throw error;}assertNavigation(current);currentListing=v;
  if(hasBuyerCapability(me)) read('/autolink/buyer/history','POST',{listingId:id}).catch(()=>{});
  shell(`<div class="trade-breadcrumb"><a href="/trade/vehicles">${esc(tr("Supplier vehicles"))}</a> / ${esc(v.brand)} ${esc(v.model)}</div><div class="trade-detail"><div><img class="trade-hero-image" src="${esc(v.image||'/favicon.svg')}" alt="${esc(v.brand)} ${esc(v.model)}"><section class="panel" style="margin-top:20px"><div class="panel-head"><h2>${esc(tr("Trade information"))}</h2></div><div class="trade-fields">${field(tr("MOQ"),v.moq)}${field(tr("Availability"),tr(v.status==='ONLINE'?'Available':'Unavailable'))}${field(tr("Stock"),v.stock)}${field(tr("Export port"),v.origin_port)}${field(tr("Lead time"),v.lead_time)}${field(tr("Price valid until"),v.valid_until)}${field(tr("Vehicle location"),v.location)}${field(tr("Incoterm"),v.incoterm)}${field(tr("Payment terms"),v.payment_terms)}${field(tr("Production year"),v.model_year)}${field(tr("VIN availability"),tr(v.vin_available?'Available on request':'Not specified'))}${field(tr("Available colors"),v.colors)}${field(tr("Export markets"),v.export_markets)}${field(tr("Steering"),v.steering)}</div><p class="trade-note">${(v.description?esc(v.description):esc(tr('Final vehicle specification and availability must be confirmed directly with the supplier.')))}</p></section></div><div><span class="eyebrow">${esc(v.brand)} · ${esc(tr(v.energy_type||'Vehicle'))}</span><h1>${esc(v.brand)} ${esc(v.model)} ${esc(v.trim||'')}</h1><p>${esc(v.model_year)} · ${esc(v.steering)} · ${esc(conditionLabel(v.vehicle_condition))}</p><div class="trade-price">${usd(v.price_minor,v.currency)}</div>${v.referenceImage?`<p class="trade-note">${esc(tr("Model reference photo · confirm actual inventory with the supplier."))}</p>`:''}<p class="trade-note">${esc(v.incoterm)} ${esc(tr("China · Reference price / unit. A formal quote may change with quantity, destination and availability."))}</p><div class="trade-detail-actions"><button class="btn" data-action="quote">${esc(tr("Request Quote"))}</button><button class="btn secondary" data-action="contact-supplier">${esc(tr("Contact Supplier"))}</button><button class="btn secondary" data-action="save">${esc(tr("Save Vehicle"))}</button><button class="btn secondary" data-action="compare">${esc(tr("Compare"))}</button><button class="btn secondary" data-action="share">${esc(tr("Share"))}</button></div><div id="trade-message" role="status" aria-live="polite"></div><section class="panel" id="inquiry-panel" hidden><div class="panel-head"><h2>${esc(tr("Send inquiry"))}</h2></div><form class="trade-form" id="inquiry-form"><label>${esc(tr("Quantity"))}<input type="number" name="quantity" min="${Number(v.moq)}" value="${Number(v.moq)}" required></label><label>${esc(tr("Destination country"))}<input name="destinationCountry" maxlength="120" required></label><label>${esc(tr("Destination port"))}<input name="destinationPort" maxlength="120"></label><label>${esc(tr("Incoterm"))}<select name="incoterm"><option value="FOB">${esc(tr("FOB"))}</option><option value="CIF">${esc(tr("CIF"))}</option><option value="CFR">${esc(tr("CFR"))}</option><option value="EXW">${esc(tr("EXW"))}</option></select></label><label>${esc(tr("Target price ({currency} / unit, optional)").replace("{currency}",v.currency))}<input type="number" name="targetPrice" min="0" step="0.01"></label><label class="wide">${esc(tr("Message"))}<textarea name="message" maxlength="2000"></textarea></label><button class="btn" type="submit">${esc(tr("Send Inquiry"))}</button></form><p class="trade-note">${esc(tr("Your inquiry goes to this supplier's inbox. No purchase or payment occurs here."))}</p></section><section class="panel"><div class="panel-head"><h2>${esc(tr("Supplier"))}</h2></div><p><strong>${esc(v.supplier_name)}</strong> ${verified}</p><p class="trade-note">${esc(tr(v.supplier_country||'China'))}</p>${link('/trade/suppliers/'+encodeURIComponent(v.supplier_id),tr("View Supplier"),true)} ${link('/support?entity=vehicle&id='+encodeURIComponent(v.id),tr("Report listing"),true)}<p class="trade-note">${esc(tr("Verification means AUTOLINK checked certain company information. It does not guarantee stock, performance, payment safety or the transaction."))}</p></section></div></div>` ,`${v.brand} ${v.model} ${v.model_year} for Export from China | AUTOLINK`);
  window.businessSEO?.page('vehicle',v);
  const model=(await modelCatalog()).find(m=>m.id===v.model_id);assertNavigation(current);if(model)await attachModelReference(model);
}
async function suppliers() {
  const current=navigationId,data=await read('/autolink/public/suppliers');
  assertNavigation(current);
  shell(`<div class="trade-intro"><div><span class="eyebrow">${esc(tr("SUPPLIER DIRECTORY"))}</span><h1>${esc(tr("Chinese vehicle suppliers."))}</h1><p>${esc(tr("Only companies approved for a public supplier profile appear here. Verification is a company information check, not a trade guarantee."))}</p></div></div>${data.length?`<div class="trade-grid">${data.map(s=>`<article class="trade-card trade-supplier-card"><span class="eyebrow">${esc(tr(s.country||'China'))}</span><h2>${esc(s.company_name)}</h2>${verified}<p>${esc(s.description||tr('Automotive supplier'))}</p>${link('/trade/suppliers/'+encodeURIComponent(s.id),tr("View supplier"))}</article>`).join('')}</div>`:`<div class="empty"><strong>${esc(tr("No verified public suppliers yet."))}</strong><p>${esc(tr("Supplier profiles appear after platform review."))}</p></div>`}<p class="trade-note">${esc(tr("AUTOLINK does not guarantee vehicle availability, contract performance or payment safety."))}</p>`,'Chinese Automotive Suppliers | AUTOLINK');
}
function supplierContact(s){
  const contact=s.contact;
  const details=contact?`<div class="trade-fields trade-contact-fields">
    ${contact.name?field('Public contact person',contact.name):''}
    ${contact.email?`<div class="trade-field"><span>${esc(tr('Email'))}</span><a dir="ltr" href="mailto:${esc(encodeURIComponent(contact.email))}">${esc(contact.email)}</a></div>`:''}
    ${contact.phone?`<div class="trade-field"><span>${esc(tr('Phone'))}</span><a dir="ltr" href="tel:${esc(contact.phone.replace(/[^+0-9]/g,''))}">${esc(contact.phone)}</a></div>`:''}
    ${contact.website?`<div class="trade-field"><span>${esc(tr('Website'))}</span><a dir="ltr" href="${esc(contact.website)}" target="_blank" rel="noopener noreferrer">${esc(contact.website)}</a></div>`:''}
    ${contact.address?field('Public business address',contact.address):''}
  </div><p class="trade-note">${esc(tr('These business contact details were published by the supplier. Confirm vehicle availability and trade terms directly.'))}</p>`:
    s.contactLocked?`<p class="trade-note">${esc(tr('Members only'))}</p>${link('/membership',tr('Membership'),true)}`:`<p class="trade-note">${esc(tr('This supplier has not published direct contact details. Choose a vehicle and send an inquiry to request a quotation and contact details.'))}</p>`;
  return `<section class="panel" id="supplier-contact" tabindex="-1"><div class="panel-head"><h2>${esc(tr('Contact Supplier'))}</h2></div>${details}${link('/trade/vehicles?supplierId='+encodeURIComponent(s.id),tr('View this supplier’s vehicles'),true)}</section>`;
}
async function supplierDetail(id) {
  const current=navigationId;
  const [s,own]=await Promise.all([read('/autolink/public/suppliers/'+encodeURIComponent(id)),read('/autolink/public/vehicles?limit=50&supplierId='+encodeURIComponent(id))]);
  assertNavigation(current);currentSupplier=s;
  shell(`<div class="trade-breadcrumb"><a href="/trade/suppliers">${esc(tr('Suppliers'))}</a> / ${esc(s.company_name)}</div>
    <div class="trade-intro"><div>${s.logo_url?`<img class="trade-company-logo" src="${esc(s.logo_url)}" alt="${esc(s.company_name)}" referrerpolicy="no-referrer">`:''}
      <span class="eyebrow">${esc(tr('SUPPLIER PROFILE'))}</span><h1>${esc(s.company_name)}</h1><p>${verified} · ${esc(tr(s.country||'China'))} ${esc(s.city||'')}</p>
    </div><div class="inline-actions"><button class="btn secondary" data-action="save-supplier">${esc(tr('Save Supplier'))}</button>${link('/support?entity=supplier&id='+encodeURIComponent(s.id),tr('Report supplier'),true)}</div></div>
    <div id="trade-message" role="status" aria-live="polite"></div><div class="two-cols">
    <section class="panel"><div class="panel-head"><h2>${esc(tr('Company overview'))}</h2></div><p>${esc(s.description||tr('No overview available.'))}</p>
      <div class="trade-fields">${field('Established',s.established_year)}${field('Main brands',s.main_brands)}${field('Main markets',s.main_markets)}${field('Export experience',s.export_experience)}${field('Location',[s.city,s.country].filter(Boolean).join(', '))}${field('Joined AUTOLINK',s.joined_at?new Date(s.joined_at*1000).toLocaleDateString(window.businessI18n.locale):'')}</div>
    </section><section class="panel"><div class="panel-head"><h2>${esc(activeAccountText(0))}</h2></div>
      <p class="trade-note">${esc(activeAccountText(1))}</p>
      <p class="trade-note">${esc(tr('For a specific vehicle, send an inquiry to request a formal quote and contact details.'))}</p>
    </section></div>${supplierContact(s)}
    <section class="panel"><div class="panel-head"><h2>${esc(tr('Published vehicles'))}</h2>${link('/trade/vehicles?supplierId='+encodeURIComponent(s.id),tr('View all vehicles'),true)}</div>
      ${own.length?`<div class="trade-grid">${own.map(card).join('')}</div>`:`<div class="empty"><strong>${esc(tr('No published vehicles from this supplier.'))}</strong><p>${esc(tr('Check again after vehicle review.'))}</p></div>`}
    </section>`,`${s.company_name} | Chinese Vehicle Supplier | AUTOLINK`);
  window.businessSEO?.page('supplier',s);
  if(location.hash==='#supplier-contact'){
    const panel=document.querySelector('#supplier-contact');panel.scrollIntoView();panel.focus({preventScroll:true});
  }
}
async function modelCatalog(){return read('/autolink/public/models');}
async function models(){
 const current=navigationId,all=await modelCatalog();assertNavigation(current);const params=new URLSearchParams(location.search);
 const keyword=(params.get('keyword')||'').trim(),brand=params.get('brand')||'',body=params.get('bodyType')||'';
 const shown=all.filter(m=>(!brand||m.brand===brand)&&(!body||m.bodyType===body)&&(m.brand+' '+m.model).toLowerCase().includes(keyword.toLowerCase()));
 const pages=Math.max(1,Math.ceil(shown.length/24)),page=Math.min(pages,Math.max(1,Math.floor(Number(params.get('page')))||1)),rows=shown.slice((page-1)*24,page*24);
 const url=n=>{const q=new URLSearchParams(params);q.set('page',String(n));return '/trade/models?'+q;};
 const allBrands={en:'All brands',zh:'全部品牌',ar:'جميع العلامات',ru:'Все марки',kk:'Барлық брендтер',uz:'Barcha brendlar',ko:'모든 브랜드',fr:'Toutes les marques',sw:'Chapa zote'}[window.businessI18n.language]||'All brands';
 const options=(values,selected,allLabel)=>`<option value="">${esc(tr(allLabel))}</option>${values.map(v=>`<option value="${esc(v)}" ${v===selected?'selected':''}>${esc(tr(v))}</option>`).join('')}`;
 shell(`<div class="trade-intro"><div><span class="eyebrow">${esc(tr("MODEL REFERENCE LIBRARY"))}</span><h1>${esc(tr("Explore Chinese vehicle models."))}</h1><p>${esc(tr("Model references help you research vehicles. They are not supplier inventory, availability or an offer to sell."))}</p></div>${link('/trade/vehicles',tr("View approved supplier listings"),true)}</div><form id="model-search" class="trade-filters model-directory-filters"><label>${esc(tr('Search brand or model'))}<input name="keyword" value="${esc(keyword)}" maxlength="80" placeholder="${esc(tr('Search brand or model'))}"></label><label>${esc(tr('Brand'))}<select name="brand">${options([...new Set(all.map(m=>m.brand))].sort(),brand,allBrands)}</select></label><label>${esc(tr('Body type'))}<select name="bodyType">${options([...new Set(all.map(m=>m.bodyType))].sort(),body,'All body types')}</select></label><button class="btn" type="submit">${esc(tr('Search models'))}</button></form><p class="trade-results">${shown.length} ${esc(tr('Model references'))}</p>${rows.length?`<div class="trade-grid">${rows.map(model=>`<article class="trade-card"><img loading="lazy" decoding="async" src="${esc(model.image)}" alt="${esc(model.brand)} ${esc(model.model)}"><div class="trade-card-body"><div class="trade-model-brand">${brandMark(model.brandLogo,model.brand)}<span>${esc(model.brand)}</span></div><span class="eyebrow">${esc(tr('MODEL REFERENCE'))}</span><h2>${esc(model.model)}</h2><p>${esc(model.year||tr('Year unspecified'))} · ${esc(tr(model.energy))} · ${esc(tr(model.bodyType))}</p>${link('/trade/models/'+encodeURIComponent(model.id),tr('View model reference'))}</div></article>`).join('')}</div>`:`<div class="empty">${esc(tr('No matching models'))}</div>`}<nav class="model-directory-page" aria-label="${esc(tr('Pagination'))}">${page>1?link(url(page-1),tr('Previous'),true):''}<span>${page} / ${pages}</span>${page<pages?link(url(page+1),tr('Next'),true):''}</nav>`,'Chinese Vehicle Model Reference Library | AUTOLINK');
}
async function modelDetail(id,known){const current=navigationId,model=known||(await modelCatalog()).find(item=>item.id===id);assertNavigation(current);if(!model){shell(`<h1>${esc(tr("404 · Model not found"))}</h1>${link('/trade/models',tr("Model references"))}`);window.businessSEO?.page('error');return;}const query=new URLSearchParams({brand:model.brand,model:model.model});shell(`<div class="trade-breadcrumb"><a href="/trade/models">${esc(tr("Model references"))}</a> / ${esc(model.brand)} ${esc(model.model)}</div><div class="trade-detail"><div><img class="trade-hero-image" src="${esc(model.image)}" alt="${esc(model.brand)} ${esc(model.model)}"></div><div><span class="eyebrow">${esc(tr("MODEL REFERENCE · NOT A STOCK OFFER"))}</span><div class="trade-brand-heading">${brandMark(model.brandLogo,model.brand)}<h1>${esc(model.brand)} ${esc(model.model)}</h1></div><div class="trade-fields">${field(tr("Brand"),model.brand)}${field(tr("Model"),model.model)}${field(tr("Year"),model.year)}${field(tr("Energy"),tr(model.energy))}${field(tr("Body type"),tr(model.bodyType))}${Object.entries(model.specifications||{}).map(([key,value])=>field(key,value)).join('')}</div>${model.description?`<p>${esc(model.description)}</p>`:''}<p class="trade-note">${esc(tr("This catalogue entry describes a model only. Confirm the exact trim, steering, specification, stock and price with an approved supplier. No supplier inventory or quote is implied."))}</p>${link('/trade/vehicles?'+query,tr("Find approved supplier offers"))} ${link('/trade/models',tr("Back to model library"),true)}</div></div>`,`${model.brand} ${model.model} ${model.year} Model Reference | AUTOLINK`);window.businessSEO?.page('model',model);await attachModelReference(model);}
async function attachModelReference(model){
 const current=navigationId;
 const holder=document.createElement('section');holder.className='model-reference';holder.id='model-reference';
 holder.innerHTML=`<div class="reference-loading">${esc(tr('Loading…'))}</div>`;document.querySelector('#main').append(holder);
 try{const {mountReference}=await import('/trade/model-reference.mjs?v=20261008-models-clean');if(current!==navigationId||!holder.isConnected)return;await mountReference(holder,{model,language:window.businessI18n.language,locale:window.businessI18n.locale,read,card,translate:tr});}
 catch(error){holder.innerHTML=`<div class="empty">${esc(tr('Configuration information unavailable'))}</div>`;}
}

function normalizeCompareIds(value) {
  if(!Array.isArray(value))return [];
  return [...new Set(value.filter(id=>typeof id==='string'&&/^[A-Za-z0-9_-]{1,100}$/.test(id)))].slice(0,4);
}
function readCompareIds() {
  try{return normalizeCompareIds(JSON.parse(sessionStorage.getItem('trade-compare')||'[]'));}
  catch{return [];}
}
function writeCompareIds(ids) {
  try{sessionStorage.setItem('trade-compare',JSON.stringify(normalizeCompareIds(ids)));}
  catch{const error=Error('Your browser cannot save this comparison.');error.storage=true;throw error;}
}
async function loadComparison(ids) {
  const records=await Promise.all(normalizeCompareIds(ids).map(async id=>{
    try{return await read('/autolink/public/vehicles/'+encodeURIComponent(id));}
    catch(error){if(error.status===404)return null;throw error;}
  }));
  return records.filter(Boolean);
}
function comparisonValue(value,translate=false) {
  if(value===null||value===undefined||value==='')return esc(tr('Not specified'));
  return esc(translate?tr(String(value)):value);
}
async function compare() {
  const current=navigationId,ids=readCompareIds();
  const vehicles=await loadComparison(ids);assertNavigation(current);
  let storageNotice='';
  const kept=vehicles.map(vehicle=>vehicle.id);
  if(ids.join('|')!==kept.join('|')){
    try{writeCompareIds(kept);}catch{storageNotice=tr('Your browser cannot save this comparison.');}
  }
  const references=vehicles.length?await modelCatalog():[];assertNavigation(current);
  const modelById=new Map(references.map(model=>[model.id,model]));
  const fields=[['Brand','brand'],['Model','model'],['Trim','trim'],['Year','model_year'],
    ['Energy type','energy_type'],['Steering','steering'],['Condition','vehicle_condition'],
    ['Price','price_minor'],['Incoterm','incoterm'],['MOQ','moq'],['Stock','stock'],
    ['Export port','origin_port'],['Lead time','lead_time'],['Price valid until','valid_until'],['Supplier','supplier_name']];
  const specifications=[['Body type','bodyType'],['Dimensions','dimensions'],['Power','power'],['Battery','battery'],['Range','range']];
  shell(`<div class="trade-intro"><div><span class="eyebrow">${esc(tr('VEHICLE COMPARISON'))}</span><h1>${esc(tr('Compare supplier listings.'))}</h1><p>${esc(tr('Compare up to four approved offers. Supplier confirmation is still required.'))}</p></div><div class="trade-detail-actions">${link('/trade/vehicles',tr('Add vehicles'),true)}${vehicles.length?`<button class="btn secondary" data-action="clear-compare">${esc(tr('Clear comparison'))}</button>`:''}</div></div><div id="trade-message" role="status" aria-live="polite">${ids.length>vehicles.length?`<p class="trade-note">${esc(tr('Unavailable listings were removed from this comparison.'))}</p>`:''}${storageNotice?`<p class="trade-note">${esc(storageNotice)}</p>`:''}</div>${vehicles.length?`<div class="compare-wrap" role="region" aria-label="${esc(tr('Vehicle comparison'))}" tabindex="0"><table class="compare-table"><thead><tr><th scope="col">${esc(tr('Details'))}</th>${vehicles.map(v=>`<th scope="col"><a href="/trade/vehicles/${esc(encodeURIComponent(v.id))}">${esc(v.brand)} ${esc(v.model)}</a><p>${comparisonValue(v.trim)}</p><button class="btn secondary" data-action="remove-compare" data-id="${esc(v.id)}" aria-label="${esc(tr('Remove {vehicle}').replace('{vehicle}',v.brand+' '+v.model))}">${esc(tr('Remove'))}</button></th>`).join('')}</tr></thead><tbody>${fields.map(([label,key])=>`<tr><th scope="row">${esc(tr(label))}</th>${vehicles.map(v=>`<td>${key==='price_minor'?usd(v[key],v.currency):key==='vehicle_condition'?esc(conditionLabel(v[key])):comparisonValue(v[key],key==='energy_type')}</td>`).join('')}</tr>`).join('')}<tr class="compare-reference"><th colspan="${vehicles.length+1}" scope="colgroup">${esc(tr('Model reference specifications'))}<p>${esc(tr('These specifications describe the reference model, not the exact supplier trim. Confirm specifications with the supplier.'))}</p></th></tr>${specifications.map(([label,key])=>`<tr><th scope="row">${esc(tr(label))}</th>${vehicles.map(v=>{const m=modelById.get(v.model_id);return `<td>${comparisonValue(key==='bodyType'?m?.bodyType:m?.specifications?.[key],key==='bodyType')}</td>`;}).join('')}</tr>`).join('')}<tr><th scope="row">${esc(tr('Details'))}</th>${vehicles.map(v=>`<td>${link('/trade/vehicles/'+encodeURIComponent(v.id),tr('View'),true)}</td>`).join('')}</tr></tbody></table></div>`:`<div class="empty"><strong>${esc(tr('No vehicles selected.'))}</strong><p>${esc(tr('Open a listing and choose Compare.'))}</p>${link('/trade/vehicles',tr('Add vehicles'),true)}</div>`}`,'Compare Vehicles | AUTOLINK');
}

function message(text,error=false) { const el=document.querySelector('#trade-message');if(el){el.className=error?'alert error':'alert';el.textContent=text;} }
document.addEventListener('click',async event=>{
  const el=event.target.closest('[data-action]');if(!el)return;
  const action=el.dataset.action,current=navigationId;
  if(action==='quote'){if(!hasBuyerCapability(me)){location.href=loginLink();return;}document.querySelector('#inquiry-panel').hidden=false;document.querySelector('#inquiry-panel').scrollIntoView({behavior:'smooth'});return;}
  if(action==='contact-supplier'){if(!me){location.href=loginLink();return;}if(currentListing)navigateTrade('/trade/suppliers/'+encodeURIComponent(currentListing.supplier_id)+'#supplier-contact');return;}
  if(action==='share'){try{await navigator.clipboard.writeText(location.href);if(current===navigationId)message(tr("Link copied."));}catch{if(current===navigationId)message(tr("Copy the address from your browser."),true);}return;}
  if(['compare','remove-compare','clear-compare'].includes(action)){
    try{
      let ids=readCompareIds();
      if(action==='compare'){
        if(!currentListing)return;
        if(!ids.includes(currentListing.id)&&ids.length>=4){message(tr('You can compare up to four listings.'),true);return;}
        if(!ids.includes(currentListing.id))ids.push(currentListing.id);
      }else ids=action==='clear-compare'?[]:ids.filter(id=>id!==el.dataset.id);
      writeCompareIds(ids);
      if(action==='compare')navigateTrade('/trade/compare');else await start({scroll:[window.scrollX,window.scrollY]});
    }catch(error){if(current===navigationId)message(tr(error.storage?'Your browser cannot save this comparison.':'Unable to load comparison. Please try again.'),true);}
    return;
  }
  if(!hasBuyerCapability(me)){location.href=loginLink();return;}
  try{
    if(action==='save'&&currentListing){await read('/autolink/buyer/saved-listings','POST',{listingId:currentListing.id});if(current===navigationId)message(tr("Vehicle saved to your Buyer Center."));}
    if(action==='save-supplier'&&currentSupplier){await read('/autolink/buyer/saved-suppliers','POST',{supplierId:currentSupplier.id});if(current===navigationId)message(tr("Supplier saved to your Buyer Center."));}
  }catch(error){if(current===navigationId)message(tr(error.message),true);}
});
document.addEventListener('submit',async event=>{
  if(event.target.id==='model-search'){event.preventDefault();const q=new URLSearchParams(new FormData(event.target));for(const [k,v] of [...q])if(!v.trim())q.delete(k);const lang=new URLSearchParams(location.search).get('lang');if(lang)q.set('lang',lang);navigateTrade('/trade/models?'+q);return;}
  if(event.target.id==='trade-search'){
    event.preventDefault();const p=new URLSearchParams(new FormData(event.target));
    for(const [name,key] of [['minPrice','minPriceMinor'],['maxPrice','maxPriceMinor']]){
      const value=p.get(name);p.delete(name);if(value)p.set(key,String(Math.round(Number(value)*100)));
    }
    for(const [k,v] of [...p])if(!v.trim())p.delete(k);
    const lang=new URLSearchParams(location.search).get('lang');if(lang)p.set('lang',lang);
    navigateTrade('/trade/vehicles?'+p);return;
  }
  if(event.target.id==='inquiry-form'){
    event.preventDefault();if(!hasBuyerCapability(me)){location.href=loginLink();return;}
    const current=navigationId,listing=currentListing;
    if(!listing)return;
    const button=event.target.querySelector('button[type=submit]');if(button.disabled)return;button.disabled=true;
    const values=Object.fromEntries(new FormData(event.target));
    const target=values.targetPrice?Math.round(Number(values.targetPrice)*100):null;
    try{
      const inquiry=await read('/autolink/buyer/inquiries','POST',{listingId:listing.id,quantity:Number(values.quantity),destinationCountry:values.destinationCountry,destinationPort:values.destinationPort,incoterm:values.incoterm,targetPriceMinor:target,message:values.message});
      if(current===navigationId)location.href='/buyer/inquiries/'+encodeURIComponent(inquiry.id);
    }catch(error){if(current===navigationId)message(tr(error.message),true);button.disabled=false;}
  }
});
async function start({scroll}={}){
  const current=++navigationId;readController?.abort();readController=new AbortController();
  navigationUrl=location.pathname+location.search;
  me=null;currentListing=null;currentSupplier=null;
  if(root.dataset.ssr==='true')delete root.dataset.ssr;
  else shell(`<div class="loading-screen" role="status" aria-live="polite">${esc(tr('Loading…'))}</div>`);
  let account=null;try{account=await read('/autolink/me');}catch{}
  if(current!==navigationId)return;me=account;
  try{
    const parts=location.pathname.split('/').filter(Boolean);
    if(parts[1]==='models'&&parts[2]) await modelDetail(decodeURIComponent(parts[2]));
    else if(parts[1]==='models') await models();
    else if(parts[1]==='brands'&&parts[2]) await brandDetail(decodeURIComponent(parts[2]));
    else if(parts[1]==='brands') await brands();
    else if(parts[1]==='vehicles'&&parts[2]) await vehicleDetail(parts[2]);
    else if(parts[1]==='vehicles') await vehicles();
    else if(parts[1]==='suppliers'&&parts[2]) await supplierDetail(parts[2]);
    else if(parts[1]==='suppliers') await suppliers();
    else if(parts[1]==='compare') await compare();
    else if(!parts[1]) await vehicles();
    else {shell(`<h1>${esc(tr("404 · Page not found"))}</h1>${link('/trade/vehicles',tr("Back to vehicles"))}`,'Page Not Found | AUTOLINK');window.businessSEO?.page('error');}
    if(current===navigationId){navigationUrl=location.pathname+location.search;restoreTradeScroll(scroll);}
  }catch(error){if(current===navigationId&&error.name!=='AbortError')fail(error);}
}
function internalTradeUrl(href){
  const url=new URL(href,location.href);
  if(url.origin!==location.origin||!/^\/trade(?:\/(?:vehicles|models|brands|suppliers|compare)(?:\/[^/]+)?)?\/?$/.test(url.pathname))return null;
  if(/\.(?:js|mjs|css|json|png|webp|jpe?g|pdf|svg)$/i.test(url.pathname))return null;
  const lang=url.searchParams.get('lang');
  if(lang&&((lang==='zh-CN'?'zh':lang)!==window.businessI18n.language))return null;
  return url;
}
function restoreTradeScroll(scroll){
  if(scroll===undefined&&!location.hash)return;
  const current=navigationId;
  requestAnimationFrame(()=>{
    if(current!==navigationId)return;
    let target;
    try{target=location.hash?document.getElementById(decodeURIComponent(location.hash.slice(1))):null;}catch{}
    if(target){target.scrollIntoView();return;}
    if(scroll)window.scrollTo(scroll[0],scroll[1]);
  });
}
function navigateTrade(href){
  const url=internalTradeUrl(href);if(!url){location.assign(href);return;}
  history.replaceState({...history.state,tradeScroll:[window.scrollX,window.scrollY]},'',location.href);
  history.pushState({tradeScroll:[0,0]},'',url.pathname+url.search+url.hash);
  void start({scroll:[0,0]});
}
document.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const anchor=event.target.closest('a[href]');
  if(!anchor||anchor.hasAttribute('download')||(anchor.target&&anchor.target!=='_self'))return;
  const url=internalTradeUrl(anchor.href);if(!url)return;
  if(url.pathname===location.pathname&&url.search===location.search&&url.hash)return;
  event.preventDefault();navigateTrade(url.href);
});
window.addEventListener('popstate',event=>{
  if(navigationUrl===location.pathname+location.search){restoreTradeScroll(event.state?.tradeScroll);return;}
  void start({scroll:event.state?.tradeScroll||[0,0]});
});
window.addEventListener('pageshow',event=>{if(event.persisted)void start({scroll:[window.scrollX,window.scrollY]});});
for(const event of ['trade-session-changed','trade-session-expired'])window.addEventListener(event,()=>{void start({scroll:[window.scrollX,window.scrollY]});});
start();

async function brands(){const current=navigationId,rows=await read('/autolink/public/brands');assertNavigation(current);shell(`<div class="trade-intro"><div><span class="eyebrow">${esc(tr("BRAND DIRECTORY"))}</span><h1>${esc(tr("Explore vehicle brands."))}</h1><p>${esc(tr("Research models, then find reviewed listings from approved suppliers."))}</p></div></div><div class="trade-grid">${rows.map(b=>`<article class="trade-card"><div class="trade-card-body"><div class="trade-brand-directory-mark">${brandMark(b.logo,b.name)}</div><h2>${esc(b.name)}</h2><p>${esc(b.country||'')}</p><small>${Number(b.model_count)} ${esc(tr("active model references"))}</small>${link('/trade/brands/'+encodeURIComponent(b.id),tr("Explore brand"))}</div></article>`).join('')}</div>`,'Vehicle Brands for Export | AUTOLINK');}
async function brandDetail(id){const current=navigationId,b=await read('/autolink/public/brands/'+encodeURIComponent(id));assertNavigation(current);const stock=await read('/autolink/public/vehicles?limit=25&brand='+encodeURIComponent(b.name));assertNavigation(current);const types=[...new Set(b.models.map(m=>m.bodyType).filter(Boolean))];const suppliers=[...new Map(stock.map(v=>[v.supplier_id,{id:v.supplier_id,name:v.supplier_name}])).values()];shell(`<div class="trade-breadcrumb"><a href="/trade/models">${esc(tr("Model references"))}</a><a href="/trade/brands">${esc(tr("Brands"))}</a> / ${esc(b.name)}</div><div class="trade-intro"><div><span class="eyebrow">${esc(tr("BRAND MODEL REFERENCE"))}</span><div class="trade-brand-heading">${brandMark(b.logo,b.name)}<h1>${esc(b.name)}</h1></div><p>${esc(b.overview||tr('Browse model references and reviewed supplier offers.'))}</p><p>${esc(b.country)}${types.length?' · '+esc(types.map(tr).join(' / ')):''}</p></div>${link('/trade/vehicles?brand='+encodeURIComponent(b.name),tr("All supplier offers"),true)}</div><section class="panel"><div class="panel-head"><h2>${esc(tr("Model references"))}</h2></div>${b.models.length?`<div class="trade-grid">${b.models.map(m=>`<article class="trade-card"><img loading="lazy" src="${esc(m.image||'/favicon.svg')}" alt="${esc(m.model)}"><div class="trade-card-body"><div class="trade-model-brand">${brandMark(m.brandLogo,b.name)}<span>${esc(b.name)}</span></div><h2>${esc(m.model)}</h2><p>${esc(m.year||tr("Year unspecified"))} · ${esc(tr(m.energy))} · ${esc(tr(m.bodyType))}</p>${link('/trade/models/'+encodeURIComponent(m.id),tr("View model"))}</div></article>`).join('')}</div>`:`<div class="empty">${esc(tr('No active model references.'))}</div>`}</section><section class="panel"><div class="panel-head"><h2>${esc(tr("Approved supplier offers"))}</h2></div>${stock.length?`<div class="trade-grid">${stock.map(card).join('')}</div>`:`<div class="empty">${esc(tr('No approved supplier offers for this brand yet.'))}</div>`}</section><section class="panel"><div class="panel-head"><h2>${esc(tr("Suppliers with listed stock"))}</h2></div>${suppliers.length?suppliers.map(s=>link('/trade/suppliers/'+encodeURIComponent(s.id),s.name,true)).join(' '):`<div class="empty">${esc(tr('Suppliers appear here when approved stock is published.'))}</div>`}</section><p class="trade-note">${esc(tr("Model references do not prove stock or availability. Confirm exact specifications and trade terms directly with the supplier."))}</p>`,`${b.name} Vehicles for Export from China | AUTOLINK`);window.businessSEO?.page('brand',b);}
