# AUTOLINK production deployment

Live at `https://autolinkglobal.com` since 2026-10-04. Caddy serves the site from `/opt/autolink-demo`; `auth` is a separate Python container on the internal Docker network. The account database is in the named volume `autolink-demo_auth_data` and has no host port.

Google Identity Services signs in merchant accounts using an ID token and a one-time nonce. The server verifies the token with Google's public keys and binds each account to the Google subject, never to email alone. New accounts require a company name and terms consent. Sessions expire after 30 minutes. `/privacy` explains stored account data and provides self-service deletion when signed in.

The login page uses the user-selected Rolls-Royce image. The current front end shows Google and Meta as its two social entry points. Google is active; Meta opens Facebook and Instagram Professional choices, which remain unavailable until Meta developer setup is complete. Password and supplier account flows are unavailable. Stock, enquiries and quotations are still demonstration content; the merchant API returns empty data until those services are built.

The 2026-10-04 front-end update removed the four icon/feature cards over the hero photo, brightened the Google button, used a vector Meta symbol, and removed the arrow from the disabled password-login button. Only the static front end was deployed; the legal pages and consent-log backend change remain local drafts pending verified business and policy details.

The follow-up Membership Terms document is staged locally as a seventh bilingual legal page at `/membership-terms`. Run `python3 deployment/build_legal_pages.py --preview` and `python3 deployment/prepare-legal-frontend.py` from the workspace root to rebuild the draft; `?draft=legal` on the local preview server shows its footer and membership-page links. The membership page currently has illustrative prices and browser-only demo activation, with no checkout or billing API. The customer has deferred the actual plans/prices, renewal policy confirmation, refund contact, taxes/invoicing, and the legal entity details. Keep the legal draft offline until those facts are verified and the production build passes without placeholders. The existing production Google sign-in remains live for user testing at `https://autolinkglobal.com/merchant/login`.

## Operations

Run in `/opt/autolink-demo`:

```sh
sudo docker compose ps
sudo docker compose logs --tail=100 auth
sudo docker compose exec -T web wget -qO- http://auth:8080/healthz
```

The Google client ID is public and set in `compose.yaml`. The OAuth client secret is not deployed because the ID token flow does not use it. Back up the SQLite volume regularly before users register; there is no automated off-server backup yet.

Pre-Google copies on the server: `compose.yaml.before-google-20261004`, `Caddyfile.before-google-20261004`, and `site/index.html.before-google-20261004`. Restore these three and reload Caddy to revert the public login feature. Keep the auth volume when reverting so registered account data can be recovered.
