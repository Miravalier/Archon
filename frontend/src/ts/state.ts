import { Application, Container, Graphics, Mask } from "pixi.js";


interface State {
    app: Application;
    camera: Container;
    mask: Graphics;
    overlay: HTMLDivElement;
    gridSize: number;
}


export const state: State = {
    app: null,
    camera: null,
    mask: null,
    overlay: null,
    gridSize: 100,
};


globalThis.state = state;