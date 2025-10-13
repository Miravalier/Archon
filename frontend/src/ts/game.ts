import { Graphics, Container } from "pixi.js";
import { addOnTick, removeOnTick, state } from "./state.ts";
import { client } from "./api.ts";
import { Alignment, Entity, Game, Position, EntityTag, ResourceType } from "./models.ts";
import { GlowFilter } from "pixi-filters";
import { Future } from "./async.ts";
import {
    addTooltip,
    animateProjectile,
    destroySprite,
    displayDeathVisual,
    fadeOutGraphics,
    lerp,
    makeGraphics,
    makeSprite,
    allProgressData,
    ProgressData,
    addQueueIndicator,
 } from "./render.ts";


const resourceTypes = [ResourceType.Food, ResourceType.Wood, ResourceType.Stone, ResourceType.Gold, ResourceType.Aether];


const resourceIcons = {
    [ResourceType.Wood]: "/images/symbols/wood.png",
    [ResourceType.Stone]: "/images/symbols/stone.png",
    [ResourceType.Gold]: "/images/symbols/gold.png",
    [ResourceType.Aether]: "/images/symbols/aether.png",
    [ResourceType.Food]: "/images/symbols/food.png",
};


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
        destroySprite(selectingLocationSprite);

        selectingLocation = false;
        selectingLocationController = null;
        selectingLocationSprite = null;
        lastSelectedLocation = null;
    });

    selectingLocation = true;
    selectingLocationController = controller;
    selectingLocationSprite = await makeSprite({ url: icon });
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


let activeButtonIndicators: {[id: string]: HTMLDivElement} = {};


