// Load only the active language and English fallback, then the existing adapter.
const files={"en":"/i18n/chunks/supplier-en-f25371bbf727.js","zh":"/i18n/chunks/supplier-zh-13b82acb1a3d.js","ar":"/i18n/chunks/supplier-ar-fd9293edeb9c.js","ru":"/i18n/chunks/supplier-ru-95b424140f0e.js","kk":"/i18n/chunks/supplier-kk-9ae6f2065573.js","uz":"/i18n/chunks/supplier-uz-77288ceacad7.js","ko":"/i18n/chunks/supplier-ko-f42e3fe69461.js","fr":"/i18n/chunks/supplier-fr-03bce41e03f5.js","sw":"/i18n/chunks/supplier-sw-176e1cb2f80d.js"};
const normalize=v=>v==='zh-CN'?'zh':v;
let requested=normalize(new URLSearchParams(location.search).get('lang'));
let stored;
for(const key of ['autolink-language','autolink_language']){try{const value=normalize(localStorage.getItem(key));if(files[value]){stored=value;break;}}catch{}}
const browser=String(navigator.language||'en').toLowerCase().split('-')[0];
const language=files[requested]?requested:stored||(files[browser]?browser:'en');
function load(url){return new Promise((resolve,reject)=>{const script=document.createElement('script');script.src=url;script.onload=resolve;script.onerror=()=>reject(Error('Resource unavailable'));document.head.append(script);});}
try{
 await Promise.all([load('/vendor/i18next-26.4.2.min.js'),...[...new Set(['en',language])].map(lang=>load(files[lang]))]);
 await Promise.all([load('/i18n/business-i18n.js?v=20261006-common'),load('/supplier/company-fields.js?v=20261013-multi-picker')]);
 await load('/supplier/app.js?v=20261013-account-role');
}catch{
 const labels={en:'Unable to load. Please reload.',zh:'加载失败，请刷新页面。',ar:'تعذر التحميل. أعد تحميل الصفحة.',ru:'Не удалось загрузить. Обновите страницу.',kk:'Жүктеу мүмкін болмады. Бетті жаңартыңыз.',uz:'Yuklanmadi. Sahifani yangilang.',ko:'불러오지 못했습니다. 새로고침하세요.',fr:'Chargement impossible. Rechargez la page.',sw:'Imeshindwa kupakia. Pakia ukurasa tena.'};
 document.querySelector('#app').textContent=labels[language]||labels.en;
}
