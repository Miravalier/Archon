import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from . import handlers
from .models import Connection
from .subscriptions import router as subscriptions_router


app = FastAPI()
app.include_router(subscriptions_router)


class HelloRequest(BaseModel):
    name: str

@handlers.register("hello", HelloRequest)
def hello_handler(connection: Connection, request: HelloRequest):
    return {"response": f"hi, {request.name}"}


if __name__ == '__main__':
    uvicorn.run(app, port=80, host="0.0.0.0")
