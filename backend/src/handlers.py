import inspect
from dataclasses import dataclass
from pydantic import BaseModel
from typing import Callable, Optional, Type, TypeVar


T = TypeVar("T", bound=BaseModel)


@dataclass
class Handler:
    model: Optional[Type[T]]
    callback: Callable
    connection_requested: bool = False


handlers: dict[str, Handler] = {}


def register(type: str):
    def register_wrapper(func: Callable):
        signature = inspect.signature(func)
        request_parameter = signature.parameters.get("request")
        if request_parameter:
            if not issubclass(request_parameter.annotation, BaseModel):
                raise TypeError("registered handler 'request' parameter must inherit from BaseModel")
            request_annotation = request_parameter.annotation
        else:
            request_annotation = None
        connection_parameter = signature.parameters.get("connection")
        handlers[type] = Handler(request_annotation, func, connection_parameter is not None)
        return func
    return register_wrapper
