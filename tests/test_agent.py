import json
import pytest
from repair.agent import run, run_collaborative, validate_source
from repair.cli import complexity_score


def test_feedback_budget_hidden_isolation_and_resume(tmp_path):
    task = {"id": "a", "description": "absolute", "entry": "absolute", "buggy": "def absolute(x): return x",
            "public_tests": [{"args": [-1], "expected": 1}], "hidden_tests": [{"args": [-987654321], "expected": 987654321}]}
    calls = []

    def model(messages):
        assert "987654321" not in json.dumps(messages)
        calls.append(len(messages))
        return ("def absolute(x): return x" if len(calls) == 1 else "def absolute(x): return abs(x)"), {"total_tokens": 10}

    class SandboxFixture:
        def run(self, code, entry, tests):
            ok = "abs(x)" in code
            return {"passed": ok, "pass_count": int(ok), "count": 1, "error": "negative case failed" if not ok else None}

    checkpoint = tmp_path / "a.json"
    result = run(task, model, SandboxFixture(), checkpoint, 3)
    assert result["public_passed"] and result["hidden"]["passed"] and result["iterations"] == 2
    assert run(task, model, SandboxFixture(), checkpoint, 3, resume=True) == result
    assert len(calls) == 2
    with pytest.raises(FileExistsError):
        run(task, model, SandboxFixture(), checkpoint, 3)
    with pytest.raises(ValueError):
        run({**task, "description": "changed"}, model, SandboxFixture(), checkpoint, 3, resume=True)
    with pytest.raises(ValueError):
        validate_source("def other(): pass", "absolute")


def test_collaborative_roles_are_real_and_hidden_stays_isolated(tmp_path):
    task = {"id": "a", "description": "absolute", "entry": "absolute", "buggy": "def absolute(x): return x",
            "public_tests": [{"args": [-1], "expected": 1}], "hidden_tests": [{"args": [-987654321], "expected": 987654321}]}
    calls = []

    def role(name, answers):
        def invoke(messages):
            assert "987654321" not in json.dumps(messages)
            calls.append(name)
            return answers.pop(0), {"total_tokens": 7}
        return invoke

    planner = role("planner", ["Use abs and preserve the signature."])
    repairer = role("repairer", ["def absolute(x): return abs(x)"])
    verifier = role("verifier", ["APPROVE\nHandles negative values."])

    class SandboxFixture:
        def run(self, code, entry, tests):
            ok = "abs(x)" in code
            return {"passed": ok, "pass_count": int(ok), "count": 1, "error": None if ok else "failed"}

    result = run_collaborative(task, planner, repairer, verifier, SandboxFixture(), tmp_path / "a.json", 2,
                               metadata={"repair_model": "repair"})
    assert calls == ["planner", "repairer", "verifier"]
    assert result["public_passed"] and result["verification_approved"] and result["hidden"]["passed"]
    assert [event["type"] for event in result["events"]] == ["plan", "patch", "feedback", "verification"]


def test_complexity_score_counts_control_flow():
    simple = {"buggy": "def f(x):\n return x"}
    branch = {"buggy": "def f(x):\n if x:\n  return x\n return 0"}
    assert complexity_score(branch) > complexity_score(simple)
