import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';
import test from 'node:test';

// Every API response and identity is synthetic. No browser or network is used.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = relative => fs.readFileSync(path.join(root, relative), 'utf8');
const settle = async () => { for (let i = 0; i < 12; i++) await Promise.resolve(); };
const legacy = JSON.stringify({token: 'synthetic-legacy-token', expiresAt: Date.now() + 3600000});
const reply = (data, status = 200, msg = 'OK') => ({status, ok: status >= 200 && status < 300,
  json: async () => ({code: status, data, msg})});

class Element {
  constructor({dataset = {}, hidden = false, href = '', classes = []} = {}) {
    Object.assign(this, {dataset, hidden, href, disabled: false, checked: false,
      textContent: '', innerHTML: '', title: '', isConnected: true, nodeType: 1});
    this.listeners = new Map(); this.queries = new Map(); this.attributes = new Map();
    this.classes = new Set(classes);
    this.classList = {contains: value => this.classes.has(value), toggle: (value, on) => {
      if (on) this.classes.add(value); else this.classes.delete(value);
    }};
  }
  addEventListener(name, callback) {
    if (!this.listeners.has(name)) this.listeners.set(name, []);
    this.listeners.get(name).push(callback);
  }
  async emit(name, extra = {}) {
    const event = {target: this, currentTarget: this, preventDefault() {}, ...extra};
    for (const callback of this.listeners.get(name) || []) await callback(event);
    await settle();
  }
  querySelector(selector) { return this.queries.get(selector) ?? null; }
  querySelectorAll(selector) { return this.queries.get(selector) ?? []; }
  setAttribute(key, value) { this.attributes.set(key, String(value)); if (key === 'href') this.href = String(value); }
  getAttribute(key) { return key === 'href' ? this.href : this.attributes.get(key) ?? null; }
  append() {}
  matches() { return false; }
  closest() { return null; }
}

function environment({responses = [], pathname = '/account-deletion', search = '',
                      stored = {}, sessionStored = {}, storageDenied = false, confirmation = true} = {}) {
  const calls = [], navigations = [], prompts = [], timers = new Map(), events = new Map();
  const local = new Map(Object.entries(stored)), session = new Map(Object.entries(sessionStored));
  const storage = map => ({getItem: key => map.get(key) ?? null,
    setItem: (key, value) => map.set(key, String(value)), removeItem: key => map.delete(key)});
  const document = new Element();
  document.documentElement = new Element(); document.documentElement.lang = 'en';
  document.body = new Element(); document.visibilityState = 'visible';
  const location = {pathname, search, origin: 'https://autolinkglobal.com',
    href: 'https://autolinkglobal.com' + pathname + search,
    assign: value => navigations.push(value), replace: value => navigations.push(value)};
  const context = {document, location, URL, URLSearchParams, AbortSignal, console,
    fetch: async (url, options = {}) => {
      calls.push({url, method: options.method || 'GET', options});
      assert.ok(responses.length, 'Unexpected mocked fetch: ' + url);
      const response = responses.shift();
      if (response instanceof Error) throw response;
      return typeof response === 'function' ? await response(url, options) : response;
    },
    confirm: message => { prompts.push(message); return confirmation; },
    MutationObserver: class { constructor(callback) { this.callback = callback; } observe() {} },
    requestAnimationFrame: callback => { callback(); return 1; },
    setTimeout: callback => { const id = timers.size + 1; timers.set(id, callback); return id; },
    clearTimeout: id => timers.delete(id),
    addEventListener: (name, callback) => events.set(name, callback)};
  for (const [name, map] of [['localStorage', local], ['sessionStorage', session]]) {
    Object.defineProperty(context, name, {get() {
      if (storageDenied) throw new Error('Synthetic browser storage denied');
      return storage(map);
    }});
  }
  context.window = context;
  vm.createContext(context);
  return {context, document, location, calls, navigations, prompts, local, session,
    run: async relative => { vm.runInContext(source(relative), context, {filename: relative}); await settle(); },
    refresh: async name => { events.get(name)?.(); const scheduled = [...timers.values()]; timers.clear();
      for (const callback of scheduled) await callback(); await settle(); }};
}

