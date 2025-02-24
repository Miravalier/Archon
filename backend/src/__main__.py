import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .errors import AuthError, ClientError
from .subscriptions import router as subscriptions_router
from .twitch import router as twitch_router


app = FastAPI()


@app.exception_handler(AuthError)
async def handle_auth_error(_: Request, exc: AuthError):
    return JSONResponse(status_code=401, content={
        "type": "error",
        "reason": str(exc),
    })


@app.exception_handler(ClientError)
async def handle_client_error(_: Request, exc: ClientError):
    return JSONResponse(status_code=400, content={
        "type": "error",
        "reason": str(exc),
    })


app.include_router(subscriptions_router)
app.include_router(twitch_router)


if __name__ == '__main__':
    uvicorn.run(app, port=80, host="0.0.0.0")
