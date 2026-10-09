(() => {
  const form=document.getElementById('agreement-confirmation');
  const body=document.getElementById('agreement-body');
  const button=document.getElementById('agreement-confirm');
  const status=document.getElementById('agreement-confirmation-status');
  const next=document.getElementById('agreement-next');
  let signed=false,busy=false,ready=false;
  const checked=()=>form.elements.agreement.checked&&form.elements.privacy.checked;
  function update(){button.disabled=!ready||signed||busy||!checked();}
  function confirmed(data){
    const sameVersion=data.version===body.dataset.version&&data.bodySha256===body.dataset.bodySha256;
    ready=data.acceptanceEnabled===true&&sameVersion;
    if(!ready){status.textContent=data.acceptanceEnabled===true?'协议版本已更新，请刷新页面并阅读最新正式协议后再确认。':'正式协议及运营资料尚未就绪，入驻暂未开放；可返回入驻页保存企业草稿。';next.hidden=false;update();return;}
    update();if(!data.confirmation)return;
    signed=true;button.textContent='已确认签署';
    status.textContent='确认记录：'+data.confirmation.id;
    next.hidden=false;form.querySelectorAll('input').forEach(input=>input.disabled=true);update();
  }
  async function request(method,payload){
    const response=await fetch('/autolink/supplier/agreement',{method,credentials:'same-origin',cache:'no-store',
      headers:method==='POST'?{'Content-Type':'application/json'}:{},
      body:payload?JSON.stringify(payload):undefined});
    const result=await response.json();
    if(!response.ok||result.code!==200){const error=new Error(result.msg||'暂时无法确认，请重试。');error.status=response.status;throw error;}
    return result.data;
  }
  const errors={
    'Supplier onboarding is not open: the final agreement and operator details are not ready.':'正式协议及运营资料尚未就绪，入驻暂未开放；可保存企业草稿。',
    'Only the company owner can confirm this agreement.':'仅企业负责人可确认本协议。',
    'Verify your email before applying as a supplier.':'请先完成邮箱验证。',
    'Supplier account required.':'请使用商家或供应商账号登录。',
    'Invalid agreement confirmation fields.':'确认信息不完整，请刷新页面。',
    'Confirm your authorization, the agreement and the privacy policy.':'请勾选协议与隐私政策确认项。',
    'Agreement version changed. Reload before confirming.':'协议已更新，请刷新页面并重新阅读。',
    'A verified active supplier account is required.':'请使用已验证邮箱的有效账号。',
    'Save your company name, registration number and address before confirming.':'请先在入驻页保存企业名称、注册号码和注册地址。'
  };
  form.addEventListener('change',update);
  form.addEventListener('submit',async event=>{
    event.preventDefault();if(!ready||busy||signed||!checked())return;
    busy=true;update();status.textContent='正在确认…';
    try{confirmed(await request('POST',{version:body.dataset.version,bodySha256:body.dataset.bodySha256,
      consent:true,authorized:true,privacyAcknowledged:true}));}
    catch(error){
      if(error.status===401){location.href='/merchant/login?returnTo=%2Fsupplier%2Fapplication';return;}
      status.textContent=errors[error.message]||'暂时无法确认，请重试。';next.hidden=false;
    }finally{busy=false;update();}
  });
  update();
  request('GET').then(confirmed).catch(error=>{
    ready=false;update();next.hidden=false;status.textContent=error.status===401?'请先登录，并在入驻页保存企业资料。':errors[error.message]||'确认服务暂时不可用，请稍后重试。';
  });
})();
