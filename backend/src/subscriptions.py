from fastapi import APIRouter, WebSocket
from starlette.websockets import WebSocketDisconnect
from pydantic import ValidationError

from .models import Connection
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
            return handler.callback(connection, handler.model.model_validate(request))
        except ValidationError as e:
            return {"type": "error", "reason": "validation", "data": e.json()}


@router.websocket("/subscribe")
async def ws_subscription(websocket: WebSocket):
    await websocket.accept()

    while True:
        request: dict = await websocket.receive_json()
        if request.get("token"):
            break

    token: str = request["token"]
    connection = Connection(token, websocket)

    print(f"[!] Connection from {token}")

    try:
        connected_clients.add(connection)
        await connection.ws.send_json({"type": "connect"})
        while True:
            request = await websocket.receive_json()
            response = await handle_ws_request(connection, request)
            if "id" in request:
                response["id"] = request["id"]
            await websocket.send_json(response)
    except WebSocketDisconnect:
        pass
    finally:
        connected_clients.discard(connection)
