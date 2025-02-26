import inspect
from dataclasses import dataclass
from pydantic import BaseModel
from typing import Callable, Optional, Type, TypeVar, get_type_hints


T = TypeVar("T", bound=BaseModel)


@dataclass
class Handler:
    model: Optional[Type[T]]
    callback: Callable
    connection_requested: bool = False
    is_async: bool = True


handlers: dict[str, Handler] = {}


def register(event: str):
    def register_wrapper(func: Callable):
        parameters = get_type_hints(func)
        is_async = inspect.iscoroutinefunction(func)
        request_parameter = parameters.get("request")
        if request_parameter:
            if not issubclass(request_parameter, BaseModel):
                raise TypeError("registered handler 'request' parameter must inherit from BaseModel")
            request_annotation = request_parameter
        else:
            request_annotation = None
        connection_parameter = parameters.get("connection")
        handlers[event] = Handler(request_annotation, func, connection_parameter is not None, is_async)
        return func
    return register_wrapper
