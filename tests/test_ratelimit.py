"""Rate limiting tests."""

import pytest
import time
from roadgateway_core.ratelimit.algorithms import (
    TokenBucket,
    SlidingWindow,
    LeakyBucket,
)
from roadgateway_core.ratelimit.limiter import RateLimiter


class TestTokenBucket:
    """Test token bucket algorithm."""

    def test_allows_within_capacity(self):
        """Test allowing requests within capacity."""
        bucket = TokenBucket(capacity=5, refill_rate=1.0)
        
        for _ in range(5):
            assert bucket.allow() is True

    def test_denies_over_capacity(self):
        """Test denying requests over capacity."""
        bucket = TokenBucket(capacity=2, refill_rate=0.0)
        
        assert bucket.allow() is True
        assert bucket.allow() is True
        assert bucket.allow() is False


class TestRateLimiter:
    """Test rate limiter."""

    def test_rate_limiter_per_key(self):
        """Test rate limiting per key."""
        limiter = RateLimiter(requests_per_second=2)
        
        assert limiter.allow("user1") is True
        assert limiter.allow("user2") is True
        assert limiter.allow("user1") is True
