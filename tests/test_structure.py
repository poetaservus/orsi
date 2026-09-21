from pathlib import Path

from app.capabilities.catalog import build_builtin_registry
from app.settings.agent import AgentFeatureConfig
from app.settings.paths import RuntimePaths


def test_builtin_catalog_has_one_exact_flag_driven_registration_path(tmp_path: Path):
    root = tmp_path / "portable"
    root.mkdir()
    registry = build_builtin_registry(
        AgentFeatureConfig(
            filesystem_stat_enabled=True,
            filesystem_list_enabled=True,
        ),
        application_root=root,
        state_directory=tmp_path / "state",
    )

    assert registry.names == ("filesystem.list", "filesystem.stat")
    assert registry.enabled_names == registry.names
    assert registry.model_visible_names == registry.names


def test_runtime_directory_creation_is_explicit(tmp_path: Path):
    paths = RuntimePaths(
        root=tmp_path,
        config=tmp_path / "config",
        models=tmp_path / "models",
        state=tmp_path / "state",
    )

    assert not any(path.exists() for path in (paths.config, paths.models, paths.state))
    paths.ensure_directories()
    assert all(path.is_dir() for path in (paths.config, paths.models, paths.state))
