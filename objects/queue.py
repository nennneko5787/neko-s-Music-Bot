import random

import logging
from typing import Any


class QueueEdge(Exception):
    pass


class QueueEmpty(Exception):
    pass


_log = logging.getLogger("music")


class Queue:
    __slots__ = (
        "__list",
        "__index",
    )

    def __init__(self):
        self.__list = list()
        self.__index = 0

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

    def shuffle(self):
        list1 = self.__list[0 : self.__index - 1]
        list2 = self.__list[self.__list : self.asize() - 1]
        random.shuffle(list2)
        self.__list = list1 + list2

    def put(self, value: Any):
        self.__list.append(value)

    def prev(self):
        if self.edge():
            raise QueueEdge()
        self.__index -= 2

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
