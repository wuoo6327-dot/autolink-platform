// Reuse the original per-model configuration and photo snapshots. Stock and
// prices are obtained only from the existing reviewed supplier listing API.
export const escapeHTML=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function translateSpecification(value,language,dictionary={},verified={}){
 const source=String(value??'—');
 return language==='zh'?source:verified[language]?.[source]??dictionary[source]??source;
}
export function selectionForYear(data,year,ids=[]){
 const choices=(data.variants||[]).filter(v=>String(v.year)===String(year));
 const selected=[...new Set(ids)].map(id=>choices.find(v=>v.id===id)).filter(Boolean).slice(0,4);
 if(!selected.length)selected.push(...choices.slice(0,2));
 return {choices,selected};
}
export function specificationGroups(data,selected,query='',differences=false,translate=String){
 const q=query.trim().toLocaleLowerCase();
 return (data.groups||[]).map((g,i)=>({...g,index:i,rows:g.rows.filter(row=>{
  const vals=selected.map(v=>String(v.values?.[row.key]??'—'));
  if(differences&&new Set(vals).size<2)return false;
  return !q||[row.label,translate(row.label),...vals,...vals.map(translate)].join(' ').toLocaleLowerCase().includes(q);
 })})).filter(g=>g.rows.length);
}
export function safePhotos(data){return (data.photos||[]).filter(p=>typeof p.src==='string'&&p.src.startsWith('/images/')&&!p.src.includes('..')&&!/[\\<>"\x00-\x1f]/.test(p.src)&&['exterior','interior'].includes(p.category));}
const labels={
 en:['Overview','Specifications','Images','Available suppliers','Model year','Primary configuration','Compare configuration','Add comparison','Remove','Search specifications','Differences only','Show Chinese source text','All photos','Exterior','Interior','Photo configuration','All configurations','Configuration information unavailable','No matching specifications','No approved supplier offers for this model yet.','Manufacturer reference data; confirm the exact export configuration with the supplier.','Model reference photos; confirm actual supplier inventory.','View source','Previous photo','Next photo','Price requires a supplier quotation','No photos available','Retry','Page {page} of {pages}'],
 zh:['概览','配置参数','图片','可供货供应商','年款','主要配置','对比配置','添加对比','移除','搜索配置项目','仅看差异','显示中文原文','全部图片','外观','内饰','图片对应配置','全部配置','暂无完整配置资料','没有匹配的配置项目','该车型暂无审核上线的供应商车源。','厂家参考资料；具体出口配置请与供应商确认。','车型参考图片；实际供应商库存请另行确认。','查看来源','上一张图片','下一张图片','价格请向供应商询价','暂无图片','重试','第 {page} 页，共 {pages} 页'],
 ar:['نظرة عامة','المواصفات','الصور','الموردون المتاحون','سنة الطراز','التجهيز الأساسي','تجهيز المقارنة','إضافة مقارنة','إزالة','البحث في المواصفات','الاختلافات فقط','عرض النص الصيني الأصلي','جميع الصور','الخارج','الداخل','تجهيز الصورة','جميع التجهيزات','معلومات التجهيز غير متاحة','لا توجد مواصفات مطابقة','لا توجد عروض معتمدة لهذا الطراز بعد.','بيانات مرجعية من المصنع؛ أكد تجهيز التصدير مع المورد.','صور مرجعية للطراز؛ أكد مخزون المورد الفعلي.','عرض المصدر','الصورة السابقة','الصورة التالية','السعر يتطلب عرضًا من المورد','لا توجد صور','إعادة المحاولة','الصفحة {page} من {pages}'],
 ru:['Обзор','Характеристики','Изображения','Доступные поставщики','Модельный год','Основная комплектация','Сравниваемая комплектация','Добавить сравнение','Удалить','Поиск характеристик','Только различия','Показать китайский оригинал','Все фотографии','Экстерьер','Интерьер','Комплектация на фото','Все комплектации','Данные комплектации недоступны','Нет подходящих характеристик','Одобренных предложений этой модели пока нет.','Справочные данные производителя; уточните экспортную комплектацию у поставщика.','Справочные фотографии модели; уточните фактический склад поставщика.','Источник','Предыдущее фото','Следующее фото','Запросите цену у поставщика','Фотографий нет','Повторить','Страница {page} из {pages}'],
 kk:['Шолу','Сипаттамалар','Суреттер','Қолжетімді жеткізушілер','Модель жылы','Негізгі жинақтама','Салыстырылатын жинақтама','Салыстыру қосу','Жою','Сипаттамаларды іздеу','Тек айырмашылықтар','Қытайша түпнұсқаны көрсету','Барлық суреттер','Сыртқы көрініс','Салон','Суреттегі жинақтама','Барлық жинақтамалар','Жинақтама деректері жоқ','Сәйкес сипаттамалар жоқ','Бұл модель бойынша мақұлданған ұсыныстар әлі жоқ.','Өндірушінің анықтамалық деректері; экспорт жинақтамасын жеткізушімен нақтылаңыз.','Модельдің анықтамалық суреттері; жеткізушінің нақты қорын тексеріңіз.','Дереккөз','Алдыңғы сурет','Келесі сурет','Бағаны жеткізушіден сұраңыз','Суреттер жоқ','Қайталау','{pages} беттің {page} беті'],
 uz:['Umumiy maʼlumot','Xususiyatlar','Rasmlar','Mavjud yetkazib beruvchilar','Model yili','Asosiy komplektatsiya','Taqqoslash komplektatsiyasi','Taqqoslash qoʻshish','Oʻchirish','Xususiyatlarni qidirish','Faqat farqlar','Xitoycha asl matnni koʻrsatish','Barcha rasmlar','Tashqi koʻrinish','Salon','Rasmdagi komplektatsiya','Barcha komplektatsiyalar','Komplektatsiya maʼlumoti mavjud emas','Mos xususiyatlar topilmadi','Bu model uchun tasdiqlangan takliflar hali yoʻq.','Ishlab chiqaruvchi maʼlumotlari; eksport komplektatsiyasini yetkazib beruvchi bilan tasdiqlang.','Modelning namunaviy rasmlari; haqiqiy zaxirani yetkazib beruvchi bilan tasdiqlang.','Manbani koʻrish','Oldingi rasm','Keyingi rasm','Narxni yetkazib beruvchidan soʻrang','Rasmlar yoʻq','Qayta urinish','{pages} sahifadan {page}-sahifa'],
 ko:['개요','제원','이미지','공급 가능한 업체','연식','기본 트림','비교 트림','비교 추가','삭제','제원 검색','차이점만 보기','중국어 원문 표시','전체 사진','외관','실내','사진의 트림','전체 트림','트림 정보 없음','일치하는 제원 없음','이 모델의 승인된 공급업체 매물이 아직 없습니다.','제조사 참고 자료입니다. 정확한 수출 사양은 공급업체에 확인하세요.','모델 참고 사진입니다. 실제 공급업체 재고를 확인하세요.','출처 보기','이전 사진','다음 사진','공급업체에 가격 문의','사진 없음','다시 시도','{pages}페이지 중 {page}페이지'],
 fr:['Présentation','Caractéristiques','Images','Fournisseurs disponibles','Année du modèle','Configuration principale','Configuration comparée','Ajouter une comparaison','Retirer','Rechercher une caractéristique','Différences uniquement','Afficher le texte chinois original','Toutes les photos','Extérieur','Intérieur','Configuration photographiée','Toutes les configurations','Informations de configuration indisponibles','Aucune caractéristique correspondante','Aucune offre approuvée pour ce modèle actuellement.','Données de référence du constructeur ; confirmez la configuration export avec le fournisseur.','Photos de référence du modèle ; confirmez le stock réel du fournisseur.','Voir la source','Photo précédente','Photo suivante','Demandez un devis au fournisseur','Aucune photo','Réessayer','Page {page} sur {pages}'],
 sw:['Muhtasari','Vipimo','Picha','Wasambazaji waliopo','Mwaka wa modeli','Toleo kuu','Toleo la kulinganisha','Ongeza ulinganisho','Ondoa','Tafuta vipimo','Tofauti pekee','Onyesha maandishi asili ya Kichina','Picha zote','Nje','Ndani','Toleo lililo kwenye picha','Matoleo yote','Taarifa za toleo hazipatikani','Hakuna vipimo vinavyolingana','Bado hakuna ofa zilizoidhinishwa kwa modeli hii.','Taarifa za mtengenezaji; thibitisha toleo la kusafirisha na msambazaji.','Picha za marejeleo ya modeli; thibitisha hisa halisi za msambazaji.','Angalia chanzo','Picha iliyotangulia','Picha inayofuata','Omba bei kutoka kwa msambazaji','Hakuna picha','Jaribu tena','Ukurasa {page} kati ya {pages}']
};
const extraLabels={
 en:['Configurations','Official promotional image','Standard','Optional','Not specified'],
 zh:['配置版本','厂家宣传图','标配','选配','未提供'],
 ar:['التجهيزات','صورة ترويجية رسمية','قياسي','اختياري','غير محدد'],
 ru:['Комплектации','Официальное рекламное фото','Стандарт','Опция','Не указано'],
 kk:['Жинақтамалар','Ресми жарнамалық сурет','Стандарт','Қосымша','Көрсетілмеген'],
 uz:['Komplektatsiyalar','Rasmiy reklama rasmi','Standart','Ixtiyoriy','Koʻrsatilmagan'],
 ko:['트림','공식 홍보 이미지','기본','선택','미제공'],
 fr:['Configurations','Photo promotionnelle officielle','De série','En option','Non précisé'],
 sw:['Matoleo','Picha rasmi ya matangazo','Kawaida','Hiari','Haijabainishwa']
};
for(const lang of Object.keys(labels))labels[lang].push(...extraLabels[lang]);
export function uiText(language,key){const i=labels.en.indexOf(key);return i<0?key:(labels[language]||labels.en)[i];}
const json=async url=>{const r=await fetch(url,{credentials:'same-origin',signal:AbortSignal.timeout(15000)});if(!r.ok)throw Error('Reference data unavailable');return r.json();};
export async function mountReference(host,options){
 const {model,language='en',locale=language,read,card,translate=x=>x}=options;
 const e=escapeHTML,t=key=>uiText(language,key),plain=key=>translate(key);
 let data,dictionary={},verified={};
 try{[data,dictionary,verified]=await Promise.all([json('/model-reference/'+encodeURIComponent(model.id)+'.json'),language==='zh'?Promise.resolve({}):json('/locales/specs-'+encodeURIComponent(language)+'.json'),json('/locales/seo-verified-terms.json')]);}
 catch(error){host.innerHTML=`<div class="empty" role="status">${e(t('Configuration information unavailable'))} <button class="btn secondary" data-reference-retry>${e(t('Retry'))}</button></div>`;host.querySelector('[data-reference-retry]').onclick=()=>mountReference(host,options);return;}
 if(!host.isConnected||data.modelId!==model.id)return;
 const st={tab:(new URLSearchParams(location.search).get('tab')||'specifications').toLowerCase(),year:data.availableYears?.[0],ids:[],query:'',diff:false,category:'',photoTrim:'',photoIndex:0};
 if(!['specifications','images','suppliers'].includes(st.tab)){st.tab='specifications';const url=new URL(location.href);if(url.searchParams.has('tab')){url.searchParams.set('tab',st.tab);history.replaceState(null,'',url.pathname+url.search+url.hash);}}
 const sourceText=value=>translateSpecification(value,language,dictionary,verified.translations);
 const valueText=value=>sourceText(String(value??'—').replace(/\d+(?:\.\d+)?\s*(?:万元|元)/g,plain('Supplier quote pending')));
 const photos=safePhotos(data),uniqueTrims=[...new Set(photos.map(p=>p.trim).filter(Boolean))];
 let offers,loadingOffers=false;
 function trimSelect(v,index,choices){return `<div class="reference-trim"><label>${e(t(index?'Compare configuration':'Primary configuration'))}<select data-reference-trim="${index}">${choices.map(c=>`<option value="${e(c.id)}" ${c.id===v.id?'selected':''} ${st.ids.includes(c.id)&&c.id!==v.id?'disabled':''}>${e(c.year+' · '+sourceText(c.name))}</option>`).join('')}</select></label>${index>1?`<button type="button" class="btn secondary" data-reference-remove="${index}">${e(t('Remove'))}</button>`:''}</div>`;}
 function specs(){
  const {choices,selected}=selectionForYear(data,st.year,st.ids);st.ids=selected.map(v=>v.id);
  if(!selected.length||!data.groups.length)return `<div class="empty">${e(t('Configuration information unavailable'))}</div>`;
  const groups=specificationGroups(data,selected,st.query,st.diff,valueText);
  return `<div class="reference-selects"><label>${e(t('Model year'))}<select data-reference-year>${data.availableYears.map(y=>`<option ${y===st.year?'selected':''}>${y}</option>`).join('')}</select></label>${selected.map((v,i)=>trimSelect(v,i,choices)).join('')}${selected.length<4&&selected.length<choices.length?`<button class="btn secondary" type="button" data-reference-add>${e(t('Add comparison'))}</button>`:''}</div><div class="reference-tools"><label class="reference-search"><span>${e(t('Search specifications'))}</span><input data-reference-search value="${e(st.query)}" placeholder="${e(t('Search specifications'))}"></label><label class="reference-check"><input type="checkbox" data-reference-differences ${st.diff?'checked':''}>${e(t('Differences only'))}</label><span class="trade-note">● ${e(t('Standard'))} &nbsp; ○ ${e(t('Optional'))} &nbsp; — ${e(t('Not specified'))}</span></div><div class="reference-comparison"><nav class="reference-categories" aria-label="${e(t('Specifications'))}">${groups.map(g=>`<a href="#reference-group-${g.index}">${e(sourceText(g.name))}</a>`).join('')}</nav><div class="reference-table-area">${groups.length?groups.map(g=>`<section id="reference-group-${g.index}" class="reference-group"><h3>${e(sourceText(g.name))}<small>${g.rows.length}</small></h3><div class="reference-table-scroll" tabindex="0"><table class="reference-table"><thead><tr><th scope="col">${e(t('Specifications'))}</th>${selected.map(v=>`<th scope="col">${e(valueText(v.name))}</th>`).join('')}</tr></thead><tbody>${g.rows.map(r=>`<tr class="${new Set(selected.map(v=>v.values?.[r.key]??'—')).size>1?'reference-different':''}"><th scope="row">${e(sourceText(r.label))}</th>${selected.map(v=>`<td>${e(valueText(v.values?.[r.key]))}</td>`).join('')}</tr>`).join('')}</tbody></table></div></section>`).join(''):`<div class="empty">${e(t('No matching specifications'))}</div>`}</div></div>`;
 }
 function filteredPhotos(){return photos.filter(p=>(!st.category||p.category===st.category)&&(!st.photoTrim||p.trim===st.photoTrim));}
 function gallery(){const selected=filteredPhotos();st.photoIndex=Math.min(st.photoIndex,Math.max(0,selected.length-1));const current=selected[st.photoIndex];return `<div class="reference-photo-tools"><div class="reference-photo-filter">${['','exterior','interior'].map(c=>`<button class="btn secondary ${st.category===c?'selected':''}" data-reference-photo-category="${c}" aria-pressed="${st.category===c}">${e(t(c==='exterior'?'Exterior':c==='interior'?'Interior':'All photos'))}</button>`).join('')}</div><label>${e(t('Photo configuration'))}<select data-reference-photo-trim><option value="">${e(t('All configurations'))}</option>${uniqueTrims.map(v=>`<option value="${e(v)}" ${v===st.photoTrim?'selected':''}>${e(v==='Official promotional image'?t('Official promotional image'):sourceText(v))}</option>`).join('')}</select></label></div>${current?`<figure class="reference-photo-view"><img src="${e(current.src)}" alt="${e(model.brand+' '+model.model+' · '+t(current.category==='interior'?'Interior':'Exterior'))}"><figcaption>${st.photoIndex+1} / ${selected.length} · ${e(current.trim==='Official promotional image'?t('Official promotional image'):sourceText(current.trim||''))}</figcaption></figure><div class="reference-photo-controls"><button class="btn secondary" data-reference-photo-step="-1" ${st.photoIndex===0?'disabled':''}>${e(t('Previous photo'))}</button><button class="btn secondary" data-reference-photo-step="1" ${st.photoIndex===selected.length-1?'disabled':''}>${e(t('Next photo'))}</button></div><div class="reference-thumbnails">${selected.map((p,i)=>`<button type="button" data-reference-photo-index="${i}" aria-label="${e(t(p.category==='interior'?'Interior':'Exterior'))} ${i+1}" aria-pressed="${i===st.photoIndex}"><img loading="lazy" decoding="async" src="${e(p.src)}" alt=""></button>`).join('')}</div>`:`<div class="empty">${e(t('No photos available'))}</div>`}<p class="trade-note">${e(t('Model reference photos; confirm actual supplier inventory.'))}</p>`;}
 function draw(){
  if(!host.isConnected)return;
  let body;
  if(st.tab==='specifications')body=specs();
  else if(st.tab==='images')body=gallery();
  else if(st.tab==='suppliers')body=loadingOffers?`<div class="loading-screen">${e(plain('Loading…'))}</div>`:offers?.length?`<div class="trade-grid">${offers.map(card).join('')}</div>`:`<div class="empty">${e(t('No approved supplier offers for this model yet.'))}</div>`;
  host.innerHTML=`<nav class="reference-tabs" role="tablist" aria-label="${e(t('Configurations'))}">${['specifications','images','suppliers'].map((tab,i)=>`<button type="button" role="tab" aria-selected="${st.tab===tab}" data-reference-tab="${tab}" id="reference-tab-${tab}" aria-controls="reference-content">${e(t(labels.en[i+1]))}</button>`).join('')}</nav><div id="reference-content" role="tabpanel" aria-labelledby="reference-tab-${st.tab}">${body}</div>`;
 }
 async function selectTab(tab){st.tab=tab;const url=new URL(location.href);url.searchParams.set('tab',tab);history.replaceState(null,'',url.pathname+url.search+url.hash);if(tab==='suppliers'&&!offers){loadingOffers=true;draw();try{offers=(await read('/autolink/public/vehicles?limit=25&brand='+encodeURIComponent(model.brand)+'&model='+encodeURIComponent(model.model))).filter(v=>v.model_id===model.id);}catch(error){loadingOffers=false;draw();host.querySelector('#reference-content').innerHTML=`<div class="alert error" role="alert">${e(plain(error.message))} <button class="btn secondary" data-reference-offers-retry>${e(t('Retry'))}</button></div>`;return;}loadingOffers=false;}draw();}
 host.addEventListener('click',event=>{const b=event.target.closest('button');if(!b||b.disabled)return;
  if(b.hasAttribute('data-reference-tab'))selectTab(b.dataset.referenceTab);
  else if(b.hasAttribute('data-reference-offers-retry'))selectTab('suppliers');
  else if(b.hasAttribute('data-reference-add')){const {choices}=selectionForYear(data,st.year,st.ids),next=choices.find(v=>!st.ids.includes(v.id));if(next&&st.ids.length<4){st.ids.push(next.id);draw();}}
  else if(b.hasAttribute('data-reference-remove')){st.ids.splice(Number(b.dataset.referenceRemove),1);draw();}
  else if(b.hasAttribute('data-reference-photo-category')){st.category=b.dataset.referencePhotoCategory;st.photoIndex=0;draw();}
  else if(b.hasAttribute('data-reference-photo-index')){st.photoIndex=Number(b.dataset.referencePhotoIndex);draw();}
  else if(b.hasAttribute('data-reference-photo-step')){st.photoIndex+=Number(b.dataset.referencePhotoStep);draw();}
 });
 host.addEventListener('change',event=>{const input=event.target;
  if(input.hasAttribute('data-reference-year')){st.year=Number(input.value);st.ids=[];draw();}
  else if(input.hasAttribute('data-reference-trim')){st.ids[Number(input.dataset.referenceTrim)]=input.value;draw();}
  else if(input.hasAttribute('data-reference-differences')){st.diff=input.checked;draw();}
  else if(input.hasAttribute('data-reference-photo-trim')){st.photoTrim=input.value;st.photoIndex=0;draw();}
 });
 host.addEventListener('input',event=>{if(!event.target.hasAttribute('data-reference-search'))return;st.query=event.target.value;const pos=event.target.selectionStart;draw();const input=host.querySelector('[data-reference-search]');input.focus({preventScroll:true});input.setSelectionRange(pos,pos);});
 draw();if(st.tab==='suppliers')await selectTab('suppliers');
}
