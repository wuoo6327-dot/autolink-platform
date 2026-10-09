const tr = value => window.businessI18n.text(value);
const root = document.querySelector('#app'), params = new URLSearchParams(location.search);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const api = async (path, method='GET', body) => {
  let response;
  try {
    response = await fetch(path, {method, credentials:'same-origin', headers:{'Content-Type':'application/json'},
      body:body === undefined ? undefined : JSON.stringify(body), signal:AbortSignal.timeout(15000)});
  } catch (error) {
    throw window.businessI18n.apiError?.(error) || Error(['TimeoutError','AbortError'].includes(error.name)
      ? 'The request timed out. Please try again.' : 'Unable to connect. Please try again.');
  }
  let result;
  try { result = await response.json(); } catch { throw window.businessI18n.apiError?.('Request failed.',response.status) || Error('Request failed.'); }
  if (!result || !response.ok || result.code !== 200) throw window.businessI18n.apiError?.(typeof result?.msg === 'string' ? result.msg : 'Request failed.',response.ok?Number(result?.code):response.status) || Error(typeof result?.msg === 'string' ? result.msg : 'Request failed.');
  return result.data;
};
let me = null;

async function start() {
  try { me = await api('/autolink/me'); } catch { /* Visitors can submit general support requests. */ }
  const plan = params.get('plan'), entity = params.get('entity'), id = params.get('id');
  const report = ['vehicle','supplier'].includes(entity) && Boolean(id);
  const listing = !report && !plan && params.get('service') === 'listing';
  const title = report ? (entity === 'supplier' ? 'Report supplier' : 'Report listing') : plan ? 'Membership application' : listing ? 'Listing service application' : 'Contact AUTOLINK';
  document.title = tr(title) + ' | AUTOLINK';
  if (plan && !['monthly','quarterly','annual'].includes(plan)) {
    root.innerHTML = `${window.businessI18n.languageControl()}<h1>${esc(tr('Membership application'))}</h1>
      <div class="alert" role="alert">${esc(tr('Unknown membership plan.'))}</div>
      <a class="button-link secondary" href="/membership">${esc(tr('View membership plans'))}</a>`;
    return;
  }
  const blocked = Boolean(report ? !me : plan && (!me || me.role !== 'BUYER'));
  const signInText = plan && me && me.role !== 'BUYER'
    ? 'Sign in with your buyer account to apply for membership.' : 'Sign in to continue';
  const subject = plan ? tr('Membership application: {plan}').replace('{plan}', tr(plan)) : listing ? tr('Listing service application') : '';
  root.innerHTML = `${window.businessI18n.languageControl()}<span class="eyebrow">${esc(tr('AUTOLINK · SUPPORT'))}</span>
    <h1>${esc(tr(title))}</h1>
    <p>${esc(tr(listing ? 'Tell us your company, model year and planned SKCs. The platform will follow up before any paid service begins.' : 'Submit a request to the platform support team. Your request is stored securely for follow-up.'))}</p>
    ${listing ? window.autolinkSupplierProgram.html(tr) : ''}
    ${blocked ? `<div class="alert"><a href="/buyer/login?returnTo=${encodeURIComponent(location.pathname + location.search)}">${esc(tr(signInText))}</a></div>` : ''}
    <section class="panel"><form id="support-form" class="form-grid">
    <label class="field">${esc(tr('Email'))}<input name="email" type="email" dir="ltr" value="${esc(me?.email || '')}" ${me ? 'readonly' : ''} required autocomplete="email"></label>
    ${report ? `<label class="field">${esc(tr('Reason'))}<select name="reason">${['Fake Vehicle','Incorrect Price','Fraud','Copyright','Spam','Other'].map(value => `<option value="${esc(value)}">${esc(tr(value))}</option>`).join('')}</select></label>`
      : listing ? `<input type="hidden" name="type" value="Supplier Application"><label class="field">${esc(tr('Type'))}<input value="${esc(tr('Supplier Application'))}" readonly></label><label class="field wide">${esc(tr('Subject'))}<input name="subject" maxlength="160" value="${esc(subject)}" required readonly></label>`
      : `<label class="field">${esc(tr('Type'))}<select name="type">${['General Support','Membership','Supplier Application','Report Fraud','Business Cooperation'].map(value => `<option value="${esc(value)}" ${value === (plan ? 'Membership' : params.get('type')) ? 'selected' : ''}>${esc(tr(value))}</option>`).join('')}</select></label>
      <label class="field wide">${esc(tr('Subject'))}<input name="subject" maxlength="160" value="${esc(subject)}" required></label>`}
    <label class="field wide">${esc(tr('Message'))}<textarea name="message" maxlength="${report ? 2000 : listing ? 3500 : 4000}" minlength="5" required ${listing ? `placeholder="${esc(tr('Tell us your company, model year and planned SKCs. The platform will follow up before any paid service begins.'))}"` : ''}></textarea></label>
    ${listing ? `<p class="notice wide">${esc(tr('Apply after company and vehicle review. Submitting this request does not publish a listing.'))}</p>` : ''}
    ${plan ? `<p class="notice wide">${esc(tr('Selected plan: {plan}').replace('{plan}', tr(plan)))} ${esc(tr('This is an application; it does not activate membership or charge a payment. All plans require manual renewal.'))}</p>
      <label class="consent wide"><input name="consent" type="checkbox" required><span>${esc(tr('I agree to the'))} <a href="/terms" target="_blank" rel="noopener">${esc(tr('Terms of Service'))}</a>,
      <a href="/membership-terms" target="_blank" rel="noopener">${esc(tr('Membership Terms'))}</a> ${esc(tr('and'))} <a href="/privacy" target="_blank" rel="noopener">${esc(tr('Privacy Policy'))}</a> ${esc(tr('for this application.'))}</span></label>` : ''}
    <div class="form-actions"><button class="btn" type="submit" ${blocked ? 'disabled' : ''}>${esc(tr(report ? 'Submit report' : 'Submit request'))}</button></div>
    </form><div id="support-result" class="support-result" role="status" aria-live="polite"></div></section>`;
  const form = document.querySelector('#support-form');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (blocked) return;
    const button = form.querySelector('[type=submit]');
    if (button.disabled) return;
    button.disabled = true;
    const values = Object.fromEntries(new FormData(form));
    if (listing) {
      values.type = 'Supplier Application';
      values.subject = tr('Listing service application');
      values.message = `[AUTOLINK ${window.autolinkSupplierProgram.plan.version}; Q1 USD40; Q2 USD140; applications only, no payment]\n` + values.message;
    }
    try {
      const result = await api(report ? '/autolink/reports' : '/autolink/support', 'POST', report
        ? {entityType:entity, entityId:id, reason:values.reason, message:values.message}
        : {...values, plan:plan || undefined, consent:values.consent === 'on', language:window.businessI18n.language});
      if (typeof result?.id !== 'string' || !result.id.trim()) throw Error('Request failed.');
      form.hidden = true;
      const message = report ? 'Your report was received. Reference: {reference}.'
        : 'Your request was received. Reference: {reference}. No payment has been collected.';
      document.querySelector('#support-result').textContent = tr(message).replace('{reference}', String(result.id));
    } catch (error) {
      document.querySelector('#support-result').textContent = tr(error.message);
      button.disabled = false;
    }
  });
}
start();
