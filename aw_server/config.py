from configparser import ConfigParser

from aw_core import dirs
from aw_core.config import load_config

default_config = ConfigParser()
default_config["server"] = {
    "host": "localhost",
    "port": 5600,
    "storage": "peewee"
}
default_config["server-testing"] = {
    "host": "localhost",
    "port": 5666,
    "storage": "peewee"
}

config = load_config("aw-server", default_config)
