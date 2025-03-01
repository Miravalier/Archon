from __future__ import annotations
import asyncio
import random
import time
import traceback
from bson import ObjectId
from enum import IntEnum, StrEnum
from math import sqrt
from pydantic import BaseModel, Field
from pydantic.functional_validators import BeforeValidator
from typing import Annotated, Any, Iterable, Optional

from .errors import AuthError, ClientError
from .handlers import register
from .request_models import Connection, ChannelRequest


def generate_id() -> str:
    return ObjectId().binary.hex()


class ResourceType(StrEnum):
    Invalid = ""
    Food = "food"
    Gold = "gold"
    Stone = "stone"
    Wood = "wood"
    Aether = "aether"

resource_types = [*ResourceType]
resource_types.pop(0)


class Job(StrEnum):
    Invalid = ""
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
jobs.pop(0)


class GameState(StrEnum):
    Lobby = "lobby"
    Active = "active"


class Position(BaseModel):
    q: int
    r: int

    def __init__(self, q: int, r: int):
        super().__init__(q=q, r=r)

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

    def flood_fill(self, limit: int = None):
        already_visited: set[Position] = {self}
        current_positions: list[Position] = [self]
        distance = 0
        while True:
            next_positions: list[Position] = []
            for position in current_positions:
                yield position
                for neighbor in position.neighbors:
                    if neighbor in already_visited:
                        continue
                    already_visited.add(neighbor)
                    next_positions.append(neighbor)
            current_positions = next_positions
            if limit is not None and distance >= limit:
                return
            distance += 1

    def __hash__(self):
        return hash((self.q, self.r))

    def __eq__(self, value: Position):
        return self.q == value.q and self.r == value.r

    def __add__(self, other: Position) -> Position:
        return Position(q=self.q + other.q, r=self.r + other.r)

    def __sub__(self, other: Position) -> Position:
        return Position(q=self.q - other.q, r=self.r - other.r)

    def distance(self, other: Position) -> int:
        vector = self - other
        return (abs(vector.q) + abs(vector.q + vector.r) + abs(vector.r)) // 2

    @property
    def magnitude(self) -> int:
        return max(abs(self.q), abs(self.r), abs(self.s))

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


class TaskType(IntEnum):
    Move = 0
    Gather = 1
    Build = 2


class Task(BaseModel):
    task_type: TaskType
    target: Position



class EntityType(StrEnum):
    Worker = "worker"
    Resource = "resource"
    Structure = "structure"


class StructureType(StrEnum):
    Invalid = ""
    TownHall = "town_hall"
    ArrowTower = "arrow_tower"


class Entity(BaseModel):
    entity_type: EntityType
    id: str = Field(default_factory=generate_id)
    name: str = "<Unknown>"
    position: Position
    hp: int = 1
    max_hp: int = 1
    image: Optional[str] = None
    # Structure Attributes
    structure_type: StructureType = StructureType.Invalid
    # Worker Attributes
    carried_resource: ResourceType = ResourceType.Invalid
    carry_amount: int = 0
    carry_capacity: int = 25
    tasks: list[Task] = Field(default_factory=list)
    job: Job = Job.Invalid
    gathering_rate: float = 1.0
    time_until_action: float = 1.0
    # Resource Attributes
    resource_type: ResourceType = ResourceType.Invalid

    async def on_tick(self, game: Game, delta: float):
        if self.entity_type == EntityType.Worker:
            await self.worker_tick(game, delta)

    async def worker_tick(self, game: Game, delta: float):
        if self.time_until_action > 0:
            self.time_until_action -= delta
            return
        self.time_until_action = (950 + random.randint(0, 100))/1000
        if self.job != Job.Invalid:
            await self.job_worker_tick(game)
        else:
            await self.manual_worker_tick(game)

    async def job_worker_tick(self, game: Game):
        if self.position.magnitude <= 2 and self.carried_resource != ResourceType.Invalid:
            task = game.add_resource(self.carried_resource, self.carry_amount)
            self.carry_amount = 0
            self.carried_resource = ResourceType.Invalid
            await task

        if self.carry_amount == self.carry_capacity:
            await self.path_to(Position(0,0).neighbors, game)

        elif self.job == Job.Builder:
            # Find nearest damaged structure
            target = None
            lowest_distance = None
            for structure in game.structures.values():
                if structure.hp == structure.max_hp:
                    continue
                distance = self.position.distance(structure.position)
                if lowest_distance is None or distance < lowest_distance:
                    lowest_distance = distance
                    target = structure
            # Repair if adjacent, or path to if not adjacent
            if target is not None:
                if lowest_distance == 1:
                    structure.hp = min(structure.hp + 5, structure.max_hp)
                else:
                    await self.path_to(structure.position, game)

        elif self.job == Job.Lumberjack:
            await self.gather(ResourceType.Wood, game)

        elif self.job == Job.Miner:
            await self.gather(ResourceType.Stone, game)

        elif self.job == Job.Farmer:
            await self.gather(ResourceType.Food, game)

    async def gather(self, resource_type: ResourceType, game: Game):
        target_position = None
        for position in self.position.flood_fill():
            entity = game.map.get(position)
            if entity is None:
                continue
            if entity.entity_type != "resource":
                continue
            if entity.resource_type != resource_type:
                continue
            target_position = position
            break
        if self.position.distance(target_position) == 1:
            if self.carried_resource != resource_type:
                self.carry_amount = 0
                self.carried_resource = resource_type
            self.carry_amount += 5
        else:
            await self.path_to(target_position, game)

    async def path_to(self, target_position: Position | Iterable[Position], game: Game):
        if isinstance(target_position, Position):
            target_position = (target_position,)
        path = game.path_between(self.position, target_position)
        if not path:
            return
        await game.move_entity(self, path[0])

    async def manual_worker_tick(self, game: Game):
        pass


