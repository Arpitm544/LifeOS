from app.rate_limit import SlidingWindowLimiter


def test_sliding_window_enforces_limit():
    limiter = SlidingWindowLimiter()
    assert limiter.allow(identity="u", bucket="chat", limit=2)[0]
    assert limiter.allow(identity="u", bucket="chat", limit=2)[0]
    allowed, retry_after = limiter.allow(identity="u", bucket="chat", limit=2)
    assert allowed is False
    assert retry_after >= 1

