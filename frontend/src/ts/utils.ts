export function generateToken(): string {
    const buffer = new Uint8Array(16);
    crypto.getRandomValues(buffer);
    let result = "";
    for (const byte of buffer) {
        result += byte.toString(16).padStart(2, '0');
    }
    return result;
}
