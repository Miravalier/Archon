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


class GameState(StrEnum):
    Lobby = "lobby"
    Active = "active"


class Position(BaseModel):
    q: int
    r: int

    def __init__(self, q: int = 0, r: int = 0):
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


class EntityTag(IntEnum):
    Unit = 1
    Resource = 2
    Structure = 4


class Alignment(IntEnum):
    Enemy = 0
    Neutral = 1
    Player = 2


class Behaviour(BaseModel):
    """
    Abstract base class for all behaviours.
    """
    time_until_activation: float = 0.0 # Time in seconds before the first activation
    cooldown: float = 0.0 # Time in seconds between subsequent activations

    async def on_tick(self, entity: Entity, game: Game, delta: float):
        """
        Called every tick.
        """
        self.time_until_activation -= delta
        if self.time_until_activation <= 0.0:
            self.time_until_activation += random.uniform(0.95, 1.05) * self.cooldown
            await self.on_activate(entity, game)

    async def on_create(self, entity: Entity, game: Game):
        """
        Called when an entity is created.
        """
        pass

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        """
        Called each time the cooldown expires. Returns whether the activation
        has been handled or should continue being processed.
        """
        pass

    async def on_remove(self, entity: Entity, game: Game):
        """
        Called when an entity is removed for any reason.
        """
        pass

    async def on_action(self, entity: Entity, target: Entity, game: Game):
        """
        Called when a user sends an action command with a given target
        """
        pass


class AttackBehaviour(Behaviour):
    range: int = 1
    min_damage: float = 0.0
    max_damage: float = 0.0
    visual: str = ""
    manual_target: Optional[str] = None

    async def on_action(self, entity, target, game):
        await super().on_action(entity, target, game)

        if target.entity_tag & EntityTag.Resource:
            return

        self.manual_target = target.id

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        manual_target = game.entities.get(self.manual_target)
        if manual_target is not None and manual_target.position.distance(entity.position) <= self.range:
            enemy = manual_target
        else:
            enemy = entity.find_enemy_nearby(game, self.range)

        if enemy is None:
            return False

        await game.handle_attack(
            entity,
            enemy,
            random.uniform(self.min_damage, self.max_damage),
            self.visual
        )
        return True


class SummonBehaviour(Behaviour):
    unit: str

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        await game.add_entity(self.unit, game.empty_space_near(entity.position), entity.alignment)
        return True