async function legal(options = {}) {
  const h = environment(options);
  const action = new Element(), button = new Element({hidden: true}), login = new Element(),
    status = new Element(), retry = new Element({hidden: true});
  for (const [selector, element] of [['[data-delete-account]', button], ['[data-account-login]', login],
    ['[data-account-status]', status], ['[data-account-retry]', retry]]) action.queries.set(selector, element);
  h.document.queries.set('[data-account-action]', action);
  const dialog = new Element(); dialog.showModal = () => {}; dialog.close = () => {};
  dialog.queries.set('#analytics-choice', new Element()); dialog.queries.set('#advertising-choice', new Element());
  h.document.createElement = tag => { assert.equal(tag, 'dialog'); return dialog; };
  Object.assign(h, {button, login, status, retry});
  await h.run('site/legal/legal.js'); return h;
}

const closeable = reply({id: 'synthetic-buyer', role: 'BUYER', accountDeletionAllowed: true});
const closed = reply({deleted: true});

for (const storageDenied of [false, true]) test(`Cookie login closes account with no local token; storage denied=${storageDenied}`, async () => {
  const h = await legal({responses: [closeable, closed], storageDenied});
  assert.equal(h.button.hidden, false); assert.equal(h.login.hidden, true);
  await h.button.emit('click');
  assert.deepEqual(h.calls.map(call => call.method), ['GET', 'DELETE']);
  for (const call of h.calls) {
    assert.equal(call.options.credentials, 'same-origin');
    assert.equal(call.options.headers.Authorization, undefined);
  }
  assert.deepEqual(h.navigations, ['/buyer/login?lang=en']);
});

test('Cookie identity takes priority over a different legacy token', async () => {
  const h = await legal({responses: [closeable, closed], stored: {'autolink-business-session': legacy}});
  assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.headers.Authorization, undefined);
  await h.button.emit('click');
  assert.equal(h.calls[1].options.headers.Authorization, undefined);
});

for (const identity of ['owner', 'last-admin']) test(`${identity}: server disallows closure, hidden button also blocks forced click`, async () => {
  const h = await legal({responses: [reply({id: identity, role: 'PLATFORM_ADMIN', accountDeletionAllowed: false})]});
  assert.equal(h.button.hidden, true); assert.equal(h.login.hidden, true);
  assert.match(h.status.textContent, /protected|受到保护/);
  await h.button.emit('click'); assert.equal(h.calls.length, 1); assert.equal(h.prompts.length, 0);
});

test('Cookie 401 shows login and cannot issue DELETE', async () => {
  const h = await legal({responses: [reply(null, 401)]});
  assert.equal(h.login.hidden, false); assert.equal(h.button.hidden, true);
  assert.match(h.login.href, /buyer\/login\?returnTo=%2Faccount-deletion/);
  await h.button.emit('click'); assert.equal(h.calls.length, 1);
});

test('Network failure leaves closure blocked and a retry can load Cookie identity', async () => {
  const h = await legal({responses: [new Error('Synthetic network failure'), closeable]});
  assert.equal(h.retry.hidden, false); assert.equal(h.login.hidden, true); assert.equal(h.button.hidden, true);
  await h.button.emit('click'); assert.equal(h.calls.length, 1);
  await h.retry.emit('click'); assert.equal(h.retry.hidden, true); assert.equal(h.button.hidden, false);
  assert.equal(h.calls.length, 2);
});

test('Legacy Bearer compatibility is attempted only after Cookie 401 and reused for DELETE', async () => {
  const h = await legal({responses: [reply(null, 401), closeable, closed], sessionStored: {'autolink-business-session': legacy}});
  assert.equal(h.calls[0].options.headers.Authorization, undefined);
  assert.equal(h.calls[1].options.headers.Authorization, 'Bearer synthetic-legacy-token');
  await h.button.emit('click');
  assert.equal(h.calls[2].options.headers.Authorization, 'Bearer synthetic-legacy-token');
});

for (const failure of [new Error('Synthetic network failure'), reply(null, 500)]) test(`Cookie ${failure instanceof Error ? 'network' : '500'} failure never switches to old Bearer identity`, async () => {
  const h = await legal({responses: [failure], stored: {'autolink-business-session': legacy}});
  assert.equal(h.calls.length, 1); assert.equal(h.button.hidden, true); assert.equal(h.retry.hidden, false);
  assert.equal(h.local.get('autolink-business-session'), legacy);
});

