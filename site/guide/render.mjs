import {guides,ui,languages,languageNames,translationNotices} from './content.mjs';
export const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const href = (path,language='en') => {
  const [pathname,hash] = path.split('#');
  return pathname + (pathname.includes('?')?'&':'?') + 'lang=' + encodeURIComponent(language) + (hash?'#'+hash:'');
};
const list = (items, className='guide-list') => `<ul class="${className}">${items.map(item=>`<li>${esc(item)}</li>`).join('')}</ul>`;
const action = (path,label,language,secondary=false) => `<a class="button-link${secondary?' secondary':''}" href="${esc(href(path,language))}">${esc(label)}</a>`;
export function guideState(id,language='en') {
  if (!guides[id]) throw new Error('Unknown guide');
  const selected=languages.includes(language)?language:'en';
  const contentLanguage=selected==='zh'?'zh':'en';
  return {id,language:selected,contentLanguage,content:guides[id][contentLanguage],labels:ui[contentLanguage],guide:guides[id],translated:['zh','en'].includes(selected)};
}
export function metadata(id,language='en') {
  const s=guideState(id,language);
  return {title:s.content.title+' | AUTOLINK',description:s.content.subtitle,
    canonical:'https://autolinkglobal.com'+href('/guide/'+id,s.contentLanguage),
    robots:s.translated?'index,follow':'noindex,follow',contentLanguage:s.contentLanguage};
}
function navigation(language,t) {
  const entries=[['/','Home'],['/trade/vehicles','Supplier Vehicles'],['/trade/models','Model references'],['/trade/brands','Brands'],['/trade/suppliers','Suppliers'],['/membership','Membership'],['/buyer','Buyer Center'],['/supplier/application','Supplier Center']];
  return entries.map(([path,label])=>`<a href="${esc(href(path,language))}">${esc(t(label))}</a>`).join('');
}
export function shell(id,language='en',translate=value=>value) {
  const s=guideState(id,language),{content:c,labels:u,guide:g}=s;
  const frameworkTranslate=translate;
  translate=value=>{const translated=frameworkTranslate(value);return translated===value?staticTranslate(s.language==='zh'?'zh':'en')(value):translated;};
  const nav=navigation(s.language,translate);
  const mobileMenu=s.language==='zh'?'菜单':translate('Menu');
  const notice=!s.translated?`<aside class="guide-language-notice" role="note" lang="${s.language}" dir="${s.language==='ar'?'rtl':'ltr'}"><strong>${esc(translationNotices[s.language]||u.fallback)}</strong><div>${action('/guide/'+id,'English', 'en',true)}${action('/guide/'+id,'中文','zh',true)}</div></aside>`:s.language==='en'?`<p class="guide-translation-note" role="note">${esc(u.englishDraft)}</p>`:'';
  const toc=tableOfContents(s);
  return `<a class="guide-skip" href="#main">${esc(translate('Skip to content'))}</a>
    <header class="trade-head guide-header"><div class="trade-head-inner"><a class="brand" href="${esc(href('/',s.language))}" aria-label="AUTOLINK ${esc(translate('Home'))}">AUTOLINK<i aria-hidden="true">▪</i></a>
      <nav class="trade-nav guide-desktop-nav" aria-label="${esc(translate('Main navigation'))}">${nav}</nav>
      <label class="business-language"><span>${esc(translate('Language'))}</span><select data-guide-language aria-label="${esc(translate('Language'))}">${languages.map(code=>`<option value="${code}"${code===s.language?' selected':''}>${esc(languageNames[code])}</option>`).join('')}</select></label>
      <details class="guide-mobile-menu"><summary>${esc(mobileMenu)}<span aria-hidden="true">＋</span></summary><nav aria-label="${esc(translate('Main navigation'))}">${nav}</nav></details>
    </div></header>
    <main id="main" class="guide-main guide-${g.type}" lang="${s.contentLanguage}" dir="ltr">
      <a class="guide-back" href="${esc(href('/#suppliers',s.language))}">${esc(u.back)}</a>
      ${notice}
      <section class="guide-hero"><div><p class="eyebrow">${esc(u.guide)} <span class="guide-slash">/</span> ${g.number}</p><h1>${esc(c.title)}</h1><p class="guide-subtitle">${esc(c.subtitle)}</p></div>
        <div class="guide-cover guide-cover-${g.type}" aria-hidden="true"><span class="guide-cover-word">${g.type==='verification'?'KNOW YOUR PARTNER':g.type==='sourcing'?'RESEARCH / SOURCE':'INQUIRY / AGREEMENT'}</span><span class="guide-cover-number">${g.number}</span><span class="guide-cover-caption">${esc(c.label)}</span></div>
      </section>
      <div class="guide-body"><aside class="guide-toc"><span>${esc(u.contents)}</span><nav aria-label="${esc(u.contents)}">${toc.map(([anchor,title],index)=>`<a href="#${anchor}"><small>${String(index+1).padStart(2,'0')}</small>${esc(title)}</a>`).join('')}</nav></aside>
        <div class="guide-content">${g.type==='verification'?verification(s):g.type==='sourcing'?sourcing(s):process(s)}
        ${nextStep(s)}<p class="guide-legal-note">${esc(u.note)} <a href="${esc(href('/terms',s.language))}">${esc(translate('Terms'))}</a></p></div>
      </div>
      <nav class="guide-related" aria-label="${esc(u.more)}">${Object.entries(guides).filter(([key])=>key!==id).map(([key,value])=>`<a href="${esc(href('/guide/'+key,s.language))}"><small>${value.number} / ${esc(u.guide)}</small><strong>${esc(value[s.contentLanguage].label)}</strong></a>`).join('')}</nav>
    </main>
    <footer class="trade-footer"><div class="trade-footer-inner"><span>${esc(translate('AUTOLINK · Connecting Chinese vehicle suppliers and global buyers.'))}</span><span>${[['/terms','Terms'],['/membership-terms','Membership Terms'],['/privacy','Privacy'],['/support','Contact support']].map(([path,label])=>`<a href="${esc(href(path,s.language))}">${esc(translate(label))}</a>`).join('')}</span></div></footer>`;
}
function tableOfContents({guide:g,labels:u,content:c}) {
  return g.type==='verification'?[['profile',u.identity],['review',u.reviewTitle],['statuses',u.states],['limits',u.notGuarantee],['cooperate',u.cooperate]]:
    g.type==='sourcing'?[['coverage',u.catalog],['authorization',c.brandTitle],['comparison',u.reference+' / '+u.listing],['checklist',u.checklist]]:
    [['timeline',u.guide],['quotation',u.quote],['trade-terms',u.terms],['responsibilities',u.platform]];
}
const paras=items=>items.map(value=>`<p>${esc(value)}</p>`).join('');
function verification({content:c,labels:u}) {
  return `<section id="profile" class="guide-section"><p class="eyebrow">COMPANY PROFILE</p><h2>${esc(u.identity)}</h2><p>${esc(c.intro)}</p>${list(c.fields,'guide-profile-fields')}<p class="guide-small-note">${esc(c.fieldsNote)}</p></section>
    <section id="review" class="guide-section"><h2>${esc(u.reviewTitle)}</h2>${paras(c.reviewBody)}</section>
    <section id="statuses" class="guide-section"><p class="eyebrow">REVIEW STATUS</p><h2>${esc(u.states)}</h2><div class="guide-status-grid">${c.states.map(([title,body],i)=>`<article class="guide-status"><span class="guide-status-number">0${i+1}</span><h3>${esc(title)}</h3><p>${esc(body)}</p></article>`).join('')}</div></section>
    <section id="limits" class="guide-limit"><h2>${esc(u.notGuarantee)}</h2><p>${esc(c.limitsLead)}</p>${list(c.limits,'guide-limits-list')}<p>${esc(c.limitsBody)}</p></section>
    <section id="cooperate" class="guide-section"><h2>${esc(u.cooperate)}</h2><ol class="guide-cooperate">${c.steps.map((step,i)=>`<li><span>0${i+1}</span>${esc(step)}</li>`).join('')}</ol></section>`;
}
function sourcing({content:c,labels:u,language:l}) {
  return `<section id="coverage" class="guide-section"><p class="eyebrow">MODEL RESEARCH</p><h2>${esc(u.catalog)}</h2><p>${esc(c.coverageBody)}</p><div class="guide-coverage">${c.coverage.map((field,i)=>`<div><span>0${i+1}</span>${esc(field)}</div>`).join('')}</div><div class="guide-actions">${action('/trade/models',u.models,l,true)}</div></section>
    <section id="authorization" class="guide-brand-note"><h2>${esc(c.brandTitle)}</h2><p>${esc(c.brandBody)}</p></section>
    <section id="comparison" class="guide-section"><p class="eyebrow">REFERENCE / OFFER</p><div class="guide-compare"><article><span class="guide-tag">01 / RESEARCH</span><h2>${esc(u.reference)}</h2><p>${esc(c.referenceBody)}</p>${list(c.referenceItems)}${action('/trade/models',u.models,l,true)}</article><article><span class="guide-tag">02 / SUPPLY</span><h2>${esc(u.listing)}</h2><p>${esc(c.listingBody)}</p>${list(c.listingItems)}${action('/trade/vehicles',u.vehicles,l)}</article></div><div class="guide-assumptions"><h3>${esc(c.assumptionsTitle)}</h3>${list(c.assumptions)}</div></section>
    <section id="checklist" class="guide-section"><p class="eyebrow">BEFORE YOUR INQUIRY</p><h2>${esc(u.checklist)}</h2><ul class="guide-checklist">${c.checklist.map((value,i)=>`<li><span>0${i+1}</span>${esc(value)}</li>`).join('')}</ul></section>`;
}
function process({content:c,labels:u,language:l}) {
  return `<section id="timeline" class="guide-section guide-timeline-section"><p class="eyebrow">SOURCING IN SIX STEPS</p><h2>${esc(c.intro)}</h2><ol class="guide-timeline">${c.steps.map((step,i)=>`<li><details${i===0?' open':''}><summary><span class="guide-step-number">0${i+1}</span><span><strong>${esc(step.title)}</strong><small>${esc(step.summary)}</small></span><span class="guide-expand" aria-hidden="true">＋</span></summary><div class="guide-step-body">${paras(step.body)}${list(step.items)}${step.action?`<div class="guide-actions">${action(step.action[1],step.action[0],l,true)}</div>`:''}</div></details></li>`).join('')}</ol></section>
    <section id="quotation" class="guide-section"><p class="eyebrow">QUOTATION CHECKLIST</p><h2>${esc(u.quote)}</h2><dl class="guide-quote-fields">${c.quoteFields.map(([title,body])=>`<div><dt>${esc(title)}</dt><dd>${esc(body)}</dd></div>`).join('')}</dl></section>
    <section id="trade-terms" class="guide-brand-note"><h2>${esc(u.terms)}</h2><p>${esc(u.termsBody)}</p></section>
    <section id="responsibilities" class="guide-section"><h2>${esc(u.responsibility)}</h2><div class="guide-responsibilities"><article><span class="guide-tag">PLATFORM</span><h3>${esc(u.platform)}</h3><p>${esc(c.platformBody)}</p></article><article><span class="guide-tag">BUYER / SELLER</span><h3>${esc(u.parties)}</h3><p>${esc(c.partiesBody)}</p></article></div></section>`;
}
function nextStep({content:c,labels:u,guide:g,language:l}) {
  const buttons=g.type==='verification'?action('/trade/suppliers',u.suppliers,l):action('/trade/vehicles',u.vehicles,l)+action(g.type==='sourcing'?'/trade/models':'/buyer/requests',g.type==='sourcing'?u.models:u.request,l,true);
  return `<section id="next-step" class="guide-next"><p class="eyebrow">${esc(u.next)}</p><h2>${esc(c.label)}</h2><p>${esc(c.ctaBody)}</p><div class="guide-actions">${buttons}</div>${g.type==='process'?`<p class="guide-small-note">${esc(u.loginNote)}</p>`:''}<div class="guide-availability" data-guide-availability="${g.availability}" role="status" aria-live="polite"><p>${esc(u.loading)}</p></div></section>`;
}
export function availabilityHTML(id,language,state) {
  const {guide:g,labels:u}=guideState(id,language);
  if(state==='error')return `<p>${esc(u.error)}</p><button class="guide-retry" type="button" data-guide-retry>${esc(u.retry)}</button>`;
  const key=g.availability+(state==='empty'?'Empty':'Ready');
  return `<strong>${esc(u[key])}</strong><p>${esc(u[key+'Body'])}</p>${state==='empty'?action('/trade/models',u.models,language,true):''}`;
}
export function documentHTML(id,language='en') {
  const m=metadata(id,language),s=guideState(id,language);
  const alternates=[['en','en'],['zh-CN','zh'],['x-default','en']].map(([code,query])=>`<link rel="alternate" hreflang="${code}" href="https://autolinkglobal.com${href('/guide/'+id,query)}">`).join('');
  return `<!doctype html>\n<html lang="${s.contentLanguage==='zh'?'zh-CN':'en'}" dir="ltr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${esc(m.title)}</title><meta name="description" content="${esc(m.description)}"><meta name="robots" content="${m.robots}"><link rel="canonical" href="${esc(m.canonical)}">${alternates}<link rel="icon" href="/favicon.svg"><link rel="stylesheet" href="/buyer/buyer.css?v=20261009-speed"><link rel="stylesheet" href="/trade/trade.css?v=20261009-speed"><link rel="stylesheet" href="/guide/guide.css?v=20261011-guide-cards"><link rel="modulepreload" href="/assets/business-language-loader.mjs?v=20261009-speed"></head><body class="guide-page"><div id="guide-app">${shell(id,language,staticTranslate(s.contentLanguage))}</div><noscript><p class="guide-noscript">${s.contentLanguage==='zh'?'所有说明与业务链接均可访问；公开目录的最新状态需打开相应目录查看。':'All guide content and business links remain available. Open the relevant directory to check its latest public information.'}</p></noscript><script type="module" src="/guide/app.mjs?v=20261011-guide-cards"></script></body></html>\n`;
}
function staticTranslate(language) {
  const zh={'Home':'首页','Supplier Vehicles':'车源','Model references':'车型参考','Brands':'品牌','Suppliers':'供应商','Membership':'会员服务','Buyer Center':'买家中心','Supplier Center':'商家中心','Main navigation':'主导航','Language':'语言','Menu':'菜单','Skip to content':'跳到正文','Terms':'用户协议','Membership Terms':'会员条款','Privacy':'隐私政策','Contact support':'联系支持','AUTOLINK · Connecting Chinese vehicle suppliers and global buyers.':'AUTOLINK · 连接中国汽车供应商与全球买家。'};
  return value=>language==='zh'?(zh[value]||value):value;
}
