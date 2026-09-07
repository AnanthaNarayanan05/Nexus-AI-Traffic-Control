"""WebSocket hub (spec section 71, docs/system-flow.md section 2).

One task per client. The manager's simulation loop runs on its own thread and publishes
immutable snapshots; this hub only *reads* them, so a slow or stalled client can never
block the simulation. Every frame is `{type, seq, t, payload}`.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.serialize import agent_update_payload, compact_state
from app.core.config import get_config
from app.core.simulation_manager import get_manager
from app.logging import get_logger

log = get_logger("API")
ws_router = APIRouter()

PROTOCOL_VERSION = "1.0"

_METRIC_EVERY = 10   # frames between metric_update pushes (20 Hz -> 2 Hz)
_STATUS_EVERY = 20   # frames between status pushes (20 Hz -> 1 Hz)


_ALWAYS_ON = frozenset({"hello", "error", "pong", "command_result"})


class _Client:
    def __init__(self, ws: WebSocket) -> None:
        self.ws = ws
        self.channels: set[str] | None = None  # None = everything
        self.seq = 0
        self.event_cursor = 0
        self.last_decision_id: str | None = None
        self.last_signal: str | None = None
        self.closed = False

    def wants(self, channel: str) -> bool:
        if channel in _ALWAYS_ON:
            return True  # control-plane replies are never filtered out by a subscription
        return self.channels is None or channel in self.channels

    async def send(self, channel: str, t: float, payload: Any) -> None:
        if self.closed or not self.wants(channel):
            return
        self.seq += 1
        await self.ws.send_json({"type": channel, "seq": self.seq, "t": t, "payload": payload})


@ws_router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    mgr = get_manager()
    client = _Client(ws)
    client.event_cursor = mgr.event_cursor()

    cfg = get_config()
    interval = 1.0 / max(float(cfg.simulation.stream_hz), 1.0)

    await client.send("hello", mgr.state().sim_time if mgr.state() else 0.0, {
        "protocol_version": PROTOCOL_VERSION,
        "config_digest": cfg.digest,
        "adapter": mgr.adapter.name,
        "status": mgr.status(),
        "channels": ["simulation_state", "signal_update", "agent_update",
                     "coordination_update", "metric_update", "event", "status",
                     "command_result"],
        "stream_hz": cfg.simulation.stream_hz,
        "server_time": time.time(),
    })

    receiver = asyncio.create_task(_receive_loop(ws, client, mgr))
    frame = 0
    try:
        while True:
            frame += 1
            state = mgr.state()
            if state is not None:
                t = state.sim_time
                await client.send("simulation_state", t, compact_state(state))

                signal_key = (f"{state.signal.current_phase.value}:{state.signal.served_phase.value}"
                              f":{state.signal.last_action}")
                if signal_key != client.last_signal:
                    client.last_signal = signal_key
                    await client.send("signal_update", t, state.signal.model_dump(mode="json"))

                decision = mgr.latest_decision()
                if decision is not None and decision.id != client.last_decision_id:
                    client.last_decision_id = decision.id
                    dump = decision.model_dump(mode="json")
                    await client.send("coordination_update", t, {
                        "coordination": dump["coordination"],
                        "safety": dump["safety"],
                        "applied_phase": dump["applied_phase"],
                        "decision_id": decision.id,
                    })
                    if dump["recommendations"]:
                        await client.send("agent_update", t, agent_update_payload(dump))

                if frame % _METRIC_EVERY == 0:
                    await client.send("metric_update", t,
                                      mgr.latest_metrics().model_dump(mode="json"))
                if frame % _STATUS_EVERY == 0:
                    await client.send("status", t, mgr.status())

                cursor = mgr.event_cursor()
                if cursor > client.event_cursor:
                    for ev in mgr.events_since(client.event_cursor):
                        await client.send("event", ev.t, ev.model_dump(mode="json"))
                    client.event_cursor = cursor

            await asyncio.sleep(interval)
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass
    except Exception:  # noqa: BLE001
        log.error("websocket stream failed", exc_info=True)
    finally:
        client.closed = True
        receiver.cancel()


async def _receive_loop(ws: WebSocket, client: _Client, mgr: Any) -> None:
    """Handle client -> server frames: `command` and `subscribe`."""
    try:
        while True:
            msg = await ws.receive_json()
            kind = msg.get("type")
            if kind == "subscribe":
                channels = msg.get("channels")
                client.channels = set(channels) if channels else None
            elif kind == "command":
                await _handle_command(client, mgr, msg)
            elif kind == "ping":
                await client.send("pong", 0.0, {"server_time": time.time()})
    except (WebSocketDisconnect, RuntimeError, ConnectionError, asyncio.CancelledError):
        pass
    except Exception:  # noqa: BLE001
        log.error("websocket receive failed", exc_info=True)


async def _handle_command(client: _Client, mgr: Any, msg: dict) -> None:
    action = str(msg.get("action", "")).lower()
    args = msg.get("args") or {}
    try:
        result = await asyncio.to_thread(_run_command, mgr, action, args)
    except Exception as exc:  # noqa: BLE001 - reported to the client, never fatal
        await client.send("error", 0.0, {"code": "command_failed", "message": str(exc),
                                         "detail": {"action": action}})
        return
    t = mgr.state().sim_time if mgr.state() else 0.0
    # `manual` and `inject` return command-specific payloads, not a status document.
    # Acknowledge those on their own channel so clients never mistake one for a status.
    if action in _STATUS_COMMANDS:
        await client.send("status", t, result)
    else:
        await client.send("command_result", t, {"action": action, "result": result})
        await client.send("status", t, mgr.status())


# Commands whose return value is a full status document.
_STATUS_COMMANDS = frozenset(
    {"start", "pause", "reset", "set_mode", "set_speed", "step", "load_scenario"}
)


def _run_command(mgr: Any, action: str, args: dict) -> dict:
    if action == "start":
        return mgr.start()
    if action == "pause":
        return mgr.pause()
    if action == "reset":
        return mgr.reset(args.get("scenario_id"), args.get("seed"))
    if action == "set_mode":
        return mgr.set_mode(args["mode"])
    if action == "set_speed":
        return mgr.set_speed(args["speed"])
    if action == "manual":
        return mgr.manual_action(args["action"])
    if action == "inject":
        return mgr.inject(args["event"], args.get("args", {}))
    if action == "step":
        return mgr.step_once(int(args.get("ticks", 1)))
    if action == "load_scenario":
        from app.scenarios import get_scenario

        return mgr.load_scenario(get_scenario(args["id"]), args.get("seed"))
    raise ValueError(f"unknown command '{action}'")
