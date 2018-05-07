from configparser import ConfigParser

from aw_core.config import load_config

default_config = ConfigParser()
default_config["server"] = {
    "host": "localhost",
    "port": "5600",
    "storage": "peewee",
    "cors_origins": ""
}
default_config["server-testing"] = {
    "host": "localhost",
    "port": "5666",
    "storage": "peewee",
    "cors_origins": ""
}

config = load_config("aw-server", default_config)
