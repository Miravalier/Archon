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
from typing import Annotated, Any, Callable, Optional, Type

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
    Finished = "finished"


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
        return isinstance(value, Position) and self.q == value.q and self.r == value.r

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

    @classmethod
    def from_string(cls, s: str) -> Position:
        return cls(*[int(value.strip()) for value in s.split(",")])

    def to_string(self) -> str:
        return f"{self.q},{self.r}"


class EntityTag(IntEnum):
    Unit = 1
    Resource = 2
    Structure = 4


class Alignment(IntEnum):
    Enemy = 0
    Neutral = 1
    Player = 2


entity_tag_map = {
    "Structure": EntityTag.Structure,
    "Unit": EntityTag.Unit,
    "Resource": EntityTag.Resource,
}


resource_type_map = {
    "": ResourceType.Null,
    "Food": ResourceType.Food,
    "Gold": ResourceType.Gold,
    "Stone": ResourceType.Stone,
    "Wood": ResourceType.Wood,
    "Aether": ResourceType.Aether,
}


class Behaviour(BaseModel):
    """
    Abstract base class for all behaviours.
    """
    label: Optional[str] = None
    time_until_activation: float = 0.0 # Time in seconds before the first activation
    cooldown: float = 0.0 # Time in seconds between subsequent activations

    def on_query(self, entity: Entity, game: Game) -> list[tuple[str, str]]:
        """
        Called when the user requests a list of commands available to this entity.
        """
        return []

    async def on_tick(self, entity: Entity, game: Game, delta: float):
        """
        Called every tick.
        """
        self.time_until_activation -= delta
        if self.time_until_activation <= 0.0:
            # If on_activate fails to do anything, try again in 1/3 the time
            if await self.on_activate(entity, game):
                self.time_until_activation += random.uniform(0.95, 1.05) * self.cooldown
            else:
                self.time_until_activation += random.uniform(0.95, 1.05) * self.cooldown * 0.33

    async def on_create(self, entity: Entity, game: Game):
        """
        Called when this entity is created.
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

    async def on_target(self, entity: Entity, game: Game, position: Position):
        """
        Called when a user sets the target of this behaviour.
        """
        pass

    async def on_command(self, entity: Entity, game: Game, key: str, value: str):
        """
        Called when the user issues a command to this behaviour.
        """
        pass

    async def on_heal(self, entity: Entity, game: Game, amount: float):
        """
        Called when the entity is healed or repaired.
        """
        pass

    @classmethod
    def from_yaml(cls: Type[Behaviour], data: dict) -> Behaviour:
        raise NotImplementedError("this class does not implement from_yaml")


class EssentialBehaviour(Behaviour):
    async def on_remove(self, entity: Entity, game: Game):
        await super().on_remove(entity, game)

        if not any(e.name == entity.name for e in game.entities.values()):
            await game.end(False, "Defeat")

    @classmethod
    def from_yaml(cls: Type[Behaviour], data: dict) -> Behaviour:
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return cls()


class KillObjectiveBehaviour(Behaviour):
    async def on_remove(self, entity: Entity, game: Game):
        await super().on_remove(entity, game)

        if not any(e.name == entity.name for e in game.entities.values()):
            await game.end(True, "Victory")

    @classmethod
    def from_yaml(cls: Type[Behaviour], data: dict) -> Behaviour:
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return cls()


class UnderConstructionBehaviour(Behaviour):
    unit: str
    builder: Entity
    costs: list[tuple[ResourceType, int]]

    async def on_heal(self, entity: Entity, game: Game, amount: float):
        await super().on_heal(entity, game, amount)
        if entity.hp == entity.max_hp:
            await game.remove_entity(entity)
            await game.add_entity(self.unit, entity.position, entity.alignment)

    async def on_remove(self, entity, game):
        await super().on_remove(entity, game)
        for behaviour in self.builder.behaviours:
            if isinstance(behaviour, PathingBehaviour) and behaviour.target_position == entity.position:
                behaviour.target_position = None

    def on_query(self, entity: Entity, game: Game) -> list[tuple[str, str]]:
        commands = super().on_query(entity, game)
        commands.append([f"cancel/{self.unit}", f"Button:/images/symbols/unknown.png:False:Cancel {self.unit}"])
        return commands

    async def on_command(self, entity: Entity, game: Game, key: str, value: str):
        await super().on_command(entity, game, key, value)

        if key == f"cancel/{self.unit}":
            for resource_type, amount in self.costs:
                await game.add_resource(resource_type, amount//2)
            await game.remove_entity(entity)


class BuildBehaviour(Behaviour):
    unit: str
    costs: list[tuple[ResourceType, int]]
    duration: float = 0.0
    description: str = ""

    @property
    def tooltip(self):
        return "<br>".join((
            f"Build {self.unit}",
            "<i>" + f", ".join((f"{amt} {res}" for res, amt in self.costs)) + "</i>",
        ))

    def on_query(self, entity: Entity, game: Game) -> list[tuple[str, str]]:
        commands = super().on_query(entity, game)

        template = entity_templates[self.unit]
        commands.append([f"build/{self.unit}", f"Button:{template.image[-1]}:True:{self.tooltip}"])

        return commands

    async def on_command(self, entity: Entity, game: Game, key: str, value: str):
        await super().on_command(entity, game, key, value)

        if key == f"build/{self.unit}":
            position = Position.from_string(value)
            if position in game.map:
                raise ClientError("position is occupied")
            await game.spend(*self.costs)
            await game.build_entity(entity, self, self.unit, position)
            # If we try to start a building, path toward it
            for behaviour in entity.behaviours:
                if isinstance(behaviour, PathingBehaviour):
                    behaviour.target_position = position

    @classmethod
    def from_yaml(cls, data):
        costs = []
        cost_data: list[dict] = data.pop("Costs", [])
        for cost in cost_data:
            costs.append((resource_type_map[cost.pop("Resource")], int(cost.pop("Amount"))))
            if cost:
                raise KeyError(f"unused cost keys: {list(cost.keys())}")
        unit = data.pop("Unit")
        result = cls(
            costs=costs,
            unit=unit,
            label=data.pop("Label", None),
            duration=data.pop("Duration", 0.0),
            description=data.pop("Description", ""),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class TrainBehaviour(Behaviour):
    unit: str
    costs: list[tuple[ResourceType, int]]
    duration: float = 0.0
    description: str = ""

    queue: int = 0
    progress: float = 0.0

    async def on_tick(self, entity, game, delta):
        await super().on_tick(entity, game, delta)
        if self.queue == 0:
            self.progress = 0.0
            return
        else:
            self.progress += delta

        if self.progress >= self.duration:
            self.progress = 0.0
            self.queue -= 1
            await game.add_entity(self.unit, game.empty_space_near(entity.position), entity.alignment)
            await self.send_training_update(entity, game)

    async def send_training_update(self, entity: Entity, game: Game):
        await game.broadcast({
            "type": "entity/progress",
            "parent": entity.id,
            "event": self.unit,
            "queue": self.queue,
            "progress": self.progress,
            "duration": self.duration,
        })

    @property
    def tooltip(self):
        return "<br>".join((
            f"Train {self.unit}",
            "<i>" + f", ".join((f"{amt} {res}" for res, amt in self.costs)) + "</i>",
        ))

    def on_query(self, entity: Entity, game: Game) -> list[tuple[str, str]]:
        commands = super().on_query(entity, game)

        template = entity_templates[self.unit]
        commands.append([f"train/{self.unit}", f"Button:{template.image[-1]}:False:{self.tooltip}"])

        return commands

    async def on_command(self, entity: Entity, game: Game, key: str, value: str):
        await super().on_command(entity, game, key, value)

        if key == f"train/{self.unit}":
            await game.spend(*self.costs)
            self.queue += 1
            await self.send_training_update(entity, game)
        elif key == f"cancel/{self.unit}":
            if self.queue > 0:
                for resource_type, amount in self.costs:
                    await game.add_resource(resource_type, amount//2)
                self.queue -= 1
                await self.send_training_update(entity, game)

    @classmethod
    def from_yaml(cls, data):
        costs = []
        cost_data: list[dict] = data.pop("Costs", [])
        for cost in cost_data:
            costs.append((resource_type_map[cost.pop("Resource")], int(cost.pop("Amount"))))
            if cost:
                raise KeyError(f"unused cost keys: {list(cost.keys())}")
        unit = data.pop("Unit")
        result = cls(
            costs=costs,
            unit=unit,
            label=data.pop("Label", None),
            duration=data.pop("Duration", 0.0),
            description=data.pop("Description", ""),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


resource_values = {
    ResourceType.Food: 0.5,
    ResourceType.Stone: 0.5,
    ResourceType.Wood: 0.5,
    ResourceType.Gold: 1.0,
    ResourceType.Aether: 5.0,
}


class TransmuteBehaviour(Behaviour):
    current_rate: int = 0
    maximum_rate: int = 15
    efficiency: float = 0.8

    from_resource: ResourceType = ResourceType.Null
    to_resource: ResourceType = ResourceType.Null
    remainder: float = 0.0

    def on_query(self, entity: Entity, game: Game) -> list[tuple[str, str]]:
        commands = super().on_query(entity, game)
        commands.append(["!", "Transmuting"])
        commands.append(["rate", f"Number:0:{self.current_rate}:{self.maximum_rate}"])
        commands.append(["from_resource", f"ResourceType:{self.from_resource.capitalize()}"])
        commands.append(["!", "per second into"])
        commands.append(["to_resource", f"ResourceType:{self.to_resource.capitalize()}"])

        return commands

    async def on_command(self, entity: Entity, game: Game, key: str, value: str):
        await super().on_command(entity, game, key, value)

        if key == "from_resource":
            self.from_resource = resource_type_map[value]
            self.remainder = 0.0
        elif key == "to_resource":
            self.to_resource = resource_type_map[value]
            self.remainder = 0.0
        elif key == "rate":
            rate = int(value)
            if rate > self.maximum_rate or rate < 0:
                raise ClientError("invalid rate")
            self.current_rate = rate
            self.remainder = 0.0

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        if self.from_resource == ResourceType.Null or self.to_resource == ResourceType.Null:
            return False

        if self.current_rate == 0:
            return False

        goods_sold = self.current_rate
        value = goods_sold * resource_values[self.from_resource]
        goods_purchased_fractional = value / resource_values[self.to_resource] * self.efficiency + self.remainder
        goods_purchased = int(goods_purchased_fractional)
        self.remainder = goods_purchased_fractional - goods_purchased

        try:
            await game.spend([self.from_resource, goods_sold])
        except ClientError:
            return False

        await game.add_resource(self.to_resource, goods_purchased)
        return True

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            maximum_rate=data.pop("Rate"),
            efficiency=data.pop("Efficiency"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class AttackBehaviour(Behaviour):
    range: int = 1
    min_damage: float = 0.0
    max_damage: float = 0.0
    visual: str = ""
    manual_target: Optional[str] = None

    async def on_target(self, entity: Entity, game: Game, position: Position):
        await super().on_target(entity, game, position)

        self.manual_target = None

        target = game.map.get(position)
        if target is None:
            return

        if target.id == entity.id:
            return

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

    @classmethod
    def from_yaml(cls, data):
        min_damage, max_damage = data.pop("Damage")
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            min_damage=min_damage,
            max_damage=max_damage,
            range=data.pop("Range"),
            visual=data.pop("Visual"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class SummonBehaviour(Behaviour):
    unit: str

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        await game.add_entity(self.unit, game.empty_space_near(entity.position), entity.alignment)
        return True

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            unit=data.pop("Unit"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class StrengthBehaviour(Behaviour):
    strength: int


class SummonPoolBehaviour(StrengthBehaviour):
    units: dict[str, int]

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        remaining_strength = self.strength
        while remaining_strength > 0:
            options = [(unit, cost) for unit, cost in self.units.items() if cost < remaining_strength]
            if not options:
                break
            unit, cost = random.choice(options)
            remaining_strength -= cost
            await game.add_entity(unit, game.empty_space_near(entity.position), entity.alignment)
        return True

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            units=data.pop("Units"),
            strength=data.pop("Strength"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class EmpowerBehaviour(StrengthBehaviour):
    empowered_behaviour: str

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True



        empowered_behaviour = entity.behaviours_by_label.get(self.empowered_behaviour)
        if empowered_behaviour is None:
            return False
        if not isinstance(empowered_behaviour, StrengthBehaviour):
            return False

        empowered_behaviour.strength += self.strength
        return True

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            empowered_behaviour=data.pop("EmpoweredBehaviour"),
            strength=data.pop("Strength"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class PathingBehaviour(Behaviour):
    target_position: Optional[Position] = None
    path: list[Position] = Field(default_factory=list)

    async def on_target(self, entity: Entity, game: Game, position: Position):
        await super().on_target(entity, game, position)
        self.target_position = None

        if position not in game.map:
            self.target_position = position

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        # If we have a pre-calculated path, use that
        if self.path:
            next_position = self.path.pop()
            if next_position in game.map:
                self.path = []
            else:
                await game.move_entity(entity, next_position)
                return True

        # If we have a manually targeted position, move toward that
        if self.target_position is not None:
            if entity.position == self.target_position:
                self.target_position = None
            else:
                await self.move_toward(entity, game, self.target_position)
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


class WorkerBehaviour(PathingBehaviour):
    target_resource: Optional[Entity] = None
    carried_resource: ResourceType = ResourceType.Null
    carry_capacity: int = 25
    carry_amount: int = 0

    async def on_target(self, entity: Entity, game: Game, position: Position):
        await super().on_target(entity, game, position)
        self.target_resource = None

        target = game.map.get(position)
        if target is None or not (target.entity_tag & EntityTag.Resource):
            self.target_position = position
        else:
            self.target_resource = target

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        # If we're near the fortress and carrying resources, drop them off
        if entity.position.magnitude <= 2 and self.carried_resource != ResourceType.Null:
            task = game.add_resource(self.carried_resource, self.carry_amount)
            self.carry_amount = 0
            self.carried_resource = ResourceType.Null
            await task

        # If our inventory is full, path toward the fortress
        if self.carry_amount == self.carry_capacity:
            await self.move_toward(entity, game, Position(0, 0))
            return True

        if self.target_resource is not None:
            # If we're adjacent to the target resource, gather from it
            if entity.position.distance(self.target_resource.position) == 1:
                if self.carried_resource != self.target_resource.resource_type:
                    self.carry_amount = 0
                    self.carried_resource = self.target_resource.resource_type
                self.carry_amount += 5
            # Otherwise path toward our target resource
            else:
                await self.move_toward(entity, game, self.target_resource.position)
            return True
        else:
            return False

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            cooldown=data.pop("Cooldown"),
            carry_capacity=data.pop("Capacity"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class RepairBehaviour(Behaviour):
    amount: float = 1.0

    async def on_activate(self, entity: Entity, game: Game):
        if await super().on_activate(entity, game):
            return True

        for position in entity.position.neighbors:
            structure = game.map.get(position)
            if structure is None:
                continue
            if structure.alignment != entity.alignment:
                continue
            if not (structure.entity_tag & EntityTag.Structure):
                continue
            if structure.hp == structure.max_hp:
                continue
            await game.heal_entity(structure, self.amount)
            return True

        return False

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            amount=float(data.pop("Amount", 1.0)),
            cooldown=data.pop("Cooldown"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class SeekEnemyBehaviour(PathingBehaviour):
    ideal_distance: int = 1
    target_entity: Optional[str] = None

    async def on_target(self, entity: Entity, game: Game, position: Position):
        await super().on_target(entity, game, position)

        self.target_entity = None

        target = game.map.get(position)
        if target is not None:
            self.target_entity = target.id

    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        # Check for an enemy in vision range
        target_entity = game.entities.get(self.target_entity)
        if target_entity is not None:
            enemy = target_entity
        else:
            enemy = entity.find_enemy_nearby(game, entity.vision_size)
        if enemy is None:
            return False

        # If we're already in our target range, don't move
        if enemy.position.distance(entity.position) <= self.ideal_distance:
            return True

        # Move toward the target
        return await self.move_toward(entity, game, enemy.position)

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            ideal_distance=data.pop("Distance", 1),
            cooldown=data.pop("Cooldown"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


class SeekFortressBehaviour(SeekEnemyBehaviour):
    async def on_activate(self, entity: Entity, game: Game) -> bool:
        if await super().on_activate(entity, game):
            return True

        return await self.move_toward(entity, game, Position(0, 0))

    @classmethod
    def from_yaml(cls, data):
        result = cls(
            label=data.pop("Label", None),
            ideal_distance=data.pop("Distance", 1),
            cooldown=data.pop("Cooldown"),
        )
        if data:
            raise KeyError(f"unused behaviour keys: {list(data.keys())}")
        return result


behaviour_map = {
    "Attack": AttackBehaviour,
    "Summon": SummonBehaviour,
    "SummonPool": SummonPoolBehaviour,
    "Empower": EmpowerBehaviour,
    "Worker": WorkerBehaviour,
    "SeekFortress": SeekFortressBehaviour,
    "Transmute": TransmuteBehaviour,
    "Build": BuildBehaviour,
    "Train": TrainBehaviour,
    "Repair": RepairBehaviour,
    "Essential": EssentialBehaviour,
    "KillObjective": KillObjectiveBehaviour,
}


class Entity(BaseModel):
    id: str = Field(default_factory=generate_id)
    removed: bool = False
    template: bool = True
    entity_tag: int = 0
    resource_type: ResourceType = ResourceType.Null # Only used if entity_tag contains Resource
    position: Position = Field(default_factory=Position)
    name: str = "<Unknown>"
    hp: float = 0
    max_hp: float = 0
    alignment: Alignment = Alignment.Neutral
    vision_size: int = 10
    image: list[str] = Field(default_factory=list)
    tint: int = 0xFFFFFF # RBG tint
    size: int = 200 # Size of image in pixels
    behaviours: list[Behaviour] = Field(default_factory=list)
    behaviours_by_label: dict[str, Behaviour] = Field(default_factory=dict)
    death_visual: str = ""

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

    async def on_target(self, game: Game, position: Position):
        for behaviour in self.behaviours:
            await behaviour.on_target(self, game, position)
        await game.broadcast({
            "type": "entity/target",
            "source": self.id,
            "target": position.model_dump(mode="json"),
        })

    async def on_command(self, game: Game, key: str, value: str):
        for behaviour in self.behaviours:
            try:
                await behaviour.on_command(self, game, key, value)
            except (KeyError, ValueError, ClientError) as e:
                print(f"OnCommand Error: {type(e)} - {e}")

    async def on_heal(self, game: Game, amount: float):
        for behaviour in self.behaviours:
            await behaviour.on_heal(self, game, amount)

    def on_query(self, game: Game) -> list[tuple[str, str]]:
        commands = []
        for behaviour in self.behaviours:
            commands.extend(behaviour.on_query(self, game))
        return commands


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

    runtime: float = 0.0
    time_since_active: float = 0.0

    food: float = 1000.0
    gold: float = 1000.0
    stone: float = 1000.0
    wood: float = 1000.0
    aether: float = 1000.0

    revealed_area: GamePolygon = Field(default_factory=generate_starting_vision)

    async def end(self, success: bool, label: str):
        self.state = GameState.Finished
        await self.broadcast({"type": "game/end", "success": success, "label": label})

    def destroy(self):
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
                    self.destroy()
                return

        if not self.subscribers:
            self.inactive = True
            self.time_since_active = 0.0
            return

        if self.state == GameState.Active:
            await self.on_active_tick(delta)

    async def on_active_tick(self, delta: float):
        self.runtime += delta

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
        if serialized_entities:
            await self.broadcast({"type": "entity/update", "entities": serialized_entities})

    async def spend(self, *costs: tuple[ResourceType, int]):
        for resource_type, amount in costs:
            available = getattr(self, str(resource_type))
            if available < amount:
                raise ClientError(f"not enough {resource_type}")
        for resource_type, amount in costs:
            setattr(self, str(resource_type), getattr(self, str(resource_type)) - amount)
            await self.broadcast({"type": "resource", "resource_type": resource_type, "amount": -amount})

    async def add_resource(self, resource_type: ResourceType, amount: int):
        setattr(self, str(resource_type), getattr(self, str(resource_type)) + amount)
        await self.broadcast({"type": "resource", "resource_type": resource_type, "amount": amount})

    async def heal_entity(self, entity: Entity, amount: float):
        if entity.hp == entity.max_hp:
            return
        actual_amount = min(amount, entity.max_hp - entity.hp)
        entity.hp += actual_amount
        self.queue_update(entity)
        await entity.on_heal(self, actual_amount)

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

    async def place_fortress(self):
        fortress = await self.add_entity("Fortress", Position(0, 0), Alignment.Player)
        for position in Position(0,0).neighbors:
            self.map[position] = fortress

        for position in [Position(0, -3), Position(0, 3), Position(-3, 0), Position(3, 0), Position(3, -3), Position(-3, 3)]:
            await self.add_entity("Arrow Tower", position, Alignment.Player)

        spawn_points = self.generate_spawn_points()
        await self.add_entity("Portal", random.choice(spawn_points), Alignment.Enemy)

    async def generate_resources(self):
        for q in range(-100, 101):
            for r in range(-100, 101):
                position = Position(q, r)
                if position.s < -100 or position.s > 100:
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

    async def build_entity(self, builder: Entity, behaviour: BuildBehaviour, name: str, position: Position) -> Entity:
        if position in self.map:
            raise RuntimeError("attempted to add entity to occupied position")

        entity = Entity(
            template=False,
            image=["/images/symbols/construction.png"],
            size=150,
            tint=0x808080,
            entity_tag=EntityTag.Structure,
            name=f"<{name}>",
            position=position,
            hp=0.0,
            max_hp=behaviour.duration,
            alignment=builder.alignment,
            vision_size=1,
            behaviours=[
                UnderConstructionBehaviour(unit=name, costs=behaviour.costs, builder=builder),
            ],
            death_visual="Spell",
        )

        await self.on_new_entity(entity)
        return entity

    async def add_entity(self, name: str, position: Position, alignment: Alignment = Alignment.Neutral) -> Entity:
        if position in self.map:
            raise RuntimeError("attempted to add entity to occupied position")

        template = entity_templates[name]

        entity = template.model_copy(deep=True)
        entity.id = generate_id()
        entity.name = name
        entity.hp = entity.max_hp
        entity.position = position
        entity.alignment = alignment
        entity.template = False

        await self.on_new_entity(entity)
        return entity

    async def on_new_entity(self, entity: Entity):
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
            if behaviour.label:
                entity.behaviours_by_label[behaviour.label] = behaviour
        for behaviour in entity.behaviours:
            await behaviour.on_create(entity, self)

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
        entity.removed = True
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
        await self.broadcast({"type": "entity/remove", "id": entity.id, "visual": entity.death_visual})

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
    await game.place_fortress()
    await game.generate_resources()
    games[game.id] = game
    game.state = GameState.Active
    return game.model_dump()


@register("game/get")
async def handle_game_get(connection: Connection, request: GameRequest):
    return request.game.model_dump(mode="json")


@register("game/subscribe")
async def handle_game_subscribe(connection: Connection, request: GameRequest):
    request.game.subscribers.add(connection)

    return {"type": "success"}


class SetTargetRequest(GameRequest):
    selected: list[str]
    position: str


@register("game/target")
async def handle_set_target(connection: Connection, request: SetTargetRequest):
    if request.game.state != GameState.Active:
        return

    position = Position.from_string(request.position)

    for selected_id in request.selected:
        selected_entity = request.game.entities.get(selected_id)
        if selected_entity is None or selected_entity.alignment != Alignment.Player:
            continue
        await selected_entity.on_target(request.game, position)


class CommandRequest(GameRequest):
    target: str
    key: str
    value: str


@register("game/command")
async def handle_command(connection: Connection, request: CommandRequest):
    if request.game.state != GameState.Active:
        return

    target_entity = request.game.entities.get(request.target)
    if target_entity is None:
        return

    await target_entity.on_command(request.game, request.key, request.value)


class QueryRequest(GameRequest):
    target: str


@register("game/query")
async def handle_query(connection: Connection, request: QueryRequest):
    target_entity = request.game.entities.get(request.target)
    if target_entity is None:
        return {"error": "invalid entity id"}

    return {"commands": target_entity.on_query(request.game)}


entity_templates: dict[str, Entity] = {}


def load_entities():
    def apply_param(entity_data: dict, params: dict, yaml_key: str, param_key: str, validator: Callable):
        value = entity_data.pop(yaml_key, None)
        if value is None:
            return
        params[param_key] = validator(value)

    with open("/data/entities.yaml") as f:
        entity_collection: dict[str, dict] = yaml.safe_load(f)

    for name, entity_data in entity_collection.items():
        try:
            params = {}

            apply_param(entity_data, params, "HP", "max_hp", int)
            apply_param(entity_data, params, "Tint", "tint", int)
            apply_param(entity_data, params, "Size", "size", int)
            apply_param(entity_data, params, "DeathVisual", "death_visual", str)

            image = entity_data.pop("Image", None)
            if image:
                params["image"] = ["/images/entities" + src.strip() for src in image.split(",")]

            params["resource_type"] = resource_type_map[entity_data.pop("ResourceType", "")]

            entity_tag = 0
            for tag in entity_data.pop("Tags", []):
                entity_tag |= entity_tag_map[tag]
            params["entity_tag"] = entity_tag

            behaviours: list[Behaviour] = []
            for behaviour_data in entity_data.pop("Behaviours", []):
                behaviour_class: Type[Behaviour] = behaviour_map[behaviour_data.pop("Type")]
                behaviours.append(behaviour_class.from_yaml(behaviour_data))
            params["behaviours"] = behaviours

            if entity_data:
                raise KeyError(f"unused keys: {list(entity_data.keys())}")

            entity_templates[name] = Entity(**params)
        except BaseException as e:
            print(f'[!] Failed to load entity "{name}":')
            traceback.print_exception(e)


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
