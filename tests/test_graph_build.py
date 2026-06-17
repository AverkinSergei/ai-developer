import json
import os

import pytest

from app.cli import main
from app.clients.fakes import FakeGitLab
from app.config import settings
from app.graph_build import GraphBuildError, build_repo_graph


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
