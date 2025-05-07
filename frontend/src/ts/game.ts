import { Assets, Graphics, Text, Container, Sprite } from "pixi.js";
import { addOnTick, removeOnTick, state } from "./state.ts";
import { client } from "./api.ts";
import { Alignment, Entity, Game, Position, EntityTag, ResourceType } from "./models.ts";
import { GlowFilter } from "pixi-filters";
import { Future } from "./async.ts";


const resourceTypes = [ResourceType.Food, ResourceType.Wood, ResourceType.Stone, ResourceType.Gold, ResourceType.Aether];


const resourceIcons = {
    [ResourceType.Wood]: "/wood.png",
    [ResourceType.Stone]: "/stone.png",
    [ResourceType.Gold]: "/gold.png",
    [ResourceType.Aether]: "/aether.png",
    [ResourceType.Food]: "/food.png",
};


function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}


function onMoveEntity(entity: Entity, durationMs: number) {
    if (!entity.sprite) {
        return;
    }

    const startX = entity.sprite.x;
    const startY = entity.sprite.y;
    const endX = entity.position.x;
    const endY = entity.position.y;
    let t = 0;
    addOnTick(entity.id, (elapsedMs) => {
        t += elapsedMs / durationMs;
        if (t >= 1) {
            entity.sprite.x = endX;
            entity.sprite.y = endY;
            removeOnTick(entity.id);
        } else {
            entity.sprite.x = lerp(startX, endX, t);
            entity.sprite.y = lerp(startY, endY, t);
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


const pixiObjectGraveyard: {[templateId: string]: any[]} = {};


function makeGraphics(): Graphics {
    const graveyardArray = pixiObjectGraveyard["<graphics>"];
    if (graveyardArray && graveyardArray.length != 0) {
        const graphics = graveyardArray.pop() as Graphics;
        graphics.clear();
        return graphics;
    }

    return new Graphics();
}


function destroyGraphics(graphics: Graphics) {
    graphics.removeFromParent();
    graphics.removeAllListeners();
    let graveyardArray = pixiObjectGraveyard["<graphics>"];
    if (!graveyardArray) {
        graveyardArray = [];
        pixiObjectGraveyard["<graphics>"] = graveyardArray;
    }
    graveyardArray.push(graphics);
}


function destroySprite(templateId: string, sprite: Container) {
    sprite.removeFromParent();
    sprite.removeAllListeners();
    let graveyardArray = pixiObjectGraveyard[templateId];
    if (!graveyardArray) {
        graveyardArray = [];
        pixiObjectGraveyard[templateId] = graveyardArray;
    }
    graveyardArray.push(sprite);
}


async function makeSprite(templateId: string, data: SpriteData): Promise<Container> {
    const graveyardArray = pixiObjectGraveyard[templateId];
    if (graveyardArray && graveyardArray.length != 0) {
        return graveyardArray.pop();
    }

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
        spriteLabel.style.stroke = {
            color: "#000000",
            width: 4,
        };
        spriteLabel.text = data.label;
        spriteLabel.y = data.size/2;
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

    return spriteContainer;
}


function setHealthPercent(entity: Entity) {
    if (!entity.sprite) {
        return;
    }

    const sprite = entity.sprite;
    const hpPercent = entity.hp / entity.maxHp;

    const hpBar = sprite.getChildByLabel("hpFill") as Graphics;
    hpBar.clear();
    hpBar.roundRect(-entity.size / 2 + 2, -entity.size / 2 - 6, (entity.size - 4) * hpPercent, 12, 2);
    hpBar.fill({ color: "#aa2020" });
}


let selectingLocation: boolean = false;
let selectingLocationController: AbortController = null;
let selectingSpriteId: string = null;
let selectingLocationSprite: Container = null;
let lastSelectedLocation: Position = null;
let selectingLocationCancelled: boolean = false;

async function selectLocation(game: Game, icon: string): Promise<Position> {
    if (selectingLocation) {
        return null;
    }

    const future = new Future<Position>();
    const controller = new AbortController();
    controller.signal.addEventListener("abort", () => {
        if (selectingLocationCancelled) {
            future.resolve(null);
        } else {
            future.resolve(lastSelectedLocation);
        }
        destroySprite(selectingSpriteId, selectingLocationSprite);

        selectingLocation = false;
        selectingLocationController = null;
        selectingSpriteId = null;
        selectingLocationSprite = null;
        lastSelectedLocation = null;
    });

    selectingLocation = true;
    selectingLocationController = controller;
    selectingSpriteId = `select-icon:${icon}`;
    selectingLocationSprite = await makeSprite(selectingSpriteId, { url: icon });
    lastSelectedLocation = null;
    selectingLocationCancelled = false;

    const sprite = selectingLocationSprite;
    sprite.alpha = 0.5;
    state.camera.addChild(sprite);
    state.app.canvas.addEventListener("mousemove", async moveEv => {
        const [x, y] = screenToWorldCoordinates(moveEv.clientX, moveEv.clientY);
        const hexPosition = Position.fromPixels(x, y);

        if (game.map[hexPosition.toString()]) {
            sprite.tint = 0xff0000;
            lastSelectedLocation = null;
        }
        else {
            sprite.tint = 0xffffff;
            lastSelectedLocation = hexPosition;
        }
        sprite.x = hexPosition.x;
        sprite.y = hexPosition.y;
    }, { signal: controller.signal });

    return await future;
}


async function showCommandPanel(game: Game, entity: Entity) {
    const actionBar = document.getElementById("action-bar") as HTMLDivElement;
    actionBar.innerHTML = "";
    actionBar.classList.remove("disabled");

    const buttonRow = actionBar.appendChild(document.createElement("div"));
    buttonRow.classList.add("button-row");

    const inputRow = actionBar.appendChild(document.createElement("div"));
    inputRow.classList.add("input-row");

    const response = await client.send({ "type": "game/query", "game": game.id, "target": entity.id });
    for (const [key, value] of response.commands) {
        if (key == "!") {
            const labelElement = inputRow.appendChild(document.createElement("div"));
            labelElement.classList.add("label");
            labelElement.textContent = value;
            continue;
        }

        const [valueType, ...args] = value.split(":");
        if (valueType == "Button") {
            const [icon, selectPosition] = args;

            const buttonElement = buttonRow.appendChild(document.createElement("img"));
            buttonElement.src = icon;
            buttonElement.classList.add("action-button");
            buttonElement.addEventListener("click", async () => {
                if (selectPosition == "True") {
                    const position = await selectLocation(game, icon);
                    if (position) {
                        client.send({
                            "type": "game/command",
                            "game": game.id,
                            "target": entity.id,
                            "key": key,
                            "value": position.toString(),
                        });
                    }
                } else {
                    client.send({
                        "type": "game/command",
                        "game": game.id,
                        "target": entity.id,
                        "key": key,
                        "value": "",
                    });
                }
            });
        } else if (valueType == "ResourceType") {
            const [currentValue,] = args;
            const selectElement = inputRow.appendChild(document.createElement("select"));
            selectElement.innerHTML = `
                <option value="">Null</option>
                <option value="Food">Food</option>
                <option value="Gold">Gold</option>
                <option value="Stone">Stone</option>
                <option value="Wood">Wood</option>
                <option value="Aether">Aether</option>
            `;
            selectElement.value = currentValue;
            selectElement.addEventListener("change", () => {
                client.send({
                    "type": "game/command",
                    "game": game.id,
                    "target": entity.id,
                    "key": key,
                    "value": selectElement.value,
                });
            });
        } else if (valueType == "Number") {
            const [minValue, currentValue, maxValue] = args;
            const inputElement = inputRow.appendChild(document.createElement("input"));
            inputElement.type = "number";
            inputElement.min = minValue;
            inputElement.max = maxValue;
            inputElement.step = "1";
            inputElement.value = currentValue;
            inputElement.addEventListener("change", () => {
                client.send({
                    "type": "game/command",
                    "game": game.id,
                    "target": entity.id,
                    "key": key,
                    "value": inputElement.value,
                });
            });
        }
    }
}


async function hideCommandPanel(_: Game) {
    const actionBar = document.getElementById("action-bar") as HTMLDivElement;
    actionBar.classList.add("disabled");

    if (selectingLocation) {
        selectingLocationController.abort();
    }
}


async function selectEntity(game: Game, entityId: string) {
    game.selected.add(entityId);

    const entity = game.entities[entityId];
    if (!entity || !entity.sprite) {
        return;
    }

    if (game.selected.size == 1) {
        await showCommandPanel(game, entity);
    } else {
        await hideCommandPanel(game);
    }

    entity.sprite.filters = [
        new GlowFilter({distance: 8, outerStrength: 2, color: 0xffdd80}),
    ];
}


async function deselectEntity(game: Game, entityId: string) {
    game.selected.delete(entityId);

    const entity = game.entities[entityId];
    if (!entity || !entity.sprite) {
        return;
    }

    if (game.selected.size == 1) {
        const lastSelectedEntity = game.entities[game.selected.values().next().value];
        if (lastSelectedEntity) {
            await showCommandPanel(game, lastSelectedEntity);
        } else {
            await hideCommandPanel(game);
        }
    } else {
        await hideCommandPanel(game);
    }

    entity.sprite.filters = [];
}


async function onEntityCreate(game: Game, entity: Entity) {
    let sprite: Container;

    let icon: string[] = ["/unknown.png"];
    let tint: number = 0xffffff;
    let size: number = 200;
    if (entity.image) {
        icon = entity.image.split(",");
        tint = entity.tint;
        size = entity.size;
    }

    if (entity.entityTag & (EntityTag.Unit|EntityTag.Structure)) {
        sprite = await makeSprite(entity.name, { url: icon, tint, size, label: entity.name });
        sprite.eventMode = "dynamic";
        const spriteLabel = sprite.getChildByLabel("label");
        sprite.addEventListener("mouseenter", () => {
            // Move this sprite to the front
            state.camera.removeChild(sprite);
            state.camera.addChild(sprite);
            // Resize the text
            spriteLabel.scale = 0.9 / state.camera.scale.x;
            spriteLabel.visible = true;
            // Add a listener to hide the text again
            sprite.addEventListener("mouseleave", () => {
                spriteLabel.visible = false;
            }, { once: true });
        });
        sprite.addEventListener("mousedown", async ev => {
            if (!ev.shiftKey) {
                for (const selectedId of game.selected) {
                    await deselectEntity(game, selectedId);
                }
                await selectEntity(game, entity.id);
            } else {
                if (game.selected.has(entity.id)) {
                    await deselectEntity(game, entity.id);
                } else {
                    await selectEntity(game, entity.id);
                }
            }
        });
    } else {
        sprite = await makeSprite(entity.name, { url: icon, tint, size });
    }
    entity.sprite = sprite;

    game.map[entity.position.toString()] = entity;
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

    if (entity.maxHp != 0) {
        const hpBackground = sprite.getChildByLabel("hpBackground") as Graphics;
        hpBackground.visible = true;
        setHealthPercent(entity);
    }

    sprite.x = entity.position.x;
    sprite.y = entity.position.y;
    state.camera.addChild(sprite);
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

    state.camera.removeChildren();

    let game = await client.getGame(game_id);
    globalThis.game = game;

    game.reveal();

    const actionBar = overlay.appendChild(document.createElement("div"));
    actionBar.id = "action-bar";

    const infoRegion = overlay.appendChild(document.createElement("div"));
    infoRegion.classList.add("info-region");
    const gameIdText = infoRegion.appendChild(document.createElement("div"));
    gameIdText.textContent = `Join ID: ${game.id}`;
    const enemyCountText = infoRegion.appendChild(document.createElement("div"));
    enemyCountText.textContent = `Enemies: ${game.enemyCount}`;

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
        enemyCountText.textContent = `Enemies: ${game.enemyCount}`;
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
                delete game.map[oldPosition.toString()];
                game.map[entity.position.toString()] = entity;
                onMoveEntity(entity, 300);
            }

            if (entity.maxHp != 0) {
                setHealthPercent(entity);
            }
        }
    });

    client.subscribe("entity/attack", async data => {
        const source = game.entities[data.source];
        const target = game.entities[data.target];
        if (source && target) {
            let target_x: number;
            let target_y: number;
            if (!target.sprite) {
                target_x = target.position.x;
                target_y = target.position.y;
            }
            else {
                target_x = target.sprite.x;
                target_y = target.sprite.y;
            }
            const attack = makeGraphics();
            attack.moveTo(source.position.x, source.position.y);
            attack.lineTo(target_x, target_y);
            attack.stroke({ color: "#0060ff", width: 4, pixelLine: true });
            state.camera.addChild(attack);
            setTimeout(() => {
                destroyGraphics(attack);
            }, 100);
        }
    });

    client.subscribe("entity/remove", async data => {
        const entity = game.entities[data.id];
        if (game.selected.has(data.id)) {
            deselectEntity(game, data.id);
        }
        removeOnTick(data.id);
        delete game.entities[data.id];
        delete game.units[data.id];
        delete game.resources[data.id];
        delete game.structures[data.id];

        if (!entity) {
            return;
        }
        delete game.map[entity.position.toString()];

        if (entity.entityTag & EntityTag.Unit && entity.alignment == Alignment.Enemy) {
            game.enemyCount -= 1;
        }

        if (entity.sprite) {
            setTimeout(() => {
                destroySprite(entity.name, entity.sprite);
            }, 100);
        }
        enemyCountText.textContent = `Enemies: ${game.enemyCount}`;
    });

    client.subscribe("reveal", async data => {
        game.revealedArea = data.area;
        game.reveal();
    });

    client.subscribe("resource", async data => {
        game[data.resource_type] += data.amount;
        resourceAmounts[data.resource_type].textContent = game[data.resource_type];
    });

    state.onEscape = (_: KeyboardEvent) => {
        selectingLocationCancelled = true;
        for (const selectedId of game.selected) {
            deselectEntity(game, selectedId);
        }
    }

    state.onBackgroundClick = (ev: MouseEvent) => {
        if (!ev.shiftKey) {
            for (const selectedId of game.selected) {
                deselectEntity(game, selectedId);
            }
        }
    };

    state.onRightClick = (ev: MouseEvent) => {
        const [x, y] = screenToWorldCoordinates(ev.clientX, ev.clientY);
        const hexPosition = Position.fromPixels(x, y);
        const entity = game.map[hexPosition.toString()];
        if (!entity) {
            return;
        }

        client.send({
            type: "game/target",
            game: game_id,
            selected: Array.from(game.selected),
            target: entity.id,
        });
    };
}
