import {ensureBusinessLanguage, loadScript, showBootstrapError} from './business-language-loader.mjs?v=20261009-speed';

const page = document.querySelector('script[data-business-page]')?.dataset.businessPage;
const version = page === 'home' ? '?v=20261012-home-fast' : page === 'trade' ? '?v=20261011-guide-cards' : '?v=20261009-gx';
const pages = {
  home: {
    before: ['/assets/supplier-program.js', '/assets/auth-entry.js', '/trade/directory-locales.js', '/assets/home-suv-visuals.js'],
    after: ['/assets/business-routes.js', '/assets/email-ui.js', '/assets/account-header.js', '/assets/business-seo.js'],
    app: '/assets/index-autolink-membership-apply-pricing.js', module: true
  },
  trade: {before: ['/trade/directory-locales.js', '/trade/directory-ui.js'], after: ['/assets/business-seo.js'], app: '/trade/app.js'},
  buyer: {before: ['/assets/password-security.js', '/assets/business-pagination.js', '/assets/auth-entry.js'], after: ['/assets/business-seo.js'], app: '/buyer/app.js'},
  support: {before: ['/assets/supplier-program.js'], after: ['/assets/business-seo.js'], app: '/support/app.js'}
};

try {
  const config = pages[page];
  if (!config) throw Error('Unknown application');
  await Promise.all([ensureBusinessLanguage(), ...config.before.map(url => loadScript(url + version))]);
  // Noncritical metadata and UI helpers may fail independently.
  void Promise.allSettled(config.after.map(url => loadScript(url + version)));
  // Load presentation, language, authentication and navigation helpers before
  // the existing application renders.
  await loadScript(config.app + version, {module: !!config.module});
} catch { showBootstrapError(); }
