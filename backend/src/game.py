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
    Null = ""
    Food = "food"
    Gold = "gold"
    Stone = "stone"
    Wood = "wood"
    Aether = "aether"

resource_types = [*ResourceType]
resource_types.pop(0)


class UnitType(StrEnum):
    Null = ""

    Miner = "miner"
    Farmer = "farmer"
    Lumberjack = "lumberjack"
    Enchanter = "enchanter"
    Builder = "builder"
    Militia = "militia"
    Merchant = "merchant"
    Scout = "scout"

    Voidling = "voidling"


resource_production: dict[UnitType, list[tuple[ResourceType, float]]] = {
    UnitType.Miner: [
        (ResourceType.Stone, 1.0),
        (ResourceType.Gold, 0.1),
    ],
    UnitType.Farmer: [
        (ResourceType.Food, 1.0),
    ],
    UnitType.Lumberjack: [
        (ResourceType.Wood, 1.0),
    ],
    UnitType.Enchanter: [
        (ResourceType.Aether, 1.0),
        (ResourceType.Gold, 0.1),
    ],
    UnitType.Builder: [],
    UnitType.Militia: [],
    UnitType.Merchant: [
        (ResourceType.Gold, 1.0),
    ],
    UnitType.Scout: [],
}
unit_types = [*UnitType]
unit_types.pop(0)


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
    Unit = "unit"
    Resource = "resource"
    Structure = "structure"


class StructureType(StrEnum):
    Null = ""
    TownHall = "town_hall"
    ArrowTower = "arrow_tower"


class Alignment(IntEnum):
    Neutral = 0
    Player = 1
    Enemy = 2


class Entity(BaseModel):
    entity_type: EntityType
    id: str = Field(default_factory=generate_id)
    name: str = "<Unknown>"
    position: Position
    hp: float = 1
    max_hp: float = 1
    image: Optional[str] = None
    alignment: Alignment = Alignment.Neutral
    # Structure Attributes
    structure_type: StructureType = StructureType.Null
    # Unit Attributes
    unit_type: UnitType = UnitType.Null
    carried_resource: ResourceType = ResourceType.Null
    carry_amount: int = 0
    carry_capacity: int = 25
    tasks: list[Task] = Field(default_factory=list)
    gathering_rate: float = 1.0
    action_cooldown: float = 1.0
    time_until_action: float = 1.0
    # Resource Attributes
    resource_type: ResourceType = ResourceType.Null

    async def on_tick(self, game: Game, delta: float):
        if self.entity_type == EntityType.Unit:
            await self.on_unit_tick(game, delta)
        if self.entity_type == EntityType.Structure:
            await self.on_structure_tick(game, delta)

    async def on_structure_tick(self, game: Game, delta: float):
        if self.time_until_action > 0:
            self.time_until_action -= delta
            return
        self.time_until_action = random.uniform(self.action_cooldown - 0.05, self.action_cooldown + 0.05)

        if self.structure_type == StructureType.ArrowTower:
            enemy = self.find_enemy_nearby(game, 6)
            if enemy is None:
                return
            await game.handle_attack(self, enemy, random.uniform(4.5, 5.5))

    async def on_unit_tick(self, game: Game, delta: float):
        if self.time_until_action > 0:
            self.time_until_action -= delta
            return
        self.time_until_action = random.uniform(self.action_cooldown - 0.05, self.action_cooldown + 0.05)

        if self.alignment == Alignment.Player:
            await self.on_worker_tick(game)
        elif self.alignment == Alignment.Enemy:
            await self.on_enemy_tick(game)

    async def on_enemy_tick(self, game: Game):
        if self.unit_type == UnitType.Voidling:
            vision_range = 6
            attack_range = 1
            damage = (2.5, 3)
        else:
            return

        # Check for an enemy in attack range

        # Check for an enemy nearby
        enemy = self.find_enemy_nearby(game, vision_range)
        if enemy is None:
            await self.move_toward(Position(0, 0), game)
            return

        # If close enough to the enemy, attack them
        if self.position.distance(enemy.position) <= attack_range:
            await game.handle_attack(self, enemy, random.uniform(*damage))
        # If not, move closer
        else:
            await self.move_toward(enemy.position, game)

    async def on_worker_tick(self, game: Game):
        if self.position.magnitude <= 2 and self.carried_resource != ResourceType.Null:
            task = game.add_resource(self.carried_resource, self.carry_amount)
            self.carry_amount = 0
            self.carried_resource = ResourceType.Null
            await task

        if self.carry_amount == self.carry_capacity:
            await self.move_toward(Position(0, 0), game)

        elif self.unit_type == UnitType.Builder:
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
                    await self.move_toward(structure.position, game)

        elif self.unit_type == UnitType.Lumberjack:
            await self.gather(ResourceType.Wood, game)

        elif self.unit_type == UnitType.Miner:
            await self.gather(ResourceType.Stone, game)

        elif self.unit_type == UnitType.Farmer:
            await self.gather(ResourceType.Food, game)

    async def gather(self, resource_type: ResourceType, game: Game):
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
            await self.move_toward(target_position, game)

    def find_enemy_nearby(self, game: Game, limit: int = 20) -> Optional[Entity]:
        for position in self.position.flood_fill(limit):
            entity = game.map.get(position)
            if entity is None:
                continue
            if entity.alignment == Alignment.Neutral:
                continue
            if entity.alignment != self.alignment:
                return entity
        return None

    async def move_toward(self, target_position: Position, game: Game, limit: int = 20) -> bool:
        path = game.path_between(self.position, target_position, limit)
        if not path:
            return False
        await game.move_entity(self, path[0])
        return True