test('Expired legacy token is not sent after Cookie 401', async () => {
  const expired = JSON.stringify({token: 'synthetic-expired-token', expiresAt: Date.now() - 1});
  const h = await legal({responses: [reply(null, 401)], stored: {'autolink-business-session': expired}});
  assert.equal(h.calls.length, 1); assert.equal(h.login.hidden, false);
});

test('Cancelled confirmation never sends DELETE', async () => {
  const h = await legal({responses: [closeable], confirmation: false});
  await h.button.emit('click'); assert.equal(h.calls.length, 1); assert.equal(h.navigations.length, 0);
});

for (const failure of [reply(null, 403), reply(null, 500), new Error('Synthetic DELETE network failure')])
  test(`DELETE ${failure instanceof Error ? 'network' : failure.status} failure never redirects or clears session markers`, async () => {
    const h = await legal({responses: [closeable, failure], stored: {'autolink-business-session': legacy, 'autolink-cookie-session': '1'}});
    await h.button.emit('click'); assert.equal(h.navigations.length, 0);
    assert.equal(h.local.get('autolink-business-session'), legacy); assert.equal(h.local.get('autolink-cookie-session'), '1');
    assert.match(h.status.textContent, /关闭未完成/);
    if (!(failure instanceof Error) && failure.status === 403) {
      assert.equal(h.button.hidden, true); await h.button.emit('click'); assert.equal(h.calls.length, 2);
    }
  });

test('Successful closure clears compatibility markers in both stores and describes retained history', async () => {
  const markers = {'autolink-business-session': legacy, 'autolink-cookie-session': '1', 'unrelated-preference': 'keep'};
  const h = await legal({responses: [closeable, closed], stored: markers, sessionStored: markers});
  await h.button.emit('click');
  for (const store of [h.local, h.session]) {
    assert.equal(store.has('autolink-business-session'), false); assert.equal(store.has('autolink-cookie-session'), false);
    assert.equal(store.get('unrelated-preference'), 'keep');
  }
  assert.match(h.prompts[0], /Necessary history will be retained/);
  assert.doesNotMatch(h.prompts[0], /Permanently delete/);
  const page = source('site/legal/account-deletion.html');
  assert.match(page, /does not erase the database or historical enquiries, quotes and audit records/);
  assert.match(page, /不会清空数据库、历史询盘、报价或审计记录/);
});

async function agreement({responses, version = 'synthetic-final-v1', digest = 'synthetic-final-hash'} = {}) {
  const h = environment({responses, pathname: '/supplier-terms'});
  const form = new Element(), body = new Element({dataset: {version, bodySha256: digest}}),
    button = new Element(), status = new Element(), next = new Element({hidden: true});
  form.elements = {agreement: new Element(), privacy: new Element()};
  form.queries.set('input', Object.values(form.elements));
  const ids = {'agreement-confirmation': form, 'agreement-body': body, 'agreement-confirm': button,
    'agreement-confirmation-status': status, 'agreement-next': next};
  h.document.getElementById = id => ids[id];
  Object.assign(h, {form, body, button, status, next});
  await h.run('site/legal/supplier-agreement.js');
  return h;
}
const final = {acceptanceEnabled: true, version: 'synthetic-final-v1', bodySha256: 'synthetic-final-hash', confirmation: null};
async function checkBoth(h) {
  h.form.elements.agreement.checked = true; h.form.elements.privacy.checked = true;
  await h.form.emit('change');
}

for (const confirmation of [null, {id: 'synthetic-old-confirmation', version: 'synthetic-draft-v0'}])
  test(`Draft agreement cannot POST even with checked boxes or legacy confirmation=${!!confirmation}`, async () => {
    const h = await agreement({responses: [reply({...final, acceptanceEnabled: false, confirmation})]});
    await checkBoth(h); assert.equal(h.button.disabled, true);
    await h.form.emit('submit'); assert.equal(h.calls.length, 1); assert.match(h.status.textContent, /暂未开放/);
    assert.notEqual(h.button.textContent, '已确认签署');
  });

test('Agreement GET network failure stays disabled and checked inputs cannot POST', async () => {
  const h = await agreement({responses: [new Error('Synthetic agreement network failure')]});
  await checkBoth(h); assert.equal(h.button.disabled, true);
  await h.form.emit('submit'); assert.equal(h.calls.length, 1);
});

