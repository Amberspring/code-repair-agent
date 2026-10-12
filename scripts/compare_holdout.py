"""Pair completed single-agent and collaborative runs on the same frozen tasks."""

import argparse
import hashlib
import json
import random
from pathlib import Path

FROZEN_DATASET_SHA256 = "df923e80d5a6e168756b0854134368b2fc5f6dab14311e0ee786424d6c610255"


def load_run(path):
    summary_path = path / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    cases = {}
    for file in path.glob("*.json"):
        if file.name == "summary.json":
            continue
        row = json.loads(file.read_text(encoding="utf-8"))
        if row["status"] != "complete" or row["id"] in cases or "hidden" not in row:
            raise ValueError(f"Incomplete or duplicate task: {file}")
        metadata = row.get("metadata", {})
        if metadata.get("repair_model") != summary["model"] or (
            summary.get("strategy") == "collaborative" and
            (metadata.get("planner_model") != summary["model"] or metadata.get("verifier_model") != summary["model"])
        ):
            raise ValueError(f"Model assignment differs from fixed comparison: {file}")
        calls = [event for event in row["events"] if event["type"] in {"plan", "patch", "verification"}]
        attempts = row.get("model_call_attempts")
        if not isinstance(attempts, dict) or not all(isinstance(n, int) and n >= 0 for n in attempts.values()):
            raise ValueError(f"Model call attempts missing: {file}")
        call_count = sum(attempts.values())
        reported = sum(isinstance(event.get("usage"), dict) and
                       isinstance(event["usage"].get("total_tokens"), int) for event in calls)
        if reported > call_count:
            raise ValueError(f"More model responses than attempts: {file}")
        cases[row["id"]] = {
            "solved": bool(row["public_passed"] and row["hidden"]["passed"]),
            "hidden_pass": row["hidden"]["pass_count"], "hidden_count": row["hidden"]["count"],
            "model_calls": call_count,
            "reported_tokens": sum(value for event in calls if isinstance(event.get("usage"), dict)
                                   and isinstance(value := event["usage"].get("total_tokens"), int)),
            "missing_usage_calls": call_count - reported, "elapsed_seconds": row["elapsed_seconds"],
        }
    if len(cases) != summary["n"]:
        raise ValueError(f"Task count differs from summary: {path}")
    return summary, cases, hashlib.sha256(summary_path.read_bytes()).hexdigest()


def paired_delta(left, right, ids, samples=5000):
    differences = [int(right[key]["solved"]) - int(left[key]["solved"]) for key in ids]
    rng = random.Random(20261012)
    boot = sorted(sum(rng.choice(differences) for _ in ids) / len(ids) for _ in range(samples))
    return {"mean_solved_delta": sum(differences) / len(ids),
            "bootstrap_95_ci": [boot[int(.025 * samples)], boot[int(.975 * samples)]],
            "improved_tasks": sum(n > 0 for n in differences), "regressed_tasks": sum(n < 0 for n in differences)}


def compare(paths, gpu_yuan_per_hour=None):
    if gpu_yuan_per_hour is not None and gpu_yuan_per_hour <= 0:
        raise ValueError("GPU hourly price must be positive")
    loaded = {name: load_run(path) for name, path in paths.items()}
    summaries = [part[0] for part in loaded.values()]
    if len({row["dataset_sha256"] for row in summaries}) != 1 or len({row["model"] for row in summaries}) != 1:
        raise ValueError("Dataset or base model differs between runs")
    if summaries[0]["dataset_sha256"] != FROZEN_DATASET_SHA256:
        raise ValueError("Run is not the frozen QuixBugs holdout")
    for name, strategy, budget in (("single", "feedback", 1), ("feedback", "feedback", 3),
                                   ("collaborative", "collaborative", 1)):
        summary = loaded[name][0]
        if summary.get("strategy", "feedback") != strategy or summary["iteration_budget"] != budget or summary.get("strong_model"):
            raise ValueError(f"Unexpected strategy, budget or routed model: {name}")
    ids = sorted(loaded["single"][1])
    if any(sorted(part[1]) != ids for part in loaded.values()):
        raise ValueError("Runs must have identical task IDs")
    if any(part[0]["n"] != 20 for part in loaded.values()):
        raise ValueError("Formal comparison requires the frozen 20-task holdout")
    results = {}
    for name, (summary, cases, digest) in loaded.items():
        calls = sum(row["model_calls"] for row in cases.values())
        missing = sum(row["missing_usage_calls"] for row in cases.values())
        seconds = sum(row["elapsed_seconds"] for row in cases.values())
        results[name] = {"summary_sha256": digest, "strategy": summary.get("strategy", "feedback"),
                         "iteration_budget": summary["iteration_budget"], "solved": sum(row["solved"] for row in cases.values()),
                         "hidden_pass_rate": sum(row["hidden_pass"] for row in cases.values()) / sum(row["hidden_count"] for row in cases.values()),
                         "model_calls": calls, "reported_tokens": sum(row["reported_tokens"] for row in cases.values()),
                         "missing_usage_calls": missing, "sum_elapsed_seconds": seconds,
                         "estimated_gpu_yuan": seconds / 3600 * gpu_yuan_per_hour if gpu_yuan_per_hour is not None else None,
                         "cases": cases}
    return {"dataset_sha256": summaries[0]["dataset_sha256"], "model": summaries[0]["model"], "n": len(ids),
            "gpu_yuan_per_hour_for_estimate": gpu_yuan_per_hour,
            "cost_limitations": "GPU cost is estimated from summed task wall time only; actual AutoDL bill and shared-service overhead must be reported separately.",
            "runs": results,
            "paired": {"feedback_minus_single": paired_delta(loaded["single"][1], loaded["feedback"][1], ids),
                       "collaborative_minus_single": paired_delta(loaded["single"][1], loaded["collaborative"][1], ids),
                       "collaborative_minus_feedback": paired_delta(loaded["feedback"][1], loaded["collaborative"][1], ids)}}


def main():
    parser = argparse.ArgumentParser()
    for name in ("single", "feedback", "collaborative", "output"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--gpu-yuan-per-hour", type=float)
    args = parser.parse_args()
    output = Path(args.output)
    if output.exists():
        raise FileExistsError(output)
    report = compare({name: Path(getattr(args, name)) for name in ("single", "feedback", "collaborative")},
                     args.gpu_yuan_per_hour)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"paired": report["paired"], "solved": {name: row["solved"] for name, row in report["runs"].items()}}))


if __name__ == "__main__":
    main()
