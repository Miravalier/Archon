from __future__ import annotations
import asyncio
import random
import time
import traceback
from bson import ObjectId
from enum import StrEnum
from pydantic import BaseModel, Field
from pydantic.functional_validators import BeforeValidator
from typing import Annotated

from .errors import AuthError, ClientError
from .handlers import register
from .request_models import Connection, ChannelRequest


def generate_id() -> str:
    return ObjectId().binary.hex()


class ResourceType(StrEnum):
    Food = "food"
    Gold = "gold"
    Stone = "stone"
    Wood = "wood"
    Aether = "aether"

resource_types = [*ResourceType]


class Job(StrEnum):
    Miner = "miner"
    Farmer = "farmer"
    Lumberjack = "lumberjack"
    Enchanter = "enchanter"
    Builder = "builder"
    Militia = "militia"
    Merchant = "merchant"
    Scout = "scout"

resource_production: dict[Job, list[tuple[ResourceType, float]]] = {
    Job.Miner: [
        (ResourceType.Stone, 1.0),
        (ResourceType.Gold, 0.1),
    ],
    Job.Farmer: [
        (ResourceType.Food, 1.0),
    ],
    Job.Lumberjack: [
        (ResourceType.Wood, 1.0),
    ],
    Job.Enchanter: [
        (ResourceType.Aether, 1.0),
        (ResourceType.Gold, 0.1),
    ],
    Job.Builder: [],
    Job.Militia: [],
    Job.Merchant: [
        (ResourceType.Gold, 1.0),
    ],
    Job.Scout: [],
}
jobs = [*Job]


class GameState(StrEnum):
    Lobby = "lobby"
    Active = "active"


# In-Memory Models
class Worker(BaseModel):
    id: str
    name: str
    job: Job = Field(default_factory=lambda: random.choice(jobs))
    gathering_rate: float = 1.0

    async def on_tick(self, game: Game, delta: float):
        for resource, share in resource_production[self.job]:
            increase = (share * self.gathering_rate * delta)
            setattr(
                game,
                resource.value,
                getattr(game, resource.value) + increase
            )


class Game(BaseModel):
    id: str # Same ID as the associated channel
    player: str = Field(exclude=True)
    state: GameState = GameState.Lobby
    workers: dict[str, Worker] = Field(default_factory=dict)

    food: float = 100.0
    gold: float = 100.0
    stone: float = 0.0
    wood: float = 0.0
    aether: float = 0.0

    async def on_tick(self, delta: float):
        if self.state == GameState.Lobby:
            return
        for worker in self.workers.values():
            worker.on_tick(self, delta)


games: dict[str, Game] = {}


def game_by_id(game_id: str) -> Game:
    game = games.get(game_id)
    if game is None:
        raise ClientError("game not found")
    return game


GameById = Annotated[Game, BeforeValidator(game_by_id)]

class GameRequest(BaseModel):
    game: GameById


@register("game/create")
async def handle_game_create(connection: Connection, request: ChannelRequest):
    if request.channel.id not in connection.user.linked_channels:
        raise AuthError("channel not linked")

    if request.channel.id in games:
        raise ClientError("channel already has a game")

    game = Game(id=request.channel.id, player=connection.user.id)
    games[game.id] = game
    return {"id": game.id}


@register("game/get")
async def handle_game_get(connection: Connection, request: GameRequest):
    if request.game.player != connection.user.id:
        raise AuthError("insufficient permissions")

    return request.game.model_dump()


async def game_thread():
    MAX_TICK_RATE = 30
    SLEEP_TIME = max(1/MAX_TICK_RATE, 0.010)

    previous_tick_start = time.monotonic()
    while True:
        await asyncio.sleep(SLEEP_TIME)

        tick_start = time.monotonic()

        tasks: list[asyncio.Future] = []
        for game in games.values():
            tasks.append(game.on_tick(tick_start - previous_tick_start))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for result in results:
            if isinstance(result, BaseException):
                print("[!] Exception In Game Thread:")
                traceback.print_exception(result)

        previous_tick_start = tick_start