class Game(BaseModel):
    id: str # Same ID as the associated channel
    player: str
    state: GameState = GameState.Lobby
    entities: dict[str, Entity] = Field(default_factory=dict)
    structures: dict[str, Entity] = Field(default_factory=dict)
    workers: dict[str, Entity] = Field(default_factory=dict)

    map: dict[Position, Entity] = Field(default_factory=dict, exclude=True)
    subscribers: set[Connection] = Field(default_factory=set, exclude=True)

    food: float = 100.0
    gold: float = 100.0
    stone: float = 0.0
    wood: float = 0.0
    aether: float = 0.0

    async def broadcast(self, message: Any):
        broken_connections: set[Connection] = set()
        for connection in self.subscribers:
            try:
                await connection.ws.send_json(message)
            except Exception:
                broken_connections.add(connection)
        self.subscribers -= broken_connections

    async def on_tick(self, delta: float):
        for worker in self.workers.values():
            await worker.on_tick(self, delta)
        for structure in self.structures.values():
            await structure.on_tick(self, delta)

    async def add_resource(self, resource_type: ResourceType, amount: int):
        if resource_type == ResourceType.Food:
            self.food += amount
        elif resource_type == ResourceType.Gold:
            self.gold += amount
        elif resource_type == ResourceType.Stone:
            self.stone += amount
        elif resource_type == ResourceType.Wood:
            self.wood += amount
        elif resource_type == ResourceType.Aether:
            self.aether += amount
        await self.broadcast({"type": "resource", "resource_type": resource_type, "amount": amount})

    async def place_town_hall(self):
        town_hall = await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.TownHall,
            position=Position(0,0)
        ))
        for position in Position(0,0).neighbors:
            self.map[position] = town_hall

        # DBG
        await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.ArrowTower,
            position=Position(0,-3)
        ))

    async def generate_resources(self):
        for q in range(-500, 501):
            for r in range(-500, 501):
                position = Position(q, r)
                if position.s < -500 or position.s > 500:
                    continue
                if position in self.map:
                    continue
                if random.randint(0, 60 + position.magnitude**2 // 100) == 0:
                    await self.add_entity(Entity(
                        entity_type=EntityType.Resource,
                        position=position,
                        resource_type=random.choice([
                            ResourceType.Stone,
                            ResourceType.Food,
                            ResourceType.Wood,
                        ])
                    ))

    async def add_entity(self, entity: Entity) -> Entity:
        self.entities[entity.id] = entity
        self.map[entity.position] = entity
        if entity.entity_type == EntityType.Structure:
            self.structures[entity.id] = entity
        elif entity.entity_type == EntityType.Worker:
            self.workers[entity.id] = entity
        await self.broadcast({"type": "entity/add", "entity": entity.model_dump(mode="json")})
        return entity

    async def move_entity(self, entity: Entity, position: Position):
        if position in self.map:
            raise ValueError("position is occupied")
        self.map.pop(entity.position, None)
        entity.position = position
        self.map[entity.position] = entity
        await self.broadcast({"type": "entity/move", "id": entity.id, "position": position.model_dump()})

    async def remove_entity(self, entity: Entity):
        self.entities.pop(entity.id, None)
        self.map.pop(entity.position, None)
        if entity.entity_type == EntityType.Structure:
            self.structures.pop(entity.id, None)
        elif entity.entity_type == EntityType.Worker:
            self.workers.pop(entity.id, None)
        await self.broadcast({"type": "entity/remove", "id": entity.id})

    def empty_space_near(self, starting_position: Position) -> Position:
        for position in starting_position.flood_fill():
            if position not in self.map:
                return position

    def path_between(self, start_position: Position, target_positions: Iterable[Position], limit: int = None) -> list[Position]:
        already_visited: set[Position] = {start_position}
        current_positions: list[Position] = [start_position]
        previous_positions: dict[Position, Position] = {}
        distance = 0
        while current_positions:
            next_positions: list[Position] = []
            for position in current_positions:
                for neighbor in position.neighbors:
                    if neighbor not in previous_positions:
                        previous_positions[neighbor] = position
                    if neighbor in target_positions:
                        path = []
                        cursor = neighbor
                        while cursor != start_position:
                            path.append(cursor)
                            cursor = previous_positions[cursor]
                        path.reverse()
                        return path
                    if neighbor in already_visited:
                        continue
                    if neighbor in self.map:
                        continue
                    already_visited.add(neighbor)
                    next_positions.append(neighbor)

            current_positions = next_positions
            if limit is not None and distance >= limit:
                return None
            distance += 1
        return None


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
    await game.place_town_hall()
    await game.generate_resources()
    games[game.id] = game
    return game.model_dump()


@register("game/get")
async def handle_game_get(connection: Connection, request: GameRequest):
    if request.game.player != connection.user.id:
        raise AuthError("insufficient permissions")

    return request.game.model_dump()


@register("game/subscribe")
async def handle_game_subscribe(connection: Connection, request: GameRequest):
    if request.game.player != connection.user.id:
        raise AuthError("insufficient permissions")

    request.game.subscribers.add(connection)

    return {"type": "success"}


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
