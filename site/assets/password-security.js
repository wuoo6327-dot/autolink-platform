/* Shared account security form; server owns authentication and session revocation. */
(() => {
  const text = value => window.businessI18n?.text(value) || value;
  const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  window.autolinkPasswordForm = data => `<form id="autolink-password-form" class="form-grid" data-mode="${data.passwordSet?'change':'set'}">
    ${data.passwordSet?`<label class="field">${esc(text('Current password'))}<input name="currentPassword" type="password" maxlength="128" required autocomplete="current-password"></label>`:''}
    <label class="field">${esc(text('New password (8–128 characters)'))}<input name="password" type="password" minlength="8" maxlength="128" required autocomplete="new-password"></label>
    <label class="field">${esc(text('Confirm password'))}<input name="confirm" type="password" minlength="8" maxlength="128" required autocomplete="new-password"></label>
    <div class="form-actions"><button class="btn" type="submit">${esc(text('Save Password'))}</button></div>
    <div class="wide" data-password-status role="status" aria-live="polite"></div>
    <p class="notice wide">${esc(text('Changing your password signs out all devices.'))}</p>
    <a class="wide" href="/merchant/login?reset=1">${esc(text('Forgot password'))}</a>
  </form>`;
  document.addEventListener('submit', async event => {
    const form = event.target;
    if (form.id !== 'autolink-password-form') return;
    event.preventDefault();
    if (form.dataset.busy === 'yes') return;
    const values = Object.fromEntries(new FormData(form));
    const status = form.querySelector('[data-password-status]');
    status.textContent = '';
    if (values.password !== values.confirm) {status.textContent = text('Passwords do not match.'); return;}
    const button = form.querySelector('[type=submit]');
    form.dataset.busy = 'yes'; button.disabled = true;
    let response;
    try {
      const endpoint = form.dataset.mode === 'change' ? 'change' : 'set';
      response = await fetch('/autolink/auth/password/'+endpoint, {method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify({password:values.password,currentPassword:values.currentPassword}),signal:AbortSignal.timeout(15000)});
      const result = await response.json();
      if (!response.ok || result.code !== 200) throw Object.assign(Error(typeof result?.msg==='string'?result.msg:'Request failed.'),{status:response.ok?Number(result?.code):response.status});
      form.reset();
      if (result.data?.signedOut) {
        status.textContent = text('Password changed. All devices are signed out.');
        const link = document.createElement('a'); link.className = 'button-link'; link.href = '/merchant/login'; link.textContent = text('Sign in again'); status.append(document.createElement('br'),link);
        form.querySelectorAll('input').forEach(input => input.disabled = true);
      } else {location.reload();}
    } catch (error) {status.textContent = window.businessI18n.apiError?.(error,response?.status).message || text(error.message);button.disabled = false;form.dataset.busy = 'no';}
  });
})();
