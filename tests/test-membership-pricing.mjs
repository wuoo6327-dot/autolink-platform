import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {join} from 'node:path';
import {fileURLToPath} from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const asset = readFileSync(join(root, 'site/assets/index-autolink-membership-apply-pricing.js'), 'utf8');
const backend = readFileSync(join(root, 'auth/membership_payments.py'), 'utf8');

for (const [plan, first, later] of [
  ['Monthly', '1.99', '19.90'],
  ['Quarterly', '9.99', '29.99'],
  ['Annual', '39.99', '99.99'],
]) {
  assert.match(asset, new RegExp(`name:"${plan}",price:"${first}",renewal:"${later}"`));
}
assert.match(asset, /name:"Annual",price:"39\.99"[^}]+first:"First year"/);
assert.match(asset, /Renew manually at \$99\.99 \/ year\. No automatic charge\./);
assert.match(backend, /"annual": \(12, 3999, 9999\)/);

for (const lang of ['', '.zh', '.ar', '.fr', '.ru', '.ko', '.kk', '.uz', '.sw']) {
  const html = readFileSync(join(root, `site/index${lang}.html`), 'utf8');
  assert.match(html, /index-autolink-membership-apply-pricing\.js\?v=20261017-annual-price/);
}
const loader = readFileSync(join(root, 'site/assets/business-page-bootstrap.mjs'), 'utf8');
assert.match(loader, /page === 'home' \? '\?v=20261017-annual-price'/);
console.log('Membership pricing, manual renewal and nine-language asset references match.');
