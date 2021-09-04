from aw_core.config import load_config_toml

default_config = """
[server]
host = "localhost"
port = "5600"
storage = "peewee"
cors_origins = ""
custom_watcher_visualizations = "{}"

[server-testing]
host = "localhost"
port = "5666"
storage = "peewee"
cors_origins = ""
custom_watcher_visualizations = "{}"
""".strip()

config = load_config_toml("aw-server", default_config)
