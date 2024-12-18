from typing import Any


class QueueEdge(Exception):
    pass


class QueueEmpty(Exception):
    pass


class Queue:
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
            raise QueueEmpty()
        value = self.__list[self.__index]
        self.__index += 1
        return value
