"""Export serialisers (R9 P4, spec §23, §64-79).

`app/api/exporters.py` is pure: dict record -> CSV / JSON string. It must never invent a
number - every cell traces back to the stored record (spec §84). These tests pin the
shape of the CSV (one tidy row per metric x controller for experiments; one row per
decision for replays) and the filename sanitisation.
"""

from __future__ import annotations

import csv
import io
import json

from app.api.exporters import (
    experiment_csv,
    experiment_rows,
    replay_csv,
    replay_rows,
    safe_filename,
)

EXPERIMENT = {
    "id": "exp-20260908T120000000Z",
    "scenario": "normal",
    "status": "completed",
    "comparison": {
        "baseline": "fixed_time",
        "metrics": {
            "traffic.avg_waiting_s": {
                "lower_is_better": True,
                "values": {
                    "fixed_time": {"mean": 40.0, "improvement_pct_vs_baseline": None},
                    "a2c v1.4": {"mean": 30.0, "improvement_pct_vs_baseline": 25.0},
                },
            },
            "traffic.throughput_vph": {
                "lower_is_better": False,
                "values": {
                    "fixed_time": {"mean": 900.0, "improvement_pct_vs_baseline": None},
                    "a2c v1.4": {"mean": 850.0, "improvement_pct_vs_baseline": -5.6},
                },
            },
        },
    },
    "results": [
        {
            "label": "fixed_time",
            "controller": "fixed_time",
            "model_mode": "fixed_time",
            "model_version": None,
            "aggregates": {
                "traffic.avg_waiting_s": {"n": 3, "mean": 40.0, "median": 39.0,
                                          "std": 4.0, "min": 36.0, "max": 45.0,
                                          "ci_half_width": 2.0},
                "traffic.throughput_vph": {"n": 3, "mean": 900.0, "median": 905.0,
                                           "std": 20.0, "min": 880.0, "max": 920.0,
                                           "ci_half_width": 10.0},
            },
        },
        {
            "label": "a2c v1.4",
            "controller": "a2c",
            "model_mode": "active",
            "model_version": "a2c-v1.4-dev",
            "aggregates": {
                "traffic.avg_waiting_s": {"n": 3, "mean": 30.0, "median": 30.0,
                                          "std": 5.0, "min": 25.0, "max": 35.0,
                                          "ci_half_width": 3.0},
                "traffic.throughput_vph": {"n": 3, "mean": 850.0, "median": 850.0,
                                           "std": 15.0, "min": 835.0, "max": 865.0,
                                           "ci_half_width": 8.0},
            },
        },
    ],
}

REPLAY = {
    "id": "replay-20260908T120000Z-abc123",
    "timeline": [
        {
            "t": 6.0, "step": 12, "applied_phase": "NS",
            "coordination": {"candidate_phase": "NS", "winner": "a2c",
                             "basis": "weighted_score"},
            "safety": {"action_taken": "APPLIED", "approved": True,
                       "violated_rules": []},
            "rewards": {"a2c": 0.5, "dqn": -0.2},
            "metrics": {"traffic": {"avg_waiting_s": 12.3, "avg_queue": 4.0},
                        "safety": {"red_light_violations": 1}},
        },
        {
            "t": 12.0, "step": 24, "applied_phase": "YELLOW",
            "coordination": {"candidate_phase": "EW", "winner": "dqn",
                             "basis": "stability"},
            "safety": {"action_taken": "REWRITTEN_TRANSITION", "approved": False,
                       "violated_rules": ["min_green", "phase_order"]},
            "rewards": {"a2c": -0.1, "dqn": 0.3},
            "metrics": {"traffic": {"avg_waiting_s": 15.0}},
        },
    ],
}


def _parse(text: str) -> list[dict]:
    return list(csv.DictReader(io.StringIO(text)))


