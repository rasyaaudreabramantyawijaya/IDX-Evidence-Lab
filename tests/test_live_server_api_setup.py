import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / ".vscode/settings.json"
TASKS = ROOT / ".vscode/tasks.json"
RUNNER = ROOT / "scripts/run_portfolio_api_sidecar.py"


def _load_runner():
    spec = importlib.util.spec_from_file_location("portfolio_api_sidecar", RUNNER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_live_server_proxies_only_api_prefix_to_loopback_sidecar():
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))

    assert settings["liveServer.settings.proxy"] == {
        "enable": True,
        "baseUri": "/api",
        "proxyUri": "http://127.0.0.1:5501/api",
    }


def test_sidecar_task_starts_on_folder_open_and_has_ready_matcher():
    tasks = json.loads(TASKS.read_text(encoding="utf-8"))
    task = next(item for item in tasks["tasks"] if item["label"] == "IDX Evidence Lab: Local API (5501)")

    assert task["runOptions"]["runOn"] == "folderOpen"
    assert task["isBackground"] is True
    assert "READY: IDX Evidence Lab API" in task["problemMatcher"]["background"]["endsPattern"]


def test_healthy_existing_sidecar_exits_without_launching_duplicate(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(runner, "api_is_healthy", lambda: True)

    def unexpected_spawn(*_args, **_kwargs):
        raise AssertionError("healthy API must not spawn another listener")

    monkeypatch.setattr(runner.subprocess, "Popen", unexpected_spawn)

    assert runner.main() == 0
    assert "already healthy" in capsys.readouterr().out


def test_unrelated_service_on_sidecar_port_is_not_stopped(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(runner, "api_is_healthy", lambda: False)
    monkeypatch.setattr(runner, "port_is_free", lambda _host, _port: False)

    def unexpected_spawn(*_args, **_kwargs):
        raise AssertionError("occupied port must not spawn or stop a process")

    monkeypatch.setattr(runner.subprocess, "Popen", unexpected_spawn)

    assert runner.main() == 1
    assert "5501" in capsys.readouterr().err


def test_sidecar_startup_failure_returns_nonzero(monkeypatch, capsys):
    runner = _load_runner()
    monkeypatch.setattr(runner, "api_is_healthy", lambda: False)
    monkeypatch.setattr(runner, "port_is_free", lambda _host, _port: True)
    monkeypatch.setattr(runner.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner.time, "monotonic", lambda: 100.0)

    class FailedChild:
        def poll(self):
            return 1

    monkeypatch.setattr(runner.subprocess, "Popen", lambda *_args, **_kwargs: FailedChild())

    assert runner.main() == 1
    assert "failed before readiness" in capsys.readouterr().err
