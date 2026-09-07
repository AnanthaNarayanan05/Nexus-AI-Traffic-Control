"""Train one RL agent headlessly and checkpoint it.

    python -m scripts.training.train --agent a2c --episodes 200
    python -m scripts.training.train --agent ppo --episodes 300 --scenario rush_hour --seed 7

Writes checkpoints + a run-metrics JSON under ``models/<agent>/`` (see docs/training.md).
Every number printed comes from a real episode and a real gradient step (spec section 84).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import scripts._bootstrap  # noqa: F401  (sys.path side effect - must precede app imports)

from app.training import AGENT_CLASSES, DEFAULT_SCENARIO, TrainingManager  # noqa: E402
from app.training.environment import EpisodeResult  # noqa: E402


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="python -m scripts.training.train",
        description="Headless single-agent RL training.",
    )
    p.add_argument("--agent", required=True, choices=sorted(AGENT_CLASSES),
                   help="which policy to train")
    p.add_argument("--episodes", type=int, default=200,
                   help="number of episodes (default: 200)")
    p.add_argument("--scenario", default=None,
                   help=f"scenario preset id (default per agent: {DEFAULT_SCENARIO})")
    p.add_argument("--seed", type=int, default=None,
                   help="base seed; episode N uses seed+(N-1) (default: config simulation.seed)")
    p.add_argument("--checkpoint-every", type=int, default=25,
                   help="checkpoint cadence in episodes (default: 25)")
    p.add_argument("--episode-seconds", type=float, default=None,
                   help="override episode length in sim seconds (default: scenario's, 3600)")
    p.add_argument("--out", default=None,
                   help="models directory (default: config models_dir)")
    return p.parse_args(argv)


def _print_episode(r: EpisodeResult) -> None:
    loss = " ".join(f"{k}={v:+.3f}" for k, v in r.losses.items()) or "(no update yet)"
    print(
        f"  ep {r.index:>4}  return={r.episode_return:>+10.2f}  "
        f"mean_r={r.mean_reward:>+7.3f}  decisions={r.decisions:>4}  "
        f"updates={r.updates:>3}  safety_overrides={r.safety_overrides:>3}  "
        f"{r.wall_time_s:>6.1f}s   {loss}",
        flush=True,
    )


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mgr = TrainingManager(
        args.agent,
        episodes=args.episodes,
        scenario=args.scenario,
        seed=args.seed,
        checkpoint_every=args.checkpoint_every,
        out_dir=Path(args.out) if args.out else None,
        episode_seconds=args.episode_seconds,
    )
    print(
        f"training {mgr.agent_name.upper()}  scenario={mgr.scenario_id}  "
        f"episodes={mgr.episodes}  base_seed={mgr.seed}  run_id={mgr.run_id}",
        flush=True,
    )
    run = mgr.run(on_episode=_print_episode)

    returns = run.episode_returns
    print(f"\ndone in {run.wall_time_s:.1f}s")
    w = min(5, len(returns) // 2)
    if w:
        first = sum(returns[:w]) / w
        last = sum(returns[-w:]) / w
        print(
            f"mean return: first{w}={first:+.2f} -> last{w}={last:+.2f}  "
            f"(delta {last - first:+.2f})"
        )
    print(f"final checkpoint: {run.final_checkpoint}")
    print(f"latest:           {mgr.out_dir / 'latest.pt'}")
    print(f"run metrics:      {mgr.out_dir / (run.run_id + '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
