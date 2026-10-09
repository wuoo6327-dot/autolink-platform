/* Shared database-list paging. It never slices a full client-side data set. */
(() => {
  const pages = new WeakMap();
  const esc = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function from(result, key='page') {
    if (!result || !Array.isArray(result.items) || !Number.isSafeInteger(result.page) || result.page<1 ||
        result.pageSize!==25 || !Number.isSafeInteger(result.total) || result.total<0 ||
        result.pages!==Math.ceil(result.total/25) || result.hasMore!==(result.page*25<result.total) ||
        result.items.length>25) throw Error('Request failed.');
    const rows = result.items;
    pages.set(rows, {page:result.page,total:result.total,pages:result.pages,key});
    return rows;
  }
  function query(path, keys=['page']) {
    const url = new URL(path, location.origin), current = new URLSearchParams(location.search);
    for(const key of keys) url.searchParams.set(key, current.get(key) || '1');
    return url.pathname+url.search;
  }
  async function load(api, path, key='page') {
    return from(await api(query(path,[key])), key);
  }
  function controls(rows) {
    const data = pages.get(rows);
    if(!data) return '';
    const tr = window.businessI18n.text;
    const href = page => {
      const q = new URLSearchParams(location.search);
      q.set(data.key,String(page));
      return esc(location.pathname+'?'+q.toString());
    };
    const previous = data.page>1 ? `<a class="button-link secondary" rel="prev" href="${href(Math.min(data.page-1,Math.max(1,data.pages)))}">${esc(tr('Previous'))}</a>` :
      `<button class="btn secondary" type="button" disabled>${esc(tr('Previous'))}</button>`;
    const next = data.page<data.pages ? `<a class="button-link secondary" rel="next" href="${href(data.page+1)}">${esc(tr('Next'))}</a>` :
      `<button class="btn secondary" type="button" disabled>${esc(tr('Next'))}</button>`;
    const format = value => new Intl.NumberFormat(window.businessI18n.locale).format(value);
    return `<nav class="business-pagination" aria-label="${esc(tr('Pagination'))}">${previous}<span>${esc(tr('Page'))} <bdi>${format(data.page)} / ${format(Math.max(1,data.pages))}</bdi> · ${format(data.total)} ${esc(tr('Records'))}</span>${next}</nav>`;
  }
  window.businessPagination = {load,from,query,controls};
})();
