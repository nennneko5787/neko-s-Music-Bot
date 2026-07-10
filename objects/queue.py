import asyncio


class MusicQueue(asyncio.LifoQueue):
    """
    「前の曲」履歴用の LIFO キュー。
    asyncio.LifoQueue の `_get` は `self._queue.pop()` と等価で、
    以前の `class MusicQueue(asyncio.Queue)` + `def _get: return self._queue.pop()`
    と挙動が完全に一致する(SPEC Phase 4 §5、検証済み)。
    """
