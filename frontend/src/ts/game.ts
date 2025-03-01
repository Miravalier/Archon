import { Assets, Graphics, Text, Container, Sprite, Ticker } from "pixi.js";
import { state } from "./state.ts";
import { client } from "./api.ts";
import { Entity, Game, Position, ResourceType, StructureType } from "./models.ts";


function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}

interface SpriteData {
    url: string | string[];
    tint?: number | number[];
    size?: number;
    mask?: Container;
    label?: string;
}


async function makeSprite(data: SpriteData): Promise<[Container, SpriteData]> {
    const spriteContainer = new Container();

    if (data.mask) {
        spriteContainer.addChild(data.mask);
    }

    if (!data.size) {
        data.size = 200;
    }

    let tint_array: number[];
    if (data.tint) {
        if (Array.isArray(data.tint)) {
            tint_array = data.tint;
        }
        else {
            tint_array = [data.tint];
        }
    }

    let url_array: string[];
    if (Array.isArray(data.url)) {
        url_array = data.url;
    }
    else {
        url_array = [data.url];
    }

    let workingSize = data.size;
    for (const [index, url] of url_array.entries()) {
        const texture = await Assets.load(url)
        const sprite = Sprite.from(texture);
        sprite.width = workingSize;
        sprite.height = workingSize;
        sprite.anchor = 0.5;
        spriteContainer.addChild(sprite);
        workingSize *= 0.75;

        if (data.tint) {
            sprite.tint = tint_array[index % tint_array.length];
        }

        if (data.mask) {
            sprite.mask = data.mask;
        }
    }

    if (data.label) {
        const text = new Text();
        text.style.fontSize = 32;
        text.style.fill = "#ffffff";
        text.style.stroke = "#000000";
        text.text = data.label;
        text.y = 102;
        text.scale = 0.9 / state.camera.scale.x;
        text.anchor.set(0.5, 0);
        spriteContainer.addChild(text);
        text.visible = false;
        text.label = "label";
    }

    const hpBackground = new Graphics();
    hpBackground.visible = false;
    hpBackground.roundRect(-data.size / 2, -data.size / 2 - 8, data.size, 16, 4);
    hpBackground.fill({ color: "#404040" })
    hpBackground.stroke({ color: "#000000", width: 4 });
    hpBackground.label = "hpBackground";
    spriteContainer.addChild(hpBackground);

    const hpFill = new Graphics();
    hpFill.label = "hpFill";
    spriteContainer.addChild(hpFill);

    return [spriteContainer, data];
}


function setHealthPercent(id: string, hpPercent: number) {
    if (!sprites[id]) {
        return;
    }

    const [sprite, data] = sprites[id];

    const hpBackground = sprite.getChildByLabel("hpBackground") as Graphics;
    hpBackground.visible = true;

    const hpBar = sprite.getChildByLabel("hpFill") as Graphics;
    hpBar.clear();
    hpBar.roundRect(-data.size / 2 + 2, -data.size / 2 - 6, (data.size - 4) * hpPercent, 12, 2);
    hpBar.fill({ color: "#aa2020" });
}


const entities: { [id: string]: Entity } = {};
const sprites: { [id: string]: [Container, SpriteData] } = {};


function addToBoard(item: Container, position: Position) {
    item.x = position.x;
    item.y = position.y;
    state.camera.addChild(item);
}


async function handleEntityCreate(entity: Entity) {
    let sprite: Container;
    let data: SpriteData;
    let hpVisible: boolean = false;
    if (entity.entity_type == "resource") {
        let icon: string = "/unknown.png";
        let tint: number = 0xffffff;
        if (entity.resource_type == ResourceType.Food) {
            icon = "/wheat.png";
            tint = 0xffff00;
        }
        else if (entity.resource_type == ResourceType.Wood) {
            icon = "/forest.png";
            tint = 0x40a010;
        }
        else if (entity.resource_type == ResourceType.Stone) {
            icon = "/rock.png";
            tint = 0x808080;
        }
        [sprite, data] = await makeSprite({ url: icon, tint });
    }
    else if (entity.entity_type == "structure") {
        let icon: string | string[] = "/unknown.png";
        let tint: number | number[] = 0xffffff;
        let size: number = 200;
        if (entity.structure_type == StructureType.TownHall) {
            icon = "/castle.png";
            size = 500;
        }
        if (entity.structure_type == StructureType.ArrowTower) {
            icon = ["/tower.png", "/arrow-tower.png"];
            tint = [0xffffff, 0x00a0ff];
        }
        [sprite, data] = await makeSprite({ url: icon, tint, size });
        hpVisible = true;
    }
    else if (entity.entity_type == "worker") {
        let icon: string = "/unknown.png";
        if (entity.image) {
            icon = entity.image;
        }
        const spriteMask = new Graphics();
        spriteMask.circle(0, 0, 100);
        spriteMask.fill(0xffffff);
        [sprite, data] = await makeSprite({ url: icon, mask: spriteMask, label: entity.name });
        sprite.eventMode = "dynamic";
        const spriteLabel = sprite.getChildByLabel("label");
        sprite.addEventListener("mouseenter", () => {
            spriteLabel.visible = true;
            sprite.addEventListener("mouseleave", () => {
                spriteLabel.visible = false;
            }, { once: true });
        });
        hpVisible = true;
    }
    else {
        return;
    }
    sprites[entity.id] = [sprite, data];
    entities[entity.id] = entity;
    if (hpVisible) {
        setHealthPercent(entity.id, entity.hp / entity.max_hp);
    }
    addToBoard(sprite, entity.position);
}


