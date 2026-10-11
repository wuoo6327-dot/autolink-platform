/* Presentation components consumed by the existing React application.
 * These are model illustrations, never supplier offers or stock records. */
(() => {
  const images = {
    im: '/images/ui-suv/im-ls9-coast.webp',
    volkswagen: '/images/ui-suv/volkswagen-id-era-9x.webp',
    lynk: '/images/ui-suv/lynk-co-900.webp',
    l9: '/images/ui-suv/li-l9-livis.webp'
  };
  const mobileImages = {
    zeekr: '/images/home-mobile/zeekr9x-city-ad.webp?v=20261012-home-fast',
    s800: '/images/home-mobile/maextro-s800-portrait.webp',
    l9: '/images/home-mobile/li-l9-portrait.webp'
  };
  // The desktop image remains the fallback. Phones select a separate official
  // portrait source, without changing the shared content or business routes.
  function picture({jsx: n, jsxs: d, mobile, image}) {
    return d('picture', {className: 'home-responsive-media', style: {display: 'contents'}, children: [
      n('source', {media: '(max-width:680px)', srcSet: mobileImages[mobile]}),
      n('img', image)
    ]});
  }
  const text = (language, key) => window.AUTOLINK_DIRECTORY_COPY[language]?.[key] || window.AUTOLINK_DIRECTORY_COPY.en[key];
  const url = (path, language) => path + '?lang=' + encodeURIComponent(language);
  const models = [
    {key: 'im', name: 'IM LS9', brand: 'IM', path: '/trade/brands/im'},
    {key: 'volkswagen', name: 'Volkswagen ID.ERA 9X', brand: 'VOLKSWAGEN', path: '/trade/models/saic-volkswagen-id-era-9x'},
    {key: 'lynk', name: 'Lynk & Co 900', brand: 'LYNK & CO', path: '/trade/models/lynk-co-900'}
  ];
  function selection({jsx: n, jsxs: d, language}) {
    return d('div', {className: 'home-suv-selection', children: [
      d('div', {className: 'home-suv-selection-heading', children: [
        n('span', {className: 'eyebrow', children: text(language, 'visualSelection')}),
        n('p', {children: text(language, 'visualOnly')})
      ]}),
      n('div', {className: 'home-suv-selection-grid', children: models.map(model => d('a', {
        href: url(model.path, language), className: 'home-suv-model home-suv-model-' + model.key,
        children: [n('figure', {children: n('img', {src: images[model.key], alt: model.name + ' — model illustration', loading: 'lazy', decoding: 'async'})}),
          d('div', {className: 'home-suv-model-caption', children: [n('span', {children: model.brand, translate: 'no'}),
            n('strong', {children: model.name, translate: 'no'}), n('span', {className: 'home-suv-model-arrow', children: '↗', 'aria-hidden': true})]})]
      }, model.key))})
    ]});
  }
  function trust({jsx: n, jsxs: d, language}) {
    const items = [['01', 'guideVerification', 'businessCheckBody', '/guide/supplier-verification'], ['02', 'guideSourcing', 'brandCoverageBody', '/guide/vehicle-sourcing'], ['03', 'guideProcess', 'directDiscussionNote', '/guide/trade-process']];
    return d('div', {className: 'home-supplier-editorial', children: [
      d('figure', {className: 'home-supplier-scene', children: [
        picture({jsx: n, jsxs: d, mobile: 'l9', image: {src: images.l9, alt: 'Li L9 — model illustration', loading: 'lazy', decoding: 'async', width: 1750, height: 1110}}),
        d('figcaption', {children: [n('span', {className: 'home-desktop-model-label', children: 'LI AUTO / L9 LIVIS', translate: 'no'}), n('span', {className: 'home-mobile-model-label', children: 'LI AUTO / L9', translate: 'no'}), n('small', {children: text(language, 'referencePhoto')})]})
      ]}),
      d('div', {className: 'home-supplier-editorial-copy', children: [
        n('p', {className: 'eyebrow', children: text(language, 'trustKicker')}),
        n('h3', {children: text(language, 'trustTitle')}),
        n('ul', {children: items.map(([index, title, body, path]) => n('li', {children: d('a', {className: 'home-supplier-guide-link', href: url(path, language), children: [n('span', {className: 'home-guide-number', children: index, translate: 'no'}),
          d('div', {children: [n('strong', {children: text(language, title)}), n('p', {children: text(language, body)})]})]})}, index))}),
        n('p', {className: 'home-supplier-photo-note', children: text(language, 'supplierVisualNote')})
      ]})
    ]});
  }
  window.autolinkHomeSuvUI = {selection, trust, picture, mobileImages};
})();
