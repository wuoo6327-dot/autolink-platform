/* Reproducible browser evidence for the public homepage, including a failed app import. */
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require('playwright');

const base = process.env.QA_BASE || 'https://autolinkglobal.com';
const output = process.env.QA_OUTPUT || 'tests/results/round11-home-baseline';
const binary = process.env.CHROME_BINARY || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const blockMain = process.env.BLOCK_MAIN === '1';
const mobile = process.env.QA_DEVICE !== 'desktop';

async function main() {
  fs.mkdirSync(path.dirname(output), {recursive: true});
  const browser = await chromium.launch({executablePath: binary, headless: true});
  try {
    const context = await browser.newContext({
      viewport: mobile ? {width: 412, height: 823} : {width: 1440, height: 900},
      deviceScaleFactor: mobile ? 2 : 1, isMobile: mobile, hasTouch: mobile,
      locale: 'en-US', serviceWorkers: 'block'
    });
    const page = await context.newPage();
    const events = [];
    page.on('console', message => { if (message.type() === 'error' || message.type() === 'warning') events.push({kind: 'console', type: message.type(), text: message.text().slice(0, 500)}); });
    page.on('pageerror', error => events.push({kind: 'pageerror', message: error.message.slice(0, 500)}));
    page.on('requestfailed', request => events.push({kind: 'requestfailed', url: request.url(), error: request.failure()?.errorText}));
    page.on('response', response => { if (response.status() >= 400) events.push({kind: 'http', url: response.url(), status: response.status()}); });
    if (blockMain) await page.route('**/assets/index-autolink-membership-apply-pricing.js*', route => route.abort('failed'));
    const client = await context.newCDPSession(page);
    await client.send('Network.enable');
    await client.send('Network.setCacheDisabled', {cacheDisabled: true});
    if (process.env.QA_THROTTLE === '1') {
      await client.send('Network.emulateNetworkConditions', {offline: false, latency: 150,
        downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8});
      await client.send('Emulation.setCPUThrottlingRate', {rate: 4});
    }
    await page.addInitScript(() => {
      window.__round11 = {lcp: [], tasks: []};
      new PerformanceObserver(list => { for (const item of list.getEntries()) window.__round11.lcp.push({start: item.startTime, url: item.url, element: item.element?.outerHTML.slice(0, 300)}); }).observe({type: 'largest-contentful-paint', buffered: true});
      new PerformanceObserver(list => { for (const item of list.getEntries()) window.__round11.tasks.push({start: item.startTime, duration: item.duration}); }).observe({type: 'longtask', buffered: true});
    });
    const traceComplete = new Promise(resolve => client.once('Tracing.tracingComplete', resolve));
    await client.send('Tracing.start', {categories: 'devtools.timeline,disabled-by-default-devtools.timeline,blink.user_timing,loading', transferMode: 'ReturnAsStream'});
    const started = Date.now();
    const navigation = await page.goto(base + '/', {waitUntil: 'domcontentloaded', timeout: 60000});
    await page.waitForTimeout(8000);
    const dom = await page.evaluate(() => ({
      title: document.title, lang: document.documentElement.lang, canonical: document.querySelector('link[rel=canonical]')?.href,
      h1: document.querySelector('h1')?.textContent?.trim(), rootText: document.querySelector('#root')?.innerText?.slice(0, 1000),
      links: [...document.querySelectorAll('#root a[href]')].map(a => a.getAttribute('href')).slice(0, 30),
      trace: window.__round11,
      resources: performance.getEntriesByType('resource').map(item => ({name: item.name, start: item.startTime,
        duration: item.duration, transfer: item.transferSize, decoded: item.decodedBodySize, initiator: item.initiatorType}))
    }));
    await page.screenshot({path: output + '.png'});
    await client.send('Tracing.end');
    const {stream} = await traceComplete;
    const pieces = [];
    while (true) {
      const part = await client.send('IO.read', {handle: stream});
      pieces.push(part.base64Encoded ? Buffer.from(part.data, 'base64') : Buffer.from(part.data));
      if (part.eof) break;
    }
    await client.send('IO.close', {handle: stream});
    const raw = Buffer.concat(pieces);
    fs.writeFileSync(output + '-trace.json', raw);
    const trace = JSON.parse(raw.toString());
    const tasks = trace.traceEvents.filter(item => item.ph === 'X' && item.name === 'RunTask' && item.dur >= 50000)
      .map(item => ({startUs: item.ts, durationMs: item.dur / 1000})).sort((a, b) => b.durationMs - a.durationMs);
    const result = {base, mobile, blockMain, throttle: process.env.QA_THROTTLE === '1', status: navigation.status(),
      wallMs: Date.now() - started, userAgent: await page.evaluate(() => navigator.userAgent), events, ...dom,
      runTasksOver50ms: tasks.slice(0, 30), traceBytes: raw.length};
    fs.writeFileSync(output + '.json', JSON.stringify(result, null, 2) + '\n');
    console.log(JSON.stringify({status: result.status, title: result.title, h1: result.h1,
      lcp: result.trace.lcp.at(-1), longTasks: result.trace.tasks, events, screenshot: output + '.png'}, null, 2));
    await context.close();
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
