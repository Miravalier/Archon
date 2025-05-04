from __future__ import annotations
import asyncio
import random
import time
import traceback
import yaml
from bson import ObjectId
from enum import IntEnum, StrEnum
from math import sqrt
from pydantic import BaseModel, ConfigDict, Field
from pydantic.functional_validators import BeforeValidator
from pydantic.functional_serializers import PlainSerializer
from shapely import Polygon, geometry
from typing import Annotated, Any, Optional

from .errors import ClientError
from .handlers import register
from .pqueue import PriorityQueue
from .request_models import Connection


GRID_SIZE = 100


def shape_to_coordinates(shape):
    return geometry.mapping(shape)["coordinates"]


GamePolygon = Annotated[
    Polygon, PlainSerializer(shape_to_coordinates, return_type=tuple)
]


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
    def x(self):
        return GRID_SIZE * 1.5 * (sqrt(3) * self.q + sqrt(3)/2 * self.r)

    @property
    def y(self):
        return GRID_SIZE * 1.5 * (3 / 2 * self.r)

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

    @property
    def random_neighbors(self) -> list[Position]:
        result = self.neighbors
        random.shuffle(result)
        return result

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
            random.shuffle(current_positions)
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
    def from_cube(cld, q: int = None, r: int = None, s: int = None) -> Position:
        if int(q != None) + int(r != None) + int(s != None) != 2:
            raise ValueError("specify exactly two of q, r, and s")
        if s is None:
            return Position(q=q, r=r)
        if r is None:
            return Position(q=q, r=-s-q)
        if q is None:
            return Position(q=-s-r, r=r)

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
            results.append(self.lerp(other, interval * i))
        return results

    def hexes_within(self, distance: int) -> list[Position]:
        results: list[Position] = []
        for i in range(-distance, distance+1):
            for j in range(max(-distance, -i-distance), min(distance, -i+distance)):
                results.append(Position(q=self.q+i, r=self.r+j))

    @classmethod
    def from_pixels(cls, x: float, y: float) -> Position:
        # For pointy-top hexes
        return cls.from_floats(
            (sqrt(3)/3 * x - 1/3 * y) / GRID_SIZE,
            (2/3 * y) / GRID_SIZE
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
    Portal = "portal"


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
    alignment: Alignment = Alignment.Neutral
    vision_size: int = 10
    time_until_update: float = 0.0
    image: Optional[str] = None # Comma separated list of PNGs
    tint: int = 0xFFFFFF # Comma separated RGB tint list applied to images
    size: int = 200 # Size of image in pixels
    # Structure Attributes
    structure_type: StructureType = StructureType.Null
    # Unit Attributes
    unit_type: UnitType = UnitType.Null
    carried_resource: ResourceType = ResourceType.Null
    carry_amount: int = 0
    carry_capacity: int = 25
    tasks: list[Task] = Field(default_factory=list)
    path: list[Position] = Field(default_factory=list)
    gathering_rate: float = 1.0
    action_cooldown: float = 1.0
    time_until_action: float = 1.0
    # Resource Attributes
    resource_type: ResourceType = ResourceType.Null

    async def on_tick(self, game: Game, delta: float):
        if self.time_until_update <= 0.0:
            game.queue_update(self)
        else:
            self.time_until_update -= delta

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
        elif self.structure_type == StructureType.Portal:
            await game.add_entity(Entity(
                entity_type=EntityType.Unit,
                unit_type=UnitType.Voidling,
                alignment=self.alignment,
                name="Voidling",
                hp=5,
                max_hp=5,
                position=game.empty_space_near(self.position),
                image="/voidling.png",
            ))

    async def on_unit_tick(self, game: Game, delta: float):
        if self.time_until_action > 0:
            self.time_until_action -= delta
            return
        self.time_until_action = random.uniform(self.action_cooldown - 0.05, self.action_cooldown + 0.05)

        if self.path:
            next_position = self.path.pop()
            if next_position in game.map:
                self.path = []
            else:
                await game.move_entity(self, next_position)
                return

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
        path = path[0:len(path)//5 + 1]
        if len(path) == 1:
            await game.move_entity(self, path[0])
        else:
            await game.assign_path(self, path)
        return True


def create_hexagon(position: Position, size: int) -> Polygon:
    positions: list[Position] = [
        Position(q=position.q, r=position.r-size),
        Position(q=position.q+size, r=position.r-size),
        Position(q=position.q+size, r=position.r),
        Position(q=position.q, r=position.r+size),
        Position(q=position.q-size, r=position.r+size),
        Position(q=position.q-size, r=position.r),
        Position(q=position.q, r=position.r-size),
    ]
    vertices: list[tuple[int, int]] = []
    for position in positions:
        vertices.append([position.x, position.y])
    return Polygon(vertices)


def generate_starting_vision() -> Polygon:
    return create_hexagon(Position(0,0), 12).normalize()


class Game(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    owner: str
    inactive: bool = False
    entities: dict[str, Entity] = Field(default_factory=dict)
    state: GameState = GameState.Lobby

    resources: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    structures: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    units: dict[str, Entity] = Field(default_factory=dict, exclude=True)
    map: dict[Position, Entity] = Field(default_factory=dict, exclude=True)
    subscribers: set[Connection] = Field(default_factory=set, exclude=True)
    queued_updates: set[str] = Field(default_factory=set, exclude=True)

    time_since_active: float = 0.0

    food: float = 1000.0
    gold: float = 1000.0
    stone: float = 1000.0
    wood: float = 1000.0
    aether: float = 1000.0

    revealed_area: GamePolygon = Field(default_factory=generate_starting_vision)

    def end(self):
        games.pop(self.id, None)

    def queue_update(self, entity: Entity):
        self.queued_updates.add(entity.id)

    def generate_spawn_points(self, distance: int = 30) -> list[Position]:
        cube_pairs = [
            {"s": distance, "r": -distance},
            {"r": -distance, "q": distance},
            {"q": distance, "s": -distance},
            {"s": -distance, "r": distance},
            {"r": distance, "q": -distance},
            {"q": -distance, "s": distance},
            {"s": distance, "r": -distance},
        ]
        spawn_points: set[Position] = set()
        previous_position = None
        for pair in cube_pairs:
            position = Position.from_cube(**pair)
            if previous_position is not None:
                for between_position in previous_position.line_to(position):
                    spawn_points.add(between_position)
            previous_position = position
        return list(spawn_points)

    async def broadcast(self, message: Any):
        broken_connections: set[Connection] = set()
        for connection in self.subscribers:
            try:
                await connection.ws.send_json(message)
            except Exception:
                broken_connections.add(connection)
        self.subscribers -= broken_connections

    async def on_tick(self, delta: float):
        if self.inactive:
            if self.subscribers:
                self.inactive = False
            else:
                self.time_since_active += delta
                if self.time_since_active > 30.0:
                    self.end()
                return

        if not self.subscribers:
            self.inactive = True
            self.time_since_active = 0.0
            return

        for unit in tuple(self.units.values()):
            await unit.on_tick(self, delta)
        for structure in tuple(self.structures.values()):
            await structure.on_tick(self, delta)

        serialized_entities = []
        for entity_id in self.queued_updates:
            entity = self.entities.get(entity_id, None)
            if entity is None:
                continue
            serialized_entities.append(entity.model_dump(mode="json"))
            entity.time_until_update = random.uniform(5.0, 6.0)
        self.queued_updates.clear()
        await self.broadcast({"type": "entity/update", "entities": serialized_entities})

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
            "type": "entity/attack",
            "visual": "laser",
            "source": attacker.id,
            "target": target.id,
        })

        if target.hp == 0:
            await self.remove_entity(target)
        else:
            self.queue_update(target)

    async def place_town_hall(self):
        town_hall = await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.TownHall,
            alignment=Alignment.Player,
            hp=100,
            max_hp=100,
            position=Position(0,0),
            image="/castle.png",
            size=500,
        ))
        for position in Position(0,0).neighbors:
            self.map[position] = town_hall

        spawn_points = self.generate_spawn_points()

        await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.Portal,
            alignment=Alignment.Enemy,
            hp=100,
            max_hp=100,
            action_cooldown=5.0,
            time_until_action=5.0,
            position=random.choice(spawn_points),
            image="/portal.png",
        ))

        # DBG
        await self.add_arrow_tower(Position(0, -3))
        await self.add_arrow_tower(Position(0, 3))

    async def add_arrow_tower(self, position: Position):
        return await self.add_entity(Entity(
            entity_type=EntityType.Structure,
            structure_type=StructureType.ArrowTower,
            alignment=Alignment.Player,
            hp=10,
            max_hp=10,
            position=position,
            image="/tower.png,/arrow-tower.png",
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
        valid_positions = [p for p in Position(0,0).flood_fill(limit=6) if p not in self.map]
        for resource_type in [ResourceType.Stone, ResourceType.Food, ResourceType.Wood]:
            position = random.choice(valid_positions)
            valid_positions.remove(position)
            await self.add_entity(Entity(
                entity_type=EntityType.Resource,
                position=position,
                resource_type=resource_type
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
        if entity.alignment == Alignment.Player:
            await self.add_vision(entity)
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
        if entity.alignment == Alignment.Player:
            await self.add_vision(entity)

        self.queue_update(entity)

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

    async def add_vision(self, entity: Entity):
        new_area = self.revealed_area.union(create_hexagon(entity.position, entity.vision_size))
        if new_area == self.revealed_area:
            return
        self.revealed_area = new_area
        await self.broadcast({"type": "reveal", "area": shape_to_coordinates(self.revealed_area)})

    async def assign_path(self, entity: Entity, path: list[Position]):
        path.reverse()
        entity.path = path
        await self.move_entity(entity, entity.path.pop())

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
        """
        Use ε-admissible A* to find the best path reachable while
        considering a limited number of positions.
        """
        queue: PriorityQueue[Position, int] = PriorityQueue()
        queue.add(start_position, 2 * target_position.distance(start_position))
        previous_positions: dict[Position, Position] = {start_position: None}

        # Least distance from start
        least_distances: dict[Position, int] = {start_position: 0}

        # Closest position to end
        best_target = start_position
        best_target_distance = target_position.distance(best_target)

        steps = 0
        while queue and steps < limit:
            steps += 1
            position = queue.pop()
            if position == target_position:
                best_target = target_position
                break
            distance_to_target = target_position.distance(position)
            if distance_to_target < best_target_distance:
                best_target = position
                best_target_distance = distance_to_target
            for neighbor in position.random_neighbors:
                if neighbor in self.map:
                    continue
                distance = least_distances[position] + 1
                current_best = least_distances.get(neighbor, None)
                if current_best is None or distance < current_best:
                    previous_positions[neighbor] = position
                    least_distances[neighbor] = distance
                    queue.add(neighbor, distance + 2 * target_position.distance(neighbor))

        return self.resolve_path(start_position, best_target, previous_positions)

    def flood_fill_path_between(self, start_position: Position, target_position: Position, limit: int = 20) -> list[Position]:
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
            random.shuffle(current_positions)
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
    return connection.user.model_dump(mode="json")


@register("game/create")
async def handle_game_create(connection: Connection):
    game = Game(id=generate_id(), owner=connection.user.id)
    await game.place_town_hall()
    await game.generate_resources()
    games[game.id] = game
    return game.model_dump()


@register("game/get")
async def handle_game_get(connection: Connection, request: GameRequest):
    return request.game.model_dump(mode="json")


@register("game/subscribe")
async def handle_game_subscribe(connection: Connection, request: GameRequest):
    request.game.subscribers.add(connection)

    return {"type": "success"}


class BuildRequest(GameRequest):
    position: Position


@register("game/build/farmer")
async def handle_buy_farmer(connection: Connection, request: GameRequest):
    await request.game.spend([ResourceType.Gold, 100])

    await request.game.add_entity(Entity(
        entity_type=EntityType.Unit,
        alignment=Alignment.Player,
        position=request.game.empty_space_near(Position(0,0)),
        unit_type=UnitType.Farmer,
        image="/farmer.png",
        name="Farmer",
    ))


@register("game/build/arrow_tower")
async def handle_build_tower(connection: Connection, request: BuildRequest):
    if request.position in request.game.map:
        raise ClientError("position is occupied")

    await request.game.spend([ResourceType.Wood, 100], [ResourceType.Stone, 100])
    await request.game.add_arrow_tower(request.position)


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
