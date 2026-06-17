import os

import pytest

from app.context_engine import ContextEngine, SandboxError, is_safe_repo_path


def test_is_safe_repo_path():
    assert is_safe_repo_path("app/main.py")
    assert is_safe_repo_path("a/b/c.txt")
    assert not is_safe_repo_path("/etc/passwd")
    assert not is_safe_repo_path("../x.py")
    assert not is_safe_repo_path("a/../../x")
    assert not is_safe_repo_path(".env")
    assert not is_safe_repo_path("a/.git/config")
    assert not is_safe_repo_path("")


@pytest.fixture
def repo(tmp_path):
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("def handler():\n    return TOKEN\n")
    (tmp_path / "README.md").write_text("# project\nuses auth module\n")
    (tmp_path / ".env").write_text("SECRET=abc")
    (tmp_path / "key.pem").write_text("-----BEGIN-----")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("[core]")
    # секрет снаружи корня
    outside = tmp_path.parent / "outside_secret.txt"
    outside.write_text("TOPSECRET")
    return tmp_path, outside


def test_list_dir_hides_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    entries = eng.list_dir(".")
    assert "app/" in entries
    assert "README.md" in entries
    assert ".env" not in entries
    assert ".git/" not in entries
    assert "key.pem" not in entries


def test_read_file_ok(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    assert "handler" in eng.read_file("app/main.py")


def test_read_env_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file(".env")


def test_read_pem_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file("key.pem")


def test_read_git_internal_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file(".git/config")


def test_absolute_path_denied(repo):
    root, outside = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file(str(outside))


def test_path_traversal_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file("../outside_secret.txt")
    with pytest.raises(SandboxError):
        eng.list_dir("../..")


def test_symlink_escape_denied(repo):
    root, outside = repo
    link = root / "escape.txt"
    os.symlink(str(outside), str(link))
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file("escape.txt")


def test_symlink_dir_escape_denied(repo):
    root, _ = repo
    link = root / "escape_dir"
    os.symlink(str(root.parent), str(link))
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.list_dir("escape_dir")


def test_read_dir_as_file_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    with pytest.raises(SandboxError):
        eng.read_file("app")


def test_read_too_large_denied(repo):
    root, _ = repo
    (root / "big.txt").write_text("x" * 5000)
    eng = ContextEngine(str(root), max_read_bytes=1000)
    with pytest.raises(SandboxError):
        eng.read_file("big.txt")


def test_grep_finds_and_skips_denied(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    hits = eng.grep("auth")
    assert any(h.path == "README.md" for h in hits)
    # секреты и .git не сканируются
    assert all(".env" not in h.path and ".git" not in h.path for h in hits)


def test_grep_glob_filter(repo):
    root, _ = repo
    eng = ContextEngine(str(root))
    hits = eng.grep("return", glob="*.py")
    assert hits and all(h.path.endswith(".py") for h in hits)
