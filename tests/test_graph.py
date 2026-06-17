import json

from app.clients.fakes import FakeGraph, FakeLLM
from app.clients.graph import GraphifyGraph, resolve_graph_path
from app.config import Settings
from app.context_engine import ContextEngine
from app.contracts import TaskCard
from app.planning import explore_and_plan

GRAPH = {
    "nodes": [
        {"id": "auth", "name": "AuthModule", "summary": "handles login and sessions"},
        {"id": "db", "name": "Database", "summary": "stores users"},
        {"id": "api", "name": "API", "summary": "http endpoints"},
    ],
    "edges": [
        {"source": "auth", "target": "db"},
        {"source": "api", "target": "auth"},
    ],
}


def _write_graph(tmp_path) -> str:
    path = tmp_path / "graph.json"
    path.write_text(json.dumps(GRAPH), encoding="utf-8")
    return str(path)


async def test_query_finds_relevant_node(tmp_path):
    g = GraphifyGraph(_write_graph(tmp_path))
    assert g.available
    out = await g.query("login sessions")
    assert "AuthModule" in out


async def test_path_between_nodes(tmp_path):
    g = GraphifyGraph(_write_graph(tmp_path))
    route = await g.path("API", "Database")
    assert route == ["API", "AuthModule", "Database"]


async def test_explain_node(tmp_path):
    g = GraphifyGraph(_write_graph(tmp_path))
    out = await g.explain("AuthModule")
    assert "login" in out
    assert "Database" in out  # связь


async def test_missing_graph_is_unavailable():
    g = GraphifyGraph("/nonexistent/graph.json")
    assert g.available is False
    assert await g.query("anything") == ""
    assert await g.path("a", "b") == []


def test_resolve_graph_path_cache_then_checkout(tmp_path):
    # кэш по repo
    cache = tmp_path / "cache"
    (cache / "grp_repo").mkdir(parents=True)
    (cache / "grp_repo" / "graph.json").write_text("{}")
    found = resolve_graph_path("grp/repo", None, str(cache))
    assert found.endswith("grp_repo/graph.json")

    # fallback на checkout/graphify-out
    root = tmp_path / "checkout"
    (root / "graphify-out").mkdir(parents=True)
    (root / "graphify-out" / "graph.json").write_text("{}")
    found2 = resolve_graph_path("x/y", str(root), "")
    assert found2.endswith("graphify-out/graph.json")

    assert resolve_graph_path("none", None, "") is None


async def test_plan_includes_graph_hint(tmp_path):
    (tmp_path / "a.py").write_text("x")
    engine = ContextEngine(str(tmp_path))
    graph = FakeGraph(answers={"добавить логин": "GRAPHHINT: смотри AuthModule"})
    llm = FakeLLM(
        responses=[
            json.dumps(
                {
                    "changes": [{"path": "app/x.py", "action": "create", "rationale": "r"}],
                    "doc_impact": "no",
                    "doc_skip_reason": "internal",
                }
            )
        ]
    )
    card = TaskCard(
        task_id="B24-1",
        task_type="feature",
        target_repo="grp/repo",
        affected_area=["backend"],
        business_goal="добавить логин",
    )
    await explore_and_plan(card, engine, llm, Settings(), graph=graph)
    # подсказка графа попала в промпт планировщика
    content = llm.calls[0]["messages"][0]["content"]
    assert "GRAPHHINT: смотри AuthModule" in content
    assert "graph_hint_untrusted" in content


async def test_plan_without_graph_still_works(tmp_path):
    engine = ContextEngine(str(tmp_path))
    llm = FakeLLM(
        responses=[
            json.dumps(
                {
                    "changes": [{"path": "app/x.py", "action": "create", "rationale": "r"}],
                    "doc_impact": "no",
                    "doc_skip_reason": "internal",
                }
            )
        ]
    )
    card = TaskCard(
        task_id="B24-1", task_type="feature", target_repo="grp/repo", affected_area=["backend"]
    )
    gate = await explore_and_plan(card, engine, llm, Settings())
    assert gate.risk_level in ("low", "medium")
