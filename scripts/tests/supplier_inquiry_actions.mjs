// Run the actual supplier entry and registered click handlers with synthetic
// responses. No browser, production request or real business data is used.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const source=fs.readFileSync(new URL('../../site/supplier/app.js',import.meta.url),'utf8');

async function page({rejectWrite=false,holdWrite=false}={}) {
  const requests=[],listeners=new Map();
  const root={innerHTML:''};
  const content={alert:'',querySelector:()=>null,insertAdjacentHTML(_position,html){this.alert=html;}};
  const inquiry={id:'INQ-CLICK/QA&01',status:'SUBMITTED',quantity:2,
    destination_country:'Synthetic QA country',buyer_company:'Synthetic QA buyer',currency:'USD'};
  let releaseWrite;
  const writeGate=holdWrite?new Promise(resolve=>{releaseWrite=resolve;}):Promise.resolve();
  const document={querySelector:selector=>selector==='#app'?root:selector==='#supplier-content'?content:null,
    addEventListener(type,handler){if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(handler);}};
  const window={addEventListener(){},businessI18n:{language:'en',locale:'en-US',text:value=>value,
    languageControl:()=>'',apiError:error=>error}};
  const location=new URL('https://synthetic.invalid/supplier/inquiries/INQ-ROUTE-QA');
  const context=vm.createContext({document,window,location,URL,URLSearchParams,AbortController,AbortSignal,
    localStorage:{getItem:()=>null,setItem(){}},
    fetch:async(path,options)=>{
      requests.push({path,method:options.method,headers:options.headers,
        credentials:options.credentials,body:options.body?JSON.parse(options.body):undefined});
      if(options.method==='PUT'){
        await writeGate;
        if(rejectWrite)return {ok:false,status:403,json:async()=>({code:403,msg:'Synthetic access denied.'})};
        inquiry.status=JSON.parse(options.body).status;
        return {ok:true,status:200,json:async()=>({code:200,data:{...inquiry}})};
      }
      let data;
      if(path==='/autolink/me')data={id:'supplier-qa',role:'BUYER',capabilities:{supplier:true},companyName:'Synthetic QA company'};
      else if(path==='/autolink/supplier/contexts')data=[{supplier_id:'supplier-qa',company_name:'Synthetic QA company',role:'OWNER',status:'APPROVED'}];
      else if(path==='/autolink/supplier/application')data={status:'APPROVED'};
      else if(path.startsWith('/autolink/supplier/inquiries/'))data={...inquiry};
      else throw Error('Unexpected synthetic request: '+path);
      return {ok:true,status:200,json:async()=>({code:200,data})};
    }});
  vm.runInContext(source,context);
  // Await actual route rendering; the built-in initial start is also exercised.
  await vm.runInContext('start()',context);
  const button={dataset:{action:'inquiry-viewed',id:inquiry.id},disabled:false};
  const click=()=>Promise.all((listeners.get('click')||[]).map(handler=>handler({
    button:0,defaultPrevented:false,target:{closest:selector=>selector==='[data-action]'?button:null}})));
  return {root,content,requests,inquiry,button,click,releaseWrite};
}

test('read-only detail renders a button; its click PUTs VIEWED and reloads the actual route',async()=>{
  const p=await page();
  assert.match(p.root.innerHTML,/data-action="inquiry-viewed"/);
  assert.ok(p.requests.every(request=>request.method==='GET'));
  assert.equal(p.inquiry.status,'SUBMITTED');
  const before=p.requests.length;
  await p.click();
  const writes=p.requests.filter(request=>request.method!=='GET');
  assert.equal(writes.length,1);
  assert.equal(writes[0].method,'PUT');
  assert.equal(writes[0].path,'/autolink/supplier/inquiries/INQ-CLICK%2FQA%2601');
  assert.deepEqual(writes[0].body,{status:'VIEWED'});
  assert.equal(writes[0].headers['X-Autolink-Supplier'],'supplier-qa');
  assert.equal(writes[0].credentials,'same-origin');
  assert.equal(p.inquiry.status,'VIEWED');
  assert.ok(p.requests.slice(before+1).some(request=>request.method==='GET'&&request.path.startsWith('/autolink/supplier/inquiries/')));
  assert.doesNotMatch(p.root.innerHTML,/data-action="inquiry-viewed"/);
});

test('failed PUT keeps inquiry unread, shows the error and permits retry',async()=>{
  const p=await page({rejectWrite:true});
  await p.click();
  assert.equal(p.inquiry.status,'SUBMITTED');
  assert.equal(p.button.disabled,false);
  assert.equal(p.button.dataset.busy,undefined);
  assert.match(p.content.alert,/Synthetic access denied/);
  assert.match(p.root.innerHTML,/data-action="inquiry-viewed"/);
});

test('a second click while PUT is pending cannot submit a duplicate mutation',async()=>{
  const p=await page({holdWrite:true});
  const first=p.click();
  assert.equal(p.button.disabled,true);
  await p.click();
  assert.equal(p.requests.filter(request=>request.method==='PUT').length,1);
  p.releaseWrite();
  await first;
  assert.equal(p.inquiry.status,'VIEWED');
});
