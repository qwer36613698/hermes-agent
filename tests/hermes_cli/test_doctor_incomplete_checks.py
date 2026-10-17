"""Interrupted diagnostics must never turn into a successful doctor report."""

from argparse import Namespace

import pytest

from hermes_cli import doctor, doctor_live
from hermes_cli.doctor_report import Finding, doctor_check


@pytest.mark.parametrize("on_error", [None, "", "Interrupted check"])
@pytest.mark.parametrize("should_fix", [False, True])
def test_static_crash_is_incomplete_and_later_checks_run(
    monkeypatch, capsys, on_error, should_fix,
):
    visited = []

    @doctor_check(on_error=on_error)
    def interrupted(should_fix, finding):
        finding.manual_issues.append("Preserved manual remedy")
        finding.fixed += int(should_fix)
        raise RuntimeError("diagnostic fixture failure")

    def subsequent(should_fix):
        visited.append("subsequent")
        return Finding()

    monkeypatch.setattr(doctor, "DOCTOR_CHECKS", (
        ("Interrupted section", interrupted), ("Later section", subsequent),
    ))
    result = doctor.run_doctor(Namespace(fix=should_fix, live=False, ack=None))
    output = capsys.readouterr().out

    assert result == 1
    assert visited == ["subsequent"]
    assert "All checks passed" not in output
    assert "Preserved manual remedy" in output
    assert "incomplete" in output.lower()
    assert "interrupted" in output.lower()
    if should_fix:
        assert "Fixed 1 issue(s)" in output


@pytest.mark.parametrize("partial_issue", [False, True])
def test_live_orchestration_crash_is_incomplete(monkeypatch, capsys, partial_issue):
    def interrupted(issues):
        if partial_issue:
            issues.append("Live probe failed: preserved backend failure")
        raise RuntimeError("live diagnostic fixture failure")

    monkeypatch.setattr(doctor, "DOCTOR_CHECKS", ())
    monkeypatch.setattr(doctor_live, "run_live_checks", interrupted)
    result = doctor.run_doctor(Namespace(fix=False, live=True, ack=None))
    output = capsys.readouterr().out

    assert result == 1
    assert "All checks passed" not in output
    assert "incomplete" in output.lower()
    assert "live" in output.lower()
    if partial_issue:
        assert "preserved backend failure" in output
