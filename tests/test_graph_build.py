import json
import os

import pytest

from app.cli import main
from app.clients.fakes import FakeGitLab
from app.config import settings
from app.graph_build import GraphBuildError, build_repo_graph, sync_repo_graph


def _fake_runner_that_builds():
    async def runner(cmd: str, cwd: str) -> None:
        out = os.path.join(cwd, "graphify-out")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "graph.json"), "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            json.dump({"nodes": [], "edges": []}, fh)

    return runner


async def test_build_repo_graph_writes_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path / "tmp"))
    cache = tmp_path / "cache"
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    dest = await build_repo_graph(
        "grp/repo", gitlab=gl, cache_dir=str(cache), ref="main", runner=_fake_runner_that_builds()
    )
    assert dest == str(cache / "grp_repo" / "graph.json")
    assert os.path.isfile(dest)


async def test_build_fails_when_no_graph_produced(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path / "tmp"))
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    async def noop_runner(cmd: str, cwd: str) -> None:
        return None

    with pytest.raises(GraphBuildError):
        await build_repo_graph(
            "grp/repo", gitlab=gl, cache_dir=str(tmp_path / "cache"), runner=noop_runner
        )


async def test_build_requires_cache_dir(tmp_path):
    gl = FakeGitLab()
    with pytest.raises(GraphBuildError):
        await build_repo_graph("grp/repo", gitlab=gl, cache_dir="")


def test_cli_build_graph_requires_cache(monkeypatch):
    monkeypatch.setattr(settings, "graph_cache_dir", "")
    rc = main(["build-graph", "grp/repo"])
    assert rc == 2


def _recording_runner():
    calls: list[str] = []

    async def runner(cmd: str, cwd: str) -> None:
        calls.append(cmd)
        out = os.path.join(cwd, "graphify-out")
        os.makedirs(out, exist_ok=True)
        with open(os.path.join(out, "graph.json"), "w", encoding="utf-8") as fh:  # noqa: ASYNC230
            json.dump({"nodes": [], "edges": []}, fh)

    return runner, calls


def _seed_cache(cache, repo="grp/repo"):
    dest_dir = os.path.join(str(cache), repo.replace("/", "_"))
    os.makedirs(dest_dir, exist_ok=True)
    with open(os.path.join(dest_dir, "graph.json"), "w", encoding="utf-8") as fh:
        json.dump({"nodes": [{"id": "old"}], "edges": []}, fh)
    return os.path.join(dest_dir, "graph.json")


def _wire(monkeypatch, tmp_path, *, refresh, auto, cache="cache"):
    monkeypatch.setattr(settings, "agent_tmp_dir", str(tmp_path / "tmp"))
    monkeypatch.setattr(settings, "graph_cache_dir", str(tmp_path / cache))
    monkeypatch.setattr(settings, "graph_refresh_on_task", refresh)
    monkeypatch.setattr(settings, "graph_auto_build", auto)


async def test_sync_refreshes_existing_each_task(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, refresh=True, auto=True)
    _seed_cache(tmp_path / "cache")
    runner, calls = _recording_runner()
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    path = await sync_repo_graph("grp/repo", gitlab=gl, runner=runner)
    assert path and os.path.isfile(path)
    assert len(calls) == 1  # граф пересобран, несмотря на наличие в кэше


async def test_sync_builds_when_missing(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, refresh=False, auto=True)
    runner, calls = _recording_runner()
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    path = await sync_repo_graph("grp/repo", gitlab=gl, runner=runner)
    assert path and os.path.isfile(path)
    assert len(calls) == 1


async def test_sync_no_rebuild_when_disabled_and_present(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, refresh=False, auto=True)
    existing = _seed_cache(tmp_path / "cache")
    runner, calls = _recording_runner()
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    path = await sync_repo_graph("grp/repo", gitlab=gl, runner=runner)
    assert path == existing
    assert calls == []  # не пересобираем


async def test_sync_failure_falls_back_to_stale(tmp_path, monkeypatch):
    _wire(monkeypatch, tmp_path, refresh=True, auto=True)
    existing = _seed_cache(tmp_path / "cache")
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "# x\n"}})

    async def broken_runner(cmd: str, cwd: str) -> None:
        return None  # graphify-out/graph.json не создан -> GraphBuildError

    path = await sync_repo_graph("grp/repo", gitlab=gl, runner=broken_runner)
    assert path == existing  # фолбэк на устаревший кэш, задача не падает


async def test_sync_no_cache_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "graph_cache_dir", "")
    gl = FakeGitLab()
    assert await sync_repo_graph("grp/repo", gitlab=gl) is None
