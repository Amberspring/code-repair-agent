import json
import pytest
from repair.agent import run, validate_source


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
