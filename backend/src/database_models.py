import secrets
from enum import IntEnum
from pydantic import BaseModel, Field
from typing import Optional


class Permission(IntEnum):
    Basic = 0
    Subscriber = 1
    VIP = 2
    Moderator = 3
    Broadcaster = 4


class DatabaseEntry(BaseModel):
    id: str = None

    def __hash__(self):
        return hash(self.id)


def generate_link_code() -> str:
    return secrets.token_hex(8)


class User(DatabaseEntry):
    token: str
    name: Optional[str] = None
    linked_channels: dict[str, Permission] = Field(default_factory=dict)
    link_code: str = Field(default_factory=generate_link_code)

    def regenerate_link_code(self):
        self.link_code = generate_link_code()


class Channel(DatabaseEntry):
    twitch_id: str
    name: str
    linked_users: dict[str, Permission] = Field(default_factory=dict)
