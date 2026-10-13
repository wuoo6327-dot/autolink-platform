const {chromium,webkit} = require('playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
const base = 'http://127.0.0.1:18094';
const browserName = process.env.ROUND14_BROWSER === 'webkit' ? 'webkit' : 'chrome';
const buyerRole = process.env.ROUND14_BUYER || 'buyer-a';
const tokens = JSON.parse(fs.readFileSync('tests/results/round14/qa-tokens.json'));

async function signedContext(browser, role, viewport) {
  const context = await browser.newContext({viewport, locale:'en-US'});
  await context.addCookies([{name:'autolink_session',value:tokens[role],url:base,httpOnly:true,sameSite:'Lax'}]);
  return context;
}

(async () => {
  const browser = browserName === 'webkit'
    ? await webkit.launch({headless:true})
    : await chromium.launch({headless:true,executablePath:'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const results=[];
  try {
    const anonymous=await browser.newContext({viewport:{width:390,height:844},locale:'en-US'});
    const unsigned=await anonymous.newPage();
    await unsigned.goto(base+'/buyer/requests?vehicleId=geely-monjaro-2026',{waitUntil:'domcontentloaded'});
    await unsigned.waitForURL(/\/buyer\/login\?returnTo=/);
    const returnTo=new URL(unsigned.url()).searchParams.get('returnTo');
    assert.equal(returnTo,'/buyer/requests?vehicleId=geely-monjaro-2026');
    await unsigned.getByRole('link',{name:'Register with email code'}).click();
    await unsigned.waitForURL(/\/buyer\/register\?returnTo=/);
    assert.equal(new URL(unsigned.url()).searchParams.get('returnTo'),returnTo);
    await anonymous.addCookies([{name:'autolink_session',value:tokens[buyerRole],url:base,httpOnly:true,sameSite:'Lax'}]);
    await unsigned.goto(base+returnTo,{waitUntil:'domcontentloaded'});
    await unsigned.locator('#request-form').waitFor();
    assert.equal(await unsigned.locator('[name=vehicleId]').inputValue(),'geely-monjaro-2026');
    results.push({browser:browserName,device:'anonymous-to-buyer',loginReturnTo:'pass',registerReturnTo:'pass',modelPrefill:'pass'});
    await anonymous.close();
    for (const [device, viewport] of [['mobile',{width:390,height:844}],['desktop',{width:1440,height:900}]]) {
      const context=await signedContext(browser,buyerRole,viewport);
      const page=await context.newPage();
      const errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(base+'/trade/models?keyword=Xingyue%20L&lang=en',{waitUntil:'domcontentloaded'});
      await page.locator('#model-search').waitFor();
      assert.match(await page.locator('.trade-results').innerText(),/1 Model references?/i);
      await page.locator('#model-search select[name=brand]').selectOption({label:'Geely'});
      await page.locator('#model-search select[name=year]').selectOption('2026');
      await page.locator('#model-search select[name=energy]').selectOption('ICE');
      await page.locator('#model-search button[type=submit]').click();
      await page.waitForURL(/year=2026/);
      assert.match(await page.locator('.trade-results').innerText(),/1 Model references?/i);
      await page.goto(base+'/trade/models/geely-monjaro-2026?lang=en',{waitUntil:'domcontentloaded'});
      const create=page.getByRole('link',{name:'Create a sourcing request'});
      await create.waitFor();
      await create.click();
      await page.waitForURL(/\/buyer\/requests\?vehicleId=geely-monjaro-2026/);
      await page.locator('#request-form').waitFor();
      assert.equal(new URL(page.url()).searchParams.get('lang'),'en');
      assert.equal(await page.locator('html').getAttribute('lang'),'en');
      const layout=await page.evaluate(()=>({viewport:innerWidth,document:document.documentElement.scrollWidth}));
      assert.ok(layout.document<=layout.viewport+2,`Horizontal overflow: ${JSON.stringify(layout)}`);
      assert.equal(await page.locator('[name=vehicleId]').inputValue(),'geely-monjaro-2026');
      assert.equal(await page.locator('[name=brand]').inputValue(),'Geely');
      assert.equal(await page.locator('[name=year]').inputValue(),'2026');
      await page.locator('[name=title]').fill(`Round14 ${device} QA ${Date.now()}`);
      await page.locator('[name=quantity]').fill('3');
      await page.locator('[name=destinationCountry]').fill('Kenya');
      await page.locator('[name=destinationPort]').fill('Mombasa');
      await page.locator('[name=configuration]').fill('LHD; exact trim to confirm');
      await page.reload({waitUntil:'domcontentloaded'});
      await page.locator('#request-form').waitFor();
      assert.equal(await page.locator('[name=destinationPort]').inputValue(),'Mombasa');
      assert.equal(await page.locator('[name=configuration]').inputValue(),'LHD; exact trim to confirm');
      assert.equal(await page.locator('#request-sharing').isChecked(),false);
      await page.locator('#request-form button[value=DRAFT]').click();
      await page.waitForURL(/created=REQ-/,{waitUntil:'domcontentloaded'});
      await page.locator('.alert.success').waitFor();
      const reference=await page.locator('.alert.success strong').innerText();
      assert.match(reference,/^REQ-[A-F0-9]{12}$/);
      assert.match(await page.locator('.list').first().innerText(),/LHD; exact trim to confirm/);
      page.once('dialog',dialog=>dialog.accept());
      await page.locator('.list .row').filter({hasText:reference}).first().locator('[data-action=close-request]').click();
      await page.locator('.alert.success').filter({hasText:/closed|已关闭/i}).first().waitFor();
      assert.match(await page.locator('.list .row').filter({hasText:reference}).first().innerText(),/Closed|已关闭/);
      assert.deepEqual(errors,[]);
      results.push({browser:browserName,device,modelAlias:'pass',requestPrefill:'pass',draftPersistence:'pass',statusFeedback:'pass',createdReference:reference,layout,jsErrors:errors.length});
      await context.close();
    }
    const admin=await signedContext(browser,'admin',{width:1440,height:900});
    const page=await admin.newPage();
    await page.goto(base+'/admin/sourcing?kind=requests',{waitUntil:'domcontentloaded'});
    await page.locator('form[data-sourcing-kind=requests]').first().waitFor();
    await page.locator('form[data-sourcing-kind=requests] input[name=note]').first().fill('Isolated QA follow-up');
    await page.locator('form[data-sourcing-kind=requests] button').first().click();
    await page.getByText('Isolated QA follow-up').first().waitFor();
    const denied=await page.request.get(base+'/autolink/admin/sourcing?kind=requests',{headers:{Cookie:'autolink_session='+tokens[buyerRole]}});
    assert.equal(denied.status(),403);
    results.push({browser:browserName,device:'admin',sourcingView:'pass',followupAudit:'pass',buyerDenied:denied.status()});
    await admin.close();
    const supplier=await signedContext(browser,'supplier-a',{width:390,height:844});
    const supplierPage=await supplier.newPage();
    const supplierErrors=[];
    supplierPage.on('pageerror',error=>supplierErrors.push(error.message));
    await supplierPage.goto(base+'/supplier/application',{waitUntil:'domcontentloaded'});
    await supplierPage.locator('#supplier-content').waitFor();
    assert.ok((await supplierPage.locator('#supplier-content').innerText()).length>80);
    assert.deepEqual(supplierErrors,[]);
    results.push({browser:browserName,device:'supplier-mobile',applicationView:'pass',jsErrors:0});
    await supplier.close();
    fs.writeFileSync('tests/results/round14/browser-qa-'+browserName+'.json',JSON.stringify(results,null,2));
    process.stdout.write(JSON.stringify(results)+'\n');
  } finally { await browser.close(); }
})().catch(error=>{process.stderr.write(error.stack+'\n');process.exitCode=1;});
