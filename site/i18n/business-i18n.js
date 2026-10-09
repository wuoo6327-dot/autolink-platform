/* i18next adapter for existing AUTOLINK account pages. */
(() => {
const supported=['en','zh','ar','ru','kk','uz','ko','fr','sw'];
const requested=new URLSearchParams(location.search).get('lang');
const normalize=value=>value==='zh-CN'?'zh':value;
const stored=()=>{for(const key of ['autolink-language','autolink_language']){try{const value=normalize(localStorage.getItem(key));if(supported.includes(value))return value;}catch{/* Try the next compatibility key. */}}return null;};
const remember=value=>{try{localStorage.setItem('autolink-language',value);localStorage.setItem('autolink_language',value==='zh'?'zh-CN':value);}catch{/* Language still works when storage is denied. */}};
const requestedLanguage=normalize(requested);
const fixedLanguage=normalize(window.AUTOLINK_BUSINESS_FIXED_LANGUAGE);
const browserLanguage=typeof navigator==='undefined'?'en':String(navigator.language||'en').toLowerCase().split('-')[0];
const language=supported.includes(fixedLanguage)?fixedLanguage:supported.includes(requestedLanguage)?requestedLanguage:stored()||(supported.includes(browserLanguage)?browserLanguage:'en');
if(!supported.includes(fixedLanguage)&&requested && (supported.includes(requested)||requested==='zh-CN')) remember(language);
const resources=window.AUTOLINK_BUSINESS_RESOURCES||{};
i18next.init({lng:language,supportedLngs:supported,fallbackLng:fixedLanguage||'en',resources,keySeparator:false,nsSeparator:false,initAsync:false,interpolation:{escapeValue:false}});
document.documentElement.lang=language==='zh'?'zh-CN':language;
document.documentElement.dir=language==='ar'?'rtl':'ltr';
const text=en=>i18next.t(en,{defaultValue:en});
// Only known application errors are shown verbatim. Unknown upstream bodies,
// browser exceptions and field names receive a localized, safe fallback.
const errorFields={quantity:'Quantity',stock:'Stock','minimum order':'MOQ',currency:'Currency',incoterm:'Incoterm',
  'company name':'Company name','company overview':'Company overview','contact name':'Contact person',
  'contact phone':'Phone',address:'Registered address',country:'Country',city:'City',website:'Website',
  'registration number':'Business registration number','destination country':'Destination country',
  'destination port':'Destination port','origin port':'Origin port','valid until':'Valid until',
  'delivery date':'Delivery date',trim:'Trim',model:'Model',brand:'Brand','model year':'Model year',
  'energy type':'Energy type','lead time':'Lead time','payment terms':'Payment terms',colors:'Available colors',
  'export markets':'Export markets',description:'Description',message:'Message',note:'Note',title:'Title',
  'request title':'Title','review reason':'Review reason','main brands':'Main brands','main markets':'Main markets',
  'export experience':'Export experience','public contact name':'Public contact person',
  'public contact email':'Public contact email','public contact phone':'Public contact phone',
  'public business address':'Public business address',email:'Email',filename:'File name'};
const errorItems={brand:'Brand',model:'Model','vehicle listing':'Vehicle','vehicle model':'Model',inquiry:'Inquiry',
  'draft quote':'Quote',quote:'Quote','buyer relationship':'Buyer relationship',account:'Account',document:'Document',
  image:'Image',notification:'Notification','support request':'Support request',report:'Report',
  'supplier workspace':'Workspace','team member':'Team member','active team member':'Team member',invitation:'Invitation',
  'buying request':'Buying request','published buying request':'Buying request',message:'Message'};
const errorAliases={
  'Platform admin required.':'Platform administrator permission is required.',
  'Platform administrator permission required.':'Platform administrator permission is required.',
  'Please sign in.':'Sign in required',
  'Login has expired. Please sign in again.':'Your session has expired. Please sign in again.',
  'Invalid or expired verification code.':'Invalid or expired code.',
  'Inquiry is closed.':'Inquiry is closed or unavailable.',
  'Document is too large.':'Document must be 5 MB or smaller.',
  'The request quantity is below the listing MOQ.':"Quantity is below this supplier's MOQ."};
const ownLabel=(labels,key)=>Object.hasOwn(labels,key)?labels[key]:null;
function errorText(value,status=0){
  const active=normalize(document.documentElement.lang);
  const errorLanguage=supported.includes(active)?active:language;
  const text=en=>i18next.t(en,{lng:errorLanguage,defaultValue:en});
const dictionary=resources[errorLanguage]?.translation||{};
const localizedValues=new Set(Object.values(dictionary));
const known=value=>{
  for(const key of [value,value.replace(/\.$/,''),value.toLowerCase()])
    if(Object.hasOwn(dictionary,key))return text(key);
  return null;
};
  const raw=typeof value==='string'?value:typeof value?.message==='string'?value.message:'';
  const exact=known(raw);if(exact)return exact;
  if(localizedValues.has(raw))return raw;
  if(Object.hasOwn(errorAliases,raw))return text(errorAliases[raw]);
  let match=raw.match(/^Invalid (.+)\.$/i),label=match&&ownLabel(errorFields,match[1].toLowerCase());
  if(label&&known(label))return text('{field} is invalid.').replace('{field}',known(label));
  match=raw.match(/^(.+) must be text\.$/i);label=match&&ownLabel(errorFields,match[1].toLowerCase());
  if(label&&known(label))return text('{field} must be text.').replace('{field}',known(label));
  match=raw.match(/^(.+) cannot be in the past\.$/i);label=match&&ownLabel(errorFields,match[1].toLowerCase());
  if(label&&known(label))return text('{field} cannot be in the past.').replace('{field}',known(label));
  match=raw.match(/^(.+?)(?: was)? not found\.$/i);label=match&&ownLabel(errorItems,match[1].toLowerCase());
  if(label&&known(label))return text('{item} could not be found.').replace('{item}',known(label));
  if(['TimeoutError','AbortError'].includes(value?.name))return text('The request timed out. Please try again.');
  if(!status&&value?.name==='TypeError')return text('Unable to connect. Please try again.');
  if(status===401)return text('Your session has expired. Please sign in again.');
  if(status===403)return text('You do not have permission to perform this action.');
  if(status===404)return text('The requested item could not be found.');
  if(status===409)return text('This record changed or cannot be updated in its current state. Reload and try again.');
  if(status===429)return text('Too many requests. Try again later.');
  if(status>=500)return text('The service is temporarily unavailable. Please try again later.');
  if(status>=400&&status<500)return text('Check the submitted information and try again.');
  return text('Request failed.');
}
function apiError(value,status){
  if(value?._autolinkLocalized)return value;
  const candidate=Number(value?.status??status??0),code=Number.isInteger(candidate)&&candidate>=400&&candidate<=599?candidate:0;
  const error=new Error(errorText(value,code||candidate));error.status=code;
  Object.defineProperty(error,'_autolinkLocalized',{value:true});return error;
}
const names={en:'English',zh:'简体中文',ar:'العربية',ru:'Русский',kk:'Қазақша',uz:'O‘zbekcha',ko:'한국어',fr:'Français',sw:'Kiswahili'};
const escape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
window.businessI18n={language,locale:language==='zh'?'zh-CN':language,translate:(zh,en)=>i18next.t(en,{defaultValue:language==='zh'?zh:en}),text,errorText,apiError,
  languageControl:()=>`<label class="business-language"><span>${escape(text('Language'))}</span><select data-business-language aria-label="${escape(text('Language'))}">${supported.map(code=>`<option value="${code}" ${code===language?'selected':''}>${names[code]}</option>`).join('')}</select></label>`};
document.addEventListener('change',async event=>{
  if(supported.includes(fixedLanguage))return;
  if(!event.target.matches('[data-business-language]')||!supported.includes(event.target.value))return;
  const selected=event.target.value;remember(selected);
  // An authenticated account stores this separately from its country. Visitors
  // and older deployed backends can still change the page language.
  try{await fetch('/autolink/auth/preferences',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({language:selected}),signal:AbortSignal.timeout(1500)});}catch{/* Keep language navigation usable when offline. */}
  const url=new URL(location.href);url.searchParams.set('lang',selected);location.assign(url.href);
});
document.addEventListener('DOMContentLoaded',()=>{
  // Only explicit, application-owned labels. Never translate user content.
  document.querySelectorAll('[data-business-text]').forEach(node=>{node.textContent=text(node.dataset.businessText);});
});
})();
