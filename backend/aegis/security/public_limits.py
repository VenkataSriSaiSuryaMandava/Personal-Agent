"""Bounded public runtime admission controls."""

import time

from collections import deque
from threading import BoundedSemaphore, Lock

from aegis.security.sessions import (
    hash_token,
    valid_token_format,
)


class PublicRequestLimits:

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.slots = BoundedSemaphore(4)
        self._lock = Lock()
        self._creations = deque()
        self._requests = {}

    def _prune(self, queue, now):
        while queue and now - queue[0] >= 60:
            queue.popleft()

    def allow_creation(self):
        with self._lock:
            now = self.clock()
            self._prune(self._creations, now)

            if len(self._creations) >= 4:
                return False

            self._creations.append(now)
            return True

    def allow_request(self, token):
        if not valid_token_format(token):
            return False

        key = hash_token(token)

        with self._lock:
            now = self.clock()

            for identifier, queue in list(
                self._requests.items()
            ):
                self._prune(queue, now)

                if not queue:
                    del self._requests[identifier]

            if key not in self._requests:
                # Bound tracking memory independently
                # of session creation and revocation.
                if len(self._requests) >= 64:
                    return False

                self._requests[key] = deque()

            queue = self._requests[key]

            if len(queue) >= 120:
                return False

            queue.append(now)
            return True


public_limits = PublicRequestLimits()
