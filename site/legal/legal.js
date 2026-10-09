(()=>{
  const key='autolink-privacy-v1';
  function storage(name,operation){try{return operation(window[name])}catch{return null}}
  const requested=new URLSearchParams(location.search).get('lang');
  const lang=(requested||storage('localStorage',s=>s.getItem('autolink-language')))==='zh'?'zh':'en';
  function setLanguage(value){document.documentElement.dataset.language=value;document.documentElement.lang=value==='zh'?'zh-CN':'en';document.querySelectorAll('[data-set-language]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.setLanguage===value)));storage('localStorage',s=>s.setItem('autolink-language',value))}
  setLanguage(lang);
  document.querySelectorAll('[data-set-language]').forEach(button=>button.addEventListener('click',()=>setLanguage(button.dataset.setLanguage)));
  const dialog=document.createElement('dialog');
  dialog.innerHTML='<h2>Cookie Settings / Cookie 设置</h2><p>Essential storage is always active. Optional choices can be changed at any time. / 必要存储始终启用，可随时调整可选项目。</p><label><input type="checkbox" checked disabled><span>Necessary / 必要</span></label><label><input id="analytics-choice" type="checkbox"><span>Visit statistics / 访问统计</span></label><label><input id="advertising-choice" type="checkbox"><span>Advertising preferences / 广告偏好</span></label><div class="actions"><button type="button" data-choice="necessary">Necessary only / 仅必要</button><button type="button" data-choice="save" class="primary">Save / 保存</button><button type="button" data-choice="all">Accept all / 全部接受</button><button type="button" data-choice="close">Close / 关闭</button></div>';
  document.body.append(dialog);
  const analytics=dialog.querySelector('#analytics-choice'),advertising=dialog.querySelector('#advertising-choice');
  function open(){try{const choice=JSON.parse(storage('localStorage',s=>s.getItem(key))||'null');analytics.checked=choice?.version===1&&choice.expiresAt>Date.now()&&choice.analytics===true;advertising.checked=choice?.version===1&&choice.expiresAt>Date.now()&&choice.advertising===true}catch{analytics.checked=false;advertising.checked=false}dialog.showModal()}
  function save(a,b){const now=Date.now();storage('localStorage',s=>{s.setItem(key,JSON.stringify({version:1,analytics:a,advertising:b,savedAt:now,expiresAt:now+180*864e5}));if(!a)s.removeItem('autolink-anonymous-visit-v1')});dialog.close()}
  document.querySelectorAll('[data-cookie-settings]').forEach(button=>button.addEventListener('click',open));
  dialog.addEventListener('click',event=>{const choice=event.target?.dataset?.choice;if(choice==='necessary')save(false,false);if(choice==='all')save(true,true);if(choice==='save')save(analytics.checked,advertising.checked);if(choice==='close')dialog.close()});
  const action=document.querySelector('[data-account-action]');
  if(action){
    const button=action.querySelector('[data-delete-account]'),login=action.querySelector('[data-account-login]'),status=action.querySelector('[data-account-status]');
    const retry=action.querySelector('[data-account-retry]');
    let authorized=false,busy=false,legacyToken='';
    function legacySession(){
      for(const name of ['localStorage','sessionStorage']){
        const raw=storage(name,s=>s.getItem('autolink-business-session'));
        try{const saved=JSON.parse(raw||'null');if(saved&&typeof saved.token==='string'&&saved.token&&saved.expiresAt>Date.now())return saved.token}catch{}
      }
      return '';
    }
    function headers(){return legacyToken?{Authorization:'Bearer '+legacyToken}:{}}
    async function current(token=''){
      const response=await fetch('/autolink/me',{credentials:'same-origin',cache:'no-store',headers:token?{Authorization:'Bearer '+token}:{}});
      const payload=await response.json();return {response,payload};
    }
    async function load(){
      if(busy)return;
      busy=true;authorized=false;legacyToken='';button.hidden=true;login.hidden=true;if(retry)retry.hidden=true;
      status.textContent='Checking sign-in… / 正在检查登录状态…';
      try{
        let result=await current();
        if(result.response.status===401){const candidate=legacySession();if(candidate){result=await current(candidate);if(result.response.ok&&result.payload.code===200)legacyToken=candidate}}
        const {response,payload}=result;
        if(response.status===401){login.hidden=false;status.textContent='Sign in to close your account. / 请先登录后关闭账号。';return}
        if(!response.ok||payload.code!==200)throw Error(payload.msg||'Could not verify sign-in / 无法确认登录状态');
        authorized=payload.data?.accountDeletionAllowed===true;button.hidden=!authorized;button.disabled=false;
        status.textContent=authorized?'Signed in. Closing your account ends all sessions. / 已登录，关闭账号后所有会话将失效。':'Self-service deletion is unavailable for this account. Platform owners and the last active administrator are protected. / 此账号不能自助删除；平台所有者及最后一个有效管理员受到保护。';
      }catch(error){status.textContent=(error.message||'Request failed')+' / 登录状态检查未完成，请重试。';if(retry)retry.hidden=false}
      finally{busy=false}
    }
    login.href='/buyer/login?returnTo='+encodeURIComponent(location.pathname||'/account-deletion')+'&lang='+document.documentElement.dataset.language;
    if(retry)retry.addEventListener('click',load);
    button.addEventListener('click',async()=>{
      if(!authorized||busy)return;
      if(!window.confirm('Close your AUTOLINK account and end all sessions? Necessary history will be retained. / 确定关闭 AUTOLINK 账号并终止所有会话？必要历史记录会保留。'))return;
      busy=true;button.disabled=true;status.textContent='Closing account… / 正在关闭账号…';
      try{
        const response=await fetch('/autolink/me',{method:'DELETE',credentials:'same-origin',headers:headers(),cache:'no-store'});
        const payload=await response.json();if(!response.ok||payload.code!==200){if(response.status===401||response.status===403){authorized=false;button.hidden=true;login.hidden=response.status!==401}throw Error(payload.msg||'Could not close account')}
        for(const name of ['localStorage','sessionStorage'])storage(name,s=>{s.removeItem('autolink-business-session');s.removeItem('autolink-cookie-session')});
        authorized=false;window.location.assign('/buyer/login?lang='+document.documentElement.dataset.language);
      }catch(error){status.textContent=(error.message||'Request failed')+' / 账号关闭未完成';button.disabled=false}
      finally{busy=false}
    });
    load();
  }
})();
