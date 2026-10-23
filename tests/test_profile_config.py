"""Port, settings, and CLI wiring for named profiles."""

import os
import sys
from pathlib import Path

import pytest

from aw_server.config import config_section, default_port
from aw_server.main import parse_settings
from aw_server.profile import DEFAULT_PROFILE, TESTING_PROFILE, export_profile
from aw_server.settings import Settings


@pytest.fixture
def xdg_tmp(tmp_path, monkeypatch):
    """Isolate dirs on every OS.

    ``XDG_*_HOME`` only redirects platformdirs on Linux. Windows/macOS keep
    using APPDATA / ~/Library, so a marker planted under the XDG data path
    is invisible there (CI: Test on windows-latest / macOS-latest). Patch
    the same platformdirs getters aw-core tests patch.
    """
    data = tmp_path / "data"
    config = tmp_path / "config"
    cache = tmp_path / "cache"

    def _join(root: Path, appname: str) -> str:
        return str(root / appname)

    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    monkeypatch.setenv("XDG_DATA_HOME", str(data))
    monkeypatch.setenv("XDG_CACHE_HOME", str(cache))
    monkeypatch.setattr(
        "aw_core.dirs.platformdirs.user_data_dir",
        lambda appname, *a, **k: _join(data, appname),
    )
    monkeypatch.setattr(
        "aw_core.dirs.platformdirs.user_config_dir",
        lambda appname, *a, **k: _join(config, appname),
    )
    monkeypatch.setattr(
        "aw_core.dirs.platformdirs.user_cache_dir",
        lambda appname, *a, **k: _join(cache, appname),
    )
    monkeypatch.setattr(
        "aw_core.dirs.platformdirs.user_cache_path",
        lambda appname, *a, **k: cache / appname,
    )
    monkeypatch.setattr(
        "aw_core.dirs.platformdirs.user_log_dir",
        lambda appname, *a, **k: str(cache / appname / "log"),
    )
    monkeypatch.delenv("AW_PROFILE", raising=False)
    return tmp_path


def _plant_legacy_testing_db(xdg_tmp: Path) -> None:
    data = xdg_tmp / "data" / "activitywatch" / "aw-server"
    data.mkdir(parents=True)
    (data / "peewee-sqlite-testing.v2.db").write_text("")


class TestConfigHelpers:
    def test_isolated_roots_use_server_section(self, xdg_tmp, monkeypatch):
        monkeypatch.delenv("AW_PROFILE", raising=False)
        assert config_section("default") == "server"
        monkeypatch.setenv("AW_PROFILE", "testing")
        assert config_section("testing") == "server"
        monkeypatch.setenv("AW_PROFILE", "research")
        assert config_section("research") == "server"

    def test_legacy_testing_keeps_server_testing_section(self, xdg_tmp, monkeypatch):
        _plant_legacy_testing_db(xdg_tmp)
        monkeypatch.setenv("AW_PROFILE", "testing")
        assert config_section("testing") == "server-testing"

    def test_default_ports(self):
        assert default_port(DEFAULT_PROFILE) == 5600
        assert default_port(TESTING_PROFILE) == 5666
        assert default_port("research") == 5600


class TestSettingsFilename:
    def test_legacy_testing_keeps_suffixed_name(self, xdg_tmp, monkeypatch):
        _plant_legacy_testing_db(xdg_tmp)
        monkeypatch.setenv("AW_PROFILE", "testing")
        settings = Settings(True)
        assert settings.config_file.name == "settings-testing.json"

    def test_isolated_testing_uses_bare_name(self, xdg_tmp, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "testing")
        settings = Settings(True)
        assert settings.config_file.name == "settings.json"

    def test_default_unsuffixed(self, xdg_tmp, monkeypatch):
        monkeypatch.delenv("AW_PROFILE", raising=False)
        settings = Settings(False)
        assert settings.config_file.name == "settings.json"

    def test_named_profile_uses_bare_name(self, xdg_tmp, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "research")
        settings = Settings(False)
        assert settings.config_file.name == "settings.json"


class TestParseSettings:
    def test_testing_flag_selects_testing_port(self, xdg_tmp, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["aw-server", "--testing"])
        settings, _storage = parse_settings()
        assert settings.testing is True
        assert settings.profile == TESTING_PROFILE
        assert settings.port == 5666
        assert os.environ["AW_PROFILE"] == "testing"

    def test_profile_testing_is_alias_for_testing_flag(self, xdg_tmp, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["aw-server", "--profile", "testing"])
        settings, _storage = parse_settings()
        assert settings.testing is True
        assert settings.profile == TESTING_PROFILE
        assert settings.port == 5666

    def test_default_keeps_port_5600_and_unsets_env(self, xdg_tmp, monkeypatch):
        monkeypatch.setenv("AW_PROFILE", "research")
        monkeypatch.setattr(sys, "argv", ["aw-server"])
        settings, _storage = parse_settings()
        assert settings.testing is False
        assert settings.profile == DEFAULT_PROFILE
        assert settings.port == 5600
        assert "AW_PROFILE" not in os.environ

    def test_named_profile_exports_env_and_uses_server_section(
        self, xdg_tmp, monkeypatch
    ):
        monkeypatch.setattr(sys, "argv", ["aw-server", "--profile", "research"])
        settings, _storage = parse_settings()
        assert settings.testing is False
        assert settings.profile == "research"
        assert settings.port == 5600
        assert os.environ["AW_PROFILE"] == "research"

    def test_isolated_named_profile_reads_server_section_port(
        self, xdg_tmp, monkeypatch
    ):
        import aw_core.dirs as aw_dirs

        export_profile("research")
        cfg = Path(aw_dirs.get_config_dir("aw-server")) / "aw-server.toml"
        cfg.write_text(
            '[server]\nhost = "localhost"\nport = "5667"\n'
            'storage = "peewee"\ncors_origins = ""\n[server.custom_static]\n'
        )
        monkeypatch.setattr(sys, "argv", ["aw-server", "--profile", "research"])
        settings, _storage = parse_settings()
        assert settings.port == 5667

    def test_cli_port_override(self, xdg_tmp, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["aw-server", "--profile", "research", "--port", "5667"]
        )
        settings, _storage = parse_settings()
        assert settings.port == 5667
        assert settings.profile == "research"

    def test_conflicting_flags_are_a_usage_error(self, xdg_tmp, monkeypatch):
        monkeypatch.setattr(
            sys, "argv", ["aw-server", "--testing", "--profile", "research"]
        )
        with pytest.raises(SystemExit):
            parse_settings()

    def test_invalid_profile_is_a_usage_error(self, xdg_tmp, monkeypatch):
        monkeypatch.setattr(sys, "argv", ["aw-server", "--profile", "Research"])
        with pytest.raises(SystemExit):
            parse_settings()


def test_named_profile_config_is_isolated_from_default(xdg_tmp, monkeypatch):
    """AW_PROFILE must be exported before load_config, else both profiles
    share ~/.config/activitywatch/aw-server."""
    import aw_core.dirs as dirs

    export_profile("research")
    research_dir = dirs.get_config_dir("aw-server")
    export_profile(DEFAULT_PROFILE)
    default_dir = dirs.get_config_dir("aw-server")
    assert research_dir != default_dir
    assert "activitywatch-research" in research_dir
    assert "activitywatch-research" not in default_dir
