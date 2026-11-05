"""A fake HidrawDevice that records writes and serves canned replies."""
from collections import deque
from typing import Callable, Deque, List, Optional


class FakeHidraw:
    def __init__(self, responder: Optional[Callable[[bytes], List[bytes]]] = None):
        self.node = "/dev/fake"
        self.writes: List[bytes] = []
        self.queue: Deque[bytes] = deque()
        self.responder = responder

    def write(self, report_id: int, payload: bytes) -> int:
        buf = bytes([report_id]) + bytes(payload)
        self.writes.append(buf)
        if self.responder:
            for rep in self.responder(buf):
                self.queue.append(rep)
        return len(buf)

    def read(self, timeout: float, max_len: int = 256) -> Optional[bytes]:
        return self.queue.popleft() if self.queue else None

    def drain(self, quiet: float = 0.02) -> int:
        n = len(self.queue)
        self.queue.clear()
        return n

    def close(self) -> None:
        pass
