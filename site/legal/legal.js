(()=>{
  const key='autolink-privacy-v1';
  const lang=localStorage.getItem('autolink-language')==='zh'?'zh':'en';
  function setLanguage(value){document.documentElement.dataset.language=value;document.documentElement.lang=value==='zh'?'zh-CN':'en';document.querySelectorAll('[data-set-language]').forEach(button=>button.setAttribute('aria-pressed',String(button.dataset.setLanguage===value)));localStorage.setItem('autolink-language',value)}
  setLanguage(lang);
  document.querySelectorAll('[data-set-language]').forEach(button=>button.addEventListener('click',()=>setLanguage(button.dataset.setLanguage)));
  const dialog=document.createElement('dialog');
  dialog.innerHTML='<h2>Cookie Settings / Cookie 设置</h2><p>Essential storage is always active. Optional choices can be changed at any time. / 必要存储始终启用，可随时调整可选项目。</p><label><input type="checkbox" checked disabled><span>Necessary / 必要</span></label><label><input id="analytics-choice" type="checkbox"><span>Visit statistics / 访问统计</span></label><label><input id="advertising-choice" type="checkbox"><span>Advertising preferences / 广告偏好</span></label><div class="actions"><button type="button" data-choice="necessary">Necessary only / 仅必要</button><button type="button" data-choice="save" class="primary">Save / 保存</button><button type="button" data-choice="all">Accept all / 全部接受</button><button type="button" data-choice="close">Close / 关闭</button></div>';
  document.body.append(dialog);
  const analytics=dialog.querySelector('#analytics-choice'),advertising=dialog.querySelector('#advertising-choice');
  function open(){try{const choice=JSON.parse(localStorage.getItem(key)||'null');analytics.checked=choice?.version===1&&choice.expiresAt>Date.now()&&choice.analytics===true;advertising.checked=choice?.version===1&&choice.expiresAt>Date.now()&&choice.advertising===true}catch{analytics.checked=false;advertising.checked=false}dialog.showModal()}
  function save(a,b){const now=Date.now();localStorage.setItem(key,JSON.stringify({version:1,analytics:a,advertising:b,savedAt:now,expiresAt:now+180*864e5}));if(!a)localStorage.removeItem('autolink-anonymous-visit-v1');dialog.close()}
  document.querySelectorAll('[data-cookie-settings]').forEach(button=>button.addEventListener('click',open));
  dialog.addEventListener('click',event=>{const choice=event.target?.dataset?.choice;if(choice==='necessary')save(false,false);if(choice==='all')save(true,true);if(choice==='save')save(analytics.checked,advertising.checked);if(choice==='close')dialog.close()});
  const action=document.querySelector('[data-account-action]');
  if(action){
    function session(){for(const storage of [localStorage,sessionStorage]){try{const saved=JSON.parse(storage.getItem('autolink-business-session')||'null');if(saved&&typeof saved.token==='string'&&saved.expiresAt>Date.now())return saved.token}catch{}}return ''}
    const token=session(),button=action.querySelector('[data-delete-account]'),login=action.querySelector('[data-account-login]'),status=action.querySelector('[data-account-status]');
    button.hidden=!token;login.hidden=!!token;
    status.textContent=token?'Signed in / 已登录':'Sign in first to delete your account, or email the privacy contact above. / 请先登录后删除账号，或联系上述隐私邮箱。';
    button.addEventListener('click',async()=>{
      if(!window.confirm('Permanently delete your AUTOLINK account and end all sessions? / 确定永久删除 AUTOLINK 账号并终止所有会话？'))return;
      button.disabled=true;status.textContent='Deleting account… / 正在删除账号…';
      try{const response=await fetch('/autolink/me',{method:'DELETE',headers:{Authorization:'Bearer '+token},cache:'no-store'});const payload=await response.json();if(!response.ok||payload.code!==200)throw Error(payload.msg||'Could not delete account');localStorage.removeItem('autolink-business-session');sessionStorage.removeItem('autolink-business-session');window.location.assign('/merchant/login')}
      catch(error){status.textContent=(error.message||'Request failed')+' / 删除未完成';button.disabled=false}
    });
  }
})();
