"""Import unmodified upstream bugs/tests from one pinned QuixBugs commit."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

COMMIT = "4257f44b0ff1181dedaedee6a447e133219fcebf"
NAMES = ("bitcount", "find_first_in_sorted", "find_in_sorted", "gcd", "is_valid_parenthesization", "max_sublist_sum", "quicksort", "to_base")


def build(source, output):
    source, output = Path(source), Path(output)
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if commit != COMMIT:
        raise ValueError("Checkout the documented pinned commit first")
    if subprocess.check_output(["git", "-C", str(source), "status", "--porcelain"], text=True).strip():
        raise ValueError("Upstream checkout must be clean")
    files, tasks = [], []
    for name in NAMES:
        code_path = source / f"python_programs/{name}.py"
        test_path = source / f"json_testcases/{name}.json"
        code = code_path.read_text(encoding="utf-8")
        cases = [{"args": args, "expected": expected} for args, expected in (json.loads(line) for line in test_path.read_text(encoding="utf-8").splitlines() if line.strip())]
        if len(cases) < 2:
            raise ValueError("Need public and hidden tests")
        tasks.append({"id": name.replace("_", "-"), "entry": name, "description": "Fix the upstream QuixBugs algorithm described in its source docstring.",
                      "buggy": code, "public_tests": cases[:1], "hidden_tests": cases[1:],
                      "source": f"https://github.com/jkoppel/QuixBugs/blob/{COMMIT}/python_programs/{name}.py"})
        for path in (code_path, test_path):
            relative = path.relative_to(source).as_posix()
            files.append({"path": relative, "url": f"https://raw.githubusercontent.com/jkoppel/QuixBugs/{COMMIT}/{relative}", "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(tasks, indent=2), encoding="utf-8")
    output.with_name("QuixBugs-LICENSE.txt").write_bytes((source / "LICENSE").read_bytes())
    manifest = {"source": "https://github.com/jkoppel/QuixBugs", "commit": COMMIT, "license": "MIT", "tasks": len(tasks),
                "selection": "Predeclared eight self-contained JSON-compatible algorithms, not full 40-task benchmark; no new bugs/tests synthesized",
                "test_split": "First upstream test public, remaining tests withheld from model prompts",
                "limitations": "Public benchmark may occur in model pretraining; withheld is not unseen. No correct_python_programs source provided to model.",
                "task_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "files": files}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "files"}))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", required=True)
    p.add_argument("--output", default="data/quixbugs.json")
    a = p.parse_args()
    build(a.source, a.output)
