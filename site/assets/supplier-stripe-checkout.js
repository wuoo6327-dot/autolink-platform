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
    button.className = 'btn'; button.type = 'button'; button.textContent = pay;
    const status = document.createElement('p');
    status.className = 'notice'; status.setAttribute('role', 'status');
    if (new URLSearchParams(location.search).get('checkout') === 'return') status.textContent = returned;
    button.addEventListener('click', async () => {
      button.disabled = true; status.textContent = opening;
      try {
        const response = await fetch(`/autolink/supplier/vehicles/${encodeURIComponent(listing)}/listing-checkout`, {
          method: 'POST', credentials: 'same-origin',
          headers: {'Content-Type': 'application/json', 'X-Autolink-Supplier': workspace}, body: '{}'
        });
        if (!response.ok) throw Error(unavailable);
        const payload = await response.json();
        const url = new URL(payload?.data?.checkoutUrl);
        if (url.protocol !== 'https:' || url.hostname !== 'checkout.stripe.com') throw Error(unavailable);
        location.assign(url.href);
      } catch { status.textContent = unavailable; button.disabled = false; }
    });
    card.append(header, amount, button, status);
    host.append(card);
  }
  new MutationObserver(schedule).observe(document.querySelector('#app'), {childList: true, subtree: true});
  schedule();
})();