class Game(BaseModel):
    id: str # Same ID as the associated channel
    player: str
    state: GameState = GameState.Lobby
    entities: dict[str, Entity] = Field(default_factory=dict)

    resources: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    structures: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    units: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    map: dict[Position, Entity] = Field(default_factory=dict, exclude=True)
    subscribers: set[Connection] = Field(default_factory=set, exclude=True)

    spawn_cooldown: float = 5.0
    time_until_spawn: float = 10.0

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
        for unit in tuple(self.units.values()):
            await unit.on_tick(self, delta)
        for structure in tuple(self.structures.values()):
            await structure.on_tick(self, delta)

        self.time_until_spawn -= delta
        if self.time_until_spawn <= 0:
            self.time_until_spawn = random.uniform(self.spawn_cooldown - 0.05, self.spawn_cooldown + 0.05)
            await self.spawn_enemy()

    async def spend(self, *costs: tuple[ResourceType, int]):
        for resource_type, amount in costs:
            available = getattr(self, str(resource_type))
            if available < amount:
                raise ClientError(f"not enough {resource_type}")
        for resource_type, amount in costs:
            setattr(self, str(resource_type), available - amount)
            await self.broadcast({"type": "resource", "resource_type": resource_type, "amount": -amount})

    async def add_resource(self, resource_type: ResourceType, amount: int):
        setattr(self, str(resource_type), getattr(self, str(resource_type)) + amount)
        await self.broadcast({"type": "resource", "resource_type": resource_type, "amount": amount})

    async def handle_attack(self, attacker: Entity, target: Entity, amount: float):
        target.hp -= amount
        if target.hp < 0:
            target.hp = 0

        await self.broadcast({
            "type": "entity/update",
            "id": target.id,
            "hp": target.hp,
            "source": attacker.id,
        })

        if target.hp == 0:
            await self.remove_entity(target)


    async def spawn_enemy(self) -> Entity:
        return await self.add_entity(Entity(
            entity_type=EntityType.Unit,
            unit_type=UnitType.Voidling,
            alignment=Alignment.Enemy,
            name="Voidling",
            hp=5,
            max_hp=5,
            position=Position(
                10 + random.randint(0, 10) * random.choice((-1, 1)),
                10 + random.randint(0, 10) * random.choice((-1, 1))
            ),
        ))

    async def place_town_hall(self):
        town_hall = await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.TownHall,
            alignment=Alignment.Player,
            hp=100,
            max_hp=100,
            position=Position(0,0)
        ))
        for position in Position(0,0).neighbors:
            self.map[position] = town_hall

        # DBG
        await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.ArrowTower,
            alignment=Alignment.Player,
            hp=10,
            max_hp=10,
            position=Position(0,-3)
        ))
        await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.ArrowTower,
            alignment=Alignment.Player,
            hp=10,
            max_hp=10,
            position=Position(0, 3)
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
        elif entity.entity_type == EntityType.Unit:
            self.units[entity.id] = entity
        elif entity.entity_type == EntityType.Resource:
            self.resources[entity.id] = entity
        await self.broadcast({"type": "entity/add", "entity": entity.model_dump(mode="json")})
        return entity

    async def move_entity(self, entity: Entity, position: Position):
        if entity.position == position:
            return
        if position in self.map:
            raise ValueError("position is occupied")
        self.map.pop(entity.position, None)
        entity.position = position
        self.map[entity.position] = entity
        await self.broadcast({"type": "entity/update", "id": entity.id, "position": position.model_dump()})

    async def remove_entity(self, entity: Entity):
        self.entities.pop(entity.id, None)
        self.map.pop(entity.position, None)
        if entity.entity_type == EntityType.Structure:
            self.structures.pop(entity.id, None)
        elif entity.entity_type == EntityType.Unit:
            self.units.pop(entity.id, None)
        elif entity.entity_type == EntityType.Resource:
            self.resources.pop(entity.id, None)
        await self.broadcast({"type": "entity/remove", "id": entity.id})

    def empty_space_near(self, starting_position: Position) -> Position:
        for position in starting_position.flood_fill():
            if position not in self.map:
                return position

    def resolve_path(self, start_position: Position, target_position: Position, previous_positions: dict[Position, Position]):
        path = []
        cursor = target_position
        while cursor != start_position:
            path.append(cursor)
            cursor = previous_positions[cursor]
        path.reverse()
        return path

    def path_between(self, start_position: Position, target_position: Position, limit: int = 20) -> list[Position]:
        already_visited: set[Position] = {start_position}
        current_positions: list[Position] = [start_position]
        previous_positions: dict[Position, Position] = {start_position: None}
        distance = 0
        while current_positions:
            next_positions: list[Position] = []
            for position in current_positions:
                for neighbor in position.neighbors:
                    if neighbor not in previous_positions:
                        previous_positions[neighbor] = position
                    if neighbor == target_position:
                        return self.resolve_path(start_position, target_position, previous_positions)
                    if neighbor in already_visited:
                        continue
                    if neighbor in self.map:
                        continue
                    already_visited.add(neighbor)
                    next_positions.append(neighbor)
            current_positions = next_positions
            if limit is not None and distance >= limit:
                break
            distance += 1
        closest_viable_target = None
        best_distance = None
        for potential_target in already_visited:
            distance = potential_target.distance(target_position)
            if best_distance is None or distance < best_distance:
                closest_viable_target = potential_target
                best_distance = distance
        return self.resolve_path(start_position, closest_viable_target, previous_positions)


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


class BuildRequest(GameRequest):
    position: Position


@register("game/build/arrow_tower")
async def handle_build_tower(connection: Connection, request: BuildRequest):
    if request.game.player != connection.user.id:
        raise AuthError("insufficient permissions")

    if request.position in request.game.map:
        raise ClientError("position is occupied")

    await request.game.spend([ResourceType.Wood, 100], [ResourceType.Stone, 100])

    await request.game.add_entity(Entity(
        entity_type=EntityType.Structure,
        structure_type=StructureType.ArrowTower,
        alignment=Alignment.Player,
        hp=10,
        max_hp=10,
        position=request.position,
    ))


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
