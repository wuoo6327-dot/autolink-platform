const tr = value => window.businessI18n.text(value);
const root = document.querySelector('#app');
const isZh = window.businessI18n.language === 'zh';
const t = (zh, en) => window.businessI18n.translate(zh,en);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const localPreview = ['127.0.0.1', 'localhost'].includes(location.hostname) && new URLSearchParams(location.search).has('preview');
const dateTime = ts => ts ? new Intl.DateTimeFormat(window.businessI18n.locale,{dateStyle:'medium',timeStyle:'short'}).format(new Date(ts*1000)) : '—';
const date = ts => ts ? new Intl.DateTimeFormat(window.businessI18n.locale, {year:'numeric',month:'short',day:'numeric'}).format(new Date(ts * 1000)) : '—';
const api = async (path, method='GET', body) => {
  let response;const epoch=navigationId,controller=method==='GET'?readController:null;
  const signal=controller?AbortSignal.any([controller.signal,AbortSignal.timeout(15000)]):AbortSignal.timeout(15000);
  try {
  if (localPreview) throw Error(t('预览模式不保存数据。','Preview mode does not save data.'));
  response = await fetch(path, {method, credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:body === undefined ? undefined : JSON.stringify(body), signal});
  const payload = await response.json();
  if(method==='GET'&&(epoch!==navigationId||controller?.signal.aborted))throw new DOMException('Navigation changed','AbortError');
  if (!response.ok || payload.code !== 200) throw Object.assign(Error(typeof payload?.msg==='string'?payload.msg:'Request failed.'),{status:response.ok?Number(payload?.code):response.status});
  return payload.data;

  } catch(error) { if(method==='GET'&&(epoch!==navigationId||controller?.signal.aborted))throw new DOMException('Navigation changed','AbortError');throw window.businessI18n.apiError?.(error,response?.status) || error; }
};
const empty = (title, body, action='') => `<div class="empty"><strong>${esc(title)}</strong><p>${esc(body)}</p>${action}</div>`;
const link = (href, label, secondary=false) => `<a class="button-link${secondary?' secondary':''}" href="${esc(href)}">${esc(label)}</a>`;
const pageTitle = (eyebrow, zh, en, descZh, descEn, action='') => `<div class="page-top"><div><span class="eyebrow">${esc(tr(eyebrow))}</span><h1>${esc(t(zh,en))}</h1><p>${esc(t(descZh,descEn))}</p></div>${action}</div>`;
const panel = (title, content, more='') => `<section class="panel"><div class="panel-head"><h2>${esc(title)}</h2>${more}</div>${content}</section>`;
const vehicleRow = (v, actions='') => `<div class="row"><img src="${esc(v.image || '/favicon.svg')}" alt=""><div class="row-main"><strong>${esc(v.brand)} ${esc(v.model)}</strong><small>${esc([v.year,v.bodyType,v.energy].filter(Boolean).join(' · '))} · ${v.priceLocked?esc(tr('Members only')):v.supplier_id&&v.price_minor!=null?`${esc(v.incoterm||'')} ${esc(v.origin_port||'')} · ${quoteMoney(v.price_minor,v.currency)}`:t('供应商报价待确认','Supplier quote pending')}</small></div><div class="row-actions">${actions || link(v.url,t('查看车型','View model'),true)}</div></div>`;
const nav = [
  ['','采购概览','Overview'],['inquiries','我的询价','My Inquiries'],['quotes','我的报价','My Quotes'],
  ['saved-listings','收藏车源','Saved Listings'],['history','浏览历史','Recently Viewed'],['favorites','收藏车型','Saved Models'],
  ['compare','车型对比','Compare'],['suppliers','关注供应商','Saved Suppliers'],['requests','采购需求','Purchase Requests'],
  ['notifications','通知','Notifications'],['messages','消息中心','Messages'],['membership','会员中心','Membership'],['company','买家企业资料','Buyer company profile'],['security','账号与安全','Account & Security']
];
let user = null, catalog = [], catalogAliases = new Map(), catalogAliasesLoaded=false, currentSection = '', renderedData = null;
let codeRetryUntil = 0, codeSending = false;
let inquiryFilterVersion = 0, inquiryFilterTimer;
let navigationId=0,readController=null,catalogLoaded=false;
function beginBuyerRead(){readController?.abort();readController=new AbortController();}
function beginBuyerNavigation(){navigationId++;beginBuyerRead();inquiryFilterVersion++;clearTimeout(inquiryFilterTimer);renderedData=null;return navigationId;}
const needsBuyerCatalog=()=>['catalog','requests'].includes(location.pathname.split('/')[2]);
async function loadBuyerCatalog(epoch){
  if(catalogLoaded){if(location.pathname==='/buyer/catalog')await loadCatalogAliases(epoch);return;}
  try{const rows=localPreview?[]:await api('/autolink/public/models');if(epoch!==navigationId)return;catalog=Array.isArray(rows)?rows:[];catalogLoaded=true;
    if(location.pathname==='/buyer/catalog')await loadCatalogAliases(epoch);
  }
  catch(error){if(epoch!==navigationId||error.name==='AbortError')throw error;catalog=[];}
}
async function loadCatalogAliases(epoch){
  if(catalogAliasesLoaded)return;
  const reviews=await fetch('/locales/seo-model-en-reviewed.json',{cache:'force-cache'}).then(r=>r.ok?r.json():{}).catch(()=>({}));
  const {reviewedAliases}=await import('/trade/model-directory.mjs?v=20261013-round14');
  if(epoch===navigationId){catalogAliases=reviewedAliases(reviews);catalogAliasesLoaded=true;}
}
const isJoinPage = () => location.pathname === '/buyer/register';
const afterLogin = () => {
  const path=new URLSearchParams(location.search).get('returnTo');
  if(!path?.startsWith('/')||path.startsWith('//')||/[\\\x00-\x1f\x7f]/.test(path))return '/buyer';
  try{const url=new URL(path,location.origin);return url.origin===location.origin?url.pathname+url.search+url.hash:'/buyer';}catch{return '/buyer';}
};
const buyerAuthUrl = register => {
  const route=register?'/buyer/register':'/buyer/login';
  const destination=afterLogin();
  return destination==='/buyer'?route:route+'?returnTo='+encodeURIComponent(destination);
};

