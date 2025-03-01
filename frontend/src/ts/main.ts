import { Application, Color, Container, Graphics, Point } from "pixi.js";
import { state } from "./state.ts";
import { client } from "./api.ts";
import { GridFilter } from "./filters.ts";
import * as channelSelect from "./channel_select.ts";


function createGrid(
    width: number,
    height: number,
    squareSize: number,
    translation_x: number,
    translation_y: number,
    scale: number,
    color: Color,
) {
    const gridFilter = new GridFilter(width, height, squareSize, translation_x, translation_y, scale, color);
    const gridContainer = new Container();
    const gridGraphics = new Graphics();
    gridGraphics.rect(0, 0, width, height);
    gridGraphics.fill({ color: new Color(0xFFFFFF), alpha: 1.0 });
    gridContainer.addChild(gridGraphics);
    gridContainer.filters = [gridFilter];
    return { gridFilter, gridGraphics, gridContainer };
}


async function Main() {
    console.log("[!] Loading Archon ...");

    document.body.addEventListener("contextmenu", ev => {
        ev.preventDefault();
    });

    // Initialize App
    state.app = new Application();
    globalThis.__PIXI_APP__ = state.app;

    await state.app.init({
        background: '#232224',
        resizeTo: window,
        resolution: 1,
    });
    document.body.appendChild(state.app.canvas);

    // Initialize Overlay
    state.overlay = document.body.appendChild(document.createElement("div"));
    state.overlay.id = "overlay";

    // Initialize Camera
    state.camera = state.app.stage.addChild(new Container());

    // Initialize hex grid
    const { gridFilter, gridGraphics, gridContainer } = createGrid(
        state.app.canvas.width,
        state.app.canvas.height,
        state.gridSize,
        0,
        0,
        1.0,
        new Color([0.1, 0.1, 0.1, 0.2]),
    );
    state.app.stage.addChild(gridContainer);

    // Add canvas pan listeners
    state.app.canvas.addEventListener("mousedown", mouseDownEvent => {
        let position = { x: mouseDownEvent.clientX, y: mouseDownEvent.clientY };

        const controller = new AbortController();

        const mouseMoveHandler = (mouseMoveEvent: MouseEvent) => {
            const deltaX = mouseMoveEvent.x - position.x;
            const deltaY = mouseMoveEvent.y - position.y;
            state.camera.x += deltaX;
            state.camera.y += deltaY;
            gridFilter.uniforms.uTranslation = new Point(state.camera.x, state.camera.y);
            position = { x: mouseMoveEvent.clientX, y: mouseMoveEvent.clientY };
        };

        state.app.canvas.addEventListener("mousemove", mouseMoveHandler, { signal: controller.signal });

        state.app.canvas.addEventListener("mouseup", mouseUpEvent => {
            mouseMoveHandler(mouseUpEvent);
            controller.abort();
        }, { signal: controller.signal });

        state.app.canvas.addEventListener("mouseleave", mouseLeaveEvent => {
            mouseMoveHandler(mouseLeaveEvent);
            controller.abort();
        }, { signal: controller.signal });
    });

    // Add resize listener
    window.addEventListener("resize", () => {
        gridGraphics.rect(0, 0, window.innerWidth, window.innerHeight);
        gridGraphics.fill({ color: new Color(0xFFFFFF), alpha: 1.0 });
        gridFilter.uniforms.uViewport = new Point(window.innerWidth, window.innerHeight);
    });

    // Add zoom listener
    state.app.canvas.addEventListener("wheel", ev => {
        ev.preventDefault();

        let zoomDelta: number;
        if (ev.deltaY > 0) {
            zoomDelta = 0.9;
            if (gridFilter.uniforms.uScale < 0.1) {
                return;
            }
        }
        else {
            zoomDelta = 1.1;
            if (gridFilter.uniforms.uScale > 3) {
                return;
            }
        }

        state.camera.x -= state.app.canvas.width / 2;
        state.camera.y -= state.app.canvas.height / 2;
        state.camera.scale.x *= zoomDelta;
        state.camera.scale.y *= zoomDelta;
        state.camera.x *= zoomDelta;
        state.camera.y *= zoomDelta;
        state.camera.x += state.app.canvas.width / 2;
        state.camera.y += state.app.canvas.height / 2;
        gridFilter.uniforms.uScale = state.camera.scale.x;
        gridFilter.uniforms.uTranslation.x = state.camera.x;
        gridFilter.uniforms.uTranslation.y = state.camera.y;
    });

    // Initialize client
    await client.init();
    globalThis.client = client;

    console.log("[!] Loading Complete");

    // Initialize channel select
    await channelSelect.activate();
}


window.addEventListener("load", Main);
