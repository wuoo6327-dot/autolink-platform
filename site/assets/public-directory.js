/* Only reviewed public records; no private contacts, certification or stock inference. */
(() => {
  let cached = null, expires = 0, pending = null;
  const split = value => typeof value === 'string' ? value.split(/[,，;；]/).map(part => part.trim()).filter(Boolean) : [];
  const project = items => {
    if (!Array.isArray(items)) throw new Error('Invalid public supplier directory.');
    return items.map(item => ({
      id: item.id, name: item.company_name, city: item.city || '', country: item.country || '',
      introduction: item.description || '', brands: split(item.main_brands), markets: split(item.main_markets),
      established: item.established_year || ''
    }));
  };
  async function load(request) {
    if (cached && Date.now() < expires) return cached;
    if (pending) return pending;
    pending = Promise.resolve().then(() => request('/autolink/public/suppliers')).then(project).then(items => {
      cached = items; expires = Date.now() + 60000; return items;
    });
    try { return await pending; } finally { pending = null; }
  }
  window.AUTOLINK_PUBLIC_DIRECTORY = Object.freeze({load});
})();
