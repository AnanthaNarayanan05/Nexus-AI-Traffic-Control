"""Populate the model registry from training-run JSON records already on disk.

    python -m scripts.training.backfill_registry            # all agents
    python -m scripts.training.backfill_registry --agent a2c

For each ``models/<agent>/<run_id>.json`` it registers the final checkpoint, and if a
newer ``models/<agent>/eval-*.json`` exists whose comparison scenario matches, attaches
that evaluation too. Idempotent - re-running re-upserts the same rows.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import scripts._bootstrap  # noqa: F401  (sys.path side effect - must precede app imports)

from app.persistence import ModelRegistry  # noqa: E402
from app.training import AGENT_CLASSES  # noqa: E402

MODELS_DIR = Path("models")


def _run_records(agent: str) -> list[Path]:
    d = MODELS_DIR / agent
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob(f"{agent}-*.json") if not p.name.startswith("eval-"))


def _latest_eval(agent: str) -> dict | None:
    evals = sorted((MODELS_DIR / agent).glob("eval-*.json"))
    if not evals:
        return None
    return json.loads(evals[-1].read_text(encoding="utf-8"))


def backfill(agent: str, reg: ModelRegistry) -> int:
    n = 0
    latest_eval = _latest_eval(agent)
    for rec_path in _run_records(agent):
        rec = json.loads(rec_path.read_text(encoding="utf-8"))
        repro = rec.get("reproducibility", {})
        episodes = len(rec.get("episode_returns", []))
        model_id = f"{rec['run_id']}-ep{episodes:03d}"
        reg.register(
            model_id=model_id,
            agent=agent,
            version=rec.get("final_model_version") or f"{agent}-loaded",
            checkpoint_path=rec.get("final_checkpoint", ""),
            run_id=rec["run_id"],
            scenario=rec.get("scenario", ""),
            seed=int(rec.get("seed", 0)),
            episodes=episodes,
            training_config=repro.get("rl_hyperparams", {}),
            reward_config=repro.get("reward_weights", {}),
            env_version=repro.get("config_digest", ""),
            code_version=repro.get("git_commit"),
            torch_version=repro.get("torch_version"),
            created_at=rec.get("finished_at") or rec.get("started_at"),
        )
        print(f"registered {model_id}")
        n += 1

        cmp = (latest_eval or {}).get("comparison", {})
        if cmp and cmp.get("scenario") == rec.get("scenario"):
            reg.attach_evaluation(model_id, scenario=cmp["scenario"], metrics=cmp)
            print(f"  + attached evaluation ({cmp['scenario']})")
    return n


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m scripts.training.backfill_registry")
    p.add_argument("--agent", choices=sorted(AGENT_CLASSES), default=None)
    args = p.parse_args(argv)

    reg = ModelRegistry()
    agents = [args.agent] if args.agent else sorted(AGENT_CLASSES)
    total = sum(backfill(a, reg) for a in agents)
    print(f"\n{total} model record(s) in the registry for: {', '.join(agents)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
