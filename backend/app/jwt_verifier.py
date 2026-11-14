"""Pinned-issuer Clerk JWT verification with bounded JWKS caching."""
from __future__ import annotations

import time
import httpx
from fastapi import HTTPException
from jose import JWTError, jwt

_cache = {}


async def load_jwks(issuer):
    now = time.monotonic()
    cached = _cache.get(issuer)
    if cached and cached[0] > now:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=False) as client:
            response = await client.get(issuer + '/.well-known/jwks.json')
            response.raise_for_status()
            if len(response.content) > 65536:
                raise ValueError('Oversized JWKS')
            keys = response.json()['keys']
            if not isinstance(keys, list) or len(keys) > 20:
                raise ValueError('Invalid key set')
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=503, detail='Signing keys temporarily unavailable') from exc
    _cache.clear()  # One configured project per process; bound cache size.
    _cache[issuer] = (now + 300, keys)
    return keys


async def verify_token(token, settings):
    issuer = settings.clerk_issuer.rstrip('/')
    jwks_url = settings.clerk_jwks_url.rstrip('/') or (issuer + '/.well-known/jwks.json')
    if not issuer.startswith('https://') or not jwks_url.startswith('https://') or '?' in issuer or '#' in issuer:
        raise HTTPException(status_code=503, detail='Configure Clerk issuer and HTTPS JWKS URL')
    try:
        header = jwt.get_unverified_header(token)
        algorithm = header.get('alg')
        if algorithm == 'RS256':
            kid = header.get('kid')
            if not isinstance(kid, str) or not kid:
                raise JWTError('Missing signing key id')
            keys = await load_jwks(jwks_url)
            matches = [item for item in keys if item.get('kid') == kid and
                item.get('use', 'sig') == 'sig' and item.get('alg', algorithm) == algorithm and
                item.get('kty') == 'RSA']
            if len(matches) != 1:
                raise JWTError('Unknown signing key')
            key = matches[0]
        else:
            raise JWTError('Unsupported signature algorithm')
        options = {'require_exp': True, 'require_sub': True, 'require_iss': True,
                   'verify_aud': bool(settings.clerk_audience)}
        claims = jwt.decode(token, key, algorithms=[algorithm], issuer=issuer,
            audience=settings.clerk_audience or None, options=options)
        subject = claims['sub']
        if not isinstance(subject, str) or not subject.startswith('user_'):
            raise JWTError('Clerk user subject required')
        parties = {item.strip() for item in settings.clerk_authorized_parties.split(',') if item.strip()}
        if parties and claims.get('azp') not in parties:
            raise JWTError('Unauthorized party')
        return subject
    except (JWTError, ValueError, TypeError, KeyError, AttributeError) as exc:
        raise HTTPException(status_code=401, detail='Invalid bearer token') from exc
