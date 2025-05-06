import { Application, Container, Graphics } from "pixi.js";


type OnTickCallback = (delta: number) => void;


interface State {
    app: Application;
    camera: Container;
    mask: Graphics;
    overlay: HTMLDivElement;
    gridSize: number;
    onTick: {[id: string]: OnTickCallback};
    onBackgroundClick: (ev: MouseEvent) => void;
    onRightClick: (ev: MouseEvent) => void;
}


export const state: State = {
    app: null,
    camera: null,
    mask: null,
    overlay: null,
    gridSize: 100,
    onTick: {},
    onBackgroundClick: null,
    onRightClick: null,
};


export function addOnTick(id: string, callback: OnTickCallback) {
    state.onTick[id] = callback;
}


export function removeOnTick(id: string) {
    delete state.onTick[id];
}


globalThis.state = state;
