import { Assets, Graphics, Text, Container, Sprite } from "pixi.js";
import { addOnTick, removeOnTick, state } from "./state.ts";
import { client } from "./api.ts";
import { Alignment, Entity, Game, Position, EntityTag, ResourceType } from "./models.ts";


const resourceTypes = [ResourceType.Food, ResourceType.Wood, ResourceType.Stone, ResourceType.Gold, ResourceType.Aether];


const resourceIcons = {
    [ResourceType.Wood]: "/wood.png",
    [ResourceType.Stone]: "/stone.png",
    [ResourceType.Gold]: "/gold.png",
    [ResourceType.Aether]: "/aether.png",
    [ResourceType.Food]: "/food.png",
};


const sprites: { [id: string]: [Container, SpriteData] } = {};


function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}


function moveSprite(sprite: Container, position: Position, durationMs: number) {
    const startX = sprite.x;
    const startY = sprite.y;
    const endX = position.x;
    const endY = position.y;
    let t = 0;
    const onTickId = addOnTick((elapsedMs) => {
        t += elapsedMs / durationMs;
        if (t >= 1) {
            sprite.x = endX;
            sprite.y = endY;
            removeOnTick(onTickId);
        } else {
            sprite.x = lerp(startX, endX, t);
            sprite.y = lerp(startY, endY, t);
        }
    })
}


