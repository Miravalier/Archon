import { client } from "./api.ts";
import * as Game from "./game.ts";


export async function activate() {
    console.log("[!] Channel Select Page");

    const canvas = document.querySelector("canvas");
    canvas.classList.add("disabled");

    const overlay = document.querySelector("#overlay");
    overlay.innerHTML = "";

    const user = await client.getUser();

    const linkCodeDiv = overlay.appendChild(document.createElement("div"));
    linkCodeDiv.classList.add("link-code");
    linkCodeDiv.textContent = `!link ${user.link_code}`;

    for (const channel_id of Object.keys(user.linked_channels)) {
        const channel = await client.getChannel(channel_id);
        const channelDiv = overlay.appendChild(document.createElement("div"));
        channelDiv.dataset.channel_id = channel.id;
        channelDiv.classList.add("channel");
        channelDiv.textContent = channel.name;
        channelDiv.addEventListener("click", () => {
            Game.activate(channel_id);
        });
    }
}
