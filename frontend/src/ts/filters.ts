import * as PIXI from "pixi.js";
import { Filter, GlProgram } from 'pixi.js';
import vertex from '../shaders/grid.vert?raw';
import fragment from '../shaders/grid.frag?raw';


export class GridFilter extends Filter {
    uniforms: {
        uViewport: PIXI.Point,
        uTranslation: PIXI.Point,
        uPitch: number,
        uScale: number,
        uColor: PIXI.Color,
    };

    constructor(
        width: number,
        height: number,
        squareSize: number,
        translation_x: number,
        translation_y: number,
        scale: number,
        color: PIXI.Color,
    ) {

        const glProgram = GlProgram.from({
            vertex,
            fragment,
            name: 'grid-filter',
        });

        super({
            glProgram,
            resources: {
                gridUniforms: {
                    uViewport: { value: new PIXI.Point(width, height), type: 'vec2<f32>' },
                    uTranslation: { value: new PIXI.Point(translation_x, translation_y), type: 'vec2<f32>' },
                    uPitch: { value: squareSize, type: 'f32' },
                    uScale: { value: scale, type: 'f32' },
                    uColor: { value: color, type: 'vec4<f32>' },
                    uDebug: { value: 0, type: 'f32' },
                },
            },
        });

        this.uniforms = this.resources.gridUniforms.uniforms;
    }
}
