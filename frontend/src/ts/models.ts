import { Container } from "pixi.js";
import { state } from "./state.ts";


export enum ResourceType {
    Null = "",
    Food = "food",
    Gold = "gold",
    Stone = "stone",
    Wood = "wood",
    Aether = "aether",
}


export enum GameState {
    Lobby = "lobby",
    Active = "active",
}


export enum EntityTag {
    Unit = 1,
    Resource = 2,
    Structure = 4,
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
    linkCode: string;

    constructor(data) {
        super(data);
        this.token = data.token;
        this.name = data.name;
        this.linkCode = data.link_code;
    }
}


export class Position {
    q: number;
    r: number;

    constructor(data) {
        this.q = data.q;
        this.r = data.r;
    }

    equals(otherPosition: Position): boolean {
        return this.q == otherPosition.q && this.r == otherPosition.r;
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


export enum Alignment {
    Enemy = 0,
    Neutral = 1,
    Player = 2,
}


export class Entity {
    id: string;
    template: boolean;
    entityTag: EntityTag;
    resourceType: ResourceType;
    position: Position;
    name: string;
    hp: number;
    maxHp: number;
    alignment: Alignment;
    visionSize: number;
    image?: string;
    tint: number;
    size: number;

    // Local Data
    sprite: Container;

    constructor(data) {
        this.id = data.id;
        this.template = data.template;
        this.entityTag = data.entity_tag;
        this.position = new Position(data.position);
        this.name = data.name;
        this.hp = data.hp;
        this.maxHp = data.max_hp;
        this.alignment = data.alignment;
        this.visionSize = data.vision_size;
        this.image = data.image;
        this.tint = data.tint;
        this.size = data.size;
        this.sprite = null;
    }

    update(data) {
        if (this.id !== data.id) {
            throw Error("entity update IDs did not match");
        }
        this.template = data.template;
        this.entityTag = data.entity_tag;
        this.position = new Position(data.position);
        this.name = data.name;
        this.hp = data.hp;
        this.maxHp = data.max_hp;
        this.alignment = data.alignment;
        this.visionSize = data.vision_size;
        this.image = data.image;
        this.tint = data.tint;
        this.size = data.size;
    }
}


export class Game {
    id: string;
    owner: string;
    inactive: boolean;
    state: GameState;
    entities: { [id: string]: Entity };
    resources: { [id: string]: Entity };
    structures: { [id: string]: Entity };
    units: { [id: string]: Entity };
    map: { [position: string]: Entity };
    enemyCount: number;
    revealedArea: any[];

    selected: Set<string>;

    food: number;
    gold: number;
    stone: number;
    wood: number;
    aether: number;

    constructor(data) {
        this.id = data.id;
        this.owner = data.owner;
        this.inactive = data.inactive;
        this.state = data.state;
        this.entities = {};
        this.resources = {};
        this.structures = {};
        this.units = {};
        this.map = {};
        this.enemyCount = 0;
        for (const [entityId, rawEntity] of Object.entries(data.entities)) {
            const entity = new Entity(rawEntity);
            this.entities[entityId] = entity;
            this.map[entity.position.toKey()] = entity;
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
        this.revealedArea = data.revealed_area;
        this.selected = new Set();
    }

    reveal() {
        const positions = [];
        for (const point of this.revealedArea[0]) {
            positions.push({x: point[0], y: point[1]});
        }
        state.mask.clear();
        state.mask.poly(positions);
        state.mask.fill({color: "#ffffff"});
    }
}