function screenToWorldCoordinates(x: number, y: number): [number, number] {
    return [
        (x - state.camera.x) / (1.5 * state.camera.scale.x),
        (y - state.camera.y) / (1.5 * state.camera.scale.x)
    ];
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
        const spriteLabel = new Text();
        spriteLabel.style.fontSize = 32;
        spriteLabel.style.fill = "#ffffff";
        spriteLabel.style.stroke = "#000000";
        spriteLabel.text = data.label;
        spriteLabel.y = 102;
        spriteLabel.scale = 0.9 / state.camera.scale.x;
        spriteLabel.anchor.set(0.5, 0);
        spriteLabel.zIndex = 1;
        spriteContainer.addChild(spriteLabel);
        spriteLabel.visible = false;
        spriteLabel.label = "label";
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


function addToBoard(item: Container, position: Position) {
    item.x = position.x;
    item.y = position.y;
    state.camera.addChild(item);
}


async function onEntityCreate(game: Game, entity: Entity) {
    let sprite: Container;
    let data: SpriteData;

    let icon: string[] = ["/unknown.png"];
    let tint: number = 0xffffff;
    let size: number = 200;
    if (entity.image) {
        icon = entity.image.split(",");
        tint = entity.tint;
        size = entity.size;
    }

    if (entity.entityTag & (EntityTag.Unit|EntityTag.Structure)) {
        [sprite, data] = await makeSprite({ url: icon, tint, size, label: entity.name });
        sprite.eventMode = "dynamic";
        const spriteLabel = sprite.getChildByLabel("label");
        sprite.addEventListener("mouseenter", () => {
            spriteLabel.scale = 0.9 / state.camera.scale.x;
            spriteLabel.visible = true;
            sprite.addEventListener("mouseleave", () => {
                spriteLabel.visible = false;
            }, { once: true });
        });
    } else {
        [sprite, data] = await makeSprite({ url: icon, tint, size });
    }

    game.map[entity.position.toKey()] = entity;
    game.entities[entity.id] = entity;
    if (entity.entityTag & EntityTag.Unit) {
        game.units[entity.id] = entity;
        if (entity.alignment == Alignment.Enemy) {
            game.enemyCount += 1;
        }
    }
    if (entity.entityTag & EntityTag.Resource) {
        game.resources[entity.id] = entity;
    }
    if (entity.entityTag & EntityTag.Structure) {
        game.structures[entity.id] = entity;
    }

    sprites[entity.id] = [sprite, data];
    if (entity.maxHp != 0) {
        setHealthPercent(entity.id, entity.hp / entity.maxHp);
    }
    addToBoard(sprite, entity.position);
}


export async function activate(game_id: string) {
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

    let placingStructure: boolean = false;
    const buildBar = overlay.appendChild(document.createElement("div"));
    buildBar.classList.add("build-bar");

    const farmerButton = buildBar.appendChild(document.createElement("img"));
    farmerButton.src = "/farmer.png";
    farmerButton.classList.add("build-button");
    farmerButton.addEventListener("click", async () => {
        client.send({ "type": "game/train/worker", "game": game_id });
    });

    const arrowButton = buildBar.appendChild(document.createElement("img"));
    arrowButton.src = "/arrow-tower.png";
    arrowButton.classList.add("build-button");
    arrowButton.addEventListener("click", async startEv => {
        if (placingStructure) {
            return;
        }
        const controller = new AbortController();
        placingStructure = true;
        const [sprite, _] = await makeSprite({ url: "/arrow-tower.png" });
        sprite.alpha = 0.5;
        state.camera.addChild(sprite);
        sprite.x = startEv.clientX;
        sprite.y = startEv.clientY;
        state.app.canvas.addEventListener("mousemove", async moveEv => {
            const [x, y] = screenToWorldCoordinates(moveEv.clientX, moveEv.clientY);
            const hexPosition = Position.from_pixels(x, y);
            if (game.map[hexPosition.toKey()]) {
                sprite.tint = 0xff0000;
            }
            else {
                sprite.tint = 0xffffff;
            }
            sprite.x = hexPosition.x;
            sprite.y = hexPosition.y;
        }, { signal: controller.signal });

        state.app.canvas.addEventListener("click", async clickEv => {
            const [x, y] = screenToWorldCoordinates(clickEv.clientX, clickEv.clientY);
            const hexPosition = Position.from_pixels(x, y);
            if (game.map[hexPosition.toKey()]) {
                return;
            }

            sprite.removeFromParent();
            controller.abort();
            placingStructure = false;
            client.send({ "type": "game/build/arrow_tower", "game": game_id, "position": { q: hexPosition.q, r: hexPosition.r } });
        }, { signal: controller.signal });
    });

    state.camera.removeChildren();

    let game = await client.getGame(game_id);
    globalThis.game = game;

    game.reveal();

    const infoRegion = overlay.appendChild(document.createElement("div"));
    infoRegion.classList.add("info-region");
    const gameIdText = infoRegion.appendChild(document.createElement("div"));
    gameIdText.textContent = `Join ID: ${game.id}`;

    // Render the initial game state
    for (const entity of Object.values(game.entities)) {
        await onEntityCreate(game, entity);
    }

    for (const resourceType of resourceTypes) {
        resourceAmounts[resourceType].textContent = game[resourceType];
    }

    // Subscribe to game updates
    await client.subscribeToGame(game_id);
    client.subscribe("connect", async () => {
        await client.subscribeToGame(game_id);
    });

    client.subscribe("entity/add", async data => {
        const entity = new Entity(data.entity);
        await onEntityCreate(game, entity);
    });

    client.subscribe("entity/update", async data => {
        for (const entityUpdate of data.entities) {
            const entity = game.entities[entityUpdate.id];
            if (!entity) {
                return;
            }

            // Update map
            const oldPosition = entity.position;
            entity.update(entityUpdate);

            // Move entity
            if (!entity.position.equals(oldPosition)) {
                delete game.map[oldPosition.toKey()];
                game.map[entity.position.toKey()] = entity;

                // Move sprite
                if (sprites[entity.id]) {
                    const [sprite, _] = sprites[entity.id];
                    moveSprite(sprite, entity.position, 300);
                }
            }

            if (entity.maxHp != 0) {
                setHealthPercent(entity.id, entity.hp / entity.maxHp);
            }
        }
    });

    client.subscribe("entity/attack", async data => {
        const source = game.entities[data.source];
        const target = game.entities[data.target];
        if (source && target) {
            let target_x: number;
            let target_y: number;
            if (!sprites[target.id]) {
                target_x = target.position.x;
                target_y = target.position.y;
            }
            else {
                const [sprite, _] = sprites[data.target];
                target_x = sprite.x;
                target_y = sprite.y;
            }
            const attack = new Graphics();
            attack.moveTo(source.position.x, source.position.y);
            attack.lineTo(target_x, target_y);
            attack.stroke({ color: "#0060ff", width: 4 });
            state.camera.addChild(attack);
            setTimeout(() => {
                attack.removeFromParent();
            }, 100);
        }
    });

    client.subscribe("entity/remove", async data => {
        const entity = game.entities[data.id];

        delete game.entities[data.id];
        delete game.units[data.id];
        delete game.resources[data.id];
        delete game.structures[data.id];

        if (!entity) {
            return;
        }
        delete game.map[entity.position.toKey()];

        if (entity.entityTag & EntityTag.Unit && entity.alignment == Alignment.Enemy) {
            game.enemyCount -= 1;
        }

        if (sprites[data.id]) {
            const [sprite, _] = sprites[data.id];
            delete sprites[data.id];
            setTimeout(() => {
                sprite.removeFromParent();
            }, 100);
        }
    });

    client.subscribe("reveal", async data => {
        game.revealedArea = data.area;
        game.reveal();
    });

    client.subscribe("resource", async data => {
        game[data.resource_type] += data.amount;
        resourceAmounts[data.resource_type].textContent = game[data.resource_type];
    });
}
