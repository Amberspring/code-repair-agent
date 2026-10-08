import argparse
import json
import hashlib
from pathlib import Path
from .agent import Model, run
from .sandbox import DockerSandbox
from .github_sandbox import GitHubSandbox


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--tasks", default="data/quixbugs.json")
    p.add_argument("--url", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--iterations", type=int, default=3)
    p.add_argument("--output", required=True)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--github-worker", help="owner/repo with sandbox.yml; gh must be authenticated locally")
    a = p.parse_args()
    target = Path(a.output)
    tasks = json.loads(Path(a.tasks).read_text(encoding="utf-8"))
    results = []
    sandbox = GitHubSandbox(a.github_worker) if a.github_worker else DockerSandbox()
    for task in tasks:
        if not task["id"].replace("-", "").isalnum():
            raise ValueError("Invalid task ID")
        results.append(run(task, Model(a.url, a.model), sandbox, target / (task["id"] + ".json"), a.iterations, a.resume))
    n = len(results)
    if not n:
        raise ValueError("No tasks")
    report = {"status": "measured", "model": a.model, "iteration_budget": a.iterations, "n": n,
              "sandbox": "github:" + a.github_worker if a.github_worker else "local Docker",
              "dataset_sha256": hashlib.sha256(Path(a.tasks).read_bytes()).hexdigest(),
              "repair_success_rate": sum(r["public_passed"] and r["hidden"]["passed"] for r in results) / n,
              "hidden_test_pass_rate": sum(r["hidden"]["pass_count"] for r in results) / sum(r["hidden"]["count"] for r in results),
              "mean_iterations": sum(r["iterations"] for r in results) / n,
              "mean_seconds": sum(r["elapsed_seconds"] for r in results) / n,
              "tool_calls": sum(sum(e["type"] == "feedback" for e in r["events"]) + 1 for r in results),
              "reported_tokens": sum((e.get("usage") or {}).get("total_tokens", 0) for r in results for e in r["events"] if e["type"] == "patch"),
              "limitations": "See dataset manifest for source and subset selection. Public benchmark may be in pretraining. Hidden tests withheld from prompts, not a tamper-proof grader. Docker shares host kernel; use disposable worker for hostile code. Tokens cover successful API responses only; no inferred monetary cost."}
    (target / "summary.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
