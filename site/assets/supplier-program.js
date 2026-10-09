/* Display-only programme. Applications use the existing support-ticket service.
 * No checkout, payment collection or paid listing entitlement is enabled here.
 */
(() => {
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plan=Object.freeze({version:'supplier-launch-20261007-v1',currency:'USD',baseMinor:20000,
    paymentAvailable:false,applicationUrl:'/support?service=listing',
    periods:Object.freeze([
      Object.freeze({title:'First quarter',discount:'80% off',amountMinor:4000}),
      Object.freeze({title:'Second quarter',discount:'30% off',amountMinor:14000})
    ])});
  const evidence=Object.freeze([
    Object.freeze(['Company details review','Company and contact details are checked before approval.']),
    Object.freeze(['Premises and inventory photos','Submit actual premises and stock photos for review.']),
    Object.freeze(['Manual listing review','Configuration, trade information and price competitiveness are reviewed. Suppliers set their prices.']),
    Object.freeze(['Direct buyer contact','Receive inquiries and manage quotations and follow-ups.'])
  ]);
  const skc='One SKC covers one supplier\'s brand, model and model year. Mid/high trims and colours are SKUs; they are not charged separately.';
  const price=minor=>'US$'+(minor/100).toFixed(0);
  function html(translate){
    const t=key=>escape(translate(key));
    return `<section class="supplier-program" aria-label="${t('Listing service')}">
      <div class="supplier-program-heading"><span class="eyebrow">${t('Founding supplier programme')}</span><h2>${t('Show real inventory to global buyers.')}</h2><p>${t('Apply to join AUTOLINK. Publish reviewed stock, receive inquiries and send quotations.')}</p></div>
      <div class="supplier-program-prices">${plan.periods.map(p=>`<article class="supplier-program-price"><span>${t(p.title)}</span><strong dir="ltr" translate="no">${price(p.amountMinor)}</strong><small>${t('per SKC / quarter')}</small><b>${t(p.discount)}</b></article>`).join('')}<article class="supplier-program-price supplier-program-base"><span>${t('Standard reference')}</span><strong dir="ltr" translate="no">${price(plan.baseMinor)}</strong><small>${t('per SKC / quarter')}</small><b>${t('Quarterly service. Manual renewal.')}</b></article></div>
      <div class="supplier-program-rules"><p>${t(skc)}</p><p>${t('Example: three trims of the same 2026 model count as one SKC, not three.')}</p></div>
      <div class="supplier-program-evidence">${evidence.map(([heading,description])=>`<article><h3>${t(heading)}</h3><p>${t(description)}</p></article>`).join('')}</div>
      <p class="supplier-program-process">${t('Save company details → submit evidence → confirm agreement → company review → listing review.')}</p>
      <p class="supplier-program-status" role="status">${t('Applications are open. No payment is collected; service activation is confirmed separately.')}</p>
      <p class="supplier-program-small">${t('Supplier review is not a transaction guarantee.')}</p>
    </section>`;
  }
  window.autolinkSupplierProgram=Object.freeze({plan,evidence,skc,price,html});
})();
