import { Assets, Container, Graphics, Sprite, Text } from "pixi.js";
import { addOnTick, removeOnTick, state } from "./state";
import { generateToken } from "./utils";


interface SpriteData {
    url: string | string[];
    tint?: number | number[];
    size?: number;
    mask?: Container;
    label?: string;
}


export function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t;
}


export function makeGraphics(): Graphics {
    return new Graphics();
}


export function destroyGraphics(graphics: Graphics) {
    graphics.removeFromParent();
    graphics.removeAllListeners();
    graphics.destroy({
        context: true,
        texture: true,
        textureSource: true,
    });
}


export function destroySpriteChild(sprite: Container, label: string) {
    const child = sprite.getChildByLabel(label);
    if (child) {
        child.removeFromParent();
        child.destroy({context: true, texture: true, textureSource: true});
    }
}


export function destroySprite(sprite: Container) {
    sprite.removeFromParent();
    sprite.removeAllListeners();
    destroySpriteChild(sprite, "label");
    destroySpriteChild(sprite, "hpBackground");
    destroySpriteChild(sprite, "hpFill");
    sprite.destroy({children: true, context: true});
}


export async function makeSprite(data: SpriteData): Promise<Container> {
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
        const texture = await Assets.load(url);
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


export function fadeOutGraphics(graphics: Graphics, durationMs: number) {
    let timeElapsed = 0;
    const tickId = generateToken();
    addOnTick(tickId, deltaMs => {
        timeElapsed += deltaMs;
        if (timeElapsed >= durationMs) {
            graphics.alpha = 0;
        } else {
            graphics.alpha = lerp(1, 0, timeElapsed/durationMs);
        }
    });

    setTimeout(() => {
        removeOnTick(tickId);
        destroyGraphics(graphics);
    }, durationMs+100);
}


export function animateProjectile(graphics: Graphics, startX: number, startY: number, endX: number, endY: number, durationMs: number) {
    let timeElapsed = 0;
    const tickId = generateToken();
    addOnTick(tickId, deltaMs => {
        timeElapsed += deltaMs;
        if (timeElapsed >= durationMs) {
            graphics.alpha = 0;
        } else {
            graphics.x = lerp(startX, endX, timeElapsed/durationMs);
            graphics.y = lerp(startY, endY, timeElapsed/durationMs);
        }
    });

    setTimeout(() => {
        removeOnTick(tickId);
        destroyGraphics(graphics);
    }, durationMs+100);
}


export function animateExpandAndFade(graphics: Graphics, startSize: number, endSize: number, durationMs: number) {
    let timeElapsed = 0;
    const tickId = generateToken();
    addOnTick(tickId, deltaMs => {
        timeElapsed += deltaMs;
        if (timeElapsed >= durationMs) {
            graphics.alpha = 0;
        } else {
            graphics.alpha = lerp(1, 0, timeElapsed/durationMs);
            graphics.scale = lerp(startSize, endSize, timeElapsed/durationMs);
        }
    });

    setTimeout(() => {
        removeOnTick(tickId);
        destroyGraphics(graphics);
    }, durationMs+100);
}


export function displayDeathVisual(x: number, y: number, visual: string) {
    const effect = makeGraphics();

    if (visual == "Void") {
        effect.circle(0, 0, 30);
        effect.fill({color: "#880088"})
        effect.x = x;
        effect.y = y;
        animateExpandAndFade(effect, 1.0, 5.0, 500);
    } else if (visual == "Blood") {
        effect.circle(0, 0, 30);
        effect.fill({color: "#600000"})
        effect.x = x;
        effect.y = y;
        animateExpandAndFade(effect, 1.0, 5.0, 500);
    } else if (visual == "Structure") {
        effect.circle(0, 0, 30);
        effect.fill({color: "#ff2f00"})
        effect.x = x;
        effect.y = y;
        animateExpandAndFade(effect, 1.0, 6.0, 600);
    }

    state.camera.addChild(effect);
}


export function addTooltip(element: HTMLElement, text: string): HTMLDivElement {
    const actionBar = document.querySelector("#action-bar");
    const tooltip = actionBar.appendChild(document.createElement("div"));
    tooltip.classList.add("tooltip");
    tooltip.classList.add("disabled");
    tooltip.innerHTML = text;

    element.addEventListener("mouseenter", () => {
        const rect = element.getBoundingClientRect();
        tooltip.classList.remove("disabled");
        tooltip.style.left = `${Math.round(rect.left + element.clientWidth/2 - tooltip.clientWidth/2)}px`;
        tooltip.style.bottom = `${document.body.clientHeight - rect.top}px`;
        element.addEventListener("mouseleave", () => {
            tooltip.classList.add("disabled");
        }, {once: true});
    });

    return tooltip;
}
