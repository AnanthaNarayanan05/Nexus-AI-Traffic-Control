import type { Frame } from './types';

const WS_URL = import.meta.env.VITE_WS_URL ?? 'ws://127.0.0.1:8000/ws';

export type ConnectionState = 'connecting' | 'open' | 'closed';

type FrameHandler = (frame: Frame) => void;
type StateHandler = (state: ConnectionState, detail?: string) => void;

/**
 * Auto-reconnecting WebSocket client.
 *
 * Reconnect backoff is capped so a backend restart is picked up within a few seconds
 * without hammering it. The socket carries no application state of its own: on reconnect
 * the server sends a fresh `hello` + full `simulation_state`, so the stores resync.
 */
export class NexusSocket {
  private ws: WebSocket | null = null;
  private frameHandlers = new Set<FrameHandler>();
  private stateHandlers = new Set<StateHandler>();
  private retry = 0;
  private timer: number | null = null;
  private stopped = false;

  connect(): void {
    this.stopped = false;
    this.open();
  }

  private open(): void {
    if (this.stopped) return;
    this.emitState('connecting');
    let ws: WebSocket;
    try {
      ws = new WebSocket(WS_URL);
    } catch (err) {
      this.scheduleReconnect(String(err));
      return;
    }
    this.ws = ws;

    ws.onopen = () => {
      this.retry = 0;
      this.emitState('open');
    };
    ws.onmessage = (ev) => {
      let frame: Frame;
      try {
        frame = JSON.parse(ev.data as string) as Frame;
      } catch {
        return;
      }
      this.frameHandlers.forEach((h) => h(frame));
    };
    ws.onerror = () => {
      /* onclose always follows; reconnect is handled there */
    };
    ws.onclose = (ev) => {
      this.ws = null;
      this.scheduleReconnect(ev.reason || `closed (${ev.code})`);
    };
  }

  private scheduleReconnect(detail: string): void {
    if (this.stopped) return;
    this.emitState('closed', detail);
    const delay = Math.min(500 * 2 ** this.retry, 5000);
    this.retry += 1;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.timer = window.setTimeout(() => this.open(), delay);
  }

  send(msg: Record<string, unknown>): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) return false;
    this.ws.send(JSON.stringify(msg));
    return true;
  }

  command(action: string, args: Record<string, unknown> = {}): boolean {
    return this.send({ type: 'command', action, args });
  }

  subscribe(channels: string[] | null): boolean {
    return this.send({ type: 'subscribe', channels });
  }

  onFrame(handler: FrameHandler): () => void {
    this.frameHandlers.add(handler);
    return () => this.frameHandlers.delete(handler);
  }

  onState(handler: StateHandler): () => void {
    this.stateHandlers.add(handler);
    return () => this.stateHandlers.delete(handler);
  }

  private emitState(state: ConnectionState, detail?: string): void {
    this.stateHandlers.forEach((h) => h(state, detail));
  }

  close(): void {
    this.stopped = true;
    if (this.timer !== null) window.clearTimeout(this.timer);
    this.ws?.close();
    this.ws = null;
  }
}

export const socket = new NexusSocket();
