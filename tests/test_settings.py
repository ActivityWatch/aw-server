"""Atomic settings persistence and actionable errors when saving fails.

All tests use a temporary config directory; the real user config is never touched.
"""

import errno
import json
import logging
import os
import stat

import pytest

from aw_server.server import AWFlask
from aw_server.settings import Settings

SETTINGS_FILE = "settings-testing.json"


@pytest.fixture
def config_dir(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    monkeypatch.setattr("aw_server.settings.get_config_dir", lambda module: str(config))
    monkeypatch.delenv("AW_PROFILE", raising=False)
    return config


def _settings_path(config_dir):
    return config_dir / SETTINGS_FILE


def _write_initial(config_dir, data=None):
    if data is None:
        data = {"locale": "en"}
    path = _settings_path(config_dir)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _dir_entries(config_dir):
    return sorted(p.name for p in config_dir.iterdir())


def _partial_dump(obj, fp, **kwargs):
    # Simulates running out of disk space part-way through serialization.
    fp.write('{"locale":')
    raise OSError(errno.ENOSPC, "No space left on device")


def test_settings_save_keeps_previous_file_on_partial_write(config_dir, monkeypatch):
    path = _write_initial(config_dir)
    settings = Settings(testing=True)
    monkeypatch.setattr("json.dump", _partial_dump)

    with pytest.raises(OSError):
        settings.set("locale", "sv")

    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "en"}
    assert settings.get("locale") == "en"
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_settings_round_trip_new_file(config_dir):
    path = _settings_path(config_dir)
    assert not path.exists()

    settings = Settings(testing=True)
    assert settings.get("locale") is None
    settings.set("locale", "sv")
    settings.set("theme", {"dark": True})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "locale": "sv",
        "theme": {"dark": True},
    }
    reloaded = Settings(testing=True)
    assert reloaded.get("locale") == "sv"
    assert reloaded.get("theme") == {"dark": True}
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_failed_replace_keeps_old_file_memory_and_temp(config_dir, monkeypatch):
    path = _write_initial(config_dir)
    settings = Settings(testing=True)
    before = dict(settings.get("", {}))

    def denied(src, dst):
        # Windows reports a file held open by another process as a PermissionError.
        raise PermissionError(errno.EACCES, "Access is denied", dst)

    monkeypatch.setattr("os.replace", denied)

    with pytest.raises(PermissionError):
        settings.set("locale", "sv")

    assert json.loads(path.read_text(encoding="utf-8")) == before
    assert settings.get("locale") == "en"
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_replace_happens_only_after_complete_serialized_temp_is_closed(
    config_dir, monkeypatch
):
    path = _write_initial(config_dir)
    settings = Settings(testing=True)
    seen = {}
    real_replace = os.replace

    def checking_replace(src, dst):
        # The temp file must be fully written and closed before the rename, which
        # is what allows Windows to replace it.
        with open(src, encoding="utf-8") as f:
            seen["content"] = json.load(f)
        real_replace(src, dst)

    monkeypatch.setattr("os.replace", checking_replace)
    settings.set("locale", "sv")

    assert seen["content"] == {"locale": "sv"}
    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "sv"}
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_serialization_failure_preserves_file_and_memory(config_dir):
    path = _write_initial(config_dir)
    settings = Settings(testing=True)

    class Unserializable:
        pass

    with pytest.raises(TypeError):
        settings.set("locale", Unserializable())

    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "en"}
    assert settings.get("locale") == "en"
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_deletion_rollback_on_failed_save(config_dir, monkeypatch):
    path = _write_initial(config_dir, {"locale": "sv"})
    settings = Settings(testing=True)
    snapshot = settings.get("")

    def denied(src, dst):
        raise PermissionError(errno.EACCES, "Access is denied", dst)

    monkeypatch.setattr("os.replace", denied)

    with pytest.raises(PermissionError):
        settings.set("locale", None)

    assert settings.get("locale") == "sv"
    assert snapshot == {"locale": "sv"}
    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "sv"}
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


def test_falsy_value_deletes_key_on_success(config_dir):
    path = _write_initial(config_dir, {"locale": "sv", "theme": "dark"})
    settings = Settings(testing=True)

    settings.set("locale", "")
    settings.set("missing", None)

    assert settings.get("locale") is None
    assert json.loads(path.read_text(encoding="utf-8")) == {"theme": "dark"}


def test_failed_save_does_not_mutate_previous_snapshot(config_dir, monkeypatch):
    _write_initial(config_dir)
    settings = Settings(testing=True)
    snapshot = settings.get("")
    monkeypatch.setattr("json.dump", _partial_dump)

    with pytest.raises(OSError):
        settings.set("locale", "sv")

    assert snapshot == {"locale": "en"}


