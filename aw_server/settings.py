import errno
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from threading import Lock

from aw_core.dirs import get_config_dir

from .profile import profile_from_env, profile_suffix

logger = logging.getLogger(__name__)


def _settings_suffix(testing: bool) -> str:
    """Bare ``settings.json`` in isolated roots; ``-testing`` only in legacy."""
    try:
        from aw_core.dirs import legacy_testing_suffix

        return legacy_testing_suffix(testing)
    except ImportError:
        return profile_suffix(profile_from_env(testing=testing))


class Settings:
    def __init__(self, testing: bool):
        # Isolated roots (including new-style activitywatch-testing/) use
        # bare settings.json — the directory already isolates. The
        # settings-testing.json suffix stays so legacy shared-root testing
        # still finds its file next to prod.
        filename = f"settings{_settings_suffix(testing)}.json"
        self.config_file = Path(get_config_dir("aw-server")) / filename
        self._lock = Lock()
        self.load()
        self._warn_if_not_writable()

    def __getitem__(self, key):
        return self.get(key)

    def __setitem__(self, key, value):
        return self.set(key, value)

    def load(self):
        if self.config_file.exists():
            with open(self.config_file) as f:
                self.data = json.load(f)
        else:
            self.data = {}

    def _warn_if_not_writable(self):
        # Best effort only: a warning at startup, never a startup failure.
        if self.config_file.exists() and not os.access(self.config_file, os.W_OK):
            logger.warning(
                f"Settings file is not writable, changes will not be saved: {self.config_file}"
            )

    def save(self):
        with self._lock:
            self._write(self.data)

    def _write(self, data):
        """Replace the settings file with `data` atomically.

        The original file is only replaced once the complete new contents are
        written, flushed and closed, so a failure leaves the old file intact.
        """
        # Preserve managed-config symlinks: replace their target, not the link.
        path = self.config_file.resolve()
        existing = path.exists()
        if existing and not os.access(path, os.W_OK):
            # Respect a deliberately read-only file; os.replace would otherwise
            # succeed where a direct write would not.
            raise PermissionError(errno.EACCES, "Settings file is read-only", str(path))

        tmp_path = None
        try:
            # Same directory, so os.replace is an atomic rename on one filesystem.
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f"{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                tmp_path = f.name
                json.dump(data, f, indent=4)
                f.flush()
                os.fsync(f.fileno())
            if existing:
                shutil.copymode(path, tmp_path)
            # The temp file is closed before the rename, which Windows requires.
            os.replace(tmp_path, path)
        except BaseException:
            if tmp_path is not None:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    # Cleanup must not hide the original persistence failure.
                    pass
            raise

    def get(self, key: str, default=None):
        if not key:
            return self.data
        return self.data.get(key, default)

    def set(self, key, value):
        # Build the new contents separately so a failed save leaves self.data
        # (and any earlier snapshot handed out by get()) unchanged.
        # Flask serves concurrent requests; serialize snapshot, write and commit
        # so independent setting updates cannot overwrite one another.
        with self._lock:
            data = dict(self.data)
            if value:
                data[key] = value
            else:
                data.pop(key, None)
            self._write(data)
            self.data = data
