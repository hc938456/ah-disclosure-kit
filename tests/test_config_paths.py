from pathlib import Path

from ah_disclosure.core import config


def test_relative_data_dir_is_stable_across_working_directories(monkeypatch, tmp_path: Path):
    project_root = tmp_path / "project"
    other_cwd = tmp_path / "other"
    project_root.mkdir()
    other_cwd.mkdir()
    monkeypatch.setattr(config, "_project_root", lambda: project_root)
    monkeypatch.setattr(
        config,
        "_read_config_file",
        lambda: {"paths": {"data_dir": "./data/ah_disclosure"}},
    )
    monkeypatch.chdir(other_cwd)

    settings = config.get_settings()

    assert settings.data_dir == (project_root / "data" / "ah_disclosure").resolve()


def test_source_checkout_keeps_workspace_data_directory(monkeypatch, tmp_path: Path):
    checkout = tmp_path / "workspace" / "tools" / "ah-disclosure-kit"
    project_root = checkout.parent.parent
    monkeypatch.setattr(config, "_source_checkout_root", lambda: checkout)
    monkeypatch.setattr(config, "_read_config_file", lambda: {})
    monkeypatch.delenv("AH_DISCLOSURE_DATA_DIR", raising=False)
    monkeypatch.delenv("AH_FILINGS_DATA_DIR", raising=False)

    settings = config.get_settings()

    assert settings.data_dir == (project_root / "data" / "ah_disclosure").resolve()


def test_wheel_install_uses_user_data_directory(monkeypatch, tmp_path: Path):
    user_data_root = tmp_path / "user-data" / "ah-disclosure"
    monkeypatch.setattr(config, "_source_checkout_root", lambda: None)
    monkeypatch.setattr(config, "_user_data_root", lambda: user_data_root)
    monkeypatch.setattr(config, "_read_config_file", lambda: {})
    monkeypatch.delenv("AH_DISCLOSURE_DATA_DIR", raising=False)
    monkeypatch.delenv("AH_FILINGS_DATA_DIR", raising=False)

    settings = config.get_settings()

    assert settings.data_dir == (user_data_root / "data").resolve()
