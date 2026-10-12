/* Browser regression for crawlable fallback and live nine-language metadata. */
const assert = require('node:assert/strict');
const {chromium} = require('playwright');

const base = process.env.QA_BASE || 'http://127.0.0.1:18083';
const chrome = process.env.CHROME_BINARY || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const choices = [
  ['zh', 'zh-CN'], ['en', 'en'], ['ar', 'ar'], ['ru', 'ru'],
  ['kk', 'kk'], ['uz', 'uz'], ['ko', 'ko'], ['fr', 'fr'], ['sw', 'sw'], ['en', 'en']
];

async function metadata(page) {
  return page.evaluate(() => ({
    lang: document.documentElement.lang,
    dir: document.documentElement.dir,
    title: document.title,
    intro: document.querySelector('.journey-subtitle')?.textContent?.trim(),
    description: document.querySelector('meta[name="description"]')?.content,
    canonical: document.querySelector('link[rel="canonical"]')?.href,
    robots: document.querySelector('meta[name="robots"]')?.content,
    ogTitle: document.querySelector('meta[property="og:title"]')?.content,
    ogUrl: document.querySelector('meta[property="og:url"]')?.content,
    twitterTitle: document.querySelector('meta[name="twitter:title"]')?.content,
    hreflang: [...document.querySelectorAll('link[hreflang]')].map(node => node.hreflang),
    url: location.href
  }));
}

async function main() {
  const browser = await chromium.launch({executablePath: chrome, headless: true});
  try {
    const blocked = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, locale: 'en-US'});
    const fallback = await blocked.newPage();
    await fallback.route('**/assets/index-autolink-membership-apply-pricing.js*', route => route.abort('failed'));
    assert.equal((await fallback.goto(base + '/', {waitUntil: 'domcontentloaded'})).status(), 200);
    await fallback.locator('#root[data-enhancement="unavailable"]').waitFor({timeout: 20000});
    assert.match(await fallback.locator('h1').innerText(), /Source China/);
    assert.equal(await fallback.locator('.home-static-search').getAttribute('action'), '/trade/vehicles');
    for (const path of ['/about', '/trade/brands', '/trade/models', '/trade/vehicles']) {
      assert.ok(await fallback.locator(`.home-static a[href="${path}"]`).count(), path);
    }
    assert.ok(!(await fallback.locator('#root').innerText()).includes('Unable to load'));
    await blocked.close();

    const context = await browser.newContext({viewport: {width: 1440, height: 900}, locale: 'en-US'});
    const page = await context.newPage();
    assert.equal((await page.goto(base + '/', {waitUntil: 'domcontentloaded', timeout: 60000})).status(), 200);
    const consent = page.locator('button').filter({hasText: /necessary only/i}).first();
    await consent.waitFor({state: 'visible', timeout: 12000}).catch(() => {});
    if (await consent.isVisible().catch(() => false)) await consent.click();
    await page.getByRole('banner').getByRole('button', {name: /语言/}).waitFor({state: 'visible', timeout: 30000});
    for (const [code, htmlLang] of choices) {
      await page.getByRole('banner').getByRole('button', {name: /语言/}).click();
      await page.locator(`.language-options button[lang="${code}"]`).click();
      await page.locator(`html[lang="${htmlLang}"]`).waitFor({state: 'attached', timeout: 15000});
      const actual = await metadata(page);
      const canonical = 'https://autolinkglobal.com/' + (code === 'en' ? '' : `?lang=${code}`);
      assert.equal(actual.canonical, canonical, code);
      assert.equal(actual.ogUrl, canonical, code);
      assert.equal(actual.ogTitle, actual.title, code);
      assert.equal(actual.twitterTitle, actual.title, code);
      assert.equal(actual.robots, ['en', 'zh'].includes(code) ? 'index, follow' : 'noindex, follow', code);
      assert.equal(actual.dir, code === 'ar' ? 'rtl' : 'ltr', code);
      assert.deepEqual(actual.hreflang, ['en', 'zh'].includes(code) ? ['en', 'zh-CN', 'x-default'] : [], code);
      if (code === 'en') assert.match(actual.description, /vehicle buyers with Chinese automotive suppliers/);
      else assert.equal(actual.description, actual.intro, code);
      console.log(JSON.stringify({language: code, title: actual.title, canonical, robots: actual.robots}));
    }
    assert.ok(await page.getByRole('link', {name: /Sign in/}).count());
    assert.ok(await page.getByRole('link', {name: /Merchant center/}).count());
    await context.close();

    const mobile = await browser.newContext({viewport: {width: 390, height: 844}, isMobile: true, locale: 'en-US'});
    const phone = await mobile.newPage();
    assert.equal((await phone.goto(base + '/', {waitUntil: 'domcontentloaded'})).status(), 200);
    const mobileConsent = phone.locator('button').filter({hasText: /necessary only/i}).first();
    await mobileConsent.waitFor({state: 'visible', timeout: 12000});
    await mobileConsent.click();
    await phone.getByRole('button', {name: 'Open menu'}).click();
    assert.ok(await phone.locator('header a[href="/buyer/login"]:visible').count());
    assert.ok(await phone.locator('header a[href="/merchant/login"]:visible').count());
    await phone.locator('header .language-trigger:visible').click();
    await phone.locator('.language-options button[lang="zh"]').click();
    await phone.locator('html[lang="zh-CN"]').waitFor({state: 'attached', timeout: 15000});
    assert.equal((await metadata(phone)).canonical, 'https://autolinkglobal.com/?lang=zh');
    await mobile.close();
    console.log('ROUND11_HOME_INTEGRATION_OK');
  } finally { await browser.close(); }
}

main().catch(error => { console.error(error); process.exitCode = 1; });
