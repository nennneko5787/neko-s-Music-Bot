"""
MessageEditQueue — 同一 target 向けの連続 edit を coalesce して 1 秒/バッチで処理する
非同期タスク付きキュー。

SPEC_REFACTOR_PR3.md 第 3 段階で cogs/music.py MusicCog から切り出したもの。
挙動不変(pure code motion + カプセル化)。coalesce ロジック・1秒スリープ・
CancelledError の 3 段捕捉・target key の型はすべて元のまま。

Public API:
- put(item: tuple)   asyncio.Queue.put と互換。(target, kwargs) タプルを積む。
- start()            pump タスクを起動(冪等)。
- stop()             pump タスクを停止(冪等)。
"""
import asyncio
import traceback

import discord


class MessageEditQueue:
    """
    Discord Interaction / Message 宛の連続 edit を coalesce して逐次送るキュー。

    SPEC #12: 元コードは 1 秒/編集の逐次処理でキュー無制限、PlayerUpdate 多発時に
    パネル更新が際限なく遅延した。同じ Message/Interaction 宛の連続更新を最後の
    ものだけに coalesce する。

    SPEC #21: cog reload で二重稼働しないよう、start/stop は冪等。
    """

    __slots__ = ("_queue", "_task")

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: asyncio.Task | None = None

    async def put(self, item: tuple) -> None:
        """
        (target, kwargs) タプルをキューに積む。asyncio.Queue.put 互換。
        """
        await self._queue.put(item)

    def start(self) -> None:
        """
        pump タスクを起動する。既に走っている場合は何もしない(冪等)。
        """
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._pump())

    def stop(self) -> None:
        """
        pump タスクをキャンセルする。走っていなければ何もしない(冪等)。
        """
        if self._task is not None and not self._task.done():
            self._task.cancel()

    @staticmethod
    def _targetKey(instance) -> tuple:
        # 同一パネル(Message)や同一 Interaction の連続更新はまとめる。
        if isinstance(instance, discord.Interaction):
            return ("i", instance.id)
        if isinstance(instance, discord.Message):
            return ("m", instance.id)
        return ("x", id(instance))

    async def _pump(self) -> None:
        # SPEC #12: 元コードは 1秒/編集の逐次処理でキュー無制限、
        # PlayerUpdate 多発時にパネル更新が際限なく遅延した。
        # 同じ Message/Interaction 宛の連続更新を最後のものだけに coalesce する。
        while True:
            try:
                instance, kwargs = await self._queue.get()
            except asyncio.CancelledError:
                break

            pending: dict[tuple, tuple] = {self._targetKey(instance): (instance, kwargs)}
            # 追加分を drain して同じキーは上書き
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
