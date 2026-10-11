import {ensureBusinessLanguage} from '/assets/business-language-loader.mjs?v=20261009-speed';
import {guides,languages} from './content.mjs';
import {shell,metadata,href,availabilityHTML} from './render.mjs';

const id=location.pathname.replace(/\/$/,'').split('/').pop().replace(/\.(?:zh|fallback)?\.?html$/,'');
const root=document.querySelector('#guide-app');
// Full static content remains readable if the language runtime cannot load.
if(guides[id] && root) {
  try {
    await ensureBusinessLanguage();
    const language=window.businessI18n.language;
    root.innerHTML=shell(id,language,value=>window.businessI18n.text(value));
    const meta=metadata(id,language);
    document.title=meta.title;
    document.querySelector('meta[name="description"]').content=meta.description;
    document.querySelector('meta[name="robots"]').content=meta.robots;
    document.querySelector('link[rel="canonical"]').href=meta.canonical;
    // Keep the public language switch read-only. It does not write preferences
    // or alter the existing buyer/supplier authentication workflow.
    root.querySelector('[data-guide-language]')?.addEventListener('change',event=>{
      if(languages.includes(event.target.value))location.assign(href('/guide/'+id,event.target.value));
    });
    const availability=root.querySelector('[data-guide-availability]');
    let checking=false;
    async function checkAvailability() {
      if(!availability || checking)return;
      checking=true;
      try {
        const resource=guides[id].availability;
        const response=await fetch('/autolink/public/'+resource+(resource==='vehicles'?'?limit=1':''),{
          method:'GET',credentials:'omit',cache:'no-store',signal:AbortSignal.timeout(10000)
        });
        const payload=await response.json();
        if(!response.ok || payload.code!==200 || !Array.isArray(payload.data))throw new Error('Public directory unavailable');
        availability.innerHTML=availabilityHTML(id,language,payload.data.length?'ready':'empty');
      } catch {
        availability.innerHTML=availabilityHTML(id,language,'error');
      } finally {checking=false;}
    }
    root.addEventListener('click',event=>{if(event.target.closest('[data-guide-retry]'))checkAvailability();});
    await checkAvailability();
  } catch {
    // Do not replace a useful initial document with an empty error screen.
    root.querySelector('[data-guide-availability]')?.remove();
  }
}
