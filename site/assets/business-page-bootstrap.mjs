import {ensureBusinessLanguage, loadScript, showBootstrapError} from './business-language-loader.mjs?v=20261009-speed';

const version = '?v=20261009-gx';
const page = document.querySelector('script[data-business-page]')?.dataset.businessPage;
const pages = {
  home: {
    before: ['/assets/supplier-program.js', '/assets/auth-entry.js'],
    after: ['/assets/business-routes.js', '/assets/email-ui.js', '/assets/account-header.js', '/assets/business-seo.js'],
    app: '/assets/index-autolink-membership-apply-pricing.js', module: true
  },
  trade: {before: [], after: ['/assets/business-seo.js'], app: '/trade/app.js'},
  buyer: {before: ['/assets/password-security.js', '/assets/business-pagination.js', '/assets/auth-entry.js'], after: ['/assets/business-seo.js'], app: '/buyer/app.js'},
  support: {before: ['/assets/supplier-program.js'], after: ['/assets/business-seo.js'], app: '/support/app.js'}
};

try {
  const config = pages[page];
  if (!config) throw Error('Unknown application');
  await Promise.all([ensureBusinessLanguage(), ...config.before.map(url => loadScript(url + version))]);
  await Promise.all(config.after.map(url => loadScript(url + version)));
  // Keep the existing compiled application intact. Its language, authentication
  // and navigation helpers are ready before its first render.
  await loadScript(config.app + version, {module: !!config.module});
} catch { showBootstrapError(); }
