import { Application, Container, Graphics } from "pixi.js";
import { generateToken } from "./utils.ts";


type OnTickCallback = (delta: number) => void;


interface State {
    app: Application;
    camera: Container;
    mask: Graphics;
    overlay: HTMLDivElement;
    gridSize: number;
    onTick: {[id: string]: OnTickCallback};
}


export const state: State = {
    app: null,
    camera: null,
    mask: null,
    overlay: null,
    gridSize: 100,
    onTick: {},
};


export function addOnTick(callback: OnTickCallback): string {
    const id = generateToken();
    state.onTick[id] = callback;
    return id;
}


export function removeOnTick(id: string) {
    delete state.onTick[id];
}


globalThis.state = state;
