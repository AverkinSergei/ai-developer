"""CLI ai-developer. Команда построения графов целевых репозиториев.

    ai-developer build-graph grp/repo-a grp/repo-b [--ref main]

Требует GRAPH_CACHE_DIR и доступ к GitLab (GITLAB_URL/GITLAB_TOKEN).
"""

import argparse
import asyncio
import sys

from app.clients.gitlab_client import GitLab
from app.config import settings
from app.graph_build import GraphBuildError, build_repo_graph


async def _build_graphs(repos: list[str], ref: str | None) -> int:
    if not settings.graph_cache_dir:
        print("Ошибка: GRAPH_CACHE_DIR не задан.", file=sys.stderr)
        return 2
    gitlab = GitLab()
    failures = 0
    for repo in repos:
        try:
            dest = await build_repo_graph(repo, gitlab=gitlab, ref=ref)
            print(f"OK  {repo} -> {dest}")
        except GraphBuildError as exc:
            failures += 1
            print(f"FAIL {repo}: {exc}", file=sys.stderr)
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ai-developer")
    sub = parser.add_subparsers(dest="command", required=True)

    bg = sub.add_parser("build-graph", help="Построить граф(ы) кода в GRAPH_CACHE_DIR")
    bg.add_argument("repos", nargs="+", help="репозитории вида namespace/project")
    bg.add_argument("--ref", default=None, help="ветка/sha (по умолчанию FORK_BASE_BRANCH)")

    args = parser.parse_args(argv)
    if args.command == "build-graph":
        return asyncio.run(_build_graphs(args.repos, args.ref))
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
