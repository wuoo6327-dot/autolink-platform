/* Real Chrome mobile first/repeat navigation timing with the normal browser cache. */
const fs=require('fs');
const puppeteer=require('puppeteer-core');
const base=process.env.QA_BASE||'http://127.0.0.1:18081';
const binary=process.env.CHROME_BINARY||'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
(async()=>{
 const browser=await puppeteer.launch({executablePath:binary,headless:true,args:['--no-sandbox']});
 try{
  const page=await browser.newPage();
  await page.setViewport({width:412,height:823,deviceScaleFactor:2,isMobile:true,hasTouch:true});
  await page.evaluateOnNewDocument(()=>{
   window.__lcp=0;
   new PerformanceObserver(list=>{for(const entry of list.getEntries())window.__lcp=entry.startTime}).observe({type:'largest-contentful-paint',buffered:true});
  });
  const results=[];
  for(const visit of ['first','repeat']){
   const start=Date.now();
   await page.goto(base+'/?lang=zh',{waitUntil:'networkidle0',timeout:60000});
   await page.waitForFunction(()=>document.querySelector('.journey-poster')?.complete&&document.querySelector('.journey-poster')?.naturalWidth>0,{timeout:30000});
   const data=await page.evaluate(()=>({
    lcpMs:window.__lcp,
    navigation:performance.getEntriesByType('navigation')[0]?.toJSON(),
    homeImage:[...performance.getEntriesByType('resource')].find(x=>x.name.includes('/images/home-mobile/zeekr9x-city-ad.webp'))?.toJSON(),
    mainScript:[...performance.getEntriesByType('resource')].find(x=>x.name.includes('/assets/index-autolink-membership-apply-pricing.js'))?.toJSON(),
    h1:document.querySelector('h1')?.innerText,
    modelLinks:document.querySelectorAll('a[href^="/trade/models/"]').length
   }));
   results.push({visit,wallMs:Date.now()-start,...data});
  }
  fs.mkdirSync('tests/results',{recursive:true});
  fs.writeFileSync('tests/results/home-visit-cache-20261012.json',JSON.stringify(results,null,2)+'\n');
  console.log(JSON.stringify(results.map(({visit,lcpMs,wallMs,homeImage,mainScript})=>({visit,lcpMs,wallMs,imageTransfer:homeImage?.transferSize,scriptTransfer:mainScript?.transferSize})),null,2));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
