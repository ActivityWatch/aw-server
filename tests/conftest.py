import logging

import pytest

import aw_server

logging.basicConfig(level=logging.WARN)


@pytest.fixture(scope="session")
def app():
    return aw_server.create_app(testing=True)


@pytest.fixture(scope="session")
def flask_client(app):
    yield app.test_client()
