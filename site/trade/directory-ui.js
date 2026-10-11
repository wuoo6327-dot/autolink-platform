/* Presentational views for the existing public directories. No API calls,
 * invented inventory, private contacts or inferred business certifications. */
(() => {
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const label = key => window.businessI18n.text(key);
  const copy = (key, values = {}) => {
    const resources = window.AUTOLINK_DIRECTORY_COPY;
    let text = resources[window.businessI18n.language]?.[key] ?? resources.en[key];
    for (const [name, value] of Object.entries(values)) text = text.replaceAll(`{${name}}`, String(value));
    return escape(text);
  };
  const icon = name => {
    const paths = {
      arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
      search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/>',
      car: '<path d="m5 10 2-5h10l2 5M3 10h18v8H3zM6 18v2m12-2v2M6 14h2m8 0h2"/>',
      company: '<path d="M4 21V3h12v18M16 9h4v12M8 7h4M8 11h4M8 15h4M8 21v-3h4v3M2 21h20"/>',
      check: '<path d="m8 12 3 3 5-6"/><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6z"/>',
      globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18"/>',
      message: '<path d="M4 4h16v12H9l-5 4zM8 8h8M8 12h5"/>',
      layers: '<path d="m3 8 9-5 9 5-9 5zM3 12l9 5 9-5M3 16l9 5 9-5"/>'
    };
    return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.arrow}</svg>`;
  };
  const href = (path, params) => {
    const query = new URLSearchParams(params || {});
    query.set('lang', window.businessI18n.language);
    return escape(path + '?' + query);
  };
  const button = (path, title, secondary = false, params, hash = '') => `<a class="button-link${secondary ? ' secondary' : ''}" href="${href(path, params)}${hash}">${title}${icon('arrow')}</a>`;
  const mark = (src, alt, className) => {
    const valid = typeof src === 'string' && (/^\/(?!\/)/.test(src) || /^https?:\/\//i.test(src));
    return valid ? `<img class="${className}" src="${escape(src)}" alt="${escape(alt)}" loading="lazy" decoding="async" referrerpolicy="no-referrer">` : '';
  };
  const stats = items => `<dl class="directory-metrics">${items.map(([value, text]) => `<div><dt>${text}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl>`;
  const badge = () => `<span class="directory-verified" title="${escape(label('Company information checked; not a transaction guarantee.'))}">${icon('check')}${escape(label('Verified supplier'))}</span>`;
  const number = value => Number.isFinite(Number(value)) && value !== null && value !== '' ? escape(value) : '—';
  const brandsOf = supplier => [...new Set(String(supplier.main_brands || '').split(/[,，、;；\n]+/).map(value => value.trim()).filter(Boolean))];
  const scopeOf = supplier => { const count = brandsOf(supplier).length; return count > 1 ? 'multi' : count === 1 ? 'focused' : 'unspecified'; };

  function listingCard(v) {
    const path = '/trade/vehicles/' + encodeURIComponent(v.id);
    const image = mark(v.image, [v.brand, v.model].filter(Boolean).join(' '), 'listing-image');
    let price;
    if (v.priceLocked) price = escape(label('Members only'));
    else if (v.price_minor != null && v.price_minor !== '' && Number.isFinite(Number(v.price_minor))) {
      try { price = escape(new Intl.NumberFormat(window.businessI18n.locale, {style: 'currency', currency: v.currency || 'USD', maximumFractionDigits: 2}).format(Number(v.price_minor) / 100)); }
      catch { price = copy('quote'); }
    } else price = copy('quote');
    const tags = [v.energy_type && label(v.energy_type), v.steering, v.vehicle_condition && label(v.vehicle_condition === 'NEW' ? 'New vehicle' : v.vehicle_condition === 'USED' ? 'Used vehicle' : v.vehicle_condition)].filter(Boolean);
    return `<article class="listing-card">
      <a class="listing-visual" href="${href(path)}" aria-label="${escape([label('View trade details'), v.brand, v.model].filter(Boolean).join(' · '))}">${image || `<span class="listing-image-placeholder">${icon('car')}${copy('photoPending')}</span>`}${v.referenceImage ? `<span class="listing-photo-note">${copy('referencePhoto')}</span>` : ''}</a>
      <div class="listing-card-copy"><div class="listing-card-heading"><span>${escape(v.brand)}</span><span>${v.model_year ? escape(v.model_year) : escape(label('Year unspecified'))}</span></div>
      <h3><a href="${href(path)}">${escape(v.model)}</a></h3>${v.trim ? `<p class="listing-trim">${escape(v.trim)}</p>` : ''}
      <div class="listing-tags">${tags.map(tag => `<span>${escape(tag)}</span>`).join('')}</div>
      <div class="listing-price"><strong>${price}</strong><span>${escape(label('Reference price / unit'))}</span></div>
      <div class="listing-terms"><span>${escape([v.incoterm, v.origin_port].filter(Boolean).join(' · ')) || '—'}</span><span>${escape(label('MOQ'))} ${number(v.moq)} · ${escape(label('Stock'))} ${number(v.stock)}</span></div>
      <div class="listing-supplier"><a href="${href('/trade/suppliers/' + encodeURIComponent(v.supplier_id))}">${escape(v.supplier_name)}</a>${v.supplier_status === 'APPROVED' ? badge() : ''}</div>
      <div class="listing-actions">${button(path, escape(label('View trade details')), true)}${button(path, escape(label('Send Inquiry')), false, {inquiry: '1'})}</div></div>
    </article>`;
  }

  function researchBrands(models) {
    const groups = new Map();
    for (const model of models) {
      if (!model.brandId || !model.brand) continue;
      if (!groups.has(model.brandId)) groups.set(model.brandId, {id: model.brandId, name: model.brand, logo: model.brandLogo, count: 0});
      groups.get(model.brandId).count++;
    }
    const rows = [...groups.values()].sort((a, b) => a.name.localeCompare(b.name, window.businessI18n.locale)).slice(0, 6);
    if (!rows.length) return '';
    return `<section class="directory-section brand-research"><div class="directory-section-heading"><div><span class="directory-kicker">${copy('research')}</span><h2>${copy('exploreBrands')}</h2><p>${copy('catalogNote')}</p></div>${button('/trade/brands', escape(label('Brands')), true)}</div><div class="directory-brand-grid">${rows.map(brand => `<a href="${href('/trade/brands/' + encodeURIComponent(brand.id))}"><span class="directory-brand-mark">${mark(brand.logo, '', 'trade-brand-logo') || escape(brand.name.slice(0, 2))}</span><strong>${escape(brand.name)}</strong><small>${copy('modelCount', {count: brand.count})}</small>${icon('arrow')}</a>`).join('')}</div></section>`;
  }

  function emptyListings(filtered, clearUrl) {
    return `<div class="listing-empty"><div class="listing-empty-copy"><span class="directory-empty-icon">${icon('car')}</span><span class="directory-kicker">${copy('approvedOnly')}</span><h3>${filtered ? escape(label('No listings match these filters.')) : copy('listingEmptyTitle')}</h3><p>${filtered ? copy('filterEmptyBody') : copy('listingEmptyBody')}</p><div class="directory-actions">${filtered ? `<a class="button-link secondary" href="${escape(clearUrl)}">${escape(label('Clear filters'))}${icon('arrow')}</a>` : ''}${button('/trade/models', escape(label('Browse model references')))}</div></div><ol class="listing-empty-steps">${[['01','researchStep','researchStepBody'],['02','requestStep','requestStepBody'],['03','quoteStep','quoteStepBody']].map(([index, title, body]) => `<li><span>${index}</span><div><strong>${copy(title)}</strong><p>${copy(body)}</p></div></li>`).join('')}</ol></div>`;
  }

  function recentlyUpdated(rows) {
    const dated = rows.filter(v => Number.isFinite(v.updated_at) && v.updated_at > 0).sort((a,b) => b.updated_at - a.updated_at).slice(0, 3);
    if (!dated.length) return '';
    return `<section class="directory-section recently-updated"><div class="directory-section-heading"><div><span class="directory-kicker">${copy('inventoryUpdates')}</span><h2>${copy('recentUpdates')}</h2><p>${copy('recentNote')}</p></div></div><div class="listing-update-list">${dated.map(v => `<a href="${href('/trade/vehicles/' + encodeURIComponent(v.id))}"><div><strong>${escape([v.brand,v.model].join(' '))}</strong><span>${escape(v.supplier_name)}</span></div><time datetime="${new Date(v.updated_at * 1000).toISOString()}">${escape(new Date(v.updated_at * 1000).toLocaleDateString(window.businessI18n.locale))}</time>${icon('arrow')}</a>`).join('')}</div></section>`;
  }

  function listings({rows, suppliers, models, filters, toolbar = '', pagination = '', filtered = false, clearUrl}) {
    return `<div class="directory-page listing-market"><section class="listing-market-hero"><div class="directory-hero-copy"><span class="directory-kicker">${copy('listingKicker')}</span><h1>${copy('listingTitle')}</h1><p>${copy('listingSubtitle')}</p>${stats([[rows.length,copy('pageListings')],[suppliers.length,copy('publicSuppliers')],[new Set(rows.map(v => v.brand).filter(Boolean)).size,copy('resultBrands')]])}<p class="directory-fineprint">${copy('listingMetricsNote')}</p><a class="directory-text-link" href="${href('/buyer/requests')}">${escape(label('Post buying request'))}${icon('arrow')}</a></div><aside class="listing-filter-panel" aria-labelledby="quick-filter-title"><div class="directory-panel-heading"><span class="directory-icon">${icon('search')}</span><div><span class="directory-kicker">${copy('quickFilterKicker')}</span><h2 id="quick-filter-title">${copy('quickFilter')}</h2></div></div>${filters}</aside></section>
      <section class="directory-section listing-results" id="listing-results" aria-labelledby="listing-results-title"><div class="directory-section-heading"><div><span class="directory-kicker">${copy('approvedOnly')}</span><h2 id="listing-results-title">${filtered ? copy('filteredListings') : copy('browseListings')}</h2></div><span class="directory-result-count">${copy('resultCount',{count:rows.length})}</span></div>${toolbar}${rows.length ? `<div class="listing-card-grid">${rows.map(listingCard).join('')}</div>` : emptyListings(filtered,clearUrl)}${pagination}</section>
      ${recentlyUpdated(rows)}${researchBrands(models)}<section class="directory-bottom-cta"><div><span class="directory-kicker">${copy('nextStep')}</span><h2>${copy('listingCta')}</h2><p>${copy('listingCtaBody')}</p></div><div class="directory-actions">${button('/buyer/requests',escape(label('Post buying request')))}${button('/trade/suppliers',escape(label('Suppliers')),true)}</div></section><p class="directory-fineprint">${escape(label('AUTOLINK connects buyers and suppliers. Vehicle payment and trade terms are agreed directly between them. AUTOLINK does not hold vehicle purchase funds or guarantee a transaction.'))}</p></div>`;
  }

  function supplierCard(s) {
    const path = '/trade/suppliers/' + encodeURIComponent(s.id), brands = brandsOf(s);
    return `<article class="supplier-profile-card"><div class="supplier-identity"><div class="supplier-avatar">${mark(s.logo_url,'','supplier-avatar-image') || escape(Array.from(s.company_name || '').slice(0,2).join('').toUpperCase())}</div><div><span class="directory-kicker">${copy('companyProfile')}</span><h3><a href="${href(path)}">${escape(s.company_name)}</a></h3><p>${escape([s.city,s.country].filter(Boolean).join(' · ')) || escape(label('Not specified'))}</p></div>${badge()}</div><div class="supplier-profile-body"><div class="supplier-profile-overview"><p>${escape(s.description || label('No overview available.'))}</p><div class="supplier-brand-tags"><span>${escape(label('Main brands'))}</span>${brands.length ? brands.map(brand => `<b>${escape(brand)}</b>`).join('') : `<b class="unspecified">${escape(label('Not specified'))}</b>`}</div></div><dl class="supplier-profile-facts"><div><dt>${escape(label('Main markets'))}</dt><dd>${escape(s.main_markets) || '—'}</dd></div><div><dt>${copy('supplyModels')}</dt><dd>${copy('confirmWithSupplier')}</dd></div><div><dt>${copy('responseTime')}</dt><dd>${copy('notPublished')}</dd></div></dl></div><div class="supplier-profile-footer"><span>${copy('companyCheckNote')}</span><div class="directory-actions">${button(path,escape(label('View supplier')),true)}${button(path,escape(label('Contact Supplier')),false,{},'#supplier-contact')}</div></div></article>`;
  }

  function trustPanel() {
    const items = [['check','businessCheck','businessCheckBody'],['globe','exportExperience','exportExperienceBody'],['layers','brandCoverage','brandCoverageBody'],['message','inquiryTracking','inquiryTrackingBody']];
    return `<aside class="supplier-trust-panel" aria-labelledby="supplier-trust-title"><div class="supplier-trust-heading">${icon('check')}<div><span class="directory-kicker">${copy('trustKicker')}</span><h2 id="supplier-trust-title">${copy('trustTitle')}</h2></div></div><ul>${items.map(([glyph,title,body])=>`<li><span class="directory-icon">${icon(glyph)}</span><div><strong>${copy(title)}</strong><p>${copy(body)}</p></div></li>`).join('')}</ul><a class="button-link secondary" href="#supplier-directory">${copy('viewSuppliers')}${icon('arrow')}</a></aside>`;
  }

  function supplierEmpty(filtered) {
    return `<div class="supplier-directory-empty"><div class="supplier-empty-seal">${icon('company')}<span>${copy('companyProfile')}</span></div><div><span class="directory-kicker">${copy('publicProfilesOnly')}</span><h3>${filtered ? copy('supplierNoMatch') : copy('supplierEmptyTitle')}</h3><p>${filtered ? copy('supplierNoMatchBody') : copy('supplierEmptyBody')}</p><div class="directory-actions">${button(filtered ? '/trade/suppliers' : '/trade/models',escape(label(filtered ? 'Clear filters' : 'Browse model references')),true)}${button('/supplier/application',copy('applySupplier'))}</div></div></div>`;
  }

  function suppliers({rows, params}) {
    const query = (params.get('supplierQuery') || '').trim().toLocaleLowerCase(window.businessI18n.locale);
    const scope = ['multi','focused','unspecified'].includes(params.get('supplierScope')) ? params.get('supplierScope') : '';
    const filtered = !!(query || scope);
    const shown = rows.filter(s => (!scope || scopeOf(s) === scope) && (!query || [s.company_name,s.city,s.country,s.main_brands].filter(Boolean).join(' ').toLocaleLowerCase(window.businessI18n.locale).includes(query)));
    const brandCount = new Set(rows.flatMap(brandsOf).map(value => value.toLocaleLowerCase(window.businessI18n.locale))).size;
    const countryCount = new Set(rows.map(s => s.country?.trim()).filter(Boolean)).size;
    const scopes = [['','allCompanies'],['multi','multiBrand'],['focused','brandFocused'],['unspecified','unspecifiedBrands']];
    return `<div class="directory-page supplier-directory"><section class="supplier-directory-hero"><div class="directory-hero-copy"><span class="directory-kicker">${copy('supplierKicker')}</span><h1>${copy('supplierTitle')}</h1><p>${copy('supplierSubtitle')}</p>${stats([[rows.length,copy('publicSuppliers')],[countryCount,copy('locations')],[brandCount,copy('declaredBrands')]])}<p class="directory-fineprint">${copy('supplierMetricsNote')}</p></div>${trustPanel()}</section>
      <section class="supplier-trust-summary" aria-label="${copy('trustSummary')}">${[['company','guideVerification','companyCheckNote','/guide/supplier-verification'],['car','guideSourcing','brandCoverageBody','/guide/vehicle-sourcing'],['message','guideProcess','directDiscussionNote','/guide/trade-process']].map(([symbol,title,body,path])=>`<a class="supplier-guide-entry" href="${href(path)}">${icon(symbol)}<strong>${copy(title)}</strong><span>${copy(body)}</span></a>`).join('')}</section>
      <section class="directory-section" id="supplier-directory" aria-labelledby="supplier-directory-title"><div class="directory-section-heading"><div><span class="directory-kicker">${copy('companyProfile')}</span><h2 id="supplier-directory-title">${copy('browseSuppliers')}</h2></div><span class="directory-result-count">${copy('companyCount',{count:shown.length})}</span></div>
      <form class="supplier-directory-search" id="supplier-directory-search" action="/trade/suppliers" method="get"><input type="hidden" name="lang" value="${escape(window.businessI18n.language)}"><label><span>${copy('companySearch')}</span><input name="supplierQuery" type="search" maxlength="120" value="${escape(params.get('supplierQuery') || '')}" placeholder="${copy('companySearchPlaceholder')}"></label><label><span>${copy('brandScope')}</span><select name="supplierScope">${scopes.map(([value,title])=>`<option value="${value}" ${value===scope?'selected':''}>${copy(title)}</option>`).join('')}</select></label><button class="btn" type="submit">${escape(label('Search'))}</button></form>
      <div class="supplier-profile-list">${shown.length ? shown.map(supplierCard).join('') : supplierEmpty(filtered)}</div></section>
      <section class="directory-section supplier-categories"><div class="directory-section-heading"><div><span class="directory-kicker">${copy('findPartner')}</span><h2>${copy('brandScope')}</h2><p>${copy('categoryNote')}</p></div></div><div class="supplier-category-grid">${scopes.slice(1).map(([value,title])=>{const count=rows.filter(s=>scopeOf(s)===value).length;return `<a href="${href('/trade/suppliers',{supplierScope:value})}#supplier-directory" ${value===scope?'aria-current="true"':''}><span>${icon(value==='multi'?'layers':value==='focused'?'car':'company')}</span><strong>${copy(title)}</strong><small>${copy('companyCount',{count})}</small>${icon('arrow')}</a>`;}).join('')}</div></section>
      <section class="directory-section buyer-confidence"><div><span class="directory-kicker">${copy('beforeTrade')}</span><h2>${copy('whyWorkTogether')}</h2><p>${copy('confidenceBody')}</p></div><ol>${[['01','researchPartner','researchPartnerBody'],['02','confirmOffer','confirmOfferBody'],['03','trackReply','trackReplyBody']].map(([index,title,body])=>`<li><span>${index}</span><div><strong>${copy(title)}</strong><p>${copy(body)}</p></div></li>`).join('')}</ol></section>
      <section class="supplier-bottom-cta"><div><span class="directory-kicker">${copy('forSuppliers')}</span><h2>${copy('supplierCta')}</h2><p>${copy('supplierCtaBody')}</p></div>${button('/supplier/application',copy('applySupplier'))}</section></div>`;
  }
  window.businessDirectoryUI = {listings, suppliers, listingCard, supplierCard, brandsOf, scopeOf, text: copy};
})();
