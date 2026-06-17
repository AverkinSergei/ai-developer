import os

from app.clients.fakes import FakeGitLab


async def test_fetch_archive_writes_files(tmp_path):
    gl = FakeGitLab(files={"grp/repo": {"app/main.py": "print('hi')", "README.md": "# x"}})
    root = await gl.fetch_archive("grp/repo", "dev", str(tmp_path))
    assert os.path.exists(os.path.join(root, "app/main.py"))
    assert os.path.exists(os.path.join(root, "README.md"))


async def test_draft_mr_and_open_mr_lookup():
    gl = FakeGitLab()
    assert await gl.find_open_mr("grp/repo", "auto-task-1") is None
    mr = await gl.create_draft_mr("grp/repo", "auto-task-1", "dev", "t", "d")
    assert mr["draft"] is True
    found = await gl.find_open_mr("grp/repo", "auto-task-1")
    assert found is not None and found["iid"] == mr["iid"]


async def test_member_role_lookup():
    gl = FakeGitLab()
    gl.roles[("grp/repo", "u1")] = "maintainer"
    assert await gl.get_project_member_role("grp/repo", "u1") == "maintainer"
    assert await gl.get_project_member_role("grp/repo", "u2") is None
