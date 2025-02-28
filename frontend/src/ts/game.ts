import { Graphics, Text } from "pixi.js";
import { state } from "./state.ts";
import { client } from "./api.ts";
import { Game } from "./models.ts";


function addToBoard(Container) {

}


export async function activate(channel_id: string) {
    console.log("[!] Game View Page");

    const canvas = document.querySelector("canvas");
    canvas.classList.remove("disabled");

    const overlay = document.querySelector("#overlay");
    overlay.innerHTML = "";

    state.camera.removeChildren();

    let game: Game;
    try {
        game = await client.getGame(channel_id);
    } catch {
        game = await client.createGame(channel_id);
    }

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
}
