from app.rate_limit import SlidingWindowLimiter


def test_sliding_window_enforces_limit():
    limiter = SlidingWindowLimiter()
    assert limiter.allow(identity="u", bucket="chat", limit=2)[0]
    assert limiter.allow(identity="u", bucket="chat", limit=2)[0]
    allowed, retry_after = limiter.allow(identity="u", bucket="chat", limit=2)
    assert allowed is False
    assert retry_after >= 1



def test_voice_quotas_are_per_user_per_service_and_expire(monkeypatch):
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app import auth, config
    from app.rate_limit import RateLimitMiddleware

    async def identity(authorization, demo):
        return authorization

    monkeypatch.setattr(auth, 'current_user_id', identity)
    monkeypatch.setattr(config, 'get_settings', lambda: SimpleNamespace(api_rate_limit=300, chat_rate_limit=30, voice_rate_limit=5))
    monkeypatch.setattr('app.rate_limit.time.monotonic', lambda: 0)
    application = FastAPI()
    limiter = SlidingWindowLimiter()
    application.add_middleware(RateLimitMiddleware, limiter=limiter)

    @application.post('/api/voice/{kind}/quota', status_code=204)
    async def reserve(kind: str):
        return None

    with TestClient(application) as client:
        for kind in ('transcribe', 'speak'):
            path = f'/api/voice/{kind}/quota'
            for _ in range(5):
                assert client.post(path, headers={'Authorization': 'user-a'}).status_code == 204
            rejected = client.post(path, headers={'Authorization': 'user-a'})
            assert rejected.status_code == 429
            assert rejected.headers['Retry-After'] == '60'
            assert client.post(path, headers={'Authorization': 'user-b'}).status_code == 204
        monkeypatch.setattr('app.rate_limit.time.monotonic', lambda: 60)
        assert client.post('/api/voice/transcribe/quota', headers={'Authorization': 'user-a'}).status_code == 204
