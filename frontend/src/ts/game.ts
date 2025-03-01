import { Assets, Graphics, Text, Container, Sprite } from "pixi.js";
import { state } from "./state.ts";
import { client } from "./api.ts";
import { Entity, Game, Position, ResourceType, StructureType } from "./models.ts";


async function makeSprite(url: string | string[], tint: number | number[] = null, size: number = null, mask: Container = null, label: string = null): Promise<Container> {
    const spriteContainer = new Container();

    if (mask) {
        spriteContainer.addChild(mask);
    }

    if (!size) {
        size = 200;
    }

    let tint_array: number[];
    if (tint) {
        if (Array.isArray(tint)) {
            tint_array = tint;
        }
        else {
            tint_array = [tint];
        }
    }

    let url_array: string[];
    if (Array.isArray(url)) {
        url_array = url;
    }
    else {
        url_array = [url];
    }

    let workingSize = size;
    for (const [index, url] of url_array.entries()) {
        const texture = await Assets.load(url)
        const sprite = Sprite.from(texture);
        sprite.width = workingSize;
        sprite.height = workingSize;
        sprite.anchor = 0.5;
        spriteContainer.addChild(sprite);
        workingSize *= 0.75;

        if (tint) {
            sprite.tint = tint_array[index % tint_array.length];
        }

        if (mask) {
            sprite.mask = mask;
        }
    }

    if (label) {
        const text = new Text();
        text.style.fontSize = 32;
        text.style.fill = "#ffffff";
        text.style.stroke = "#000000";
        text.text = label;
        text.y = 102;
        text.scale = 0.9 / state.camera.scale.x;
        text.anchor.set(0.5, 0);
        spriteContainer.addChild(text);
        text.visible = false;
        text.label = "label";
    }

    return spriteContainer;
}


const entities: { [id: string]: Entity } = {};
const sprites: { [id: string]: Container } = {};


function addToBoard(item: Container, position: Position) {
    item.x = position.x;
    item.y = position.y;
    state.camera.addChild(item);
}


async function handleEntityCreate(entity: Entity) {
    let sprite: Container;
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
        sprite = await makeSprite(icon, tint);
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
        sprite = await makeSprite(icon, tint, size);
    }
    else if (entity.entity_type == "worker") {
        let icon: string = "/unknown.png";
        if (entity.image) {
            icon = entity.image;
        }
        const spriteMask = new Graphics();
        spriteMask.circle(0, 0, 100);
        spriteMask.fill(0xffffff);
        sprite = await makeSprite(icon, null, 200, spriteMask, entity.name);
        sprite.eventMode = "dynamic";
        const spriteLabel = sprite.getChildByLabel("label");
        sprite.addEventListener("mouseenter", () => {
            spriteLabel.visible = true;
            sprite.addEventListener("mouseleave", () => {
                spriteLabel.visible = false;
            }, { once: true });
        });
    }
    else {
        return;
    }
    sprites[entity.id] = sprite;
    entities[entity.id] = entity;
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
        const entity = entities[data.id];
        const sprite = sprites[data.id];
        if (!entity) {
            return;
        }
        entity.position = new Position(data.position);
        sprite.x = entity.position.x;
        sprite.y = entity.position.y;
    });

    client.subscribe("resource", async data => {
        console.log(data);
        game[data.resource_type] += data.amount;
        resourceAmounts[data.resource_type].textContent = game[data.resource_type];
    });
}
