"""Port, settings, and CLI wiring for named profiles."""

import os
import sys

import pytest

from aw_server.config import config_section, default_port
from aw_server.main import parse_settings
from aw_server.profile import DEFAULT_PROFILE, TESTING_PROFILE, export_profile
from aw_server.settings import Settings


@pytest.fixture
def xdg_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.delenv("AW_PROFILE", raising=False)
    return tmp_path


class TestConfigHelpers:
    def test_sections_are_disjoint(self):
        sections = {config_section(p) for p in ("default", "testing", "research")}
        assert sections == {"server", "server-testing", "server-research"}

    def test_default_ports(self):
        assert default_port(DEFAULT_PROFILE) == 5600
        assert default_port(TESTING_PROFILE) == 5666
        assert default_port("research") == 5600


class TestSettingsFilename:
    def test_testing_keeps_legacy_name(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "aw_server.settings.get_config_dir", lambda module: str(tmp_path)
        )
        monkeypatch.delenv("AW_PROFILE", raising=False)
        settings = Settings(True)
        assert settings.config_file.name == "settings-testing.json"

    def test_default_unsuffixed(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "aw_server.settings.get_config_dir", lambda module: str(tmp_path)
        )
        monkeypatch.delenv("AW_PROFILE", raising=False)
        settings = Settings(False)
        assert settings.config_file.name == "settings.json"

    def test_named_profile_suffix(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "aw_server.settings.get_config_dir", lambda module: str(tmp_path)
        )
        monkeypatch.setenv("AW_PROFILE", "research")
        settings = Settings(False)
        assert settings.config_file.name == "settings-research.json"


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

    def test_named_profile_exports_env_and_falls_back_to_server_section(
        self, xdg_tmp, monkeypatch
    ):
        monkeypatch.setattr(sys, "argv", ["aw-server", "--profile", "research"])
        settings, _storage = parse_settings()
        assert settings.testing is False
        assert settings.profile == "research"
        assert settings.port == 5600
        assert os.environ["AW_PROFILE"] == "research"

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
