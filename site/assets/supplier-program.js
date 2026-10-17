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
    en:'Checkout opens only after company and listing review. A confirmed payment publishes an unchanged, eligible listing for three months; changed listings require manual review.',
    zh:'企业和车源审核通过后才开放付款。确认收款后，符合条件且未变更的车源上线三个月；资料变更须重新人工审核。',
    ar:'لا يتاح الدفع إلا بعد مراجعة الشركة والإعلان. ينشر الدفع المؤكد الإعلان المؤهل وغير المعدّل لمدة ثلاثة أشهر؛ وتتطلب التغييرات مراجعة يدوية.',
    ru:'Оплата доступна после проверки компании и объявления. Подтверждённая оплата публикует неизменённое подходящее объявление на три месяца; изменения требуют повторной проверки.',
    kk:'Төлем компания мен хабарландыру тексерілген соң ғана қолжетімді. Расталған төлем өзгермеген жарамды хабарландыруды үш айға жариялайды; өзгерістер қайта қаралады.',
    uz:'To‘lov kompaniya va e’lon tekshirilgach ochiladi. Tasdiqlangan to‘lov o‘zgarmagan mos e’lonni uch oyga chiqaradi; o‘zgarishlar qayta ko‘rib chiqiladi.',
    ko:'회사와 차량 등록 심사가 끝난 뒤 결제할 수 있습니다. 결제가 확인되면 변경되지 않은 적격 등록이 3개월간 공개되며, 변경 시 재심사가 필요합니다.',
    fr:'Le paiement suit la vérification de l’entreprise et de l’annonce. Une fois confirmé, il publie l’annonce admissible et inchangée pendant trois mois ; toute modification exige un nouvel examen.',
    sw:'Malipo hupatikana baada ya kampuni na tangazo kukaguliwa. Malipo yakithibitishwa, tangazo linalostahili na ambalo halijabadilishwa huonekana kwa miezi mitatu; mabadiliko huhitaji ukaguzi tena.'
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
