"""Server-side authorization-code exchanges for AUTOLINK social sign-in."""

from __future__ import annotations

import os
from urllib.parse import urlencode

import jwt
import requests


ORIGIN = "https://autolinkglobal.com"
GRAPH_VERSION = os.environ.get("META_GRAPH_VERSION", "v25.0")
PROVIDERS = ("linkedin", "facebook", "instagram")


class ProviderError(Exception):
    pass


def credentials(provider: str):
    if provider not in PROVIDERS:
        raise ProviderError("Unknown sign-in provider.")
    prefix = provider.upper()
    return os.environ.get(f"{prefix}_CLIENT_ID", ""), os.environ.get(f"{prefix}_CLIENT_SECRET", "")


def enabled(provider: str) -> bool:
    return all(credentials(provider))


def callback_url(provider: str) -> str:
    return f"{ORIGIN}/autolink/auth/{provider}/callback"


def authorization_url(provider: str, state: str, nonce: str) -> str:
    client_id, secret = credentials(provider)
    if not client_id or not secret:
        raise ProviderError("This sign-in provider is not configured.")
    params = {"client_id": client_id, "redirect_uri": callback_url(provider),
              "response_type": "code", "state": state}
    if provider == "linkedin":
        params.update(scope="openid profile email", nonce=nonce)
        base = "https://www.linkedin.com/oauth/v2/authorization"
    elif provider == "facebook":
        params.update(scope="public_profile,email")
        base = f"https://www.facebook.com/{GRAPH_VERSION}/dialog/oauth"
    else:
        params.update(scope="instagram_business_basic", enable_fb_login="0")
        base = "https://www.instagram.com/oauth/authorize"
    return base + "?" + urlencode(params)


def _response_json(response):
    try:
        response.raise_for_status()
        data = response.json()
    except (ValueError, requests.RequestException) as exc:
        raise ProviderError("The identity provider could not verify this login.") from exc
    if not isinstance(data, dict) or data.get("error"):
        raise ProviderError("The identity provider rejected this login.")
    return data


def exchange(provider: str, code: str, nonce: str) -> dict:
    """Return a verified stable subject and optional basic profile; never retain tokens."""
    client_id, client_secret = credentials(provider)
    if not client_id or not client_secret:
        raise ProviderError("This sign-in provider is not configured.")
    if provider == "linkedin":
        data = _response_json(requests.post(
            "https://www.linkedin.com/oauth/v2/accessToken",
            data={"grant_type": "authorization_code", "code": code,
                  "redirect_uri": callback_url(provider), "client_id": client_id,
                  "client_secret": client_secret}, timeout=10))
        token = data.get("id_token")
        if not isinstance(token, str):
            raise ProviderError("LinkedIn did not return an identity token.")
        try:
            key = jwt.PyJWKClient("https://www.linkedin.com/oauth/openid/jwks").get_signing_key_from_jwt(token)
            claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=client_id,
                                issuer="https://www.linkedin.com", options={"require": ["exp", "iat", "sub"]})
        except (jwt.PyJWTError, requests.RequestException) as exc:
            raise ProviderError("LinkedIn identity token could not be verified.") from exc
        if claims.get("nonce") is not None and claims["nonce"] != nonce:
            raise ProviderError("LinkedIn login challenge did not match.")
        return {"subject": str(claims["sub"]), "email": str(claims.get("email") or "")[:320],
                "name": str(claims.get("name") or "")[:160]}
    if provider == "facebook":
        data = _response_json(requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/oauth/access_token",
            params={"client_id": client_id, "client_secret": client_secret,
                    "redirect_uri": callback_url(provider), "code": code}, timeout=10))
        token = data.get("access_token")
        if not isinstance(token, str):
            raise ProviderError("Facebook did not return an access token.")
        inspection = _response_json(requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/debug_token",
            params={"input_token": token, "access_token": client_id + "|" + client_secret},
            timeout=10)).get("data", {})
        if not isinstance(inspection, dict) or not inspection.get("is_valid") or str(inspection.get("app_id")) != client_id:
            raise ProviderError("Facebook login token did not belong to AUTOLINK.")
        profile = _response_json(requests.get(
            f"https://graph.facebook.com/{GRAPH_VERSION}/me",
            params={"fields": "id,name,email", "access_token": token}, timeout=10))
        subject = profile.get("id")
        if not subject or str(inspection.get("user_id")) != str(subject):
            raise ProviderError("Facebook identity could not be verified.")
        return {"subject": str(subject), "email": str(profile.get("email") or "")[:320],
                "name": str(profile.get("name") or "")[:160]}
    data = _response_json(requests.post(
        "https://api.instagram.com/oauth/access_token",
        data={"client_id": client_id, "client_secret": client_secret,
              "grant_type": "authorization_code", "redirect_uri": callback_url(provider),
              "code": code}, timeout=10))
    subject, token = data.get("user_id"), data.get("access_token")
    if not subject or not isinstance(token, str):
        raise ProviderError("Instagram did not return a professional account identity.")
    profile = _response_json(requests.get(
        "https://graph.instagram.com/me", params={"fields": "user_id,username,account_type",
                                                     "access_token": token}, timeout=10))
    if str(profile.get("user_id") or profile.get("id")) != str(subject):
        raise ProviderError("Instagram identity could not be verified.")
    if profile.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR", "CREATOR"):
        raise ProviderError("An Instagram Business or Creator account is required.")
    return {"subject": str(subject), "email": "", "name": str(profile.get("username") or "")[:160]}