test('Matching new FINAL agreement posts its exact version/hash once after both consents', async () => {
  const h = await agreement({responses: [reply(final), reply({...final, confirmation: {id: 'synthetic-new-confirmation'}})]});
  assert.equal(h.button.disabled, true); await h.form.emit('submit'); assert.equal(h.calls.length, 1);
  await checkBoth(h); assert.equal(h.button.disabled, false); await h.form.emit('submit');
  assert.equal(h.calls[1].method, 'POST'); assert.equal(h.calls[1].options.credentials, 'same-origin');
  assert.deepEqual(JSON.parse(h.calls[1].options.body), {version: final.version, bodySha256: final.bodySha256,
    consent: true, authorized: true, privacyAcknowledged: true});
  assert.equal(h.button.disabled, true); assert.equal(h.button.textContent, '已确认签署');
  await h.form.emit('submit'); assert.equal(h.calls.length, 2);
});

test('A newly released FINAL version cannot be signed from stale rendered agreement HTML', async () => {
  const h = await agreement({responses: [reply(final)], version: 'synthetic-old-draft', digest: 'synthetic-old-hash'});
  await checkBoth(h); assert.equal(h.button.disabled, true);
  await h.form.emit('submit'); assert.equal(h.calls.length, 1);
});

async function header(options = {}) {
  const h = environment(options);
  const navigation = ['desktop', 'mobile'].map(() => {
    const nav = new Element(), account = new Element({href: '/buyer/login'}),
      supplier = new Element({href: '/merchant/login', classes: ['nav-merchant-entry']}),
      join = new Element({href: '/register', classes: ['nav-join']});
    nav.queries.set('a', [account, supplier, join]); return {nav, account, supplier, join};
  });
  h.document.queries.set('.nav-account, .mobile-account', navigation.map(n => n.nav));
  h.navigation = navigation; await h.run('site/assets/account-header.js'); return h;
}
const business = role => ({role, nickName: 'Synthetic account', capabilities: {buyer: true, supplier: true, admin: false}});

for (const [role, pathname] of [['BUYER', '/supplier/application'], ['MERCHANT', '/buyer/profile']])
  test(`Header Cookie single-role ${role} preserves protected pathname without forced redirects`, async () => {
    const h = await header({responses: [reply(business(role))], pathname, stored: {'autolink-business-session': legacy}});
    assert.equal(h.calls.length, 1); assert.equal(h.calls[0].options.headers?.Authorization, undefined);
    for (const n of h.navigation) {
      assert.equal(n.account.href, role === 'BUYER' ? '/buyer' : '/supplier');
      assert.equal(n.supplier.href, '/merchant/login'); assert.equal(n.supplier.hidden, true);
    }
    assert.equal(h.location.pathname, pathname); assert.equal(h.navigations.length, 0);
    assert.equal(h.local.get('autolink-cookie-session'), '1');
    assert.equal(h.local.has('autolink-business-session'), false);
  });

test('Header successful Bearer fallback preserves legacy token until Cookie authentication exists', async () => {
  const h = await header({responses: [reply(null, 401), reply(business('MERCHANT'))],
    stored: {'autolink-business-session': legacy, 'autolink-cookie-session': '1'}});
  assert.equal(h.calls[1].options.headers.Authorization, 'Bearer synthetic-legacy-token');
  assert.equal(h.local.get('autolink-business-session'), legacy); assert.equal(h.local.has('autolink-cookie-session'), false);
});

test('Header temporary network error preserves current account and the unverified legacy token', async () => {
  const h = await header({responses: [reply(business('BUYER')), new Error('Synthetic refresh network failure')]});
  h.local.set('autolink-business-session', legacy);
  await h.refresh('focus');
  assert.equal(h.local.get('autolink-business-session'), legacy);
  for (const n of h.navigation) assert.equal(n.account.textContent, 'Synthetic account');
  assert.equal(h.calls.length, 2); assert.equal(h.navigations.length, 0);
});

test('Header Cookie navigation still works when browser storage is unavailable', async () => {
  const h = await header({responses: [reply(business('BUYER'))], storageDenied: true});
  for (const n of h.navigation) assert.equal(n.account.textContent, 'Synthetic account');
});

test('Administrator header does not offer a supplier capability', async () => {
  const h = await header({responses: [reply({role: 'PLATFORM_ADMIN', capabilities: {buyer: false, supplier: false, admin: true}})]});
  for (const n of h.navigation) { assert.equal(n.account.href, '/admin'); assert.equal(n.supplier.hidden, true); }
});
