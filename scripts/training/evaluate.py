"""Evaluate a trained checkpoint against fixed-time and the untrained network.

    python -m scripts.training.evaluate --agent a2c --scenario emergency_heavy \
        --seeds 1,2,3,4,5,6,7,8 --checkpoint models/a2c/latest.pt

Runs three controllers over the same held-out seeds — fixed-time, the agent's
untrained (random-init) network, and the trained checkpoint — prints a comparison
table (mean ± 95% CI half-width, improvement % vs fixed-time) and writes a JSON
report under models/<agent>/. Every number is a real episode measurement (spec §84).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import scripts._bootstrap  # noqa: F401  (sys.path side effect - must precede app imports)

from app.training import AGENT_CLASSES, evaluate, improvement_pct, write_report  # noqa: E402
from app.training.evaluation import METRIC_DIRECTION  # noqa: E402

_HEADLINE = {
    "a2c": ["emergency.emergency_delay_s", "emergency.emergency_wait_s",
            "emergency.emergency_cleared", "traffic.avg_waiting_s",
            "traffic.throughput_vph", "traffic.avg_queue"],
    "dqn": ["environmental.fuel_l_per_veh", "environmental.co2_kg_per_veh",
            "traffic.stops_per_veh", "safety.red_light_violations",
            "safety.other_violations", "traffic.avg_waiting_s"],
    "ppo": ["traffic.avg_queue", "traffic.avg_waiting_s", "traffic.throughput_vph",
            "traffic.avg_travel_time_s", "traffic.avg_speed_mps"],
}


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="python -m scripts.training.evaluate",
                                description="Trained vs fixed-time vs untrained evaluation.")
    p.add_argument("--agent", required=True, choices=sorted(AGENT_CLASSES))
    p.add_argument("--scenario", required=True)
    p.add_argument("--seeds", default="1,2,3,4,5,6,7,8",
                   help="comma-separated eval seeds (default: 1..8)")
    p.add_argument("--checkpoint", default=None,
                   help="trained checkpoint (default: models/<agent>/latest.pt)")
    p.add_argument("--out", default=None, help="report dir (default: models/<agent>/)")
    p.add_argument("--full", action="store_true", help="print every metric, not just headline")
    p.add_argument("--episode-seconds", type=float, default=None,
                   help="override episode length in sim seconds (default: scenario's, 3600)")
    return p.parse_args(argv)


def _fmt(agg: dict) -> str:
    return f"{agg['mean']:>9.3f} +/-{agg['ci_half_width']:<7.3f}"


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    ckpt = Path(args.checkpoint) if args.checkpoint else Path("models") / args.agent / "latest.pt"
    if not ckpt.exists():
        print(f"checkpoint not found: {ckpt}", file=sys.stderr)
        return 2
    out_dir = Path(args.out) if args.out else Path("models") / args.agent

    print(f"evaluating {args.agent.upper()} on '{args.scenario}'  seeds={seeds}\n"
          f"checkpoint: {ckpt}\n", flush=True)

    es = args.episode_seconds
    fixed = evaluate("fixed_time", scenario_id=args.scenario, seeds=seeds, label="fixed_time",
                     episode_seconds=es)
    untrained = evaluate(args.agent, scenario_id=args.scenario, seeds=seeds,
                         label=f"{args.agent} untrained", episode_seconds=es)
    trained = evaluate(args.agent, scenario_id=args.scenario, seeds=seeds, checkpoint=ckpt,
                       episode_seconds=es)
    results = [fixed, untrained, trained]

    keys = list(METRIC_DIRECTION) if args.full else _HEADLINE[args.agent]
    w = 22
    print(f"{'metric':<26} {'dir':>5} {'fixed_time':>{w}} {'untrained':>{w}} "
          f"{trained.label:>{w}}   {'trained vs fixed':>18}")
    print("-" * (26 + 6 + 3 * (w + 1) + 21))
    for k in keys:
        direction = "low" if METRIC_DIRECTION[k] else "high"
        imp = improvement_pct(fixed, trained, k)
        imp_s = "n/a" if imp is None else f"{imp:+.1f}%"
        print(f"{k:<26} {direction:>5} {_fmt(fixed.aggregates[k]):>{w}} "
              f"{_fmt(untrained.aggregates[k]):>{w}} {_fmt(trained.aggregates[k]):>{w}}   "
              f"{imp_s:>18}")

    print(f"\nsafety overrides / episode: fixed {fixed.aggregates['safety_overrides']['mean']:.1f}"
          f"  untrained {untrained.aggregates['safety_overrides']['mean']:.1f}"
          f"  trained {trained.aggregates['safety_overrides']['mean']:.1f}")

    report = write_report(results, out_dir)
    print(f"\nreport: {report}")
    print(f"n={len(seeds)} episodes per controller — CIs are wide at this n; "
          f"treat as indicative, not a significance claim.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
