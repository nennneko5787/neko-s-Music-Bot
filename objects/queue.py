import random
import logging
from typing import Any, Optional


class QueueEdge(Exception):
    pass


class QueueEmpty(Exception):
    pass


_log = logging.getLogger("music")


class Queue:
    __slots__ = (
        "__list",
        "__index",
        "__original_list",
        "shuffled",
    )

    def __init__(self):
        self.__list = []
        self.__index = 0
        self.__original_list: Optional[list] = None
        self.shuffled: bool = False

    @property
    def index(self):
        return self.__index

    def __repr__(self):
        return f"<{self.__list}>"

    def edge(self):
        return self.__index == 0

    def empty(self):
        return self.qsize() == 0

    def asize(self):
        return len(self.__list)

    def qsize(self):
        return len(self.__list) - self.__index

    def clear(self):
        self.__index = 0
        self.__list.clear()
        self.__original_list = None
        self.shuffled = False

    def shuffle(self):
        if not self.shuffled:
            self.__original_list = self.__list[:]
        list1 = self.__list[: self.__index]
        list2 = self.__list[self.__index :]
        random.shuffle(list2)
        self.__list = list1 + list2
        self.shuffled = True

    def unshuffle(self):
        if not self.shuffled or self.__original_list is None:
            _log.warning("Cannot unshuffle: No original list available.")
            return
        self.__list = self.__original_list + self.__list[len(self.__original_list) :]
        self.__original_list = None
        self.__index = 0
        self.shuffled = False

    def put(self, value: Any):
        self.__list.append(value)
        if self.shuffled and self.__original_list is not None:
            self.__original_list.append(value)

    def prev(self):
        if self.edge():
            raise QueueEdge()
        self.__index -= 1

    def get(self):
        if self.empty():
            return None
        value = self.__list[self.__index]
        self.__index += 1
        return value

    def pagenation(self, page: int, *, pageSize: int = 10):
        startIndex = (page - 1) * pageSize
        endIndex = startIndex + pageSize
        if startIndex >= len(self.__list) or page < 1:
            return ()
        return tuple(self.__list[startIndex:endIndex])
