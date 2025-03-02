import { state } from "./state.ts";


export enum Permission {
    Basic = 0,
    Subscriber = 1,
    VIP = 2,
    Moderator = 3,
    Broadcaster = 4,
}


export enum UnitType {
    Null = "",

    Miner = "miner",
    Farmer = "farmer",
    Lumberjack = "lumberjack",
    Enchanter = "enchanter",
    Builder = "builder",
    Militia = "militia",
    Merchant = "merchant",
    Scout = "scout",

    Voidling = "voidling",
}


export enum ResourceType {
    Null = "",
    Food = "food",
    Gold = "gold",
    Stone = "stone",
    Wood = "wood",
    Aether = "aether",
}


export enum GameState {
    Lobby = 0,
}


export class DatabaseEntry {
    id: string;

    constructor(data) {
        this.id = data.id;
    }
}


export class User extends DatabaseEntry {
    token: string;
    name: string;
    linked_channels: { [id: string]: Permission };
    link_code: string;

    constructor(data) {
        super(data);
        this.token = data.token;
        this.name = data.name;
        this.linked_channels = data.linked_channels;
        this.link_code = data.link_code;
    }
}


export class Channel extends DatabaseEntry {
    twitch_id: string;
    name: string;
    linked_users: { [id: string]: Permission };

    constructor(data) {
        super(data);
        this.twitch_id = data.twitch_id;
        this.name = data.name;
        this.linked_users = data.linked_users;
    }
}


export class Position {
    q: number;
    r: number;

    constructor(data) {
        this.q = data.q;
        this.r = data.r;
    }

    get s() {
        return -this.q - this.r;
    }

    get x() {
        return state.gridSize * 1.5 * (Math.sqrt(3) * this.q + Math.sqrt(3) / 2 * this.r);
    }

    get y() {
        return state.gridSize * 1.5 * (3 / 2 * this.r);
    }

    toKey() {
        return `${this.q},${this.r}`;
    }

    get neighbors() {
        return [
            new Position({ q: this.q, r: this.r - 1 }),
            new Position({ q: this.q + 1, r: this.r - 1 }),
            new Position({ q: this.q + 1, r: this.r }),
            new Position({ q: this.q, r: this.r + 1 }),
            new Position({ q: this.q - 1, r: this.r + 1 }),
            new Position({ q: this.q - 1, r: this.r }),
        ]
    }

    public static from_floats(q: number, r: number): Position {
        const q_grid = Math.round(q);
        const r_grid = Math.round(r);
        q -= q_grid;
        r -= r_grid;
        if (Math.abs(q) >= Math.abs(r)) {
            return new Position({ q: q_grid + Math.round(q + 0.5 * r), r: r_grid });
        }
        else {
            return new Position({ q: q_grid, r: r_grid + Math.round(r + 0.5 * q) });
        }
    }

    public static from_pixels(x: number, y: number): Position {
        return Position.from_floats(
            (Math.sqrt(3) / 3 * x - 1 / 3 * y) / state.gridSize,
            (2 / 3 * y) / state.gridSize
        )
    }
}


export enum TaskType {
    Move = 0,
    Gather = 1,
    Build = 2,
}


export class Task {
    task_type: TaskType;
    target: Position;

    constructor(data) {
        this.task_type = data.task_type;
        this.target = data.target;
    }
}


export enum StructureType {
    Null = "",
    TownHall = "town_hall",
    ArrowTower = "arrow_tower",
}


export enum EntityType {
    Unit = "unit",
    Resource = "resource",
    Structure = "structure",
}


export enum Alignment {
    Neutral = 0,
    Player = 1,
    Enemy = 2,
}


export class Entity {
    entity_type: EntityType;
    id: string;
    name: string;
    position: Position;
    hp: number;
    max_hp: number;
    image?: string;
    alignment: Alignment;

    unit_type: UnitType;
    tasks: Task[];
    gathering_rate: number;
    carried_resource: ResourceType;
    carry_amount: number;
    carry_capacity: number;

    structure_type: StructureType;

    resource_type: ResourceType;

    constructor(data) {
        this.entity_type = data.entity_type;
        this.id = data.id;
        this.name = data.name;
        this.position = new Position(data.position);
        this.unit_type = data.unit_type;
        this.gathering_rate = data.gathering_rate;
        this.resource_type = data.resource_type;
        this.tasks = [];
        for (const task of data.tasks) {
            this.tasks.push(new Task(task));
        }
        this.carried_resource = data.carried_resource;
        this.carry_amount = data.carry_amount;
        this.carry_capacity = data.carry_capacity;
        this.hp = data.hp;
        this.max_hp = data.max_hp;
        this.structure_type = data.structure_type;
        this.image = data.image;
        this.alignment = data.alignment;
    }
}


export class Game {
    id: string;
    player: string;
    state: GameState;
    entities: { [id: string]: Entity };
    resources: { [id: string]: Entity };
    structures: { [id: string]: Entity };
    units: { [id: string]: Entity };

    map: { [position: string]: Entity };
    spawn_points: Position[];
    enemyCount: number;

    food: number;
    gold: number;
    stone: number;
    wood: number;
    aether: number;

    constructor(data) {
        this.id = data.id;
        this.player = data.player;
        this.state = data.state;
        this.entities = {};
        this.resources = {};
        this.structures = {};
        this.units = {};
        this.map = {};
        this.enemyCount = 0;
        for (const [entityId, rawEntity] of Object.entries(data.entities)) {
            const entity = new Entity(rawEntity);
            this.map[entity.position.toKey()] = entity;
            this.entities[entityId] = entity;
            if (entity.entity_type == EntityType.Unit) {
                this.units[entityId] = entity;
                if (entity.alignment == Alignment.Enemy) {
                    this.enemyCount += 1;
                }
            }
            else if (entity.entity_type == EntityType.Resource) {
                this.resources[entityId] = entity;
            }
            else if (entity.entity_type == EntityType.Structure) {
                this.structures[entityId] = entity;
            }
        }
        const origin = new Position({ q: 0, r: 0 });
        for (const neighbor of origin.neighbors) {
            this.map[neighbor.toKey()] = this.map[origin.toKey()];
        }
        this.food = data.food;
        this.gold = data.gold;
        this.stone = data.stone;
        this.wood = data.wood;
        this.aether = data.aether;
        this.spawn_points = data.spawn_points;
    }
}
