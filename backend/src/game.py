from __future__ import annotations
import asyncio
import random
import time
import traceback
from bson import ObjectId
from enum import StrEnum
from math import sqrt
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


class Position(BaseModel):
    q: int
    r: int

    @property
    def s(self):
        return -self.q - self.r

    @property
    def neighbors(self) -> list[Position]:
        return [
            Position(q=self.q, r=self.r-1),
            Position(q=self.q+1, r=self.r-1),
            Position(q=self.q+1, r=self.r),
            Position(q=self.q, r=self.r+1),
            Position(q=self.q-1, r=self.r+1),
            Position(q=self.q-1, r=self.r),
        ]

    def __hash__(self):
        return hash((self.q, self.r))

    def __add__(self, other: Position) -> Position:
        return Position(q=self.q + other.q, r=self.r + other.r)

    def __sub__(self, other: Position) -> Position:
        return Position(q=self.q - other.q, r=self.r - other.r)

    def distance(self, other: Position) -> int:
        vector = self - other
        return (abs(vector.q) + abs(vector.q + vector.r) + abs(vector.r)) // 2

    @classmethod
    def from_floats(cls, q: float, r: float) -> Position:
        q_grid = round(q)
        r_grid = round(r)
        q -= q_grid
        r -= r_grid
        if abs(q) >= abs(r):
            return cls(q=q_grid + round(q + 0.5*r), r=r_grid)
        else:
            return cls(q=q_grid, r=r_grid + round(r + 0.5*q))

    def lerp(self, other: Position, t: float) -> Position:
        return self.from_floats(
            self.q + (other.q - self.q) * t,
            self.r + (other.r - self.r) * t
        )

    def line_to(self, other: Position) -> list[Position]:
        distance = self.distance(other)
        results: list[Position] = []
        interval = 1/distance
        for i in range(distance+1):
            results.append(self.from_floats(self.lerp(other, interval * i)))
        return results

    def hexes_within(self, distance: int) -> list[Position]:
        results: list[Position] = []
        for i in range(-distance, distance+1):
            for j in range(max(-distance, -i-distance), min(distance, -i+distance)):
                results.append(Position(q=self.q+i, r=self.r+j))

    @classmethod
    def from_pixels(cls, x: float, y: float, grid_size: float) -> Position:
        # For pointy-top hexes
        return cls.from_floats(
            (sqrt(3)/3 * x - 1/3 * y) / grid_size,
            (2/3 * y) / grid_size
        )


class Entity(BaseModel):
    entity_type: str
    id: str
    name: str
    position: Position

    async def on_tick(self, game: Game, delta: float):
        pass


class Worker(Entity):
    entity_type: str = 'worker'
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
    player: str
    state: GameState = GameState.Lobby
    entities: dict[str, Entity] = Field(default_factory=dict)

    food: float = 100.0
    gold: float = 100.0
    stone: float = 0.0
    wood: float = 0.0
    aether: float = 0.0

    async def on_tick(self, delta: float):
        if self.state == GameState.Lobby:
            return
        for entity in self.entities.values():
            entity.on_tick(self, delta)


games: dict[str, Game] = {}


def game_by_id(game_id: str) -> Game:
    game = games.get(game_id)
    if game is None:
        raise ClientError("game not found")
    return game


GameById = Annotated[Game, BeforeValidator(game_by_id)]

class GameRequest(BaseModel):
    game: GameById


@register("user/get")
async def handle_user_get(connection: Connection):
    return connection.user.model_dump()


@register("channel/get")
async def handle_channel_get(connection: Connection, request: ChannelRequest):
    if request.channel.id not in connection.user.linked_channels:
        raise AuthError("channel not linked")

    return request.channel.model_dump()


@register("game/create")
async def handle_game_create(connection: Connection, request: ChannelRequest):
    if request.channel.id not in connection.user.linked_channels:
        raise AuthError("channel not linked")

    if request.channel.id in games:
        raise ClientError("channel already has a game")

    game = Game(id=request.channel.id, player=connection.user.id)
    games[game.id] = game
    return game.model_dump()


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
