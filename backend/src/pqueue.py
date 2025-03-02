import heapq
import itertools
from typing import Generic, TypeVar


T = TypeVar("T")
P = TypeVar("P")


class PriorityQueue(Generic[T, P]):
    def __init__(self):
        self.heap: list[list] = []
        self.entries: dict[T, list] = {}
        self.counter = itertools.count()

    def __bool__(self):
        return bool(self.heap)

    def add(self, item: T, priority: P):
        """
        Add an item to the queue with the given priority, or
        re-prioritize if the item is already in the queue.
        """
        entry = self.entries.get(item, None)
        if entry:
            if entry[0] == priority:
                return
            else:
                self.remove(item)
        entry = [priority, next(self.counter), item]
        self.entries[item] = entry
        heapq.heappush(self.heap, entry)

    def remove(self, item: T):
        """
        Remove an item from the queue.
        """
        self.entries[item][-1] = None

    def peek(self) -> T:
        """
        Return the next item in the queue with the lowest
        remaining priority.
        """
        while self.heap:
            item = self.heap[0][-1]
            if item is None:
                heapq.heappop(self.heap)
            else:
                return item
        raise IndexError("peek on empty priority queue")

    def pop(self) -> T:
        """
        Remove the next item from the queue with the lowest
        remaining priority and return it.
        """
        while self.heap:
            item = heapq.heappop(self.heap)[-1]
            if item is not None:
                del self.entries[item]
                return item
        raise IndexError("pop from empty priority queue")
