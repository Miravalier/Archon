from dataclasses import dataclass
from pydantic import BaseModel
from typing import Any, Callable, Type, TypeVar

from .models import Connection


T = TypeVar("T", bound=BaseModel)


@dataclass
class Handler:
    model: Type[T]
    callback: Callable[[Connection, T], dict]


handlers: dict[str, Handler] = {}


def register(type: str, model: Type[T]):
    def register_wrapper(func: Callable[[Connection, T], dict]):
        handlers[type] = Handler(model, func)
        return func
    return register_wrapper
