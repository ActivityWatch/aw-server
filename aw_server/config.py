import os

from aw_core.config import load_config_toml

from .profile import DEFAULT_PROFILE, ENV_VAR, TESTING_PROFILE, is_testing

default_config = """
[server]
host = "localhost"
port = "5600"
storage = "peewee"
cors_origins = ""
# Cache query results for finished past periods in memory (see query_cache.py)
query_cache = true

[server.custom_static]

[server.auth]
# Uncomment and set to enable API key authentication for /api/* endpoints.
# Clients must send: Authorization: Bearer <api_key>
# GET /api/0/info and OPTIONS preflight requests are always public.
# api_key = ""

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""
query_cache = true

[server-testing.custom_static]

[server-testing.auth]
# api_key = ""
""".strip()


def _using_legacy_testing_root() -> bool:
    """True when testing data still lives on the shared ``activitywatch/`` root."""
    try:
        from aw_core.dirs import using_legacy_testing_root

        return using_legacy_testing_root()
    except ImportError:
        return os.environ.get(ENV_VAR) == TESTING_PROFILE


def default_config_for(profile: str) -> str:
    """Default TOML for this profile's config file.

    Isolated roots (including a fresh ``activitywatch-testing/``) get a
    single ``[server]`` section — the directory already isolates, and
    ``[server-testing]`` in the same file is the pre-profile model.
    The two-section default stays on the shared root so legacy testing
    still finds ``[server-testing]`` next to prod.
    """
    if profile != DEFAULT_PROFILE and not _using_legacy_testing_root():
        port = default_port(profile)
        return f"""
[server]
host = "localhost"
port = "{port}"
storage = "peewee"
cors_origins = ""

[server.custom_static]
""".strip()
    return default_config


def load_config(profile: str = DEFAULT_PROFILE):
    """Load aw-server.toml from the current profile's config dir.

    Must be called *after* ``export_profile`` so aw-core dirs see
    ``AW_PROFILE`` and isolate the file from other instances.
    """
    return load_config_toml("aw-server", default_config_for(profile))


def config_section(profile: str) -> str:
    """TOML section for this profile.

    Isolated roots use ``[server]``. ``[server-testing]`` remains only
    for the legacy shared-root testing layout (same 3-rule as aw-core#152).
    """
    if profile != DEFAULT_PROFILE and _using_legacy_testing_root():
        return f"server-{profile}"
    return "server"


def default_port(profile: str) -> int:
    """Built-in port: 5666 for testing, 5600 otherwise.

    Named profiles take ``port`` from their own isolated config (the
    research build bakes 5667 into that file). There is no hash-to-port
    table — a custom profile without a port set collides with default.
    """
    return 5666 if is_testing(profile) else 5600
