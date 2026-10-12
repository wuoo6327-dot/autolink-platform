// Execute the actual adapter from this isolated checkout. Synthetic public
// records never leave this VM; this is not a production business test.
import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const source=fs.readFileSync(new URL('../../site/assets/business-seo.js',import.meta.url),'utf8');
const languages=['en','zh','ar','ru','kk','uz','ko','fr','sw'];
class Element {
  constructor(tag,head){this.tagName=tag;this.head=head;this.attributes={};this.textContent='';}
  setAttribute(key,value){this.attributes[key]=String(value);}
  get content(){return this.attributes.content;}
  remove(){this.head.children=this.head.children.filter(node=>node!==this);}
  matches(selector){
    if(selector.startsWith('#'))return this.id===selector.slice(1);
    const tag=selector.match(/^\w+/)?.[0];if(this.tagName!==tag)return false;
    return [...selector.matchAll(/\[([^=\]]+)(?:="([^"]+)")?\]/g)].every(([,key,value])=>value===undefined?(this.attributes[key]??this[key])!==undefined:(this.attributes[key]??this[key])===value);
  }
}
class Head {
  constructor(){this.children=[];}
  append(node){this.children.push(node);}
  querySelector(selector){return this.children.find(node=>node.matches(selector))||null;}
  querySelectorAll(selector){return this.children.filter(node=>node.matches(selector));}
}
for(const language of languages){
  const head=new Head();head.append(new Element('title',head));
  const location={pathname:'/trade/models/model-synthetic',search:'?lang='+language,href:'https://autolinkglobal.com/trade/models/model-synthetic?lang='+language};
  const document={head,title:'AUTOLINK',documentElement:{lang:language==='zh'?'zh-CN':language},
    querySelector:()=>null,createElement:tag=>new Element(tag,head)};
  const history={state:null,pushState(state,_,href){this.state=state;this.replaceState(state,_,href)},
    replaceState(state,_,href){const url=new URL(href,location.href);this.state=state;location.href=url.href;location.pathname=url.pathname;location.search=url.search}};
  const context=vm.createContext({document,location,history,URL,URLSearchParams,encodeURIComponent,
    queueMicrotask:callback=>callback(),MutationObserver:class{observe(){}}});
  context.window=context;context.addEventListener=()=>{};context.businessI18n={language,text:value=>value};
  vm.runInContext(source,context);
  const api=context.businessSEO;
  const record={id:'model-synthetic',brand:'Synthetic <script>',model:'Reference',year:2026,image:'/images/reference.webp',price_minor:987654321,review_reason:'PRIVATE_MARKER',contact:{email:'PRIVATE_MARKER'},seo:{indexLanguages:languages}};
  api.page('model',record);
  const canonical=()=>head.querySelector('link[rel="canonical"]').attributes.href;
  const expected='https://autolinkglobal.com'+location.pathname+(language==='en'?'':'?lang='+language);
  assert.equal(canonical(),expected);
  const alternates=head.querySelectorAll('link[rel="alternate"][hreflang]');
  assert.equal(alternates.length,10);
  for(const code of languages){const link=alternates.find(node=>node.hreflang===(code==='zh'?'zh-CN':code));assert.equal(link.href,'https://autolinkglobal.com'+location.pathname+(code==='en'?'':'?lang='+code));}
  assert.equal(alternates.find(node=>node.hreflang==='x-default').href,'https://autolinkglobal.com'+location.pathname);
  const schema=head.querySelector('#autolink-public-jsonld').textContent;
  assert.ok(!schema.includes('<script>')&&!schema.includes('PRIVATE_MARKER')&&!schema.includes('987654321'));
  assert.ok(JSON.parse(schema)['@graph'].some(entity=>entity['@type']==='ProductModel'));
  api.update();assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,10);
  location.search+='&keyword=synthetic';api.update();assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,0);
  assert.equal(head.querySelector('meta[name="robots"]').content,'noindex, follow');
  location.pathname='/buyer/security';api.update();assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,0);
  assert.equal(head.querySelector('meta[name="robots"]').content,'noindex, nofollow');
  location.pathname='/trade/models/model-synthetic';location.search='?lang='+language;
  api.page('model',{...record,seo:{indexLanguages:['zh']}});
  assert.equal(head.querySelector('meta[name="robots"]').content,language==='zh'?'index, follow':'noindex, follow');
  assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,language==='zh'?2:0);
  if(language==='zh')assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').find(n=>n.hreflang==='x-default').href,'https://autolinkglobal.com'+location.pathname+'?lang=zh');
  api.page('model',{...record,seo:{indexLanguages:[]}});
  api.update();assert.equal(head.querySelector('meta[name="robots"]').content,'noindex, follow');
  assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,0);
  api.page('model',record);
  location.pathname='/trade/brands/brand-synthetic';
  api.page('brand',{id:'brand-synthetic',name:'Synthetic',seo:{indexLanguages:[]}});
  assert.equal(head.querySelector('meta[name="robots"]').content,'noindex, follow');
  // A React language switch keeps the page alive while changing <html lang>.
  // The canonical, URL and index policy must follow the new language.
  location.pathname='/';location.search='?lang=zh';location.href='https://autolinkglobal.com/?lang=zh';
  document.documentElement.lang='zh-CN';document.title='AUTOLINK — 中国车源。 连接全球。';api.update();
  assert.equal(canonical(),'https://autolinkglobal.com/?lang=zh');
  assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,3);
  document.documentElement.lang='en';document.title='AUTOLINK — Source China. Drive Global.';api.update();
  assert.equal(location.href,'https://autolinkglobal.com/');
  assert.equal(canonical(),'https://autolinkglobal.com/');
  assert.equal(document.title,'AUTOLINK | Chinese Vehicle Sourcing & B2B Supplier Platform');
  document.documentElement.lang='ar';api.update();
  assert.equal(location.href,'https://autolinkglobal.com/?lang=ar');
  assert.equal(head.querySelector('meta[name="robots"]').content,'noindex, follow');
  assert.equal(head.querySelectorAll('link[rel="alternate"][hreflang]').length,0);
  console.log(language+': isolated adapter canonical, language alternates, private/filter exclusions and schema redaction PASS');
}