async function showCommandPanel(game: Game, entity: Entity) {
    const actionBar = document.getElementById("action-bar") as HTMLDivElement;
    actionBar.innerHTML = "";
    actionBar.classList.remove("disabled");

    const buttonRow = actionBar.appendChild(document.createElement("div"));
    buttonRow.classList.add("button-row");

    const inputRow = actionBar.appendChild(document.createElement("div"));
    inputRow.classList.add("input-row");

    const response: {commands: [string, any][]} = await client.send({ "type": "game/query", "game": game.id, "target": entity.id });
    for (const [key, value] of response.commands) {
        if (key == "!") {
            const labelElement = inputRow.appendChild(document.createElement("div"));
            labelElement.classList.add("label");
            labelElement.textContent = value;
            continue;
        }

        const [valueType, ...args] = value.split(":");
        if (valueType == "Button") {
            const [icon, selectPosition, tooltip] = args;

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
            addTooltip(buttonElement, tooltip);
            if (key.startsWith("train/")) {
                const event = key.split("/")[1];
                buttonElement.addEventListener("contextmenu", async () => {
                    client.send({
                        "type": "game/command",
                        "game": game.id,
                        "target": entity.id,
                        "key": `cancel/${event}`,
                        "value": "",
                    });
                });
                activeButtonIndicators[`${entity.id}-${event}`] = addQueueIndicator(buttonElement);            }
        } else if (valueType == "ResourceType") {
            const [currentValue,] = args;
            const selectElement = inputRow.appendChild(document.createElement("select"));
            selectElement.innerHTML = `
                <option value=""></option>
                <option value="Food">Food</option>
                <option value="Wood">Wood</option>
                <option value="Stone">Stone</option>
                <option value="Gold">Gold</option>
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
    activeButtonIndicators = {};

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

    let icon: string[] = ["/images/symbols/unknown.png"];
    let tint: number = 0xffffff;
    let size: number = 200;
    if (entity.image && entity.image.length > 0) {
        icon = entity.image;
        tint = entity.tint;
        size = entity.size;
    }

    if (entity.entityTag & (EntityTag.Unit|EntityTag.Structure)) {
        sprite = await makeSprite({ url: icon, tint, size, label: entity.name });
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
        sprite = await makeSprite({ url: icon, tint, size });
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

    client.subscribe("game/end", async data => {
        const gameOverText = overlay.appendChild(document.createElement("div"));
        gameOverText.classList.add("game-over");
        if (data.success) {
            gameOverText.classList.add("good");
            gameOverText.textContent = data.label.toUpperCase();
        } else {
            gameOverText.classList.add("bad");
            gameOverText.textContent = data.label;
        }
    });

    client.subscribe("entity/add", async data => {
        const entity = new Entity(data.entity);
        await onEntityCreate(game, entity);
        enemyCountText.textContent = `Enemies: ${game.enemyCount}`;
    });

    client.subscribe("entity/status/add", async data => {
        const entity = game.entities[data.id];
        if (!entity || !entity.sprite) {
            return;
        }

        if (data.status == "stealth") {
            entity.sprite.alpha = 0.15;
        }
    });

    client.subscribe("entity/status/remove", async data => {
        const entity = game.entities[data.id];
        if (!entity || !entity.sprite) {
            return;
        }

        if (data.status == "stealth") {
            entity.sprite.alpha = 1.0;
        }
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
            let srcX: number;
            let srcY: number;
            if (!source.sprite) {
                srcX = source.position.x;
                srcY = source.position.y;
            } else {
                srcX = source.sprite.x;
                srcY = source.sprite.y;
            }

            let targetX: number;
            let targetY: number;
            if (!target.sprite) {
                targetX = target.position.x;
                targetY = target.position.y;
            } else {
                targetX = target.sprite.x;
                targetY = target.sprite.y;
            }

            const attack = makeGraphics();

            if (data.visual == "laser") {
                attack.moveTo(srcX, srcY);
                attack.lineTo(targetX, targetY);
                attack.stroke({ color: "#880088", width: 8, pixelLine: true });
                fadeOutGraphics(attack, 200);
            } else if (data.visual == "claws") {
                for (const [x, y] of [[60, -240], [80, -210], [70, -180]]) {
                    attack.moveTo(-x, y);
                    attack.bezierCurveTo(-36, y-24, 36, y-24, x, y);
                    attack.bezierCurveTo(-36, y-12, 36, y-12, -x, y);
                    attack.fill({ color: "#880088"});
                }
                attack.x = srcX;
                attack.y = srcY;
                attack.rotation = Math.atan2(targetY - srcY, targetX - srcX) + Math.PI/2;
                fadeOutGraphics(attack, 200);
            } else if (data.visual == "arrow" || data.visual == "void orb") {
                attack.moveTo(-50, 0);
                attack.lineTo(-55, -10);
                attack.lineTo(-35, -10);
                attack.lineTo(-35, -3);
                attack.lineTo(40, -3);
                attack.lineTo(35, -15);
                attack.lineTo(55, 0);
                attack.lineTo(35, 15);
                attack.lineTo(40, 3);
                attack.lineTo(-35, 3);
                attack.lineTo(-35, 10);
                attack.lineTo(-55, 10);
                attack.lineTo(-50, 0);
                attack.fill({ color: "#888888" });
                attack.x = srcX;
                attack.y = srcY;
                attack.rotation = Math.atan2(targetY - srcY, targetX - srcX);
                animateProjectile(attack, srcX, srcY, targetX, targetY, 200);
            }

            state.camera.addChild(attack);
        }
    });

    client.subscribe("entity/remove", async data => {
        const entity = game.entities[data.id];
        if (game.selected.has(data.id)) {
            deselectEntity(game, data.id);
        }
        removeOnTick(data.id);
        const entityProgressCollection = allProgressData[data.id];
        if (entityProgressCollection) {
            for (const event of Object.keys(entityProgressCollection)) {
                removeOnTick(`${data.id}-${event}`);
            }
        }
        delete allProgressData[data.id];
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
                displayDeathVisual(entity.sprite.x, entity.sprite.y, data.visual);
                destroySprite(entity.sprite);
            }, 200);
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

    client.subscribe("entity/progress", async (data: ProgressData) => {
        const keyId = `${data.parent}-${data.event}`;

        // Get the progress collection for this entity
        let entityCollection = allProgressData[data.parent];
        if (!entityCollection) {
            entityCollection = {};
            allProgressData[data.parent] = entityCollection;
        }

        // Add or remove the data from the entity collection
        if (data.queue == 0) {
            const queueIndicator = activeButtonIndicators[keyId];
            if (queueIndicator) {
                queueIndicator.classList.add("disabled");
            }
            delete entityCollection[data.event];
            removeOnTick(keyId);
        } else {
            entityCollection[data.event] = data;
            addOnTick(keyId, (deltaMs) => {
                data.progress += deltaMs/1000;

                const queueIndicator = activeButtonIndicators[keyId];
                if (!queueIndicator) {
                    return;
                }
                queueIndicator.classList.remove("disabled");

                const queueNumber = queueIndicator.querySelector(".queue-number");
                queueNumber.textContent = data.queue.toString();

                const progressForeground = queueIndicator.querySelector<HTMLDivElement>(".progress-bar");
                progressForeground.style.width = `${queueIndicator.clientWidth * (data.progress / data.duration)}px`;
            });
        }

        // If the data was removed and there are no more events
        // for the given entity collection, remove the entire collection
        if (Object.keys(entityCollection).length == 0) {
            delete allProgressData[data.parent];
        }
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
        if (game.selected.size == 0) {
            return;
        }
        const [x, y] = screenToWorldCoordinates(ev.clientX, ev.clientY);
        const hexPosition = Position.fromPixels(x, y);
        client.send({
            type: "game/target",
            game: game_id,
            selected: Array.from(game.selected),
            position: hexPosition.toString(),
        });
    };
}
