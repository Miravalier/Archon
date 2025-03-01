precision mediump float;
in vec2 vTextureCoord;
out vec4 finalColor;

uniform sampler2D uTexture;

uniform vec2 uViewport;      // e.g. [800 600] Size of the canvas
uniform vec2 uTranslation;   // e.g. [0 0] Shifts the grid by x, y pixels
uniform vec4 uColor;         // e.g. [0.1, 0.1, 0.1, 0.2] Color of the  grid
uniform float uPitch;        // e.g. 150, Size of the grid hexes in px
uniform float uScale;        // e.g. 1.0, Scale percentage
uniform float uDebug;        // e.g. Debug Value

#define M_PI 3.1415926535897932384626433832795

void main(void)
{
    float gridSize = sqrt(uPitch * uScale);
    float offX = (gl_FragCoord.x - uTranslation.x);
    float offY = (uViewport.y - (gl_FragCoord.y + uTranslation.y));

    offY -= 1.5*gridSize*gridSize;

    float q = (sqrt(3.0)/3.0 * offX - 1.0/3.0 * offY);
    float r = (2.0/3.0 * offY);
    float s = -q - r;

    float aq = (sqrt(3.0)/3.0 * offY - 1.0/3.0 * offX);
    float ar = (2.0/3.0 * offX);
    float as = -aq - ar;

    q /= gridSize;
    r /= gridSize;
    s /= gridSize;

    aq /= gridSize;
    ar /= gridSize;
    as /= gridSize;

    if (
        (mod(s, gridSize * 3.0) < gridSize && mod(aq+0.15, gridSize*sqrt(3.0)) < 0.3) ||
        (mod(q, gridSize * 3.0) < gridSize && mod(as+0.15, gridSize*sqrt(3.0)) < 0.3) ||
        (mod(r, gridSize * 3.0) < gridSize && mod(ar+0.15, gridSize*sqrt(3.0)) < 0.3) ||
        (mod(s + 1.5*gridSize, gridSize * 3.0) < gridSize && mod(aq + gridSize*(sqrt(3.0)/2.0) + 0.15, gridSize*sqrt(3.0)) < 0.3) ||
        (mod(q + 1.5*gridSize, gridSize * 3.0) < gridSize && mod(as + gridSize*(sqrt(3.0)/2.0) + 0.15, gridSize*sqrt(3.0)) < 0.3) ||
        (mod(r + 1.5*gridSize, gridSize * 3.0) < gridSize && mod(ar + gridSize*(sqrt(3.0)/2.0) + 0.15, gridSize*sqrt(3.0)) < 0.3)
    ) {
        finalColor = uColor;
    } else {
        finalColor = vec4(0.0, 0.0, 0.0, 0.0);
    }

    // // The SAW
    // if (
    //     (mod(s, gridSize * 3.0) < gridSize && mod(r, gridSize) < 0.2) ||
    //     (mod(q, gridSize * 3.0) < gridSize && mod(s, gridSize) < 0.2) ||
    //     (mod(r, gridSize * 3.0) < gridSize && mod(q, gridSize) < 0.2)
    // ) {
    //     finalColor = vec4(1.0, 0.0, 0.0, 1.0);
    // } else {
    //     finalColor = vec4(0.0, 0.0, 0.0, 0.0);
    // }
}