# --------------------------------------------------------------------- experiments
def test_experiment_rows_are_one_per_metric_per_controller():
    rows = experiment_rows(EXPERIMENT)
    assert len(rows) == 2 * 2  # 2 metrics x 2 controllers
    waiting_a2c = next(
        r for r in rows
        if r["metric"] == "traffic.avg_waiting_s" and r["controller"] == "a2c"
    )
    assert waiting_a2c["mean"] == 30.0
    assert waiting_a2c["median"] == 30.0
    assert waiting_a2c["std"] == 5.0
    assert waiting_a2c["improvement_pct_vs_baseline"] == 25.0
    assert waiting_a2c["is_baseline"] is False
    assert waiting_a2c["lower_is_better"] is True
    assert waiting_a2c["model_mode"] == "active"


def test_experiment_baseline_row_has_no_improvement():
    rows = experiment_rows(EXPERIMENT)
    base = next(r for r in rows if r["label"] == "fixed_time"
               and r["metric"] == "traffic.avg_waiting_s")
    assert base["is_baseline"] is True
    assert base["improvement_pct_vs_baseline"] is None


def test_experiment_csv_header_and_values():
    text = experiment_csv(EXPERIMENT)
    parsed = _parse(text)
    assert parsed[0].keys() >= {
        "experiment_id", "scenario", "metric", "controller", "mean", "median",
        "std", "min", "max", "ci_half_width", "improvement_pct_vs_baseline",
    }
    thr = next(r for r in parsed if r["metric"] == "traffic.throughput_vph"
              and r["controller"] == "a2c")
    assert thr["mean"] == "850.0"
    assert thr["improvement_pct_vs_baseline"] == "-5.6"
    assert thr["lower_is_better"] == "False"


def test_experiment_export_never_invents_a_metric():
    # a metric absent from the record must not appear in the export
    text = experiment_csv(EXPERIMENT)
    assert "emergency.emergency_delay_s" not in text


# --------------------------------------------------------------------- replays
def test_replay_rows_track_the_authoritative_phase_change():
    rows = replay_rows(REPLAY)
    assert len(rows) == 2
    assert rows[0]["safety_changed_phase"] is False
    assert rows[0]["candidate_phase"] == rows[0]["applied_phase"] == "NS"
    # frame 2: coordinator wanted EW, safety forced a YELLOW transition
    assert rows[1]["candidate_phase"] == "EW"
    assert rows[1]["applied_phase"] == "YELLOW"
    assert rows[1]["safety_changed_phase"] is True
    assert rows[1]["safety_action"] == "REWRITTEN_TRANSITION"
    assert rows[1]["violated_rules"] == "min_green;phase_order"


def test_replay_csv_has_a_reward_column_per_agent_and_flat_metrics():
    text = replay_csv(REPLAY)
    parsed = _parse(text)
    assert "reward.a2c" in parsed[0] and "reward.dqn" in parsed[0]
    assert parsed[0]["reward.a2c"] == "0.5"
    assert parsed[0]["traffic.avg_waiting_s"] == "12.3"
    assert parsed[0]["safety.red_light_violations"] == "1"
    # a metric missing from a frame is blank, not zero (no fabrication)
    assert parsed[1]["traffic.avg_queue"] == ""


def test_replay_csv_is_stable_when_timeline_is_empty():
    text = replay_csv({"id": "replay-empty", "timeline": []})
    assert text.splitlines()[0].startswith("replay_id,index,t,step")
    assert len(text.splitlines()) == 1  # header only


# --------------------------------------------------------------------- filenames
def test_safe_filename_strips_path_separators_and_dodgy_chars():
    assert safe_filename("experiment-exp-1", "csv") == "experiment-exp-1.csv"
    assert safe_filename("../../etc/passwd", "json") == "etc-passwd.json"
    assert safe_filename("", "csv") == "export.csv"


def test_to_json_round_trips_the_record():
    from app.api.exporters import to_json

    assert json.loads(to_json(EXPERIMENT))["id"] == EXPERIMENT["id"]
