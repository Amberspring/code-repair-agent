import base64
import json
from types import SimpleNamespace
from pathlib import Path
from repair.github_sandbox import GitHubSandbox


def test_worker_data_is_file_input_not_shell_and_url_is_preserved(monkeypatch):
    tag = []
    def invoke(command, **kwargs):
        assert isinstance(command, list) and not kwargs.get("shell")
        if command[1:3] == ["workflow", "run"]:
            tag.append(command[command.index("-f") + 1].split("=", 1)[1])
            path = command[command.index("-F") + 1].split("@", 1)[1]
            payload = json.loads(base64.b64decode(Path(path).read_text()))
            assert payload["source"] == "def f(): return '$(unsafe)'"
            return SimpleNamespace(stdout="")
        if command[2] == "list":
            return SimpleNamespace(stdout=json.dumps([{"displayTitle": "sandbox-" + tag[0], "databaseId": 1,
                "status": "completed", "conclusion": "success", "url": "https://fixture/run/1"}]))
        Path(command[command.index("-D") + 1], "sandbox-result.json").write_text('{"passed":true,"count":1,"pass_count":1}')
        return SimpleNamespace(stdout="")
    monkeypatch.setattr("subprocess.run", invoke)
    result = GitHubSandbox("owner/repo").run("def f(): return '$(unsafe)'", "f", [{"args": [], "expected": "$(unsafe)"}])
    assert result["passed"] and result["worker_url"] == "https://fixture/run/1"
