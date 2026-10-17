"""Only executed checks are evidence; filtered pytest runs remain targeted."""

import pytest

from agent.verification_evidence import record_terminal_result, verification_status
from agent.verification_command_intent import verification_intent


@pytest.mark.parametrize("recipe,args,expected", [
    ("python -m pytest", ["-q"], (True, False)),
    ("pytest -ksmoke", [], (True, True)),
    ("scripts/run_tests.sh", ["--collect-only"], (False, False)),
])
def test_runner_prefix_and_recipe_filters(recipe, args, expected):
    assert verification_intent(recipe, args) == expected


@pytest.mark.parametrize("command", [
    "pytest --collect-only", "python -m pytest --co", "pytest --help",
    "pytest --version", "pytest --setup-plan",
])
def test_discovery_commands_do_not_mark_workspace_passed(tmp_path, monkeypatch, command):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "1")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    event = record_terminal_result(command=command, cwd=tmp_path, session_id="intent", exit_code=0)

    assert event is None
    assert verification_status(session_id="intent", cwd=tmp_path)["status"] == "unverified"


@pytest.mark.parametrize("args,scope", [
    ("-k smoke", "targeted"), ("-m unit", "targeted"),
    ("--deselect=tests/test_slow.py::test_slow", "targeted"),
    ("--ignore=tests/integration", "targeted"), ("-q", "full"),
])
def test_filtered_checks_keep_their_actual_scope(tmp_path, monkeypatch, args, scope):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("HERMES_VERIFY_ON_STOP", "1")
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")

    event = record_terminal_result(command=f"pytest {args}", cwd=tmp_path, session_id="intent", exit_code=0)

    assert event is not None
    status = verification_status(session_id="intent", cwd=tmp_path)
    assert status["status"] == "passed"
    assert status["evidence"]["scope"] == scope
