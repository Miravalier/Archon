from dataclasses import dataclass
from fastapi import WebSocket


@dataclass
class Connection:
    token: str
    ws: WebSocket

    def __hash__(self):
        return hash(self.token)
