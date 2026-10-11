// This independent owner console is always Chinese; public language preferences stay unchanged.
window.AUTOLINK_BUSINESS_FIXED_LANGUAGE='zh';
document.documentElement.lang='zh-CN';
document.documentElement.dir='ltr';
const status=document.querySelector('[data-business-text]');if(status)status.textContent='正在加载平台管理…';
try{
  const chinese=import('/admin/i18n/zh.js?v=20261007-owner-zh');
  await Promise.all([
    import('/vendor/i18next-26.4.2.min.js'),
    chinese.then(()=>import('/admin/i18n/evidence-zh.js?v=20261007-review-gates')),
    import('/assets/business-pagination.js'),
    import('/assets/password-security.js?v=20261006-security'),
    import('/assets/business-seo.js')
  ]);
  await import('/i18n/business-i18n.js?v=20261007-owner-zh');
  await import('/admin/app.js?v=20261012-overseas-seo');
}catch{
  if(status)status.textContent='加载失败，请刷新重试。';
}
