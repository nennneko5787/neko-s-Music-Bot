import asyncio


class MusicQueue(asyncio.LifoQueue):
    """「前の曲」履歴用の LIFO キュー。"""
