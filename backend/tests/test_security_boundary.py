import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import HTTPException
from jose import jwk, jwt

from app import jwt_verifier
from app.db import apply_user_context

OWNER = 'user_2RfWKJREkjKbHZy0Wqa5qrHeAnb'
ISSUER = 'https://audit.clerk.accounts.dev'


def settings():
    return SimpleNamespace(clerk_issuer=ISSUER, clerk_jwks_url=ISSUER + '/.well-known/jwks.json',
        clerk_audience='lifeos-api', clerk_authorized_parties='http://localhost:3000')


def claims():
    return {'sub': OWNER, 'aud': 'lifeos-api', 'azp': 'http://localhost:3000', 'iss': ISSUER,
        'exp': int((datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp())}


def signed_token(data=None, kid='current'):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption())
    public = key.public_key().public_bytes(serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo)
    published = jwk.construct(public, 'RS256').to_dict()
    published.update(kid='current', alg='RS256', use='sig')
    return jwt.encode(data or claims(), private, algorithm='RS256', headers={'kid': kid}), published


@pytest.mark.parametrize('changes', [
    {'iss': 'https://other.clerk.accounts.dev'}, {'aud': 'wrong'}, {'azp': 'https://attacker.test'},
    {'exp': 1}, {'sub': 'not-a-clerk-user'},
])
def test_reject_untrusted_clerk_claims(monkeypatch, changes):
    data = claims(); data.update(changes)
    token, key = signed_token(data)
    monkeypatch.setattr(jwt_verifier, 'load_jwks', lambda url: asyncio.sleep(0, result=[key]))
    with pytest.raises(HTTPException) as exc:
        asyncio.run(jwt_verifier.verify_token(token, settings()))
    assert exc.value.status_code == 401


@pytest.mark.parametrize('missing', ['sub', 'iss', 'exp'])
def test_required_claims(monkeypatch, missing):
    data = claims(); del data[missing]
    token, key = signed_token(data)
    monkeypatch.setattr(jwt_verifier, 'load_jwks', lambda url: asyncio.sleep(0, result=[key]))
    with pytest.raises(HTTPException):
        asyncio.run(jwt_verifier.verify_token(token, settings()))


def test_rs256_signature_and_unknown_key_rejection(monkeypatch):
    token, key = signed_token()
    async def keys(url):
        assert url == ISSUER + '/.well-known/jwks.json'
        return [key]
    monkeypatch.setattr(jwt_verifier, 'load_jwks', keys)
    assert asyncio.run(jwt_verifier.verify_token(token, settings())) == OWNER
    unknown, _ = signed_token(kid='unknown')
    with pytest.raises(HTTPException):
        asyncio.run(jwt_verifier.verify_token(unknown, settings()))


def test_transaction_context_reapplied_and_parameterized():
    session, connection = Mock(), Mock()
    session.info = {'user_id': OWNER}
    for _ in range(2):
        apply_user_context(session, None, connection)
    calls = connection.execute.call_args_list
    assert len(calls) == 6
    assert str(calls[0].args[0]) == 'SET LOCAL ROLE lifeos_api'
    assert calls[1].args[1] == {'owner': OWNER}
    assert calls[4].args[1] == {'owner': OWNER}
    assert OWNER not in str(calls[1].args[0])


def test_admin_session_not_silently_tenant_scoped():
    session, connection = Mock(), Mock()
    session.info = {}
    apply_user_context(session, None, connection)
    connection.execute.assert_not_called()
