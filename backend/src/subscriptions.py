import traceback
from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from pydantic import BaseModel, ValidationError
from typing import Union

from . import database
from .database_models import User
from .request_models import Connection, channel_by_id
from .handlers import handlers


router = APIRouter()
connected_clients: set[Connection] = set()


async def handle_ws_request(connection: Connection, request: dict) -> dict:
    request_type = request.get("type")

    if request_type == "ping":
        return {"type": "pong"}

    if request_type in handlers:
        handler = handlers[request_type]
        try:
            params = {}
            if handler.model is not None:
                params["request"] = handler.model.model_validate(request)
            if handler.connection_requested:
                params["connection"] = connection
            if handler.is_async:
                return await handler.callback(**params)
            else:
                return handler.callback(**params)
        except ValidationError as e:
            return {"type": "error", "reason": "validation", "details": e.json()}
        except Exception as e:
            traceback.print_exception(e)
            return {"type": "error", "reason": str(e)}


@router.websocket("/subscribe")
async def ws_subscription(websocket: WebSocket):
    await websocket.accept()

    while True:
        request: dict = await websocket.receive_json()
        if request.get("token"):
            break

    token: str = request["token"]
    user = database.users.find_one({"token": token})
    if user is None:
        user = database.users.create(User(token=token))
    connection = Connection(user=user, ws=websocket)

    print(f"[!] Connection from '{user.name if user.name else user.id}'")

    try:
        connected_clients.add(connection)
        await connection.ws.send_json({"type": "connect"})
        while True:
            request = await websocket.receive_json()
            response = await handle_ws_request(connection, request)
            if response is None:
                response = {}
            if "request_id" in request:
                response["request_id"] = request["request_id"]
            await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(connection)


async def broadcast(message: Union[BaseModel, dict]):
    if isinstance(message, BaseModel):
        message = message.model_dump()
