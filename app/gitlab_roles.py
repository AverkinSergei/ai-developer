"""Резолвер maintainer-роли для авторизации high-risk /go.

Маппит проверку прав на роль пользователя в GitLab-проекте.
"""

from app.clients.protocols import GitLabClient
from app.orchestrator import MaintainerResolver

_MAINTAINER_ROLES = {"maintainer", "owner"}


def make_maintainer_resolver(gitlab: GitLabClient) -> MaintainerResolver:
    async def resolve(repo: str, user_id: str) -> bool:
        role = await gitlab.get_project_member_role(repo, user_id)
        return role in _MAINTAINER_ROLES

    return resolve
