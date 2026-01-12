"""Rate Limiting Algorithms - Various rate limiting algorithms.

Copyright (c) 2024-2026 BlackRoad OS, Inc. All rights reserved.
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


class Algorithm(ABC):
    """Abstract rate limiting algorithm."""

    @abstractmethod
    def allow(self) -> bool:
        """Check if request is allowed."""
        pass

    @abstractmethod
    def reset(self) -> None:
        """Reset the algorithm state."""
        pass


@dataclass
class TokenBucket(Algorithm):
    """Token Bucket Algorithm.

    Tokens are added at a fixed rate (refill_rate).
    Each request consumes one token.
    Requests are allowed if tokens > 0.

    Good for: Allowing bursts while maintaining average rate.
    """

    capacity: int = 10
    refill_rate: float = 1.0  # tokens per second
    tokens: float = field(default=None)
    last_refill: float = field(default=None)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if self.tokens is None:
            self.tokens = float(self.capacity)
        if self.last_refill is None:
            self.last_refill = time.time()

    def allow(self) -> bool:
        """Check if request is allowed and consume token."""
        with self._lock:
            self._refill()

            if self.tokens >= 1:
                self.tokens -= 1
                return True
            return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now

    def reset(self) -> None:
        """Reset to full capacity."""
        with self._lock:
            self.tokens = float(self.capacity)
            self.last_refill = time.time()


@dataclass
class SlidingWindow(Algorithm):
    """Sliding Window Algorithm.

    Tracks requests in a time window.
    Uses interpolation for smoother limiting.

    Good for: Smooth rate limiting without sharp edges.
    """

    window_size: float = 60.0  # seconds
    max_requests: int = 100
    _requests: Deque[float] = field(default_factory=deque, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        """Check if request is allowed."""
        with self._lock:
            now = time.time()
            window_start = now - self.window_size

            # Remove old requests
            while self._requests and self._requests[0] < window_start:
                self._requests.popleft()

            if len(self._requests) < self.max_requests:
                self._requests.append(now)
                return True

            return False

    def reset(self) -> None:
        """Reset window."""
        with self._lock:
            self._requests.clear()


@dataclass
class FixedWindow(Algorithm):
    """Fixed Window Algorithm.

    Counts requests in fixed time windows.
    Simple but can allow bursts at window edges.

    Good for: Simple implementation, clear limits.
    """

    window_size: float = 60.0  # seconds
    max_requests: int = 100
    _count: int = field(default=0, repr=False)
    _window_start: float = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if self._window_start is None:
            self._window_start = time.time()

    def allow(self) -> bool:
        """Check if request is allowed."""
        with self._lock:
            now = time.time()

            # Check if window has passed
            if now - self._window_start >= self.window_size:
                self._count = 0
                self._window_start = now

            if self._count < self.max_requests:
                self._count += 1
                return True

            return False

    def reset(self) -> None:
        """Reset window."""
        with self._lock:
            self._count = 0
            self._window_start = time.time()


@dataclass
class LeakyBucket(Algorithm):
    """Leaky Bucket Algorithm.

    Requests are added to a queue (bucket).
    Requests leak out at a fixed rate.
    Bucket overflow = rate limited.

    Good for: Smoothing traffic, queueing requests.
    """

    capacity: int = 10
    leak_rate: float = 1.0  # requests per second
    _level: float = field(default=0.0, repr=False)
    _last_leak: float = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self):
        if self._last_leak is None:
            self._last_leak = time.time()

    def allow(self) -> bool:
        """Check if request is allowed."""
        with self._lock:
            self._leak()

            if self._level < self.capacity:
                self._level += 1
                return True

            return False

    def _leak(self) -> None:
        """Leak requests from bucket."""
        now = time.time()
        elapsed = now - self._last_leak
        leaked = elapsed * self.leak_rate
        self._level = max(0, self._level - leaked)
        self._last_leak = now

    def reset(self) -> None:
        """Reset bucket."""
        with self._lock:
            self._level = 0.0
            self._last_leak = time.time()


@dataclass
class SlidingWindowLog(Algorithm):
    """Sliding Window Log Algorithm.

    Stores timestamps of all requests.
    Most accurate but uses more memory.

    Good for: Accurate limiting with small request volumes.
    """

    window_size: float = 60.0
    max_requests: int = 100
    _timestamps: List[float] = field(default_factory=list, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def allow(self) -> bool:
        """Check if request is allowed."""
        with self._lock:
            now = time.time()
            window_start = now - self.window_size

            # Filter to recent timestamps
            self._timestamps = [
                ts for ts in self._timestamps if ts > window_start
            ]

            if len(self._timestamps) < self.max_requests:
                self._timestamps.append(now)
                return True

            return False

    def reset(self) -> None:
        """Reset log."""
        with self._lock:
            self._timestamps.clear()


__all__ = [
    "Algorithm",
    "TokenBucket",
    "SlidingWindow",
    "FixedWindow",
    "LeakyBucket",
    "SlidingWindowLog",
]
