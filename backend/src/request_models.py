from fastapi import WebSocket
from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_validators import BeforeValidator
from typing import Annotated

from . import database
from .database_models import User
from .errors import ClientError


class Connection(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    user: User
    ws: WebSocket = Field(exclude=True)

    def __hash__(self):
        return hash(id(self))


def user_by_id(user_id: str) -> User:
    user = database.users.find_one(user_id)
    if user is None:
        raise ClientError("invalid user id")
    return user


UserById = Annotated[User, BeforeValidator(user_by_id)]


class UserRequest(BaseModel):
    user: UserById
