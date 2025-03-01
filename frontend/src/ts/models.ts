import { state } from "./state.ts";


export enum Permission {
    Basic = 0,
    Subscriber = 1,
    VIP = 2,
    Moderator = 3,
    Broadcaster = 4,
}


export enum Job {
    Miner = "miner",
    Farmer = "farmer",
    Lumberjack = "lumberjack",
    Enchanter = "enchanter",
    Builder = "builder",
    Militia = "militia",
    Merchant = "merchant",
    Scout = "scout",
}


export enum ResourceType {
    Invalid = "",
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
    Invalid = "",
    TownHall = "town_hall",
    ArrowTower = "arrow_tower",
}


export class Entity {
    entity_type: string;
    id: string;
    name: string;
    position: Position;
    hp: number;
    max_hp: number;
    image?: string;

    tasks: Task[];
    job: Job;
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
        this.job = data.job;
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
    }
}


export class Game {
    id: string;
    player: string;
    state: GameState;
    entities: { [id: string]: Entity };
    structures: { [id: string]: Entity };
    workers: { [id: string]: Entity };

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
        for (const [entityId, entity] of Object.entries(data.entities)) {
            this.entities[entityId] = new Entity(entity);
        }
        this.structures = {};
        for (const entityId of Object.keys(data.structures)) {
            this.structures[entityId] = this.entities[entityId];
        }
        this.workers = {};
        for (const entityId of Object.keys(data.workers)) {
            this.workers[entityId] = this.entities[entityId];
        }
        this.food = data.food;
        this.gold = data.gold;
        this.stone = data.stone;
        this.wood = data.wood;
        this.aether = data.aether;
    }
}
