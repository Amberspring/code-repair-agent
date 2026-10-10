import argparse
import ast
import json
import hashlib
from pathlib import Path
from .agent import Model, run, run_collaborative
from .sandbox import DockerSandbox
from .github_sandbox import GitHubSandbox


def complexity_score(task):
    tree = ast.parse(task["buggy"])
    branches = sum(isinstance(node, (ast.If, ast.For, ast.While, ast.Try, ast.BoolOp)) for node in ast.walk(tree))
    return len(task["buggy"].splitlines()) + branches * 3


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", default="data/quixbugs.json")
    p.add_argument("--url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--strong-model", help="route tasks at or above --route-threshold to this model")
    p.add_argument("--strong-url", help="OpenAI-compatible URL for --strong-model; defaults to --url")
    p.add_argument("--route-threshold", type=int, default=30)
    p.add_argument("--strategy", choices=("feedback", "collaborative"), default="feedback")
    p.add_argument("--planner-model")
    p.add_argument("--planner-url")
    p.add_argument("--verifier-model")
    p.add_argument("--verifier-url")
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--output", required=True)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--github-worker", help="owner/repo with sandbox.yml; gh must be authenticated locally")
    a = p.parse_args()
    target = Path(a.output)
    tasks = json.loads(Path(a.tasks).read_text(encoding="utf-8"))
    results = []
    sandbox = GitHubSandbox(a.github_worker) if a.github_worker else DockerSandbox()
    base_model = Model(a.url, a.model)
    strong_model = Model(a.strong_url or a.url, a.strong_model) if a.strong_model else None
    planner = Model(a.planner_url or a.url, a.planner_model or a.model)
    verifier = Model(a.verifier_url or a.url, a.verifier_model or a.model)
    for task in tasks:
        if not task["id"].replace("-", "").isalnum():
            raise ValueError("Invalid task ID")
        score = complexity_score(task)
        selected = strong_model if strong_model and score >= a.route_threshold else base_model
        metadata = {"strategy": a.strategy, "repair_model": selected.model, "complexity_score": score,
                    "route_threshold": a.route_threshold if strong_model else None,
                    "planner_model": planner.model if a.strategy == "collaborative" else None,
                    "verifier_model": verifier.model if a.strategy == "collaborative" else None}
        function = run_collaborative if a.strategy == "collaborative" else run
        args = (task, planner, selected, verifier, sandbox) if a.strategy == "collaborative" else (task, selected, sandbox)
        results.append(function(*args, target / (task["id"] + ".json"), a.iterations, a.resume, metadata))
    n = len(results)
    if not n:
        raise ValueError("No tasks")
    report = {"status": "measured", "model": a.model, "strong_model": a.strong_model, "strategy": a.strategy,
              "iteration_budget": a.iterations, "n": n,
              "sandbox": "github:" + a.github_worker if a.github_worker else "local Docker",
              "dataset_sha256": hashlib.sha256(Path(a.tasks).read_bytes()).hexdigest(),
              "repair_success_rate": sum(r["public_passed"] and r["hidden"]["passed"] for r in results) / n,
              "hidden_test_pass_rate": sum(r["hidden"]["pass_count"] for r in results) / sum(r["hidden"]["count"] for r in results),
              "mean_iterations": sum(r["iterations"] for r in results) / n,
              "mean_seconds": sum(r["elapsed_seconds"] for r in results) / n,
              "model_calls": sum(e["type"] in {"plan", "patch", "verification"} for r in results for e in r["events"]),
              "reported_tokens": sum((e.get("usage") or {}).get("total_tokens", 0) for r in results for e in r["events"] if e["type"] in {"plan", "patch", "verification"}),
              "route_counts": {name: sum(r["metadata"]["repair_model"] == name for r in results)
                               for name in sorted({r["metadata"]["repair_model"] for r in results})},
              "limitations": "See dataset manifest for source and subset selection. Public benchmark may be in pretraining. Hidden tests withheld from prompts, not a tamper-proof grader. Docker shares host kernel; use disposable worker for hostile code. Tokens cover successful API responses only; no inferred monetary cost."}
    (target / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
