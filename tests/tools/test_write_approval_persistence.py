"""Pending writes must not acknowledge proposals that failed to reach disk."""

import importlib
import json

import pytest


@pytest.fixture
def approval_home(tmp_path, monkeypatch):
    from hermes_cli import config

    home = tmp_path / "hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        "memory:\n  write_approval: true\nskills:\n  write_approval: true\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    config._LOAD_CONFIG_CACHE.clear()
    yield home
    config._LOAD_CONFIG_CACHE.clear()


@pytest.mark.parametrize("path", ["memory", "skills", "background_single", "background_batch"])
def test_failed_pending_save_is_not_acknowledged(approval_home, monkeypatch, path):
    from tools import memory_tool, write_approval as wa
    from tools.registry import registry
    from tools.skill_provenance import (
        reset_current_write_origin, reset_review_attended,
        set_current_write_origin, set_review_attended,
    )

    importlib.import_module("tools.skill_manager_tool")

    store = memory_tool.MemoryStore()
    store.load_from_disk()
    assert store.add("memory", "Keep this existing memory.")["success"]
    assert store.add("memory", "Keep this other entry too.")["success"]
    memory_path = approval_home / "memories" / "MEMORY.md"
    before = memory_path.read_bytes()
    # Exercise the real gate and registered handler; only the failing I/O is injected.
    monkeypatch.setattr(wa, "_prompt_inline_memory_approval", lambda *_: None)

    attempts = []
    def fail_write(*args, **kwargs):
        attempts.append(args[0])
        raise OSError("pending storage unavailable")

    monkeypatch.setattr(wa, "atomic_json_write", fail_write)
    origin = set_current_write_origin("background_review" if path.startswith("background") else "foreground")
    attended = set_review_attended(False)
    try:
        if path == "skills":
            payload = {"operations": [{"action": "create", "name": "pending-example", "content":
                "---\nname: pending-example\ndescription: Example procedure\n---\n# Example\nUse the procedure.\n"}]}
            result = registry.get_entry("skill_manage").handler(payload)
        else:
            op = ({"action": "remove", "old_text": "Keep this existing memory."}
                  if path.startswith("background") else {"action": "add", "content": "A new memory."})
            payload = {"operations": [op]} if path == "background_batch" else op
            payload["target"] = "memory"
            result = registry.get_entry("memory").handler(payload, store=store)
    finally:
        reset_review_attended(attended)
        reset_current_write_origin(origin)

    response = json.loads(result)
    assert attempts, response
    assert response.get("success") is False, response
    assert not response.get("staged"), response
    assert not response.get("proposal_staged"), response
    assert "pending_id" not in response, response
    assert wa.list_pending(wa.MEMORY) == []
    assert wa.list_pending(wa.SKILLS) == []
    assert memory_path.read_bytes() == before
    assert store.memory_entries == ["Keep this existing memory.", "Keep this other entry too."]
    assert not (approval_home / "skills" / "pending-example" / "SKILL.md").exists()


@pytest.mark.parametrize("subsystem", ["memory", "skills"])
def test_successful_pending_save_returns_a_reloadable_record(approval_home, subsystem):
    from tools import write_approval as wa

    payload = {"action": "add", "target": "memory", "content": "A durable proposal."}
    record = wa.stage_write(subsystem, payload, summary="Save proposal", origin="foreground")

    assert wa.get_pending(subsystem, record["id"]) == record
    assert record["payload"] == payload
    assert not (approval_home / "memories" / "MEMORY.md").exists()
