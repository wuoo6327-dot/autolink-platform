// Exercise actual public trade event handlers with isolated synthetic responses.
// This test never calls the production website or creates real business data.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import test from 'node:test';

const source=fs.readFileSync(new URL('../../site/trade/app.js',import.meta.url),'utf8');
async function page(account) {
  const requests=[],listeners=new Map(),root={innerHTML:'',dataset:{}};
  const message={};
  const panel={hidden:true,scrollIntoView(){}};
  const document={documentElement:{},querySelector:s=>s==='#app'?root:s==='#trade-message'?message:s==='#inquiry-panel'?panel:null,
    addEventListener(type,handler){if(!listeners.has(type))listeners.set(type,[]);listeners.get(type).push(handler);}};
  const window={addEventListener(){},businessI18n:{text:x=>x,language:'en',locale:'en-US',languageControl:()=>'',apiError:e=>e}};
  let address=new URL('https://synthetic.invalid/trade/unknown');
  const location=new Proxy({}, {get:(_object,key)=>address[key],set:(_object,key,value)=>{if(key==='href')address=new URL(value,address);else address[key]=value;return true;}});
  class SyntheticFormData {constructor(form){this.values=form.values;}[Symbol.iterator](){return Object.entries(this.values)[Symbol.iterator]();}}
  const context=vm.createContext({document,window,location,URL,URLSearchParams,AbortController,AbortSignal,DOMException,
    FormData:SyntheticFormData,localStorage:{getItem:()=>null,setItem(){}},
    fetch:async(path,options)=>{
      requests.push({path,method:options.method,credentials:options.credentials,body:options.body?JSON.parse(options.body):undefined});
      const data=path==='/autolink/me'?account:{id:'SYNTHETIC-INQUIRY'};
      return {ok:true,status:200,json:async()=>({code:200,data})};
    }});
  vm.runInContext(source,context);
  await vm.runInContext('start()',context);
  vm.runInContext("currentListing={id:'SYNTHETIC-LISTING',supplier_id:'SYNTHETIC-SUPPLIER'};currentSupplier={id:'SYNTHETIC-SUPPLIER'};",context);
  const dispatch=(type,event)=>Promise.all((listeners.get(type)||[]).map(fn=>fn(event)));
  const click=action=>dispatch('click',{button:0,defaultPrevented:false,preventDefault(){},target:{closest:s=>s==='[data-action]'?{dataset:{action}}:null}});
  const submit=()=>dispatch('submit',{preventDefault(){},target:{id:'inquiry-form',querySelector:()=>({disabled:false}),
    values:{quantity:'2',destinationCountry:'Synthetic QA',destinationPort:'Synthetic port',incoterm:'FOB',targetPrice:'123',message:'Synthetic test only'}}});
  return {requests,location,click,submit,panel,role:()=>vm.runInContext('me?.role',context)};
}

for(const account of [{role:'BUYER',capabilities:{buyer:true}},{role:'MERCHANT',capabilities:{buyer:true}},
  {role:'SUPPLIER',capabilities:{buyer:true}},{role:'MERCHANT'},{role:'SUPPLIER'}]) {
  test(`${account.role}/${account.capabilities?'capability':'legacy'} can save and inquire without losing its role`,async()=>{
    const p=await page(account);
    await p.click('quote');assert.equal(p.panel.hidden,false);
    await p.click('save');await p.click('save-supplier');await p.submit();
    const writes=p.requests.filter(r=>r.method==='POST');
    assert.deepEqual(writes.map(r=>r.path),['/autolink/buyer/saved-listings','/autolink/buyer/saved-suppliers','/autolink/buyer/inquiries']);
    assert.ok(writes.every(r=>r.credentials==='same-origin'));
    assert.deepEqual(writes[2].body,{listingId:'SYNTHETIC-LISTING',quantity:2,destinationCountry:'Synthetic QA',destinationPort:'Synthetic port',incoterm:'FOB',targetPriceMinor:12300,message:'Synthetic test only'});
    assert.equal(p.role(),account.role);
    assert.equal(p.location.pathname,'/buyer/inquiries/SYNTHETIC-INQUIRY');
  });
}
for(const account of [null,{role:'ADMIN'},{role:'MERCHANT',capabilities:{buyer:false}}]) {
  test(`${account?.role||'anonymous'}/${account?.capabilities?'denied capability':'default'} cannot submit buyer writes`,async()=>{
    const p=await page(account);
    await p.click('quote');assert.equal(p.panel.hidden,true);
    await p.click('save');await p.submit();
    assert.equal(p.requests.filter(r=>r.method==='POST').length,0);
    assert.equal(p.location.pathname,'/buyer/login');
  });
}
