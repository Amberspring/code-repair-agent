"""Workflow data is decoded, never interpolated into shell or executed on the runner."""
import base64
import json
import os
from pathlib import Path
from repair.sandbox import DockerSandbox

payload = json.loads(base64.b64decode(os.environ["REPAIR_PAYLOAD"], validate=True))
result = DockerSandbox().run(payload["source"], payload["entry"], payload["tests"])
Path("sandbox-result.json").write_text(json.dumps(result), encoding="utf-8")
