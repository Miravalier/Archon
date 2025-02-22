import { Application, Container, Graphics, Text } from "pixi.js";
import { state } from "./state.ts";


async function Main() {
    console.log("[!] Loading Archon ...");

    document.body.addEventListener("contextmenu", ev => {
        ev.preventDefault();
    });

    // Initialize App
    state.app = new Application();
    globalThis.__PIXI_APP__ = state.app;

    await state.app.init({ background: '#232224', resizeTo: window });
    document.body.appendChild(state.app.canvas);

    // Initialize Camera
    state.camera = state.app.stage.addChild(new Container());

    // Add canvas pan listeners
    state.app.canvas.addEventListener("mousedown", mouseDownEvent => {
        let position = { x: mouseDownEvent.clientX, y: mouseDownEvent.clientY };

        const controller = new AbortController();

        const mouseMoveHandler = (mouseMoveEvent: MouseEvent) => {
            const deltaX = mouseMoveEvent.x - position.x;
            const deltaY = mouseMoveEvent.y - position.y;
            state.camera.x += deltaX;
            state.camera.y += deltaY;
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

    // Add zoom listener
    state.app.canvas.addEventListener("wheel", ev => {
        ev.preventDefault();

        let zoomDelta: number;
        if (ev.deltaY > 0) {
            zoomDelta = 0.9;
        }
        else {
            zoomDelta = 1.1;
        }

        state.camera.x -= state.app.canvas.width / 2;
        state.camera.y -= state.app.canvas.height / 2;
        state.camera.scale.x *= zoomDelta;
        state.camera.scale.y *= zoomDelta;
        state.camera.x *= zoomDelta;
        state.camera.y *= zoomDelta;
        state.camera.x += state.app.canvas.width / 2;
        state.camera.y += state.app.canvas.height / 2;
    });

    // Add debug rectangle
    const rectangle = new Graphics();
    rectangle.roundRect(-100, -100, 200, 200, 4);
    rectangle.fill("#5080ff");
    state.camera.addChild(rectangle);

    // Add label to debug rectangle
    const text = new Text();
    text.style.fontSize = 32;
    text.style.fill = "#ffffff";
    text.style.stroke = "#000000";
    text.text = "Test";
    text.y = -102;
    text.anchor.set(0.5, 1);
    state.camera.addChild(text);

    console.log("[!] Loading Complete");
}


window.addEventListener("load", Main);
