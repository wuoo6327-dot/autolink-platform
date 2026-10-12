/* Progressive enhancement for the existing membership modal. */
(() => {
  const copy = {
    en: ['Pay for one period', 'Automatic renewal is unavailable. Renew manually at the standard price.', 'Card (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'Sign in as a buyer to pay.', 'This payment method is awaiting merchant approval.', 'Opening secure checkout…', 'Available payment methods are shown at checkout. Each paid period ends unless you renew it.', 'Choose a secure payment method below, or contact AUTOLINK for help. Membership starts only after confirmed payment.'],
    zh: ['购买一个会员周期', '自动续费尚未开放；到期后按正常价格手动续费。', '银行卡（Stripe）', '支付宝（空中云汇）', '微信支付（空中云汇）', '请先登录买家账号。', '该支付方式仍待商户审核。', '正在打开安全收银台…', '可用支付方式将在结算时显示。已付款周期结束后需自行续费。', '请在下方选择安全支付方式，或联系 AUTOLINK 寻求帮助。付款确认后才会开通会员。'],
    ar: ['ادفع لفترة واحدة', 'التجديد التلقائي غير متاح. جدّد يدوياً بالسعر العادي.', 'بطاقة (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'سجّل دخولك كمشترٍ للدفع.', 'طريقة الدفع هذه بانتظار موافقة التاجر.', 'جارٍ فتح الدفع الآمن…', 'تظهر طرق الدفع المتاحة عند إتمام الطلب. يجب تجديد العضوية يدوياً بعد انتهاء الفترة المدفوعة.', 'اختر طريقة دفع آمنة أدناه أو اتصل بـ AUTOLINK للمساعدة. تبدأ العضوية بعد تأكيد الدفع فقط.'],
    ru: ['Оплатить один период', 'Автопродление недоступно. Продлите вручную по обычной цене.', 'Карта (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'Войдите как покупатель для оплаты.', 'Способ оплаты ожидает одобрения продавца.', 'Открываем защищённую оплату…', 'Доступные способы оплаты показаны при оформлении. После оплаченного периода продлите членство вручную.', 'Выберите безопасный способ оплаты ниже или обратитесь в AUTOLINK. Членство начнётся только после подтверждения оплаты.'],
    kk: ['Бір кезеңге төлеу', 'Автоматты ұзарту қолжетімсіз. Әдеттегі бағамен қолмен ұзартыңыз.', 'Карта (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'Төлеу үшін сатып алушы ретінде кіріңіз.', 'Төлем әдісі саудагердің мақұлдауын күтуде.', 'Қауіпсіз төлем ашылуда…', 'Қолжетімді төлем әдістері рәсімдеу кезінде көрсетіледі. Төленген мерзім біткен соң өзіңіз ұзартыңыз.', 'Төменнен қауіпсіз төлем әдісін таңдаңыз немесе AUTOLINK қызметіне хабарласыңыз. Мүшелік төлем расталғаннан кейін басталады.'],
    uz: ['Bir davr uchun to‘lash', 'Avtomatik yangilash mavjud emas. Oddiy narxda qo‘lda yangilang.', 'Karta (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'To‘lash uchun xaridor sifatida kiring.', 'To‘lov usuli tasdiqlanishini kutmoqda.', 'Xavfsiz to‘lov ochilmoqda…', 'Mavjud to‘lov usullari rasmiylashtirishda ko‘rsatiladi. To‘langan muddat tugagach, a’zolikni qo‘lda yangilang.', 'Quyida xavfsiz to‘lov usulini tanlang yoki AUTOLINK bilan bog‘laning. A’zolik faqat to‘lov tasdiqlangach boshlanadi.'],
    ko: ['한 기간 결제', '자동 갱신은 제공되지 않습니다. 정상 가격으로 직접 갱신하세요.', '카드(Stripe)', 'Alipay(Airwallex)', 'WeChat Pay(Airwallex)', '결제하려면 구매자 계정으로 로그인하세요.', '이 결제 수단은 가맹점 승인을 기다리고 있습니다.', '보안 결제 페이지를 여는 중…', '이용 가능한 결제 수단은 결제 단계에서 표시됩니다. 결제 기간 종료 후 직접 갱신해야 합니다.', '아래에서 안전한 결제 수단을 선택하거나 AUTOLINK에 문의하세요. 결제가 확인된 후에만 멤버십이 시작됩니다.'],
    fr: ['Payer une période', 'Renouvellement automatique indisponible. Renouvelez manuellement au tarif normal.', 'Carte (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'Connectez-vous comme acheteur pour payer.', 'Ce mode de paiement attend l’approbation du marchand.', 'Ouverture du paiement sécurisé…', 'Les moyens de paiement disponibles s’affichent à la commande. Renouvelez vous-même à la fin de la période payée.', 'Choisissez un moyen de paiement sécurisé ci-dessous ou contactez AUTOLINK. L’adhésion commence après confirmation du paiement.'],
    sw: ['Lipa kipindi kimoja', 'Uhuishaji wa kiotomatiki haupatikani. Sasisha mwenyewe kwa bei ya kawaida.', 'Kadi (Stripe)', 'Alipay (Airwallex)', 'WeChat Pay (Airwallex)', 'Ingia kama mnunuzi ili ulipe.', 'Njia hii ya malipo inasubiri idhini ya mfanyabiashara.', 'Tunafungua malipo salama…', 'Njia za malipo zinazopatikana zinaonyeshwa unapolipa. Sasisha mwenyewe baada ya kipindi ulicholipia.', 'Chagua njia salama ya malipo hapa chini au wasiliana na AUTOLINK. Uanachama huanza tu baada ya malipo kuthibitishwa.']
  };
  const methods = [['stripe_card', 2], ['airwallex_alipay', 3], ['airwallex_wechat', 4]];
  let plan = null;
  let mounted = null;
  const lang = () => {
    const code = document.documentElement.lang.toLowerCase().split('-')[0];
    return copy[code] || copy.en;
  };
  const planAt = button => {
    const card = button.closest('.plan-grid article');
    if (!card) return null;
    return ['monthly', 'quarterly', 'annual'][Array.from(card.parentElement.children).indexOf(card)] || null;
  };
  document.addEventListener('click', event => {
    const button = event.target.closest('.plan-grid article button');
    if (button) plan = planAt(button);
  }, true);
  async function mount() {
    if (location.pathname !== '/membership') return;
    const modal = document.querySelector('.membership-apply');
    if (!modal || !plan || modal === mounted) return;
    mounted = modal;
    const wrapper = document.createElement('section');
    wrapper.className = 'membership-checkout';
    wrapper.setAttribute('aria-label', lang()[0]);
    const title = document.createElement('strong');
    title.textContent = lang()[0];
    const detail = document.createElement('p');
    detail.textContent = lang()[1];
    const buttons = document.createElement('div');
    buttons.className = 'membership-checkout-methods';
    const status = document.createElement('p');
    status.setAttribute('role', 'status');
    wrapper.append(title, detail, buttons, status);
    modal.append(wrapper);
    let data;
    try {
      const response = await fetch('/autolink/buyer/membership', {credentials: 'same-origin', cache: 'no-store'});
      if (response.status === 401 || response.status === 403) {
        const link = document.createElement('a');
        link.href = '/buyer/login?returnTo=%2Fmembership';
        link.textContent = lang()[5];
        buttons.append(link);
        return;
      }
      if (!response.ok) throw new Error('Membership status unavailable');
      data = (await response.json()).data;
    } catch (_) {
      status.textContent = lang()[6];
      return;
    }
    if (modal !== mounted || !modal.isConnected) return;
    const due = data.pricing.plans[plan].dueMinor;
    title.textContent = `${lang()[0]} · $${(due / 100).toFixed(2)} USD`;
    let available = 0;
    methods.forEach(([method, label]) => {
      if (!data.pricing.methods[method].available) return;
      available++;
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = lang()[label];
      button.addEventListener('click', async () => {
        button.disabled = true;
        status.textContent = lang()[7];
        try {
          const response = await fetch('/autolink/buyer/membership/checkout', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({plan, method, autoRenew: false})
          });
          const result = await response.json();
          if (!response.ok || !result.data?.checkoutUrl) throw new Error(result.msg || lang()[6]);
          const url = new URL(result.data.checkoutUrl);
          if (url.protocol !== 'https:' || !['checkout.stripe.com', 'checkout.airwallex.com'].includes(url.hostname)) throw new Error(lang()[6]);
          location.assign(url.href);
        } catch (error) {
          status.textContent = error.message;
          button.disabled = false;
        }
      });
      buttons.append(button);
    });
    if (!available) {
      status.textContent = lang()[6];
    } else {
      const pageNotice = document.querySelector('.plan-grid')?.previousElementSibling?.querySelector('p');
      const modalNotice = modal.querySelector('.membership-apply-plan + p');
      if (pageNotice) pageNotice.textContent = lang()[8];
      if (modalNotice) modalNotice.textContent = lang()[9];
    }
  }
  new MutationObserver(mount).observe(document.documentElement, {childList: true, subtree: true});
  mount();
})();
