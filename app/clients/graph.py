"""Навигация по персистентному графу кода graphify (graph.json).

Граф строится один раз на репозиторий офлайн (`graphify <repo> --update`) и читается
здесь без внешних процессов — query/path/explain реализованы поверх graph.json. Если графа
для репозитория нет, объект «недоступен» и фаза Explore & Plan опирается только на safe-tools.

Содержимое графа происходит из недоверенного репозитория — для планирования это лишь
навигационная подсказка, не источник истины.
"""

import json
import os
from collections import deque


def resolve_graph_path(repo: str, checkout_root: str | None, cache_dir: str) -> str | None:
    """Ищет graph.json: сначала в кэше графов по repo, затем в checkout/graphify-out."""
    candidates: list[str] = []
    if cache_dir:
        candidates.append(os.path.join(cache_dir, repo.replace("/", "_"), "graph.json"))
    if checkout_root:
        candidates.append(os.path.join(checkout_root, "graphify-out", "graph.json"))
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None


class GraphifyGraph:
    def __init__(self, graph_path: str | None) -> None:
        self._path = graph_path
        self._loaded = False
        self._nodes: dict[str, dict] = {}  # id -> {name, summary}
        self._adj: dict[str, set[str]] = {}  # id -> соседи (неориентированно)
        self._name_to_id: dict[str, str] = {}

    @property
    def available(self) -> bool:
        self._ensure_loaded()
        return bool(self._nodes)

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self._path or not os.path.isfile(self._path):
            return
        try:
            with open(self._path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            return

        for node in data.get("nodes") or []:
            nid = str(node.get("id") or node.get("name") or node.get("label") or "")
            if not nid:
                continue
            name = str(node.get("name") or node.get("label") or node.get("title") or nid)
            summary = str(node.get("summary") or node.get("description") or node.get("text") or "")
            self._nodes[nid] = {"name": name, "summary": summary}
            self._adj.setdefault(nid, set())
            self._name_to_id.setdefault(name.lower(), nid)

        edges = data.get("edges") or data.get("links") or []
        for edge in edges:
            src = str(edge.get("source") or edge.get("src") or edge.get("from") or "")
            dst = str(edge.get("target") or edge.get("dst") or edge.get("to") or "")
            if src in self._nodes and dst in self._nodes:
                self._adj[src].add(dst)
                self._adj[dst].add(src)

    def _resolve_id(self, name_or_id: str) -> str | None:
        self._ensure_loaded()
        if name_or_id in self._nodes:
            return name_or_id
        return self._name_to_id.get(name_or_id.lower())

    async def query(self, question: str, budget: int = 1500) -> str:
        """Релевантные узлы по терминам вопроса + их непосредственные связи (BFS-широта)."""
        self._ensure_loaded()
        if not self._nodes:
            return ""
        terms = {t for t in question.lower().split() if len(t) > 2}
        scored: list[tuple[int, str]] = []
        for nid, node in self._nodes.items():
            haystack = f"{node['name']} {node['summary']}".lower()
            score = sum(1 for t in terms if t in haystack)
            if score:
                scored.append((score, nid))
        scored.sort(reverse=True)

        max_chars = budget * 4
        lines: list[str] = []
        used = 0
        for _, nid in scored[:8]:
            node = self._nodes[nid]
            neighbors = ", ".join(self._nodes[n]["name"] for n in list(self._adj[nid])[:5])
            line = f"- {node['name']}: {node['summary'][:160]}"
            if neighbors:
                line += f" (связи: {neighbors})"
            if used + len(line) > max_chars:
                break
            lines.append(line)
            used += len(line)
        return "\n".join(lines)

    async def path(self, src: str, dst: str) -> list[str]:
        """Кратчайший путь между узлами (BFS по связям). Имена узлов в порядке маршрута."""
        self._ensure_loaded()
        a = self._resolve_id(src)
        b = self._resolve_id(dst)
        if not a or not b:
            return []
        if a == b:
            return [self._nodes[a]["name"]]
        prev: dict[str, str] = {a: a}
        queue = deque([a])
        while queue:
            cur = queue.popleft()
            for nxt in self._adj.get(cur, ()):
                if nxt not in prev:
                    prev[nxt] = cur
                    if nxt == b:
                        chain = [b]
                        while chain[-1] != a:
                            chain.append(prev[chain[-1]])
                        return [self._nodes[i]["name"] for i in reversed(chain)]
                    queue.append(nxt)
        return []

    async def explain(self, node: str) -> str:
        """Краткое описание узла и его связей."""
        self._ensure_loaded()
        nid = self._resolve_id(node)
        if not nid:
            return ""
        data = self._nodes[nid]
        neighbors = ", ".join(self._nodes[n]["name"] for n in list(self._adj[nid])[:8])
        out = f"{data['name']}: {data['summary']}"
        if neighbors:
            out += f"\nСвязи: {neighbors}"
        return out
