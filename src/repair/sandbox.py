"""Never execute generated code on the host. Expected outputs remain outside the container."""
import json
import subprocess
import tempfile
import threading
import uuid
from pathlib import Path

HARNESS = '''import contextlib, importlib.util, json, sys
payload = json.load(sys.stdin)
with open('/dev/null', 'w') as sink, contextlib.redirect_stdout(sink), contextlib.redirect_stderr(sink):
    spec = importlib.util.spec_from_file_location('candidate', '/work/candidate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = [getattr(module, payload['entry'])(*args) for args in payload['inputs']]
print(json.dumps(result, allow_nan=False))
'''


class DockerSandbox:
    def __init__(self, image="python:3.12-slim", timeout=10):
        if not 0 < timeout <= 60:
            raise ValueError("Sandbox timeout must be 0..60 seconds")
        self.image, self.timeout = image, timeout

    def run(self, source, entry, tests):
        if len(source.encode()) > 32000 or not entry.isidentifier() or not 1 <= len(tests) <= 100:
            raise ValueError("Invalid code, entry point or case count")
        payload = json.dumps({"entry": entry, "inputs": [t["args"] for t in tests]}).encode()
        if len(payload) > 32000:
            raise ValueError("Test input budget exceeded")
        name = "repair-" + uuid.uuid4().hex
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.py"
            path.write_text(source, encoding="utf-8")
            command = ["docker", "run", "--rm", "--pull=never", "--name", name, "--network=none",
                       "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--user=65534:65534",
                       "--memory=256m", "--memory-swap=256m", "--cpus=1", "--pids-limit=32",
                       "--ulimit", "nofile=64:64", "--tmpfs", "/tmp:rw,noexec,nosuid,size=16m",
                       "--mount", f"type=bind,source={path.resolve()},target=/work/candidate.py,readonly",
                       "-i", self.image, "python", "-I", "-B", "-c", HARNESS]
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            chunks, size, overflow = [], [0], threading.Event()

            def read_output():
                while data := process.stdout.read(4096):
                    size[0] += len(data)
                    if size[0] > 65536:
                        overflow.set()
                        process.kill()
                        break
                    chunks.append(data)

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            timed_out = False
            try:
                process.stdin.write(payload)
                process.stdin.close()
                process.wait(timeout=self.timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                process.kill()
                process.wait()
            except BrokenPipeError:
                process.kill()
                process.wait()
            finally:
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                reader.join(timeout=2)
                if process.poll() is None:
                    process.kill()
                    process.wait()
            text = b"".join(chunks).decode(errors="replace")
            if timed_out or overflow.is_set() or process.returncode:
                return {"passed": False, "pass_count": 0, "count": len(tests), "error": "timeout" if timed_out else "output_limit" if overflow.is_set() else text[-2000:]}
            try:
                values = json.loads(text)
                if not isinstance(values, list) or len(values) != len(tests):
                    raise ValueError("Invalid sandbox result count")
                passed = [type(v) is type(t["expected"]) and v == t["expected"] for v, t in zip(values, tests)]
                return {"passed": all(passed), "pass_count": sum(passed), "count": len(tests),
                        "failures": [{"args": t["args"], "expected": t["expected"], "actual": v} for t, v, ok in zip(tests, values, passed) if not ok]}
            except (ValueError, TypeError) as e:
                return {"passed": False, "pass_count": 0, "count": len(tests), "error": str(e)}
