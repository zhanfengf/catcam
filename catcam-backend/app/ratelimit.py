import time
from collections import defaultdict, deque

from .config import get_settings


_hits: dict[str, deque[float]] = defaultdict(deque)


def check_ip(ip: str) -> bool:
    """Return True if this IP is allowed to make another request right now."""
    s = get_settings()
    now = time.monotonic()
    window = s.ip_window_seconds
    q = _hits[ip]

    while q and now - q[0] > window:
        q.popleft()

    if len(q) >= s.ip_max_hits:
        return False

    q.append(now)
    return True
