// Compatible controls: selections are stored in the existing text fields.
(() => {
 const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const codes='AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT ZA ZM ZW'.split(' ');
 const languages=['en','zh','ar','ru','kk','uz','ko','fr','sw'];
 const english=new Intl.DisplayNames(['en'],{type:'region'});
 const normalize=value=>String(value||'').trim().toLocaleLowerCase().replace(/\s+/g,' ');
 let regionChoices;
 function regions(){
   if(!regionChoices){
     const names=languages.map(lang=>new Intl.DisplayNames([lang],{type:'region'}));
     regionChoices=codes.map(code=>({value:english.of(code),code,aliases:[code,english.of(code),...names.map(display=>display.of(code))]}));
   }
   const display=new Intl.DisplayNames([window.businessI18n.locale],{type:'region'});
   return regionChoices.map(r=>({...r,label:display.of(r.code)})).sort((a,b)=>a.label.localeCompare(b.label,window.businessI18n.locale));
 }
 function country(value,city){
   const options=regions();
   if(['china','cn','中国'].includes(normalize(value))&&/^(hong ?kong|香港|hk)$/i.test(String(city).trim()))value=options.find(r=>r.code==='HK').value;
   if(['china','cn','中国'].includes(normalize(value))&&/^(macao|macau|澳门|mo)$/i.test(String(city).trim()))value=options.find(r=>r.code==='MO').value;
   const chosen=options.find(r=>r.aliases.some(a=>normalize(a)===normalize(value)));
   if(value&&!chosen)options.unshift({value,label:value});
   return `<select name="country" required><option value="">${escape(window.businessI18n.text('Select country or region'))}</option>${options.map(r=>`<option value="${escape(r.value)}" ${r===chosen||(!chosen&&r.value===value)?'selected':''}>${escape(r.label)}</option>`).join('')}</select>`;
 }
 function values(value){return [...new Set(String(value||'').split(/[,，;；\n]+/).map(v=>v.trim()).filter(Boolean))];}
 function choices(kind,brands){
   if(kind==='mainBrands')return brands.map(b=>({value:b.name,label:b.name,aliases:[b.name]}));
   const broad=['Middle East','Central Asia','East Asia','Southeast Asia','Africa','Europe','North America','South America','Oceania'].map(value=>({value,label:window.businessI18n.text(value),aliases:[value,window.businessI18n.text(value)]}));
   return [...broad,...regions()];
 }
 function multi(kind,label,value,brands=[]){
   const options=choices(kind,brands),selected=[];
   for(const token of values(value)){
     let option=options.find(r=>r.aliases.some(a=>normalize(a)===normalize(token)));
     if(!option){option={value:token,label:token,aliases:[token]};options.push(option);}
     if(!selected.includes(option.value))selected.push(option.value);
   }
   const summary=options.filter(r=>selected.includes(r.value)).map(r=>r.label).join('、')||window.businessI18n.text('Choose one or more');
   return `<div class="field"><span id="label-${kind}">${escape(window.businessI18n.text(label))}</span><input type="hidden" name="${kind}" value="${escape(selected.join(', '))}"><details class="seller-multi" data-company-multi="${kind}"><summary>${escape(summary)}</summary><div class="seller-multi-menu"><input type="search" data-choice-filter placeholder="${escape(window.businessI18n.text('Search options'))}" aria-label="${escape(window.businessI18n.text('Search options'))}"><div class="seller-multi-options" role="group" aria-labelledby="label-${kind}">${options.map(r=>`<label class="seller-multi-option"><input type="checkbox" value="${escape(r.value)}" ${selected.includes(r.value)?'checked':''}><span>${escape(r.label)}</span></label>`).join('')}</div><div class="seller-multi-add"><input data-choice-custom maxlength="100" aria-label="${escape(window.businessI18n.text('Other option'))}" placeholder="${escape(window.businessI18n.text('Other option'))}"><button type="button" class="btn secondary" data-choice-add>${escape(window.businessI18n.text('Add'))}</button></div></div></details></div>`;
 }
 function sync(details){
   const selected=[...details.querySelectorAll('input[type=checkbox]:checked')];
   const hidden=details.closest('.field').querySelector('input[type=hidden]');
   const joined=selected.map(input=>input.value).join(', ');
   if(joined.length>500){return false;}
   hidden.value=joined;
   details.querySelector('summary').textContent=selected.map(input=>input.nextElementSibling.textContent).join('、')||window.businessI18n.text('Choose one or more');
   hidden.dispatchEvent(new Event('input',{bubbles:true}));return true;
 }
 document.addEventListener('change',event=>{
   if(!event.target.matches('[data-company-multi] input[type=checkbox]'))return;
   if(!sync(event.target.closest('details'))){event.target.checked=!event.target.checked;sync(event.target.closest('details'));}
 });
 document.addEventListener('input',event=>{
   if(!event.target.matches('[data-choice-filter]'))return;
   const query=normalize(event.target.value);
   event.target.closest('details').querySelectorAll('.seller-multi-option').forEach(option=>{option.hidden=!normalize(option.textContent+' '+option.querySelector('input').value).includes(query);});
 });
 document.addEventListener('click',event=>{
   const button=event.target.closest('[data-choice-add]');if(!button)return;
   const details=button.closest('details'),input=details.querySelector('[data-choice-custom]'),value=input.value.trim();
   if(!value||/[,，;；\n]/.test(value))return;
   let checkbox=[...details.querySelectorAll('input[type=checkbox]')].find(c=>normalize(c.value)===normalize(value));
   if(!checkbox){
     const label=document.createElement('label');label.className='seller-multi-option';
     checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.value=value;
     const span=document.createElement('span');span.textContent=value;label.append(checkbox,span);details.querySelector('.seller-multi-options').append(label);
   }
   checkbox.checked=true;
   if(!sync(details)){checkbox.checked=false;sync(details);return;}
   input.value='';
 });
 window.autolinkCompanyFields={country,multi,values};
})();
