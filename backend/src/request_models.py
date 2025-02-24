from dataclasses import dataclass
from fastapi import WebSocket
from pydantic import BaseModel
from pydantic.functional_validators import BeforeValidator
from typing import Annotated

from . import database
from .database_models import Channel, User
from .errors import ClientError


@dataclass
class Connection:
    user: User
    ws: WebSocket

    def __hash__(self):
        return hash(id(self))


def user_by_id(user_id: str) -> User:
    channel = database.users.find_one(user_id)
    if channel is None:
        raise ClientError("invalid user id")
    return channel


def channel_by_id(channel_id: str) -> Channel:
    channel = database.channels.find_one(channel_id)
    if channel is None:
        raise ClientError("invalid channel id")
    return channel


def channel_by_twitch_id(twitch_id: str) -> Channel:
    channel = database.channels.find_one({"twitch_id": twitch_id})
    if channel is None:
        raise ClientError("invalid twitch id")
    return channel


UserById = Annotated[User, BeforeValidator(user_by_id)]
ChannelById = Annotated[Channel, BeforeValidator(channel_by_id)]
ChannelByTwitchId = Annotated[Channel, BeforeValidator(channel_by_twitch_id)]


class UserRequest(BaseModel):
    user: UserById


class ChannelRequest(BaseModel):
    channel: ChannelById
