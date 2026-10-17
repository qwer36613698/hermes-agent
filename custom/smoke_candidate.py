"""Offline package smoke check. Uses a disposable profile and real package imports."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="hermes-candidate-") as directory:
        root = Path(directory)
        os.environ["HERMES_HOME"] = str(root / "profile")
        os.environ["HERMES_VERIFY_ON_STOP"] = "1"
        from agent import verification_evidence
        from hermes_cli.doctor_report import doctor_check
        from tools import memory_tool, write_approval

        for module in (verification_evidence, memory_tool, write_approval):
            assert Path(module.__file__).resolve().is_relative_to(ROOT), module.__file__
        store = memory_tool.MemoryStore()
        store.load_from_disk()
        assert store.add("memory", "候選版持久化測試")["success"]
        reopened = memory_tool.MemoryStore()
        reopened.load_from_disk()
        assert reopened.memory_entries == ["候選版持久化測試"]
        with patch.object(write_approval, "atomic_json_write", side_effect=OSError("fixture")):
            try:
                write_approval.stage_write("memory", {}, summary="fixture", origin="foreground")
            except OSError:
                pass
            else:
                raise AssertionError("Unsaved proposal was acknowledged")
        assert write_approval.list_pending("memory") == []
        (root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
        assert verification_evidence.classify_verification_command("pytest --collect-only", cwd=root) is None
        evidence = verification_evidence.classify_verification_command("pytest -k smoke", cwd=root)
        assert evidence is not None and evidence.scope == "targeted"

        @doctor_check()
        def interrupted(should_fix, finding):
            raise OSError("fixture")

        assert interrupted(False).incomplete_checks
    print(json.dumps({"ok": True, "checks": ["source-origin", "memory-reload", "staging-failure",
                                             "verification-intent", "doctor-incomplete"]}))


if __name__ == "__main__":
    main()
