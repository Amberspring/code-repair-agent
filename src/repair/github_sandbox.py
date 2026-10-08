"""Dedicated disposable GitHub worker; local gh credentials never reach generated code."""
import base64
import json
import subprocess
import tempfile
import time
import uuid
from pathlib import Path


class GitHubSandbox:
    def __init__(self, repo):
        self.repo = repo

    def run(self, source, entry, tests):
        if len(source.encode()) > 32000 or not entry.isidentifier() or not 1 <= len(tests) <= 100:
            raise ValueError("Invalid code, entry point or case count")
        encoded = base64.b64encode(json.dumps({"source": source, "entry": entry, "tests": tests}).encode()).decode()
        if len(encoded) > 60000:
            raise ValueError("Workflow payload budget exceeded")
        tag = uuid.uuid4().hex
        def gh(*args):
            return subprocess.run(["gh", *args, "--repo", self.repo], check=True, capture_output=True, text=True, timeout=60).stdout
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.txt"
            path.write_text(encoded, encoding="ascii")
            gh("workflow", "run", "sandbox.yml", "-f", "request_id=" + tag, "-F", "payload=@" + str(path))
            deadline = time.monotonic() + 360
            while time.monotonic() < deadline:
                runs = json.loads(gh("run", "list", "--workflow", "sandbox.yml", "--limit", "30", "--json", "databaseId,displayTitle,status,conclusion,url"))
                match = next((r for r in runs if r["displayTitle"] == "sandbox-" + tag), None)
                if match and match["status"] == "completed":
                    if match["conclusion"] != "success":
                        raise RuntimeError("Sandbox worker failed: " + match["url"])
                    gh("run", "download", str(match["databaseId"]), "-n", "sandbox-result", "-D", directory)
                    result = json.loads((Path(directory) / "sandbox-result.json").read_text(encoding="utf-8"))
                    result["worker_url"] = match["url"]
                    return result
                time.sleep(5)
            raise TimeoutError("GitHub sandbox worker did not complete within 360 seconds")
