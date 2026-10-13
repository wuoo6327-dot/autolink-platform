const { chromium } = require('playwright');
const fs = require('node:fs');

const base = process.env.QA_BASE || 'https://autolinkglobal.com';
const output = process.env.QA_OUTPUT || 'tests/results/afme-public-browser-20261014.json';
const routes = ['/?lang=en', '/trade/brands', '/trade/models',
  '/trade/models/haval-catalog-1', '/buyer/login'];

(async () => {
  const browser = await chromium.launch({headless: true,
    executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'});
  const rows = [];
  try {
    for (const [device, viewport] of [
      ['mobile', {width: 390, height: 844}],
      ['desktop', {width: 1440, height: 900}],
    ]) {
      const context = await browser.newContext({viewport, locale: 'en-US'});
      for (const path of routes) {
        const page = await context.newPage();
        const errors = [];
        const failedResources = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('requestfailed', request => {
          if (['image', 'script', 'stylesheet'].includes(request.resourceType()))
            failedResources.push({type: request.resourceType(), url: new URL(request.url()).pathname});
        });
        page.on('response', response => {
          if (response.status() >= 400 && ['image', 'script', 'stylesheet'].includes(response.request().resourceType()))
            failedResources.push({type: response.request().resourceType(), url: new URL(response.url()).pathname, status: response.status()});
        });
        const response = await page.goto(base + path, {waitUntil: 'domcontentloaded', timeout: 30000});
        await page.locator('h1').first().waitFor({timeout: 15000});
        if (path === '/trade/models/haval-catalog-1') {
          await page.locator('.trade-hero-image').waitFor({timeout: 15000});
          await page.waitForFunction(() => document.querySelector('.trade-hero-image')?.complete, null, {timeout: 15000});
        }
        const result = await page.evaluate(() => ({
          h1: document.querySelector('h1')?.textContent?.trim() || '',
          canonical: document.querySelector('link[rel=canonical]')?.href || '',
          robots: document.querySelector('meta[name=robots]')?.content || '',
          bodyLength: document.body.innerText.length,
          documentWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
          modelLinks: document.querySelectorAll('a[href^="/trade/models/"]').length,
          brandLinks: document.querySelectorAll('a[href^="/trade/brands/"]').length,
          heroImageLoaded: document.querySelector('.trade-hero-image')
            ? document.querySelector('.trade-hero-image').complete && document.querySelector('.trade-hero-image').naturalWidth > 0
            : null,
        }));
        rows.push({device, path, status: response.status(), ...result, jsErrors: errors, failedResources});
        await page.close();
      }
      const fallback = await context.newPage();
      await fallback.route(/\/assets\/(business-seo|account-header)\.js/, route => route.abort());
      const response = await fallback.goto(base + '/?lang=en', {waitUntil: 'domcontentloaded'});
      await fallback.locator('h1').first().waitFor({timeout: 15000});
      rows.push({device, path: '/?lang=en', optionalScriptFailure: true,
        status: response.status(), h1: await fallback.locator('h1').first().innerText(),
        bodyLength: (await fallback.locator('body').innerText()).length});
      await context.close();
    }
    const pass = rows.every(row => row.status === 200 && row.h1 && row.bodyLength > 100 &&
      (!row.jsErrors || row.jsErrors.length === 0) &&
      (!row.failedResources || row.failedResources.length === 0) &&
      (row.path !== '/trade/models/haval-catalog-1' || row.heroImageLoaded) &&
      (!row.documentWidth || row.documentWidth <= row.viewportWidth + 2));
    fs.mkdirSync(require('node:path').dirname(output), {recursive: true});
    fs.writeFileSync(output, JSON.stringify({base, checkedAt: new Date().toISOString(), pass, rows}, null, 2) + '\n');
    console.log(JSON.stringify({pass, rows: rows.map(({device, path, status, h1, jsErrors}) =>
      ({device, path, status, h1, jsErrors}))}));
    if (!pass) process.exitCode = 1;
  } finally { await browser.close(); }
})().catch(error => { console.error(error.stack); process.exitCode = 1; });
