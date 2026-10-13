const labels = {
  en: ['Notifications', 'unread', 'You have new notifications', 'View', 'Dismiss'],
  zh: ['通知', '条未读', '您有新通知', '查看', '关闭'],
  ar: ['الإشعارات', 'غير مقروءة', 'لديك إشعارات جديدة', 'عرض', 'إغلاق'],
  ru: ['Уведомления', 'непрочитанных', 'У вас новые уведомления', 'Посмотреть', 'Закрыть'],
  kk: ['Хабарламалар', 'оқылмаған', 'Жаңа хабарламалар бар', 'Қарау', 'Жабу'],
  uz: ['Bildirishnomalar', 'o‘qilmagan', 'Yangi bildirishnomalar bor', 'Ko‘rish', 'Yopish'],
  ko: ['알림', '읽지 않음', '새 알림이 있습니다', '보기', '닫기'],
  fr: ['Notifications', 'non lues', 'Vous avez de nouvelles notifications', 'Voir', 'Fermer'],
  sw: ['Arifa', 'hazijasomwa', 'Una arifa mpya', 'Angalia', 'Funga']
};

export function createNotificationIndicator(userId, destination) {
  const language = window.businessI18n?.language || 'en';
  const [name, unreadLabel, newLabel, viewLabel, closeLabel] = labels[language] || labels.en;
  const seenKey = `autolink-notification-seen:${userId}`;
  let count = 0, latestId = null, stopped = false, inFlight = false, pendingAnnounce = null;
  let toast = null, toastTimer = null;

  function render() {
    if (document.querySelector('#app')?.dataset.notificationUser !== userId) return;
    document.querySelectorAll('[data-notification-badge]').forEach(badge => {
      badge.hidden = count === 0;
      badge.textContent = count > 99 ? '99+' : String(count);
    });
    document.querySelectorAll('[data-notification-link]').forEach(link => {
      link.setAttribute('aria-label', count ? `${name}: ${count} ${unreadLabel}` : name);
    });
  }

  function dismissToast() {
    clearTimeout(toastTimer);
    toast?.remove();
    toast = null;
  }

  function showToast() {
    dismissToast();
    toast = document.createElement('div');
    toast.className = 'notification-toast';
    toast.setAttribute('role', 'status');
    const message = document.createElement('span');
    message.textContent = newLabel;
    const view = document.createElement('a');
    view.href = destination;
    view.textContent = viewLabel;
    const close = document.createElement('button');
    close.type = 'button';
    close.setAttribute('aria-label', closeLabel);
    close.textContent = '×';
    close.addEventListener('click', dismissToast);
    toast.append(message, view, close);
    document.body.append(toast);
    toastTimer = setTimeout(dismissToast, 8000);
  }

  async function refresh({announce = true} = {}) {
    if (stopped || document.hidden) return;
    if (inFlight) {
      pendingAnnounce = pendingAnnounce === null ? announce : pendingAnnounce && announce;
      return;
    }
    inFlight = true;
    try {
      const response = await fetch('/autolink/notifications/summary', {
        credentials: 'same-origin', signal: AbortSignal.timeout(8000)
      });
      if (response.status === 401) { count = 0; render(); return; }
      if (!response.ok) return;
      const payload = await response.json();
      const summary = payload?.code === 200 ? payload.data : null;
      if (stopped || summary?.userId !== userId) return;
      const nextCount = Number(summary.unread);
      if (!Number.isSafeInteger(nextCount) || nextCount < 0) return;
      const nextId = typeof summary.latestId === 'string' ? summary.latestId : null;
      let seenId = null;
      try { seenId = sessionStorage.getItem(seenKey); } catch {}
      if (announce && nextCount > 0 && nextId && nextId !== seenId &&
          (latestId === null || nextCount > count)) showToast();
      count = nextCount;
      latestId = nextId;
      try { if (nextId) sessionStorage.setItem(seenKey, nextId); } catch {}
      render();
    } catch { /* Notifications never block the current page. */ }
    finally {
      inFlight = false;
      if (pendingAnnounce !== null) {
        const nextAnnounce = pendingAnnounce;
        pendingAnnounce = null;
        void refresh({announce: nextAnnounce});
      }
    }
  }

  const onVisible = () => { if (!document.hidden) void refresh(); };
  document.addEventListener('visibilitychange', onVisible);
  const timer = setInterval(() => { if (!document.hidden) void refresh(); }, 30000);
  void refresh();
  return { userId, render, refresh, stop() {
    stopped = true;
    clearInterval(timer);
    document.removeEventListener('visibilitychange', onVisible);
    dismissToast();
  }};
}