class PathingBehaviour(Behaviour):
    path: list[Position] = Field(default_factory=list)

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        if self.path:
            next_position = self.path.pop()
            if next_position in game.map:
                self.path = []
            else:
                await game.move_entity(entity, next_position)
                return True

        return False

    async def move_toward(self, entity: Entity, game: Game, target_position: Position, limit: int = 20) -> bool:
        # Find a path to the target location
        path = game.path_between(entity.position, target_position, limit)
        if not path:
            return False

        # Truncate the path to 1/5 of its length (rounded up)
        path = path[0:len(path)//5 + 1]

        # If the remaining path contains only 1 space, just move
        if len(path) == 1:
            await game.move_entity(entity, path[0])
        # If the remaining path is longer, store the future spaces and move
        else:
            path.reverse()
            self.path = path
            await game.move_entity(entity, self.path.pop())

        return True


class GatherResourcesBehaviour(PathingBehaviour):
    target_resource: Optional[Entity] = None
    carried_resource: ResourceType = ResourceType.Null
    carry_capacity: int = 25
    carry_amount: int = 0

    async def on_action(self, entity: Entity, target: Entity, game: Game):
        await super().on_action(entity, target, game)

        if not (target.entity_tag & EntityTag.Resource):
            return

        self.target_resource = target

    async def on_create(self, entity: Entity, game: Game):
        await super().on_create(entity, game)

        if self.target_resource is None:
            for position in entity.position.flood_fill():
                target_entity = game.map.get(position)
                if target_entity is None:
                    continue
                if not (target_entity.entity_tag & EntityTag.Resource):
                    continue
                self.target_resource = target_entity
                break

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        # If we're near the town hall and carrying resources, drop them off
        if entity.position.magnitude <= 2 and self.carried_resource != ResourceType.Null:
            task = game.add_resource(self.carried_resource, self.carry_amount)
            self.carry_amount = 0
            self.carried_resource = ResourceType.Null
            await task

        # If our inventory is full, path toward the town hall
        if self.carry_amount == self.carry_capacity:
            await self.move_toward(entity, game, Position(0, 0))
            return True

        # If we're adjacent to the target resource, gather from it
        if entity.position.distance(self.target_resource.position) == 1:
            if self.carried_resource != self.target_resource.resource_type:
                self.carry_amount = 0
                self.carried_resource = self.target_resource.resource_type
            self.carry_amount += 5
        # Otherwise path toward our target resource
        else:
            await self.move_toward(entity, game, self.target_resource.position)

        # We always have something to do
        return True


class RepairBehaviour(PathingBehaviour):
    async def on_activate(self, entity, game):
        if await super().on_activate(entity, game):
            return True

        # Find nearest damaged structure
        target = None
        lowest_distance = None
        for structure in game.structures.values():
            if structure.alignment != entity.alignment:
                continue
            if structure.hp == structure.max_hp:
                continue
            distance = entity.position.distance(structure.position)
            if lowest_distance is None or distance < lowest_distance:
                lowest_distance = distance
                target = structure

        # Nothing to repair
        if target is None:
            return False

        # Repair if adjacent, or path to if not adjacent
        if lowest_distance == 1:
            structure.hp = min(structure.hp + 5, structure.max_hp)
        else:
            await self.move_toward(entity, game, structure.position)
        return True


class SeekEnemyBehaviour(PathingBehaviour):
    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        enemy = entity.find_enemy_nearby(game, entity.vision_size)
        if enemy is None:
            return False

        return await self.move_toward(entity, game, enemy.position)


class SeekTownHallBehaviour(SeekEnemyBehaviour):
    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        return await self.move_toward(entity, game, Position(0, 0))


class Entity(BaseModel):
    id: str = Field(default_factory=generate_id)
    template: bool = True
    entity_tag: int = 0
    resource_type: ResourceType = ResourceType.Null # Only used if entity_tag contains Resource
    position: Position = Field(default_factory=Position)
    name: str = "<Unknown>"
    hp: float = 0
    max_hp: float = 0
    alignment: Alignment = Alignment.Neutral
    vision_size: int = 10
    image: Optional[str] = None # Comma separated list of PNGs
    tint: int = 0xFFFFFF # RBG tint
    size: int = 200 # Size of image in pixels
    behaviours: list[Behaviour] = Field(default_factory=list)

    time_until_update: float = Field(0.0, exclude=True)

    async def on_tick(self, game: Game, delta: float):
        self.time_until_update -= delta
        if self.time_until_update <= 0.0:
            game.queue_update(self)

        for behaviour in self.behaviours:
            await behaviour.on_tick(self, game, delta)

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

    async def on_action(self, game: Game, target: Entity):
        for behaviour in self.behaviours:
            await behaviour.on_action(self, target, game)


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
    state: GameState = GameState.Lobby
    entities: dict[str, Entity] = Field(default_factory=dict)

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

        for entity in tuple(self.entities.values()):
            await entity.on_tick(self, delta)

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

    async def handle_attack(self, attacker: Entity, target: Entity, amount: float, visual: str):
        target.hp -= amount
        if target.hp < 0:
            target.hp = 0

        await self.broadcast({
            "type": "entity/attack",
            "visual": visual,
            "source": attacker.id,
            "target": target.id,
        })

        if target.hp == 0:
            await self.remove_entity(target)
        else:
            self.queue_update(target)

    async def place_town_hall(self):
        town_hall = await self.add_entity("Town Hall", Position(0, 0), Alignment.Player)
        for position in Position(0,0).neighbors:
            self.map[position] = town_hall

        spawn_points = self.generate_spawn_points()
        await self.add_entity("Portal", random.choice(spawn_points), Alignment.Enemy)
        await self.add_entity("Arrow Tower", Position(0, -3), Alignment.Player)
        await self.add_entity("Arrow Tower", Position(0, 3), Alignment.Player)

    async def generate_resources(self):
        for q in range(-500, 501):
            for r in range(-500, 501):
                position = Position(q, r)
                if position.s < -500 or position.s > 500:
                    continue
                if position in self.map:
                    continue
                if random.randint(0, 60 + position.magnitude**2 // 100) == 0:
                    await self.add_entity(random.choice(["Stone", "Food", "Wood"]), position)

        valid_positions = [p for p in Position(0,0).flood_fill(limit=6) if p not in self.map]
        for resource_type in ["Stone", "Food", "Wood"]:
            position = random.choice(valid_positions)
            valid_positions.remove(position)
            await self.add_entity(resource_type, position)

    async def add_entity(self, name: str, position: Position, alignment: Alignment = Alignment.Neutral) -> Entity:
        if position in self.map:
            raise RuntimeError("attempted to add entity to occupied position")

        template = entity_templates[name]

        entity = template.model_copy()
        entity.id = generate_id()
        entity.name = name
        entity.hp = entity.max_hp
        entity.position = position
        entity.alignment = alignment
        entity.template = False
        entity.behaviours = [behaviour.model_copy() for behaviour in entity.behaviours]

        self.entities[entity.id] = entity
        self.map[entity.position] = entity
        if entity.entity_tag & EntityTag.Structure:
            self.structures[entity.id] = entity
        elif entity.entity_tag & EntityTag.Unit:
            self.units[entity.id] = entity
        elif entity.entity_tag & EntityTag.Resource:
            self.resources[entity.id] = entity
        if entity.alignment == Alignment.Player:
            await self.add_vision(entity)

        await self.broadcast({"type": "entity/add", "entity": entity.model_dump(mode="json")})
        for behaviour in entity.behaviours:
            await behaviour.on_create(entity, self)
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
        if entity.entity_tag & EntityTag.Structure:
            self.structures.pop(entity.id, None)
        elif entity.entity_tag & EntityTag.Unit:
            self.units.pop(entity.id, None)
        elif entity.entity_tag & EntityTag.Resource:
            self.resources.pop(entity.id, None)
        for behaviour in entity.behaviours:
            await behaviour.on_remove(entity, self)
        await self.broadcast({"type": "entity/remove", "id": entity.id})

    async def add_vision(self, entity: Entity):
        new_area = self.revealed_area.union(create_hexagon(entity.position, entity.vision_size))
        if new_area == self.revealed_area:
            return
        self.revealed_area = new_area
        await self.broadcast({"type": "reveal", "area": shape_to_coordinates(self.revealed_area)})

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


@register("game/train/worker")
async def handle_train_worker(connection: Connection, request: GameRequest):
    await request.game.spend([ResourceType.Gold, 100])
    await request.game.add_entity("Worker", request.game.empty_space_near(Position(0, 0)), Alignment.Player)


@register("game/build/arrow_tower")
async def handle_build_tower(connection: Connection, request: BuildRequest):
    if request.position in request.game.map:
        raise ClientError("position is occupied")

    await request.game.spend([ResourceType.Wood, 100], [ResourceType.Stone, 100])
    await request.game.add_entity("Arrow Tower", request.position, Alignment.Player)


class ActionRequest(GameRequest):
    selected: list[str]
    target: str


@register("game/action")
async def handle_take_action(connection: Connection, request: ActionRequest):
    target_entity = request.game.entities.get(request.target)
    if target_entity is None:
        return

    for selected_id in request.selected:
        selected_entity = request.game.entities.get(selected_id)
        if selected_entity is None or selected_entity.alignment != Alignment.Player:
            continue
        await selected_entity.on_action(request.game, target_entity)


entity_templates: dict[str, Entity] = {
    "Stone": Entity(
        entity_tag=EntityTag.Resource,
        resource_type=ResourceType.Stone,
        image="/rock.png",
        tint=0x808080,
    ),
    "Food": Entity(
        entity_tag=EntityTag.Resource,
        resource_type=ResourceType.Food,
        image="/wheat.png",
        tint=0xffff00,
    ),
    "Wood": Entity(
        entity_tag=EntityTag.Resource,
        resource_type=ResourceType.Wood,
        image="/forest.png",
        tint=0x40a010,
    ),
    "Town Hall": Entity(
        entity_tag=EntityTag.Structure,
        max_hp=100,
        image="/castle.png",
        size=500,
    ),
    "Arrow Tower": Entity(
        entity_tag=EntityTag.Structure,
        max_hp=15,
        image="/tower.png,/arrow-tower.png",
        behaviours=[
            AttackBehaviour(cooldown=1.0, range=6, min_damage=4.0, max_damage=6.0, visual="arrow"),
        ],
    ),
    "Voidling": Entity(
        entity_tag=EntityTag.Unit,
        max_hp=5,
        image="/voidling.png",
        behaviours=[
            SeekTownHallBehaviour(cooldown=1.0),
            AttackBehaviour(cooldown=1.0, range=1, min_damage=0.75, max_damage=1.25, visual="claws"),
        ],
    ),
    "Portal": Entity(
        entity_tag=EntityTag.Structure,
        max_hp=100,
        image="/portal.png",
        behaviours=[
            SummonBehaviour(cooldown=5.0, unit="Voidling"),
        ]
    ),
    "Worker": Entity(
        entity_tag=EntityTag.Unit,
        image="/farmer.png",
        max_hp=10,
        behaviours=[
            GatherResourcesBehaviour(cooldown=1.0, carry_capacity=25),
        ]
    ),
}


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
