import asyncio
import traceback

import discord


class MessageEditQueue:
    """
    同一 target 宛の連続 edit を coalesce して 1 秒/バッチで送る(SPEC #12)。
    start/stop は冪等(SPEC #21)。
    """

    __slots__ = ("_queue", "_task")

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def put(self, item: tuple) -> None:
        """(target, kwargs) タプルを積む。"""
        await self._queue.put(item)

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._pump())

    def stop(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()

    @staticmethod
    def _targetKey(instance) -> tuple:
        if isinstance(instance, discord.Interaction):
            return ("i", instance.id)
        if isinstance(instance, discord.Message):
            return ("m", instance.id)
        return ("x", id(instance))

    async def _pump(self) -> None:
        while True:
            try:
                instance, kwargs = await self._queue.get()
            except asyncio.CancelledError:
                break

            pending: dict[tuple, tuple] = {self._targetKey(instance): (instance, kwargs)}
            # 追加分を drain し、同じキーは最後のものだけ残す
            while True:
                try:
                    nextInstance, nextKwargs = self._queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                pending[self._targetKey(nextInstance)] = (nextInstance, nextKwargs)

            for inst, kw in pending.values():
                try:
                    if isinstance(inst, discord.Interaction):
                        await inst.edit_original_response(**kw)
                    elif isinstance(inst, discord.Message):
                        await inst.edit(**kw)
                except asyncio.CancelledError:
                    return
                except Exception:
                    traceback.print_exc()

            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
