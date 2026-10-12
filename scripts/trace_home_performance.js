/* Cold Chrome Performance trace for the existing homepage. */
const fs = require('fs');
const path = require('path');
const puppeteer = require('puppeteer-core');

const base = process.env.TRACE_BASE || 'http://127.0.0.1:18081';
const route = process.env.TRACE_PATH || '/?lang=zh';
const output = process.env.TRACE_OUTPUT || 'tests/results/traces/home-mobile-baseline';
const browserPath = process.env.CHROME_BINARY || '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

(async () => {
  const browser = await puppeteer.launch({executablePath: browserPath, headless: true,
    args: ['--no-sandbox', '--disable-cache', '--no-first-run']});
  try {
    const page = await browser.newPage();
    await page.setViewport({width: 412, height: 823, deviceScaleFactor: 1.75, isMobile: true, hasTouch: true});
    const client = await page.createCDPSession();
    await client.send('Network.enable');
    await client.send('Network.setCacheDisabled', {cacheDisabled: true});
    await client.send('Network.emulateNetworkConditions', {offline: false, latency: 150,
      downloadThroughput: 1.6 * 1024 * 1024 / 8, uploadThroughput: 750 * 1024 / 8});
    await client.send('Emulation.setCPUThrottlingRate', {rate: 4});
    await client.send('Profiler.enable');
    await page.evaluateOnNewDocument(() => {
      window.__autolinkTrace = {longTasks: [], lcp: []};
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) window.__autolinkTrace.longTasks.push({start: entry.startTime, duration: entry.duration});
      }).observe({type: 'longtask', buffered: true});
      new PerformanceObserver(list => {
        for (const entry of list.getEntries()) window.__autolinkTrace.lcp.push({start: entry.startTime,
          element: entry.element?.outerHTML.slice(0, 600) || '', url: entry.url, loadTime: entry.loadTime,
          renderTime: entry.renderTime});
      }).observe({type: 'largest-contentful-paint', buffered: true});
    });
    const traceDone = new Promise(resolve => client.once('Tracing.tracingComplete', resolve));
    await client.send('Tracing.start', {categories: 'devtools.timeline,disabled-by-default-devtools.timeline,blink.user_timing,loading',
      transferMode: 'ReturnAsStream'});
    await client.send('Profiler.start');
    const started = Date.now();
    await page.goto(base + route, {waitUntil: 'domcontentloaded', timeout: 90000});
    await page.waitForFunction(() => document.querySelector('#root')?.innerText.length > 100, {timeout: 90000});
    await page.waitForFunction(() => {
      const poster = document.querySelector('.journey-poster');
      return poster?.complete && poster.naturalWidth > 0;
    }, {timeout: 15000});
    await new Promise(resolve => setTimeout(resolve, 2000));
    const browserSummary = await page.evaluate(() => ({
      readyState: document.readyState,
      title: document.title,
      h1: document.querySelector('h1')?.innerText,
      trace: window.__autolinkTrace,
      resources: performance.getEntriesByType('resource').map(entry => ({name: entry.name,
        start: entry.startTime, duration: entry.duration, responseEnd: entry.responseEnd,
        transfer: entry.transferSize, decoded: entry.decodedBodySize, initiator: entry.initiatorType})),
    }));
    const {profile} = await client.send('Profiler.stop');
    await client.send('Tracing.end');
    const {stream} = await traceDone;
    const chunks = [];
    while (true) {
      const part = await client.send('IO.read', {handle: stream});
      chunks.push(part.base64Encoded ? Buffer.from(part.data, 'base64') : Buffer.from(part.data));
      if (part.eof) break;
    }
    await client.send('IO.close', {handle: stream});
    const raw = Buffer.concat(chunks);
    const trace = JSON.parse(raw.toString());
    const timed = trace.traceEvents.filter(event => Number.isFinite(event.dur) && event.ph === 'X');
    const longTasks = timed.filter(event => event.name === 'RunTask' && event.dur >= 50000)
      .map(event => ({durationMs: event.dur / 1000, startUs: event.ts, thread: event.tid}));
    const scripts = timed.filter(event => ['EvaluateScript', 'CompileScript'].includes(event.name));
    const scriptTotals = {};
    for (const event of scripts) {
      const url = event.args?.data?.url || '(unknown)';
      scriptTotals[url] = (scriptTotals[url] || 0) + event.dur / 1000;
    }
    const summary = {...browserSummary, wallTimeMs: Date.now() - started,
      traceEvents: trace.traceEvents.length, traceBytes: raw.length,
      runTasksOver50ms: longTasks.sort((a, b) => b.durationMs - a.durationMs).slice(0, 20),
      scriptEvaluationAndCompileMs: Object.entries(scriptTotals).sort((a, b) => b[1] - a[1]).slice(0, 20)};
    fs.mkdirSync(path.dirname(output), {recursive: true});
    fs.writeFileSync(output + '.json', raw);
    fs.writeFileSync(output + '.cpuprofile', JSON.stringify(profile));
    const nodeById = new Map(profile.nodes.map(node => [node.id, node]));
    const cpuSelf = {};
    for (let i = 0; i < (profile.samples || []).length; i++) {
      const frame = nodeById.get(profile.samples[i])?.callFrame;
      if (!frame) continue;
      const key = `${frame.functionName || '(anonymous)'} ${frame.url}:${frame.lineNumber + 1}:${frame.columnNumber + 1}`;
      cpuSelf[key] = (cpuSelf[key] || 0) + (profile.timeDeltas?.[i] || 0) / 1000;
    }
    summary.cpuSelfMs = Object.entries(cpuSelf).sort((a, b) => b[1] - a[1]).slice(0, 30);
    fs.writeFileSync(output + '-summary.json', JSON.stringify(summary, null, 2) + '\n');
    console.log(JSON.stringify({output, traceBytes: raw.length, wallTimeMs: summary.wallTimeMs,
      lcp: summary.trace.lcp.at(-1), longTasks: summary.trace.longTasks,
      topScripts: summary.scriptEvaluationAndCompileMs.slice(0, 6),
      largestRunTasks: summary.runTasksOver50ms.slice(0, 6),
      cpuSelf: summary.cpuSelfMs.slice(0, 12)}, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
