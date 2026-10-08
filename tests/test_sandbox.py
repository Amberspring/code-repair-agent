import shutil
import pytest
from repair.sandbox import DockerSandbox


@pytest.mark.skipif(not shutil.which("docker"), reason="Docker unavailable; never substitute host execution")
def test_real_sandbox():
    sandbox = DockerSandbox(timeout=5)
    tests = [{"args": [-2], "expected": 2}]
    assert sandbox.run("def absolute(x): return abs(x)", "absolute", tests)["passed"]
    assert not sandbox.run("def absolute(x): return x", "absolute", tests)["passed"]
    assert sandbox.run("def absolute(x):\n while True: pass", "absolute", tests)["error"] == "timeout"
    assert not sandbox.run("def absolute(x):\n open('/work/candidate.py','w').write('bad')\n return 2", "absolute", tests)["passed"]
    assert not sandbox.run("def absolute(x):\n import socket\n socket.create_connection(('1.1.1.1',80), timeout=1)\n return 2", "absolute", tests)["passed"]
