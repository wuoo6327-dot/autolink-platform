/* Browser-level regression for the optimized home translator and entry points. */
const fs=require('fs');
const puppeteer=require('puppeteer-core');
const base=process.env.QA_BASE||'http://127.0.0.1:18081';
const browserPath=process.env.CHROME_BINARY||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const languages=['en','zh','ar','ru','kk','uz','ko','fr','sw'];
(async()=>{
 const browser=await puppeteer.launch({executablePath:browserPath,headless:true,args:['--no-sandbox']});
 const result={languages:{},viewports:{}};
 try{
  const page=await browser.newPage();
  await page.setViewport({width:412,height:823,deviceScaleFactor:2,isMobile:true,hasTouch:true});
  for(const lang of languages){
   await page.goto(base+'/?lang='+lang,{waitUntil:'domcontentloaded'});
   await page.waitForFunction(()=>document.querySelector('#root')?.innerText.length>100,{timeout:30000});
   result.languages[lang]=await page.evaluate(()=>({h1:document.querySelector('h1')?.innerText||'',
    mainLength:document.querySelector('main')?.innerText.length||0,
    modelLink:!!document.querySelector('a[href="/trade/models"]'),
    brandLink:!!document.querySelector('a[href="/trade/brands"]')}));
  }
  await page.goto(base+'/?lang=zh',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('h1'));
  await page.waitForSelector('button.language-trigger',{timeout:45000});
  await page.evaluate(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='仅必要项')?.click());
  const before=await page.$eval('h1',x=>x.innerText);
  result.languageControl=await page.evaluate(()=>{
   const trigger=[...document.querySelectorAll('button.language-trigger')].find(x=>x.getBoundingClientRect().width>0);
   if(!trigger)return null;
   trigger.click();return trigger.getAttribute('aria-label');
  });
  await page.waitForSelector('button[lang="en"]');
  await page.click('button[lang="en"]');
  await page.waitForFunction(previous=>document.querySelector('h1')?.innerText!==previous,{timeout:15000},before);
  result.switchedToEnglish=await page.$eval('h1',x=>x.innerText);
  result.viewports.mobile=await page.evaluate(()=>({h1:document.querySelector('h1')?.innerText,
   brands:document.querySelectorAll('a[href^="/trade/brands/"]').length,
   modelEntry:!!document.querySelector('a[href="/trade/models"]'),
   loginEntry:!!document.querySelector('a[href="/buyer/login"]')}));
  const menu=await page.evaluate(()=>{
   const button=[...document.querySelectorAll('button')].find(x=>/打开菜单|open menu/i.test(x.getAttribute('aria-label')||''));
   if(button){button.click();return true}return false;
  });
  result.mobileMenuOpened=menu;
  await page.setViewport({width:1440,height:900,deviceScaleFactor:1});
  await page.goto(base+'/?lang=en',{waitUntil:'domcontentloaded'});
  await page.waitForSelector('a[href="/buyer/login"]',{timeout:45000});
  result.viewports.desktop=await page.evaluate(()=>({h1:document.querySelector('h1')?.innerText,
   brands:document.querySelectorAll('a[href^="/trade/brands/"]').length,
   modelEntry:!!document.querySelector('a[href="/trade/models"]'),
   loginEntry:!!document.querySelector('a[href="/buyer/login"]')}));
  result.mainScriptLoads=await page.evaluate(()=>performance.getEntriesByType('resource')
   .filter(item=>item.name.includes('/assets/index-autolink-membership-apply-pricing.js'))
   .map(item=>item.name));
  await page.evaluate(()=>[...document.querySelectorAll('button')].find(x=>x.textContent.trim()==='Necessary only')?.click());
  await page.evaluate(()=>[...document.querySelectorAll('a[href="/buyer/login"]')].find(x=>x.getBoundingClientRect().width>0)?.click());
  await page.waitForFunction(()=>location.pathname==='/buyer/login',{timeout:15000});
  result.loginNavigation=new URL(page.url()).pathname;
  await page.goto(base+'/?lang=en',{waitUntil:'domcontentloaded'});
  await page.waitForSelector('a[href="/buyer/login"]',{timeout:45000});
  await page.evaluate(()=>[...document.querySelectorAll('a[href="/trade/models"]')].find(x=>x.getBoundingClientRect().width>0)?.click());
  await page.waitForFunction(()=>location.pathname==='/trade/models',{timeout:15000});
  result.modelNavigation=new URL(page.url()).pathname;
  result.pass=languages.every(lang=>result.languages[lang].mainLength>100&&result.languages[lang].modelLink&&result.languages[lang].brandLink)
   &&!!result.languageControl&&!!result.switchedToEnglish&&result.viewports.mobile.h1===result.viewports.desktop.h1
   &&result.viewports.mobile.brands===result.viewports.desktop.brands
   &&result.viewports.mobile.modelEntry&&result.viewports.desktop.modelEntry
   &&result.viewports.mobile.loginEntry&&result.viewports.desktop.loginEntry
   &&result.mobileMenuOpened&&result.loginNavigation==='/buyer/login'&&result.modelNavigation==='/trade/models';
  result.pass=result.pass&&result.mainScriptLoads.length===1&&result.mainScriptLoads[0].endsWith('?v=20261012-home-fast');
  fs.mkdirSync('tests/results',{recursive:true});
  fs.writeFileSync('tests/results/home-interaction-qa-20261012.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result,null,2));
  if(!result.pass)process.exitCode=1;
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
