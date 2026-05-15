"""In-memory thread state."""

import asyncio

# Lock by thread_id to serialize concurrent requests in the same conversation
# (IAedu returns 500 for parallel calls on the same thread).
THREAD_LOCKS: dict[str, asyncio.Lock] = {}
THREAD_LOCKS_LOCK = asyncio.Lock()

# Threads where the system prompt has already been sent. Do not repeat it,
# because IAedu keeps server-side history.
THREADS_WITH_SYSTEM_SENT: set[str] = set()

# Threads cancelled mid-flight. The next request on these threads may receive
# the previous request's "stuck" response, so mark them for rotation.
CANCELLED_THREADS: set[str] = set()


async def get_thread_lock(thread_id: str) -> asyncio.Lock:
    async with THREAD_LOCKS_LOCK:
        lock = THREAD_LOCKS.get(thread_id)
        if lock is None:
            lock = asyncio.Lock()
            THREAD_LOCKS[thread_id] = lock
        return lock
