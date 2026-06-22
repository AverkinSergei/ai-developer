import pytest

from app.config import settings
from app.sandbox_exec import run_check, run_checks


@pytest.fixture(autouse=True)
def _confirm_isolation(monkeypatch):
    # Большинство тестов прогоняют реальные команды — подтверждаем изоляцию.
    monkeypatch.setattr(settings, "sandbox_isolation_confirmed", True)


async def test_passing_command(tmp_path):
    r = await run_check("test", 'python3 -c "import sys; sys.exit(0)"', str(tmp_path))
    assert r.ok and r.status == "passed" and r.returncode == 0


async def test_failing_command(tmp_path):
    r = await run_check("test", 'python3 -c "import sys; sys.exit(1)"', str(tmp_path))
    assert not r.ok and r.status == "failed" and r.returncode == 1


async def test_refuses_non_allowlisted_binary(tmp_path):
    r = await run_check("evil", "rm -rf /", str(tmp_path))
    assert r.status == "refused"


async def test_refused_without_isolation_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sandbox_isolation_confirmed", False)
    r = await run_check("test", 'python3 -c "import sys; sys.exit(0)"', str(tmp_path))
    assert r.status == "refused"
    assert "isolation" in r.output


async def test_chaining_is_neutralized_by_no_shell(tmp_path):
    # shell=False: `; rm` уходит литеральными argv в python и НЕ исполняется как команда.
    marker = tmp_path / "victim.txt"
    marker.write_text("alive")
    await run_check("chain", 'python3 -c "print(1)" ; rm -rf victim.txt', str(tmp_path))
    assert marker.exists()  # rm не выполнился — цепочка через оболочку невозможна


async def test_empty_command_skipped(tmp_path):
    assert (await run_check("lint", None, str(tmp_path))).status == "skipped"
    assert (await run_check("lint", "   ", str(tmp_path))).status == "skipped"


async def test_timeout(tmp_path):
    r = await run_check(
        "slow", 'python3 -c "import time; time.sleep(5)"', str(tmp_path), timeout_sec=1
    )
    assert r.status == "timeout"


async def test_service_secrets_not_leaked(tmp_path, monkeypatch):
    # Секрет в окружении сервиса не должен попасть в дочерний процесс проверки.
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak")
    r = await run_check(
        "probe",
        "python3 -c \"import os; print(os.environ.get('OPENAI_API_KEY','MISSING'))\"",
        str(tmp_path),
    )
    assert r.ok
    assert "MISSING" in r.output
    assert "sk-should-not-leak" not in r.output


async def test_output_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "sandbox_max_output_kb", 1)  # 1 KiB лимит
    r = await run_check("noisy", "python3 -c \"print('x' * 100000)\"", str(tmp_path))
    assert not r.ok and r.status == "failed"  # превышение лимита -> провал
    assert "truncated" in r.output


async def test_runs_in_checkout_cwd(tmp_path):
    (tmp_path / "marker.txt").write_text("hi")
    r = await run_check(
        "ls", "python3 -c \"import os; print(os.path.exists('marker.txt'))\"", str(tmp_path)
    )
    assert "True" in r.output


async def test_run_checks_batch(tmp_path):
    results = await run_checks(
        {
            "test": 'python3 -c "import sys; sys.exit(0)"',
            "lint": None,
            "typecheck": "rm -rf /",
        },
        str(tmp_path),
    )
    assert results["test"].status == "passed"
    assert results["lint"].status == "skipped"
    assert results["typecheck"].status == "refused"
