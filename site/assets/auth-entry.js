/* Shared entry labels and navigation only. Account permissions remain server controlled. */
(() => {
  const labels={
    en:{buyer:"I'm a buyer",supplier:"I'm a supplier",buyerHint:'Global vehicle buyers',supplierHint:'Automotive suppliers and exporters',label:'Choose your account type'},
    zh:{buyer:'我是采购商',supplier:'我是供应商',buyerHint:'全球汽车采购商',supplierHint:'汽车供应商与出口企业',label:'选择账号类型'},
    ar:{buyer:'أنا مشتري',supplier:'أنا مورّد',buyerHint:'مشترو السيارات حول العالم',supplierHint:'موردو السيارات وشركات التصدير',label:'اختر نوع الحساب'},
    ru:{buyer:'Я покупатель',supplier:'Я поставщик',buyerHint:'Покупатели автомобилей по всему миру',supplierHint:'Поставщики и экспортёры автомобилей',label:'Выберите тип аккаунта'},
    kk:{buyer:'Мен сатып алушымын',supplier:'Мен жеткізушімін',buyerHint:'Әлемдік автокөлік сатып алушылары',supplierHint:'Автокөлік жеткізушілері мен экспорттаушылар',label:'Тіркелгі түрін таңдаңыз'},
    uz:{buyer:'Men xaridorman',supplier:'Men yetkazib beruvchiman',buyerHint:'Dunyo bo‘ylab avtomobil xaridorlari',supplierHint:'Avtomobil yetkazib beruvchilar va eksportchilar',label:'Hisob turini tanlang'},
    ko:{buyer:'저는 구매자입니다',supplier:'저는 공급업체입니다',buyerHint:'글로벌 자동차 구매자',supplierHint:'자동차 공급업체 및 수출 기업',label:'계정 유형 선택'},
    fr:{buyer:'Je suis acheteur',supplier:'Je suis fournisseur',buyerHint:'Acheteurs de véhicules dans le monde',supplierHint:'Fournisseurs et exportateurs automobiles',label:'Choisissez votre type de compte'},
    sw:{buyer:'Mimi ni mnunuzi',supplier:'Mimi ni msambazaji',buyerHint:'Wanunuzi wa magari duniani',supplierHint:'Wasambazaji na wauzaji wa magari nje ya nchi',label:'Chagua aina ya akaunti'}
  };
  const normalize=value=>value==='zh-CN'?'zh':value;
  const supported=value=>Object.hasOwn(labels,normalize(value));
  function text(language,key){return (labels[normalize(language)]||labels.en)[key]||'';}
  function safeReturnTo(value,kind){
    if(typeof value!=='string'||!value.startsWith('/')||value.startsWith('//')||/[\\\x00-\x1f\x7f]/.test(value))return null;
    try{
      const decoded=decodeURIComponent(value);
      if(decoded.startsWith('//')||/[\\\x00-\x1f\x7f]/.test(decoded))return null;
      const origin=location.origin||'https://autolinkglobal.com',destination=new URL(value,origin),path=new URL(decoded,origin).pathname;
      if(destination.origin!==origin)return null;
      const center=kind==='buyer'?'/buyer':'/supplier';
      const ownCenter=path===center||path.startsWith(center+'/');
      if(/^\/buyer\/(?:login|register)(?:\/|$)/.test(path))return null;
      const publicPage=['/','/membership','/support','/about','/contact','/help','/how-it-works'].includes(path)||/^\/(?:trade\/)?(?:vehicles|models|brands|suppliers)(?:\/|$)/.test(path);
      return ownCenter||publicPage?destination.pathname+destination.search+destination.hash:null;
    }catch{return null;}
  }
  function url(kind,{register=false}={}){
    if(!['buyer','supplier'].includes(kind))throw new TypeError('Unknown account entry.');
    const current=new URLSearchParams(location.search||''),query=new URLSearchParams();
    const requested=current.get('lang'),language=supported(requested)?normalize(requested):supported(window.businessI18n?.language)?normalize(window.businessI18n.language):supported(document.documentElement?.lang)?normalize(document.documentElement.lang):null;
    if(language)query.set('lang',language);
    const destination=safeReturnTo(current.get('returnTo'),kind);
    if(destination)query.set('returnTo',destination);
    return `/${kind==='buyer'?'buyer':'merchant'}/${register===true?'register':'login'}${query.size?'?'+query.toString():''}`;
  }
  window.AUTOLINK_AUTH_ENTRY=Object.freeze({text,url});
})();
