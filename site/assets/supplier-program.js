/* Existing supplier programme; the server separately controls checkout eligibility. */
(() => {
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const plan=Object.freeze({version:'supplier-launch-20261007-v1',currency:'USD',baseMinor:20000,
    applicationUrl:'/support?service=listing',
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
  const reviewBeforeCheckout={
    en:'Company and listing reviews come before any available checkout. Payment alone does not publish a listing.',
    zh:'企业和车源审核须先完成，之后才可能开放付款。付款本身不会自动公开车源。',
    ar:'تسبق مراجعة الشركة والإدراج أي دفع متاح. الدفع وحده لا ينشر الإدراج.',
    ru:'Оплата возможна только после проверки компании и объявления. Сама оплата не публикует объявление.',
    kk:'Төлем компания мен хабарландыру тексерілгеннен кейін ғана қолжетімді. Төлем хабарландыруды өздігінен жарияламайды.',
    uz:'To‘lov faqat kompaniya va e’lon tekshirilgandan keyin mavjud bo‘lishi mumkin. To‘lov e’lonni o‘z-o‘zidan chop etmaydi.',
    ko:'회사와 차량 등록 심사가 끝난 뒤에만 결제가 제공될 수 있습니다. 결제만으로 등록이 공개되지는 않습니다.',
    fr:'Le paiement éventuel suit les vérifications de l’entreprise et de l’annonce. Payer ne publie pas automatiquement l’annonce.',
    sw:'Malipo yanapatikana tu baada ya ukaguzi wa kampuni na tangazo. Malipo peke yake hayachapishi tangazo.'
  };
  function html(translate){
    const t=key=>escape(translate(key));
    const status=reviewBeforeCheckout[document.documentElement.lang.toLowerCase().split('-')[0]]||reviewBeforeCheckout.en;
    return `<section class="supplier-program" aria-label="${t('Listing service')}">
      <div class="supplier-program-heading"><span class="eyebrow">${t('Founding supplier programme')}</span><h2>${t('Show real inventory to global buyers.')}</h2><p>${t('Apply to join AUTOLINK. Publish reviewed stock, receive inquiries and send quotations.')}</p></div>
      <div class="supplier-program-prices">${plan.periods.map(p=>`<article class="supplier-program-price"><span>${t(p.title)}</span><strong dir="ltr" translate="no">${price(p.amountMinor)}</strong><small>${t('per SKC / quarter')}</small><b>${t(p.discount)}</b></article>`).join('')}<article class="supplier-program-price supplier-program-base"><span>${t('Standard reference')}</span><strong dir="ltr" translate="no">${price(plan.baseMinor)}</strong><small>${t('per SKC / quarter')}</small><b>${t('Quarterly service. Manual renewal.')}</b></article></div>
      <div class="supplier-program-rules"><p>${t(skc)}</p><p>${t('Example: three trims of the same 2026 model count as one SKC, not three.')}</p></div>
      <div class="supplier-program-evidence">${evidence.map(([heading,description])=>`<article><h3>${t(heading)}</h3><p>${t(description)}</p></article>`).join('')}</div>
      <p class="supplier-program-process">${t('Save company details → submit evidence → confirm agreement → company review → listing review.')}</p>
      <p class="supplier-program-status" role="status">${escape(status)}</p>
      <p class="supplier-program-small">${t('Supplier review is not a transaction guarantee.')}</p>
    </section>`;
  }
  window.autolinkSupplierProgram=Object.freeze({plan,evidence,skc,price,html});
})();
