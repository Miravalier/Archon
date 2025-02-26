import { TimedFuture, Future, Sleep } from "./async.ts";


export interface WebsocketMessage {
    type?: string;
    data?: any;
    id?: any;
}


type WebsocketHandler = (data: any) => Promise<void>;


function generateToken(): string {
    const buffer = new Uint8Array(16);
    crypto.getRandomValues(buffer);
    let result = "";
    for (const byte of buffer) {
        result += byte.toString(16).padStart(2, '0');
    }
    return result;
}


export class Client {
    token: string;
    ws: WebSocket;
    subscriptions: { [type: string]: Set<WebsocketHandler> };
    lastTransmit: number;
    messageId: number;
    waitingSenders: { [messageId: string]: TimedFuture<any> };
    connected: boolean;

    constructor() {
        this.token = null;
        this.ws = null;
        this.subscriptions = {};
        this.lastTransmit = 0;
        this.messageId = 0;
        this.waitingSenders = {};
        this.connected = false;
    }

    async init() {
        this.token = localStorage.getItem("token");
        if (!this.token) {
            this.token = generateToken();
            localStorage.setItem("token", this.token);
        }
        this.connectionWorker();
    }

    async tryPing() {
        if (Date.now() - this.lastTransmit < 5000) {
            return;
        }

        try {
            await this.send({ type: "ping" });
        }
        catch {
            console.error("Ping failed!");
        }
    }

    async connectionWorker() {
        while (true) {
            if (this.ws) {
                await this.tryPing();
            }
            else {
                try {
                    console.log("[!] WebSocket Connecting ...");
                    this.ws = await this.websocketConnect();
                    console.log("[!] WebSocket Connected!");
                }
                catch {
                    console.log("[!] Connection Failed");
                }
            }
            await Sleep(1000);
        }
    }

    async request(method: string, endpoint: string, data: any = null): Promise<any> {
        if (!data) {
            data = {};
        }
        if (this.token) {
            data.token = this.token;
        }

        const response = await fetch(`/api${endpoint}`, {
            method,
            cache: 'no-cache',
            headers: {
                'Content-Type': 'application/json'
            },
            body: data ? JSON.stringify(data) : null,
        });

        if (response.status < 200 || response.status >= 300) {
            throw `[API ERROR] ${response.status} ${response.statusText} - ${await response.text()}`;
        }

        return await response.json();
    }

    async send(data: any): Promise<any> {
        const messageId = this.messageId;
        this.messageId += 1;
        data.id = messageId;

        const future = new TimedFuture<any>(5000);
        this.waitingSenders[messageId] = future;

        try {
            this.ws.send(JSON.stringify(data));
            this.lastTransmit = Date.now();
            const response = await future;
            if (response.type == "error") {
                throw Error(`${response.reason} - ${response.data}`);
            }
            return response;
        }
        finally {
            delete this.waitingSenders[messageId];
        }
    }

    async onMessage(message: WebsocketMessage) {
        if (message.type != "pong") {
            console.log("[API Message]", message);
        }

        if (message.type == "connect") {
            this.connected = true;
        }

        const waitingSender = this.waitingSenders[message.id];
        if (waitingSender) {
            waitingSender.resolve(message);
        }

        let subscription_set = this.subscriptions[message.type];
        if (subscription_set) {
            for (const callback of subscription_set) {
                callback(message);
            }
        }
    }

    async websocketConnect(): Promise<WebSocket> {
        const connected = new Future<WebSocket>();

        let ws_prefix = (location.protocol === "https:" ? "wss:" : "ws:");
        const ws = new WebSocket(`${ws_prefix}//${location.host}/api/subscribe`);

        ws.onopen = () => {
            console.log("[!] WS - Sending Token");
            ws.send(JSON.stringify({ "token": this.token }));
            connected.resolve(ws);
        };
        ws.onmessage = ev => {
            const message = JSON.parse(ev.data);
            this.onMessage(message);
        };
        ws.onclose = () => {
            if (this.ws) {
                this.onMessage({ type: "disconnected" });
            }
            this.ws = null;
            this.connected = false;
            connected.reject("ws disconnected");
        };

        return await connected;
    }

    subscribe(type: string, callback: WebsocketHandler) {
        let subscription_set = this.subscriptions[type];
        if (!subscription_set) {
            subscription_set = new Set();
            this.subscriptions[type] = subscription_set;
        }
        subscription_set.add(callback);
    }

    unsubscribe(type: string, callback: WebsocketHandler) {
        let subscription_set = this.subscriptions[type];
        if (subscription_set) {
            subscription_set.delete(callback);
        }
    }
}


export const client = new Client();
