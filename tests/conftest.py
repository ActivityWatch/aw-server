import logging

import pytest
from aw_server.server import AWFlask

logging.basicConfig(level=logging.WARN)


@pytest.fixture(scope="session")
def app():
    return AWFlask("127.0.0.1", testing=True)


@pytest.fixture(scope="session")
def flask_client(app):
    yield app.test_client()
