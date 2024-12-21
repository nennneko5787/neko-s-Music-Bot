from typing import Any


class QueueEdge(Exception):
    pass


class QueueEmpty(Exception):
    pass


class Queue:
    __slots__ = (
        "__list",
        "__index",
    )

    def __init__(self):
        self.__list = list()
        self.__index = 0

    def __repr__(self):
        return f"<{self.__list}>"

    def edge(self):
        return self.__index == 0

    def empty(self):
        return self.qsize() == 0

    def qsize(self):
        return len(self.__list) - self.__index

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

    def pagenation(self, page: int = None, pageSize: int = 10):
        if self.empty():
            return tuple()
        if not page:
            page = (self.__index // pageSize) + 1

        startIndex = (page - 1) * pageSize
        endIndex = startIndex + pageSize
        if startIndex >= len(self.__list) or page < 1:
            return ()
        return (
            tuple(self.__list[startIndex:endIndex]),
            page,
        )
