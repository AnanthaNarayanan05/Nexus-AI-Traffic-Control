# Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `pip install` fails on `torch==2.5.1` | no matching wheel for your Python/OS | use Python 3.11–3.12; for CUDA/other platforms install torch first per <https://pytorch.org>, then `pip install -r backend/requirements.txt` |
| Backend: `ModuleNotFoundError: app` | wrong working dir | run uvicorn with `--app-dir backend`, or from `backend/`: `uvicorn app.main:app` |
| Frontend: blank page, console `WebSocket connection failed` | backend not running or wrong URL | start the backend; check `VITE_WS_URL` in `.env` matches the backend host/port |
| UI shows "SIMULATION DISCONNECTED" banner | WS dropped | it auto-reconnects with backoff; if it persists, check the backend log for a sim-loop exception |
| `NEXUS_SIM_ADAPTER=sumo` → error at startup | SUMO/`libsumo` not installed | install SUMO + set `SUMO_HOME`, `pip install ".[sumo]"` from `backend/`; or set `NEXUS_SIM_ADAPTER=builtin` |
| Vehicles freeze / signal stuck | sim-loop thread died | backend log will show the traceback under `component=SIMULATION`; `POST /api/v1/simulation/reset` |
| Agents always pick the same action | checkpoint not loaded or untrained | `GET /api/v1/models`; load a checkpoint or run `scripts.training.train`; untrained agents are near-random by design |
| Low FPS | too many vehicles / low-end GPU | command bar → quality `MEDIUM`/`LOW` (spec §75); reduce `demand.default_arrivals_vph` |
| pytest: `torch` slow to import on first run | one-time | subsequent runs are cached; use `-q` and select a subdir (`pytest tests/coordination`) |
| Experiment results differ slightly between machines | BLAS / CPU differences in the torch forward pass | expected — see [`experiments.md`](experiments.md) §4; the metric *series* is stable |
| Port 8000 / 5173 in use | another process | `NEXUS_PORT` in `.env`; `vite --port` or edit `vite.config.ts` |

## Logs

- Backend structured logs → stdout (and `logs/nexus.log` if `NEXUS_LOG_LEVEL=DEBUG`). Filter by
  `component` (`SIMULATION`, `A2C`, `DQN`, `PPO`, `COORDINATION`, `SAFETY`, `API`, `EXPERIMENT`,
  `TRAINING`).
- Frontend: browser console; the WS service logs every reconnect and every malformed frame.
- `GET /api/v1/health` returns sim-loop status, adapter, tick rate, connected clients.