def test_startup_warns_when_existing_file_not_writable(config_dir, monkeypatch, caplog):
    path = _write_initial(config_dir)
    real_access = os.access

    def fake_access(p, mode, *args, **kwargs):
        # Stubbed rather than chmod-based so the test holds when run as root.
        if os.fspath(p) == os.fspath(path) and mode & os.W_OK:
            return False
        return real_access(p, mode, *args, **kwargs)

    monkeypatch.setattr("os.access", fake_access)

    with caplog.at_level(logging.WARNING, logger="aw_server.settings"):
        settings = Settings(testing=True)

    assert settings.get("locale") == "en"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any(str(path) in r.getMessage() for r in warnings)


def test_no_startup_warning_when_file_writable_or_missing(config_dir, caplog):
    with caplog.at_level(logging.WARNING, logger="aw_server.settings"):
        Settings(testing=True)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]

    _write_initial(config_dir)
    with caplog.at_level(logging.WARNING, logger="aw_server.settings"):
        Settings(testing=True)
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_read_only_existing_file_is_not_replaced(config_dir, monkeypatch):
    path = _write_initial(config_dir)
    settings = Settings(testing=True)
    real_access = os.access

    def fake_access(p, mode, *args, **kwargs):
        if os.fspath(p) == os.fspath(path) and mode & os.W_OK:
            return False
        return real_access(p, mode, *args, **kwargs)

    monkeypatch.setattr("os.access", fake_access)

    with pytest.raises(PermissionError):
        settings.set("locale", "sv")

    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "en"}
    assert settings.get("locale") == "en"
    assert _dir_entries(config_dir) == [SETTINGS_FILE]


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes")
def test_existing_file_mode_is_preserved(config_dir):
    path = _write_initial(config_dir)
    os.chmod(path, 0o640)
    settings = Settings(testing=True)

    settings.set("locale", "sv")

    assert stat.S_IMODE(os.stat(path).st_mode) == 0o640
    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "sv"}


def _settings_app():
    # In-memory datastore; the only disk state is the settings file in config_dir.
    # Built after the settings file exists, since Settings loads it at startup.
    application = AWFlask("127.0.0.1", testing=True)
    return application, application.test_client()


def test_settings_post_os_error_returns_actionable_500(config_dir, monkeypatch, caplog):
    path = _write_initial(config_dir)
    application, client = _settings_app()

    def no_space(src, dst):
        raise OSError(errno.ENOSPC, "No space left on device", dst)

    monkeypatch.setattr("os.replace", no_space)

    with caplog.at_level(logging.ERROR, logger="aw_server"):
        response = client.post(
            "/api/0/settings/locale",
            json="secret-locale-value",
            headers={"Host": "localhost"},
        )

    assert response.status_code == 500
    body = response.get_json()
    assert "unable to save" in body["message"].lower()
    assert "No space left on device" in body["message"]
    assert str(path) in body["message"]
    assert body["path"] == str(path)
    assert body["errno"] == errno.ENOSPC

    # Nothing was saved: no success response, and the old value still applies.
    assert application.api.get_setting("locale") == "en"
    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "en"}
    # The log names the path and reason but never the value being saved.
    assert str(path) in caplog.text
    assert "secret-locale-value" not in caplog.text


def test_settings_post_success_returns_value(config_dir):
    path = _write_initial(config_dir)
    _, client = _settings_app()

    response = client.post(
        "/api/0/settings/locale",
        json="sv",
        headers={"Host": "localhost"},
    )

    assert response.status_code == 200
    assert response.get_json() == "sv"
    assert json.loads(path.read_text(encoding="utf-8")) == {"locale": "sv"}


def test_concurrent_settings_writes_preserve_both_updates(config_dir, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    _write_initial(config_dir)
    settings = Settings(testing=True)
    writing_first = Event()
    release_first = Event()
    second_started = Event()
    real_write = settings._write

    def controlled_write(data):
        if "first" in data and "second" not in data:
            writing_first.set()
            assert release_first.wait(5)
        real_write(data)

    def second_update():
        second_started.set()
        settings.set("second", "two")

    monkeypatch.setattr(settings, "_write", controlled_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(settings.set, "first", "one")
        assert writing_first.wait(5)
        second = pool.submit(second_update)
        assert second_started.wait(5)
        # Without serialization the second write completes while the first is
        # paused, and the first then overwrites its newer snapshot.
        try:
            second.result(timeout=0.1)
        except TimeoutError:
            pass
        finally:
            release_first.set()
        first.result(timeout=5)
        second.result(timeout=5)
    expected = {"locale": "en", "first": "one", "second": "two"}
    assert settings.get("") == expected
    assert json.loads(_settings_path(config_dir).read_text()) == expected


@pytest.mark.skipif(
    os.name == "nt", reason="symlink creation requires Windows privileges"
)
def test_save_preserves_settings_symlink(config_dir):
    target_dir = config_dir / "managed"
    target_dir.mkdir()
    target = target_dir / "settings.json"
    target.write_text('{"locale": "en"}', encoding="utf-8")
    path = _settings_path(config_dir)
    path.symlink_to(target)
    settings = Settings(testing=True)
    settings.set("locale", "sv")
    assert path.is_symlink()
    assert json.loads(target.read_text()) == {"locale": "sv"}
    assert sorted(p.name for p in target_dir.iterdir()) == ["settings.json"]
