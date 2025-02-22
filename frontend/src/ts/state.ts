import { Application, Container } from "pixi.js";


interface State {
    app: Application;
    camera: Container;
}


export const state: State = {
    app: null,
    camera: null,
};
