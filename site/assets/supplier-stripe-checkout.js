/* Optional checkout for a reviewed supplier listing. The server owns price and eligibility. */
(() => {
  const messages = {
    en: ['Listing service', 'One reviewed SKC for one quarter. Renewal is manual.', 'Pay securely with Stripe', 'Opening Stripe checkout…', 'Payment status is being confirmed. Check your listing service record before trying again.', 'Online payment is temporarily unavailable.'],
    zh: ['车源上架服务', '一项已审核 SKC 的一个季度服务，需手动续费。', '前往 Stripe 安全付款', '正在打开 Stripe 收银台…', '付款状态正在确认，请先核对上架服务记录，不要重复付款。', '在线付款暂时不可用。'],
    ar: ['خدمة نشر المركبة', 'خدمة ربع سنوية لإدراج SKC واحد تمت مراجعته. التجديد يدوي.', 'الدفع الآمن عبر Stripe', 'جارٍ فتح صفحة الدفع…', 'يجري تأكيد حالة الدفع. راجع سجل خدمة الإدراج قبل المحاولة مرة أخرى.', 'الدفع عبر الإنترنت غير متاح مؤقتاً.'],
    ru: ['Услуга размещения', 'Один проверенный SKC на квартал. Продление вручную.', 'Оплатить через Stripe', 'Открываем Stripe…', 'Статус оплаты проверяется. Посмотрите запись об услуге до повторной оплаты.', 'Онлайн оплата временно недоступна.'],
    kk: ['Жариялау қызметі', 'Бір тексерілген SKC үшін бір тоқсан. Қолмен жаңартылады.', 'Stripe арқылы төлеу', 'Stripe ашылуда…', 'Төлем күйі тексерілуде. Қайта төлемес бұрын қызмет жазбасын қараңыз.', 'Онлайн төлем уақытша қолжетімсіз.'],
    uz: ['E’lon xizmati', 'Bir tasdiqlangan SKC uchun bir chorak. Qo‘lda yangilanadi.', 'Stripe orqali to‘lash', 'Stripe ochilmoqda…', 'To‘lov holati tekshirilmoqda. Qayta to‘lashdan oldin xizmat qaydini ko‘ring.', 'Onlayn to‘lov vaqtincha mavjud emas.'],
    ko: ['차량 등록 서비스', '검토가 끝난 SKC 하나의 분기 서비스입니다. 직접 갱신합니다.', 'Stripe에서 안전하게 결제', 'Stripe 결제 페이지를 여는 중…', '결제 상태를 확인 중입니다. 다시 결제하기 전에 서비스 내역을 확인하세요.', '온라인 결제를 일시적으로 사용할 수 없습니다.'],
    fr: ['Service de publication', 'Un SKC vérifié pour un trimestre. Renouvellement manuel.', 'Payer avec Stripe', 'Ouverture du paiement Stripe…', 'Le paiement est en cours de vérification. Consultez le suivi du service avant de réessayer.', 'Paiement en ligne temporairement indisponible.'],
    sw: ['Huduma ya kutangaza gari', 'SKC moja iliyokaguliwa kwa robo mwaka. Utaongeza muda mwenyewe.', 'Lipa kwa usalama kupitia Stripe', 'Tunafungua malipo ya Stripe…', 'Hali ya malipo inathibitishwa. Angalia rekodi ya huduma kabla ya kulipa tena.', 'Malipo ya mtandaoni hayapatikani kwa muda.']
  };
  const words = () => messages[document.documentElement.lang.toLowerCase().split('-')[0]] || messages.en;
  const disclosures = {
    en: 'I understand this is a manually renewed, three-month listing service for one reviewed SKC. Confirmed payment publishes eligible unchanged listings; expiry or a full refund removes them. Partial refunds and disputes require review. Vehicle sales are separate.',
    zh: '我已了解：这是按一个已审核 SKC 收取的三个月上架服务费，需手动续费。确认付款后，符合条件且资料未变更的车源上线；到期或全额退款后下线。部分退款及争议由人工处理。车辆交易另行进行。',
    ar: 'أفهم أن هذه خدمة إدراج لمدة ثلاثة أشهر لـ SKC واحد تمت مراجعته، وتجديدها يدوي. تنشر الدفعة المؤكدة الإدراجات المؤهلة غير المعدّلة؛ وينتهي عرضها عند انتهاء المدة أو رد المبلغ بالكامل. تُراجع المبالغ المستردة جزئيًا والنزاعات يدويًا. بيع المركبات منفصل.',
    ru: 'Я понимаю: это услуга размещения одного проверенного SKC на три месяца с ручным продлением. Подтверждённая оплата публикует подходящие неизменённые объявления; по истечении срока или после полного возврата они снимаются. Частичный возврат и споры рассматриваются вручную. Продажа автомобилей осуществляется отдельно.',
    kk: 'Бұл бір тексерілген SKC үшін үш айлық, қолмен ұзартылатын жариялау қызметі екенін түсінемін. Расталған төлем жарамды әрі өзгермеген хабарландыруларды жариялайды; мерзімі бітсе немесе толық қайтарым жасалса, олар алынады. Ішінара қайтарымдар мен даулар жеке қаралады. Автокөлік саудасы бөлек жасалады.',
    uz: 'Bu bitta tekshirilgan SKC uchun uch oylik, qo‘lda uzaytiriladigan e’lon xizmati ekanini tushunaman. Tasdiqlangan to‘lov mos va o‘zgarmagan e’lonlarni chiqaradi; muddat tugasa yoki to‘liq qaytarim bo‘lsa, ular olib tashlanadi. Qisman qaytarim va nizolar alohida ko‘rib chiqiladi. Avtomobil savdosi alohida.',
    ko: '이 서비스는 심사된 SKC 하나에 대한 3개월 등록 서비스이며 갱신은 직접 진행해야 합니다. 결제가 확인되면 변경되지 않은 적격 등록이 공개되고, 기간 만료 또는 전액 환불 시 내려갑니다. 부분 환불과 분쟁은 별도 심사합니다. 차량 거래는 별개입니다.',
    fr: 'Je comprends que ce service de publication de trois mois concerne un SKC vérifié et se renouvelle manuellement. Un paiement confirmé publie les annonces admissibles et inchangées ; elles sont retirées à l’expiration ou après remboursement intégral. Les remboursements partiels et litiges sont examinés. La vente du véhicule est distincte.',
    sw: 'Ninaelewa kuwa hii ni huduma ya miezi mitatu kwa SKC moja iliyokaguliwa, inayoongezwa muda kwa hiari. Malipo yakithibitishwa, matangazo yanayostahili na ambayo hayajabadilishwa huchapishwa; huondolewa muda ukiisha au malipo yakirudishwa yote. Marejesho ya sehemu na migogoro hukaguliwa. Mauzo ya gari ni tofauti.'
  };
  const path = () => location.pathname.match(/^\/supplier\/vehicles\/([^/]+)$/);
  let scheduled = false;
  function schedule() {
    if (scheduled) return;
    scheduled = true;
    queueMicrotask(() => { scheduled = false; void mount(); });
  }
  async function mount() {
    const match = path(), host = document.querySelector('#supplier-content');
    if (!match || !host || host.dataset.stripeQuoteFor === location.pathname) return;
    const workspace = document.querySelector('#supplier-workspace')?.value;
    if (!workspace || match[1] === 'new') return;
    host.dataset.stripeQuoteFor = location.pathname;
    const listing = match[1];
    let quote;
    try {
      const response = await fetch(`/autolink/supplier/vehicles/${encodeURIComponent(listing)}/listing-quote`, {
        credentials: 'same-origin', cache: 'no-store', headers: {'X-Autolink-Supplier': workspace}
      });
      if (!response.ok) return;
      const payload = await response.json();
      quote = payload?.data;
    } catch { return; }
    if (!quote?.available || !host.isConnected || host !== document.querySelector('#supplier-content') ||
        workspace !== document.querySelector('#supplier-workspace')?.value || !path()) return;
    const [heading, detail, pay, opening, returned, unavailable] = words();
    const card = document.createElement('section');
    card.className = 'panel';
    card.setAttribute('aria-label', heading);
    const header = document.createElement('div');
    header.className = 'panel-head';
    const h2 = document.createElement('h2');
    h2.textContent = heading;
    header.append(h2);
    const amount = document.createElement('p');
    amount.textContent = `${new Intl.NumberFormat(document.documentElement.lang, {style:'currency',currency:'USD'}).format(quote.amountMinor / 100)} · ${detail}`;
    const button = document.createElement('button');
    button.className = 'btn'; button.type = 'button'; button.textContent = pay; button.disabled = true;
    const consent = document.createElement('label');
    consent.className = 'supplier-public-consent';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox'; checkbox.required = true;
    const explanation = document.createElement('span');
    explanation.textContent = disclosures[document.documentElement.lang.toLowerCase().split('-')[0]] || disclosures.en;
    const terms = document.createElement('a');
    terms.href = '/supplier-listing-terms'; terms.target = '_blank'; terms.rel = 'noopener';
    terms.textContent = document.documentElement.lang.toLowerCase().startsWith('zh') ? '查看上架服务条款' : 'Read listing service terms';
    consent.append(checkbox, explanation);
    checkbox.addEventListener('change', () => { button.disabled = !checkbox.checked; });
    const status = document.createElement('p');
    status.className = 'notice'; status.setAttribute('role', 'status');
    if (new URLSearchParams(location.search).get('checkout') === 'return') status.textContent = returned;
    button.addEventListener('click', async () => {
      if (!checkbox.checked) return;
      button.disabled = true; status.textContent = opening;
      try {
        const response = await fetch(`/autolink/supplier/vehicles/${encodeURIComponent(listing)}/listing-checkout`, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-Autolink-Supplier': workspace},
          body: JSON.stringify({serviceConsent: true, serviceTermsVersion: 'supplier-listing-service-20261017-v1'})
        });
        if (!response.ok) throw Error(unavailable);
        const payload = await response.json();
        const url = new URL(payload?.data?.checkoutUrl);
        if (url.protocol !== 'https:' || url.hostname !== 'checkout.stripe.com') throw Error(unavailable);
        location.assign(url.href);
      } catch { status.textContent = unavailable; button.disabled = !checkbox.checked; }
    });
    card.append(header, amount, terms, consent, button, status);
    host.append(card);
  }
  new MutationObserver(schedule).observe(document.querySelector('#app'), {childList: true, subtree: true});
  schedule();
})();
