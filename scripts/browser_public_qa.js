/* Browser regression for direct SSR, mobile images, and optional script failure. */
const puppeteer=require('puppeteer-core');
const fs=require('fs');
const base=process.env.QA_BASE||'http://127.0.0.1:18081';
const browserPath=process.env.CHROME_BINARY||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
(async()=>{
 const browser=await puppeteer.launch({executablePath:browserPath,headless:true,args:['--no-sandbox']});
 const results={};
 try{
  const page=await browser.newPage();await page.setViewport({width:412,height:915,deviceScaleFactor:2});
  await page.setRequestInterception(true);
  page.on('request',request=>/\/assets\/(business-seo|account-header)\.js/.test(request.url())?request.abort():request.continue());
  await page.goto(base+'/?lang=zh',{waitUntil:'domcontentloaded'});
  await page.waitForFunction(()=>document.querySelector('#root')?.innerText.length>100,{timeout:20000});
  results.optionalScriptFailure=await page.evaluate(()=>({bodyLength:document.querySelector('#root').innerText.length,error:document.querySelector('#root').getAttribute('role')==='alert',h1:document.querySelector('h1')?.innerText||''}));
  const model=await browser.newPage();await model.setViewport({width:412,height:915,deviceScaleFactor:2});
  await model.goto(base+'/trade/models/zeekr-9x-2026?lang=zh',{waitUntil:'networkidle2'});
  results.modelMobile=await model.evaluate(()=>({h1:document.querySelector('h1')?.innerText,ssr:document.querySelector('#app')?.dataset.ssr,canonical:document.querySelector('link[rel="canonical"]')?.href,image:document.querySelector('.trade-hero-image')?.currentSrc,specifications:document.querySelectorAll('[data-ssr-reference] tr').length}));
  const english=await browser.newPage();await english.setViewport({width:1280,height:900});
  await english.goto(base+'/trade/models/geely-monjaro-2026',{waitUntil:'networkidle2'});
  results.modelEnglish=await english.evaluate(()=>({h1:document.querySelector('h1')?.innerText,ssr:document.querySelector('#app')?.dataset.ssr,canonical:document.querySelector('link[rel="canonical"]')?.href,robots:document.querySelector('meta[name="robots"]')?.content,specifications:document.querySelectorAll('[data-ssr-reference] tr').length}));
  const bot=await browser.newPage();await bot.setViewport({width:412,height:915,deviceScaleFactor:2});
  await bot.setUserAgent('Mozilla/5.0 (Linux; Android 11; Pixel 5) AppleWebKit/537.36 (KHTML, like Gecko; compatible; Googlebot/2.1; +http://www.google.com/bot.html) Chrome/131.0.0.0 Mobile Safari/537.36');
  await bot.goto(base+'/trade/models/geely-monjaro-2026',{waitUntil:'networkidle2'});
  results.googlebotEmulation=await bot.evaluate(()=>({h1:document.querySelector('h1')?.innerText,ssr:document.querySelector('#app')?.dataset.ssr,specifications:document.querySelectorAll('[data-ssr-reference] tr').length}));
  results.pass=results.optionalScriptFailure.bodyLength>100&&!results.optionalScriptFailure.error&&results.modelMobile.ssr==='true'&&results.modelMobile.image.includes('seo-heroes')&&results.modelEnglish.ssr==='true'&&results.modelEnglish.robots==='index, follow'&&results.googlebotEmulation.h1===results.modelEnglish.h1&&results.googlebotEmulation.specifications===results.modelEnglish.specifications;
  console.log(JSON.stringify(results,null,2));
  fs.mkdirSync('tests/results',{recursive:true});fs.writeFileSync('tests/results/browser-public-qa-20261012.json',JSON.stringify(results,null,2)+'\n');
  if(!results.pass)process.exitCode=1;
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1});
