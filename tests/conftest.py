import logging

import pytest
from aw_server.server import create_app

logging.basicConfig(level=logging.WARN)


@pytest.fixture(scope="session")
def app():
    return create_app("127.0.0.1", testing=True)


@pytest.fixture(scope="session")
def flask_client(app):
    yield app.test_client()
