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


export enum GameState {
    Lobby = 0,
}


export interface DatabaseEntry {
    id: string;
}


export interface User extends DatabaseEntry {
    token: string;
    name: string;
    linked_channels: { [id: string]: Permission };
    link_code: string;
}


export interface Channel extends DatabaseEntry {
    twitch_id: string;
    name: string;
    linked_users: { [id: string]: Permission };
}


export interface Position {
    q: number;
    r: number;
}


export interface Entity {
    entity_type: string;
    id: string;
    name: string;
    position: Position;
}


export interface Worker extends Entity {
    entity_type: 'worker';
    job: Job;
    gathering_rate: number;
}


export interface Game {
    id: string;
    player: string;
    state: GameState;
    entities: { [id: string]: Entity };

    food: number;
    gold: number;
    stone: number;
    wood: number;
    aether: number;
}
