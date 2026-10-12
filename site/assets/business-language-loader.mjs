// Keep every dictionary key, but download only the active language and English.
// The content-hash map is generated from the existing full business dictionary.
export const languageFiles = {"en":"/i18n/chunks/business-en-584799cf575b.js","zh":"/i18n/chunks/business-zh-e929ef16659e.js","ar":"/i18n/chunks/business-ar-f8eeedef4074.js","ru":"/i18n/chunks/business-ru-8f2f5e51171f.js","kk":"/i18n/chunks/business-kk-6daa5dd46af2.js","uz":"/i18n/chunks/business-uz-7184ab6e01e6.js","ko":"/i18n/chunks/business-ko-bbf4c138c613.js","fr":"/i18n/chunks/business-fr-8a29910e1c6e.js","sw":"/i18n/chunks/business-sw-fb1b7089103f.js"};

export function selectBusinessLanguage() {
  const normalize = value => value === 'zh-CN' ? 'zh' : value;
  const fixed = normalize(window.AUTOLINK_BUSINESS_FIXED_LANGUAGE);
  if (Object.hasOwn(languageFiles, fixed)) return fixed;
  const requested = normalize(new URLSearchParams(location.search).get('lang'));
  if (Object.hasOwn(languageFiles, requested)) return requested;
  for (const key of ['autolink-language', 'autolink_language']) {
    try {
      const stored = normalize(localStorage.getItem(key));
      if (Object.hasOwn(languageFiles, stored)) return stored;
    } catch { /* Continue when browser storage is unavailable. */ }
  }
  const browser = String(navigator.language || 'en').toLowerCase().split('-')[0];
  return Object.hasOwn(languageFiles, browser) ? browser : 'en';
}

const scripts = new Map();
export function loadScript(url, {module = false} = {}) {
  if (!scripts.has(url)) {
    const pending = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      if (module) script.type = 'module';
      script.src = url;
      script.onload = resolve;
      script.onerror = () => { scripts.delete(url); reject(Error('Resource unavailable')); };
      document.head.append(script);
    });
    scripts.set(url, pending);
  }
  return scripts.get(url);
}

let languageReady;
function installHomeLanguageChoices() {
  // The homepage changes language without navigation. Load the selected
  // business dictionary before React renders translated copy; the initial
  // request still downloads only English and the active language.
  document.addEventListener('click', event => {
    const button = event.target.closest?.('.language-options button[lang]');
    const code = button?.getAttribute('lang');
    if (!Object.hasOwn(languageFiles, code) ||
        window.AUTOLINK_BUSINESS_RESOURCES?.[code] ||
        button.dataset.autolinkLocaleAttempted === '1') return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (button.dataset.autolinkLocaleLoading === '1') return;
    button.dataset.autolinkLocaleLoading = '1';
    void loadScript(languageFiles[code]).then(() => {
      const messages = window.AUTOLINK_BUSINESS_RESOURCES?.[code]?.translation;
      if (messages && window.i18next?.addResourceBundle) {
        window.i18next.addResourceBundle(code, 'translation', messages, true, true);
      }
    }).catch(() => { /* The UI can still switch to its bundled translations. */ })
      .finally(() => {
        button.dataset.autolinkLocaleAttempted = '1';
        delete button.dataset.autolinkLocaleLoading;
        if (button.isConnected) button.click();
      });
  }, true);
}
export function ensureBusinessLanguage() {
  if (!languageReady) languageReady = (async () => {
    const language = selectBusinessLanguage();
    await Promise.all([
      window.i18next ? Promise.resolve() : loadScript('/vendor/i18next-26.4.2.min.js'),
      ...[...new Set(['en', language])].map(code => loadScript(languageFiles[code]))
    ]);
    await loadScript('/i18n/business-i18n.js?v=20261009-speed');
    installHomeLanguageChoices();
    // The adapter can arrive after DOMContentLoaded. Translate only explicit,
    // application-owned labels, using the same contract as the existing adapter.
    for (const node of document.querySelectorAll('[data-business-text]')) {
      node.textContent = window.businessI18n.text(node.dataset.businessText);
    }
    return window.businessI18n;
  })();
  return languageReady;
}

export function showBootstrapError(language = selectBusinessLanguage()) {
  const messages = {
    en: 'Unable to load. Please reload.', zh: '加载失败，请刷新页面。',
    ar: 'تعذر التحميل. أعد تحميل الصفحة.', ru: 'Не удалось загрузить. Обновите страницу.',
    kk: 'Жүктеу мүмкін болмады. Бетті жаңартыңыз.', uz: 'Yuklanmadi. Sahifani yangilang.',
    ko: '불러오지 못했습니다. 새로고침하세요.', fr: 'Chargement impossible. Rechargez la page.',
    sw: 'Imeshindwa kupakia. Pakia ukurasa tena.'
  };
  const root = document.querySelector('#app, #root');
  // The public homepage contains a complete static search and navigation
  // fallback. A failed optional application import must not erase it.
  if (root?.querySelector('.home-static')) {
    root.dataset.enhancement = 'unavailable';
    return;
  }
  if (root) { root.textContent = messages[language] || messages.en; root.setAttribute('role', 'alert'); }
}
