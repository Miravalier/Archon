import { Application, Container } from "pixi.js";


interface State {
    app: Application;
    camera: Container;
    overlay: HTMLDivElement;
    gridSize: number;
}


export const state: State = {
    app: null,
    camera: null,
    overlay: null,
    gridSize: 100,
};
