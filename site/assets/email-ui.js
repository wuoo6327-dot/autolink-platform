/* Email authentication extends the existing React login card without changing Google/Meta. */
(() => {
  if (!location.pathname.startsWith('/merchant/')) return;
  let mode = new URLSearchParams(location.search).get('reset')==='1'?'reset':'password', cooldownUntil = 0, emailValue = '', codeValue = '', companyValue = '', busy = false;
  const id = 'autolink-email-auth';
  const zh = () => (document.querySelector('.merchant-auth-card-heading h2')?.textContent || '').includes('欢迎');
  const language=()=>{const value=window.businessI18n?.language||new URLSearchParams(location.search).get('lang')||document.documentElement.lang;return zh()||value==='zh-CN'?'zh':['en','zh','ar','ru','kk','uz','ko','fr','sw'].includes(value)?value:'en';};
  const word = (cn,en) => window.AUTOLINK_BUSINESS_RESOURCES?.[language()]?.translation?.[en]||(language()==='zh'?cn:en);
  const escape = s => String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const request = async (url, body) => {
    let response;
    try {
      response = await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
      const result = await response.json();
      if (!response.ok || result?.code!==200) throw Object.assign(new Error(typeof result?.msg==='string'?result.msg:'Request failed.'),{status:response.ok?Number(result?.code):response.status});
      return result.data;
    } catch(error) { throw window.businessI18n?.apiError?.(error,response?.status)||Error(word('请求失败，请重试。','Request failed. Please retry.')); }
  };
  const status = (message,error=false) => {const box=document.querySelector(`#${id} .email-status`);if(box){box.textContent=message;box.classList.toggle('error',error);}};
  const saveFields = () => {const form=document.getElementById(id);if(form){emailValue=form.querySelector('[name=email]')?.value||emailValue;codeValue=form.querySelector('[name=code]')?.value||codeValue;companyValue=form.querySelector('[name=companyName]')?.value||companyValue;}};
  const render = () => {
    const form=document.getElementById(id);if(!form)return;
    const code=mode!=='password', showPassword=mode!=='code';
    form.innerHTML=`<div class="email-tabs" role="tablist" aria-label="${word('登录方式','Sign-in method')}"><button type="button" role="tab" data-mode="password" aria-selected="${mode==='password'}">${word('密码登录','Password Login')}</button><button type="button" role="tab" data-mode="code" aria-selected="${mode==='code'}">${word('验证码登录','Email Code Login')}</button></div><label>${word('邮箱','Email')}<input name="email" type="email" required autocomplete="email" value="${escape(emailValue)}" placeholder="you@company.com"></label><label ${showPassword?'':'hidden'}>${word(mode==='reset'?'新密码':'密码',mode==='reset'?'New password':'Password')}<input name="password" type="password" minlength="8" ${showPassword?'required':''} autocomplete="${mode==='reset'?'new-password':'current-password'}"></label><label ${mode==='code'?'':'hidden'}>${word('公司名称','Company Name')}<input name="companyName" type="text" maxlength="160" autocomplete="organization" value="${escape(companyValue)}"></label><label ${mode==='reset'?'':'hidden'}>${word('确认新密码','Confirm new password')}<input name="confirm" type="password" minlength="8" ${mode==='reset'?'required':''} autocomplete="new-password"></label><label ${code?'':'hidden'}>${word('验证码','Verification Code')}<span class="email-code-line"><input name="code" type="text" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" ${code?'required':''} autocomplete="one-time-code" value="${escape(codeValue)}" placeholder="000000"><button type="button" data-send-code>${word('获取验证码','Send Code')}</button></span></label><div class="email-options" ${mode==='password'?'':'hidden'}><label><input type="checkbox" name="remember">${word('保持登录','Keep me signed in')}</label><button type="button" data-mode="reset">${word('忘记密码？','Forgot password?')}</button></div><label class="email-consent" ${mode==='code'?'':'hidden'}><input type="checkbox" name="consent"><span>${word('新账号注册时，我同意','For a new account, I agree to the')} <a href="/terms" target="_blank">${word('服务条款','Terms')}</a> ${word('和','and')} <a href="/privacy" target="_blank">${word('隐私政策','Privacy Policy')}</a></span></label><button class="back-login" type="button" data-mode="password" ${mode==='reset'?'':'hidden'}>${word('返回登录','Back to sign in')}</button><div class="email-status" role="status" aria-live="polite"></div><button class="email-submit" type="submit">${mode==='reset'?word('重置密码','Reset Password'):mode==='code'?word('登录 / 注册','Continue'):word('登录','Log In')}</button>`;
    refreshCountdown();
  };
  const refreshCountdown = () => {
    const button=document.querySelector(`#${id} [data-send-code]`);if(!button)return;
    const remaining=Math.max(0,Math.ceil((cooldownUntil-Date.now())/1000));
    button.disabled=busy||remaining>0||(mode==='code'&&!document.querySelector(`#${id} [name=consent]`)?.checked);
    button.textContent=busy?word('发送中…','Sending…'):remaining?`${remaining}s`:word('获取验证码','Send Code');
  };
  setInterval(refreshCountdown,1000);
  async function sendCode() {
    const form=document.getElementById(id),input=form.querySelector('[name=email]');
    if(!input.reportValidity())return;
    if(mode==='code'&&!form.querySelector('[name=consent]')?.checked){status(word('请先同意服务条款和隐私政策。','Agree to the Terms and Privacy Policy first.'),true);return;}
    if(busy||cooldownUntil>Date.now())return;
    saveFields();busy=true;refreshCountdown();status('');
    try {await request('/autolink/auth/email/send-code',{email:emailValue,purpose:mode==='reset'?'reset_password':'login',consent:mode==='code',language:language()});cooldownUntil=Date.now()+60000;status(word('验证码已发送','Verification code sent'));}
    catch(e){status(window.businessI18n?.errorText?.(e,e.status)||word('验证码发送失败，请稍后重试。','Failed to send verification code. Please try again.'),true);}
    finally{busy=false;refreshCountdown();}
  }
  async function submit(event) {
    event.preventDefault();const form=event.currentTarget;
    if(!form.reportValidity()||busy)return;
    saveFields();const data=new FormData(form);busy=true;form.querySelector('.email-submit').disabled=true;status(word('正在处理…','Working…'));
    try {
      if(mode==='reset') {
        if(data.get('password')!==data.get('confirm'))throw Error(word('两次密码不一致。','Passwords do not match.'));
        await request('/autolink/auth/password/reset',{email:emailValue,code:String(data.get('code')||''),password:String(data.get('password')||'')});
        mode='password';codeValue='';render();status(word('密码已更新，请登录。','Password updated. Sign in now.'));return;
      }
      const result=mode==='password'?await request('/autolink/auth/password/login',{email:emailValue,password:String(data.get('password')||''),remember:!!data.get('remember'),role:'MERCHANT'}):await request('/autolink/auth/email/login',{email:emailValue,code:String(data.get('code')||''),consent:!!data.get('consent'),remember:!!data.get('remember'),language:language(),role:'MERCHANT',companyName:companyValue.trim()});
      const role=result.role;
      if(!['BUYER','MERCHANT','SUPPLIER','ADMIN','PLATFORM_ADMIN'].includes(role))throw Error(word('账号角色未配置。','Account role is not configured.'));
      if(role==='MERCHANT'||role==='SUPPLIER'||(role==='ADMIN'||role==='PLATFORM_ADMIN'))localStorage.setItem('autolink-cookie-session','1');
      location.assign(role==='BUYER'?'/buyer':(role==='ADMIN'||role==='PLATFORM_ADMIN')?'/admin':'/supplier');
    } catch(e) {status(window.businessI18n?.errorText?.(e,e.status)||word('登录失败，请重试。','Sign-in failed. Please retry.'),true);}
    finally{busy=false;const button=form.querySelector('.email-submit');if(button)button.disabled=false;}
  }
  function attach() {
    const old=document.querySelector('.merchant-auth-form-wrap form.trade-login');
    if(!old||document.getElementById(id))return;
    const form=document.createElement('form');form.id=id;form.className='autolink-email-auth';old.before(form);
    render();
    form.addEventListener('click',event=>{const switcher=event.target.closest('[data-mode]');if(switcher){saveFields();mode=switcher.dataset.mode;codeValue='';render();return;}if(event.target.closest('[data-send-code]'))sendCode();});
    form.addEventListener('submit',submit);
    form.addEventListener('change',event=>{if(event.target.name==='consent')refreshCountdown();});
  }
  new MutationObserver(attach).observe(document.documentElement,{childList:true,subtree:true});
  attach();
})();
