"""Locally staged Qwen variants retain their installed vision projector."""
from types import SimpleNamespace

from hermes_cli.local_runtime import bootstrap, catalog, presets
from hermes_cli.local_runtime.estimator import HardwareBudget, ModelProfile


def test_local_qwen_projector_is_launched_and_priced(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    projector = bootstrap.assets_dir() / "mmproj-F16.gguf"
    projector.parent.mkdir(parents=True, exist_ok=True)
    projector.write_bytes(b"projector")
    monkeypatch.setattr(catalog, "entry_for_model", lambda _: None)
    monkeypatch.setattr(presets, "read_gguf_header", lambda _: SimpleNamespace(sampling_defaults={}))
    monkeypatch.setattr(presets, "profile_from_gguf", lambda _: ModelProfile("local", 1 << 30, 0, 65536, []))
    budget = HardwareBudget(8 << 30, 8 << 30, 8 << 30)
    model = tmp_path / "Qwen3.5-9B-IQ2_M.gguf"
    result = presets.preset_for_model(model, budget, set())
    assert result.keys["mmproj"] == str(projector)
    with_projector = presets.resident_footprint(model, budget, result.window)
    projector.unlink()
    assert "mmproj" not in presets.preset_for_model(model, budget, set()).keys
    assert with_projector - presets.resident_footprint(model, budget, result.window) == len(b"projector")


def test_projector_fallback_is_qwen_specific_and_catalog_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    assets = bootstrap.assets_dir()
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "mmproj-F16.gguf").write_bytes(b"fallback")
    preferred = assets / "catalog-projector.gguf"
    preferred.write_bytes(b"preferred")
    entry = SimpleNamespace(mmproj=SimpleNamespace(local_name=preferred.name, size_bytes=42), mtp_head=None)
    assert presets._companions(None, "unrelated-model").mmproj is None
    companions = presets._companions(entry, "Qwen3.5-9B-IQ2_M")
    assert companions.mmproj == preferred
    assert companions.nbytes == 42