const resourceTypes = [ResourceType.Food, ResourceType.Wood, ResourceType.Stone, ResourceType.Gold, ResourceType.Aether];


const resourceIcons = {
    [ResourceType.Wood]: "/wood.png",
    [ResourceType.Stone]: "/stone.png",
    [ResourceType.Gold]: "/gold.png",
    [ResourceType.Aether]: "/aether.png",
    [ResourceType.Food]: "/food.png",
};


const validCommands = [
    "!join",
    "!job builder",
    "!job farmer",
    "!job lumberjack",
    "!job miner",
];


export async function activate(channel_id: string) {
    console.log("[!] Game View Page");

    const canvas = document.querySelector("canvas");
    canvas.classList.remove("disabled");

    const overlay = document.querySelector("#overlay");
    overlay.innerHTML = "";

    const resourceBar = overlay.appendChild(document.createElement("div"));
    resourceBar.classList.add("resource-bar");

    const resourceAmounts: { [resourceType: string]: HTMLDivElement } = {};
    for (const resourceType of resourceTypes) {
        const resource = resourceBar.appendChild(document.createElement("div"));
        resource.classList.add("resource");
        const resourceIcon = resource.appendChild(document.createElement("img"));
        resourceIcon.classList.add("icon");
        resourceIcon.src = resourceIcons[resourceType];

        const resourceAmount = resource.appendChild(document.createElement("div"));
        resourceAmount.classList.add("amount");
        resourceAmounts[resourceType] = resourceAmount;
    }

    const commandsBar = overlay.appendChild(document.createElement("div"));
    commandsBar.classList.add("commands-bar");
    for (const validCommand of validCommands) {
        const commandText = commandsBar.appendChild(document.createElement("div"));
        commandText.classList.add("command");
        commandText.textContent = validCommand;
    }

    state.camera.removeChildren();

    let game: Game;
    try {
        game = await client.getGame(channel_id);
    } catch (e) {
        game = await client.createGame(channel_id);
    }

    // Render the initial game state
    for (const entity of Object.values(game.entities)) {
        handleEntityCreate(entity);
    }

    for (const resourceType of resourceTypes) {
        resourceAmounts[resourceType].textContent = game[resourceType];
    }

    // Subscribe to game updates
    await client.subscribeToGame(channel_id);
    client.subscribe("connect", async () => {
        await client.subscribeToGame(channel_id);
    });

    client.subscribe("entity/add", async data => {
        handleEntityCreate(new Entity(data.entity));
    });

    client.subscribe("entity/move", async data => {
        if (!entities[data.id]) {
            return;
        }
        const entity = entities[data.id];
        entity.position = new Position(data.position);

        if (!sprites[data.id]) {
            return;
        }
        const [sprite, _] = sprites[data.id];
        const startX = sprite.x;
        const startY = sprite.y;
        const endX = entity.position.x;
        const endY = entity.position.y;
        const durationMs = 300;
        let t = 0;
        const moveHandler = (ticker: Ticker) => {
            t += ticker.elapsedMS / durationMs;
            if (t >= 1) {
                sprite.x = endX;
                sprite.y = endY;
                ticker.remove(moveHandler);
            }
            else {
                sprite.x = lerp(startX, endX, t);
                sprite.y = lerp(startY, endY, t);
            }
        }
        state.app.ticker.add(moveHandler);
    });

    client.subscribe("entity/remove", async data => {
        if (entities[data.id]) {
            delete entities[data.id];
        }

        if (sprites[data.id]) {
            const [sprite, _] = sprites[data.id];
            sprite.removeFromParent();
            delete sprites[data.id];
        }
    });

    client.subscribe("resource", async data => {
        game[data.resource_type] += data.amount;
        resourceAmounts[data.resource_type].textContent = game[data.resource_type];
    });
}
