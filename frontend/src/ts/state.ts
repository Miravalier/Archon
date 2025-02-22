import { Application, Container } from "pixi.js";


interface State {
    app: Application;
    camera: Container;
    overlay: HTMLDivElement;
}


export const state: State = {
    app: null,
    camera: null,
    overlay: null,
};
