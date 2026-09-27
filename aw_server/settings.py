import json
from pathlib import Path

from aw_core.dirs import get_config_dir

from .profile import profile_from_env, profile_suffix


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
        self.load()

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

    def save(self):
        with open(self.config_file, "w") as f:
            json.dump(self.data, f, indent=4)

    def get(self, key: str, default=None):
        if not key:
            return self.data
        return self.data.get(key, default)

    def set(self, key, value):
        if value:
            self.data[key] = value
        else:
            if key in self.data:
                del self.data[key]
        self.save()