function supplierContact(contact,locked=false) {
  if(locked)return `<p>${esc(tr("Members only"))}</p>${link("/membership",tr("Membership"),true)}`;
  if(!contact) return '';
  return `<div class="supplier-contact"><p><strong>${esc(contact.contact_name||contact.company_name)}</strong></p><p>${t('邮箱','Email')}: ${esc(contact.email)}</p><p>${t('电话','Phone')}: ${esc(contact.contact_phone||'—')}</p></div>`;
}
function shell(section, contents) {
  const menu = nav.map(([slug,zh,en]) => `<a href="/buyer${slug?'/'+slug:''}" class="${section===slug?'active':''}" ${section===slug?'aria-current="page"':''}>${esc(t(zh,en))}</a>`).join('');
  root.innerHTML = `<header class="site-head"><div class="site-head-inner"><a class="brand" href="/">AUTOLINK<i>▪</i></a><div class="head-right">${window.businessI18n.languageControl()}<span>${esc(user?.nickName || user?.companyName || user?.username || t('预览模式','Preview mode'))}</span><a href="/trade/vehicles">${t('真实车源','Supplier Vehicles')}</a><a href="/">${t('返回网站','Website')}</a></div></div></header><div class="workspace"><aside class="side" id="buyer-sidebar"><div class="side-title">${esc(tr("AUTOLINK · BUYER CENTER"))}</div>${menu}<div class="side-bottom"><a href="/trade/vehicles">${t('浏览车源','Supplier Vehicles')}</a><a href="/">${t('返回网站','Back to Website')}</a><button data-action="logout">${t('退出登录','Log Out')}</button></div></aside><main class="content"><button class="btn secondary mobile-menu" data-action="menu" aria-controls="buyer-sidebar" aria-expanded="false">☰ ${t('菜单','Menu')}</button><div id="buyer-content">${contents}</div></main></div>`;
}
function setContent(html) { document.querySelector('#buyer-content').innerHTML = html; }
function loading(section) { shell(section, `<div class="skeleton"></div><div class="skeleton" style="margin-top:20px"></div>`); }
function error(section, e, retry) { e=window.businessI18n.apiError?.(e)||e; shell(section, `<div class="alert error" role="alert">${esc(e.message)}</div>${link(retry || location.pathname,t('重试','Retry'))}`); }
function buyerRoleSelector(register){
  const entry=window.AUTOLINK_AUTH_ENTRY;if(!entry)return '';
  const language=window.businessI18n.language;
  const icons={buyer:'<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a17 17 0 0 1 0 18 17 17 0 0 1 0-18Z"/>',supplier:'<path d="M4 21V7h6V3h10v18H4ZM10 7v14M14 7h2M14 11h2M14 15h2M6 11h1M6 15h1"/>'};
  return `<nav class="buyer-role-selector" aria-label="${esc(entry.text(language,'label'))}">${['buyer','supplier'].map(kind=>`<a class="buyer-role-option${kind==='buyer'?' active':''}" data-auth-kind="${kind}" href="${esc(kind==='buyer'?buyerAuthUrl(register):entry.url(kind,{register}))}" ${kind==='buyer'?'aria-current="page"':''}><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">${icons[kind]}</svg><span><strong>${esc(entry.text(language,kind))}</strong><small>${esc(entry.text(language,kind+'Hint'))}</small></span></a>`).join('')}</nav>`;
}
function renderLogin(message='') {
  const joining = isJoinPage();
  document.title = `${t(joining ? '加入 AUTOLINK' : '买家登录', joining ? 'Join AUTOLINK' : 'Buyer sign in')} · AUTOLINK`;
  root.innerHTML = `<div class="login-shell"><aside class="login-hero"><a class="brand" href="/" style="color:white">AUTOLINK<i>▪</i></a><div><span class="eyebrow">${esc(tr("AUTOLINK · BUYER CENTER"))}</span><h1>${t('连接中国车源，管理全球采购。','Source China. Manage global opportunities.')}</h1><p>${t('收藏车型、发起询价、跟进供应商回复。','Save models, send inquiries and follow supplier replies.')}</p></div><small>${t('买家采购工作台','A sourcing workspace for global buyers')}</small></aside><main class="login-main"><div class="login-card"><h2>${t(joining?'创建买家账号':'买家登录',joining?'Create your buyer account':'Buyer sign in')}</h2><p>${esc(tr(joining?'Verify your email to create an account and set your password.':'Sign in with a password, email code or Google.'))}</p>${buyerRoleSelector(joining)}${message?`<div class="alert error" role="alert">${esc(message)}</div>`:''}${joining?'':`<div class="buyer-login-tabs"><button type="button" class="btn secondary" data-login-tab="password">${t('密码登录','Password Login')}</button><button type="button" class="btn secondary" data-login-tab="code">${t('验证码登录','Email Code Login')}</button></div><form id="buyer-password-form"><label class="field">${t('邮箱','Email')}<input name="email" type="email" required autocomplete="email"></label><label class="field">${t('密码','Password')}<input name="password" type="password" required autocomplete="current-password"></label><label class="consent"><input name="remember" type="checkbox"><span>${t('保持登录','Keep me signed in')}</span></label><button class="btn buyer-continue" type="submit">${t('登录','Log in')}</button><p>${link('/merchant/login?reset=1',t('忘记密码','Forgot password'),true)}</p><div id="buyer-password-status" role="status"></div></form>`}<form id="buyer-email-form" ${joining?'':'hidden'}><label class="field">${t('邮箱','Email')}<input name="email" type="email" required autocomplete="email" placeholder="${esc(tr("you@company.com"))}"></label>${joining?registrationFields():''}<label class="field">${t('验证码','Verification code')}<span class="buyer-code-row"><input name="code" type="text" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" required autocomplete="one-time-code" placeholder="000000"><button id="buyer-send-code" type="button">${t('获取验证码','Send code')}</button></span></label><label class="consent"><input id="buyer-consent" type="checkbox"><span>${t('新账号注册时，我同意','For a new account, I agree to the')} <a href="/terms" target="_blank">${t('服务条款','Terms')}</a> ${t('和','and')} <a href="/privacy" target="_blank">${t('隐私政策','Privacy Policy')}</a></span></label><div id="buyer-code-status" class="notice" role="status" aria-live="polite"></div><button class="btn buyer-continue" type="submit">${joining?tr('Create account'):t('登录 / 注册','Continue')}</button></form><div class="buyer-divider">${t('或使用 Google','or continue with Google')}</div><label class="field">${t('企业名称（可选）','Company name (optional)')}<input id="buyer-company" maxlength="160" autocomplete="organization"></label><div class="google-button" id="google-button">${t('正在加载 Google 登录…','Loading Google sign-in…')}</div><p class="notice">${t('商家和供应商请走独立的企业申请流程。','Merchants and suppliers use the separate business application flow.')}</p><div class="buyer-login-links">${link('/supplier/application',t('申请成为商家 / 供应商','Apply as a merchant / supplier'),true)}${link(buyerAuthUrl(true),t('邮箱验证码快速注册','Register with email code'),true)}</div></div></main></div>`;
  updateCodeButton();
  if (!localPreview) setupGoogle();
}
function registrationFields(){
  return `<label class="field">${esc(tr('Country / Region'))}<input name="country" required minlength="2" maxlength="120" autocomplete="country-name"></label><label class="field">${esc(tr('Password'))}<input name="password" type="password" required minlength="8" maxlength="128" autocomplete="new-password"><small>${esc(tr('Password must be 8 to 128 characters.'))}</small></label>`;
}
function codeStatus(message, error=false) {
  const box = document.querySelector('#buyer-code-status');
  if (box) { box.textContent = message; box.classList.toggle('code-error', error); }
}
function updateCodeButton() {
  const button = document.querySelector('#buyer-send-code');
  if (!button) return;
  const remaining = Math.max(0, Math.ceil((codeRetryUntil - Date.now()) / 1000));
  button.disabled = codeSending || remaining > 0 || !document.querySelector('#buyer-consent')?.checked;
  button.textContent = codeSending ? t('发送中…', 'Sending…') : remaining ? `${remaining}s` : t('获取验证码', 'Send code');
}
setInterval(updateCodeButton, 1000);
async function setupGoogle() {
  try {
    const googleLocale=window.businessI18n.language==='zh'?'zh_CN':window.businessI18n.language;
    const challengeRes = await fetch('/autolink/auth/google/challenge',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const challenge = await challengeRes.json();
    if (!challengeRes.ok || !challenge.data?.clientId) throw Error(challenge.msg || 'Google is unavailable');
    if (!window.google?.accounts?.id) await new Promise((resolve,reject)=>{const s=document.createElement('script');s.src='https://accounts.google.com/gsi/client?hl='+encodeURIComponent(googleLocale);s.onload=resolve;s.onerror=reject;document.head.append(s)});
    google.accounts.id.initialize({client_id:challenge.data.clientId,nonce:challenge.data.nonce,auto_select:false,callback:async result=>{
      const companyName=document.querySelector('#buyer-company')?.value.trim() || '';
      const consent=!!document.querySelector('#buyer-consent')?.checked;
      try {
        const r=await fetch('/autolink/auth/google/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({credential:result.credential,nonce:challenge.data.nonce,role:'BUYER',companyName,consent,language:window.businessI18n.language})});
        const p=await r.json();
        if (!r.ok || p.code!==200) throw Error(p.msg || t('登录失败','Sign-in failed'));
        if (p.data.registrationRequired) throw Error(t('请同意条款，然后再次使用 Google 注册。','Accept the terms, then continue with Google again.'));
        location.href=p.data.role==='PLATFORM_ADMIN'?'/admin':['MERCHANT','SUPPLIER'].includes(p.data.role)?'/supplier':afterLogin();
      } catch(e) { renderLogin(e.message); }
    }});
    const target=document.querySelector('#google-button');
    target.replaceChildren();
    google.accounts.id.renderButton(target,{theme:'outline',size:'large',text:'continue_with',width:260,locale:googleLocale});
  } catch(e) { const target=document.querySelector('#google-button'); if(target) target.textContent=t('Google 登录暂时不可用，请稍后重试。','Google sign-in is unavailable. Please retry.'); }
}

function overview(data) {
  const m=data.membership, c=data.counts;
  const status=m.status==='ACTIVE'?`${tr('Paid membership')} · ${t('有效期至','Valid until')} ${date(m.endAt)}`:m.status==='EXPIRED'?t('会员已到期','Membership expired'):t('免费账号 · 浏览更多采购功能','Free Account · Explore more sourcing features');
  const cards=[['savedVehicles','收藏车辆','Saved Vehicles','已保存的采购候选车型','Saved sourcing candidates'],['activeInquiries','进行中询价','Active Inquiries','等待或沟通中的询价','Waiting or in discussion'],['quotes','收到的报价','Quotations','供应商发来的报价','Quotes sent by suppliers'],['savedSuppliers','关注供应商','Saved Suppliers','已保存的供应商','Saved suppliers']];
  const stats=cards.map(([key,zh,en,dz,de])=>`<article class="card stat"><h2>${t(zh,en)}</h2><b>${Number(c[key]||0)}</b><p>${t(dz,de)}</p></article>`).join('');
  const todo=[];
  if(data.unreadNotifications) todo.push(link('/buyer/notifications',t('查看未读通知','View unread notifications')+' ('+Number(data.unreadNotifications)+')'));
  if(c.supplierReplies) todo.push(link('/buyer/messages',t('查看新的供应商回复','View supplier replies')));
  if(!data.profileComplete) todo.push(link('/buyer/company',t('完善企业资料','Complete company profile'),true));
  if(m.status==='ACTIVE' && m.endAt && m.endAt-Date.now()/1000<14*86400) todo.push(link('/buyer/membership',t('会员即将到期','Membership expires soon'),true));
  const recent=data.recentInquiries.length?data.recentInquiries.map(inquiryRow).join(''):empty(t('暂无询价','No inquiries yet'),t('从车型目录发起第一条采购询价。','Start an inquiry from a vehicle model.'),link('/buyer/catalog',t('浏览车型','Browse models')));
  const candidates=[...(data.savedListings||[]).map(v=>({...v,year:v.model_year,energy:v.energy_type,url:'/trade/vehicles/'+encodeURIComponent(v.id)})),...data.savedVehicles];
  const saved=candidates.length?candidates.slice(0,4).map(v=>vehicleRow(v,link(v.url,t('查看详情','View details'),true))).join(''):empty(t('还没有收藏车辆','No saved vehicles yet'),t('浏览车型并建立采购候选清单。','Browse models to build your shortlist.'),link('/buyer/catalog',t('浏览车型','Browse models')));
  return pageTitle('AUTOLINK · BUYER CENTER','采购中心','Buyer Center','收藏车辆、管理询价并连接中国汽车供应商。','Save vehicles, manage inquiries and connect with Chinese automotive suppliers.',link('/trade/vehicles',t('浏览车源','Browse Vehicles')))+`<div class="status"><strong>${esc(data.displayName||data.companyName||user?.email||'')}</strong><span>${esc(data.companyName||'')} · ${esc(data.country||'')} · ${data.emailVerified?t('邮箱已验证','Email verified'):t('邮箱未验证','Email not verified')}</span><span>${esc(status)}</span></div><div class="stats">${stats}</div><div class="two-cols">${panel(t('最近询价','Recent Inquiries'),`<div class="list">${recent}</div>`,link('/buyer/inquiries',t('查看全部','View all'),true))}${panel(t('待办事项','Action Required'),todo.length?`<div class="list">${todo.join('')}</div>`:empty(t('暂无待处理事项','You’re all caught up.'),''))}</div>${panel(t('最近报价','Recent Quotes'),(data.recentQuotes||[]).length?`<div class="list">${data.recentQuotes.map(quoteRow).join('')}</div>`:empty(t('暂无报价','No quotes yet'),''),link('/buyer/quotes',t('查看全部','View all'),true))}${panel(t('收藏车辆','Saved Vehicles'),`<div class="list">${saved}</div>`,link('/buyer/saved-listings',t('查看全部','View all'),true))}<section class="purchase-cta"><h2>${t('发布采购需求','Post a Purchase Request')}</h2><p>${t('告诉供应商你正在寻找的车型、数量和目标市场。','Describe the models, quantities and market you source for.')}</p>${link('/buyer/requests',t('创建需求','Create request'))}</section>`;
}
function inquiryRow(item) {
  const v=item.vehicle||{};
  return `<div class="row"><img src="${esc(v.image||'/favicon.svg')}" alt=""><div class="row-main"><strong>${esc(v.brand||'')} ${esc(v.model||'')}</strong><small>${esc(item.id)} · ${esc(tr('Quantity'))} ${Number(item.quantity||0)} · ${esc(item.supplier_name||t('供应商待匹配','Supplier pending'))} · ${esc(inquiryStatus(item.status))}${item.unread_replies?` · <b>${t('新回复','New Reply')}</b>`:''}</small><small>${esc(tr('Destination country'))} ${esc(item.destination_country||'—')} · ${esc(tr('Destination port'))} ${esc(item.destination_port||'—')} · ${esc(tr('Incoterm'))} ${esc(item.trade_term||'—')}</small><small>${t('发起','Created')} ${dateTime(item.created_at)} · ${t('更新','Updated')} ${dateTime(item.updated_at)}</small></div>${link(`/buyer/inquiries/${encodeURIComponent(item.id)}`,t('查看询价','View Inquiry'),true)}</div>`;
}
function renderInquiries(data) {
  const params=new URLSearchParams(location.search),chosen=params.get('vehicle'),selected=params.get('status')||'ALL',keyword=params.get('keyword')||'';
  const help=chosen?panel(t('请选择已审核车源','Choose an approved supplier listing'),`<p>${t('车型资料仅供参考。正式询盘必须针对具体供应商已审核的车源，才能送达商家。','Model data is a reference. Choose an approved supplier listing so the inquiry reaches the seller.')}</p>${link('/trade/vehicles?keyword='+encodeURIComponent(chosen),t('查看供应商车源','Find supplier listings'))}`):'';
  return pageTitle('AUTOLINK · BUYER CENTER','我的询价','My Inquiries','查看实际发送给供应商的询盘和回复。','Track inquiries delivered to suppliers.',link('/trade/vehicles',t('浏览真实车源','Browse supplier vehicles')))+help+panel(t('询价记录','Inquiry Records'),`<div class="tabs" id="inquiry-tabs">${[['ALL','全部','All'],['SUBMITTED','已提交','Submitted'],['VIEWED','已查看','Viewed'],['CONTACTED','已联系','Contacted'],['QUOTED','已报价','Quoted'],['NEGOTIATING','洽谈中','Negotiating'],['CLOSED','已关闭','Closed']].map(([x,z,e])=>`<button data-filter="${x}" aria-selected="${x===selected}">${t(z,e)}</button>`).join('')}</div><div class="filters"><input id="inquiry-search" type="search" maxlength="160" value="${esc(keyword)}" placeholder="${t('搜索车型、供应商、询价编号','Search model, supplier or inquiry ID')}"></div><div id="inquiry-list" class="list">${data.length?data.map(inquiryRow).join(''):empty(selected!=='ALL'||keyword?t('没有匹配询价','No matching inquiries'):t('暂无询价','No inquiries yet'),selected!=='ALL'||keyword?t('调整筛选条件。','Change the filters.'):t('从已审核的供应商车源提交第一条询盘。','Start with an approved supplier listing.'),link('/trade/vehicles',t('浏览车源','Browse listings')))}</div><div id="inquiry-pagination">${window.businessPagination.controls(data)}</div>`);
}
function inquiryStatus(value){
  const labels={WAITING:'Supplier pending',SUBMITTED:'Submitted',VIEWED:'Viewed by supplier',CONTACTED:'Supplier contacted',QUOTED:'Quote Received',NEGOTIATING:'Negotiating',DISCUSSION:'In Discussion',CLOSED:'Closed',CANCELLED:'Cancelled'};
  return tr(labels[value]||value);
}
function renderInquiryDetail(item) {
  if(!item) return pageTitle(tr('BUYER CENTER'),'询价不存在','Inquiry not found','','')+empty(t('未找到询价','Inquiry not found'),'',link('/buyer/inquiries',t('返回询价','Back to inquiries')));
  const v=item.vehicle||{};
  const vehicle=`<div class="row"><img src="${esc(v.image||'/favicon.svg')}" alt=""><div class="row-main"><strong>${esc(v.brand||'')} ${esc(v.model||'')}</strong><small>${esc([v.year,v.bodyType,v.energy].filter(Boolean).join(' · '))}</small></div>${link(item.listing_id?'/trade/vehicles/'+encodeURIComponent(item.listing_id):'/trade/models/'+encodeURIComponent(item.vehicle_id),tr(item.listing_id?'View Listing':'View model'),true)}</div>`;
  const details=[['Inquiry',item.id],['Status',inquiryStatus(item.status)],['Quantity',item.quantity],
    ['Destination country',item.destination_country],['Destination port',item.destination_port],['Incoterm',item.trade_term],
    ['Target price',item.target_price_minor==null?tr('Not specified'):quoteMoney(item.target_price_minor,item.currency)],
    ['Created at',dateTime(item.created_at)],['Updated',dateTime(item.updated_at)]];
  const summary=`<div class="buyer-inquiry-data">${details.map(([label,value])=>`<div><span>${esc(tr(label))}</span><strong>${esc(value===null||value===undefined||value===''?'—':value)}</strong></div>`).join('')}</div>`;
  const replies=(item.replies||[]).length?item.replies.map(r=>`<div class="row"><div class="row-main"><strong>${dateTime(r.created_at)}</strong><small>${esc(r.message)}</small><small>${r.priceLocked?esc(tr('Members only')):r.amount_minor==null?t('无报价金额','No quote amount'):quoteMoney(r.amount_minor,r.currency)}</small></div></div>`).join(''):empty(t('暂无供应商回复','No supplier replies yet'),t('收到回复后会在这里显示。','Replies will appear here when received.'));
  return `<div class="page-top"><div><span class="eyebrow">${esc(tr('AUTOLINK · BUYER CENTER'))}</span><h1>${esc(tr('Inquiry'))} ${esc(item.id)}</h1><p>${esc(tr('Review your inquiry and reply history.'))}</p></div>${link('/buyer/inquiries',tr('Back to list'),true)}</div>`+
    `<div class="two-cols">${panel(tr('Vehicle & Inquiry'),vehicle+summary+`<p>${esc(item.note||tr('No note'))}</p>`)}${panel(tr('Supplier'),item.supplier_name?`<p>${esc(item.supplier_name)}</p>${supplierContact(item.supplierContact,item.contactLocked)}${item.supplier_id?link('/trade/suppliers/'+encodeURIComponent(item.supplier_id),tr('View supplier'),true):''}`:empty(tr('Supplier pending'),tr('Saved without a selected supplier.')))}</div>${panel(tr('Supplier quotations'),link('/buyer/quotes',tr('View my quotations')))}${panel(tr('Reply History'),replies)}`;
}
function renderFavorites(data) {
  const rows=data.map(v=>vehicleRow(v,`${link(v.url,t('查看详情','View Details'),true)}<button class="btn secondary" data-action="inquire" data-id="${esc(v.id)}">${t('立即询价','Inquire')}</button><button class="btn secondary" data-action="compare" data-id="${esc(v.id)}">${t('加入对比','Compare')}</button><button class="btn secondary" data-action="remove-favorite" data-id="${esc(v.id)}">${t('取消收藏','Remove')}</button>`)).join('');
  return pageTitle('AUTOLINK · BUYER CENTER','收藏车辆','Saved Vehicles','管理已保存的采购候选车型。','Manage your sourcing shortlist.',link('/buyer/catalog',t('浏览车型','Browse Models')))+panel(t('我的收藏','My Shortlist'),data.length?`<div class="filters"><input id="favorite-search" type="search" placeholder="${t('搜索品牌或车型','Search brand or model')}"></div><div id="favorite-list" class="list">${rows}</div>`:empty(t('还没有收藏车辆','No saved vehicles yet'),t('浏览车型后点击收藏。','Browse models and save a candidate.'),link('/buyer/catalog',t('浏览车型','Browse Models'))));
}
function renderCompare(data) {
  const fields=[['brand',t('品牌','Brand')],['model',t('车型','Model')],['year',t('年份','Year')],['bodyType',t('车身类型','Body type')],['energy',t('能源类型','Energy')]];
  const rows=fields.map(([key,label])=>`<tr><th>${label}</th>${data.map(v=>`<td>${esc(v[key]||'—')}</td>`).join('')}</tr>`).join('');
  return pageTitle('AUTOLINK · BUYER CENTER','车型对比','Compare Vehicles','最多同时对比 4 台车型。','Compare up to four models.',link('/buyer/catalog',t('添加车型','Add models')))+panel(t('对比清单','Comparison'),data.length?`<div class="compare-wrap"><table class="compare-table"><tr><th></th>${data.map(v=>`<td><img src="${esc(v.image)}" alt=""><p><strong>${esc(v.brand)} ${esc(v.model)}</strong></p>${link(v.url,t('查看详情','View Details'),true)} <button class="btn secondary" data-action="remove-compare" data-id="${esc(v.id)}">${t('移除','Remove')}</button></td>`).join('')}</tr>${rows}<tr><th>${t('FOB 参考价','FOB reference')}</th>${data.map(()=>`<td>${t('待供应商确认','Supplier quote pending')}</td>`).join('')}</tr><tr><th>${t('询价','Inquiry')}</th>${data.map(v=>`<td>${link(`/buyer/requests?vehicleId=${encodeURIComponent(v.id)}`,t('提交采购需求','Create request'))}</td>`).join('')}</tr></table></div><p class="notice">${t('其他规格请以车型详情和供应商确认资料为准。','Confirm further specifications with the supplier.')}</p>`:empty(t('对比清单为空','No models to compare'),t('从车型目录或收藏列表加入最多 4 台。','Add up to four models from the catalogue or shortlist.'),link('/buyer/catalog',t('浏览车型','Browse Models'))));
}
function renderCatalog(data) {
  return pageTitle('AUTOLINK · BUYER CENTER','车型目录','Model Catalogue','基于 AUTOLINK 现有车型资料；库存、FOB 价格与供应商须另行确认。','Existing AUTOLINK model references. Stock, FOB prices and suppliers require confirmation.',link('/vehicles',t('浏览车源','Browse Vehicles'),true))+`<div class="filters"><input type="search" id="catalog-search" placeholder="${t('搜索品牌或车型','Search brand or model')}"><select id="catalog-brand"><option value="">${t('全部品牌','All brands')}</option>${[...new Set(data.map(v=>v.brand))].sort().map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')}</select><select id="catalog-year"><option value="">${t('全部年份','All years')}</option>${[...new Set(data.map(v=>v.year).filter(Boolean))].sort((a,b)=>b-a).map(v=>`<option value="${esc(v)}">${esc(v)}</option>`).join('')}</select><select id="catalog-energy"><option value="">${t('全部动力','All energy types')}</option><option value="EV">${esc(tr("EV"))}</option><option value="PHEV">${esc(tr("PHEV"))}</option><option value="ICE">${esc(tr("ICE"))}</option><option value="HEV">${esc(tr("HEV"))}</option></select></div><div id="catalog-grid" class="catalog-grid">${catalogCards(data.slice(0,24))}</div><p class="notice" id="catalog-count">${t('显示前 24 台车型；可搜索完整目录。','Showing 24 models; search the full catalogue.')}</p>`;
}
function catalogCards(data) { return data.length?data.map(v=>`<article class="model-card"><img loading="lazy" src="${esc(v.image||'/favicon.svg')}" alt=""><div><h3>${esc(v.brand)} ${esc(v.model)}</h3><p>${esc([v.year,v.bodyType,v.energy].filter(Boolean).join(' · '))}</p><p>${t('库存与价格以供应商确认信息为准','Stock and pricing require supplier confirmation')}</p><div class="row-actions">${link(v.url,t('详情','Details'),true)}<button class="btn secondary" data-action="save" data-id="${esc(v.id)}">${t('收藏','Save')}</button><button class="btn secondary" data-action="compare" data-id="${esc(v.id)}">${t('对比','Compare')}</button>${link(`/buyer/requests?vehicleId=${encodeURIComponent(v.id)}`,t('提交采购需求','Create request'))}${link(`/trade/vehicles?brand=${encodeURIComponent(v.brand)}&model=${encodeURIComponent(v.model)}`,t('找已审核车源','Find approved listings'))}</div></div></article>`).join(''):empty(t('没有匹配车型','No matching models'),t('尝试其他关键词。','Try another search.')); }
function renderSuppliers(data) {
  const rows=data.map(s=>`<div class="row"><div class="row-main"><strong>${esc(s.companyName)}</strong><small>${esc(s.country||'—')} · ${esc(tr(s.verificationStatus==='COMPANY_CHECKED'?'Verified supplier':'Unverified'))}</small><small>${esc(s.description)}</small></div><div class="row-actions">${link('/trade/suppliers/'+encodeURIComponent(s.id),tr('View Supplier'),true)}<button class="btn secondary" data-action="unsave-supplier" data-id="${esc(s.id)}">${t('取消关注','Remove')}</button></div></div>`).join('');
  return pageTitle('AUTOLINK · BUYER CENTER','关注供应商','Saved Suppliers','保存并管理真实入驻的供应商。','Follow suppliers with published profiles.')+`<p class="notice">${esc(tr('AUTOLINK checked certain company information. Verification does not guarantee a vehicle exists, supplier performance, payment security or a completed deal.'))}</p>`+panel(t('已关注','Following'),data.length?`<div class="list">${rows}</div>`:empty(t('还没有关注供应商','No saved suppliers'),t('目前没有已关注的真实供应商资料。','No published supplier profile has been saved.')));
}
function buyingDestination() {
  const value=new URLSearchParams(location.search).get('destinationCountry')||'';
  return value.length<=120&&!/[\x00-\x1f\x7f]/.test(value)?value.trim():'';
}
const requestDraftKey='autolink-buyer-request-draft-v1';
function requestDraft() {
  try {
    const saved=JSON.parse(sessionStorage.getItem(requestDraftKey)||'null');
    return saved?.owner===user?.id && Date.now()-saved.savedAt<86400000 ? saved.fields : null;
  } catch { return null; }
}
function saveRequestDraft(form) {
  if(!user?.id)return;
  try {
    const fields=Object.fromEntries(new FormData(form));
    delete fields.publishConsent;
    sessionStorage.setItem(requestDraftKey,JSON.stringify({owner:user.id,savedAt:Date.now(),fields}));
  } catch { /* Browsers may disable storage; the live form still works. */ }
}
function requestSeed() {
  const requested=new URLSearchParams(location.search).get('vehicleId')||'';
  const model=catalog.find(item=>item.id===requested);
  const saved=requestDraft();
  const fields=saved&&(!model||saved.vehicleId===model.id)?saved:{};
  if(model){
    fields.vehicleId=model.id;
    fields.title=fields.title||`${model.brand} ${model.model} sourcing request`;
    fields.brand=model.brand;
    fields.year=model.year||'';
    fields.energy=model.energy||'';
  }
  return {fields,model};
}
function renderRequests(data) {
  const {fields:seed,model:selectedModel}=requestSeed();
  const created=new URLSearchParams(location.search).get('created');
  const createdRow=data.find(item=>item.id===created);
  const creationNotice=createdRow?`<div class="alert success" role="status">${t('采购需求已保存，编号：','Purchase request saved. Reference: ')}<strong>${esc(createdRow.id)}</strong> · ${esc(createdRow.status)}</div>`:'';
  const labels={DRAFT:t('草稿','Draft'),PUBLISHED:t('已发布','Published'),RESPONSES_RECEIVED:t('已收到回应','Responses received'),CLOSED:t('已关闭','Closed')};
  const list=data.length?data.map(r=>`<div class="row"><div class="row-main"><strong>${esc(r.title)}</strong><small>${esc(r.id)} · ${t('数量','Quantity')} ${Number(r.quantity)} · ${esc(labels[r.status]||r.status)} · ${date(r.created_at)}</small><small>${esc([r.brand,r.year,r.energy,r.configuration].filter(Boolean).join(' · '))}</small><small>${esc(r.destination_country||'—')} · ${esc(r.destination_port||'—')} · ${esc(r.trade_term||'—')}</small><p>${r.status==='CLOSED'?t('已停止接收新供应商回应。历史询盘和报价保留。','New supplier responses are closed. Existing inquiries and quotes remain available.'):r.distribution_consent?t('已分享给认证供应商。','Shared with verified suppliers.'):t('仅保存于你的账号，尚未向供应商分享。','Saved in your account; not shared with suppliers.')}</p></div><div class="row-actions">${r.response_count?link('/buyer/quotes',t('查看回应报价','View response quotations')+' ('+Number(r.response_count)+')',true):''}${r.status!=='CLOSED'&&!r.distribution_consent?`<button class="btn" data-action="publish-request" data-id="${esc(r.id)}">${t('分享给认证供应商','Share with verified suppliers')}</button>`:''}${r.status!=='CLOSED'?`<button class="btn secondary" data-action="close-request" data-id="${esc(r.id)}">${t('关闭需求','Close request')}</button>`:''}</div></div>`).join(''):empty(t('暂无采购需求','No purchase requests'),t('填写需求后可保存为草稿或发布。','Create a draft or publish your sourcing request.'));
  return pageTitle('AUTOLINK · BUYER CENTER','采购需求','Purchase Requests','发布你需要的车型、数量和目标市场。','Describe the vehicles, quantity and destination you need.')+creationNotice+panel(t('新建采购需求','New Request'),`${selectedModel?`<p class="notice">${esc(selectedModel.brand)} ${esc(selectedModel.model)} · ${t('车型参考，不代表现货。','Model reference; supplier stock must be verified.')}</p>`:''}<form id="request-form" class="form-grid"><label class="field wide">${t('采购标题','Title')}<input name="title" maxlength="160" value="${esc(seed.title||'')}" required></label><label class="field">${t('目标车型','Model')}<select name="vehicleId"><option value="">${t('不限车型','Any model')}</option>${catalog.map(v=>`<option value="${esc(v.id)}" ${v.id===seed.vehicleId?'selected':''}>${esc(v.brand)} ${esc(v.model)}</option>`).join('')}</select></label><label class="field">${t('品牌','Brand')}<input name="brand" maxlength="120" value="${esc(seed.brand||'')}"></label><label class="field">${t('年份','Model year')}<input name="year" type="number" min="1900" max="2100" value="${esc(seed.year||'')}"></label><label class="field">${t('能源类型','Energy type')}<input name="energy" maxlength="100" value="${esc(seed.energy||'')}"></label><label class="field">${t('数量','Quantity')}<input name="quantity" type="number" min="1" max="100000" value="${esc(seed.quantity||1)}" required></label><label class="field">${t('目标国家','Destination country')}<input name="destinationCountry" maxlength="120" value="${esc(seed.destinationCountry||buyingDestination())}"></label><label class="field">${t('目的港','Destination port')}<input name="destinationPort" maxlength="120" value="${esc(seed.destinationPort||'')}"></label><label class="field">${t('贸易方式','Trade term')}<select name="tradeTerm"><option value="">${t('待确认','To be confirmed')}</option><option value="FOB" ${seed.tradeTerm==='FOB'?'selected':''}>${esc(tr("FOB"))}</option><option value="CIF" ${seed.tradeTerm==='CIF'?'selected':''}>${esc(tr("CIF"))}</option><option value="CFR" ${seed.tradeTerm==='CFR'?'selected':''}>${esc(tr("CFR"))}</option><option value="EXW" ${seed.tradeTerm==='EXW'?'selected':''}>${esc(tr("EXW"))}</option></select></label><label class="field">${t('目标单价，美元（可选）','Target unit price, USD (optional)')}<input name="budget" type="number" min="0" step="0.01" value="${esc(seed.budget||'')}"></label><label class="field wide">${t('所需配置（选填）','Requested configuration (optional)')}<input name="configuration" maxlength="160" value="${esc(seed.configuration||'')}"></label><label class="field wide">${t('备注','Note')}<textarea name="note" maxlength="2000">${esc(seed.note||'')}</textarea></label><label class="consent field wide"><input id="request-sharing" name="publishConsent" type="checkbox"><span>${requestSharingText()}</span></label><div class="form-actions"><button class="btn secondary" type="submit" name="status" value="DRAFT">${t('保存草稿','Save Draft')}</button><button id="publish-request" class="btn" type="submit" name="status" value="PUBLISHED" disabled>${t('发布需求','Publish Request')}</button></div></form><p class="notice">${t('供应商必须使用自己的已审核车源发送报价。报价进入你的个人中心，不产生平台车辆付款。','Suppliers must respond with their own approved listings. Quotations arrive in your account and do not create vehicle payments.')}</p>`)+panel(t('我的需求','My Requests'),`<div class="list">${list}</div>`);
}
function requestSharingText(){return t('我同意向已认证供应商展示此采购需求，并向回应供应商提供我的企业资料和联系邮箱。','I agree to share this buying request with verified suppliers and provide my business profile and contact email to suppliers who respond.');}
function renderMessages(data) {
  return pageTitle('AUTOLINK · BUYER CENTER','消息中心','Messages','查看真实供应商询价回复。','Read actual supplier inquiry replies.')+panel(t('供应商消息','Supplier Messages'),data.length?`<div class="list">${data.map(m=>`<div class="row"><div class="row-main"><strong>${esc(m.supplier_name)} ${m.read_at?'':'· '+t('未读','Unread')}</strong><small>${date(m.created_at)} · ${esc(m.inquiry_id)}</small><p>${esc(m.message)}</p></div><div class="row-actions">${link(`/buyer/inquiries/${encodeURIComponent(m.inquiry_id)}`,t('查看询价','View Inquiry'),true)}${m.read_at?'':`<button class="btn secondary" data-action="mark-read" data-id="${esc(m.id)}">${t('标记已读','Mark read')}</button>`}</div></div>`).join('')}</div>`:empty(t('暂无消息','No messages yet'),t('供应商回复后会显示在这里。','Supplier replies will appear here.')));
}
const quoteMoney = (minor,currency='USD') => minor==null?esc(tr('Members only')):new Intl.NumberFormat(window.businessI18n.locale,{style:'currency',currency:currency||'USD'}).format(Number(minor)/100);
function quoteRow(q) {
  const v=q.vehicle||{};
  return `<div class="row"><img src="${esc(v.image||'/favicon.svg')}" alt=""><div class="row-main"><strong>${esc(q.supplier_name||q.supplier_id)} · ${esc(v.brand||'')} ${esc(v.model||'')}</strong><small>${esc(q.id)} · ${esc(quoteStatus(q.status))} · ${date(q.created_at)}</small><small>${quoteMoney(q.total_price_minor,q.currency)} · ${Number(q.quantity)} ${t('台','units')} · ${esc(q.incoterm)} · ${t('有效至','Valid until')} ${esc(q.valid_until)}</small></div><div class="row-actions">${link('/buyer/quotes/'+encodeURIComponent(q.id),t('查看报价','View Quote'),true)}</div></div>`;
}
function renderQuotes(data) {
  return pageTitle('AUTOLINK · BUYER CENTER','我的报价','My Quotes','查看供应商正式发送的报价；确认意向不产生平台付款。','Review supplier quotations. Accepting an intention does not create a platform payment.',link('/trade/vehicles',t('浏览车源','Browse supplier vehicles'),true))+panel(t('报价记录','Quotations'),data.length?`<div class="list">${data.map(quoteRow).join('')}</div>`:empty(t('暂无报价','No quotations yet'),t('从已审核车源向供应商提交询盘，供应商发送报价后会显示在这里。','Send an inquiry for an approved listing. Supplier quotes appear here.'),link('/trade/vehicles',t('浏览车源','Browse supplier vehicles'))));
}
function renderQuoteDetail(q) {
  const v=q.vehicle||{};
  return pageTitle('AUTOLINK · BUYER CENTER',`${t('报价','Quotation')} ${q.id}`,`${t('报价','Quotation')} ${q.id}`,'请确认数量、贸易条款和有效期。','Check quantity, trade terms and validity.',link('/buyer/quotes',t('返回报价列表','Back to quotes'),true))+`<div class="status"><strong>${esc(quoteStatus(q.status))}</strong><span>${esc(q.supplier_name)}</span><span>${t('有效至','Valid until')} ${esc(q.valid_until)}</span></div><div class="two-cols">${panel(t('报价内容','Quotation'),`<p><strong>${esc(v.brand||'')} ${esc(v.model||'')} ${esc(q.trim||'')}</strong></p><p>${t('数量','Quantity')}: ${Number(q.quantity)} · ${t('单价','Unit price')}: ${quoteMoney(q.unit_price_minor,q.currency)}</p><p>${t('运费','Shipping cost')}: ${quoteMoney(q.priceLocked?null:q.shipping_cost_minor||0,q.currency)}</p><p><strong>${t('总价','Total')}: ${quoteMoney(q.total_price_minor,q.currency)}</strong></p><p>${esc(q.incoterm)} · ${esc(q.origin_port)} → ${esc(q.destination_port||'—')}</p><p>${t('付款条款','Payment terms')}: ${esc(q.payment_terms||'—')}</p><p>${t('备货周期','Lead time')}: ${esc(q.lead_time||'—')}</p><p>${t('备注','Notes')}: ${esc(q.notes||'—')}</p>`)}${panel(t('供应商与回应','Supplier & Response'),`<p>${esc(q.supplier_name)}</p>${supplierContact(q.supplierContact,q.contactLocked)}${link('/trade/suppliers/'+encodeURIComponent(q.supplier_id),t('联系供应商','Contact Supplier'),true)}<div class="form-actions">${!q.priceLocked&&['SENT','VIEWED'].includes(q.status)?`<button class="btn" data-action="quote-accept" data-id="${esc(q.id)}">${t('接受报价意向','Accept Quote Intention')}</button><button class="btn secondary" data-action="quote-reject" data-id="${esc(q.id)}">${t('拒绝报价','Reject Quote')}</button>`:''}</div><p class="notice">${t('接受仅表示采购意向，不会在 AUTOLINK 付款或产生车辆订单。','Accepting records your interest only. It does not pay for a vehicle or create a platform order.')}</p>`)}</div>`;
}
function listingRow(v, saved=false) {
  return `<div class="row"><img src="${esc(v.image||'/favicon.svg')}" alt=""><div class="row-main"><strong>${esc(v.brand)} ${esc(v.model)} · ${esc(v.supplier_name)}</strong><small>${Number(v.model_year)} · ${esc(v.incoterm)} ${esc(v.origin_port)} · ${quoteMoney(v.price_minor,v.currency)}</small></div><div class="row-actions">${link('/trade/vehicles/'+encodeURIComponent(v.id),t('查看车源','View Listing'),true)}${saved?`<button class="btn secondary" data-action="unsave-listing" data-id="${esc(v.id)}">${t('取消收藏','Remove')}</button>`:''}</div></div>`;
}
function renderSavedListings(data) {return pageTitle('AUTOLINK · BUYER CENTER','收藏车源','Saved Supplier Listings','这些车源来自已审核供应商，可直接提交询盘。','These listings come from approved suppliers and support real inquiries.',link('/trade/vehicles',t('浏览车源','Browse listings')))+panel(t('已收藏车源','Saved Listings'),data.length?`<div class="list">${data.map(v=>listingRow(v,true)).join('')}</div>`:empty(t('还没有收藏车源','No saved supplier listings'),t('浏览已审核车源后点击收藏。','Browse approved listings and save one.')));}
function renderHistory(data) {return pageTitle('AUTOLINK · BUYER CENTER','浏览历史','Recently Viewed','最近查看的车源，最多保留 50 条。','Your 50 most recently viewed supplier listings.',link('/trade/vehicles',t('浏览车源','Browse listings')))+panel(t('最近查看','Recent Listings'),data.length?`<div class="list">${data.map(v=>listingRow(v)).join('')}</div>`:empty(t('暂无浏览记录','No recent views'),t('打开一条已审核车源后会记录在这里。','Open an approved listing to see it here.')));}
function renderMembership(data) {
  const m=data.membership, status=m.status==='FREE'?t('免费账号','Free Account'):m.status==='ACTIVE'?t('已开通','Active'):t('已到期','Expired');
  return pageTitle('AUTOLINK · BUYER CENTER','会员中心','Membership','查看会员状态与会员费账单。','Review your plan and membership fee history.')+`<div class="status"><strong>${esc(status)}</strong><span>${m.plan?`${esc(tr(m.plan))} · ${date(m.startAt)} — ${date(m.endAt)}`:t('暂无付费会员记录','No paid membership record')}</span><span>${m.autoRenew?t('自动续费已开启','Auto-renewal enabled'):t('不会自动续费','Does not renew automatically')}</span></div>${panel(t('会员权益','Membership Benefits'),`<p>${esc(tr("Free buyers: one inquiry per account in total. Prices and full supplier contacts are for members. All three plans include the same benefits."))}</p><p>${t('当前可用权益以正式开通的方案为准。','Available benefits depend on your activated plan.')}</p><p class="notice">${t('线上付款暂未开放。你可以在会员方案页发送开通申请。','Online payment is not yet available. Submit a membership application from the plans page.')}</p>${link('/membership',t('申请开通会员','Apply for membership'),true)}`)}${panel(t('会员费账单','Membership Billing History'),data.billing.length?data.billing.map(b=>`<div class="row"><div class="row-main"><strong>${esc(tr(b.plan))} · ${esc(b.currency)} ${(b.amount_minor/100).toFixed(2)}</strong><small>${date(b.paid_at)} · ${esc(b.status)} · ${esc(b.transaction_id)}</small></div></div>`).join(''):empty(t('暂无会员费账单','No membership payments'),t('仅展示平台会员费，不含车辆交易款项。','Only platform membership fees appear here; vehicle payments are excluded.')))}<p class="notice">${t('续费和升级将在真实会员付款服务开通后提供。','Renewal and upgrade will be available when a real membership checkout is connected.')}</p>`;
}
function renderCompany(data) {
  const fields=[['companyName','公司名称','Company Name'],['contact_person','联系人','Contact Person'],['job_title','职位','Job Title'],['phone','电话','Phone'],['whatsapp','WhatsApp','WhatsApp'],['country','国家/地区','Country / Region'],['city','城市','City'],['website','公司网站','Website'],['company_type','公司类型','Company Type'],['target_market','采购市场','Target Market'],['preferred_brands','主要采购品牌','Preferred Brands'],['annual_volume','年采购量','Annual Volume']];
  return pageTitle('AUTOLINK · BUYER CENTER','买家企业资料','Buyer company profile','维护采购企业与联系人资料。','Maintain your company and contact details.')+`<div class="status"><strong>${t('认证状态','Verification')}</strong><span>${data.verificationStatus==='VERIFIED'?t('已认证','Verified'):data.verificationStatus==='PENDING'?t('审核中','Pending'):t('未认证','Unverified')}</span></div>${panel(t('企业信息','Company Information'),`<form id="company-form" class="form-grid">${fields.map(([key,zh,en])=>`<label class="field">${t(zh,en)}<input name="${key}" value="${esc(data[key]||'')}" ${key==='companyName'?'required':''}></label>`).join('')}<label class="field wide">${t('企业简介','Company Introduction')}<textarea name="introduction">${esc(data.introduction||'')}</textarea></label><div class="form-actions"><button class="btn" type="submit">${t('保存修改','Save Changes')}</button></div></form><p class="notice">${t('登录邮箱：','Sign-in email: ')} ${esc(data.email)} · ${t('企业认证尚未开放。','Company verification is not yet available.')}</p>`)}`;
}
function renderSecurity(data) {
  return pageTitle('AUTOLINK · BUYER CENTER','账号与安全','Account & Security','管理邮箱登录与账号会话。','Manage email sign-in and account sessions.')+panel(t('登录方式','Sign-in Method'),`<p><strong>${t('登录邮箱','Email')}:</strong> ${esc(data.email)} · ${data.emailVerified?t('邮箱已验证','Email verified'):t('邮箱未验证','Email not verified')}</p><p><strong>${esc(tr("Google:"))}</strong> ${data.googleLinked?t('已绑定','Connected'):t('未绑定','Not connected')}</p><p><strong>${t('密码','Password')}:</strong> ${data.passwordSet?t('已设置','Set'):t('未设置','Not set')}</p><p><strong>${t('最近登录','Last sign-in')}:</strong> ${date(data.lastLoginAt)}</p><div class="form-actions"><button class="btn secondary" data-action="logout-all">${t('退出所有设备','Sign out all sessions')}</button></div>`)+panel(data.passwordSet?t('修改密码','Change Password'):t('设置密码','Set Password'),window.autolinkPasswordForm(data))+panel(t('删除账户','Delete account'),`<p>${t('申请关闭账户请联系平台支持。历史询盘和报价按隐私政策处理，不会因会员到期而删除。','Contact platform support to request account closure. Historical inquiries and quotes are handled under the Privacy Policy and are retained when membership expires.')}</p>${link('/support?type=General%20Support',t('申请删除账户','Request account deletion'),true)}`)+panel(t('最近设备','Recent Devices'),empty(t('设备记录尚不可用','Device history is unavailable'),t('当前账号服务尚未记录设备信息。','The account service does not record device details.')));
}

async function loadPage(epoch=navigationId) {
  const pathname=location.pathname,section=pathname.split('/')[2]||'';
  if(epoch!==navigationId)return;
  currentSection=section;
  loading(currentSection);
  try {
    const previewData = {overview:{counts:{savedVehicles:0,activeInquiries:0,supplierReplies:0,savedSuppliers:0},membership:{status:'FREE'},recentInquiries:[],savedVehicles:[],profileComplete:true},profile:{companyName:'',email:'',verificationStatus:'UNVERIFIED'},membership:{membership:{status:'FREE',autoRenew:false},billing:[]},security:{email:'',googleLinked:false,passwordSet:false,lastLoginAt:null}};
    const read=async request=>{const result=await request;if(epoch!==navigationId)throw new DOMException('Navigation changed','AbortError');return result;};
    const get=path=>read(localPreview?Promise.resolve(previewData[path]??[]):api(`/autolink/buyer/${path}`));
    if(needsBuyerCatalog())await read(loadBuyerCatalog(epoch));
    let html='';
    if(!currentSection) html=overview(await get('overview'));
    else if(currentSection==='catalog') html=renderCatalog(catalog);
    else if(currentSection==='inquiries' && pathname.split('/')[3]) html=renderInquiryDetail(await get(`inquiries/${encodeURIComponent(pathname.split('/')[3])}`));
    else if(currentSection==='inquiries') {renderedData=localPreview?[]:await read(window.businessPagination.load(api,inquiryApiPath()));html=renderInquiries(renderedData);}
    else if(currentSection==='quotes' && pathname.split('/')[3]) html=renderQuoteDetail(await get(`quotes/${encodeURIComponent(pathname.split('/')[3])}`));
    else if(currentSection==='quotes') {const rows=localPreview?[]:await read(window.businessPagination.load(api,'/autolink/buyer/quotes'));html=renderQuotes(rows)+window.businessPagination.controls(rows);}
    else if(currentSection==='saved-listings') html=renderSavedListings(await get('saved-listings'));
    else if(currentSection==='history') html=renderHistory(await get('history'));
    else if(currentSection==='favorites') {renderedData=await get('favorites');html=renderFavorites(renderedData);}
    else if(currentSection==='compare') html=renderCompare(await get('compare'));
    else if(currentSection==='suppliers') html=renderSuppliers(await get('saved-suppliers'));
    else if(currentSection==='requests') {const rows=localPreview?[]:await read(window.businessPagination.load(api,'/autolink/buyer/requests'));html=renderRequests(rows)+window.businessPagination.controls(rows);}
    else if(currentSection==='messages') html=renderMessages(await get('messages'));
    else if(currentSection==='membership') html=renderMembership(await get('membership'));
    else if(currentSection==='company') html=renderCompany(await get('profile'));
    else if(currentSection==='notifications') html=await read(notificationPage());
    else if(currentSection==='security') html=renderSecurity(await get('security'));
    else html=pageTitle('AUTOLINK · BUYER CENTER','页面不存在','Page not found','','')+link('/buyer',t('返回采购中心','Back to Buyer Center'));
    if(epoch===navigationId)setContent(html);
  } catch(e) { if(epoch!==navigationId||e.name==='AbortError')return;if(e.status===401){user=null;renderedData=null;location.replace('/buyer/login?returnTo='+encodeURIComponent(location.pathname+location.search));return;}error(section,e,pathname); }
}

async function mutation(path,method,body) { const epoch=navigationId;try { await api(`/autolink/buyer/${path}`,method,body);if(epoch===navigationId)await start();return true;} catch(e) { if(epoch!==navigationId)return false;const old=document.querySelector('.content .alert'); if(old) old.remove(); document.querySelector('#buyer-content')?.insertAdjacentHTML('afterbegin',`<div class="alert error" role="alert">${esc(e.message)}</div>`);return false;} }
document.addEventListener('change', event => {
  if (event.target.id === 'buyer-consent') updateCodeButton();
});
document.addEventListener('click', async event => {
  if (!event.target.closest('#buyer-send-code')) return;
  const form = document.querySelector('#buyer-email-form');
  const emailInput = form?.elements.email;
  if (!emailInput?.reportValidity() || codeSending || codeRetryUntil > Date.now()) return;
  if (!document.querySelector('#buyer-consent')?.checked) {
    codeStatus(t('请先同意服务条款和隐私政策。', 'Agree to the Terms and Privacy Policy first.'), true);
    return;
  }
  codeSending = true; updateCodeButton(); codeStatus('');
  try {
    await api('/autolink/auth/email/send-code', 'POST', {email:emailInput.value.trim(), purpose:'login', consent:true, language:window.businessI18n.language});
    codeRetryUntil = Date.now() + 60000;
    codeStatus(t('验证码已发送，有效期 10 分钟。', 'Code sent. It is valid for 10 minutes.'));
  } catch(e) {
    codeStatus(t('发送失败，请稍后重试。', 'Could not send the code. Please retry.'), true);
  } finally { codeSending = false; updateCodeButton(); }
});
document.addEventListener('submit', async event => {
  if (event.target.id !== 'buyer-email-form') return;
  event.preventDefault();
  const form = event.target;
  if (!document.querySelector('#buyer-consent')?.checked) {
    codeStatus(t('请先同意服务条款和隐私政策。', 'Agree to the Terms and Privacy Policy first.'), true);
    return;
  }
  const submit = form.querySelector('[type=submit]');
  submit.disabled = true; codeStatus(t('正在登录…', 'Signing in…'));
  try {
    const values = Object.fromEntries(new FormData(form));
    const joining=isJoinPage();
    const body={email:values.email.trim(),code:values.code,consent:true,language:window.businessI18n.language};
    if(joining){body.country=values.country;body.password=values.password;}
    const result = await api(joining?'/autolink/auth/email/register':'/autolink/auth/email/login','POST',body);
    const destinations = {BUYER:'/buyer', MERCHANT:'/supplier', SUPPLIER:'/supplier', ADMIN:'/admin', PLATFORM_ADMIN:'/admin'};
    const destination = destinations[result.role];
    if (!destination) throw Error(t('账号角色未配置。', 'Account role is not configured.'));
    if (result.role !== 'BUYER') localStorage.setItem('autolink-cookie-session', '1');
    location.assign(result.role==='BUYER'?afterLogin():destination);
  } catch(e) {
    codeStatus(e.message || t('验证码错误或已失效。', 'Invalid or expired code.'), true);
    submit.disabled = false;
  }
});
document.addEventListener('click', async event => {
  const el=event.target.closest('[data-action],[data-filter]'); if(!el) return;
  const action=el.dataset.action, id=el.dataset.id;
  if(action==='menu') { const side=document.querySelector('#buyer-sidebar'); side.classList.toggle('open'); el.setAttribute('aria-expanded',side.classList.contains('open')); }
  if(action==='logout') { try { sessionStorage.removeItem(requestDraftKey);await api('/auth/logout','POST',{}); } catch {} location.href='/buyer/login'; }
  if(action==='logout-all') { try{sessionStorage.removeItem(requestDraftKey);}catch{} await mutation('logout-all','POST',{});location.href='/buyer/login'; }
  if(action==='save') await mutation('favorites','POST',{vehicleId:id});
  if(action==='remove-favorite') await mutation(`favorites/${encodeURIComponent(id)}`,'DELETE');
  if(action==='compare') await mutation('compare','POST',{vehicleId:id});
  if(action==='remove-compare') await mutation(`compare/${encodeURIComponent(id)}`,'DELETE');
  if(action==='unsave-supplier') await mutation(`saved-suppliers/${encodeURIComponent(id)}`,'DELETE');
  if(action==='unsave-listing') await mutation(`saved-listings/${encodeURIComponent(id)}`,'DELETE');
  if(action==='quote-accept') await mutation(`quotes/${encodeURIComponent(id)}/response`,'POST',{decision:'ACCEPTED'});
  if(action==='quote-reject') await mutation(`quotes/${encodeURIComponent(id)}/response`,'POST',{decision:'REJECTED'});
  if(action==='publish-request'&&!el.disabled&&confirm(requestSharingText())){
    el.disabled=true;
    if(await mutation(`requests/${encodeURIComponent(id)}`,'PUT',{status:'PUBLISHED',publishConsent:true}))
      document.querySelector('#buyer-content')?.insertAdjacentHTML('afterbegin',`<div class="alert success" role="status">${t('采购需求已分享给符合条件的供应商。','Purchase request shared with eligible suppliers.')}</div>`);
    else el.disabled=false;
  }
  if(action==='close-request'&&!el.disabled&&confirm(t('关闭后停止接收新供应商回应，已有询盘和报价继续保留。','Close this request to stop new responses? Existing inquiries and quotes remain available.'))){
    el.disabled=true;
    if(await mutation(`requests/${encodeURIComponent(id)}`,'PUT',{status:'CLOSED'}))
      document.querySelector('#buyer-content')?.insertAdjacentHTML('afterbegin',`<div class="alert success" role="status">${t('采购需求已关闭；历史询盘和报价保留。','Purchase request closed; existing inquiries and quotes remain available.')}</div>`);
    else el.disabled=false;
  }
  if(action==='mark-read') await mutation(`messages/${encodeURIComponent(id)}/read`,'POST',{});
  if(action==='inquire') location.href=`/buyer/requests?vehicleId=${encodeURIComponent(id)}`;
  if(el.dataset.filter) { document.querySelectorAll('#inquiry-tabs button').forEach(b=>b.setAttribute('aria-selected',b===el));await filterInquiries(); }
});
function inquiryApiPath() {
  const current=new URLSearchParams(location.search),query=new URLSearchParams();
  for(const key of ['status','keyword'])if(current.has(key))query.set(key,current.get(key));
  return '/autolink/buyer/inquiries'+(query.size?'?'+query.toString():'');
}
async function filterInquiries() {
  clearTimeout(inquiryFilterTimer);
  const epoch=navigationId,version=++inquiryFilterVersion,list=document.querySelector('#inquiry-list'),pager=document.querySelector('#inquiry-pagination');
  if(!list||!pager)return;
  beginBuyerRead();
  const q=(document.querySelector('#inquiry-search')?.value||'').trim();
  const selected=document.querySelector('#inquiry-tabs [aria-selected=true]')?.dataset.filter||'ALL';
  const url=new URL(location.href);
  if(q)url.searchParams.set('keyword',q);else url.searchParams.delete('keyword');
  if(selected!=='ALL')url.searchParams.set('status',selected);else url.searchParams.delete('status');
  url.searchParams.set('page','1');history.replaceState(null,'',url.pathname+url.search);
  list.setAttribute('aria-busy','true');list.innerHTML='<div class="skeleton"></div>';pager.innerHTML='';
  try {
    const rows=localPreview?[]:await window.businessPagination.load(api,inquiryApiPath());
    if(epoch!==navigationId||version!==inquiryFilterVersion||!list.isConnected)return;
    renderedData=rows;
    list.innerHTML=rows.length?rows.map(inquiryRow).join(''):empty(t('没有匹配询价','No matching inquiries'),t('调整筛选条件。','Change the filters.'));
    pager.innerHTML=window.businessPagination.controls(rows);
  } catch(e) {
    if(epoch!==navigationId||version!==inquiryFilterVersion||!list.isConnected||e.name==='AbortError')return;
    e=window.businessI18n.apiError?.(e)||e;
    list.innerHTML='<div class="alert error" role="alert">'+esc(e.message)+'</div>'+link(location.pathname+location.search,t('重试','Retry'),true);
  } finally {if(epoch===navigationId&&version===inquiryFilterVersion&&list.isConnected)list.removeAttribute('aria-busy');}
}
document.addEventListener('input', event => {
  if(event.target.closest('#request-form'))saveRequestDraft(event.target.form);
  if(event.target.id==='inquiry-search') {inquiryFilterVersion++;readController?.abort();clearTimeout(inquiryFilterTimer);inquiryFilterTimer=setTimeout(filterInquiries,300);}
  if(event.target.id==='favorite-search') { const q=event.target.value.toLowerCase();const filtered=(renderedData||[]).filter(v=>`${v.brand} ${v.model}`.toLowerCase().includes(q));document.querySelector('#favorite-list').innerHTML=filtered.length?filtered.map(v=>vehicleRow(v,`${link(v.url,t('查看详情','View Details'),true)}<button class="btn secondary" data-action="inquire" data-id="${esc(v.id)}">${t('询价','Inquire')}</button><button class="btn secondary" data-action="compare" data-id="${esc(v.id)}">${t('对比','Compare')}</button><button class="btn secondary" data-action="remove-favorite" data-id="${esc(v.id)}">${t('移除','Remove')}</button>`)).join(''):empty(t('没有匹配车型','No matching models'),''); }
  if(['catalog-search','catalog-brand','catalog-year','catalog-energy'].includes(event.target.id)) { const q=(document.querySelector('#catalog-search')?.value||'').trim().toLocaleLowerCase(),brand=document.querySelector('#catalog-brand')?.value||'',year=document.querySelector('#catalog-year')?.value||'',energy=document.querySelector('#catalog-energy')?.value||'';const matched=catalog.filter(v=>(!brand||v.brand===brand)&&(!year||String(v.year)===year)&&(!energy||String(v.energy||'').split(/[,/]/).map(x=>x.trim()).includes(energy))&&(!q||[v.brand,v.model,catalogAliases.get(v.id)].filter(Boolean).join(' ').toLocaleLowerCase().includes(q)));document.querySelector('#catalog-grid').innerHTML=catalogCards(matched.slice(0,60));document.querySelector('#catalog-count').textContent=`${matched.length} ${t('台匹配车型，最多显示前 60 台','matching models; showing at most 60')}`; }
});
document.addEventListener('submit', async event => {
  const form=event.target; if(!['inquiry-form','request-form','company-form'].includes(form.id)) return;
  event.preventDefault();const values=Object.fromEntries(new FormData(form));
  if(form.id==='inquiry-form') { values.quantity=Number(values.quantity);if(await mutation('inquiries','POST',values))location.href='/buyer/inquiries'; }
  if(form.id==='request-form') {
    if(form.dataset.submitting==='1')return;
    form.dataset.submitting='1';
    const buttons=[...form.querySelectorAll('button[type=submit]')];
    buttons.forEach(button=>button.disabled=true);
    values.quantity=Number(values.quantity);
    values.year=values.year?Number(values.year):null;
    values.status=event.submitter?.value||'DRAFT';
    values.publishConsent=values.publishConsent==='on';
    values.budgetMinor=values.budget?Math.round(Number(values.budget)*100):null;
    values.currency='USD';delete values.budget;
    try {
      const saved=await api('/autolink/buyer/requests','POST',values);
      try{sessionStorage.removeItem(requestDraftKey);}catch{}
      location.assign('/buyer/requests?created='+encodeURIComponent(saved.id));
    } catch(error) {
      form.querySelector('[data-request-error]')?.remove();
      form.insertAdjacentHTML('afterbegin',`<div class="alert error" role="alert" data-request-error>${esc(error.message)} · ${link('/buyer/requests',t('查看已有需求','Check existing requests'),true)}</div>`);
      buttons.forEach(button=>button.disabled=button.id==='publish-request'&&!form.elements.publishConsent.checked);
      delete form.dataset.submitting;
    }
  }
  if(form.id==='company-form') await mutation('profile','PUT',values);
});

async function start() {
  const epoch=beginBuyerNavigation();
  if(location.pathname==='/buyer/login'||location.pathname==='/buyer/register') { renderLogin();return; }
  loading(location.pathname.split('/')[2]||'');
  if(localPreview) { user={companyName:t('预览模式','Preview mode')};await loadPage(epoch);return; }
  try { const [me]=await Promise.all([api('/autolink/me'),needsBuyerCatalog()?loadBuyerCatalog(epoch):Promise.resolve()]);if(epoch!==navigationId)return;if(me.role!=='BUYER') {user=null;renderLogin(t('此账号不是买家账号。','This is not a buyer account.'));return;}user=me;await loadPage(epoch); }
  catch(e) { if(epoch!==navigationId||e.name==='AbortError')return;user=null;renderedData=null;if(e.message.includes('不是买家')||e.message.includes('not a buyer')) {renderLogin(e.message);return;}location.replace('/buyer/login?returnTo='+encodeURIComponent(location.pathname+location.search)); }
}
function internalBuyerUrl(href){
  const url=new URL(href,location.href);
  if(url.origin!==location.origin||!(url.pathname==='/buyer'||url.pathname.startsWith('/buyer/')))return null;
  if(['/buyer/login','/buyer/register'].includes(url.pathname)||/\.(?:js|mjs|css|png|jpe?g|pdf|svg)$/.test(url.pathname))return null;
  const nextLanguage=url.searchParams.get('lang'),currentLanguage=new URLSearchParams(location.search).get('lang');
  if(nextLanguage&&nextLanguage!==currentLanguage)return null;
  return url;
}
function navigateBuyer(href){
  const url=internalBuyerUrl(href);if(!url){location.assign(href);return;}
  history.pushState(null,'',url.pathname+url.search+url.hash);void start();window.scrollTo?.(0,0);
}
document.addEventListener('click',event=>{
  if(event.defaultPrevented||event.button!==0||event.metaKey||event.ctrlKey||event.shiftKey||event.altKey)return;
  const anchor=event.target.closest('a[href]');if(!anchor||anchor.hasAttribute('download')||(anchor.target&&anchor.target!=='_self'))return;
  const url=internalBuyerUrl(anchor.href);if(!url)return;
  if(url.pathname===location.pathname&&url.search===location.search&&url.hash)return;
  event.preventDefault();navigateBuyer(url.href);
});
document.addEventListener('submit',event=>{
  const form=event.target;
  if(event.defaultPrevented||form.tagName!=='FORM'||form.method.toLowerCase()!=='get'||Object.keys(form.dataset).length||['inquiry-form','request-form','company-form','buyer-email-form','buyer-password-form'].includes(form.id))return;
  const url=internalBuyerUrl(form.action||location.href);if(!url)return;
  event.preventDefault();url.search=new URLSearchParams(new FormData(form)).toString();navigateBuyer(url.href);
});
window.addEventListener('popstate',()=>{if(internalBuyerUrl(location.href))void start();});
start();

document.addEventListener('click',e=>{const b=e.target.closest('[data-login-tab]');if(!b)return;document.querySelector('#buyer-email-form').hidden=b.dataset.loginTab!=='code';document.querySelector('#buyer-password-form').hidden=b.dataset.loginTab!=='password';});
document.addEventListener('submit',async e=>{if(e.target.id!=='buyer-password-form')return;e.preventDefault();const f=e.target,b=f.querySelector('[type=submit]');b.disabled=true;try{const v=Object.fromEntries(new FormData(f));const data=await api('/autolink/auth/password/login','POST',{email:v.email,password:v.password,remember:v.remember==='on'});location.href=data.role==='BUYER'?afterLogin():data.role==='PLATFORM_ADMIN'?'/admin':'/supplier';}catch(error){document.querySelector('#buyer-password-status').textContent=error.message;b.disabled=false;}});


async function notificationPage(){const data=await window.businessPagination.load(api,'/autolink/notifications');return `<section class="panel"><div class="panel-head"><h2>${t('通知','Notifications')}</h2></div>${data.length?`<div class="list">${data.map(n=>`<div class="supplier-row"><div class="supplier-row-main"><strong>${esc(notificationName(n.event))}</strong><small>${esc(n.entity_id)}</small></div><a class="button-link secondary" href="${esc(n.url)}">${t('查看','View')}</a>${!n.read_at?`<button class="btn secondary" data-notice="${esc(n.id)}">${t('标记已读','Mark read')}</button>`:''}</div>`).join('')}</div>`:`<div class="empty"><strong>${t('暂无通知','No notifications yet.')}</strong></div>`}</section>`+window.businessPagination.controls(data);}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-notice]');if(!b)return;const epoch=navigationId;try{await api('/autolink/notifications/'+encodeURIComponent(b.dataset.notice),'POST',{});if(epoch===navigationId)await start();}catch(error){if(epoch===navigationId&&b.isConnected)b.textContent=error.message;}});

function notificationName(event){const translated=tr(event);if(translated!==event)return translated;const labels={QUOTE_CANCELLED:['供应商已取消报价','Quotation cancelled'],NEW_QUOTE:['收到新报价','New quote'],NEW_INQUIRY:['收到新询盘','New inquiry'],QUOTE_RESPONSE:['买家回应报价','Buyer quote response'],SUPPLIER_REVIEW:['企业审核结果','Supplier review'],VEHICLE_REVIEW:['车辆审核结果','Vehicle review'],SUPPORT_REQUEST:['新支持请求','Support request'],TEAM_INVITED:['供应商团队邀请','Supplier team invitation'],TEAM_JOINED:['团队成员已加入','Team member joined'],BUYER_ASSIGNED:['已分配客户','Buyer assigned'],QUOTE_ACCEPTED:['买家接受报价意向','Buyer accepted quote intention'],QUOTE_REJECTED:['买家拒绝报价','Buyer rejected quote'],SUPPLIER_APPROVED:['企业审核通过','Supplier approved'],SUPPLIER_REJECTED:['企业申请未通过','Supplier rejected'],SUPPLIER_REQUIRES_CHANGES:['企业资料需修改','Supplier changes required'],SUPPLIER_SUSPENDED:['企业资格已暂停','Supplier suspended'],VEHICLE_APPROVED:['车源审核通过','Listing approved'],VEHICLE_REJECTED:['车源审核未通过','Listing rejected']};return labels[event]?t(...labels[event]):t('账户更新','Account update');}

function quoteStatus(value){const names={DRAFT:["草稿","Draft"],SENT:["已发送","Sent"],VIEWED:["已查看","Viewed"],ACCEPTED:["已接受意向","Accepted"],REJECTED:["已拒绝","Rejected"],EXPIRED:["已过期","Expired"],CANCELLED:["已取消","Cancelled"]};return names[value]?t(...names[value]):value;}

document.addEventListener("change",event=>{
  const form=event.target.closest('#request-form');
  if(!form)return;
  if(event.target.name==='vehicleId'){
    const model=catalog.find(item=>item.id===event.target.value);
    if(model){
      form.elements.brand.value=model.brand;
      form.elements.year.value=model.year||'';
      form.elements.energy.value=model.energy||'';
      if(!form.elements.title.value.trim())form.elements.title.value=`${model.brand} ${model.model} sourcing request`;
    }
  }
  if(event.target.id==='request-sharing')document.querySelector('#publish-request').disabled=!event.target.checked;
  saveRequestDraft(form);
});
