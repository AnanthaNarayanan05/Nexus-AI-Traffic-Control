"""Headless evaluation harness — deterministic, safety-authoritative, real aggregates."""

from __future__ import annotations

import pytest

from app.training import evaluate, improvement_pct
from app.training.evaluation import METRIC_DIRECTION, compare, write_report

ES = 180.0
SEEDS = [1, 2, 3]


def test_fixed_time_eval_is_deterministic():
    a = evaluate("fixed_time", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    b = evaluate("fixed_time", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    assert [e.metrics for e in a.episodes] == [e.metrics for e in b.episodes]
    assert a.model_version is None
    # fixed-time never trips the safety layer on the ring schedule
    assert a.aggregates["safety_overrides"]["mean"] == 0.0


def test_agent_eval_is_deterministic_and_untrained_by_default():
    a = evaluate("a2c", scenario_id="emergency_heavy", seeds=SEEDS, episode_seconds=ES)
    b = evaluate("a2c", scenario_id="emergency_heavy", seeds=SEEDS, episode_seconds=ES)
    assert a.model_version == "untrained"
    assert [e.metrics for e in a.episodes] == [e.metrics for e in b.episodes]


def test_aggregates_have_every_metric_key():
    r = evaluate("fixed_time", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    for key in METRIC_DIRECTION:
        assert key in r.aggregates
        agg = r.aggregates[key]
        assert {"n", "mean", "median", "std", "min", "max", "ci_half_width"} <= set(agg)
        assert agg["n"] == len(SEEDS)


def test_trained_checkpoint_loads_and_changes_behaviour(tmp_path):
    from app.training import TrainingManager

    mgr = TrainingManager("a2c", episodes=3, scenario="emergency_heavy", seed=42,
                          out_dir=tmp_path, episode_seconds=ES)
    mgr.run()
    ckpt = tmp_path / "a2c" / "latest.pt"

    untrained = evaluate("a2c", scenario_id="emergency_heavy", seeds=SEEDS, episode_seconds=ES)
    trained = evaluate("a2c", scenario_id="emergency_heavy", seeds=SEEDS,
                       checkpoint=ckpt, episode_seconds=ES)

    assert trained.model_version != "untrained"
    assert trained.checkpoint == str(ckpt)
    # the trained policy is a different controller — at least one metric moves
    assert any(
        untrained.mean(k) != trained.mean(k) for k in METRIC_DIRECTION
    )


def test_improvement_pct_sign_follows_metric_direction():
    fixed = evaluate("fixed_time", scenario_id="emergency_heavy", seeds=SEEDS, episode_seconds=ES)
    untrained = evaluate("a2c", scenario_id="emergency_heavy", seeds=SEEDS, episode_seconds=ES)

    # untrained A2C is much worse than fixed-time on waiting → negative improvement
    imp = improvement_pct(fixed, untrained, "traffic.avg_waiting_s")
    if fixed.mean("traffic.avg_waiting_s") > 0.01 and untrained.mean("traffic.avg_waiting_s") > fixed.mean("traffic.avg_waiting_s"):
        assert imp is not None and imp < 0


def test_compare_blob_shape():
    fixed = evaluate("fixed_time", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    untrained = evaluate("ppo", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    blob = compare([fixed, untrained], baseline_label="fixed_time")
    assert blob["baseline"] == "fixed_time"
    assert blob["n_episodes"] == len(SEEDS)
    row = blob["metrics"]["traffic.avg_queue"]
    assert row["lower_is_better"] is True
    assert row["values"]["fixed_time"]["improvement_pct_vs_baseline"] is None
    assert "mean" in row["values"][untrained.label]


def test_write_report_round_trips(tmp_path):
    import json

    fixed = evaluate("fixed_time", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
    path = write_report([fixed], tmp_path)
    assert path.exists()
    payload = json.loads(path.read_text())
    assert payload["comparison"]["baseline"] == "fixed_time"
    assert len(payload["results"][0]["episodes"]) == len(SEEDS)


def test_unknown_controller_rejected():
    with pytest.raises(KeyError):
        evaluate("greedy", scenario_id="normal", seeds=SEEDS, episode_seconds=ES)
