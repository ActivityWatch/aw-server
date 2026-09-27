from aw_core.config import load_config_toml

from .profile import DEFAULT_PROFILE, is_testing

default_config = """
[server]
host = "localhost"
port = "5600"
storage = "peewee"
cors_origins = ""
# Cache query results for finished past periods in memory (see query_cache.py)
query_cache = true

[server.custom_static]

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""
query_cache = true

[server-testing.custom_static]
""".strip()


def load_config():
    """Load aw-server.toml from the current profile's config dir.

    Must be called *after* ``export_profile`` so aw-core dirs see
    ``AW_PROFILE`` and isolate the file from other instances.
    """
    return load_config_toml("aw-server", default_config)


def config_section(profile: str) -> str:
    """TOML section for this profile: ``server`` or ``server-<profile>``."""
    return "server" if profile == DEFAULT_PROFILE else f"server-{profile}"


def default_port(profile: str) -> int:
    """Built-in port: 5666 for testing, 5600 otherwise.

    Named profiles take ``port`` from their own isolated config (the
    research build bakes 5667 into that file). There is no hash-to-port
    table — a custom profile without a port set collides with default.
    """
    return 5666 if is_testing(profile) else 5600
