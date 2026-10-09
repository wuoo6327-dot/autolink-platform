/* Keep the public navigation in sync with the server-side account session. */
(() => {
  const accountPaths = { BUYER: '/buyer', MERCHANT: '/supplier', SUPPLIER: '/supplier', ADMIN: '/admin', PLATFORM_ADMIN: '/admin' };
  const accountEntryPaths = new Set(['/login', '/account', '/buyer', '/buyer/login', '/merchant', '/platform', '/supplier', '/admin']);
  const navigationLabels = {
    en: ['Sign in', 'Open your workspace'], zh: ['登录', '返回个人工作台'],
    ar: ['تسجيل الدخول', 'فتح مساحة العمل'], ru: ['Войти', 'Открыть рабочий кабинет'],
    kk: ['Кіру', 'Жұмыс кабинетіңізді ашу'], uz: ['Kirish', 'Ish kabinetingizni ochish'],
    ko: ['로그인', '내 업무 공간 열기'], fr: ['Se connecter', 'Ouvrir votre espace de travail'],
    sw: ['Ingia', 'Fungua eneo lako la kazi']
  };
  let account = null;
  let requestNumber = 0;
  let refreshTimer;

  function savedBearerToken() {
    try {
      const session = JSON.parse(localStorage.getItem('autolink-business-session') || 'null');
      return session && session.expiresAt > Date.now() && typeof session.token === 'string'
        ? session.token : '';
    } catch { return ''; }
  }

  async function readAccount(headers) {
    const response = await fetch('/autolink/me', {
      credentials: 'same-origin', cache: 'no-store', headers,
      signal: AbortSignal.timeout(10000)
    });
    if (response.status === 401) return null;
    if (!response.ok) throw new Error('Account service unavailable');
    const body = await response.json();
    if (body.code !== 200 || !body.data) throw new Error('Invalid account response');
    return body.data;
  }

  async function refreshAccount() {
    const currentRequest = ++requestNumber;
    try {
      let next = await readAccount();
      const cookieAuthenticated = !!next;
      if (!next) {
        const token = savedBearerToken();
        if (token) next = await readAccount({ Authorization: `Bearer ${token}` });
      }
      if (currentRequest !== requestNumber) return;
      account = next && accountPaths[next.role] ? next : null;
      try {
        if (account && cookieAuthenticated) localStorage.setItem('autolink-cookie-session', '1');
        else localStorage.removeItem('autolink-cookie-session');
        // A successful legacy Bearer read does not create an HttpOnly cookie.
        // Remove it only after cookie authentication succeeds, or it is rejected.
        if (cookieAuthenticated || !account) localStorage.removeItem('autolink-business-session');
      } catch {}
      updateNavigation();
    } catch {
      // Keep the visible account when the network has a temporary error.
    }
  }

  function scheduleRefresh() {
    clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshAccount, 50);
  }

  function displayName(user) {
    for (const key of ['nickName', 'username', 'email', 'companyName']) {
      const value = typeof user[key] === 'string' ? user[key].trim() : '';
      if (value) return value;
    }
    return navigationLabels[language()][1];
  }

  function language() {
    const value = document.documentElement.lang;
    return /^zh(?:-|$)/i.test(value) ? 'zh' : navigationLabels[value] ? value : 'en';
  }

  function setLink(link, href, label, title) {
    link.dataset.authAccountLink = '1';
    if (link.getAttribute('href') !== href) link.setAttribute('href', href);
    if (link.textContent !== label) link.textContent = label;
    if (link.title !== title) link.title = title;
    link.classList.toggle('autolink-signed-in-name', !!account);
  }

  function updateNavigation(root = document) {
    const selector = '.nav-account, .mobile-account';
    const navigation = [...(root.matches?.(selector) ? [root] : []), ...root.querySelectorAll(selector)];
    for (const nav of navigation) {
      const links = [...nav.querySelectorAll('a')];
      const entry = links.find(link => link.classList.contains('nav-merchant-entry'));
      const accountLink = links.find(link => !link.classList.contains('nav-merchant-entry') &&
        (link.dataset.authAccountLink === '1' || accountEntryPaths.has(link.getAttribute('href'))));
      const join = links.find(link => link.classList.contains('nav-join') || link.getAttribute('href') === '/register');
      if (!account) {
        if (accountLink) setLink(accountLink, '/buyer/login', navigationLabels[language()][0], '');
        if (entry && entry.hidden) entry.hidden = false;
        if (join && join.hidden) join.hidden = false;
        continue;
      }
      const path = accountPaths[account.role];
      const name = displayName(account);
      const title = navigationLabels[language()][1];
      if (accountLink) setLink(accountLink, path, name, title);
      if (entry) {
        const supplier = account.capabilities?.supplier ?? ['BUYER', 'MERCHANT', 'SUPPLIER'].includes(account.role);
        if (supplier) entry.setAttribute('href', '/supplier/application');
        entry.hidden = !supplier;
      }
      if (join && !join.hidden) join.hidden = true;
    }
  }

  const pendingNavigation = new Set();
  let navigationFrame = 0;
  new MutationObserver(records => {
    if (!records) { updateNavigation(); return; }
    const selector = '.nav-account, .mobile-account';
    for (const record of records) {
      const enclosing = record.target.closest?.(selector);
      if (enclosing) pendingNavigation.add(enclosing);
      for (const node of record.addedNodes) {
        if (node.nodeType !== 1) continue;
        if (node.matches(selector)) pendingNavigation.add(node);
        for (const nav of node.querySelectorAll(selector)) pendingNavigation.add(nav);
      }
    }
    if (!pendingNavigation.size || navigationFrame) return;
    navigationFrame = requestAnimationFrame(() => {
      navigationFrame = 0;
      for (const nav of pendingNavigation) if (nav.isConnected) updateNavigation(nav);
      pendingNavigation.clear();
    });
  }).observe(document.documentElement, { childList: true, subtree: true });
  updateNavigation();
  refreshAccount();
  window.addEventListener('trade-session-changed', scheduleRefresh);
  window.addEventListener('trade-session-expired', scheduleRefresh);
  window.addEventListener('pageshow', scheduleRefresh);
  window.addEventListener('focus', scheduleRefresh);
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') scheduleRefresh();
  });
})();
