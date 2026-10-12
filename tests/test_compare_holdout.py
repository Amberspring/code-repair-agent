import json

import pytest

from scripts.compare_holdout import FROZEN_DATASET_SHA256, compare


def test_paired_holdout_requires_matching_real_run_protocol(tmp_path):
    paths = {name: tmp_path / name for name in ("single", "feedback", "collaborative")}
    for name, path in paths.items():
        path.mkdir()
        summary = {"n": 20, "dataset_sha256": FROZEN_DATASET_SHA256, "model": "Qwen3-8B",
                   "strategy": "collaborative" if name == "collaborative" else "feedback",
                   "iteration_budget": 3 if name == "feedback" else 1, "strong_model": None}
        (path / "summary.json").write_text(json.dumps(summary))
        for i in range(20):
            solved = i < {"single": 5, "feedback": 7, "collaborative": 8}[name]
            metadata = {"repair_model": "Qwen3-8B", "planner_model": "Qwen3-8B",
                        "verifier_model": "Qwen3-8B"}
            row = {"id": f"task-{i}", "status": "complete", "metadata": metadata,
                   "public_passed": solved, "hidden": {"passed": solved, "pass_count": int(solved), "count": 1},
                   "events": [{"type": "patch", "usage": {"total_tokens": 100}}],
                   "model_call_attempts": {"repairer": 1}, "elapsed_seconds": 60}
            (path / f"task-{i}.json").write_text(json.dumps(row))
    result = compare(paths, 1.58)
    assert result["runs"]["single"]["solved"] == 5
    assert result["runs"]["collaborative"]["model_calls"] == 20
    assert result["paired"]["feedback_minus_single"]["mean_solved_delta"] == .1
    assert result["paired"]["collaborative_minus_feedback"]["mean_solved_delta"] == .05
    assert result["runs"]["single"]["estimated_gpu_yuan"] == pytest.approx(20 / 60 * 1.58)
    summary_path = paths["feedback"] / "summary.json"
    summary = json.loads(summary_path.read_text())
    summary["iteration_budget"] = 4
    summary_path.write_text(json.dumps(summary))
    with pytest.raises(ValueError, match="Unexpected strategy"):
        compare(paths)
